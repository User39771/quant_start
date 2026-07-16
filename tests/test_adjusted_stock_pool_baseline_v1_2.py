from __future__ import annotations

import importlib.util
import math
import sys
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_adjusted_stock_pool_baseline_v1_2.py"
SPEC = importlib.util.spec_from_file_location("run_adjusted_stock_pool_baseline_v1_2", MODULE_PATH)
baseline = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = baseline
SPEC.loader.exec_module(baseline)


def panel_row(
    code: str,
    date: str,
    adjusted_close: object,
    *,
    adjusted_flag: object = "true",
    qfq_close: object | None = None,
    close: object = 999,
) -> dict[str, object]:
    return {
        "stock_code": code,
        "trade_date": date,
        "close": close,
        "qfq_close": adjusted_close if qfq_close is None else qfq_close,
        "adjusted_close": adjusted_close,
        "adjusted_flag": adjusted_flag,
    }


def full_boundary(start: str, end: str) -> object:
    return baseline.Boundary(pd.Timestamp(start), pd.Timestamp(end), 20, "full")


class AdjustedStockPoolBaselineV12Tests(unittest.TestCase):
    def test_code6_and_multitheme_universe_deduplication(self):
        universe = pd.DataFrame({"code": ["63", "000063", "002049"], "theme": ["AI", "space", "AI"]})
        self.assertEqual(baseline.normalize_universe(universe), ["000063", "002049"])

    def test_duplicate_stock_date_fails_fast(self):
        frame = pd.DataFrame(
            [
                panel_row("000063", "2025-01-01", 10),
                panel_row("000063", "2025-01-01", 11),
            ]
        )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            baseline.prepare_price_panel(frame)

    def test_invalid_date_and_adjusted_qfq_mismatch_fail_fast(self):
        with self.assertRaisesRegex(ValueError, "invalid trade_date"):
            baseline.prepare_price_panel(pd.DataFrame([panel_row("000063", "not-a-date", 10)]))
        with self.assertRaisesRegex(ValueError, "positive equal"):
            baseline.prepare_price_panel(
                pd.DataFrame([panel_row("000063", "2025-01-01", 10, qfq_close=11)])
            )

    def test_unadjusted_row_is_not_replaced_with_raw_close(self):
        frame = pd.DataFrame(
            [panel_row("000063", "2025-01-01", "", adjusted_flag="false", qfq_close="", close=10)]
        )
        prepared = baseline.prepare_price_panel(frame)
        self.assertTrue(prepared.empty)

    def test_eligibility_uses_start_date_only(self):
        prepared = baseline.prepare_price_panel(
            pd.DataFrame(
                [
                    panel_row("000001", "2025-01-01", 10),
                    panel_row("000002", "2025-01-01", 20),
                    panel_row("000001", "2025-01-29", 11),
                    panel_row("000003", "2025-01-29", 30),
                ]
            )
        )
        observation = baseline.evaluate_period(
            ["000001", "000002", "000003"],
            baseline.make_price_index(prepared),
            full_boundary("2025-01-01", "2025-01-29"),
        )
        self.assertEqual(observation["eligible_codes"], "000001;000002")
        self.assertEqual(observation["eligible_count"], 2)
        self.assertNotIn("000003", observation["eligible_codes"])
        self.assertIn("000002", observation["end_price_missing_codes"])
        self.assertFalse(observation["period_valid"])
        self.assertTrue(math.isnan(observation["gross_return"]))

    def test_baseline_starts_at_first_three_consecutive_valid_full_periods(self):
        observations = [
            {"period_type": "full", "coverage_pass": False, "period_valid": False},
            {"period_type": "full", "coverage_pass": True, "period_valid": True},
            {"period_type": "full", "coverage_pass": True, "period_valid": True},
            {"period_type": "full", "coverage_pass": True, "period_valid": True},
        ]
        self.assertEqual(baseline.find_baseline_start(observations), 1)

    def test_invalid_period_after_start_terminates_nav_chain(self):
        dates = pd.date_range("2025-01-01", periods=6, freq="28D")
        rows: list[dict[str, object]] = []
        for i, date in enumerate(dates):
            for number in range(1, 6):
                if i == 4 and number == 5:
                    continue
                rows.append(panel_row(f"{number:06d}", date.strftime("%Y-%m-%d"), 10 * number + i))
        prices = baseline.make_price_index(baseline.prepare_price_panel(pd.DataFrame(rows)))
        boundaries = [baseline.Boundary(dates[i], dates[i + 1], 20, "full") for i in range(5)]
        universe = [f"{number:06d}" for number in range(1, 6)]
        periods = baseline.run_scenario(universe, prices, boundaries, "research", 0.0)
        self.assertEqual(periods.loc[3, "period_phase"], "termination_period")
        self.assertEqual(periods.loc[4, "period_phase"], "post_termination_diagnostic")
        self.assertTrue(periods.loc[4, "period_valid"])
        self.assertTrue(pd.isna(periods.loc[3, "nav"]))
        self.assertTrue(pd.isna(periods.loc[4, "nav"]))

    def test_partial_period_is_provisional_and_excluded_from_headline_metrics(self):
        dates = pd.date_range("2025-01-01", periods=5, freq="28D")
        rows = [panel_row("000001", date.strftime("%Y-%m-%d"), 10 * (1.1**i)) for i, date in enumerate(dates)]
        prices = baseline.make_price_index(baseline.prepare_price_panel(pd.DataFrame(rows)))
        boundaries = [baseline.Boundary(dates[i], dates[i + 1], 20, "full") for i in range(3)]
        boundaries.append(baseline.Boundary(dates[3], dates[4], 5, "partial"))
        periods = baseline.run_scenario(["000001"], prices, boundaries, "research", 0.0)
        metrics = baseline.portfolio_metrics(periods)
        self.assertTrue(periods.loc[3, "provisional"])
        self.assertFalse(periods.loc[3, "headline_included"])
        self.assertAlmostEqual(metrics["cumulative_return"], 1.1**3 - 1)
        self.assertAlmostEqual(metrics["latest_partial_period_return"], 0.1)

    def test_invalid_partial_is_still_marked_provisional_without_return(self):
        dates = pd.date_range("2025-01-01", periods=5, freq="28D")
        rows: list[dict[str, object]] = []
        for i, date in enumerate(dates):
            rows.append(panel_row("000001", date.strftime("%Y-%m-%d"), 10 + i))
            if i != 4:
                rows.append(panel_row("000002", date.strftime("%Y-%m-%d"), 20 + i))
        prices = baseline.make_price_index(baseline.prepare_price_panel(pd.DataFrame(rows)))
        boundaries = [baseline.Boundary(dates[i], dates[i + 1], 20, "full") for i in range(3)]
        boundaries.append(baseline.Boundary(dates[3], dates[4], 5, "partial"))
        periods = baseline.run_scenario(["000001", "000002"], prices, boundaries, "research", 0.0)
        self.assertEqual(periods.loc[3, "period_phase"], "invalid_partial")
        self.assertTrue(periods.loc[3, "provisional"])
        self.assertTrue(pd.isna(periods.loc[3, "net_return"]))

    def test_drifted_weight_turnover_uses_previous_period_returns(self):
        previous = {"000001": 0.5, "000002": 0.5}
        previous_returns = {"000001": 0.2, "000002": 0.0}
        drifted = baseline.drifted_weights(previous, previous_returns)
        target = {"000001": 0.5, "000002": 0.5}
        self.assertAlmostEqual(drifted["000001"], 0.6 / 1.1)
        self.assertAlmostEqual(baseline.turnover_from_drift(target, drifted), 0.04545454545454547)

    def test_scenario_turnover_uses_previous_not_current_period_returns(self):
        dates = pd.date_range("2025-01-01", periods=4, freq="28D")
        prices_by_code = {
            "000001": [10, 12, 12, 12],
            "000002": [10, 10, 15, 15],
        }
        rows = [
            panel_row(code, date.strftime("%Y-%m-%d"), values[index])
            for code, values in prices_by_code.items()
            for index, date in enumerate(dates)
        ]
        prices = baseline.make_price_index(baseline.prepare_price_panel(pd.DataFrame(rows)))
        boundaries = [baseline.Boundary(dates[i], dates[i + 1], 20, "full") for i in range(3)]
        periods = baseline.run_scenario(sorted(prices_by_code), prices, boundaries, "research", 0.0)
        self.assertAlmostEqual(periods.loc[1, "turnover"], 0.04545454545454547)

    def test_cost_and_nav_are_compounded(self):
        dates = pd.date_range("2025-01-01", periods=4, freq="28D")
        rows = [panel_row("000001", date.strftime("%Y-%m-%d"), 10 * (1.1**i)) for i, date in enumerate(dates)]
        prices = baseline.make_price_index(baseline.prepare_price_panel(pd.DataFrame(rows)))
        boundaries = [baseline.Boundary(dates[i], dates[i + 1], 20, "full") for i in range(3)]
        periods = baseline.run_scenario(["000001"], prices, boundaries, "research", 0.001)
        self.assertAlmostEqual(periods.loc[0, "turnover"], 1.0)
        self.assertAlmostEqual(periods.loc[0, "net_return"], 0.099)
        self.assertAlmostEqual(periods.loc[2, "nav"], 1.099 * 1.1 * 1.1)

    def test_extreme_return_is_flagged_but_included(self):
        prepared = baseline.prepare_price_panel(
            pd.DataFrame(
                [
                    panel_row("000001", "2025-01-01", 10),
                    panel_row("000001", "2025-01-29", 16),
                ]
            )
        )
        observation = baseline.evaluate_period(
            ["000001"], baseline.make_price_index(prepared), full_boundary("2025-01-01", "2025-01-29")
        )
        self.assertEqual(observation["stock_return_outlier_codes"], "000001")
        self.assertTrue(observation["portfolio_return_outlier"])
        self.assertAlmostEqual(observation["gross_return"], 0.6)

    def test_extreme_return_remains_in_headline_metrics(self):
        dates = pd.date_range("2025-01-01", periods=4, freq="28D")
        rows = [
            panel_row("000001", dates[0].strftime("%Y-%m-%d"), 10),
            panel_row("000001", dates[1].strftime("%Y-%m-%d"), 16),
            panel_row("000001", dates[2].strftime("%Y-%m-%d"), 16),
            panel_row("000001", dates[3].strftime("%Y-%m-%d"), 16),
        ]
        prices = baseline.make_price_index(baseline.prepare_price_panel(pd.DataFrame(rows)))
        boundaries = [baseline.Boundary(dates[i], dates[i + 1], 20, "full") for i in range(3)]
        periods = baseline.run_scenario(["000001"], prices, boundaries, "research", 0.0)
        metrics = baseline.portfolio_metrics(periods)
        self.assertTrue(periods.loc[0, "portfolio_return_outlier"])
        self.assertAlmostEqual(metrics["cumulative_return"], 0.6)

    def test_period_endpoint_maximum_drawdown(self):
        self.assertAlmostEqual(baseline.period_endpoint_maximum_drawdown([1.1, 0.88, 0.924]), -0.2)

    def test_benchmark_requires_exact_portfolio_period_endpoints(self):
        periods = pd.DataFrame(
            [
                {
                    "rebalance_date": pd.Timestamp("2025-01-01"),
                    "next_rebalance_date": pd.Timestamp("2025-01-29"),
                    "period_trading_days": 20,
                    "period_type": "full",
                    "headline_included": True,
                    "provisional": False,
                    "net_return": 0.1,
                    "nav": 1.1,
                }
            ]
        )
        prices = {("000300", pd.Timestamp("2025-01-01")): 100.0}
        _nav, metrics = baseline.benchmark_comparison(periods, prices, "000300")
        self.assertFalse(metrics["benchmark_comparison_valid"])

        prices[("000300", pd.Timestamp("2025-01-29"))] = 105.0
        nav, metrics = baseline.benchmark_comparison(periods, prices, "000300")
        self.assertTrue(metrics["benchmark_comparison_valid"])
        self.assertAlmostEqual(nav.loc[0, "benchmark_return"], 0.05)
        self.assertAlmostEqual(nav.loc[0, "active_return"], 0.05)

    def test_missing_partial_benchmark_endpoint_does_not_invalidate_headline_comparison(self):
        periods = pd.DataFrame(
            [
                {
                    "rebalance_date": pd.Timestamp("2025-01-01"),
                    "next_rebalance_date": pd.Timestamp("2025-01-29"),
                    "period_type": "full",
                    "headline_included": True,
                    "provisional": False,
                    "net_return": 0.1,
                    "nav": 1.1,
                },
                {
                    "rebalance_date": pd.Timestamp("2025-01-29"),
                    "next_rebalance_date": pd.Timestamp("2025-02-05"),
                    "period_type": "partial",
                    "headline_included": False,
                    "provisional": True,
                    "net_return": 0.02,
                    "nav": 1.122,
                },
            ]
        )
        prices = {
            ("000300", pd.Timestamp("2025-01-01")): 100.0,
            ("000300", pd.Timestamp("2025-01-29")): 105.0,
        }
        nav, metrics = baseline.benchmark_comparison(periods, prices, "000300")
        self.assertTrue(metrics["benchmark_comparison_valid"])
        self.assertTrue(nav.loc[0, "benchmark_period_valid"])
        self.assertFalse(nav.loc[1, "benchmark_period_valid"])
        self.assertTrue(pd.isna(metrics["latest_partial_benchmark_return"]))

    def test_report_has_research_only_metadata_and_drawdown_caveat(self):
        summary = pd.DataFrame(
            [
                {
                    "universe_name": "research",
                    "transaction_cost": 0.0,
                    "benchmark_code": "000300",
                    "scenario_status": "terminated_on_invalid_period",
                    "baseline_start_date": pd.Timestamp("2025-01-01"),
                    "last_full_period_end": pd.Timestamp("2025-04-01"),
                    "termination_date": pd.Timestamp("2025-04-01"),
                    "termination_reason": "end_price_missing",
                    "universe_count": 2,
                    "average_coverage_ratio": 1.0,
                    "minimum_coverage_ratio": 1.0,
                    "latest_partial_period_return": math.nan,
                    "cumulative_return": 0.1,
                    "benchmark_comparison_valid": True,
                }
            ]
        )
        report = baseline.render_report(summary, pd.DataFrame())
        self.assertIn("research_baseline_only=true", report)
        self.assertIn("formal_performance_conclusion_allowed=false", report)
        self.assertIn("no_investment_conclusion=true", report)
        self.assertIn("no investment conclusion", report)
        self.assertIn("period_endpoint_maximum_drawdown", report)
        self.assertIn("termination_reason=end_price_missing", report)
        self.assertIn("No full-sample effective-universe filter", report)

    def test_all_csv_metadata_fields_are_fixed(self):
        output = baseline._with_metadata(pd.DataFrame([{"value": 1}]))
        for key, value in baseline.METADATA.items():
            self.assertEqual(output.loc[0, key], value)


if __name__ == "__main__":
    unittest.main()
