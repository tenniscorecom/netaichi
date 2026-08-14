"""shrink（ルールC）の純粋ロジックのテスト"""
from datetime import datetime
from unittest.mock import patch

import pandas as pd

from netaichi.db import M_Account
from netaichi.services.cancel import ReservationSlot
from netaichi.services.shrink import (
    cancel_order,
    find_surplus_courts,
    practice_capacity,
    required_courts,
    required_courts_for_reservation,
    run,
)


TARGET = datetime(2026, 11, 23)  # 夏ではないので1面3人
SUMMER = datetime(2026, 7, 23)  # 夏なので1面4人
OTAKA = "大高緑地"
CONF = {
    "days_before": 2,
    "lesson_courts": 1,
    "practice_capacity": 3,
    "summer_capacity": 4,
    "summer_months": [7, 8],
    "court_map": {OTAKA: OTAKA},
}
SWAP_COURTS = {
    OTAKA: {
        "prefix": "庭球場",
        "priority": [[1, 3, 7, 10], [4, 6, 11, 14], [2, 8, 9], [5, 12, 13]],
    }
}


def _ev(start, participants, *, lesson=False, date=TARGET, court=OTAKA):
    return {
        "id": f"{start}-{participants}",
        "date": date,
        "start": start,
        "court": court,
        "participants": participants,
        "is_lesson": lesson,
        "is_practice": not lesson,
    }


def _reservations(numbers, *, start=9, end=13, date=TARGET, court=OTAKA):
    return pd.DataFrame(
        [
            {
                "date": date,
                "start": start,
                "end": end,
                "court": court,
                "court_number": number,
            }
            for number in numbers
        ]
    )


class TestPracticeCapacity:
    def test_summer(self):
        assert practice_capacity(SUMMER, CONF) == 4

    def test_not_summer(self):
        assert practice_capacity(TARGET, CONF) == 3


class TestRequiredCourts:
    def test_lesson_needs_one_court(self):
        assert required_courts([_ev(9, 3, lesson=True)], 3) == 1

    def test_lesson_with_many_participants_still_one_court(self):
        assert required_courts([_ev(9, 8, lesson=True)], 3) == 1

    def test_empty_lesson_needs_none(self):
        assert required_courts([_ev(9, 0, lesson=True)], 3) == 0

    def test_solo_practice_needs_none(self):
        assert required_courts([_ev(9, 1)], 3) == 0

    def test_three_people_fit_one_court(self):
        assert required_courts([_ev(9, 3)], 3) == 1

    def test_four_people_need_two_courts_outside_summer(self):
        assert required_courts([_ev(9, 4)], 3) == 2

    def test_four_people_fit_one_court_in_summer(self):
        assert required_courts([_ev(9, 4)], 4) == 1

    def test_participants_are_summed_across_events(self):
        assert required_courts([_ev(9, 2), _ev(9, 2)], 3) == 2

    def test_no_events_needs_none(self):
        assert required_courts([], 3) == 0


class TestRequiredCourtsForReservation:
    def test_uses_the_busiest_time_slot(self):
        """前半3人・後半5人なら、多い後半に合わせて2面残す"""
        events = [_ev(9, 3), _ev(11, 5)]
        assert required_courts_for_reservation(events, 3) == 2

    def test_single_slot(self):
        assert required_courts_for_reservation([_ev(9, 2)], 3) == 1


def _slot(number, *, start=9, end=13, date=TARGET, court=OTAKA):
    return ReservationSlot(
        date=date,
        start=start,
        end=end,
        court_name=court,
        court_number=number,
        court_keyword=court,
    )


class TestCancelOrder:
    def test_worst_court_comes_first(self):
        ordered = cancel_order([_slot("1"), _slot("5"), _slot("4")], SWAP_COURTS)

        assert [s.court_number for s in ordered] == ["5", "4", "1"]

    def test_same_rank_cancels_the_larger_number_first(self):
        ordered = cancel_order([_slot("1"), _slot("3")], SWAP_COURTS)

        assert [s.court_number for s in ordered] == ["3", "1"]

    def test_unknown_park_keeps_a_stable_order(self):
        ordered = cancel_order([_slot("2", court="小幡緑地"), _slot("8", court="小幡緑地")], SWAP_COURTS)

        assert [s.court_number for s in ordered] == ["8", "2"]


