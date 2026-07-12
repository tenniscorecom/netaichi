import json
import os
from datetime import datetime
from time import sleep

import gspread
import pandas as pd
from dataclasses import dataclass
from gspread_dataframe import set_with_dataframe
from oauth2client.service_account import ServiceAccountCredentials

from netaichi.config import GSS_KEYFILE
from netaichi.db import M_Account


def retry_api_error(func):
    """Sheets APIの一時的なエラー（5xx等）なら少し待ってリトライする"""
    def _wrapper(*args, **kwargs):
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                return func(*args, **kwargs)
            except gspread.exceptions.APIError as e:
                # 4xxは何度やっても失敗するのでリトライしない
                if 400 <= e.code < 500 or attempt == max_attempts:
                    raise
                sleep(15 * attempt)
    return _wrapper


class SpreadSheet:

    def __init__(self, id: str) -> None:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        creds_json = os.environ.get('GSS_CREDENTIALS_JSON')
        if creds_json:
            credentials = ServiceAccountCredentials.from_json_keyfile_dict(
                json.loads(creds_json), scope)
        else:
            credentials = ServiceAccountCredentials.from_json_keyfile_name(
                GSS_KEYFILE, scope)
        self.client = gspread.authorize(credentials)
        self.workbook_id = id
        self.open_workbook()

    @retry_api_error
    def open_workbook(self):
        self.WORKBOOK = self.client.open_by_key(self.workbook_id)
        self.account_sheet = self.WORKBOOK.worksheet(Sheets.ACCOUNT)
        self.reserve_sheet = self.WORKBOOK.worksheet(Sheets.RESERVE)
        return self.WORKBOOK

    def __to_maccount(self, df: pd.DataFrame) -> list[M_Account]:
        temp = []
        for i, d in df.iterrows():
            name = d[Headers.NAME]
            id = d[Headers.ID]
            password = d[Headers.PASSWORD]
            expiration_date = d[Headers.EXPIRATION]
            group = d[Headers.GROUP]
            temp.append(M_Account(name=name, id=id,
                        password=password, expiration_date=expiration_date, account_group=group))
        return temp

    def get_use_accounts(self, group_id: str) -> list[M_Account]:
        df = self.get_all_accounts()
        group_df = df[df[Headers.GROUP] == group_id]
        group_df[Headers.EXPIRATION] = pd.to_datetime(
            group_df[Headers.EXPIRATION])
        accounts = self.__to_maccount(group_df)
        for i, v in enumerate(accounts):
            if v.id == group_id:
                accounts[i].is_master = True

        return accounts

    def get_all_accounts(self):
        df = pd.DataFrame(self.account_sheet.get_values()[
                          1:], columns=self.account_sheet.get_values()[0])
        return df

    def add_account(self, name, id, password, group_id, expiry_date=None) -> bool:
        self.account_sheet.append_row(
            [name, id, password, expiry_date, group_id])
        return True

    def delete_account(self, id) -> bool:
        cell = self.account_sheet.find(id)
        if cell:
            self.account_sheet.delete_rows(cell.row)
            return True
        return False

    def update_account(self, id, **kwargs):
        cell = self.account_sheet.find(id)
        if cell:
            headers = self.account_sheet.row_values(1)
            for key, value in kwargs.items():
                if key in headers:
                    col = headers.index(key) + 1
                    self.account_sheet.update_cell(cell.row, col, value)
            return True
        return False

    def replace_all(self, sheet, df):
        set_with_dataframe(sheet, df, allow_formulas=False)

    def _get_or_create_sheet(self, name: str, cols: int = 5) -> gspread.Worksheet:
        try:
            return self.WORKBOOK.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            sheet = self.WORKBOOK.add_worksheet(title=name, rows=2000, cols=cols)
            return sheet

    @retry_api_error
    def get_current_slots(self, sheet_name: str = None) -> list[dict]:
        """前回チェック時点の空き枠一覧を返す"""
        sheet = self._get_or_create_sheet(sheet_name or Sheets.AVAILABILITY)
        rows = sheet.get_all_values()
        result = []
        for row in rows:
            if len(row) >= 4 and row[0]:
                try:
                    result.append({
                        "value": row[0],
                        "date": datetime.strptime(row[1], "%Y-%m-%d"),
                        "start": int(row[2]),
                        "end": int(row[3]),
                        "facility": row[4] if len(row) > 4 else "",
                    })
                except (ValueError, IndexError):
                    pass
        return result

    @retry_api_error
    def set_current_slots(self, slots: list[dict], sheet_name: str = None) -> None:
        """シートを今回の空き枠で上書きする（clear→writeの順でアトミックに近い形で実行）"""
        sheet = self._get_or_create_sheet(sheet_name or Sheets.AVAILABILITY)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if not slots:
            sheet.clear()
            return
        rows = [
            [s["value"], s["date"].strftime("%Y-%m-%d"), str(s["start"]), str(s["end"]),
             s.get("facility", ""), now]
            for s in slots
        ]
        # 既存行数より多い場合に備えてリサイズしてからupdate（clear不要でwindowを最小化）
        sheet.resize(rows=len(rows) + 1)
        sheet.clear()
        sheet.append_rows(rows)


@dataclass
class Headers:
    NAME = '名前'
    ID = 'ID'
    PASSWORD = 'パスワード'
    EXPIRATION = '有効期限'
    GROUP = 'グループ'


@dataclass
class Sheets:
    ACCOUNT = 'アカウント一覧'
    RESERVE = '予約情報'
    LOTTERY = '抽選情報'
    AVAILABILITY = '通知済み空き'
