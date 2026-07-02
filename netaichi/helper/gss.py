from oauth2client.service_account import ServiceAccountCredentials
import gspread
import pandas as pd
from gspread_dataframe import set_with_dataframe
from netaichi.config import GSS_KEYFILE
from dataclasses import dataclass
from netaichi.db import M_Account


class SpreadSheet:

    def __init__(self, id: str) -> None:
        scope = ['https://spreadsheets.google.com/feeds',
                 'https://www.googleapis.com/auth/drive']
        credentials = ServiceAccountCredentials.from_json_keyfile_name(
            GSS_KEYFILE, scope)
        self.client = gspread.authorize(credentials)
        self.workbook_id = id
        self.open_workbook()

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
