import inspect
import unittest

import numpy as np
import pandas as pd

from scripts import audit_turnover_like_proxy_feasibility as audit
from scripts import build_h5b_vt20_signal as build


class H5BVT20SignalTests(unittest.TestCase):
    def test_exact_twenty_day_contract(self):
        dates = pd.date_range("2026-01-01", periods=21)
        frame = pd.DataFrame(
            {"amount": 10.0, "total_market_cap": 100.0}, index=dates
        )
        self.assertAlmostEqual(audit.exact_vt20(frame, dates[:20]), 0.1)
        self.assertTrue(np.isnan(audit.exact_vt20(frame.drop(dates[0]), dates[:20])))
        frame.loc[dates[0], "amount"] = 0
        self.assertTrue(np.isnan(audit.exact_vt20(frame, dates[:20])))
        frame.loc[dates[0], ["amount", "total_market_cap"]] = [10.0, np.inf]
        self.assertTrue(np.isnan(audit.exact_vt20(frame, dates[:20])))
        frame.loc[dates[-1], ["amount", "total_market_cap"]] = [1e30, 1.0]
        self.assertTrue(np.isnan(audit.exact_vt20(frame, dates[:20])))

    def test_vt_states_are_deterministic_and_near_equal(self):
        frame = pd.DataFrame(
            {
                "period_index": [1] * 6,
                "stock_code": ["000006", "000005", "000004", "000003", "000002", "000001"],
                "VT20_DAILY": [0.3, 0.2, 0.2, 0.1, 0.1, 0.1],
                "signal_ready": True,
                "vt20_valid": True,
            }
        )
        result = build.assign_vt20_states(frame).sort_values(["VT20_DAILY", "stock_code"])
        self.assertEqual(
            result["VT20_STATE"].tolist(),
            ["LOW_VT", "LOW_VT", "MID_VT", "MID_VT", "HIGH_VT", "HIGH_VT"],
        )

    def test_h5a_membership_and_return_state_must_match(self):
        formal = pd.DataFrame(
            {"period_index": [1], "stock_code": ["000001"], "return_state": ["LOW_RETURN"]}
        )
        build.validate_reused_return_states(formal, formal.copy())
        changed = formal.assign(return_state="HIGH_RETURN")
        with self.assertRaisesRegex(ValueError, "h5a_membership_or_return_state_mismatch"):
            build.validate_reused_return_states(formal, changed)

    def test_primary_periods_and_signal_only_schema(self):
        audit.validate_primary_periods(pd.Series(range(1, 57)))
        build.assert_signal_time_columns(
            ["period_index", "RETURN60", "RETURN_STATE", "VT20_DAILY", "VOL20"]
        )
        with self.assertRaisesRegex(ValueError, "outcome_columns_forbidden"):
            build.assert_signal_time_columns(["future_return_20d"])

    def test_runner_does_not_read_outcome_artifacts(self):
        source = inspect.getsource(build)
        self.assertNotIn("h5a_period_state_returns.csv", source)
        self.assertNotIn("future_endpoint_availability", source)
        self.assertNotIn("VT20_SIGNAL_APPROX", source)


if __name__ == "__main__":
    unittest.main()
