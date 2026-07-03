"""cancel（ルールB）の純粋ロジックのテスト"""
from datetime import datetime

from netaichi.services.cancel import find_empty_lessons, find_solo_practices, format_message


def _ev(day, start, participants, *, lesson, practice, court="モリコロパークテニスコート"):
    return {
        "id": f"{day}-{start}",
        "date": datetime(2026, 7, day),
        "start": start,
        "court": court,
        "participants": participants,
        "is_lesson": lesson,
        "is_practice": practice,
    }


TARGET = datetime(2026, 7, 6)


class TestFindEmptyLessons:
    def test_lesson_with_zero_participants(self):
        events = [_ev(6, 9, 0, lesson=True, practice=False)]
        result = find_empty_lessons(events, TARGET)
        assert len(result) == 1

    def test_lesson_with_participants_not_included(self):
        events = [_ev(6, 9, 1, lesson=True, practice=False)]
        assert find_empty_lessons(events, TARGET) == []

    def test_practice_not_included(self):
        events = [_ev(6, 9, 0, lesson=False, practice=True)]
        assert find_empty_lessons(events, TARGET) == []

    def test_different_date_not_included(self):
        events = [_ev(7, 9, 0, lesson=True, practice=False)]
        assert find_empty_lessons(events, TARGET) == []


class TestFindSoloPractices:
    def test_practice_with_one_participant(self):
        events = [_ev(6, 13, 1, lesson=False, practice=True)]
        result = find_solo_practices(events, TARGET)
        assert len(result) == 1

    def test_practice_with_two_participants_not_included(self):
        events = [_ev(6, 13, 2, lesson=False, practice=True)]
        assert find_solo_practices(events, TARGET) == []

    def test_lesson_not_included(self):
        events = [_ev(6, 13, 1, lesson=True, practice=False)]
        assert find_solo_practices(events, TARGET) == []

    def test_different_date_not_included(self):
        events = [_ev(7, 13, 1, lesson=False, practice=True)]
        assert find_solo_practices(events, TARGET) == []


class TestFormatMessage:
    def test_lesson_label(self):
        ev = _ev(6, 9, 0, lesson=True, practice=False)
        msg = format_message([ev])
        assert "レッスン(集客0)" in msg

    def test_practice_label(self):
        ev = _ev(6, 13, 1, lesson=False, practice=True)
        msg = format_message([ev])
        assert "練習会(自分のみ)" in msg
