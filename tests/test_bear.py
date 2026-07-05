"""bear の純粋ロジック（枠分割・コート照合・イベント変換・掲載判定）のテスト"""
from datetime import datetime

import pandas as pd

from netaichi.services.bear import (
    compute_deadline,
    deadline_days_for,
    match_court,
    reservations_to_events,
    select_events_to_post,
    split_slots,
)

CONF = {
    "event_hours": 2,
    "deadline_days_before": 2,
    "deadline_overrides": {"上納池": 9},
    "courts": {
        "大高緑地": "大高緑地",
        "モリコロ": "モリコロパーク",
        "上納池": "上納池",
    },
}


class TestSplitSlots:
    def test_four_hours_into_two(self):
        assert split_slots(13, 17, 2) == [(13, 15), (15, 17)]

    def test_two_hours_single(self):
        assert split_slots(19, 21, 2) == [(19, 21)]

    def test_odd_remainder_dropped(self):
        assert split_slots(9, 12, 2) == [(9, 11)]


class TestMatchCourt:
    def test_partial_match(self):
        assert match_court("大高緑地公園テニスコート", CONF["courts"]) == "大高緑地"

    def test_no_match(self):
        assert match_court("知らないコート", CONF["courts"]) is None


class TestReservationsToEvents:
    def test_conversion(self):
        df = pd.DataFrame(
            [
                {
                    "court": "大高緑地",
                    "court_number": "1",
                    "date": datetime(2026, 10, 3),
                    "start": "13",
                    "end": "17",
                    "account": "x",
                },
                {
                    "court": "モリコロパーク",
                    "court_number": "2",
                    "date": datetime(2026, 10, 5),
                    "start": "19",
                    "end": "21",
                    "account": "y",
                },
            ]
        )
        events = reservations_to_events(df, CONF)
        assert len(events) == 3  # 大高2枠 + モリコロ1枠
        assert events[0]["bear_court"] == "大高緑地"
        assert (events[0]["start"], events[0]["end"]) == (13, 15)
        assert (events[1]["start"], events[1]["end"]) == (15, 17)
        assert events[2]["bear_court"] == "モリコロパーク"

    def test_unknown_court_skipped(self):
        df = pd.DataFrame(
            [
                {
                    "court": "知らないコート",
                    "court_number": "1",
                    "date": datetime(2026, 10, 3),
                    "start": "13",
                    "end": "17",
                    "account": "x",
                }
            ]
        )
        assert reservations_to_events(df, CONF) == []

    def test_empty_df(self):
        assert reservations_to_events(pd.DataFrame(), CONF) == []


class TestSelectEventsToPost:
    TODAY = datetime(2026, 7, 2)

    def _event(self, day, start):
        return {
            "court": "大高緑地",
            "bear_court": "大高緑地",
            "date": datetime(2026, 10, day),
            "start": start,
            "end": start + 2,
        }

    def test_excludes_already_posted(self):
        events = [self._event(3, 9), self._event(3, 13)]
        # 9時枠はテニスベアに掲載済み（同一コート）
        existing = [{"date": datetime(2026, 10, 3), "start": 9, "court": "大高緑地公園"}]
        result = select_events_to_post(events, existing, today=self.TODAY)
        assert len(result) == 1
        assert result[0]["start"] == 13

    def test_same_datetime_different_court_posted(self):
        events = [self._event(3, 9)]
        # 同じ日時でも別コートの募集なら掲載対象
        existing = [{"date": datetime(2026, 10, 3), "start": 9, "court": "上納池スポーツ公園"}]
        result = select_events_to_post(events, existing, today=self.TODAY)
        assert len(result) == 1

    def test_unknown_existing_court_treated_as_same(self):
        events = [self._event(3, 9)]
        # 既存募集のコート名が取れていない場合は二重掲載を避けるためスキップ
        existing = [{"date": datetime(2026, 10, 3), "start": 9, "court": ""}]
        result = select_events_to_post(events, existing, today=self.TODAY)
        assert result == []

    def test_excludes_past(self):
        events = [
            {"court": "大高緑地", "bear_court": "大高緑地",
             "date": datetime(2026, 6, 1), "start": 9, "end": 11},  # 過去
            self._event(3, 9),
        ]
        result = select_events_to_post(events, [], today=self.TODAY)
        assert len(result) == 1
        assert result[0]["date"] == datetime(2026, 10, 3)

    def test_all_new(self):
        events = [self._event(3, 9), self._event(4, 13)]
        result = select_events_to_post(events, [], today=self.TODAY)
        assert len(result) == 2


class TestDeadlineDaysFor:
    def test_override_applied(self):
        assert deadline_days_for("上納池", CONF) == 9

    def test_default_used(self):
        assert deadline_days_for("大高緑地", CONF) == 2


class TestComputeDeadline:
    TODAY = datetime(2026, 7, 6)

    def test_empty_uses_days_before(self):
        # 0人 → 開催の9日前、開始時刻
        d = compute_deadline(datetime(2026, 8, 14), 19, 0, 9, self.TODAY)
        assert d == datetime(2026, 8, 5, 19, 0)

    def test_with_participants_is_same_day(self):
        # 参加者あり → 締切は当日
        d = compute_deadline(datetime(2026, 7, 11), 17, 1, 9, self.TODAY)
        assert d == datetime(2026, 7, 11, 17, 0)

    def test_past_deadline_falls_back_to_same_day(self):
        # 0人でも9日前が過去日なら当日にする
        d = compute_deadline(datetime(2026, 7, 10), 19, 0, 9, self.TODAY)
        assert d == datetime(2026, 7, 10, 19, 0)
