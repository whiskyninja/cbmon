# 來源註記：這是 Codex 弄的。
# -*- coding: utf-8 -*-
import unittest
from datetime import date, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_cb_call_streaks as streaks


def market_days(close_values):
    start = date(2026, 6, 1)
    return [
        {
            "date": (start + timedelta(days=index)).isoformat(),
            "twse": {"1234": close} if close is not None else {},
            "tpex": {},
        }
        for index, close in enumerate(close_values)
    ]


class StreakTests(unittest.TestCase):
    def setUp(self):
        self.row = {
            "code": "12341",
            "conv_price": "100",
            "conv_price_eff_date": "2026/01/01",
        }

    def test_full_thirty_day_streak(self):
        record = streaks.build_record(self.row, market_days([130] * 30), [])
        self.assertEqual(record["current_streak"], 30)
        self.assertTrue(record["price_condition_met"])
        self.assertEqual(record["data_quality"], "complete")

    def test_latest_failure_resets_streak(self):
        record = streaks.build_record(self.row, market_days([130] * 29 + [129.9]), [])
        self.assertEqual(record["current_streak"], 0)
        self.assertFalse(record["price_condition_met"])

    def test_prior_thirty_day_run_keeps_exercise_window_visible(self):
        record = streaks.build_record(self.row, market_days([130] * 30 + [120] * 5), [])
        self.assertEqual(record["current_streak"], 0)
        self.assertTrue(record["redemption_window_active"])
        self.assertEqual(record["qualified_on"], "2026-06-30")

    def test_conversion_price_regime_uses_effective_date(self):
        snapshots = [
            (date(2026, 7, 1), {"12341": {"price": 110.0, "effective_date": "2026-01-01"}}),
            (date(2026, 7, 20), {"12341": {"price": 100.0, "effective_date": "2026-07-20"}}),
        ]
        old_price, _ = streaks.conversion_price_for_day(
            "12341", date(2026, 7, 19), 100.0, date(2026, 7, 20), snapshots
        )
        new_price, _ = streaks.conversion_price_for_day(
            "12341", date(2026, 7, 20), 100.0, date(2026, 7, 20), snapshots
        )
        self.assertEqual(old_price, 110.0)
        self.assertEqual(new_price, 100.0)

    def test_missing_pre_adjustment_price_is_incomplete(self):
        row = dict(self.row, conv_price_eff_date="2026/06/20")
        days = market_days([130] * 30)
        days[0]["date"] = "2026-06-19"
        record = streaks.build_record(row, days, [])
        self.assertEqual(record["data_quality"], "incomplete")
        self.assertFalse(record["price_condition_met"])

    def test_missing_close_is_incomplete(self):
        record = streaks.build_record(self.row, market_days([130] * 29 + [None]), [])
        self.assertEqual(record["data_quality"], "incomplete")
        self.assertEqual(record["current_streak"], 0)


if __name__ == "__main__":
    unittest.main()
