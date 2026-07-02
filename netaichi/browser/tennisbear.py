"""テニスベア（tennisbear.net）のサイト操作。

イベント作成は「過去のイベントをコピー」機能を使い、
コピー元と同じコートの最新イベントを選んで日時だけ差し替える。
"""
from datetime import datetime
from pathlib import Path
import re
import time

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from .chrome import ChromeBrowser
from netaichi.config import (
    IS_HEADLESS,
    ROOT_DIR,
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
        # 専用プロファイルにCookie/セッションを残し、ログインを省略する
        profile = str(Path(ROOT_DIR) / ".chrome-profile-tennisbear")
        super().__init__(is_headless, logger_name, user_data_dir=profile)

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
        # 認証必須ページで既存セッションの有効性を確認し、有効なら省略する
        self.go_page(self.ORGANIZED_URL)
        self._wait_render()
        if "/login" not in self.current_url and "organized" in self.current_url:
            self.logger.info("テニスベア: セッション有効（ログイン省略）")
            return True

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

    def list_existing_events(self) -> set:
        """テニスベアの作成済みイベントの (開始日, 開始時) 集合を返す

        「過去のイベントをコピー」ダイアログのイベント一覧
        （タイトルと "2026/9/28(月) 19:00" 形式の日時）から抽出する。
        一覧は新しい順で下にスクロールすると過去のイベントが追加ロードされる。
        過去日付が現れる（＝未来分を読み切った）までスクロールして集める。
        """
        self.go_page(f"{self.BASE_URL}/event/create")
        self._wait_render(5)
        if not self._click_button_by_text("過去のイベントをコピー"):
            return set()
        self._wait_render(2)
        dialogs = self.__visible(".v-dialog")
        if not dialogs:
            self.logger.error("コピー元一覧ダイアログが開きませんでした")
            return set()
        dialog = dialogs[-1]

        pattern = r"(\d{4})/(\d{1,2})/(\d{1,2})\([月火水木金土日]\)\s*(\d{1,2}):(\d{2})"
        today = datetime.today().replace(hour=0, minute=0, second=0, microsecond=0)
        existing = set()
        prev_count = -1
        for _ in range(40):
            for m in re.finditer(pattern, dialog.text):
                y, mo, d, h, _ = map(int, m.groups())
                existing.add((datetime(y, mo, d), h))
            # 過去日付まで到達した（未来分を読み切った）か、増分が無くなれば終了
            if any(dt < today for dt, _ in existing):
                break
            if len(existing) == prev_count:
                break
            prev_count = len(existing)
            # ダイアログ本体と内部のスクロールコンテナ（div）を両方最下部へ
            self.driver.execute_script(
                "arguments[0].scrollTop = arguments[0].scrollHeight;", dialog
            )
            for sc in dialog.find_elements(By.CSS_SELECTOR, "div"):
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollTop = arguments[0].scrollHeight;", sc
                    )
                except Exception:
                    pass
            time.sleep(0.7)
        return existing

    ORGANIZED_URL = (
        "https://www.tennisbear.net/my-page/organized-and-participated-event"
    )

    def list_organized_events(self, today: datetime | None = None) -> list[dict]:
        """主催・参加イベント一覧（今後の予定）から各イベント情報を取得する

        各dict: id, date(datetime), start(時), court, participants, capacity,
                is_lesson(【初回割】シングルス実戦), is_practice(シングルス練習)
        """
        self.go_page(self.ORGANIZED_URL)
        self._wait_render(6)
        if today is None:
            today = datetime.today()

        events = []
        seen = set()
        for a in self.driver.find_elements(By.CSS_SELECTOR, 'a[href*="/event/"]'):
            href = a.get_attribute("href") or ""
            m_id = re.search(r"/event/(\d+)/", href)
            if not m_id or m_id.group(1) in seen:
                continue
            text = a.text
            m_p = re.search(r"(\d+)人/(\d+)人", text)
            m_d = re.search(r"(\d{1,2})/(\d{1,2})\(", text)
            m_t = re.search(r"(\d{1,2}):(\d{2})", text)
            if not (m_p and m_d and m_t):
                continue
            seen.add(m_id.group(1))
            court = ""
            cm = re.search(r"[都道府県]\s+(\S+)", text)
            if cm:
                court = cm.group(1)
            events.append(
                {
                    "id": m_id.group(1),
                    "date": self._resolve_date(int(m_d.group(1)), int(m_d.group(2)), today),
                    "start": int(m_t.group(1)),
                    "court": court,
                    "participants": int(m_p.group(1)),
                    "capacity": int(m_p.group(2)),
                    "is_lesson": "シングルス実戦" in text,
                    "is_practice": "シングルス練習" in text,
                }
            )
        return events

    @staticmethod
    def _resolve_date(month: int, day: int, today: datetime) -> datetime:
        """月日だけの表記に、今日以降で最も近い年を補う"""
        for year in (today.year, today.year + 1):
            d = datetime(year, month, day)
            if d.date() >= today.date():
                return d
        return datetime(today.year, month, day)

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

        # 次へ → 招待モーダルが開く
        if not self._click_button_by_text("次へ"):
            return False
        self._wait_render()

        # 招待モーダルが開いたことを確認
        if not self.__invite_dialog_open():
            self.logger.error("「次へ」後の招待モーダルが開きませんでした（未入力の必須項目がある可能性）")
            return False

        if not submit:
            self.logger.info(
                f"[確認モード] 招待モーダルまで到達、確定せず終了: {court_name} {start:%m/%d %H:%M}"
            )
            return True

        # 「招待せずにイベントを作成」→ 確認ページ(/event/confirm)へ
        if not self._click_button_by_text("招待せずにイベントを作成"):
            return False
        self._wait_render()

        # 確認ページの「作成する」で最終確定
        if not self._click_button_by_text("作成する"):
            self.logger.error("確認ページの「作成する」ボタンが見つかりませんでした")
            return False
        self._wait_render()
        self.logger.info(f"イベントを作成しました: {court_name} {start:%m/%d %H:%M}-{end:%H:%M}")
        return True

    def delete_event(self, event_id: str, comment: str = "都合により削除させていただきます。") -> bool:
        """作成済みイベントを削除する（管理メニュー→イベントの削除→確認）"""
        self.go_page(f"{self.BASE_URL}/event/{event_id}/info")
        self._wait_render()
        if not self._click_button_by_text("管理メニュー"):
            return False
        time.sleep(1.5)

        # 「イベントの削除」項目（v-list-item）を選ぶ
        clicked = False
        for item in self.__visible(".v-list-item"):
            if "イベントの削除" in item.text:
                self.driver.execute_script("arguments[0].click();", item)
                clicked = True
                break
        if not clicked:
            self.logger.error("「イベントの削除」項目が見つかりません")
            return False
        time.sleep(1.5)

        dialog = None
        for d in self.__visible(".v-dialog"):
            if "イベントを削除しますか" in d.text:
                dialog = d
                break
        if dialog is None:
            self.logger.error("削除確認ダイアログが開きませんでした")
            return False

        # 参加者への通知コメント（任意）
        textareas = dialog.find_elements(By.CSS_SELECTOR, "textarea")
        if textareas:
            textareas[0].send_keys(comment)
            time.sleep(0.4)

        # 確認ダイアログの「削除する」はActionChainsで押す（JSクリックは効かない）
        for b in dialog.find_elements(By.CSS_SELECTOR, "button"):
            if b.text.strip() == "削除する":
                ActionChains(self.driver).move_to_element(b).click().perform()
                self._wait_render()
                self.logger.info(f"イベントを削除しました: {event_id}")
                return True
        self.logger.error("削除ダイアログの「削除する」ボタンが見つかりません")
        return False

    def _set_datetimes(self, start: datetime, end: datetime, deadline: datetime) -> bool:
        """日付/時間フィールドを書き換える

        日付欄・時間欄とも readonly で、クリックするとVuetifyのカレンダー／
        時計ピッカーが開く。ピッカーを操作して値を設定する。

        「募集開始日を設定する」未チェック時、表示中のdate入力は
        [開始日, 終了日, 申込期限, キャンセル期限] の4つ。
        申込期限とキャンセル期限は同じ deadline を入れる。
        """
        # [開始, 終了, 申込期限, キャンセル期限]
        targets = [start, end, deadline, deadline]

        # 選択でDOMが組み替わるため、各操作の直前にフィールドを取り直す
        for i, dt in enumerate(targets):
            fields = self.__visible(TennisBearSelector.DATE_INPUTS)
            if len(fields) < 4:
                self.logger.error(f"日付フィールドが想定数未満です: {len(fields)}")
                return False
            if not self._pick_date(fields[i], dt):
                return False
        for i, dt in enumerate(targets):
            fields = self.__visible('input[placeholder="時間"]')
            if len(fields) < 4:
                self.logger.error(f"時間フィールドが想定数未満です: {len(fields)}")
                return False
            if not self._pick_time(fields[i], dt.hour, dt.minute):
                return False
        return True

    def __visible(self, css: str) -> list:
        return [
            e for e in self.driver.find_elements(By.CSS_SELECTOR, css) if e.is_displayed()
        ]

    def __invite_dialog_open(self) -> bool:
        """「次へ」後に開く招待モーダルが表示されているか"""
        for d in self.__visible(".v-dialog"):
            if "招待せずにイベントを作成" in d.text:
                return True
        return False

    def _open_picker(self, field):
        """readonlyフィールドをクリックしてピッカー(.v-menu__content)を開く"""
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", field)
        time.sleep(0.4)
        field.click()
        time.sleep(1.0)
        menus = self.__visible(".v-menu__content")
        return menus[-1] if menus else None

    def _pick_date(self, field, target: datetime) -> bool:
        menu = self._open_picker(field)
        if menu is None:
            self.logger.error("日付ピッカーが開きませんでした")
            return False
        # ヘッダーの年月を読み、前月/次月ボタンで目的の月まで移動する
        for _ in range(36):
            header = menu.find_element(
                By.CSS_SELECTOR, ".v-date-picker-header__value button"
            ).text
            m = re.match(r"(\d+)\D+(\d+)", header)
            cur_y, cur_m = int(m.group(1)), int(m.group(2))
            diff = (target.year - cur_y) * 12 + (target.month - cur_m)
            if diff == 0:
                break
            label = "Next month" if diff > 0 else "Previous month"
            menu.find_element(By.CSS_SELECTOR, f'button[aria-label="{label}"]').click()
            time.sleep(0.35)
        for b in menu.find_elements(By.CSS_SELECTOR, ".v-date-picker-table button"):
            if b.text.strip() == str(target.day):
                self.driver.execute_script("arguments[0].click();", b)
                time.sleep(0.5)
                return True
        self.logger.error(f"日付ボタンが見つかりません: {target:%Y-%m-%d}")
        return False

    def _pick_time(self, field, hour: int, minute: int) -> bool:
        menu = self._open_picker(field)
        if menu is None:
            self.logger.error("時間ピッカーが開きませんでした")
            return False
        # 時計ピッカー：時を選ぶと自動で分モードに切り替わる
        if not self._click_clock_item(menu, hour):
            return False
        time.sleep(0.6)
        if not self._click_clock_item(menu, minute):
            return False
        time.sleep(0.4)
        # 分選択後もメニューが残る場合があるのでbodyクリックで閉じる
        self.driver.execute_script("document.body.click();")
        time.sleep(0.3)
        return True

    def _click_clock_item(self, menu, value: int) -> bool:
        # アナログ時計はマウス座標から角度を計算するため、JSクリックでは
        # 選択されない。ActionChainsで実際にクリックする必要がある。
        candidates = {str(value), f"{value:02d}"}
        for item in menu.find_elements(By.CSS_SELECTOR, ".v-time-picker-clock__item"):
            if item.text.strip() in candidates:
                ActionChains(self.driver).move_to_element(item).click().perform()
                return True
        self.logger.error(f"時計の値が見つかりません: {value}")
        return False
