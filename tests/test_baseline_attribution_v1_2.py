import unittest

import numpy as np
import pandas as pd

from scripts.analyze_baseline_attribution_v1_2 import (
    benchmark_metrics,
    attribution_coverage,
    align_benchmark_periods,
    align_cost_scenarios,
    critical_qa_exit_code,
    concentration_metrics,
    drawdown_window,
    fractional_theme_contributions,
    leave_one_out_returns,
    link_contributions,
    parse_eligible_codes,
    positive_contributor_code,
    render_report,
    select_headline_periods,
    theme_map_from_universe,
)


class BaselineAttributionTests(unittest.TestCase):
    def test_core_attribution_math(self):
        self.assertEqual(parse_eligible_codes("000001;300001", 2), ["000001", "300001"])
        with self.assertRaises(ValueError):
            parse_eligible_codes("1;300001", 2)
        with self.assertRaises(ValueError):
            parse_eligible_codes("000001;000001", 2)

        detail = pd.DataFrame(
            {
                "period_index": [0, 0, 1, 1],
                "stock_code": ["000001", "300001", "000001", "300001"],
                "stock_contribution": [0.05, 0.05, -0.025, 0.025],
            }
        )
        linked = link_contributions(detail, pd.Series({0: 0.10, 1: 0.00}))
        self.assertTrue(np.isclose(linked["linked_contribution"].sum(), 0.10))

        metrics = concentration_metrics(pd.Series([0.08, 0.02, -0.04]))
        self.assertTrue(np.isclose(metrics["positive_contribution_hhi"], 0.68))
        self.assertTrue(np.isclose(metrics["absolute_contribution_hhi"], 0.4285714285714286))

    def test_period_selection_drawdown_and_leave_one_out(self):
        periods = pd.DataFrame(
            {
                "rebalance_date": pd.to_datetime(["2024-01-01", "2024-02-01", "2024-03-01"]),
                "next_rebalance_date": pd.to_datetime(["2024-02-01", "2024-03-01", "2024-04-01"]),
                "period_type": ["full", "full", "partial"],
                "period_phase": ["headline", "headline", "provisional_partial"],
                "headline_included": [True, True, False],
            }
        )
        selected = select_headline_periods(periods)
        self.assertEqual(len(selected), 2)

        nav = pd.DataFrame(
            {
                "period_end": pd.to_datetime(["2024-02-01", "2024-03-01", "2024-04-01"]),
                "nav": [1.2, 0.9, 1.21],
            }
        )
        window = drawdown_window(nav, pd.Timestamp("2024-01-01"))
        self.assertEqual(window["peak_date"], pd.Timestamp("2024-02-01"))
        self.assertEqual(window["trough_date"], pd.Timestamp("2024-03-01"))
        self.assertEqual(window["recovery_date"], pd.Timestamp("2024-04-01"))

        stock_returns = pd.DataFrame(
            {
                "period_index": [0, 0, 1, 1],
                "stock_code": ["000001", "300001", "000001", "300001"],
                "stock_return": [0.10, 0.00, -0.10, 0.20],
            }
        )
        counterfactual = leave_one_out_returns(stock_returns, "000001")
        self.assertTrue(np.allclose(counterfactual["period_return"], [0.0, 0.2]))
        self.assertTrue(np.isclose(counterfactual.iloc[-1]["nav"], 1.2))

    def test_theme_allocation_and_benchmark_relative_wealth(self):
        stock = pd.DataFrame(
            {
                "period_index": [0],
                "stock_code": ["002049"],
                "stock_contribution": [0.10],
                "linked_contribution": [0.12],
            }
        )
        themes = {"002049": ["AI", "商业航天"]}
        allocated = fractional_theme_contributions(stock, themes)
        self.assertTrue(np.allclose(allocated["theme_allocation"], [0.5, 0.5]))
        self.assertTrue(np.isclose(allocated["theme_contribution"].sum(), 0.10))

        metrics = benchmark_metrics(
            pd.DataFrame(
                {
                    "portfolio_net_return": [0.10, -0.05],
                    "benchmark_return": [0.05, -0.02],
                    "portfolio_nav": [1.10, 1.045],
                    "benchmark_nav": [1.05, 1.029],
                }
            )
        )
        self.assertTrue(np.isclose(metrics["relative_wealth"], 1.045 / 1.029 - 1))
        self.assertTrue(np.isclose(metrics["arithmetic_active_return_sum"], 0.02))

    def test_benchmark_endpoint_alignment_rejects_missing_and_duplicates(self):
        expected = pd.DataFrame(
            {
                "rebalance_date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
                "next_rebalance_date": pd.to_datetime(["2024-02-01", "2024-03-01"]),
            }
        )
        missing = expected.iloc[:1].assign(
            benchmark_period_valid=True,
            benchmark_comparison_valid=True,
        )
        _, diagnostic = align_benchmark_periods(expected, missing)
        self.assertFalse(diagnostic["valid"])
        self.assertEqual(diagnostic["missing_count"], 1)

        duplicate = pd.concat([missing, missing], ignore_index=True)
        _, diagnostic = align_benchmark_periods(expected.iloc[:1], duplicate)
        self.assertFalse(diagnostic["valid"])
        self.assertEqual(diagnostic["duplicate_count"], 1)

    def test_cost_scenarios_align_by_period_key(self):
        left = pd.DataFrame(
            {
                "rebalance_date": pd.to_datetime(["2024-01-01", "2024-02-01"]),
                "next_rebalance_date": pd.to_datetime(["2024-02-01", "2024-03-01"]),
                "gross_return": [0.1, 0.2],
            }
        )
        right = left.iloc[::-1].copy()
        aligned = align_cost_scenarios(left, right)
        self.assertTrue(np.allclose(aligned["gross_return_cost_0"], aligned["gross_return_cost_0.001"]))
        with self.assertRaises(ValueError):
            align_cost_scenarios(left, right.iloc[:1])

    def test_coverage_theme_and_no_positive_contributor(self):
        universe = pd.DataFrame(
            {"code": ["000001", "000002", "000003"], "theme": ["AI", "AI", "商业航天"]}
        )
        detail = pd.DataFrame({"stock_code": ["000001", "000002"]})
        coverage = attribution_coverage(universe, detail)
        self.assertEqual(coverage["universe_unique_stock_count"], 3)
        self.assertEqual(coverage["attributed_stock_count"], 2)
        self.assertEqual(coverage["never_eligible_in_headline_codes"], "000003")
        self.assertIsNone(
            positive_contributor_code(pd.DataFrame({"linked_gross_contribution": [-0.1]}))
        )
        with self.assertRaises(ValueError):
            theme_map_from_universe(pd.DataFrame({"code": ["000001"], "theme": [np.nan]}))

    def test_critical_qa_and_report_boundaries(self):
        qa = pd.DataFrame(
            {
                "critical": [True],
                "pass": [False],
                "absolute_error": [0.01],
            }
        )
        self.assertEqual(critical_qa_exit_code(qa), 1)
        stock = pd.DataFrame(
            {
                "stock_code": ["000001"],
                "stock_name": ["Sample"],
                "linked_gross_contribution": [0.1],
            }
        )
        theme = pd.DataFrame(
            {
                "theme": ["AI"],
                "arithmetic_contribution_sum": [0.1],
                "linked_gross_contribution": [0.1],
                "contribution_rank": [1],
            }
        )
        summary = pd.DataFrame(
            [
                {
                    "section": "concentration",
                    "metric": "universe_unique_stock_count",
                    "value": 3,
                    "notes": "attribution coverage",
                }
            ]
        )
        report = render_report(stock, theme, summary, qa)
        self.assertIn("formal_performance_conclusion_allowed=false", report)
        self.assertIn("Attribution Coverage", report)


if __name__ == "__main__":
    unittest.main()
