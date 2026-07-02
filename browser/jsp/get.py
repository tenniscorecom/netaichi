from .message import InfoMessage, ErrorMessage
from .selecter import Selecter
from .data import LotteryStatusDetail, LotteryStatus
from database import T_LotteryData
from unicodedata import normalize
import pandas as pd
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .base import Jsp


class JspGet:
    def __init__(self, jsp) -> None:
        self.jsp: Jsp = jsp

    def court_properties(self) -> list[dict]:
        self.jsp.go.lottery()
        soup = self.jsp.get_html()
        inputs = soup.select(".s-242 > input")
        names = soup.select(".s-242")[0].stripped_strings

        courts = []
        for i, name in zip(inputs, names):
            temp = {}
            value = i["value"]
            if int(value) in self.jsp.USE_COURTS:
                temp |= {
                    "name": name,
                    "value": value,
                }
                self.jsp.select.court(value)
                times = self.jsp.get.times()

                start = times[0]
                end = times[-1]
                diffs = [times[i] - times[i + 1] for i in range(len(times) - 1)]
                if len(set(diffs)) == 1:
                    span = abs(diffs[0])
                else:
                    raise Exception(
                        ErrorMessage.PROPERTY_MULTIPLE_TIME.format(value, times)
                    )
                temp |= {"start": start, "end": end, "span": span}
                courts.append(temp)
                self.jsp.click(Selecter.BTN_REVERSE)
                self.jsp.click(Selecter.BTN_REVERSE2)
        return courts

    def reservation(self) -> pd.DataFrame:
        if self.amount_reserve() is False:
            return pd.DataFrame()
        # self.jsp.go.reservation()
        temp = []
        for i in self.jsp.go.reservation_list():
            soup = self.jsp.get_html()
            dates = soup.select(Selecter.RESERVE_DATA_DATE)
            courts = soup.select(Selecter.RESERVE_DATA_COURT)
            if len(dates) != len(courts):
                raise RuntimeError(ErrorMessage.RESERVATION_DATA)
            for i in range(len(dates)):
                date_split = normalize("NFKD", dates[i].text).split(" ")
                court_split = normalize("NFKD", courts[i].text).split(" ")
                date = self.jsp.to_datetime(date_split[0])
                # week = date_split[1]
                start = date_split[2].removesuffix("時")
                end = date_split[4].removesuffix("時")
                court = court_split[0]
                court_number = court_split[2][
                    court_split[2].find("場") + 1 : court_split[2].find("(")
                ]
                temp.append(
                    {
                        "court": court,
                        "court_number": court_number,
                        "date": date,
                        "start": start,
                        "end": end,
                        "account": self.jsp.logged_account.id,
                    }
                )
        return pd.DataFrame(temp)

    def lottery(self) -> list[dict]:
        if self.amount_lottery() is False:
            return []
        temp = []
        for _ in self.jsp.go.lottery_list():
            soup = self.jsp.get_html()
            dates = soup.select(Selecter.LOTTERY_DATA_DATE)
            starts = soup.select(Selecter.LOTTERY_DATA_START)
            ends = soup.select(Selecter.LOTTERY_DATA_END)
            courts = soup.select(Selecter.LOTTERY_DATA_COURT)
            amounts = soup.select(Selecter.LOTTERY_DATA_AMOUNT)
            for i in range(len(dates)):
                date = self.jsp.to_datetime(dates[i].text[:-3])
                start = starts[i].text.removesuffix("時")
                end = ends[i].text.removesuffix("時")
                court_name = courts[i].text
                value = self.jsp.to_value(court_name)
                amount = int(amounts[i].text)
                self.jsp.logger.info(
                    InfoMessage.LOTTERY_DATA_DETAILS.format(
                        date, court_name, start, end, amount
                    )
                )
                print(value)
                temp.append(
                    {
                        "value": value,
                        "date": date,
                        "start": start,
                        "end": end,
                        "amount": amount,
                        "account_group": self.jsp.logged_account.id,
                    }
                )

        return temp

    def amount_lottery(self) -> int:
        return self.__get_amount()[1]

    def amount_reserve(self) -> int:
        return self.__get_amount()[0]

    def __get_amount(self) -> list[int]:
        self.jsp.go.mypage()
        eles = self.jsp.get_elements_by_css(Selecter.AMOUNT_RESERVE)
        if eles:
            return [int(e.text) for e in eles]
        else:
            raise "not get mypage amount"

    def lottery_status(self) -> LotteryStatus:
        self.jsp.go.lottery()
        alltime = self.jsp.get_element_by_css(Selecter.STATUS_ALL).text
        zone = self.jsp.get_element_by_css(Selecter.STATUS_ZONE).text
        count = self.jsp.get_element_by_css(Selecter.STATUS_COUNT).text
        status = LotteryStatus(
            count=count,
            zone=zone,
            alltime=alltime,
            account_id=self.jsp.logged_account_id,
        )

        return status

    def lottery_status_detaill(self):
        """
        [name,count,value=0],....
        """
        self.jsp.go.lottery()
        soup = self.jsp.get_html()
        dl = soup.select_one(".smenu > dl")
        court_names = dl.select("dt")
        court_counts = dl.select("dd")
        data = []

        for name, count in zip(court_names, court_counts):
            name = name.text
            if name == "申し込み合計":
                continue

            value = self.jsp.to_value(name)
            data.append(
                LotteryStatusDetail(
                    name=name,
                    count=int(count.text.split("件")[0]),
                    value=value,
                )
            )
        return data

    def expiration_date(self):
        pass

    def error_message(self, selecter) -> None | str:
        em = self.jsp.get_element_by_css(selecter)
        if not em:
            return None
        return em.text

    def times(self):
        times = [
            int(normalize("NFKC", time.text[:-2]))
            for time in self.jsp.get_elements_by_css(Selecter.TIMES)
        ]

        return times
