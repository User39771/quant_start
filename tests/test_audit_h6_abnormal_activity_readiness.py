import inspect
import unittest

import numpy as np
import pandas as pd

from scripts import audit_h6_abnormal_activity_readiness as h6


class H6AbnormalActivityReadinessTests(unittest.TestCase):
    def test_exact_50_dates_and_formation_day_are_required(self):
        dates = pd.date_range("2026-01-01", periods=51)
        values = pd.Series(np.arange(1, 52, dtype=float), index=dates)
        result = h6.own_history_rank(values, dates[:50])
        self.assertTrue(result["valid"])
        self.assertEqual(result["own_history_rank"], 50)
        self.assertEqual(result["shock_state"], "HIGH_SHOCK")
        self.assertFalse(h6.own_history_rank(values.drop(dates[10]), dates[:50])["valid"])
        self.assertFalse(h6.own_history_rank(values, dates[:49])["valid"])
        values.loc[dates[10]] = 0
        self.assertFalse(h6.own_history_rank(values, dates[:50])["valid"])

    def test_ties_use_date_as_deterministic_tie_breaker(self):
        dates = pd.date_range("2026-01-01", periods=50)
        values = pd.Series(1.0, index=dates)
        result = h6.own_history_rank(values, dates)
        self.assertEqual(result["own_history_rank"], 50)
        self.assertEqual(result["formation_tie_count"], 50)

    def test_counts_reuse_return_state_without_outcomes(self):
        states = pd.DataFrame(
            {
                "period_index": [1, 1],
                "stock_code": ["000001", "000002"],
                "RETURN_STATE": ["LOW_RETURN", "HIGH_RETURN"],
            }
        )
        observations = pd.DataFrame(
            {
                "period_index": [1, 1],
                "stock_code": ["000001", "000002"],
                "candidate": [h6.CANDIDATES[0]] * 2,
                "valid_50d": [True, True],
                "shock_state": ["LOW_SHOCK", "HIGH_SHOCK"],
            }
        )
        expanded_states = pd.concat(
            [states.assign(period_index=period) for period in range(1, 57)], ignore_index=True
        )
        expanded_observations = pd.concat(
            [observations.assign(period_index=period) for period in range(1, 57)],
            ignore_index=True,
        )
        counts = h6.build_counts(expanded_states, expanded_observations)
        cell = counts.loc[
            counts["row_type"].eq("period_3x3_cell")
            & counts["candidate"].eq(h6.CANDIDATES[0])
            & counts["period_index"].eq(1)
            & counts["return_state"].eq("LOW_RETURN")
            & counts["shock_state"].eq("LOW_SHOCK")
        ]
        self.assertEqual(int(cell["count"].iloc[0]), 1)

    def test_runner_does_not_read_outcome_or_network_sources(self):
        source = inspect.getsource(h6)
        self.assertNotIn("h5a_period_state_returns.csv", source)
        self.assertNotIn("future_endpoint_availability", source)
        self.assertNotIn("requests.", source)
        self.assertNotIn("akshare", source.lower())


if __name__ == "__main__":
    unittest.main()
