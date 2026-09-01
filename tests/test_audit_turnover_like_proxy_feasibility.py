import inspect
import unittest

import numpy as np
import pandas as pd

from scripts import audit_turnover_like_proxy_feasibility as audit


class TurnoverLikeProxyFeasibilityTests(unittest.TestCase):
    def test_code_normalization_and_unit_conversion(self):
        self.assertEqual(audit.code6("SZ_1"), "000001")
        ratio = audit.value_turnover(
            pd.Series([100.0]), pd.Series([2.0]), amount_multiplier=10_000
        )
        self.assertEqual(ratio.iloc[0], 500_000.0)

    def test_exact_window_rejects_missing_invalid_and_ignores_future(self):
        dates = pd.date_range("2026-01-01", periods=21, freq="D")
        frame = pd.DataFrame(
            {"amount": 10.0, "total_market_cap": 100.0}, index=dates
        )
        self.assertAlmostEqual(audit.exact_vt20(frame, dates[:20]), 0.1)
        self.assertTrue(np.isnan(audit.exact_vt20(frame.drop(dates[5]), dates[:20])))
        broken = frame.copy()
        broken.loc[dates[5], "total_market_cap"] = 0
        self.assertTrue(np.isnan(audit.exact_vt20(broken, dates[:20])))
        broken.loc[dates[5], "total_market_cap"] = np.inf
        self.assertTrue(np.isnan(audit.exact_vt20(broken, dates[:20])))
        frame.loc[dates[20], "amount"] = 1e30
        self.assertAlmostEqual(audit.exact_vt20(frame, dates[:20]), 0.1)

    def test_current_snapshot_cannot_be_mapped_back_to_history(self):
        dates = pd.date_range("2026-01-01", periods=20, freq="D")
        current_only = pd.DataFrame(
            {"amount": [10.0], "total_market_cap": [100.0]}, index=[dates[-1]]
        )
        self.assertTrue(np.isnan(audit.exact_vt20(current_only, dates)))

    def test_primary_periods_are_exactly_one_to_fifty_six(self):
        audit.validate_primary_periods(pd.Series(range(1, 57)))
        with self.assertRaisesRegex(ValueError, "primary_periods_not_1_to_56"):
            audit.validate_primary_periods(pd.Series(range(2, 57)))

    def test_proxy_groups_are_deterministic(self):
        frame = pd.DataFrame(
            {
                "period_index": [1] * 6,
                "stock_code": ["000006", "000005", "000004", "000003", "000002", "000001"],
                "vt20_daily": [0.3, 0.2, 0.2, 0.1, 0.1, 0.1],
                "log_total_market_cap": [6, 5, 4, 3, 2, 1],
            }
        )
        result = audit.assign_proxy_states(frame)
        ordered = result.sort_values(["vt20_daily", "stock_code"])
        self.assertEqual(
            ordered["proxy_state"].tolist(),
            ["LOW_PROXY", "LOW_PROXY", "MID_PROXY", "MID_PROXY", "HIGH_PROXY", "HIGH_PROXY"],
        )

    def test_source_does_not_read_future_outcome_artifacts(self):
        source = inspect.getsource(audit)
        self.assertNotIn("h5a_period_state_returns.csv", source)
        self.assertNotIn("future_endpoint_availability", source)
        self.assertNotIn("VT20_SIGNAL_APPROX", source)


if __name__ == "__main__":
    unittest.main()
