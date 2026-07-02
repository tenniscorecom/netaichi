"""cancel（ルールB）の純粋ロジックのテスト"""
from datetime import datetime

from netaichi.services.cancel import find_empty_lessons, format_message, map_court

COURT_MAP = {"大高緑地": "大高緑地", "モリコロパーク": "愛・地球博記念公園"}


def _lesson(day, start, participants, court, is_lesson=True, is_practice=False):
    return {
        "id": f"{day}{start}",
        "date": datetime(2026, 7, day),
        "start": start,
        "court": court,
        "participants": participants,
        "capacity": 4,
        "is_lesson": is_lesson,
        "is_practice": is_practice,
    }


class TestFindEmptyLessons:
    def test_only_zero_participant_lessons_on_target_date(self):
        events = [
            _lesson(6, 19, 0, "モリコロパークテニスコート"),
            _lesson(6, 21, 2, "モリコロパークテニスコート"),  # 2人→対象外
            _lesson(9, 19, 0, "モリコロパークテニスコート"),  # 別日→対象外
        ]
        result = find_empty_lessons(events, datetime(2026, 7, 6))
        assert len(result) == 1
        assert result[0]["start"] == 19

    def test_practice_excluded(self):
        events = [
            _lesson(6, 13, 0, "モリコロパークテニスコート",
                    is_lesson=False, is_practice=True),  # 練習は対象外
        ]
        assert find_empty_lessons(events, datetime(2026, 7, 6)) == []


class TestMapCourt:
    def test_odaka(self):
        assert map_court("大高緑地テニスコート", COURT_MAP) == "大高緑地"

    def test_morikoro_to_official_name(self):
        assert map_court("モリコロパークテニスコート", COURT_MAP) == "愛・地球博記念公園"

    def test_unmapped(self):
        assert map_court("日進市上納池スポーツ公園", COURT_MAP) is None


class TestFormatMessage:
    def test_message(self):
        cancelled = [_lesson(6, 19, 0, "モリコロパークテニスコート")]
        msg = format_message(cancelled)
        assert "取消" in msg.split("\n")[0]
        assert "07/06(月) 19時 モリコロパークテニスコート" in msg
