"""テニスベア（tennisbear.net）のサイト操作。

イベント作成は「過去のイベントをコピー」機能を使い、
コピー元と同じコートの最新イベントを選んで日時だけ差し替える。
"""
from datetime import datetime
import time

from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from .chrome import ChromeBrowser
from netaichi.config import (
    IS_HEADLESS,
    TENNISBEAR_EMAIL,
    TENNISBEAR_PW,
)


class TennisBearSelector:
    LOGIN_EMAIL = 'input[name="email"]'
    LOGIN_PW = 'input[name="current-password"]'
    EVENT_TITLE = 'input[name="eventTitle"]'
    DIALOG = ".v-dialog"
    DATE_INPUTS = 'input[name="date"]'


class TennisBear(ChromeBrowser):
    BASE_URL = "https://tennisbear.net"
    # SPAの描画待ち秒数
    RENDER_WAIT = 4

    def __init__(self, is_headless=IS_HEADLESS, logger_name="TennisBear"):
        super().__init__(is_headless, logger_name)

    def _wait_render(self, seconds: float | None = None):
        time.sleep(seconds or self.RENDER_WAIT)

    def _click_button_by_text(self, text: str, base=None) -> bool:
        root = base or self.driver
        for b in root.find_elements(By.CSS_SELECTOR, "button"):
            if text in b.text:
                self.driver.execute_script(
                    "arguments[0].scrollIntoView({block:'center'});", b
                )
                time.sleep(0.5)
                self.driver.execute_script("arguments[0].click();", b)
                return True
        self.logger.error(f"ボタンが見つかりません: {text}")
        return False

    def login(self) -> bool:
        self.go_page(f"{self.BASE_URL}/login")
        self._wait_render()
        self.send_form(TennisBearSelector.LOGIN_EMAIL, TENNISBEAR_EMAIL)
        self.send_form(TennisBearSelector.LOGIN_PW, TENNISBEAR_PW)
        if not self._click_button_by_text("ログイン"):
            return False
        self._wait_render(5)
        if "/login" in self.current_url:
            self.logger.error("テニスベアへのログインに失敗しました")
            return False
        self.logger.info("テニスベアにログインしました")
        return True

    def create_event_from_template(
        self,
        template_title: str,
        court_name: str,
        start: datetime,
        end: datetime,
        deadline: datetime,
        submit: bool = False,
    ) -> bool:
        """過去イベントをコピーして日時を差し替え、イベントを作成する

        Args:
            template_title: コピー元イベントのタイトル
            court_name: 場所欄に表示されるべきコート名（照合用の部分一致）
            start / end: イベントの開始・終了日時
            deadline: 申込期限
            submit: Falseの場合、最終確定ボタンを押さずに終了する（動作確認用）
        """
        # コピー元候補を順に試し、コートが一致するものを使う
        index = 0
        while True:
            self.go_page(f"{self.BASE_URL}/event/create")
            self._wait_render(5)
            if not self._click_button_by_text("過去のイベントをコピー"):
                return False
            self._wait_render(2)

            dialogs = self.driver.find_elements(By.CSS_SELECTOR, TennisBearSelector.DIALOG)
            if not dialogs:
                self.logger.error("コピー元選択ダイアログが開きませんでした")
                return False
            items = dialogs[-1].find_elements(
                By.XPATH, f".//*[contains(text(), '{template_title}')]"
            )
            if index >= len(items):
                self.logger.error(
                    f"コート「{court_name}」のコピー元イベントが見つかりません: {template_title}"
                )
                return False
            self.driver.execute_script("arguments[0].click();", items[index])
            self._wait_render()

            body = self.driver.find_element(By.TAG_NAME, "body").text
            if court_name in body:
                break
            self.logger.info(
                f"候補{index}はコート不一致のため次を試します（期待: {court_name}）"
            )
            index += 1

        # 日時の差し替え
        # date/timeの並び: [0]開始日 [1]終了日 [2]申込期限（募集開始日は非表示想定）
        if not self._set_datetimes(start, end, deadline):
            return False

        # 次へ → 確認ページ
        if not self._click_button_by_text("次へ"):
            return False
        self._wait_render()

        if not submit:
            self.logger.info(
                f"[確認モード] 確定ボタンは押していません: {court_name} {start:%m/%d %H:%M}"
            )
            return True

        # 確認ページの確定ボタン（「作成」を含むボタンを想定）
        if not self._click_button_by_text("作成"):
            return False
        self._wait_render()
        self.logger.info(f"イベントを作成しました: {court_name} {start:%m/%d %H:%M}-{end:%H:%M}")
        return True

    def _set_datetimes(self, start: datetime, end: datetime, deadline: datetime) -> bool:
        """開始・終了・申込期限の日付/時間フィールドを書き換える"""
        date_inputs = self.driver.find_elements(
            By.CSS_SELECTOR, TennisBearSelector.DATE_INPUTS
        )
        # 表示中のdate入力のみ対象（開始日・終了日・申込期限）
        visible_dates = [e for e in date_inputs if e.is_displayed()]
        if len(visible_dates) < 3:
            self.logger.error(f"日付フィールドが想定数未満です: {len(visible_dates)}")
            return False

        values = [
            (visible_dates[0], self._format_date(start)),
            (visible_dates[1], self._format_date(end)),
            (visible_dates[2], self._format_date(deadline)),
        ]
        for element, value in values:
            if not self._set_input_value(element, value):
                return False

        # 時間フィールド（各date入力の直後にある placeholder="時間" の入力）
        time_inputs = [
            e
            for e in self.driver.find_elements(By.CSS_SELECTOR, 'input[placeholder="時間"]')
            if e.is_displayed()
        ]
        if len(time_inputs) < 3:
            self.logger.error(f"時間フィールドが想定数未満です: {len(time_inputs)}")
            return False
        for element, value in [
            (time_inputs[0], f"{start:%H:%M}"),
            (time_inputs[1], f"{end:%H:%M}"),
            (time_inputs[2], f"{deadline:%H:%M}"),
        ]:
            if not self._set_input_value(element, value):
                return False
        return True

    WEEKDAY_LABELS = ["月", "火", "水", "木", "金", "土", "日"]

    def _format_date(self, dt: datetime) -> str:
        # サイトの表記例: 2026/9/28(月)
        return f"{dt.year}/{dt.month}/{dt.day}({self.WEEKDAY_LABELS[dt.weekday()]})"

    def _set_input_value(self, element, value: str) -> bool:
        """Vue管理下のinputに値を反映する（inputイベントを発火）"""
        try:
            self.driver.execute_script(
                """
                const el = arguments[0], value = arguments[1];
                el.focus();
                el.value = value;
                el.dispatchEvent(new Event('input', {bubbles: true}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.blur();
                """,
                element,
                value,
            )
            time.sleep(0.3)
            return True
        except Exception as e:
            self.logger.error(f"入力に失敗しました: {value} ({e})")
            return False
