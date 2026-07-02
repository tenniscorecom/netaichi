"""build_lottery_data / rule_applies / lottery_month_dates のユニットテスト。

Selenium・DB不要（T_LotteryDataの生成のみ）。
"""
from datetime import datetime

from netaichi.services.lottery import (
    build_lottery_data,
    lottery_month_dates,
    rule_applies,
)

WEEKEND_RULE = {
    "name": "土日祝の昼",
    "days": "weekend_holiday",
    "times": [[9, 13], [13, 17]],
    "amount": 1,
    "courts": ["130", "180"],
}

WEEKNIGHT_RULE = {
    "name": "平日ナイター",
    "days": [0, 1, 3, 4],
    "times": [[19, 21]],
    "amount": 1,
    "courts": ["400"],
}


class TestRuleApplies:
    def test_saturday_matches_weekend_holiday(self):
        assert rule_applies(WEEKEND_RULE, datetime(2026, 10, 3))  # 土曜

    def test_holiday_matches_weekend_holiday(self):
        assert rule_applies(WEEKEND_RULE, datetime(2026, 10, 12))  # スポーツの日（月曜）

    def test_ordinary_weekday_does_not_match_weekend_holiday(self):
        assert not rule_applies(WEEKEND_RULE, datetime(2026, 10, 2))  # 金曜

    def test_monday_matches_weeknight(self):
        assert rule_applies(WEEKNIGHT_RULE, datetime(2026, 10, 5))  # 月曜

    def test_wednesday_does_not_match_weeknight(self):
        assert not rule_applies(WEEKNIGHT_RULE, datetime(2026, 10, 7))  # 水曜

    def test_holiday_excluded_from_weeknight(self):
        assert not rule_applies(WEEKNIGHT_RULE, datetime(2026, 10, 12))  # 祝日の月曜


class TestBuildLotteryData:
    def test_weekend_generates_two_slots_per_court(self):
        data = build_lottery_data(
            [WEEKEND_RULE], [datetime(2026, 10, 3)], account_group="test"
        )
        # 2コート × 2時間帯
        assert len(data) == 4
        assert {(d.value, d.start, d.end) for d in data} == {
            ("130", 9, 13),
            ("130", 13, 17),
            ("180", 9, 13),
            ("180", 13, 17),
        }
        assert all(d.account_group == "test" for d in data)
        assert all(d.amount == 1 for d in data)

    def test_weekday_generates_night_slot(self):
        data = build_lottery_data(
            [WEEKNIGHT_RULE], [datetime(2026, 10, 5)], account_group="test"
        )
        assert len(data) == 1
        assert (data[0].value, data[0].start, data[0].end) == ("400", 19, 21)

    def test_no_rule_matches_returns_empty(self):
        data = build_lottery_data(
            [WEEKNIGHT_RULE], [datetime(2026, 10, 3)], account_group="test"  # 土曜
        )
        assert data == []

    def test_multiple_rules_combined(self):
        dates = [datetime(2026, 10, 3), datetime(2026, 10, 5)]  # 土曜・月曜
        data = build_lottery_data(
            [WEEKEND_RULE, WEEKNIGHT_RULE], dates, account_group="test"
        )
        assert len(data) == 5  # 土曜4 + 月曜1


class TestLotteryMonthDates:
    def test_returns_all_days_of_target_month(self):
        dates = lottery_month_dates(base=datetime(2026, 7, 1), months=3)
        assert len(dates) == 31  # 2026年10月
        assert dates[0] == datetime(2026, 10, 1)
        assert dates[-1] == datetime(2026, 10, 31)

    def test_february(self):
        dates = lottery_month_dates(base=datetime(2026, 11, 1), months=3)
        assert len(dates) == 28  # 2027年2月
