from __future__ import annotations

import inspect
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import run_h7_dynamic_volume_return_v1 as h7


class H7ContractTests(unittest.TestCase):
    def test_preregistration_is_checked_before_any_fit(self) -> None:
        source = inspect.getsource(h7.run)
        self.assertLess(source.index("prereg.exists()"), source.index("fit_stock("))
        prereg = Path(
            "reports/hypothesis_7/h7_dynamic_volume_return_preregistration_v1.md"
        ).read_text(encoding="utf-8")
        self.assertIn("PRIMARY_750_ROLE_FIXED_BEFORE_C2=true", prereg)

    def test_frozen_constants(self) -> None:
        self.assertEqual(h7.ANALYSIS_CUTOFF, pd.Timestamp("2026-05-11"))
        self.assertEqual(h7.PRIMARY_MIN_ROWS, 750)
        self.assertEqual(h7.LONG_HISTORY_MIN_ROWS, 1000)
        self.assertEqual(h7.HAC_MAXLAGS, 5)

    def test_baseline_is_prior_active_only_and_no_epsilon(self) -> None:
        turnover = pd.Series(np.exp(np.arange(204, dtype=float) / 100.0))
        active = pd.Series(True, index=turnover.index)
        active.iloc[50] = False
        logs, baseline = h7.previous_active_log_baseline(turnover, active)
        valid_positions = np.flatnonzero(active)
        current_position = valid_positions[200]
        expected = logs.iloc[valid_positions[:200]].mean()
        self.assertAlmostEqual(baseline.iloc[current_position], expected)
        self.assertFalse(current_position in valid_positions[:200])
        self.assertTrue(np.isnan(logs.iloc[50]))

    def test_suspended_rows_not_zero_and_st_only_excludes_formation(self) -> None:
        calendar = pd.bdate_range("2024-01-01", periods=210)
        group = pd.DataFrame({
            "stock_code": "000001", "trade_date": calendar,
            "trading_status": 1, "is_st": 0, "total_share_turnover": 0.01,
            "baostock_circulating_turnover": 0.02,
        })
        group.loc[3, "trading_status"] = 0
        group.loc[205, "is_st"] = 1
        prices = pd.Series(np.linspace(10, 12, len(calendar)), index=calendar)
        rows = h7.prepare_stock_rows(group, prices, calendar)
        self.assertTrue(np.isnan(rows.iloc[3].primary_v))
        self.assertFalse(rows.iloc[205].formation_base)
        self.assertTrue(np.isfinite(rows.iloc[206].primary_v))

    def test_exact_market_date_returns_and_no_fill(self) -> None:
        prices = pd.Series([10.0, 11.0, np.nan, 13.0, 14.0, 15.0])
        result = h7.exact_returns(prices)
        self.assertAlmostEqual(result.loc[1, "current_return"], 0.1)
        self.assertTrue(np.isnan(result.loc[2, "current_return"]))
        self.assertTrue(np.isnan(result.loc[3, "current_return"]))
        self.assertAlmostEqual(result.loc[0, "future_5d_return"], 0.5)
        self.assertTrue(np.isnan(result.loc[0, "future_2d_return"]))

    def test_regression_equation_and_c2(self) -> None:
        rng = np.random.default_rng(7)
        n = 900
        current = rng.normal(0, 0.02, n)
        v = rng.normal(0, 0.5, n)
        future = 0.001 - 0.2 * current + 0.7 * v * current
        rows = pd.DataFrame({"current_return": current, "primary_v": v, "future_1d_return": future})
        fit = h7.fit_stock(rows, "primary_v", "future_1d_return")
        self.assertEqual(fit["evaluation_status"], "SUCCESS")
        self.assertAlmostEqual(fit["C0"], 0.001, places=10)
        self.assertAlmostEqual(fit["C1"], -0.2, places=10)
        self.assertAlmostEqual(fit["C2"], 0.7, places=10)
        self.assertAlmostEqual(fit["effective_slope_p50"], -0.2 + 0.7 * fit["V_p50"])

    def test_singular_regression_fails_without_repair(self) -> None:
        rows = pd.DataFrame({
            "current_return": [0.1] * 800,
            "primary_v": np.arange(800),
            "future_1d_return": 0.0,
        })
        fit = h7.fit_stock(rows, "primary_v", "future_1d_return")
        self.assertEqual(fit["evaluation_status"], "REGRESSION_NUMERIC_FAILURE")

    def test_exact_matched_contract(self) -> None:
        frame = pd.DataFrame({
            "primary_valid_1d": [True, True, False, True],
            "secondary_v": [0.1, np.nan, 0.2, 0.3],
            "future_1d_return": [0.01, 0.02, 0.03, np.nan],
        })
        matched = (
            frame.primary_valid_1d
            & np.isfinite(frame.secondary_v)
            & np.isfinite(frame.future_1d_return)
        )
        self.assertEqual(matched.tolist(), [True, False, False, False])

    def test_size_uses_only_valid_dates_and_cutoff(self) -> None:
        # The helper is tested through a small temporary project-shaped directory.
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / h7.RAW_PRICE_DIR
            path.mkdir(parents=True)
            pd.DataFrame({
                "date": ["2026-05-08", "2026-05-11", "2026-05-12"],
                "total_market_cap": [100.0, 400.0, 1e12],
            }).to_csv(path / "000001.csv", index=False)
            dates = pd.DatetimeIndex(["2026-05-08", "2026-05-11", "2026-05-12"])
            value, count = h7.historical_size(root, "000001", dates)
            self.assertEqual(count, 2)
            self.assertAlmostEqual(value, np.median(np.log([100.0, 400.0])))

    def test_nested_threshold_roles(self) -> None:
        counts = pd.Series([749, 750, 999, 1000])
        primary = counts.ge(h7.PRIMARY_MIN_ROWS)
        long_history = counts.ge(h7.LONG_HISTORY_MIN_ROWS)
        self.assertEqual(primary.tolist(), [False, True, True, True])
        self.assertEqual(long_history.tolist(), [False, False, False, True])
        self.assertTrue((~long_history | primary).all())

    def test_no_forbidden_research_features(self) -> None:
        source = Path(h7.__file__).read_text(encoding="utf-8").lower()
        forbidden_terms = (
            "sharpe", "calmar", "long_short", "mcts_sandbox", "phase_b_rev60", "winsorize("
        )
        for forbidden in forbidden_terms:
            self.assertNotIn(forbidden, source)
        self.assertNotIn("limit_status =", source)


if __name__ == "__main__":
    unittest.main()
