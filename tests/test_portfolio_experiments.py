from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from aq_factor_lab.portfolio_experiments import (
    default_portfolio_experiments,
    run_portfolio_experiments,
    save_portfolio_experiment_outputs,
)


def row(date: str, code: str, factor: float, cap: float) -> dict[str, object]:
    return {
        "date": pd.Timestamp(date),
        "code": code,
        "name": code,
        "composite_alpha_ic_weighted": factor,
        "total_market_cap": cap,
        "amount_20d": 100_000_000.0,
        "amount": 10_000_000.0,
        "high": 11.0,
        "low": 10.0,
    }


def panel() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for date, lead_code in [
        ("2025-01-31", "000001"),
        ("2025-02-28", "000002"),
        ("2025-03-31", "000003"),
        ("2025-04-30", "000004"),
    ]:
        for index in range(1, 7):
            code = f"{index:06d}"
            factor = 10.0 if code == lead_code else float(6 - index)
            cap = 100.0 + index * 10.0
            rows.append(row(date, code, factor, cap))
    return pd.DataFrame(rows)


class PortfolioExperimentTests(unittest.TestCase):
    def test_default_experiment_grid_contains_required_configs(self):
        names = [config.name for config in default_portfolio_experiments()]

        self.assertEqual(
            names,
            [
                "baseline_top50_equal_no_buffer",
                "top100_equal",
                "top200_equal",
                "top50_buy50_sell150",
                "top100_buy100_sell300",
                "top100_buy100_sell300_max_turnover_0.5",
                "top100_buy100_sell300_max_turnover_0.5_dust_maxpos300",
            ],
        )

    def test_portfolio_experiments_output_metrics_nav_and_report(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            metrics, nav = run_portfolio_experiments(panel(), default_portfolio_experiments()[:2])
            report_path = save_portfolio_experiment_outputs(metrics, nav, root / "data", root / "reports")

            metrics_csv = pd.read_csv(root / "data" / "portfolio_experiment_metrics.csv")
            nav_csv = pd.read_csv(root / "data" / "portfolio_experiment_nav.csv")
            report = report_path.read_text(encoding="utf-8")

        required_metrics = {
            "experiment",
            "annualized_return",
            "annualized_excess_return",
            "max_drawdown",
            "excess_max_drawdown",
            "sharpe_ratio",
            "information_ratio",
            "annualized_turnover",
            "average_holding_count",
            "median_holding_count",
            "max_holding_count",
            "min_holding_count",
            "average_trade_count",
            "average_transaction_cost",
            "average_positions_below_10bp",
            "average_top10_weight",
            "average_effective_number_of_positions",
            "average_portfolio_factor_score",
            "average_benchmark_factor_score",
            "average_active_factor_score",
        }
        self.assertTrue(required_metrics.issubset(metrics_csv.columns))
        self.assertIn("baseline_top50_equal_no_buffer", set(metrics_csv["experiment"]))
        self.assertIn("top100_equal", set(metrics_csv["experiment"]))
        self.assertIn("experiment", nav_csv.columns)
        self.assertIn("IC strong does not guarantee portfolio alpha", report)
        self.assertIn("sample_inference=in_sample_comparison_only", report)
        self.assertIn("survivorship_bias_caveat", report)
        self.assertFalse(metrics.empty)
        self.assertFalse(nav.empty)


if __name__ == "__main__":
    unittest.main()
