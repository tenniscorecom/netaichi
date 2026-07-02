"""bear の純粋ロジック（枠分割・コート照合・イベント変換）のテスト"""
from datetime import datetime

import pandas as pd

from netaichi.services.bear import match_court, reservations_to_events, split_slots

CONF = {
    "event_hours": 2,
    "courts": {
        "大高緑地": "大高緑地",
        "モリコロ": "モリコロパーク",
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
