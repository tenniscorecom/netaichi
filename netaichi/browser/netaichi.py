from .pages import Jsp
from .pages.selector import Selector
from netaichi.db import NetaichiDatabase, M_CourtProperty, T_LotteryData
from sqlmodel import delete, select
from selenium.webdriver.common.by import By
from selenium.common.exceptions import StaleElementReferenceException
import pandas as pd
from datetime import datetime as dd
import re
import time
from unicodedata import normalize

from netaichi.helper import filter_applied, sqlmodel_to_df
from netaichi.config import IS_HEADLESS


class NetAichi(Jsp):
    BASE_URL = "https://www4.pref.aichi.jp/yoyaku/"
    LOTTERY_MONTHS = 3
    DATE_TEMP = "%Y年%m月%d日"
    TENNIS_FACILITY_PREFIX = "庭球場"
    TENNIS_PURPOSE_VALUE = "1000-10000010"
    RESERVATION_PLAYERS = 4
    STALE_CLICK_RETRY_COUNT = 3
    STALE_CLICK_RETRY_WAIT_SECONDS = 0.5
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
            if not self.select.court(value):
                self.logger.warning(f"抽選メニューにないコートのためスキップ: {value}")
                continue

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

        # このアカウントの申込済み一覧と突合し、重複する枠は申し込まない
        applied = self.get.lottery()
        before = len(df)
        df = filter_applied(df, applied)
        self.logger.info(f"申込済みのため除外: {before - len(df)}件 / 申込対象: {len(df)}件")
        if df.empty:
            self.logger.info("新規に申し込む枠はありません")
            return

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

    def cancel_lottery(
        self, court_value: str | None = None, start: int | None = None
    ) -> list[dict]:
        """抽選申込一覧から条件（コート、開始時）に一致する申込をすべて取り消す。
        court_value=None なら全コートが対象。

        取り消すたびに一覧の行番号がずれるため、一致がなくなるまで
        一覧の走査からやり直す。
        """
        cancelled = []
        while True:
            target = self.__find_lottery_row(court_value, start)
            if target is None:
                break
            index, info = target
            self.js_exec(f"doSelect(document.form1, {index}, gLotUInstLotSelectAction);")
            time.sleep(1.5)
            if self.click('input[value="取消"]') is False:
                self.logger.error(f"取消ボタンが見つかりません: {info}")
                break
            self.alert_switch(True)
            time.sleep(1.5)
            self.logger.info(f"抽選申込を取り消しました: {info['date']} {info['start']}時 {info['court']}")
            cancelled.append(info)
        return cancelled

    def __find_lottery_row(
        self, court_value: str | None, start: int | None
    ) -> tuple[int, dict] | None:
        """抽選申込一覧を走査し、条件一致する最初の行の（ページ内index, 情報）を返す"""
        for _ in self.go.lottery_list():
            soup = self.get_html()
            dates = soup.select(Selector.LOTTERY_DATA_DATE)
            starts = soup.select(Selector.LOTTERY_DATA_START)
            courts = soup.select(Selector.LOTTERY_DATA_COURT)
            states = soup.select("#lotStateLabel")
            for i in range(len(dates)):
                if states and "抽選前" not in states[i].text:
                    continue  # 抽選済み等は取消不可
                value = self.to_value(courts[i].text)
                s = int(starts[i].text.removesuffix("時"))
                if (court_value is None or value == str(court_value)) and (
                    start is None or s == start
                ):
                    return i, {"date": dates[i].text, "start": s, "court": courts[i].text}
        return None

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

        if not self.__search_and_select_park(park_keyword, court_filter):
            if not self.__recover_and_select_park(park_keyword, court_filter):
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
                        if not self.__search_and_select_park(park_keyword, court_filter):
                            if not self.__recover_and_select_park(park_keyword, court_filter):
                                return slots
        self.logger.info(f"{park_keyword} 合計取得: {len(slots)}件 (filter={court_filter})")
        return slots

    def __search_and_select_park(self, park_keyword: str, court_filter: list[str]) -> bool:
        """施設名検索でparkを選択し、空き状況ページを開く"""
        if not self._go_name_search():
            self.logger.error("施設名検索ページに移動できませんでした")
            return False
        self.send_form("#textKeyword", park_keyword)
        self.click('input[value="上記の内容で検索する"]')
        if self.click('input[value="選択"]') is False:
            self.logger.warning(f"施設が見つかりませんでした: {park_keyword}")
            return False
        self.__filter_facilities(court_filter)
        return True

    def __recover_and_select_park(self, park_keyword: str, court_filter: list[str]) -> bool:
        """壊れたページ状態からトップページ経由で施設検索をやり直す"""
        self.logger.info("トップページに戻って復帰を試みます")
        self.go_page(self.BASE_URL)
        return self.__search_and_select_park(park_keyword, court_filter)

    def __filter_facilities(self, court_filter: list[str]) -> None:
        """サイドバーの施設チェックボックスを対象施設だけに絞り込む。
        表示ページ数が減り、日付ごとのパースが大幅に速くなる。"""
        soup = self.get_html()
        unchecked = 0
        for cb in soup.select('input[name="chkIcd"]'):
            label = cb.find_parent("label")
            name = label.get_text(strip=True) if label else ""
            if not any(f in name for f in court_filter):
                self.js_exec(
                    "document.querySelector("
                    f"'input[name=\"chkIcd\"][value=\"{cb.get('value')}\"]').checked = false;"
                )
                unchecked += 1
        if unchecked:
            self.click("#doReload")
            self.logger.debug(f"施設絞り込み: {unchecked}件を非表示")

    def _go_name_search(self) -> bool:
        """「施設名から探す」ページへ移動する。

        ログイン中のサイドバーリンク・未ログインのトップページメニューの
        両方に対応する（空き状況の確認だけならログイン不要）。
        """
        elements = self.get_elements_by_css("#goNameSearch")
        if not elements:
            elements = self.get_elements_by_contains_text("//a", "施設名から探す")
        if elements:
            elements[0].click()
            return True
        # 未ログインではトップページの「施設名から」画像リンクから入る
        if not self.get_elements_by_css('img[alt="施設名から"]'):
            self.go_page(self.BASE_URL)
            try:
                self.wait_element_load_by_css('img[alt="施設名から"]')
            except Exception:
                return False
        self.js_exec('document.querySelector(\'img[alt="施設名から"]\').closest("a").click();')
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

    def _facility_matches(self, text: str, facility_keyword: str) -> bool:
        """コート名が facility_keyword と一致するか（番号の直後が数字でないことを確認）

        単純な部分一致だと「庭球場1」が「庭球場11」にも当たってしまう。
        大高緑地のように14面ある施設で1桁の面を狙うと、別の面を取消・予約しかねない。
        """
        normalized_text = re.sub(r"\s+", "", normalize("NFKC", str(text)))
        normalized_keyword = re.sub(
            r"\s+", "", normalize("NFKC", str(facility_keyword))
        )
        suffix = r"(?!\d)" if normalized_keyword[-1:].isdigit() else ""
        return (
            re.search(
                rf"{re.escape(normalized_keyword)}{suffix}",
                normalized_text,
            )
            is not None
        )

    def cancel_reservation(
        self,
        date: dd,
        start: int,
        end: int,
        court_keyword: str,
        court_number: str | None = None,
    ) -> bool:
        """(日付, コート, 面番号) 一致かつ start以上end未満に始まる予約を取り消す

        実画面では4時間の予約も一覧に1行（13時～17時）で出るが、開始時ちょうどではなく
        範囲で照合しておくことで、一覧が2時間ごとに分かれて表示されても取りこぼさない。
        「取消」ボタン押下で出る確認ダイアログをOKして確定する。
        キャンセル限界日を過ぎていると取消ボタンが無く、Falseを返す。
        """
        self.go.mypage()
        for attempt in range(self.STALE_CLICK_RETRY_COUNT):
            link = self.get_element_by_contains_text("//a", "予約状況の一覧")
            if link is None:
                self.logger.error("「予約状況の一覧」リンクが見つかりません")
                return False
            try:
                link.click()
                break
            except StaleElementReferenceException:
                self.logger.warning(
                    "「予約状況の一覧」リンクが再描画されました（%d/%d）",
                    attempt + 1,
                    self.STALE_CLICK_RETRY_COUNT,
                )
                if attempt + 1 == self.STALE_CLICK_RETRY_COUNT:
                    raise
                time.sleep(self.STALE_CLICK_RETRY_WAIT_SECONDS)
        time.sleep(2)

        normalized_number = (
            normalize("NFKC", court_number) if court_number is not None else None
        )
        for page in range(1, 12):
            buttons = self.get_elements_by_css('input[value="選択"]')
            for btn in buttons:
                tr = btn.find_element(By.XPATH, "./ancestor::tr[1]")
                txt = normalize("NFKC", " ".join(tr.text.split()))
                m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?(\d{1,2})時", txt)
                if not m:
                    continue
                y, mo, d, h = map(int, m.groups())
                facility_matches = normalized_number is None or self._facility_matches(
                    txt, f"{self.TENNIS_FACILITY_PREFIX}{normalized_number}"
                )
                if not (
                    dd(y, mo, d) == date
                    and start <= h < end
                    and normalize("NFKC", court_keyword) in txt
                    and facility_matches
                ):
                    continue
                btn.click()
                time.sleep(2)
                cancel_btn = self.get_element_by_css('input[value="取消"]')
                if cancel_btn is None:
                    self.logger.error(
                        f"取消ボタンがありません（限界日超過の可能性）: "
                        f"{date:%Y-%m-%d} {h}時 {court_keyword}"
                    )
                    return False
                cancel_btn.click()
                self.alert_switch(True)  # 確認ダイアログでOK＝取消確定
                time.sleep(2)
                self.logger.info(
                    f"予約を取消しました: {date:%Y-%m-%d} {h}時 {court_keyword}"
                )
                return True
            nxt = self.get_elements_by_css("#goNextPager")
            if nxt and nxt[0].is_displayed():
                self.js_exec(f"movePage({page + 1});")
                time.sleep(2)
            else:
                break
        self.logger.warning(
            f"該当予約が見つかりません: {date:%Y-%m-%d} {start}-{end}時 {court_keyword}"
        )
        return False

    def reserve_available_slot(
        self,
        date: dd,
        start: int,
        end: int,
        court_name: str,
        court_number: str,
    ) -> bool:
        """指定コートの空き時間を予約し、予約一覧への反映まで確認する"""
        normalized_number = normalize("NFKC", court_number)
        facility_keyword = f"{self.TENNIS_FACILITY_PREFIX}{normalized_number}"
        submitted = False
        try:
            if not self.__search_and_select_park(
                court_name,
                [self.TENNIS_FACILITY_PREFIX],
            ):
                return False
            self.go.change_calendar_date(date)
            time.sleep(2)

            slot_ids = self.__find_available_slot_ids(
                date,
                start,
                end,
                facility_keyword,
            )
            if not slot_ids:
                self.logger.error(
                    f"取り直す空き枠が見つかりません: "
                    f"{date:%Y-%m-%d} {start}-{end}時 "
                    f"{court_name} {facility_keyword}"
                )
                return False

            for slot_id in slot_ids:
                slot_input = self.get_element_by_css(f"#{slot_id}")
                if slot_input is None:
                    return False
                parent = slot_input.find_element(By.XPATH, "..")
                available_icon = parent.find_element(By.CSS_SELECTOR, 'img[alt="空き"]')
                available_icon.click()
                time.sleep(0.5)

            if not self.click(Selector.BTN_CART_ADD):
                return False
            if not self.click(Selector.BTN_CART_CONFIRM):
                return False
            if not self.click(Selector.BTN_RESERVATION_PROCEED):
                return False

            purpose = self.get_element_by_css(Selector.SELECT_SPORTS)
            players = self.get_element_by_css(Selector.SELECT_PLAYERS)
            if purpose is None or players is None:
                return False
            self.select_by_value(purpose, self.TENNIS_PURPOSE_VALUE)
            players.clear()
            players.send_keys(str(self.RESERVATION_PLAYERS))

            if not self.click(Selector.BTN_RESERVATION_CHECK):
                return False
            submitted = self.click(Selector.BTN_RESERVATION_CONFIRM)
            if not submitted:
                return False
            time.sleep(2)
            return self.__reservation_exists(
                date,
                start,
                end,
                court_name,
                court_number,
            )
        except Exception:
            self.logger.error(
                f"コート予約の取り直しに失敗: "
                f"{date:%Y-%m-%d} {start}-{end}時 "
                f"{court_name} {facility_keyword}",
                exc_info=True,
            )
            if submitted:
                return self.__reservation_exists(
                    date,
                    start,
                    end,
                    court_name,
                    court_number,
                )
            return False

    def reset_reservation_session(self) -> bool:
        """未確定の予約カートを破棄するため、ログアウトして再ログインする"""
        account = self.logged_account
        if account is None or not self.logout():
            self.logger.error("予約カートを初期化できませんでした")
            return False
        self.go.last_page = None
        return self.login(account=account)

    def __find_available_slot_ids(
        self,
        date: dd,
        start: int,
        end: int,
        facility_keyword: str,
    ) -> list[str]:
        """現在の検索結果から指定時間を連続して覆う空き枠IDを返す"""
        target_date = date.strftime("%Y%m%d")
        target_start = start * 100
        target_end = end * 100

        for page in range(1, 12):
            if page > 1:
                self.js_exec(f"movePage({page});")
                time.sleep(1)
            soup = self.get_html()
            facility_names = {}
            for checkbox in soup.select('input[name="chkIcd"]'):
                label = checkbox.find_parent("label")
                if label:
                    facility_names[checkbox.get("value")] = normalize(
                        "NFKC",
                        label.get_text(strip=True),
                    )

            slots = []
            for info in soup.select('input[name="selectInfo"]'):
                parts = (info.get("value") or "").split(":")
                if len(parts) < 6:
                    continue
                facility_name = facility_names.get(parts[1], "")
                slot_start = int(parts[4])
                slot_end = int(parts[5])
                if (
                    parts[2] != target_date
                    or not self._facility_matches(facility_name, facility_keyword)
                    or slot_start < target_start
                    or slot_end > target_end
                ):
                    continue
                icon = info.find_previous_sibling("img")
                if icon is None or icon.get("alt") != "空き":
                    return []
                slots.append((slot_start, slot_end, info.get("id")))

            if slots:
                slots.sort()
                cursor = target_start
                slot_ids = []
                for slot_start, slot_end, slot_id in slots:
                    if slot_start != cursor or slot_id is None:
                        return []
                    slot_ids.append(slot_id)
                    cursor = slot_end
                return slot_ids if cursor == target_end else []
            if not soup.select("#goNextPager"):
                break
        return []

    def __reservation_exists(
        self,
        date: dd,
        start: int,
        end: int,
        court_name: str,
        court_number: str,
    ) -> bool:
        """予約一覧に指定枠が反映されたか確認する"""
        try:
            self.go.last_page = None
            reservations = self.get.reservation()
            normalized_number = normalize("NFKC", court_number)
            for row in reservations.itertuples():
                reservation_date = pd.Timestamp(row.date).to_pydatetime()
                if (
                    reservation_date.date() == date.date()
                    and int(row.start) == start
                    and int(row.end) == end
                    and normalize("NFKC", str(row.court))
                    == normalize("NFKC", court_name)
                    and normalize("NFKC", str(row.court_number)) == normalized_number
                ):
                    self.logger.info(
                        f"コート予約を取り直しました: "
                        f"{date:%Y-%m-%d} {start}-{end}時 "
                        f"{court_name} 庭球場{court_number}"
                    )
                    return True
            self.logger.error(
                f"取り直した予約を一覧で確認できません: "
                f"{date:%Y-%m-%d} {start}-{end}時 "
                f"{court_name} 庭球場{court_number}"
            )
            return False
        except Exception:
            self.logger.error(
                f"取り直した予約の確認中にエラー: "
                f"{date:%Y-%m-%d} {start}-{end}時 "
                f"{court_name} 庭球場{court_number}",
                exc_info=True,
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
