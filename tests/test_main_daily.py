"""daily コマンドのフェーズ継続とエラー通知のテスト。"""
from unittest.mock import Mock, patch

import pytest

from netaichi.__main__ import _run_daily, _safe_exception_message


def test_daily_notifies_failure_continues_and_raises_at_end():
    prune_run = Mock(side_effect=RuntimeError("画面エラー"))
    cancel_run = Mock(return_value=([{"id": "1"}], []))
    notice_run = Mock(return_value=[])

    with (
        patch("netaichi.services.prune.run", prune_run),
        patch("netaichi.services.cancel.run", cancel_run),
        patch("netaichi.services.shrink.run", return_value=[]),
        patch("netaichi.services.eaichi_notice.run", notice_run),
        patch("netaichi.notify.notify") as notify,
        pytest.raises(RuntimeError, match="prune"),
    ):
        _run_daily(headless=True)

    cancel_run.assert_not_called()
    notice_run.assert_called_once_with(headless=True)
    messages = [call_args.args[0] for call_args in notify.call_args_list]
    assert any("画面エラー" in message for message in messages)
    assert any("cancel を安全側でスキップ" in message for message in messages)


def test_daily_runs_phases_in_required_order():
    order = []

    with (
        patch("netaichi.services.prune.run", side_effect=lambda **_: order.append("prune") or []),
        patch(
            "netaichi.services.cancel.run",
            side_effect=lambda **_: order.append("cancel") or ([], []),
        ),
        patch(
            "netaichi.services.cancel.load_rules",
            return_value={"days_before": 2},
        ),
        patch(
            "netaichi.services.shrink.run",
            side_effect=lambda **_: order.append("shrink") or [],
        ),
        patch(
            "netaichi.services.eaichi_notice.run",
            side_effect=lambda **_: order.append("eaichi_notice") or [],
        ),
    ):
        _run_daily(headless=False)

    # 通常cancel → cancel再確認 → shrink → 窓口取消 の順
    assert order == [
        "prune",
        "cancel",
        "cancel",
        "shrink",
        "eaichi_notice",
    ]


def test_daily_runs_notice_after_cancel_failure_and_raises_at_end():
    notice_run = Mock(return_value=[])

    shrink_run = Mock(return_value=[])

    with (
        patch("netaichi.services.prune.run", return_value=[]),
        patch("netaichi.services.cancel.run", side_effect=RuntimeError("取消エラー")),
        patch("netaichi.services.shrink.run", shrink_run),
        patch("netaichi.services.eaichi_notice.run", notice_run),
        patch("netaichi.notify.notify"),
        pytest.raises(RuntimeError, match="cancel"),
    ):
        _run_daily(headless=True)

    # cancelが落ちてもshrinkは動く（面を多めに残す側へ倒れるので安全）
    shrink_run.assert_called_once_with(headless=True)
    notice_run.assert_called_once_with(headless=True)


def test_safe_exception_message_redacts_credentials_and_url_query():
    error = RuntimeError(
        "password=secret token:abc https://example.test/path?api_key=secret"
    )

    message = _safe_exception_message(error)

    assert "secret" not in message
    assert message == (
        "password=[REDACTED] token:[REDACTED] "
        "https://example.test/path?[REDACTED]"
    )


def test_daily_invokes_cancel_twice_for_recheck_pass():
    """_run_daily は cancel.run を通常パスと再確認パスで2回呼ぶ"""
    cancel_calls = []

    def fake_cancel(**kwargs):
        cancel_calls.append(kwargs)
        return [], []

    with (
        patch("netaichi.services.prune.run", return_value=[]),
        patch("netaichi.services.cancel.run", side_effect=fake_cancel),
        patch("netaichi.services.cancel.load_rules", return_value={"days_before": 2}),
        patch("netaichi.services.shrink.run", return_value=[]),
        patch("netaichi.services.eaichi_notice.run", return_value=[]),
    ):
        _run_daily(headless=True)

    assert len(cancel_calls) == 2
    # 1回目: 通常のcancel（is_recheck フラグ無し、target_date 未指定）
    assert cancel_calls[0].get("is_recheck", False) is False
    assert cancel_calls[0].get("target_date") is None
    # 2回目: 再確認パス。target_date は今日+1日（days_before=2 → 1日前）
    from datetime import datetime, timedelta

    expected = datetime.today().replace(
        hour=0, minute=0, second=0, microsecond=0
    ) + timedelta(days=1)
    assert cancel_calls[1]["is_recheck"] is True
    assert cancel_calls[1]["target_date"] == expected
    assert cancel_calls[1]["headless"] is True
    assert cancel_calls[1]["execute"] is True


def test_daily_skips_recheck_when_prune_fails():
    """pruneが落ちたときは cancel 自体を安全側スキップし、再確認も走らない"""
    cancel_calls = []

    def fake_cancel(**kwargs):
        cancel_calls.append(kwargs)
        return [], []

    with (
        patch("netaichi.services.prune.run", side_effect=RuntimeError("prune失敗")),
        patch("netaichi.services.cancel.run", side_effect=fake_cancel),
        patch("netaichi.services.shrink.run", return_value=[]),
        patch("netaichi.services.eaichi_notice.run", return_value=[]),
        patch("netaichi.notify.notify"),
        pytest.raises(RuntimeError, match="prune"),
    ):
        _run_daily(headless=True)

    assert cancel_calls == []


def test_daily_continues_after_recheck_failure_and_reports_phase():
    """再確認だけが落ちても後続フェーズを実行し、再確認名で失敗終了する"""
    cancel_run = Mock(side_effect=[([], []), RuntimeError("再確認エラー")])
    shrink_run = Mock(return_value=[])
    notice_run = Mock(return_value=[])

    with (
        patch("netaichi.services.prune.run", return_value=[]),
        patch("netaichi.services.cancel.run", cancel_run),
        patch("netaichi.services.cancel.load_rules", return_value={"days_before": 2}),
        patch("netaichi.services.shrink.run", shrink_run),
        patch("netaichi.services.eaichi_notice.run", notice_run),
        patch("netaichi.notify.notify") as notify,
        pytest.raises(RuntimeError, match="cancel-recheck"),
    ):
        _run_daily(headless=True)

    shrink_run.assert_called_once_with(headless=True)
    notice_run.assert_called_once_with(headless=True)
    messages = [called.args[0] for called in notify.call_args_list]
    assert any("cancel-recheck フェーズ" in message for message in messages)
