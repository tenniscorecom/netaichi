"""NagoyaSporec の純粋パースロジックのテスト"""
from datetime import datetime

from netaichi.browser.nagoya import NagoyaSporec


class TestParseTimeRange:
    def test_fullwidth_range(self):
        assert NagoyaSporec._parse_time_range("１３：００－１６：３０（午後）") == (13, 17)

    def test_morning(self):
        assert NagoyaSporec._parse_time_range("０８：３０－１２：００（午前）") == (8, 12)

    def test_night(self):
        assert NagoyaSporec._parse_time_range("１７：００－２０：３０（夜間）") == (17, 21)

    def test_daytime_skipped(self):
        assert NagoyaSporec._parse_time_range("昼間") is None

    def test_sunrise_skipped(self):
        assert NagoyaSporec._parse_time_range("日の出－０８：００（早朝夏）") is None


class TestParseHeaderDates:
    def test_same_month(self):
        header = ["7月", "6", "7", "8"]
        dates = NagoyaSporec._parse_header_dates(header, datetime(2026, 7, 6))
        assert dates == [datetime(2026, 7, 6), datetime(2026, 7, 7), datetime(2026, 7, 8)]

    def test_month_crossing(self):
        header = ["7月", "26", "8/1", "2"]
        dates = NagoyaSporec._parse_header_dates(header, datetime(2026, 7, 26))
        assert dates == [datetime(2026, 7, 26), datetime(2026, 8, 1), datetime(2026, 8, 2)]

    def test_year_crossing(self):
        header = ["12月", "28", "1/4", "5"]
        dates = NagoyaSporec._parse_header_dates(header, datetime(2026, 12, 28))
        assert dates == [datetime(2026, 12, 28), datetime(2027, 1, 4), datetime(2027, 1, 5)]

    def test_non_date_cell_is_none(self):
        header = ["7月", "6", "曜日"]
        dates = NagoyaSporec._parse_header_dates(header, datetime(2026, 7, 6))
        assert dates == [datetime(2026, 7, 6), None]
