import unittest

import numpy as np
import pandas as pd

from scripts.audit_h5a_activity_main_effect import (
    _interpretation,
    board_from_code,
    exact_vol20,
    standardized_difference,
)


class H5AActivityMainEffectAuditTests(unittest.TestCase):
    def test_board_mapping(self):
        self.assertEqual(board_from_code("600000"), "SH_MAIN")
        self.assertEqual(board_from_code("000001"), "SZ_MAIN")
        self.assertEqual(board_from_code("300001"), "CHINEXT")
        self.assertEqual(board_from_code("688001"), "STAR")

    def test_vol20_reuses_exact_window_and_rejects_missing(self):
        dates = pd.date_range("2026-01-01", periods=21, freq="D")
        prices = pd.Series(np.linspace(10, 12, 21), index=dates)
        expected = float(prices.pct_change(fill_method=None).dropna().std(ddof=1) * np.sqrt(252))
        self.assertAlmostEqual(exact_vol20(prices, dates), expected)
        self.assertTrue(np.isnan(exact_vol20(prices.drop(dates[5]), dates)))

    def test_standardized_difference(self):
        high = pd.Series([3.0, 4.0, 5.0])
        low = pd.Series([1.0, 2.0, 3.0])
        self.assertAlmostEqual(standardized_difference(high, low), 2.0)

    def test_interpretation_is_not_a_hypothesis_gate(self):
        correlations = pd.DataFrame(
            {
                "scope": ["ALL", "ALL", "ALL"],
                "covariate": ["log_total_market_cap", "log_raw_signal_price", "vol20"],
                "mean_spearman": [0.65, 0.35, 0.10],
            }
        )
        inventory = pd.DataFrame(
            {"covariate": ["total_market_cap"], "coverage": [0.95]}
        )
        self.assertEqual(
            _interpretation(correlations, inventory), "ACTIVITY_MULTI_FACTOR_PROXY"
        )


if __name__ == "__main__":
    unittest.main()
