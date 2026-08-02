"""prune（ルールA）の純粋ロジックのテスト"""
from datetime import datetime

from netaichi.services.prune import (
    find_filled_practices,
    find_lessons_to_prune,
    format_message,
    same_court,
)


def _ev(day, start, participants, *, lesson, practice, court="モリコロパークテニスコート", end=None):
    ev = {
        "id": f"{day}-{start}-{'L' if lesson else 'P'}",
        "date": datetime(2026, 7, day),
        "start": start,
        "court": court,
        "participants": participants,
        "capacity": 4,
        "is_lesson": lesson,
        "is_practice": practice,
    }
    # 練習の end は run() が編集画面から補完する
    if end is not None:
        ev["end"] = end
    return ev


def _practice(day, start, participants, end, court="モリコロパークテニスコート"):
    return _ev(day, start, participants, lesson=False, practice=True, court=court, end=end)


def _lesson(day, start, court="モリコロパークテニスコート"):
    return _ev(day, start, 0, lesson=True, practice=False, court=court)


class TestFindLessonsToPrune:
    def test_prunes_lesson_when_practice_filled(self):
        events = [
            _practice(4, 13, 2, end=15),   # 練習2人→埋まった
            _lesson(4, 13),                # 同枠レッスン→削除対象
        ]
        result = find_lessons_to_prune(events, 2)
        assert len(result) == 1
        assert result[0]["is_lesson"]
        assert result[0]["start"] == 13

    def test_prunes_both_halves_of_four_hour_practice(self):
        """4時間1本の練習に対し、2時間×2枠のレッスンを両方消す（後半の消し漏れ対策）"""
        events = [
            _practice(4, 13, 2, end=17),
            _lesson(4, 13),
            _lesson(4, 15),
        ]
        result = find_lessons_to_prune(events, 2)
        assert sorted(ev["start"] for ev in result) == [13, 15]

    def test_lesson_starting_at_practice_end_is_kept(self):
        """練習の終了時刻ちょうどに始まるレッスンは範囲外なので残す"""
        events = [
            _practice(4, 13, 2, end=15),
            _lesson(4, 15),
        ]
        assert find_lessons_to_prune(events, 2) == []

    def test_other_court_in_same_range_is_kept(self):
        events = [
            _practice(4, 13, 2, end=17),
            _lesson(4, 15, court="大高緑地テニスコート"),
        ]
        assert find_lessons_to_prune(events, 2) == []

    def test_practice_below_threshold_not_pruned(self):
        events = [
            _practice(4, 13, 1, end=17),   # 練習1人（自分だけ）
            _lesson(4, 13),
            _lesson(4, 15),
        ]
        assert find_lessons_to_prune(events, 2) == []

    def test_no_practice_same_slot(self):
        events = [
            _practice(5, 9, 2, end=13),    # 練習は別の日
            _lesson(4, 13),
        ]
        assert find_lessons_to_prune(events, 2) == []

    def test_only_lessons_returned_not_practice(self):
        events = [
            _practice(4, 13, 3, end=17),
            _lesson(4, 13),
        ]
        result = find_lessons_to_prune(events, 2)
        assert all(ev["is_lesson"] for ev in result)


class TestFindFilledPractices:
    def test_returns_only_filled_practices(self):
        events = [
            _practice(4, 13, 2, end=17),
            _practice(5, 13, 1, end=17),
            _lesson(4, 13),
        ]
        result = find_filled_practices(events, 2)
        assert [ev["date"].day for ev in result] == [4]


class TestSameCourt:
    def test_partial_name_matches(self):
        assert same_court("モリコロパーク", "モリコロパークテニスコート")

    def test_missing_name_does_not_match(self):
        assert not same_court("", "モリコロパークテニスコート")
        assert not same_court("モリコロパークテニスコート", "")


class TestFormatMessage:
    def test_message(self):
        pruned = [_lesson(4, 13)]
        msg = format_message(pruned)
        assert "削除" in msg.split("\n")[0]
        assert "07/04(土) 13時 モリコロパークテニスコート" in msg
