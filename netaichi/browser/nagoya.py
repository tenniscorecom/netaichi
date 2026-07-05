import re
import time
import unicodedata
from datetime import datetime, timedelta

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select

from netaichi.browser.chrome import ChromeBrowser
from netaichi.config import IS_HEADLESS


class NagoyaSporec(ChromeBrowser):
    """名古屋市スポーツ・レクリエーション情報システムのサイト操作。

    「施設ごとの空き照会」(sp05001) で施設・種目・開始日を指定して照会すると、
    2週間分の空き表（行=時間帯、列=日付）が返る。ログイン不要。
    セルは ×=埋まり、－=対象外、＝=照会可能期間外、それ以外（空き面数の数字等）=空き。
    照会できるのは「抽選の終了した利用月」まで（例: 7月時点では8月末まで）。
    """

    URL = "https://www.net.city.nagoya.jp/cgi-bin/sp05001"
    TENNIS = "001"  # 種目コード: テニス

    def __init__(self, is_headless=IS_HEADLESS, logger_name="NagoyaSporec"):
        super().__init__(is_headless, logger_name)

    def find_available_slots(
        self, facility_code: str, facility_name: str, dates: list[datetime]
    ) -> list[dict]:
        """対象日付リストに含まれる日の空き時間帯を返す。

        照会1回で2週間分出るため、日付範囲をカバーするまで開始日を
        ずらしながら繰り返し照会する。
        """
        if not dates:
            return []
        wanted = {d.date() for d in dates}
        start = min(dates)
        until = max(dates)

        slots = []
        while start <= until:
            day_slots, last_date = self._query_two_weeks(
                facility_code, facility_name, start
            )
            slots += [s for s in day_slots if s["date"].date() in wanted]
            if last_date is None:
                self.logger.warning(f"{facility_name}: 照会結果を読めませんでした")
                break
            start = last_date + timedelta(days=1)
        self.logger.info(f"{facility_name} 合計取得: {len(slots)}件")
        return slots

    def _query_two_weeks(
        self, facility_code: str, facility_name: str, start: datetime
    ) -> tuple[list[dict], datetime | None]:
        """開始日から2週間分を照会し、(空きリスト, 表の最終日付) を返す"""
        self.go_page(self.URL)
        time.sleep(1)
        Select(self.driver.find_element(By.NAME, "sisetu")).select_by_value(facility_code)
        Select(self.driver.find_element(By.NAME, "syumoku")).select_by_value(self.TENNIS)
        Select(self.driver.find_element(By.NAME, "month")).select_by_value(f"{start.month:02d}")
        Select(self.driver.find_element(By.NAME, "day")).select_by_value(f"{start.day:02d}")
        Select(self.driver.find_element(By.NAME, "time")).select_by_value("1")  # 指定日から2週間
        self.driver.find_element(By.NAME, "B1").click()
        time.sleep(2)

        soup = self.get_html()
        table = self._find_result_table(soup)
        if table is None:
            return [], None

        rows = table.select("tr")
        header = [td.get_text(strip=True) for td in rows[0].select("td, th")]
        dates = self._parse_header_dates(header, start)
        if not dates:
            return [], None

        slots = []
        for row in rows[1:]:
            cells = [td.get_text(strip=True) for td in row.select("td, th")]
            if len(cells) < 2:
                continue
            hours = self._parse_time_range(cells[0])
            if hours is None:
                continue  # 曜日行・昼間などの包括枠はスキップ
            for date, cell in zip(dates, cells[1:]):
                if date is None or not self._cell_available(cell):
                    continue
                slots.append({
                    "value": facility_name,
                    "date": date,
                    "start": hours[0],
                    "end": hours[1],
                    "facility": "",
                })
        last = max((d for d in dates if d), default=None)
        return slots, last

    @staticmethod
    def _cell_available(cell: str) -> bool:
        """×=埋まり、－=対象外、＝=照会可能期間外、空=データなし。それ以外を空きとする"""
        return cell not in ("×", "－", "＝", "")

    @staticmethod
    def _find_result_table(soup):
        """時間帯行（HH：MM－HH：MM）を含むテーブルを探す"""
        for table in soup.select("table"):
            text = table.get_text()
            if "：" in text and "－" in text and ("午前" in text or "昼間" in text):
                return table
        return None

    @staticmethod
    def _parse_header_dates(header: list[str], start: datetime) -> list[datetime | None]:
        """ヘッダー行（例: ['7月', '6', '7', ..., '8/1', '2']）を日付リストにする"""
        month = start.month
        year = start.year
        dates = []
        for cell in header[1:]:
            m = re.fullmatch(r"(?:(\d{1,2})/)?(\d{1,2})", cell)
            if not m:
                dates.append(None)
                continue
            if m.group(1):
                new_month = int(m.group(1))
                if new_month < month:  # 年またぎ
                    year += 1
                month = new_month
            dates.append(datetime(year, month, int(m.group(2))))
        return dates

    @staticmethod
    def _parse_time_range(label: str) -> tuple[int, int] | None:
        """時間帯ラベルを (開始時, 終了時) にする。例: １３：００－１６：３０ → (13, 17)

        「昼間」（包括枠）や「日の出－08:00」など時刻2つが取れないものはNone。
        """
        text = unicodedata.normalize("NFKC", label)
        m = re.search(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", text)
        if not m:
            return None
        start = int(m.group(1))
        end = int(m.group(3)) + (1 if int(m.group(4)) > 0 else 0)
        return start, end
