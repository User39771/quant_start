import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from scripts.test_mom60_hypothesis_v1_3 import (
    DIRECTION_EPSILON,
    assess_hypothesis,
    assign_signal_quantiles,
    build_factor_panel,
    critical_exit_code,
    lookback_endpoints,
    mark_continuous_interval,
    market_calendar,
    q5_stock_contributions,
    quantile_monotonicity,
    rank_ic,
    render_report,
    write_csv,
)


class Mom60HypothesisTests(unittest.TestCase):
    def test_market_calendar_and_lookback_are_exact(self):
        dates = pd.bdate_range("2024-01-01", periods=90)
        benchmark = pd.DataFrame(
            {"benchmark_code": "000300", "trade_date": dates, "close": 1.0}
        )
        calendar = market_calendar(benchmark)
        self.assertEqual(calendar, list(dates))

        rebalance = dates[81]
        endpoints = lookback_endpoints(calendar, rebalance)
        self.assertEqual(endpoints["signal_as_of_date"], dates[80])
        self.assertEqual(endpoints["lookback_60_date"], dates[20])
        self.assertEqual(endpoints["lookback_40_date"], dates[40])
        self.assertEqual(endpoints["lookback_80_date"], dates[0])

    def test_signal_sample_is_grouped_before_label_availability(self):
        frame = pd.DataFrame(
            {
                "stock_code": [f"{i:06d}" for i in range(1, 11)],
                "baseline_eligible": True,
                "mom60": np.arange(10, dtype=float),
                "forward_return": np.arange(10, dtype=float) / 100,
            }
        )
        complete = assign_signal_quantiles(frame, "mom60")
        missing = frame.copy()
        missing.loc[9, "forward_return"] = np.nan
        missing = assign_signal_quantiles(missing, "mom60")
        self.assertEqual(complete["quantile"].tolist(), missing["quantile"].tolist())
        self.assertTrue(missing.loc[9, "signal_sample_member"])
        self.assertFalse(missing.loc[9, "evaluation_sample_member"])

    def test_factor_panel_keeps_all_codes_and_missing_label_eligible_stock(self):
        calendar = list(pd.bdate_range("2024-01-01", periods=90))
        rebalance, period_end = calendar[81], calendar[85]
        periods = pd.DataFrame(
            {
                "rebalance_date": [rebalance],
                "next_rebalance_date": [period_end],
                "eligible_codes": ["000001;000002"],
                "eligible_count": [2],
            }
        )
        universe = pd.DataFrame({"code": ["000001", "000002", "000003"]})
        rows = []
        for code in ("000001", "000002"):
            for date, price in (
                (calendar[20], 1.0),
                (calendar[40], 1.0),
                (calendar[0], 1.0),
                (calendar[80], 2.0),
                (rebalance, 2.0),
            ):
                rows.append((code, date, price))
        rows.append(("000001", period_end, 2.2))
        prices = pd.DataFrame(rows, columns=["stock_code", "trade_date", "adjusted_close"])
        panel = build_factor_panel(periods, universe, prices, calendar)
        self.assertEqual(len(panel), 3)
        missing_label = panel.loc[panel["stock_code"].eq("000002")].iloc[0]
        self.assertTrue(missing_label.signal_sample_member)
        self.assertFalse(missing_label.label_available)
        self.assertFalse(missing_label.evaluation_sample_member)

    def test_rank_ic_quantiles_and_invalid_signal(self):
        x = pd.Series([1.0, 2.0, 3.0, 4.0])
        y = pd.Series([10.0, 20.0, 30.0, 40.0])
        self.assertTrue(np.isclose(rank_ic(x, y, minimum_count=4), 1.0))
        self.assertTrue(np.isnan(rank_ic(pd.Series([1.0] * 4), y, minimum_count=4)))

        frame = pd.DataFrame(
            {
                "stock_code": [f"{i:06d}" for i in range(25)],
                "baseline_eligible": True,
                "mom60": np.arange(25),
                "forward_return": np.arange(25),
            }
        )
        grouped = assign_signal_quantiles(frame, "mom60")
        self.assertEqual(grouped.groupby("quantile").size().to_dict(), {1: 5, 2: 5, 3: 5, 4: 5, 5: 5})
        self.assertEqual(grouped.loc[grouped.mom60.idxmin(), "quantile"], 1)
        self.assertEqual(grouped.loc[grouped.mom60.idxmax(), "quantile"], 5)

    def test_continuous_interval_does_not_restart(self):
        readiness = pd.DataFrame(
            {
                "primary_period_valid": [False, True, True, True, True, False, True, True],
            }
        )
        marked = mark_continuous_interval(readiness, confirmation_periods=3)
        self.assertEqual(marked["period_phase"].tolist(), [
            "pre_start_diagnostic", "main", "main", "main", "main",
            "termination_period", "post_termination_diagnostic", "post_termination_diagnostic",
        ])

    def test_assessment_and_critical_exit_are_fixed(self):
        supported = assess_hypothesis(
            validation_mean_ic=0.01,
            validation_mean_spread=0.02,
            auxiliary_passes=[True, True, True, True, False],
        )
        self.assertEqual(supported, "directionally_supported_for_strategy_prototyping")
        self.assertEqual(
            assess_hypothesis(-DIRECTION_EPSILON * 2, -0.01, [False] * 5),
            "not_supported",
        )
        self.assertEqual(critical_exit_code(pd.DataFrame({"critical": [True], "pass": [False]})), 2)

    def test_mixed_long_table_allows_empty_stock_code(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "mixed.csv"
            write_csv(
                pd.DataFrame(
                    {
                        "row_type": ["segment", "q5_stock"],
                        "stock_code": [np.nan, "000001"],
                    }
                ),
                path,
            )
            result = pd.read_csv(path, dtype={"stock_code": str})
            self.assertTrue(pd.isna(result.loc[0, "stock_code"]))
            self.assertEqual(result.loc[1, "stock_code"], "000001")

    def test_q5_contribution_is_equal_weighted_and_monotonicity_is_explicit(self):
        q5 = pd.DataFrame(
            {
                "period_index": [0, 0, 1],
                "stock_code": ["000001", "000002", "000001"],
                "forward_return": [0.10, 0.20, 0.30],
            }
        )
        result = q5_stock_contributions(q5).set_index("stock_code")
        self.assertTrue(np.isclose(result.loc["000001", "q5_cumulative_arithmetic_contribution"], 0.35))
        self.assertTrue(np.isclose(result.loc["000002", "q5_cumulative_arithmetic_contribution"], 0.10))

        monotonic = quantile_monotonicity(pd.Series({1: 0.01, 2: 0.02, 3: 0.03, 4: 0.04, 5: 0.05}), 0.025)
        self.assertTrue(monotonic["strictly_monotonic"])
        self.assertTrue(monotonic["q5_above_universe"])

    def test_report_keeps_research_boundaries(self):
        report = render_report("completed", "not_supported", 54, 23)
        self.assertIn("current-universe", report)
        self.assertIn("historical chronological validation", report)
        self.assertIn("formal_performance_conclusion_allowed=false", report)


if __name__ == "__main__":
    unittest.main()
