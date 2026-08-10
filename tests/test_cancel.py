"""cancel（ルールB）の純粋ロジックのテスト"""
from datetime import datetime
from unittest.mock import call, patch

import pandas as pd

from netaichi.services.cancel import (
    ReservationSlot,
    find_empty_lessons,
    find_reservation,
    find_solo_practices,
    format_message,
    merge_event_ranges,
    run,
)


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
COURT_NAME = "愛・地球博記念公園"
BEAR_COURT = "モリコロパークテニスコート"
COURT_MAP = {"モリコロパーク": COURT_NAME}
CONF = {"days_before": 2, "event_hours": 2, "court_map": COURT_MAP}


def _reservations(start=13, end=17):
    return pd.DataFrame(
        [
            {
                "date": TARGET,
                "start": str(start),
                "end": str(end),
                "court": COURT_NAME,
                "court_number": "1",
            }
        ]
    )


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


class TestFindReservation:
    def test_split_events_match_same_four_hour_reservation(self):
        reservations = _reservations()

        first = find_reservation(
            _ev(6, 13, 0, lesson=True, practice=False),
            COURT_NAME,
            reservations,
        )
        second = find_reservation(
            _ev(6, 15, 0, lesson=True, practice=False),
            COURT_NAME,
            reservations,
        )

        expected = ReservationSlot(TARGET, 13, 17, COURT_NAME, "1", COURT_NAME)
        assert first == expected
        assert second == expected

    def test_adjacent_reservations_match_separately(self):
        reservations = pd.concat([_reservations(13, 15), _reservations(15, 17)])

        first = find_reservation(
            _ev(6, 13, 0, lesson=True, practice=False),
            COURT_NAME,
            reservations,
        )
        second = find_reservation(
            _ev(6, 15, 0, lesson=True, practice=False),
            COURT_NAME,
            reservations,
        )

        assert first == ReservationSlot(TARGET, 13, 15, COURT_NAME, "1", COURT_NAME)
        assert second == ReservationSlot(TARGET, 15, 17, COURT_NAME, "1", COURT_NAME)


class TestMergeEventRanges:
    def test_single_lesson_uses_event_hours(self):
        events = [_ev(6, 13, 0, lesson=True, practice=False)]
        assert merge_event_ranges(events, 2, 17) == [(13, 15)]

    def test_four_hour_practice_keeps_its_own_length(self):
        """残す練習が4時間1本なら、4時間まるごと取り直す"""
        practice = {**_ev(6, 13, 2, lesson=False, practice=True), "end": 17}
        assert merge_event_ranges([practice], 2, 17) == [(13, 17)]

    def test_contiguous_lessons_are_merged(self):
        events = [
            _ev(6, 13, 0, lesson=True, practice=False),
            _ev(6, 15, 0, lesson=True, practice=False),
        ]
        assert merge_event_ranges(events, 2, 17) == [(13, 17)]

    def test_end_is_clipped_to_reservation(self):
        events = [_ev(6, 15, 0, lesson=True, practice=False)]
        assert merge_event_ranges(events, 4, 17) == [(15, 17)]

    def test_gap_produces_separate_ranges(self):
        events = [
            _ev(6, 9, 0, lesson=True, practice=False),
            _ev(6, 15, 0, lesson=True, practice=False),
        ]
        assert merge_event_ranges(events, 2, 17) == [(9, 11), (15, 17)]


class TestFormatMessage:
    def test_lesson_label(self):
        ev = _ev(6, 9, 0, lesson=True, practice=False)
        msg = format_message([ev])
        assert "レッスン(集客0)" in msg

    def test_practice_label(self):
        ev = _ev(6, 13, 1, lesson=False, practice=True)
        msg = format_message([ev])
        assert "練習会(自分のみ)" in msg


