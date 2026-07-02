from dataclasses import dataclass
from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.select import Select
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.webelement import WebElement

from datetime import datetime
from selenium.webdriver import Chrome as WebDriver

# 自作モジュール
from netaichi.config import OPTIONS
from netaichi.helper import AppLogger, random_sleep


class ChromeBrowser:
    today = datetime.today().replace(day=1)

    def __init__(
        self,
        is_headless: bool,
        logger_name: str = "ChromeBrowser",
        user_data_dir: str | None = None,
    ) -> None:
        self.driver = None
        self.is_headless = is_headless
        self.logger = AppLogger(logger_name)
        self.wait = None
        # 指定するとCookie/セッションが永続化され、次回ログインを省略できる
        self.user_data_dir = user_data_dir

    def __enter__(self):
        self.new()
        self.js_exec("delete Object.getPrototypeOf(navigator).webdriver;")
        return self

    def __exit__(self, ex_type, ex_value, trace):
        self.quit()

    def new(self) -> WebDriver:
        # ------ ChromeDriver のオプション ------
        options = webdriver.ChromeOptions()
        # config.seleniumでオプション設定
        for o in OPTIONS:
            # プロファイル永続化時はシークレットモードと併用できない
            if self.user_data_dir and o == "--incognito":
                continue
            options.add_argument(o)
        if self.user_data_dir:
            options.add_argument(f"--user-data-dir={self.user_data_dir}")
        if self.is_headless:
            options.add_argument("--headless=new")
        # Chromeは自動テスト ソフトウェア~~ ｜ コンソールに表示されるエラー　を非表示
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation", "enable-logging"]
        )
        # 暗黙の待機タイムアウト
        options.timeouts = {"implicit": 5000}
        self.driver = webdriver.Chrome(options=options)
        self.wait = WebDriverWait(self.driver, 10)
        return self.driver

    def quit(self) -> None:
        if self.driver:
            self.driver.quit()

    @random_sleep
    def go_page(self, url: str) -> None:
        self.driver.get(url)
        self.driver.execute_script(
            """delete Object.getPrototypeOf(navigator).webdriver;"""
        )

    def get_elements(
        self, selector: str, type: str = By.CSS_SELECTOR, base: WebElement | None = None
    ):
        if base:
            res = base.find_elements(type, selector)
        else:
            res = self.driver.find_elements(type, selector)
        if res:
            return res
        return []

    def get_element(
        self, selector: str, type: str, index: int, base: WebElement | None = None
    ):
        elements = self.get_elements(selector, type, base)
        if not elements or len(elements) <= index:
            self.logger.error(BrowserError.NO_SUCH.format(selector))
            return None
        return elements[index]

    def get_elements_by_css(
        self, css_selector: str, base: WebElement | None = None
    ) -> list[WebElement]:
        return self.get_elements(css_selector, By.CSS_SELECTOR, base)

    def get_element_by_css(
        self, css_selector: str, index: int = 0, base: WebElement | None = None
    ) -> WebElement:
        return self.get_element(css_selector, By.CSS_SELECTOR, index, base)

    def get_elements_by_contains_text(
        self, path: str, text: str, base: WebElement | None = None
    ) -> list[WebElement]:
        xpath = f".{path}[contains(text(), '{text}')]"
        return self.get_elements(xpath, By.XPATH, base)

    def get_element_by_contains_text(
        self, path: str, text: str, index: int = 0, base: WebElement | None = None
    ) -> WebElement:
        xpath = f".{path}[contains(text(), '{text}')]"
        return self.get_element(xpath, By.XPATH, index, base)

    def get_element_by_xpath(
        self, xpath, index: int = 0, base: WebElement | None = None
    ):
        return self.get_element(xpath, By.XPATH, index, base)

    def get_elements_by_xpath(self, xpath, base: WebElement | None = None):
        return self.get_elements(xpath, By.XPATH, base)

    @random_sleep
    def get_html(self) -> BeautifulSoup:
        return BeautifulSoup(self.driver.page_source, "lxml")

    @property
    def current_url(self) -> str:
        return self.driver.current_url

    def select_by_index(self, select_element: WebElement, index: int) -> None:
        Select(select_element).select_by_index(index)

    def select_by_value(self, select_element: WebElement, value: str) -> None:
        Select(select_element).select_by_value(value)

    def select_by_visible_text(self, select_element: WebElement, text: str) -> None:
        Select(select_element).select_by_visible_text(text)

    @random_sleep
    def send_form(self, selector, value):
        form = self.get_element_by_css(
            selector,
        )
        if form:
            form.clear()
            form.send_keys(value)
        else:
            self.logger.error(BrowserError.BASE_NO_FORM.format(selector))

    def select_radio_by_value(self, value):
        radio = self.get_element_by_css(f'input[value="{value}"]')
        radio.send_keys(Keys.SPACE)

    def select_pulldown(self, selector: str, index: int):
        self.select_by_index(self.get_element_by_css(selector), index - 1)

    @random_sleep
    def click(self, selector, index=0) -> bool:
        ele = self.get_element_by_css(selector, index)
        if ele is None:
            return False
        ele.click()
        return True

    @random_sleep
    def alert_switch(self, bool: bool):
        self.wait_alert(3)
        if bool is True:
            self.driver.switch_to.alert.accept()
        else:
            self.driver.switch_to.alert.dismiss()

    def wait_alert(self, second=3):
        WebDriverWait(self.driver, second).until(EC.alert_is_present())

    def wait_element_load_by_css(self, selector):
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))

    @random_sleep
    def js_exec(self, code: str) -> None:
        self.driver.execute_script(code)

    @random_sleep
    def drag_and_drop(self, source: WebElement, target: str) -> None:
        """ドラッグアンドドロップする関数

        Args:
            source (WebElement): ドラッグ対象のWebElement
            target (str): ドロップ先のWebElement
        """
        actions = ActionChains(self.driver)
        actions.drag_and_drop(source, target)
        actions.perform()

    @random_sleep
    def scroll_into_view(self, target: str, block: str = "start") -> None:
        """要素が可視範囲までスクロールする関数

        Args:
            target (str): 対象のWebElement
            block (str, optional): 垂直範囲の指定('start'、'center'、'end'、'nearest')、デフォルトは'start'.
        """
        self.driver.execute_script(
            f'arguments[0].scrollIntoView({{block: "{block}"}});', target
        )


@dataclass
class BrowserError:
    NONE = "None selector. -> {}:{}"
    NO_SUCH = "No such selector. -> {}"
    NO_FORM = "Form does not exist. -> {}"
