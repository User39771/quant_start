from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from aq_factor_lab.portfolio_experiments import PortfolioExperimentConfig
from aq_factor_lab.walk_forward import (
    WalkForwardSplit,
    run_walk_forward_validation,
    save_walk_forward_outputs,
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
    dates = ["2021-01-31", "2021-02-28", "2021-03-31", "2021-04-30", "2021-05-31"]
    for date in dates:
        rows.extend(
            [
                row(date, "000001", 2.0, 100.0),
                row(date, "000002", 1.0, 100.0),
                row(date, "000003", 0.5, 100.0),
            ]
        )
    # Train period rewards concentrated top1; test period reverses it. The selected config
    # must still be the train winner, proving the test period is not used for selection.
    cap_by_date = {
        "2021-02-28": {"000001": 120.0, "000002": 100.0, "000003": 100.0},
        "2021-03-31": {"000001": 144.0, "000002": 100.0, "000003": 100.0},
        "2021-04-30": {"000001": 72.0, "000002": 130.0, "000003": 130.0},
        "2021-05-31": {"000001": 36.0, "000002": 169.0, "000003": 169.0},
    }
    frame = pd.DataFrame(rows)
    for date, caps in cap_by_date.items():
        for code, cap in caps.items():
            frame.loc[(frame["date"] == pd.Timestamp(date)) & (frame["code"] == code), "total_market_cap"] = cap
    return frame


class WalkForwardTests(unittest.TestCase):
    def test_walk_forward_selects_config_using_train_period_only(self):
        experiments = [
            PortfolioExperimentConfig("concentrated", top_n=1, buy_rank=1, sell_rank=1),
            PortfolioExperimentConfig("diversified", top_n=2, buy_rank=2, sell_rank=2),
        ]
        splits = [
            WalkForwardSplit("s1", "2021-01-31", "2021-03-31", "2021-03-31", "2021-05-31"),
        ]

        metrics, nav = run_walk_forward_validation(
            panel(),
            experiments,
            splits=splits,
            selection_metric="annualized_excess_return",
            transaction_cost_rate=0.0,
        )

        self.assertEqual(metrics.loc[0, "selected_experiment"], "concentrated")
        self.assertLess(float(metrics.loc[0, "test_annualized_excess_return"]), 0.0)
        self.assertIn("split", nav.columns)
        self.assertFalse(nav.empty)

    def test_walk_forward_outputs_csv_and_report(self):
        experiments = [PortfolioExperimentConfig("top1", top_n=1, buy_rank=1, sell_rank=1)]
        splits = [WalkForwardSplit("s1", "2021-01-31", "2021-03-31", "2021-03-31", "2021-05-31")]
        metrics, nav = run_walk_forward_validation(panel(), experiments, splits=splits, transaction_cost_rate=0.0)

        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            report_path = save_walk_forward_outputs(metrics, nav, root / "data", root / "reports")
            metrics_csv = pd.read_csv(root / "data" / "walk_forward_metrics.csv")
            nav_csv = pd.read_csv(root / "data" / "walk_forward_nav.csv")
            report = report_path.read_text(encoding="utf-8")

        self.assertIn("selected_experiment", metrics_csv.columns)
        self.assertIn("test_annualized_excess_return", metrics_csv.columns)
        self.assertIn("split", nav_csv.columns)
        self.assertIn("out_of_sample_overall_annualized_excess_return", report)
        self.assertIn("in_sample_best_is_not_strategy_proof", report)


if __name__ == "__main__":
    unittest.main()
