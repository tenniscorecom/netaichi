"""コート乗り換えの純粋ロジックのテスト"""
from datetime import datetime
from unittest.mock import Mock, call

from sqlalchemy.exc import OperationalError

from netaichi.services.swap import (
    court_rank,
    covers,
    find_swap_targets,
    format_orphan_message,
    normalize_number,
    parse_court_number,
    _swap_one,
)


TARGET = datetime(2026, 11, 23)
OTAKA = "大高緑地"
MORIKORO = "愛・地球博記念公園"
# 1-3 / 4-6 / 7-10 / 11-14 の4ブロック。各ブロックの端が当たり
OTAKA_PRIORITY = [[1, 3, 7, 10], [4, 6, 11, 14], [2, 8, 9], [5, 12, 13]]
COURTS = {
    OTAKA: {"prefix": "庭球場", "priority": OTAKA_PRIORITY},
    MORIKORO: {"prefix": "庭球場", "priority": [[1], [6], [2, 3, 4, 5]]},
}


def _reservation(number, *, park=OTAKA, start=9, end=13, date=TARGET, account="oguri"):
    return {
        "account_id": account,
        "park": park,
        "date": date,
        "start": start,
        "end": end,
        "number": number,
    }


def _slot(number, *, park=OTAKA, start=9, end=13, date=TARGET):
    return {
        "value": park,
        "date": date,
        "facility": f"庭球場{number}（人工芝）",
        "start": start,
        "end": end,
    }


class TestCourtRank:
    def test_first_row_is_best(self):
        assert court_rank(1, OTAKA_PRIORITY) == 0

    def test_same_row_is_equal(self):
        assert court_rank(3, OTAKA_PRIORITY) == court_rank(10, OTAKA_PRIORITY)

    def test_later_row_is_worse(self):
        assert court_rank(5, OTAKA_PRIORITY) > court_rank(4, OTAKA_PRIORITY)

    def test_unlisted_number_is_last(self):
        assert court_rank(99, OTAKA_PRIORITY) == len(OTAKA_PRIORITY)


class TestParseCourtNumber:
    def test_full_width_number(self):
        assert parse_court_number("庭球場１４（人工芝）", "庭球場") == 14

    def test_half_width_number(self):
        assert parse_court_number("庭球場7(人工芝)", "庭球場") == 7

    def test_single_digit_is_not_confused_with_two_digits(self):
        """庭球場11 を 庭球場1 と読み違えない"""
        assert parse_court_number("庭球場11", "庭球場") == 11

    def test_other_facility_returns_none(self):
        assert parse_court_number("フットサルコートA", "庭球場") is None


class TestNormalizeNumber:
    def test_full_width(self):
        assert normalize_number("１４") == 14

    def test_plain(self):
        assert normalize_number("7") == 7

    def test_no_digits(self):
        assert normalize_number("A") is None


class TestCovers:
    def test_exact_match(self):
        assert covers({"start": 9, "end": 13}, 9, 13)

    def test_wider_slot(self):
        assert covers({"start": 9, "end": 17}, 9, 13)

    def test_partial_slot_is_rejected(self):
        assert not covers({"start": 9, "end": 11}, 9, 13)

    def test_late_start_is_rejected(self):
        assert not covers({"start": 11, "end": 13}, 9, 13)


