import hashlib
import math
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from scripts.test_lowvol20_hypothesis_v1_4 import (
    OUTPUT_FILES,
    assess_hypothesis,
    assign_quantiles,
    evaluate_factor,
    forward_risk_statistics,
    main,
    market_calendar,
    mark_continuous_interval,
    moving_block_bootstrap,
    period_annualization,
    window_statistics,
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LowVol20Tests(unittest.TestCase):
    def test_exact_window_and_lowvol_direction(self):
        dates = pd.bdate_range("2024-01-01", periods=30)
        prices = pd.Series(np.linspace(10.0, 12.0, 21), index=dates[:21])
        result = window_statistics(prices, list(dates), dates[20], 20)
        self.assertEqual(result["price_observation_count"], 21)
        self.assertEqual(result["return_interval_count"], 20)
        self.assertEqual(result["window_start_date"], dates[0])
        self.assertTrue(np.isclose(result["lowvol"], -result["volatility"]))

        missing = window_statistics(prices.drop(dates[10]), list(dates), dates[20], 20)
        self.assertFalse(missing["signal_available"])

    def test_flat_price_reliability_is_fixed(self):
        dates = pd.bdate_range("2024-01-01", periods=21)
        flat = window_statistics(pd.Series(10.0, index=dates), list(dates), dates[-1], 20)
        self.assertTrue(flat["flat_price_risk_flag"])
        self.assertFalse(flat["primary_reliable_signal"])
        self.assertEqual(flat["zero_return_count"], 20)

        moving = pd.Series(10.0 + np.arange(21) * 0.1, index=dates)
        reliable = window_statistics(moving, list(dates), dates[-1], 20)
        self.assertTrue(reliable["primary_reliable_signal"])
        self.assertEqual(reliable["longest_zero_return_run"], 0)

    def test_forward_risk_uses_every_market_date(self):
        dates = list(pd.bdate_range("2024-01-01", periods=6))
        prices = pd.Series([10, 11, 10, 12, 11, 13], index=dates, dtype=float)
        result = forward_risk_statistics(prices, dates, dates[0], dates[-1])
        expected = prices.pct_change().dropna().std(ddof=1) * math.sqrt(252)
        self.assertEqual(result["forward_market_interval_count"], 5)
        self.assertEqual(result["forward_price_observation_count"], 6)
        self.assertTrue(np.isclose(result["forward_realized_volatility"], expected))

        missing = forward_risk_statistics(prices.drop(dates[3]), dates, dates[0], dates[-1])
        self.assertFalse(missing["forward_risk_available"])

    def test_quantiles_ignore_future_label_and_report_ties(self):
        frame = pd.DataFrame(
            {
                "stock_code": [f"{i:06d}" for i in range(25)],
                "baseline_eligible": True,
                "lowvol20": np.arange(25, dtype=float),
                "primary_reliable_signal": True,
                "forward_return": np.arange(25, dtype=float) / 100,
                "forward_risk_available": True,
            }
        )
        complete, diagnostics = assign_quantiles(frame, "lowvol20", reliable=True)
        missing = frame.copy()
        missing.loc[24, "forward_return"] = np.nan
        missing, _ = assign_quantiles(missing, "lowvol20", reliable=True)
        self.assertEqual(complete["quantile"].tolist(), missing["quantile"].tolist())
        self.assertTrue(missing.loc[24, "signal_sample_member"])
        self.assertFalse(missing.loc[24, "evaluation_sample_member"])
        self.assertEqual(complete.loc[complete.lowvol20.idxmin(), "quantile"], 1)
        self.assertEqual(complete.loc[complete.lowvol20.idxmax(), "quantile"], 5)
        self.assertEqual(diagnostics["signal_unique_value_count"], 25)

        tied = frame.copy()
        tied["lowvol20"] = np.repeat([1.0, 2.0, 3.0, 4.0, 4.0], 5)
        tied, diagnostics = assign_quantiles(tied, "lowvol20", reliable=True)
        self.assertFalse(diagnostics["quantile_valid"])
        self.assertTrue(tied["quantile"].isna().all())
        self.assertEqual(diagnostics["signal_unique_value_count"], 4)
        self.assertEqual(diagnostics["largest_tie_group_count"], 10)

    def test_period_annualization_uses_actual_median(self):
        fixed = period_annualization([20, 20, 20])
        self.assertTrue(np.isclose(fixed["factor"], math.sqrt(252 / 20)))
        self.assertFalse(fixed["approximate"])
        varied = period_annualization([19, 20, 22])
        self.assertTrue(np.isclose(varied["factor"], math.sqrt(252 / 20)))
        self.assertTrue(varied["approximate"])
        self.assertEqual(varied["minimum"], 19)
        self.assertEqual(varied["maximum"], 22)

    def test_q5_contribution_reconciles_to_period_return(self):
        panel = pd.DataFrame(
            {
                "period_index": 0,
                "stock_code": [f"{i:06d}" for i in range(25)],
                "rebalance_date": pd.Timestamp("2024-01-02"),
                "baseline_eligible": True,
                "lowvol20": np.arange(25, dtype=float),
                "primary_reliable_signal": True,
                "forward_return": np.arange(25, dtype=float) / 100,
                "forward_realized_volatility": np.arange(25, dtype=float) / 10 + 0.1,
                "forward_risk_available": True,
                "flat_price_risk_flag": False,
            }
        )
        _, quantiles, members = evaluate_factor(
            panel, {0}, "lowvol20", "lowvol20_primary_reliable_sample"
        )
        q5_return = quantiles.loc[quantiles["portfolio"].eq("Q5"), "period_return"].iloc[0]
        self.assertTrue(np.isclose(members["q5_contribution"].sum(), q5_return))

    def test_bootstrap_is_deterministic(self):
        q1 = np.array([0.01, -0.02, 0.03, -0.01, 0.02])
        q5 = np.array([0.02, -0.01, 0.04, 0.00, 0.03])
        first = moving_block_bootstrap(q1, q5, math.sqrt(252 / 20), replications=50)
        second = moving_block_bootstrap(q1, q5, math.sqrt(252 / 20), replications=50)
        self.assertEqual(first, second)

    def test_continuous_interval_does_not_restart(self):
        readiness = pd.DataFrame({"primary_period_valid": [False, True, True, True, False, True]})
        marked = mark_continuous_interval(readiness)
        self.assertEqual(
            marked["period_phase"].tolist(),
            [
                "pre_start_diagnostic",
                "main",
                "main",
                "main",
                "termination_period",
                "post_termination_diagnostic",
            ],
        )

    def test_assessment_requires_all_primary_evidence(self):
        self.assertEqual(
            assess_hypothesis([True, True, True, True], [True] * 5 + [False] * 3),
            "directionally_supported_for_strategy_prototyping",
        )
        self.assertEqual(
            assess_hypothesis([True, False, True, True], [True] * 8),
            "mixed",
        )
        self.assertEqual(
            assess_hypothesis([False, False, True, True], [True] * 8),
            "mixed_risk_reduction_only",
        )
        self.assertEqual(
            assess_hypothesis([False, False, False, True], [False] * 8),
            "not_supported",
        )

    def test_market_calendar_rejects_duplicate_dates(self):
        dates = pd.to_datetime(["2024-01-02", "2024-01-02"])
        benchmark = pd.DataFrame(
            {"benchmark_code": ["000300", "000300"], "trade_date": dates, "close": [1, 1]}
        )
        with self.assertRaises(ValueError):
            market_calendar(benchmark)

    def test_main_end_to_end_writes_only_lowvol_outputs(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data" / "processed"
            reports = root / "reports"
            data.mkdir(parents=True)
            reports.mkdir()
            dates = pd.bdate_range("2023-06-01", periods=370)
            codes = [f"{i:06d}" for i in range(1, 26)]

            pd.DataFrame(
                {"benchmark_code": "000300", "trade_date": dates, "close": np.arange(len(dates)) + 1}
            ).to_csv(data / "hybrid_benchmark_panel_v1_2.csv", index=False)
            pd.DataFrame({"code": codes}).to_csv(
                data / "backtest_universe_research_v1_2.csv", index=False
            )

            periods = []
            for index, start in enumerate(range(60, 360, 20)):
                periods.append(
                    {
                        "universe_name": "research_universe_v1_2",
                        "transaction_cost": 0,
                        "headline_included": True,
                        "period_type": "full",
                        "period_phase": "headline",
                        "rebalance_date": dates[start],
                        "next_rebalance_date": dates[start + 20],
                        "eligible_codes": ";".join(codes),
                        "eligible_count": len(codes),
                    }
                )
            pd.DataFrame(periods).to_csv(
                reports / "adjusted_stock_pool_baseline_periods_v1_2.csv", index=False
            )

            rows = []
            for stock_index, code in enumerate(codes, start=1):
                amplitude = 0.001 + stock_index * 0.0002
                returns = 0.0005 + amplitude * np.sin(np.arange(len(dates)) / 3 + stock_index)
                close = 10 * np.cumprod(1 + returns)
                rows.extend(
                    {
                        "stock_code": code,
                        "trade_date": date,
                        "adjusted_close": price,
                        "qfq_close": price,
                        "adjusted_flag": True,
                        "close": price,
                    }
                    for date, price in zip(dates, close)
                )
            pd.DataFrame(rows).to_csv(data / "adjusted_price_panel_v1_2.csv", index=False)

            frozen = [
                data / "hybrid_benchmark_panel_v1_2.csv",
                data / "backtest_universe_research_v1_2.csv",
                data / "adjusted_price_panel_v1_2.csv",
                reports / "adjusted_stock_pool_baseline_periods_v1_2.csv",
            ]
            mom = reports / "factor_mom60_v1_3.md"
            mom.write_text("frozen", encoding="utf-8")
            frozen.append(mom)
            before = {path: sha256(path) for path in frozen}

            exit_code = main(["--project-root", str(root)])
            self.assertEqual(exit_code, 0)
            for relative in OUTPUT_FILES:
                self.assertTrue((root / relative).exists(), relative)
            factor_panel = pd.read_csv(
                data / "lowvol20_factor_panel_v1_4.csv",
                dtype={"stock_code": str},
            )
            self.assertTrue(
                {
                    "signal_available",
                    "label_available",
                    "risk_label_available",
                    "sample_basis",
                    "all_exact_signal_sample_member",
                    "common_exact_signal_sample_member",
                }.issubset(factor_panel.columns)
            )
            self.assertEqual(before, {path: sha256(path) for path in frozen})
            report = (reports / "factor_lowvol20_v1_4.md").read_text(encoding="utf-8")
            self.assertIn("formal_performance_conclusion_allowed=false", report)
            self.assertIn("suspension_status_available=false", report)
            self.assertIn("current-universe", report)

            not_ready = pd.read_csv(
                reports / "adjusted_stock_pool_baseline_periods_v1_2.csv"
            )
            not_ready["eligible_codes"] = ";".join(codes[:5])
            not_ready["eligible_count"] = 5
            not_ready.to_csv(
                reports / "adjusted_stock_pool_baseline_periods_v1_2.csv", index=False
            )
            self.assertEqual(main(["--project-root", str(root)]), 1)

            bad_prices = pd.read_csv(data / "adjusted_price_panel_v1_2.csv")
            bad_prices = pd.concat([bad_prices, bad_prices.iloc[[0]]], ignore_index=True)
            bad_prices.to_csv(data / "adjusted_price_panel_v1_2.csv", index=False)
            self.assertEqual(main(["--project-root", str(root)]), 2)


if __name__ == "__main__":
    unittest.main()
