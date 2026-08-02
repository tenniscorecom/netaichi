"""eaichi_notice（ルールC・窓口取消の事前通知）の純粋ロジックのテスト"""
from datetime import datetime

from netaichi.services.eaichi_notice import (
    find_notice_targets,
    format_message,
    is_unwanted,
    notice_date,
)

CONF = {
    "courts": {
        "上納池": {"days_before": 9, "limit_days_before": 8, "closed_weekday": 0},
    }
}
COURT = "日進市上納池スポーツ公園"


def _ev(date, start=19, participants=0, *, lesson=True, court=COURT):
    return {
        "id": f"{date:%m%d}-{start}",
        "date": date,
        "start": start,
        "court": court,
        "participants": participants,
        "capacity": 4,
        "is_lesson": lesson,
        "is_practice": not lesson,
    }


class TestNoticeDate:
    def test_nine_days_before(self):
        # 2026-08-11(火) の9日前 = 08-02(日) 休館日ではないのでそのまま
        assert notice_date(datetime(2026, 8, 11), 9, 0) == datetime(2026, 8, 2)

    def test_shifts_to_sunday_when_monday(self):
        # 2026-08-12(水) の9日前 = 08-03(月) 休館 → 前日の 08-02(日)
        assert notice_date(datetime(2026, 8, 12), 9, 0) == datetime(2026, 8, 2)

    def test_without_closed_weekday(self):
        assert notice_date(datetime(2026, 8, 12), 9) == datetime(2026, 8, 3)


class TestIsUnwanted:
    def test_empty_lesson(self):
        assert is_unwanted(_ev(datetime(2026, 8, 11), participants=0))

    def test_lesson_with_participant(self):
        assert not is_unwanted(_ev(datetime(2026, 8, 11), participants=1))

    def test_solo_practice(self):
        assert is_unwanted(_ev(datetime(2026, 8, 11), participants=1, lesson=False))

    def test_practice_with_others(self):
        assert not is_unwanted(_ev(datetime(2026, 8, 11), participants=2, lesson=False))


class TestFindNoticeTargets:
    def test_notifies_on_ninth_day_before(self):
        events = [_ev(datetime(2026, 8, 11))]
        result = find_notice_targets(events, CONF, datetime(2026, 8, 2))
        assert len(result) == 1
        assert result[0]["limit"] == datetime(2026, 8, 3)

    def test_monday_notice_moves_to_sunday(self):
        """9日前が月曜(休館)の回は、前日の日曜に通知する"""
        events = [_ev(datetime(2026, 8, 12))]
        assert find_notice_targets(events, CONF, datetime(2026, 8, 3)) == []
        assert len(find_notice_targets(events, CONF, datetime(2026, 8, 2))) == 1

    def test_not_notified_on_other_days(self):
        events = [_ev(datetime(2026, 8, 11))]
        assert find_notice_targets(events, CONF, datetime(2026, 8, 1)) == []
        assert find_notice_targets(events, CONF, datetime(2026, 8, 3)) == []

    def test_lesson_with_participant_not_notified(self):
        events = [_ev(datetime(2026, 8, 11), participants=1)]
        assert find_notice_targets(events, CONF, datetime(2026, 8, 2)) == []

    def test_other_court_not_notified(self):
        events = [_ev(datetime(2026, 8, 11), court="大高緑地テニスコート")]
        assert find_notice_targets(events, CONF, datetime(2026, 8, 2)) == []


class TestFormatMessage:
    def test_message(self):
        targets = find_notice_targets(
            [_ev(datetime(2026, 8, 11))], CONF, datetime(2026, 8, 2)
        )
        msg = format_message(targets)
        assert "窓口" in msg.split("\n")[0]
        assert "08/11(火) 19時 日進市上納池スポーツ公園【レッスン(0人)】" in msg
        assert "取消期限 08/03(月)" in msg