class TestFindSwapTargets:
    def test_moves_to_better_court(self):
        targets = find_swap_targets([_reservation(5)], [_slot(3)], COURTS)

        assert len(targets) == 1
        assert (targets[0].from_number, targets[0].to_number) == (5, 3)

    def test_does_not_move_to_worse_court(self):
        assert find_swap_targets([_reservation(1)], [_slot(5)], COURTS) == []

    def test_does_not_move_within_same_rank(self):
        """同じ順位の中では動かさない（1も3も端かつ手前）"""
        assert find_swap_targets([_reservation(1)], [_slot(3)], COURTS) == []

    def test_does_not_move_when_slot_covers_partially(self):
        """9-13時の予約に対し9-11時しか空いていないなら動かさない"""
        slots = [_slot(3, start=9, end=11)]
        assert find_swap_targets([_reservation(5)], slots, COURTS) == []

    def test_ignores_unlisted_number_as_destination(self):
        assert find_swap_targets([_reservation(5)], [_slot(99)], COURTS) == []

    def test_picks_the_best_of_several_slots(self):
        targets = find_swap_targets(
            [_reservation(5)], [_slot(4), _slot(2), _slot(7)], COURTS
        )

        assert len(targets) == 1
        assert targets[0].to_number == 7

    def test_two_reservations_do_not_take_the_same_slot(self):
        """同じ日時に2面持っているとき、同じ空きコートを奪い合わない"""
        reservations = [_reservation(5), _reservation(12)]

        targets = find_swap_targets(reservations, [_slot(3)], COURTS)

        assert len(targets) == 1
        assert targets[0].to_number == 3

    def test_each_reservation_moves_once(self):
        targets = find_swap_targets([_reservation(5)], [_slot(3), _slot(7)], COURTS)

        assert len(targets) == 1

    def test_reservations_with_different_ends_are_distinct(self):
        """開始時刻が同じでも別の予約なら、一方を重複行として捨てない"""
        reservations = [
            _reservation(5, start=9, end=11),
            _reservation(5, start=9, end=13),
        ]
        slots = [_slot(3, start=9, end=11), _slot(7, start=9, end=13)]

        targets = find_swap_targets(reservations, slots, COURTS)

        assert len(targets) == 2

    def test_different_date_is_not_mixed(self):
        slots = [_slot(3, date=datetime(2026, 11, 24))]
        assert find_swap_targets([_reservation(5)], slots, COURTS) == []

    def test_different_park_is_not_mixed(self):
        slots = [_slot(1, park=MORIKORO)]
        assert find_swap_targets([_reservation(5)], slots, COURTS) == []

    def test_unknown_park_is_skipped(self):
        reservations = [_reservation(5, park="小幡緑地")]
        slots = [_slot(3, park="小幡緑地")]
        assert find_swap_targets(reservations, slots, COURTS) == []

    def test_same_court_number_is_skipped(self):
        assert find_swap_targets([_reservation(5)], [_slot(5)], COURTS) == []

    def test_different_time_slots_can_use_the_same_court(self):
        """同じコートでも時間帯が重ならなければ両方移動できる"""
        reservations = [_reservation(5, start=9, end=13), _reservation(12, start=13, end=17)]
        slots = [_slot(3, start=9, end=13), _slot(3, start=13, end=17)]

        targets = find_swap_targets(reservations, slots, COURTS)

        assert len(targets) == 2
        assert all(t.to_number == 3 for t in targets)

    def test_morikoro_prefers_court_one(self):
        reservations = [_reservation(3, park=MORIKORO)]
        slots = [_slot(6, park=MORIKORO), _slot(1, park=MORIKORO)]

        targets = find_swap_targets(reservations, slots, COURTS)

        assert targets[0].to_number == 1


class TestTargetAccounts:
    def test_falls_back_to_master_when_table_is_missing(self, monkeypatch):
        """DBを持たない環境（GitHub Actions）ではマスターだけを対象にする"""
        from netaichi.services import swap

        monkeypatch.setattr(
            swap,
            "get_group_accounts",
            Mock(side_effect=OperationalError("select", {}, Exception())),
        )

        accounts = swap.target_accounts("oguri")

        assert [a.id for a in accounts] == [swap.GROUP_IDS["oguri"]]

    def test_uses_db_accounts_when_available(self, monkeypatch):
        from netaichi.services import swap

        monkeypatch.setattr(
            swap, "get_group_accounts", Mock(return_value=["a", "b", "c"])
        )

        assert swap.target_accounts("oguri") == ["a", "b", "c"]


class TestFormatOrphanMessage:
    def test_tells_which_court_to_cancel(self):
        targets = find_swap_targets([_reservation(5)], [_slot(3)], COURTS)

        message = format_orphan_message(targets)

        assert "庭球場5" in message
        assert "庭球場3" in message
        assert "取り消して" in message
        assert "予約状況の一覧" in message


class TestSwapOne:
    def test_reserves_then_cancels_only_after_confirmation(self):
        browser = Mock()
        browser.reserve_available_slot.return_value = True
        browser.cancel_reservation.return_value = True
        target = find_swap_targets([_reservation(5)], [_slot(3)], COURTS)[0]

        assert _swap_one(browser, target, []) is True
        assert browser.method_calls[:2] == [
            call.reserve_available_slot(TARGET, 9, 13, OTAKA, "3"),
            call.cancel_reservation(TARGET, 9, 13, OTAKA, "5"),
        ]

    def test_does_not_cancel_when_destination_is_unconfirmed(self):
        browser = Mock()
        browser.reserve_available_slot.return_value = False
        target = find_swap_targets([_reservation(5)], [_slot(3)], COURTS)[0]

        assert _swap_one(browser, target, []) is False
        browser.cancel_reservation.assert_not_called()
