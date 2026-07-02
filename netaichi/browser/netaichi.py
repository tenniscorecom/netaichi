from .pages import Jsp
from .pages.selector import Selector
from netaichi.db import NetaichiDatabase, M_CourtProperty, T_LotteryData
from sqlmodel import delete, select
import pandas as pd
from datetime import datetime as dd
import re
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
