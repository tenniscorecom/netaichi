"""ネットあいちの予約取消の行照合テスト

実画面では4時間の予約も一覧に1行（13時～17時）で並ぶ（2026-07-26 確認）。
開始時ちょうどではなく範囲で照合しているので、その前提が崩れても拾える。
"""
from datetime import datetime
from unittest.mock import Mock, patch

import pytest
from selenium.common.exceptions import StaleElementReferenceException

from netaichi.browser.netaichi import NetAichi

TARGET = datetime(2026, 7, 6)
COURT_NAME = "愛・地球博記念公園"

FOUR_HOUR_ROW = "2026年07月06日 (月) 13時 ～ 17時 愛・地球博記念公園 庭球場1(人工芝)"
LATE_HALF_ROW = "2026年07月06日 (月) 15時 ～ 17時 愛・地球博記念公園 庭球場1(人工芝)"
MORNING_ROW = "2026年07月06日 (月) 9時 ～ 13時 愛・地球博記念公園 庭球場1(人工芝)"
OTHER_COURT_ROW = "2026年07月06日 (月) 13時 ～ 17時 大高緑地 庭球場7(人工芝)"


def _browser(rows: list[str], *, can_cancel: bool = True) -> NetAichi:
    """予約状況の一覧に rows が並んでいるブラウザを組み立てる"""
    browser = NetAichi.__new__(NetAichi)
    browser.logger = Mock()
    browser.go = Mock()
    browser.get_element_by_contains_text = Mock(return_value=Mock())
    browser.alert_switch = Mock()
    browser.js_exec = Mock()

    buttons = []
    for row in rows:
        tr = Mock()
        tr.text = row
        button = Mock()
        button.find_element = Mock(return_value=tr)
        buttons.append(button)

    def get_elements_by_css(selector):
        return buttons if selector == 'input[value="選択"]' else []

    browser.get_elements_by_css = Mock(side_effect=get_elements_by_css)
    browser.cancel_button = Mock() if can_cancel else None
    browser.get_element_by_css = Mock(return_value=browser.cancel_button)
    browser.clicked_buttons = buttons
    return browser


@pytest.fixture(autouse=True)
def _no_sleep():
    with patch("netaichi.browser.netaichi.time.sleep"):
        yield


class TestCancelReservation:
    def test_retries_stale_reservation_list_link(self):
        browser = _browser([FOUR_HOUR_ROW])
        stale_link = Mock()
        stale_link.click.side_effect = StaleElementReferenceException()
        fresh_link = Mock()
        browser.get_element_by_contains_text.side_effect = [stale_link, fresh_link]

        with patch("netaichi.browser.netaichi.time.sleep") as sleep:
            assert browser.cancel_reservation(TARGET, 13, 17, COURT_NAME, "1") is True
        assert browser.get_element_by_contains_text.call_count == 2
        fresh_link.click.assert_called_once()
        sleep.assert_any_call(0.5)

    def test_cancels_four_hour_row_by_its_start_hour(self):
        browser = _browser([FOUR_HOUR_ROW])

        assert browser.cancel_reservation(TARGET, 13, 17, COURT_NAME, "1") is True
        browser.cancel_button.click.assert_called_once()

    def test_cancels_row_that_starts_inside_the_range(self):
        # 一覧が15時始まりの行として並んでいても、13-17時の取消で拾える
        browser = _browser([LATE_HALF_ROW])

        assert browser.cancel_reservation(TARGET, 13, 17, COURT_NAME, "1") is True
        browser.cancel_button.click.assert_called_once()

    def test_ignores_reservation_outside_the_range(self):
        # 同じ日・同じ面の午前枠(9-13時)は13-17時の取消では触らない
        browser = _browser([MORNING_ROW])

        assert browser.cancel_reservation(TARGET, 13, 17, COURT_NAME, "1") is False
        assert browser.cancel_button.click.call_count == 0

    def test_picks_the_matching_court_only(self):
        browser = _browser([OTHER_COURT_ROW, FOUR_HOUR_ROW])

        assert browser.cancel_reservation(TARGET, 13, 17, COURT_NAME, "1") is True
        # 別コートの行の「選択」は押していない
        assert browser.clicked_buttons[0].click.call_count == 0
        assert browser.clicked_buttons[1].click.call_count == 1

    def test_ignores_other_court_number(self):
        browser = _browser([FOUR_HOUR_ROW])

        assert browser.cancel_reservation(TARGET, 13, 17, COURT_NAME, "2") is False

    def test_returns_false_when_cancel_button_is_missing(self):
        # 限界日超過などで取消ボタンが出ない場合
        browser = _browser([FOUR_HOUR_ROW], can_cancel=False)

        assert browser.cancel_reservation(TARGET, 13, 17, COURT_NAME, "1") is False
