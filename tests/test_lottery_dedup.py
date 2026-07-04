"""filter_applied（申込済み除外）のテスト"""
from datetime import datetime

import pandas as pd

from netaichi.services.lottery import filter_applied


def _df(rows):
    return pd.DataFrame(rows, columns=["value", "date", "start", "end", "amount"])


class TestFilterApplied:
    def test_applied_slot_removed(self):
        df = _df([
            ["400", datetime(2026, 10, 5), 19, 21, 1],
            ["400", datetime(2026, 10, 6), 19, 21, 1],
        ])
        applied = [{"value": "400", "date": datetime(2026, 10, 5), "start": "19", "end": "21"}]
        result = filter_applied(df, applied)
        assert len(result) == 1
        assert result.iloc[0]["date"] == datetime(2026, 10, 6)

    def test_no_applied_keeps_all(self):
        df = _df([["400", datetime(2026, 10, 5), 19, 21, 1]])
        assert len(filter_applied(df, [])) == 1

    def test_different_court_not_removed(self):
        df = _df([["550", datetime(2026, 10, 5), 19, 21, 1]])
        applied = [{"value": "400", "date": datetime(2026, 10, 5), "start": "19"}]
        assert len(filter_applied(df, applied)) == 1

    def test_different_start_not_removed(self):
        df = _df([["400", datetime(2026, 10, 5), 9, 13, 1]])
        applied = [{"value": "400", "date": datetime(2026, 10, 5), "start": "13"}]
        assert len(filter_applied(df, applied)) == 1
