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
        patch("netaichi.services.cancel.run", side_effect=lambda **_: order.append("cancel") or ([], [])),
        patch("netaichi.services.shrink.run", side_effect=lambda **_: order.append("shrink") or []),
        patch(
            "netaichi.services.eaichi_notice.run",
            side_effect=lambda **_: order.append("eaichi_notice") or [],
        ),
    ):
        _run_daily(headless=False)

    assert order == ["prune", "cancel", "shrink", "eaichi_notice"]


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