class TestRun:
    def test_continues_after_one_reservation_group_raises(self):
        first = _ev(6, 13, 0, lesson=True, practice=False, court=BEAR_COURT)
        second = _ev(6, 15, 0, lesson=True, practice=False, court=BEAR_COURT)
        reservations = pd.concat([_reservations(13, 15), _reservations(15, 17)])

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [first, second]
            tennis_bear.delete_event.return_value = True
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = reservations
            netaichi.cancel_reservation.side_effect = [RuntimeError("stale"), True]

            cancelled, warned = run(target_date=TARGET)

        assert cancelled == [second]
        assert warned == []
        assert netaichi.cancel_reservation.call_count == 2
        tennis_bear.delete_event.assert_called_once_with(second["id"])
        assert any(
            "手動で予約状況を確認" in call_args.args[0]
            for call_args in notify.call_args_list
        )

    def test_notifies_urgent_failure_when_error_occurs_after_cancellation(self):
        empty_event = _ev(
            6,
            13,
            0,
            lesson=True,
            practice=False,
            court=BEAR_COURT,
        )
        occupied_event = _ev(
            6,
            15,
            2,
            lesson=True,
            practice=False,
            court=BEAR_COURT,
        )

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [
                empty_event,
                occupied_event,
            ]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = _reservations()
            netaichi.cancel_reservation.return_value = True
            netaichi.reserve_available_slot.side_effect = RuntimeError("画面エラー")

            cancelled, warned = run(target_date=TARGET)

        assert cancelled == []
        assert warned == []
        tennis_bear.delete_event.assert_not_called()
        messages = [call_args.args[0] for call_args in notify.call_args_list]
        assert any("取り消したまま取り直せていない可能性" in message for message in messages)
        assert any("至急手動で確保" in message for message in messages)
        assert not any("手動で予約状況を確認してください" in message for message in messages)

    def test_cancels_four_hour_reservation_once_and_deletes_both_events(self):
        events = [
            _ev(6, 13, 0, lesson=True, practice=False, court=BEAR_COURT),
            _ev(6, 15, 0, lesson=True, practice=False, court=BEAR_COURT),
        ]

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify"),
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = events
            tennis_bear.delete_event.return_value = True
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = _reservations()
            netaichi.cancel_reservation.return_value = True

            cancelled, warned = run(target_date=TARGET)

        assert cancelled == events
        assert warned == []
        netaichi.cancel_reservation.assert_called_once_with(
            TARGET,
            13,
            17,
            COURT_NAME,
            "1",
        )
        netaichi.reserve_available_slot.assert_not_called()
        assert tennis_bear.delete_event.call_args_list == [
            call(events[0]["id"]),
            call(events[1]["id"]),
        ]

    def test_rebooks_only_occupied_half_of_four_hour_reservation(self):
        empty_event = _ev(
            6,
            13,
            0,
            lesson=True,
            practice=False,
            court=BEAR_COURT,
        )
        occupied_event = _ev(
            6,
            15,
            2,
            lesson=True,
            practice=False,
            court=BEAR_COURT,
        )

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify"),
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [
                empty_event,
                occupied_event,
            ]
            tennis_bear.delete_event.return_value = True
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = _reservations()
            netaichi.cancel_reservation.return_value = True
            netaichi.reserve_available_slot.return_value = True

            cancelled, warned = run(target_date=TARGET)

        assert cancelled == [empty_event]
        assert warned == []
        netaichi.reserve_available_slot.assert_called_once_with(
            TARGET,
            15,
            17,
            COURT_NAME,
            "1",
        )
        tennis_bear.delete_event.assert_called_once_with(empty_event["id"])

    def test_restores_original_time_when_partial_rebook_fails(self):
        empty_event = _ev(
            6,
            13,
            0,
            lesson=True,
            practice=False,
            court=BEAR_COURT,
        )
        occupied_event = _ev(
            6,
            15,
            2,
            lesson=True,
            practice=False,
            court=BEAR_COURT,
        )

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify"),
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [
                empty_event,
                occupied_event,
            ]
            tennis_bear.delete_event.return_value = True
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = _reservations()
            netaichi.cancel_reservation.return_value = True
            netaichi.reserve_available_slot.side_effect = [False, True]
            netaichi.reset_reservation_session.return_value = True

            cancelled, warned = run(target_date=TARGET)

        assert cancelled == [empty_event]
        assert warned == []
        assert netaichi.reserve_available_slot.call_args_list == [
            call(TARGET, 15, 17, COURT_NAME, "1"),
            call(TARGET, 13, 17, COURT_NAME, "1"),
        ]
        tennis_bear.delete_event.assert_called_once_with(empty_event["id"])

    def test_keeps_bear_events_when_partial_rebook_and_restore_fail(self):
        empty_event = _ev(
            6,
            13,
            0,
            lesson=True,
            practice=False,
            court=BEAR_COURT,
        )
        occupied_event = _ev(
            6,
            15,
            2,
            lesson=True,
            practice=False,
            court=BEAR_COURT,
        )

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [
                empty_event,
                occupied_event,
            ]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = _reservations()
            netaichi.cancel_reservation.return_value = True
            netaichi.reserve_available_slot.side_effect = [False, False]
            netaichi.reset_reservation_session.return_value = True

            cancelled, warned = run(target_date=TARGET)

        assert cancelled == []
        assert warned == []
        tennis_bear.delete_event.assert_not_called()
        assert "至急手動で確保" in notify.call_args.args[0]
