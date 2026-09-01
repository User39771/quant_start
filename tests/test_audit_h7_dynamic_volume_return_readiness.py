from __future__ import annotations

import inspect
import unittest

import numpy as np
import pandas as pd

from scripts import audit_h7_dynamic_volume_return_readiness as h7


class H7ReadinessAuditTests(unittest.TestCase):
    def test_exact_prior_200_excludes_current_from_baseline(self) -> None:
        values = pd.Series(np.arange(202, dtype=float) + 1)
        valid = h7.exact_prior_200_valid(values)
        self.assertFalse(valid.iloc[199])
        self.assertTrue(valid.iloc[200])

    def test_current_value_is_still_required(self) -> None:
        values = pd.Series(np.ones(201))
        values.iloc[200] = np.nan
        self.assertFalse(h7.exact_prior_200_valid(values).iloc[200])

    def test_missing_prior_day_is_not_filled_or_substituted(self) -> None:
        values = pd.Series(np.ones(202))
        values.iloc[17] = np.nan
        self.assertFalse(h7.exact_prior_200_valid(values).iloc[200])
        self.assertFalse(h7.exact_prior_200_valid(values).iloc[201])

    def test_future_value_does_not_change_signal_validity(self) -> None:
        values = pd.Series(np.ones(202))
        before = h7.exact_prior_200_valid(values).iloc[200]
        values.iloc[201] = np.nan
        after = h7.exact_prior_200_valid(values).iloc[200]
        self.assertEqual(before, after)

    def test_endpoint_check_is_presence_only(self) -> None:
        valid = pd.Series([False, True, True, True, True])
        prices = pd.Series([10.0, 11.0, 12.0, 13.0, 14.0])
        result = h7.potential_endpoint_valid(valid, prices, 2)
        self.assertTrue(result.iloc[1])
        prices.iloc[3] = np.nan
        self.assertFalse(h7.potential_endpoint_valid(valid, prices, 2).iloc[1])

    def test_discontinuity_count(self) -> None:
        self.assertEqual(h7.discontinuities(pd.Series([100.0, 100.0, 130.0, 130.0])), 1)

    def test_threshold_summary_never_promotes_unresolved_turnover(self) -> None:
        history = pd.DataFrame({
            "row_type": ["stock"] * 4,
            "stock_code": ["1", "2", "3", "4"],
            "potential_1d_rows_upper_bound": [400, 600, 800, 1300],
            "local_history_days": [600, 800, 1000, 1500],
            "latest_total_market_cap": [1e9, 2e9, 3e9, 4e9],
            "log_size": np.log([1e9, 2e9, 3e9, 4e9]),
            "size_quartile": ["Q1_SMALL", "Q2", "Q3", "Q4_LARGE"],
        })
        summary, _, _, _ = h7.threshold_rows(history)
        self.assertTrue(summary.exact_candidate_stock_count.eq(0).all())
        count = summary.loc[summary.threshold.eq(500), "upper_bound_stock_count"].iloc[0]
        self.assertEqual(count, 3)

    def test_identity_forbids_research_runs_and_data_roles(self) -> None:
        forbidden_runs = (
            "C2_estimated", "volume_return_regression_run",
            "future_performance_used_for_design", "H5_run", "H6_run", "MCTS_run",
            "Phase_B_run", "prospective_data_accessed", "final_test_accessed",
        )
        for key in forbidden_runs:
            self.assertIs(h7.IDENTITY[key], False)

    def test_runner_has_no_network_or_regression_client(self) -> None:
        source = inspect.getsource(h7)
        forbidden_clients = (
            "import requests", "import akshare", "statsmodels", "sklearn", "lstsq(", ".fit(",
        )
        for forbidden in forbidden_clients:
            self.assertNotIn(forbidden, source.lower())

    def test_probe_set_is_fixed_and_unique(self) -> None:
        self.assertEqual(len(h7.PROBE_CODES), 25)
        self.assertEqual(len(set(h7.PROBE_CODES)), 25)


if __name__ == "__main__":
    unittest.main()
