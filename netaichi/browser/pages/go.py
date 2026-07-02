from collections.abc import Generator
from typing import TYPE_CHECKING

from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from netaichi.helper import random_sleep

from .data import PAGE_STATUS
from .selector import Selector

if TYPE_CHECKING:
    from .base import Jsp


class JspGo:
    last_page = None

    def __init__(self, jsp) -> None:
        self.jsp: Jsp = jsp

    def __status_update(self, status: PAGE_STATUS):
        self.last_page = status
        return status

    @random_sleep
    def login(self) -> PAGE_STATUS:
        self.jsp.go_page(self.jsp.BASE_URL)
        self.jsp.click(Selector.GO_LOGIN)
        return self.__status_update(PAGE_STATUS.MYPAGE)

    @random_sleep
    def mypage(self) -> object:
        if self.last_page == PAGE_STATUS.MYPAGE:
            return self
        WebDriverWait(self.jsp.driver, 5).until(EC.presence_of_all_elements_located)
        self.jsp.click(Selector.GO_MYPAGE, 1)
        self.__status_update(PAGE_STATUS.MYPAGE)
        return self

    @random_sleep
    def lottery(self) -> PAGE_STATUS:
        if self.last_page == PAGE_STATUS.LOTTERY:
            return self.last_page
        if self.last_page != PAGE_STATUS.MYPAGE:
            self.mypage()
        self.jsp.click(Selector.GO_LOTTERY)
        return self.__status_update(PAGE_STATUS.LOTTERY)

    @random_sleep
    def reservation(self) -> PAGE_STATUS:
        if self.last_page == PAGE_STATUS.RESERVATION:
            return self.last_page
        if self.last_page != PAGE_STATUS.MYPAGE:
            self.mypage()
        self.jsp.click(Selector.GO_RESERVATION)
        return self.__status_update(PAGE_STATUS.RESERVATION)

    @random_sleep
    def lottery_list(self) -> Generator[int]:
        if self.last_page != PAGE_STATUS.MYPAGE:
            self.mypage()
        self.jsp.click(Selector.GO_LIST, 1)
        self.last_page = PAGE_STATUS.LOTTERY_LIST
        return self.__loop_list()

    @random_sleep
    def reservation_list(self) -> Generator[int]:
        if self.last_page != PAGE_STATUS.MYPAGE:
            self.mypage()
        self.jsp.click(Selector.GO_LIST, 0)
        self.last_page = PAGE_STATUS.RESERVATION_LIST
        return self.__loop_list()

    def back_lottery(self) -> PAGE_STATUS:
        self.__back_lottery()
        self.__back_lottery2()
        return self.__status_update(PAGE_STATUS.LOTTERY)

    @random_sleep
    def __back_lottery(self):
        self.jsp.click(Selector.BTN_REVERSE)

    @random_sleep
    def __back_lottery2(self):
        self.jsp.click(Selector.BTN_REVERSE2)

    @random_sleep
    def __loop_list(self) -> Generator[int]:
        page_index = 1
        yield page_index
        while self.jsp.get_html().select(Selector.LIST_NEXT) != []:
            page_index += 1
            self.jsp.js_exec(f"movePage({page_index});")
            yield page_index

    def change_calendar_date(self, date):
        str_date = date.strftime("%Y,%m,%d")
        self.jsp.js_exec(f"selectCalendarDate({str_date})")
