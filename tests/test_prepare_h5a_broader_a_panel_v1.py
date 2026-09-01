import unittest
from pathlib import Path

import pandas as pd

from scripts.prepare_h5a_broader_a_panel_v1 import (
    code6,
    endpoint_date,
    ordinary_a_share,
    stable_groups,
)


class BroaderAH5APreparationTests(unittest.TestCase):
    def test_code_and_universe_rules_are_conservative(self):
        self.assertEqual(code6("63"), "000063")
        self.assertTrue(ordinary_a_share("600000", "SH"))
        self.assertTrue(ordinary_a_share("920001", "BJ"))
        self.assertFalse(ordinary_a_share("000300", "SH"))
        self.assertFalse(ordinary_a_share("123456", "SZ"))

    def test_stable_groups_are_reproducible_with_ties(self):
        frame = pd.DataFrame(
            {"stock_code": ["000003", "000001", "000002", "000004"], "value": [1.0, 1.0, 2.0, 3.0]}
        )
        first = stable_groups(frame, "value", 2)
        second = stable_groups(frame, "value", 2)
        self.assertTrue(first.equals(second))
        self.assertEqual(first.astype(int).value_counts().to_dict(), {1: 2, 2: 2})

    def test_endpoint_is_exact_market_session_and_never_filled(self):
        calendar = pd.DatetimeIndex(pd.to_datetime(["2026-01-02", "2026-01-05", "2026-01-06"]))
        self.assertEqual(
            endpoint_date(calendar, pd.Timestamp("2026-01-02"), 2), pd.Timestamp("2026-01-06")
        )
        self.assertTrue(pd.isna(endpoint_date(calendar, pd.Timestamp("2026-01-05"), 2)))
        self.assertTrue(pd.isna(endpoint_date(calendar, pd.Timestamp("2026-01-03"), 1)))

    def test_generated_panels_keep_signal_and_future_availability_separate(self):
        root = Path(__file__).resolve().parents[1]
        feature_path = root / "data/processed/h5a_broader_a_signal_features_v1.csv"
        availability_path = (
            root / "data/processed/h5a_broader_a_future_endpoint_availability_v1.csv"
        )
        if not feature_path.exists() or not availability_path.exists():
            self.skipTest("generated preparation artifacts not present")
        features = pd.read_csv(feature_path)
        availability = pd.read_csv(availability_path)
        self.assertFalse(features.duplicated(["period_index", "stock_code"]).any())
        self.assertFalse(availability.duplicated(["period_index", "stock_code"]).any())
        self.assertEqual(features["period_index"].nunique(), 57)
        self.assertFalse(
            any(
                "future" in column.lower() or "rankic" in column.lower()
                for column in features.columns
            )
        )
        self.assertFalse(any("return" in column.lower() for column in availability.columns))


if __name__ == "__main__":
    unittest.main()
