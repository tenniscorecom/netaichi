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
