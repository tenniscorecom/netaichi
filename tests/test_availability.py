"""availability の純粋ロジック（対象日付・時間フィルタ・メッセージ整形）のテスト"""
from datetime import datetime

from netaichi.services.availability import (
    diff_slots,
    format_message,
    in_time_ranges,
    merge_hour_slots,
    target_dates,
)


class TestMergeHourSlots:
    def test_contiguous_hours_merged(self):
        date = datetime(2026, 10, 3)
        slots = [
            {"value": "大高緑地", "date": date, "start": 9, "end": 10, "facility": "庭球場１"},
            {"value": "大高緑地", "date": date, "start": 10, "end": 11, "facility": "庭球場１"},
            {"value": "大高緑地", "date": date, "start": 13, "end": 14, "facility": "庭球場１"},
        ]
        merged = merge_hour_slots(slots)
        assert {(m["start"], m["end"]) for m in merged} == {(9, 11), (13, 14)}

    def test_facilities_kept_separate(self):
        # コート番号を表示するため、施設（コート）ごとに別の枠として扱う
        date = datetime(2026, 10, 3)
        slots = [
            {"value": "大高緑地", "date": date, "start": 9, "end": 10, "facility": "庭球場１"},
            {"value": "大高緑地", "date": date, "start": 9, "end": 10, "facility": "庭球場２"},
        ]
        merged = merge_hour_slots(slots)
        assert len(merged) == 2
        assert {m["facility"] for m in merged} == {"庭球場１", "庭球場２"}



    def test_same_time_without_facility_deduped(self):
        # show_court: false の施設はfacilityが空になり、同時間帯の複数コートは1件にまとまる
        date = datetime(2026, 10, 3)
        slots = [
            {"value": "森林公園", "date": date, "start": 9, "end": 10, "facility": ""},
            {"value": "森林公園", "date": date, "start": 9, "end": 10, "facility": ""},
            {"value": "森林公園", "date": date, "start": 10, "end": 11, "facility": ""},
        ]
        merged = merge_hour_slots(slots)
        assert len(merged) == 1
        assert (merged[0]["start"], merged[0]["end"]) == (9, 11)


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


class TestDiffSlots:
    def _slot(self, value, day, start, end=None, facility=""):
        return {
            "value": value,
            "date": datetime(2026, 10, day),
            "start": start,
            "end": end or start + 2,
            "facility": facility,
        }

    def test_new_slot_detected(self):
        new, gone = diff_slots([self._slot("大高緑地", 3, 9)], [])
        assert len(new) == 1
        assert len(gone) == 0

    def test_gone_slot_detected(self):
        new, gone = diff_slots([], [self._slot("大高緑地", 3, 9)])
        assert len(new) == 0
        assert len(gone) == 1

    def test_unchanged_slot_not_in_either(self):
        slot = self._slot("大高緑地", 3, 9)
        new, gone = diff_slots([slot], [slot])
        assert len(new) == 0
        assert len(gone) == 0

    def test_facility_difference_detected(self):
        # 同じ時間でもコートが違えば別の枠として扱う
        prev = [self._slot("大高緑地", 3, 9, facility="庭球場１")]
        curr = [self._slot("大高緑地", 3, 9, facility="庭球場２")]
        new, gone = diff_slots(curr, prev)
        assert len(new) == 1
        assert len(gone) == 1

    def test_mixed(self):
        prev = [self._slot("大高緑地", 3, 9), self._slot("小幡緑地", 4, 13)]
        curr = [self._slot("大高緑地", 3, 9), self._slot("愛・地球博", 5, 11)]
        new, gone = diff_slots(curr, prev)
        assert len(new) == 1 and new[0]["value"] == "愛・地球博"
        assert len(gone) == 1 and gone[0]["value"] == "小幡緑地"


class TestFormatMessage:
    def test_grouped_by_date_with_court(self):
        slots = [
            {"value": "小幡緑地", "date": datetime(2026, 10, 4), "start": 13, "end": 15, "facility": "庭球場３"},
            {"value": "大高緑地", "date": datetime(2026, 10, 3), "start": 9, "end": 11, "facility": "庭球場１"},
        ]
        message = format_message(slots, fetch_time=datetime(2026, 10, 3, 12, 0))
        lines = message.split(chr(10))
        assert "現在の空き" in lines[0]
        assert "[2件]" in lines[0]
        assert "10/03 12:00" in lines[0]
        assert lines[1] == "10/03(土)"
        assert lines[2] == "　大高緑地 9-11時 庭球場１"
        assert lines[3] == "10/04(日)"
        assert lines[4] == "　小幡緑地 13-15時 庭球場３"

    def test_same_date_grouped_under_one_header(self):
        date = datetime(2026, 10, 3)
        slots = [
            {"value": "大高緑地", "date": date, "start": 9, "end": 11, "facility": ""},
            {"value": "小幡緑地", "date": date, "start": 13, "end": 15, "facility": ""},
        ]
        message = format_message(slots, fetch_time=datetime(2026, 10, 3, 12, 0))
        assert message.count("10/03(土)") == 1

    def test_facility_optional(self):
        slots = [{"value": "大高緑地", "date": datetime(2026, 10, 3), "start": 9, "end": 11}]
        message = format_message(slots, fetch_time=datetime(2026, 10, 3, 12, 0))
        assert "　大高緑地 9-11時" in message
