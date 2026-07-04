from .pages import Jsp
from .pages.selector import Selector
from netaichi.db import NetaichiDatabase, M_CourtProperty, T_LotteryData
from sqlmodel import delete, select
from selenium.webdriver.common.by import By
import pandas as pd
from datetime import datetime as dd
import re
import time
from netaichi.helper import sqlmodel_to_df
from netaichi.config import IS_HEADLESS


class NetAichi(Jsp):
    BASE_URL = "https://www4.pref.aichi.jp/yoyaku/"
    LOTTERY_MONTHS = 3
    DATE_TEMP = "%Y年%m月%d日"
    USE_COURTS = [
        130,
        180,
        310,
        320,
        400,
        410,
        530,
        540,
        550,
        660,
    ]
    properties = None

    def __init__(self, is_headless=IS_HEADLESS, logger_name="NetAichi", dry_run=False):
        super().__init__(is_headless, logger_name)
        self.db = NetaichiDatabase(False)
        # Trueの場合、抽選確認画面まで進むが確定はしない
        self.dry_run = dry_run

    def add_lottery(self, df: pd.DataFrame):
        for value, group in df.groupby("value"):
            self.go.mypage().lottery()
            self.select.court(value)

            for g in group.itertuples():
                self.go.change_calendar_date(g.date)
                self.select.amount(g.amount)
                span = 2
                try:
                    if self.select.time(g.start, g.end, span):
                        self.click(Selector.BTN_APPLY)
                        self.select.sports()
                        self.select.players(4)
                        self.click(Selector.BTN_CHECK)
                        if not self.__check_lottery(g):
                            continue
                        if self.dry_run:
                            self.logger.info(f"[dry-run] 確定せずスキップ: {g}")
                            # 確認画面 → 設定画面 → 日時選択画面 の順に戻る
                            self.click(Selector.BTN_TO_SETTING)
                            self.click(Selector.BTN_RESELECT_DATE)
                            continue
                        self.click(Selector.BTN_CONFIRM)
                        self.alert_switch(True)
                        if self.get_element_by_css(Selector.LOGIN_ERROR_MESSAGE):
                            self.click(Selector.BTN_RESELECT_DATE)
                        else:
                            self.click(Selector.BTN_ANOTHER_DATE)
                    else:
                        self.logger.warning(f"時間帯を選択できませんでした: {g}")
                except Exception as e:
                    self.logger.error(f"Error adding lottery: {e}")

    def run_lottery(self, master_id: str, players: int = 4):
        with self.db.session() as session:
            lottery_data = session.exec(
                select(T_LotteryData).where(
                    T_LotteryData.account_group == master_id,
                    T_LotteryData.created_at >= self.today,
                )
            ).all()

        df = sqlmodel_to_df(lottery_data)

        for value, group in df.groupby("value"):
            self.go.mypage().lottery()

            r = self.select.court(value)
            if r is False:
                continue
            for g in group.itertuples():
                self.go.change_calendar_date(g.date)
                self.select.amount(g.amount)
                span = 2

                if self.select.time(g.start, g.end, span):
                    self.click(Selector.BTN_APPLY)
                    self.select.sports()
                    self.select.players(players)
                    self.click(Selector.BTN_CHECK)
                    if not self.__check_lottery(g):
                        continue
                    if self.dry_run:
                        self.logger.info(f"[dry-run] 確定せずスキップ: {g}")
                        self.click(Selector.BTN_RESELECT_DATE)
                        continue
                    self.click(Selector.BTN_CONFIRM)
                    self.alert_switch(True)
                    if self.get_element_by_css(Selector.LOGIN_ERROR_MESSAGE):
                        self.click(Selector.BTN_RESELECT_DATE)
                    else:
                        self.click(Selector.BTN_ANOTHER_DATE)
                else:
                    self.logger.warning(f"時間帯を選択できませんでした: {g}")
                status = self.get.lottery_status()
                if status.alltime == "810":
                    break
        self.logger.info(self.get.lottery_status())
        self.logger.info(self.get.lottery_status_detail())

    def __check_lottery(self, data: T_LotteryData) -> bool:
        """抽選確認画面の表示内容が申込データと一致するか検証する"""
        court_name = self.get_element_by_css(Selector.LOTTERY_CHECK_COURT).text
        d = self.get_element_by_css(Selector.LOTTERY_CHECK_DATE).text
        ds = d.split()
        date = dd.strptime(ds[0][:-3], "%Y年%m月%d日")
        times = re.findall(r"([0-9]{1,2})時", d)
        start = int(times[0])
        end = int(times[1])
        page_value = self.to_value(court_name)

        cause = None
        if start != data.start:
            cause = "開始時刻"
            error_message = f"{data.value} {date} > {data.start} != {start}"
        if end != data.end:
            cause = "終了時刻"
            error_message = f"{data.value} {date} > {data.end} != {end}"
        if page_value != data.value:
            cause = "コート"
            error_message = f"{data.value} != {page_value} ({court_name})"

        if cause:
            self.logger.error(f"{cause}指定ミス {self.logged_account} {error_message}")
            self.click(Selector.BTN_RESELECT_DATE)
            return False
        return True

    def find_available_slots(
        self, park_keyword: str, dates: list, court_filter: list[str] | None = None
    ) -> list[dict]:
        """施設名検索の空き状況ページから、各日付の空き時間帯を収集する

        Args:
            park_keyword: 施設名検索のキーワード（例: 大高緑地）
            dates: チェック対象の日付リスト
            court_filter: 施設名にこのいずれかを含むもののみ対象
                          （テニス以外の野球場などを除外する）
        """
        if court_filter is None:
            court_filter = ["庭球場", "テニス", "コート"]

        if not self.__search_and_select_park(park_keyword):
            return []

        slots = []
        for date in dates:
            # ページ状態が壊れた場合（selectCalendarDate未定義等）は
            # 施設検索からやり直して1回だけリトライする
            for attempt in range(2):
                try:
                    self.go.change_calendar_date(date)
                    day_slots = self.__parse_vacant_slots(park_keyword, date, court_filter)
                    self.logger.debug(f"{park_keyword} {date:%Y-%m-%d}: {len(day_slots)}件")
                    slots += day_slots
                    break
                except Exception as e:
                    self.logger.error(f"空き取得エラー {park_keyword} {date:%Y-%m-%d}: {e}")
                    if attempt == 0:
                        self.logger.info(f"{park_keyword}: 施設検索からやり直します")
                        if not self.__search_and_select_park(park_keyword):
                            return slots
        self.logger.info(f"{park_keyword} 合計取得: {len(slots)}件 (filter={court_filter})")
        return slots

    def __search_and_select_park(self, park_keyword: str) -> bool:
        """施設名検索でparkを選択し、空き状況ページを開く"""
        if not self.__go_name_search():
            self.logger.error("施設名検索ページに移動できませんでした")
            return False
        self.send_form("#textKeyword", park_keyword)
        self.click('input[value="上記の内容で検索する"]')
        if self.click('input[value="選択"]') is False:
            self.logger.warning(f"施設が見つかりませんでした: {park_keyword}")
            return False
        return True

    def __go_name_search(self) -> bool:
        """「施設名から探す」ページへ移動する（マイページ/検索系ページの両方に対応）"""
        elements = self.get_elements_by_css("#goNameSearch")
        if not elements:
            elements = self.get_elements_by_contains_text("//a", "施設名から探す")
        if not elements:
            return False
        elements[0].click()
        return True

    def __parse_vacant_slots(
        self, park_keyword: str, date, court_filter: list[str]
    ) -> list[dict]:
        """表示中の空き状況ページ（全ページ分）から空き枠を抽出する

        各時間帯セルの構造:
          <td><div><img alt="空き"><input name="selectInfo"
              value="館cd:施設cd:YYYYMMDD:...:0900:1000:..."></div></td>
        """
        slots = []
        seen = set()
        # 前の日付のパースでページ送りした位置が残っていることがあるため、
        # 必ず1ページ目に戻してから読み始める（ページャがない施設では何もしない）
        self.js_exec("if (typeof movePage === 'function') { movePage(1); }")
        for page in range(1, 11):  # 無限ループ防止
            if page > 1:
                self.js_exec(f"movePage({page});")
            soup = self.get_html()

            # 施設cd → 施設名（サイドバーのチェックボックスから取得）
            names = {}
            for cb in soup.select('input[name="chkIcd"]'):
                label = cb.find_parent("label")
                if label:
                    names[cb.get("value")] = label.get_text(strip=True)

            for info in soup.select('input[name="selectInfo"]'):
                parts = (info.get("value") or "").split(":")
                if len(parts) < 6:
                    continue
                icd = parts[1]
                start, end = parts[4], parts[5]
                facility = names.get(icd, "")
                if not any(f in facility for f in court_filter):
                    continue
                div = info.find_parent("div")
                img = div.find("img") if div else None
                if img is None or img.get("alt") != "空き":
                    continue
                key = (icd, start)
                if key in seen:
                    continue
                seen.add(key)
                slots.append(
                    {
                        "value": park_keyword,
                        "date": date,
                        "start": int(start) // 100,
                        "end": int(end) // 100,
                        "facility": facility,
                    }
                )
            if not soup.select("#goNextPager"):
                break
        return slots

    def cancel_reservation(self, date: dd, start: int, court_keyword: str) -> bool:
        """予約状況の一覧から (日付, 開始時, コート) 一致の予約を取り消す

        「取消」ボタン押下で出る確認ダイアログをOKして確定する。
        キャンセル限界日を過ぎていると取消ボタンが無く、Falseを返す。
        """
        self.go.mypage()
        link = self.get_element_by_contains_text("//a", "予約状況の一覧")
        if link is None:
            self.logger.error("「予約状況の一覧」リンクが見つかりません")
            return False
        link.click()
        time.sleep(2)

        for page in range(1, 12):
            buttons = self.get_elements_by_css('input[value="選択"]')
            for btn in buttons:
                tr = btn.find_element(By.XPATH, "./ancestor::tr[1]")
                txt = " ".join(tr.text.split())
                m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{1,2})時", txt)
                if not m:
                    continue
                y, mo, d, h = map(int, m.groups())
                if dd(y, mo, d) == date and h == start and court_keyword in txt:
                    btn.click()
                    time.sleep(2)
                    cancel_btn = self.get_element_by_css('input[value="取消"]')
                    if cancel_btn is None:
                        self.logger.error(
                            f"取消ボタンがありません（限界日超過の可能性）: "
                            f"{date:%Y-%m-%d} {start}時 {court_keyword}"
                        )
                        return False
                    cancel_btn.click()
                    self.alert_switch(True)  # 確認ダイアログでOK＝取消確定
                    time.sleep(2)
                    self.logger.info(
                        f"予約を取消しました: {date:%Y-%m-%d} {start}時 {court_keyword}"
                    )
                    return True
            nxt = self.get_elements_by_css("#goNextPager")
            if nxt and nxt[0].is_displayed():
                self.js_exec(f"movePage({page + 1});")
                time.sleep(2)
            else:
                break
        self.logger.warning(
            f"該当予約が見つかりません: {date:%Y-%m-%d} {start}時 {court_keyword}"
        )
        return False

    def to_value(self, court_name: str) -> int:
        if self.properties is None:
            with self.db.session() as session:
                self.properties = session.exec(select(M_CourtProperty)).all()

        for p in self.properties:
            if p.name == court_name:
                return p.value

    def update_court_properties(self) -> list[M_CourtProperty]:
        with self.db.session() as session:
            courts = session.exec(select(M_CourtProperty)).all()
            if courts == []:
                new_properties = [
                    M_CourtProperty(**c) for c in self.get.court_properties()
                ]
                session.add_all(new_properties)
                session.commit()
                return new_properties

            update_courts = []
            for court in courts:
                if court.updated_at < self.today:
                    update_courts.append(court)
            if update_courts == []:
                return courts

            new_properties = [M_CourtProperty(**c) for c in self.get.court_properties()]
            for uc in update_courts:
                old = session.exec(
                    select(M_CourtProperty).where(M_CourtProperty.value == uc.value)
                ).one()
                for np in new_properties:
                    if np.value == old.value:
                        old.name = np.name
                        old.start = np.start
                        old.end = np.end
                        old.span = np.span
                        session.add(old)
                session.commit()

            return new_properties

    def update_lottery_data(self) -> list[T_LotteryData]:
        with self.db.session() as session:
            session.exec(
                delete(T_LotteryData).where(
                    T_LotteryData.account_group == self.logged_account_id,
                    T_LotteryData.created_at >= self.today,
                )
            )
            new_lotteries = [T_LotteryData(**lottery) for lottery in self.get.lottery()]
            session.add_all(new_lotteries)
            session.commit()
            return new_lotteries
