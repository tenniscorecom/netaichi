"""cancel（ルールB）の失敗通知と再確認パスのテスト。

実際のネットあいち／テニスベアに繋がないことを確認するため、TennisBear /
NetAichi / notify をモック化し、run() が返す Discord 通知文だけを見る。
"""
from datetime import datetime
from unittest.mock import call, patch

import pandas as pd
import pytest

from netaichi.db import M_Account
from netaichi.services.cancel import (
    format_cancel_failure_message,
    format_message,
    format_unmatched_court_message,
    format_unmatched_reservation_message,
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

MASTER_ID = "master"
MEMBER_ID = "member"
MASTER = M_Account(name="本人", id=MASTER_ID, password="x", is_master=True)
MEMBER = M_Account(name="家族", id=MEMBER_ID, password="x")


def _reservations(start=13, end=17, account=MASTER_ID):
    return pd.DataFrame(
        [
            {
                "date": TARGET,
                "start": str(start),
                "end": str(end),
                "court": COURT_NAME,
                "court_number": "1",
                "account": account,
            }
        ]
    )


@pytest.fixture
def patched_env(monkeypatch):
    """テスト共通: TennisBear / NetAichi / notify を差し替える土台"""
    monkeypatch.setattr(
        "netaichi.services.cancel.target_accounts",
        lambda *args, **kwargs: [MASTER, MEMBER],
    )


@pytest.fixture
def patched_env_single(monkeypatch):
    """アカウント1件（マスターのみ）のパターン用"""
    monkeypatch.setattr(
        "netaichi.services.cancel.target_accounts",
        lambda *args, **kwargs: [MASTER],
    )


class TestCancelReservationFailure:
    """cancel_reservation が False を返したときの通知"""

    def test_notify_called_once_with_urgent_message(
        self, patched_env,
    ):
        event = _ev(6, 13, 0, lesson=True, practice=False, court=BEAR_COURT)

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [event]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = _reservations()
            # 取消APIが False を返す（ここが事故の再現条件）
            netaichi.cancel_reservation.return_value = False

            cancelled, warned = run(target_date=TARGET)

        assert cancelled == []
        assert warned == []
        tennis_bear.delete_event.assert_not_called()
        # 🚨 が1回、警告文に「手動で取り消してください」が含まれる
        urgent_calls = [
            c for c in notify.call_args_list
            if "🚨" in c.args[0] and "手動で取り消してください" in c.args[0]
        ]
        assert len(urgent_calls) == 1


class TestFindReservationUnmatched:
    """find_reservation が None のときの通知"""

    def test_warning_notification_when_no_reservation_match(self, patched_env):
        # モリコロパークは対応コート、予約一覧は空 → 対応する予約なし
        event = _ev(6, 13, 0, lesson=True, practice=False, court=BEAR_COURT)

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [event]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = pd.DataFrame()

            cancelled, warned = run(target_date=TARGET)

        assert cancelled == []
        assert warned == []
        # ⚠️ が1回、対応する予約が見つからない主旨
        warning_calls = [
            c for c in notify.call_args_list
            if "⚠️" in c.args[0] and "対応するネットあいちの予約" in c.args[0]
        ]
        assert len(warning_calls) == 1

    def test_message_marks_master_only_judgement_when_single_account(
        self, patched_env_single,
    ):
        """アカウント1件のときは「マスターのみ判定」文言が必ず入る"""
        event = _ev(6, 13, 0, lesson=True, practice=False, court=BEAR_COURT)

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [event]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = pd.DataFrame()

            run(target_date=TARGET)

        messages = [c.args[0] for c in notify.call_args_list]
        unmatched_msgs = [m for m in messages if "対応するネットあいちの予約" in m]
        assert len(unmatched_msgs) == 1
        assert "マスターアカウントのみで判定" in unmatched_msgs[0]

    def test_message_omits_master_only_note_when_multiple_accounts(
        self, patched_env,
    ):
        """複数アカウント時は「マスターのみ判定」文言は付かない"""
        event = _ev(6, 13, 0, lesson=True, practice=False, court=BEAR_COURT)

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [event]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = pd.DataFrame()

            run(target_date=TARGET)

        messages = [c.args[0] for c in notify.call_args_list]
        unmatched_msgs = [m for m in messages if "対応するネットあいちの予約" in m]
        assert len(unmatched_msgs) == 1
        assert "マスターアカウントのみで判定" not in unmatched_msgs[0]


class TestMapCourtUnmatched:
    """map_court が None（未対応コート）のときの通知"""

    def test_warning_notification_for_unsupported_court(self, patched_env):
        # コート名に court_map のキーが含まれない → map_court は None
        event = _ev(
            6,
            13,
            0,
            lesson=True,
            practice=False,
            court="上納池テニスコート",
        )

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [event]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = _reservations()

            run(target_date=TARGET)

        warning_calls = [
            c for c in notify.call_args_list
            if "⚠️" in c.args[0] and "未対応" in c.args[0]
        ]
        assert len(warning_calls) == 1


class TestRecheckPath:
    """is_recheck=True で再確認パスとして動く"""

    def test_no_notification_when_nothing_to_recheck(self, patched_env):
        """再確認パスで対象0件のときは notify を呼ばない（ノイズ抑止）"""
        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = []  # 対象なし
            netaichi = netaichi_class.return_value.__enter__.return_value

            cancelled, warned = run(
                target_date=TARGET,
                is_recheck=True,
            )

        assert cancelled == []
        assert warned == []
        notify.assert_not_called()

    def test_recheck_uses_different_header_when_unmatched(self, patched_env):
        """予約なしは取消済みと予約残りの両方の可能性を示す"""
        event = _ev(6, 13, 0, lesson=True, practice=False, court=BEAR_COURT)

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [event]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = pd.DataFrame()

            run(target_date=TARGET, is_recheck=True)

        messages = [c.args[0] for c in notify.call_args_list]
        recheck_msgs = [m for m in messages if "再確認対象の募集" in m]
        assert len(recheck_msgs) == 1
        assert "既にコート取消済みで募集だけ残っている可能性" in recheck_msgs[0]
        assert "予約が残っている可能性" in recheck_msgs[0]
        assert "前日に取り消せていなかった枠が見つかりました" not in recheck_msgs[0]

    def test_recheck_success_uses_recovery_message(self, patched_env):
        """再確認で取消できた場合は通常成功と区別して回収を通知する"""
        event = _ev(6, 13, 0, lesson=True, practice=False, court=BEAR_COURT)

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [event]
            tennis_bear.delete_event.return_value = True
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = _reservations()
            netaichi.cancel_reservation.return_value = True

            run(target_date=TARGET, is_recheck=True)

        messages = [called.args[0] for called in notify.call_args_list]
        recovery_messages = [message for message in messages if "再確認で回収" in message]
        assert len(recovery_messages) == 1
        assert "不要枠をキャンセルしました" not in recovery_messages[0]

    def test_recheck_does_not_repeat_unsupported_court_notification(self, patched_env):
        """ネット取消不能なコートは翌日の再確認で同じ通知を繰り返さない"""
        event = _ev(
            6,
            13,
            0,
            lesson=True,
            practice=False,
            court="上納池テニスコート",
        )

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [event]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = pd.DataFrame()

            run(target_date=TARGET, is_recheck=True)

        notify.assert_not_called()

    def test_recheck_uses_different_header_when_cancel_fails(self, patched_env):
        """再確認パスで取り直しに失敗したときも通常時と文言が変わる"""
        event = _ev(6, 13, 0, lesson=True, practice=False, court=BEAR_COURT)

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [event]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = _reservations()
            netaichi.cancel_reservation.return_value = False

            run(target_date=TARGET, is_recheck=True)

        messages = [c.args[0] for c in notify.call_args_list]
        recheck_msgs = [
            m for m in messages
            if "🚨" in m and "前日の再確認" in m
        ]
        assert len(recheck_msgs) == 1

    def test_recheck_does_not_notify_warn_targets(self, patched_env):
        """再確認パスでは warn_targets（2日後の予告）を通知しない"""
        # 1日後の枠と2日後の枠が両方ある状況を作る
        later_event = _ev(7, 13, 0, lesson=True, practice=False, court=BEAR_COURT)

        with (
            patch("netaichi.services.cancel.load_rules", return_value=CONF),
            patch("netaichi.services.cancel.TennisBear") as tennis_bear_class,
            patch("netaichi.services.cancel.NetAichi") as netaichi_class,
            patch("netaichi.services.cancel.notify") as notify,
        ):
            tennis_bear = tennis_bear_class.return_value.__enter__.return_value
            tennis_bear.list_organized_events.return_value = [later_event]
            netaichi = netaichi_class.return_value.__enter__.return_value
            netaichi.get.reservation.return_value = pd.DataFrame()

            # 7/7 を再確認対象として渡す
            run(target_date=datetime(2026, 7, 7), is_recheck=True)

        # 2日後の予告通知は出ない
        warn_msgs = [
            c for c in notify.call_args_list
            if "明日キャンセル予定" in c.args[0]
        ]
        assert warn_msgs == []


class TestFormatHelpers:
    """format_*_message 単体のスモークテスト（import & 分岐確認）"""

    def test_cancel_failure_message_normal_header(self):
        slot = ReservationSlot_like()
        msg = format_cancel_failure_message([slot])
        assert "🚨" in msg
        assert "コート取消に失敗" in msg
        assert "手動で取り消してください" in msg

    def test_success_message_differs_between_normal_and_recheck(self):
        ev = _ev(6, 13, 0, lesson=True, practice=False)
        normal = format_message([ev])
        recheck = format_message([ev], is_recheck=True)

        assert "不要枠をキャンセルしました" in normal
        assert "再確認で回収" not in normal
        assert "再確認で回収" in recheck
        assert normal != recheck

    def test_cancel_failure_message_recheck_header(self):
        slot = ReservationSlot_like()
        msg = format_cancel_failure_message([slot], is_recheck=True)
        assert "🚨" in msg
        assert "前日の再確認" in msg

    def test_unmatched_reservation_message_marks_master_only(self):
        ev = _ev(6, 13, 0, lesson=True, practice=False)
        msg = format_unmatched_reservation_message([ev], single_account=True)
        assert "⚠️" in msg
        assert "マスターアカウントのみで判定" in msg

    def test_unmatched_court_message_recheck_header(self):
        ev = _ev(6, 13, 0, lesson=True, practice=False)
        msg = format_unmatched_court_message([ev], is_recheck=True)
        assert "⚠️" in msg
        assert "前日時点" in msg


# ---- 内部ヘルパ -----------------------------------------------------------

def ReservationSlot_like():  # noqa: N802
    from netaichi.services.cancel import ReservationSlot

    return ReservationSlot(
        date=datetime(2026, 7, 6),
        start=13,
        end=17,
        court_name=COURT_NAME,
        court_number="1",
        court_keyword=COURT_NAME,
        account_id=MASTER_ID,
    )
