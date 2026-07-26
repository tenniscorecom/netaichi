"""ネットあいちの部分予約取り直しロジックのテスト"""
from datetime import datetime
from unittest.mock import Mock

from bs4 import BeautifulSoup

from netaichi.browser.netaichi import NetAichi


TARGET = datetime(2026, 7, 6)


def _browser_with_html(html: str) -> NetAichi:
    browser = NetAichi.__new__(NetAichi)
    browser.get_html = Mock(return_value=BeautifulSoup(html, "lxml"))
    browser.js_exec = Mock()
    return browser


class TestFindAvailableSlotIds:
    def test_returns_contiguous_available_slots_for_same_court(self):
        browser = _browser_with_html(
            """
            <label><input name="chkIcd" value="court-1">庭球場１（人工芝）</label>
            <div>
              <img alt="空き">
              <input name="selectInfo" id="slot-13"
                     value="1090:court-1:20260706:x:1300:1400:x">
            </div>
            <div>
              <img alt="空き">
              <input name="selectInfo" id="slot-14"
                     value="1090:court-1:20260706:x:1400:1500:x">
            </div>
            <div>
              <img alt="空き">
              <input name="selectInfo" id="slot-15"
                     value="1090:court-1:20260706:x:1500:1600:x">
            </div>
            """
        )

        result = browser._NetAichi__find_available_slot_ids(
            TARGET,
            13,
            15,
            "庭球場1",
        )

        assert result == ["slot-13", "slot-14"]

    def test_returns_empty_when_one_hour_is_not_available(self):
        browser = _browser_with_html(
            """
            <label><input name="chkIcd" value="court-1">庭球場１（人工芝）</label>
            <div>
              <img alt="空き">
              <input name="selectInfo" id="slot-13"
                     value="1090:court-1:20260706:x:1300:1400:x">
            </div>
            <div>
              <img alt="予約">
              <input name="selectInfo" id="slot-14"
                     value="1090:court-1:20260706:x:1400:1500:x" disabled>
            </div>
            """
        )

        result = browser._NetAichi__find_available_slot_ids(
            TARGET,
            13,
            15,
            "庭球場1",
        )

        assert result == []
