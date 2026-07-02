from netaichi.db import M_Account
from .select import JspSelect
from .get import JspGet
from .go import JspGo
from netaichi.browser.chrome import ChromeBrowser
from datetime import datetime
from dateutil.relativedelta import relativedelta
from netaichi.config import default_pw
from .selector import Selector
from .message import SystemMessage, ErrorMessage
from collections.abc import Generator


class Jsp(ChromeBrowser):
    BASE_URL = ""
    LOTTERY_MONTHS = 0
    logged_account = None
    DATE_TEMP = "%Y年%m月%d日"

    def __init__(self, is_headless: bool, logger_name: str = "JspBase") -> None:
        super().__init__(is_headless, logger_name)
        self.go: JspGo = JspGo(self)
        self.get: JspGet = JspGet(self)
        self.select: JspSelect = JspSelect(self)
        self.lottery_date = self.today + relativedelta(months=self.LOTTERY_MONTHS)

    @property
    def logged_account_id(self) -> str:
        return self.logged_account.id

    @property
    def is_logged(self) -> bool:
        return bool(self.logged_account)

    def login(
        self,
        id: str = "",
        password: str = default_pw,
        name: str = "",
        account: M_Account = None,
    ) -> bool:
        def send_login_form():
            self.send_form(Selector.LOGIN_ID, account.id)
            self.send_form(Selector.LOGIN_PW, account.password)

        if account is None:
            account = M_Account(name=name, id=id, password=password)

        if self.is_logged:
            if self.logged_account_id == account.id:
                self.go.mypage()
            else:
                self.logout()
        self.go.login()
        send_login_form()
        self.click(Selector.BTN_LOGIN)
        self.driver.implicitly_wait(3)
        error_message = self.get.error_message(Selector.LOGIN_ERROR_MESSAGE)
        match error_message:
            case SystemMessage.ERROR_BOT:
                send_login_form()
                input("ReCAPTCHA")
            case SystemMessage.ERROR_INCORECT:
                self.logger.error(ErrorMessage.INCORRECT)
                return False
            case SystemMessage.ERROR_EXPIRATION:
                self.logger.error(SystemMessage.ERROR_EXPIRATION)
                return False
            case None:
                pass
            case _:
                self.logger.error(error_message)
                return False

        self.logged_account = account
        self.logger.info(f"{account.id}にログインしました。")
        return True

    def logout(self) -> bool:
        if self.is_logged:
            self.click(Selector.BTN_LOGOUT)
            self.logged_account = None
            return True
        return False

    def next_date(self) -> Generator[datetime, None, None]:
        tmp_date = self.lottery_date
        while tmp_date.month == self.lottery_date.month:
            yield tmp_date
            tmp_date += relativedelta(days=1)

    def to_datetime(self, text_date: str):
        return datetime.strptime(text_date, self.DATE_TEMP)