class TestRun:
    def test_cancels_surplus_as_its_owner(self):
        """余った面は持ち主のアカウントでログインしてから取り消す"""
        master = M_Account(name="本人", id="master", password="x", is_master=True)
        member = M_Account(name="家族", id="member", password="x")
        events = [_ev(9, 2)]  # 2人 → 1面
        reservations = pd.DataFrame(
            [
                {
                    "date": TARGET, "start": 9, "end": 13, "court": OTAKA,
                    "court_number": number, "account": account,
                }
                for number, account in (("3", "master"), ("5", "member"))
            ]
        )

        with (
            patch("netaichi.services.shrink.load_rules", return_value=CONF),
            patch("netaichi.services.shrink.load_swap_rules", return_value={"courts": SWAP_COURTS}),
            patch("netaichi.services.shrink.target_accounts", return_value=[master, member]),
            patch("netaichi.services.shrink.collect_reservations", return_value=reservations),
            patch("netaichi.services.shrink.TennisBear") as bear_class,
            patch("netaichi.services.shrink.NetAichi") as netaichi_class,
            patch("netaichi.services.shrink.notify"),
        ):
            bear_class.return_value.__enter__.return_value.list_organized_events.return_value = events
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.cancel_reservation.return_value = True

            cancelled = run(target_date=TARGET)

        # 真ん中の5番（家族名義）を取り消す。端の3番は残す
        assert [slot.court_number for slot, _, _ in cancelled] == ["5"]
        assert netaichi.login.call_args.kwargs["account"] is member


class TestFindSurplusCourts:
    def test_two_courts_with_three_people_shrink_to_one(self):
        events = [_ev(9, 2), _ev(9, 1)]  # 合計3人 → 1面
        surplus = find_surplus_courts(
            events, _reservations(["3", "5"]), CONF, SWAP_COURTS
        )

        assert len(surplus) == 1
        slot, needed, current = surplus[0]
        assert slot.court_number == "5"  # 端の3番を残し、真ん中の5番を取り消す
        assert (needed, current) == (1, 2)

    def test_keeps_both_courts_when_people_do_not_fit(self):
        events = [_ev(9, 3), _ev(9, 2)]  # 合計5人 → 2面
        surplus = find_surplus_courts(
            events, _reservations(["3", "5"]), CONF, SWAP_COURTS
        )

        assert surplus == []

    def test_summer_fits_four_people_in_one_court(self):
        events = [_ev(9, 4, date=SUMMER)]
        surplus = find_surplus_courts(
            events, _reservations(["3", "5"], date=SUMMER), CONF, SWAP_COURTS
        )

        assert len(surplus) == 1

    def test_single_court_is_left_to_cancel_rule(self):
        events = [_ev(9, 1)]
        surplus = find_surplus_courts(events, _reservations(["3"]), CONF, SWAP_COURTS)

        assert surplus == []

    def test_solo_practice_with_multiple_courts_is_left_to_cancel_rule(self):
        events = [_ev(9, 1)]
        surplus = find_surplus_courts(
            events, _reservations(["3", "5"]), CONF, SWAP_COURTS
        )

        assert surplus == []

    def test_empty_lesson_with_multiple_courts_is_left_to_cancel_rule(self):
        events = [_ev(9, 0, lesson=True)]
        surplus = find_surplus_courts(
            events, _reservations(["3", "5"]), CONF, SWAP_COURTS
        )

        assert surplus == []

    def test_slot_without_court_number_is_left_alone(self):
        """フットサルのように面番号が出ない予約が混じる枠は触らない

        面番号なしで取消を頼むと「庭球場」を含む別の面を掴んでしまう。
        """
        events = [_ev(9, 2)]  # 2人 → 1面
        surplus = find_surplus_courts(
            events, _reservations(["6", ""]), CONF, SWAP_COURTS
        )

        assert surplus == []

    def test_no_events_means_no_judgement(self):
        """募集が出ていない枠は判断材料がないので触らない"""
        surplus = find_surplus_courts([], _reservations(["3", "5"]), CONF, SWAP_COURTS)

        assert surplus == []

    def test_two_lessons_shrink_to_one_court(self):
        events = [_ev(9, 2, lesson=True), _ev(9, 1, lesson=True)]
        surplus = find_surplus_courts(
            events, _reservations(["3", "5"]), CONF, SWAP_COURTS
        )

        assert len(surplus) == 1
        assert surplus[0][1] == 1

    def test_worst_courts_are_cancelled_first(self):
        """3面から1面に減らすとき、端の面を残して真ん中から取り消す"""
        events = [_ev(9, 2)]  # 2人 → 1面
        surplus = find_surplus_courts(
            events, _reservations(["1", "5", "13"]), CONF, SWAP_COURTS
        )

        cancelled = sorted(slot.court_number for slot, _, _ in surplus)
        assert cancelled == ["13", "5"]

    def test_other_time_slot_is_not_mixed(self):
        events = [_ev(9, 2)]
        reservations = pd.concat(
            [_reservations(["3", "5"]), _reservations(["7", "9"], start=13, end=17)]
        )

        surplus = find_surplus_courts(events, reservations, CONF, SWAP_COURTS)

        assert len(surplus) == 1
        assert surplus[0][0].start == 9
