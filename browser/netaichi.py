from .jsp import Jsp
from .jsp.selecter import Selecter
from database import NetaichiDatabase, M_CourtProperty, M_Account, T_LotteryData
from sqlmodel import delete, select, SQLModel
import pandas as pd
from datetime import datetime as dd
import re
from .jsp.data import LotteryStatusDetail
from helper import sqmodel_to_df
from dataclasses import asdict
from config import IS_HEADLESS


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

    def __init__(self, is_headless=IS_HEADLESS, logger_name="NetAichi"):
        super().__init__(is_headless, logger_name)
        self.db = NetaichiDatabase(False)

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
                        self.click(Selecter.BTN_APPLY)
                        self.select.sports()
                        self.select.players(4)
                        self.click(Selecter.BTN_CECHK)
                        # self.wait_element_load_by_css(Selecter.LOTTERY_CHECK_COURT)
                        if not self.__check_lottery(g, value, span):
                            continue
                        self.click(Selecter.BTN_CONFIRM)
                        self.alert_switch(True)
                        if self.get_element_by_css(Selecter.LOGIN_ERROR_MESSAGE):
                            self.click(Selecter.BTN_RESELECT_DATE)
                        else:
                            self.click(Selecter.BTN_ANOTHER_DATE)
                    else:
                        print(g)
                        print("time False")
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

        df = sqmodel_to_df(lottery_data)

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
                    self.click(Selecter.BTN_APPLY)
                    self.select.sports()
                    self.select.players(players)
                    self.click(Selecter.BTN_CECHK)
                    # self.wait_element_load_by_css(Selecter.LOTTERY_CHECK_COURT)
                    if not self.__check_lottery(g, value, span):
                        continue
                    self.click(Selecter.BTN_CONFIRM)
                    self.alert_switch(True)
                    if self.get_element_by_css(Selecter.LOGIN_ERROR_MESSAGE):
                        self.click(Selecter.BTN_RESELECT_DATE)
                    else:
                        self.click(Selecter.BTN_ANOTHER_DATE)
                else:
                    print(g)
                    print("time False")
                status = self.get.lottery_status()
                if status.alltime == "810":
                    break
        print(self.get.lottery_status())
        print(self.get.lottery_status_detaill())
        print("-" * 30)

    def __check_lottery(self, data: T_LotteryData, value, span):
        court_name = self.get_element_by_css(Selecter.LOTTERY_CHECK_COURT).text
        # amount = self.get_element_by_css(Selecter.LOTTERY_CHECK_AMOUNT).text
        d = self.get_element_by_css(Selecter.LOTTERY_CHECK_DATE).text
        ds = d.split()
        date = dd.strptime(ds[0][:-3], "%Y年%m月%d日")
        times = re.findall(r"([0-9]{1,2})時", d)
        start = int(times[0])
        end = int(times[1])

        case = None
        if start != data.start:
            cause = "start"
            error_message = f"{data.value} {date} > {data.start} != {start}"

        if end != data.end:
            cause = "end"
            error_message = f"{data.value} {date} > {data.end} != {end}"

        if value != data.value:
            cause = "コート"
            error_message = f"{data.value} != {value}"

        # if amount != lottery.amount:
        #     self.logger.error(
        #         f'面数ミス{self.logged_account} : {lottery.amount} != {amount}'
        #     )
        #     flag = True

        if case:
            self.logger.error(f"{cause}指定ミス {self.logged_account} {error_message}")
            self.click(Selecter.BTN_RESELECT_DATE)
            return False
        return True

    def to_value(self, court_name: str) -> int:
        if self.properties is None:
            with self.db.session() as session:
                self.properties = session.exec(select(M_CourtProperty)).all()

        for p in self.properties:
            if p.name == court_name:
                return p.value

    def update_court_propreties(self) -> list[M_CourtProperty]:
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
            new_lotterys = [T_LotteryData(**lottery) for lottery in self.get.lottery()]
            session.add_all(new_lotterys)
            session.commit()
