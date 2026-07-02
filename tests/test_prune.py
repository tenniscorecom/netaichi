"""prune（ルールA）の純粋ロジックのテスト"""
from datetime import datetime

from netaichi.services.prune import find_lessons_to_prune, format_message


def _ev(day, start, participants, *, lesson, practice, court="モリコロパークテニスコート"):
    return {
        "id": f"{day}-{start}-{'L' if lesson else 'P'}",
        "date": datetime(2026, 7, day),
        "start": start,
        "court": court,
        "participants": participants,
        "capacity": 4,
        "is_lesson": lesson,
        "is_practice": practice,
    }


class TestFindLessonsToPrune:
    def test_prunes_lesson_when_practice_filled(self):
        events = [
            _ev(4, 13, 2, lesson=False, practice=True),   # 練習2人→埋まった
            _ev(4, 13, 0, lesson=True, practice=False),   # 同枠レッスン→削除対象
        ]
        result = find_lessons_to_prune(events, 2)
        assert len(result) == 1
        assert result[0]["is_lesson"]
        assert result[0]["start"] == 13

    def test_practice_below_threshold_not_pruned(self):
        events = [
            _ev(4, 13, 1, lesson=False, practice=True),   # 練習1人（自分だけ）
            _ev(4, 13, 0, lesson=True, practice=False),
        ]
        assert find_lessons_to_prune(events, 2) == []

    def test_no_practice_same_slot(self):
        events = [
            _ev(5, 9, 2, lesson=False, practice=True),    # 練習は別の日時
            _ev(4, 13, 0, lesson=True, practice=False),
        ]
        assert find_lessons_to_prune(events, 2) == []

    def test_only_lessons_returned_not_practice(self):
        events = [
            _ev(4, 13, 3, lesson=False, practice=True),
            _ev(4, 13, 0, lesson=True, practice=False),
        ]
        result = find_lessons_to_prune(events, 2)
        assert all(ev["is_lesson"] for ev in result)


class TestFormatMessage:
    def test_message(self):
        pruned = [_ev(4, 13, 0, lesson=True, practice=False)]
        msg = format_message(pruned)
        assert "削除" in msg.split("\n")[0]
        assert "07/04(土) 13時 モリコロパークテニスコート" in msg
