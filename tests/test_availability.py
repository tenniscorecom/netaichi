"""availability の純粋ロジック（対象日付・時間フィルタ・メッセージ整形）のテスト"""
from datetime import datetime

from netaichi.services.availability import (
    format_message,
    in_time_ranges,
    target_dates,
)


class TestTargetDates:
    def test_weekend_holiday_only(self):
        conf = {"days": "weekend_holiday", "months_ahead": 1}
        dates = target_dates(conf, today=datetime(2026, 10, 1))
        assert all(d.weekday() in (5, 6) or d.day == 12 for d in dates)  # 10/12=祝
        assert datetime(2026, 10, 3) in dates   # 土曜
        assert datetime(2026, 10, 12) in dates  # 祝日（月曜）
        assert datetime(2026, 10, 2) not in dates  # 金曜

    def test_starts_tomorrow(self):
        conf = {"days": "weekend_holiday", "months_ahead": 1}
        dates = target_dates(conf, today=datetime(2026, 10, 3))  # 土曜
        assert datetime(2026, 10, 3) not in dates  # 当日は含まない
        assert datetime(2026, 10, 4) in dates      # 翌日（日曜）


class TestInTimeRanges:
    def test_overlap(self):
        assert in_time_ranges({"start": 9, "end": 11}, [[9, 17]])
        assert in_time_ranges({"start": 15, "end": 19}, [[9, 17]])  # 部分重複

    def test_no_overlap(self):
        assert not in_time_ranges({"start": 17, "end": 19}, [[9, 17]])
        assert not in_time_ranges({"start": 7, "end": 9}, [[9, 17]])


class TestFormatMessage:
    def test_sorted_and_named(self):
        slots = [
            {"value": "180", "date": datetime(2026, 10, 4), "start": 13, "end": 15},
            {"value": "130", "date": datetime(2026, 10, 3), "start": 9, "end": 11},
        ]
        message = format_message(slots)
        lines = message.split("\n")
        assert "空き" in lines[0]
        assert lines[1] == "・10/03(土) 9-11時 大高緑地"
        assert lines[2] == "・10/04(日) 13-15時 小幡緑地"
