"""イベント終了時刻補完のテスト。"""
from unittest.mock import Mock

from netaichi.services.event_times import fill_event_ends


def _event(start: int = 13) -> dict:
    return {"id": "123", "start": start}


class TestFillEventEnds:
    def test_uses_time_range_from_edit_page(self):
        tb = Mock()
        tb.get_event_time_range.return_value = (13, 17)
        event = _event()

        fill_event_ends(tb, [event], 2)

        assert event["end"] == 17

    def test_falls_back_when_time_range_is_missing(self):
        tb = Mock()
        tb.get_event_time_range.return_value = None
        event = _event()

        fill_event_ends(tb, [event], 2)

        assert event["end"] == 15

    def test_falls_back_when_edit_page_start_does_not_match(self):
        tb = Mock()
        tb.get_event_time_range.return_value = (15, 17)
        event = _event()

        fill_event_ends(tb, [event], 2)

        assert event["end"] == 15
        tb.logger.warning.assert_called_once()

    def test_existing_end_is_not_fetched_again(self):
        tb = Mock()
        event = {**_event(), "end": 17}

        fill_event_ends(tb, [event], 2)

        tb.get_event_time_range.assert_not_called()
