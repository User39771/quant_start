from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "run_stock_pool_smoke_baseline_v1_2.py"
SPEC = importlib.util.spec_from_file_location("run_stock_pool_smoke_baseline_v1_2", MODULE_PATH)
smoke = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def price(code: str, date: str, close: str = "10") -> dict[str, str]:
    return {"stock_code": code, "trade_date": date, "close": close}


class StockPoolSmokeBaselineV12Tests(unittest.TestCase):
    def test_code6_preserves_leading_zero(self):
        self.assertEqual(smoke.code6("63"), "000063")

    def test_scenarios_are_four(self):
        scenarios = smoke.scenarios()
        self.assertEqual(
            [(s.universe_name, s.transaction_cost) for s in scenarios],
            [
                ("expanded_only_v1_2", 0.0),
                ("expanded_only_v1_2", 0.001),
                ("research_universe_v1_2", 0.0),
                ("research_universe_v1_2", 0.001),
            ],
        )

    def test_rebalance_dates_use_every_20th_trading_day(self):
        dates = [f"2025-01-{day:02d}" for day in range(1, 32)]
        self.assertEqual(smoke.rebalance_dates(dates, step=20), ["2025-01-01", "2025-01-21", "2025-01-31"])

    def test_equal_weight_target_weights_sum_to_one(self):
        weights = smoke.equal_weights(["000001", "000002", "000003"])
        self.assertAlmostEqual(sum(weights.values()), 1.0)
        self.assertAlmostEqual(weights["000001"], 1 / 3)

    def test_coverage_threshold_flags_diagnostic_period(self):
        universe = ["000001", "000002", "000003", "000004", "000005"]
        prices = smoke.index_prices(
            [
                price("000001", "2025-01-01", "10"),
                price("000002", "2025-01-01", "10"),
                price("000003", "2025-01-01", "10"),
                price("000001", "2025-01-21", "11"),
                price("000002", "2025-01-21", "11"),
                price("000003", "2025-01-21", "11"),
            ]
        )
        row, _weights, _qa = smoke.period_row(
            universe,
            prices,
            "expanded_only_v1_2",
            0.0,
            "2025-01-01",
            "2025-01-21",
            {},
            min_coverage_ratio=0.8,
        )
        self.assertEqual(row["available_count"], 3)
        self.assertEqual(row["coverage_pass"], "false")

    def test_duplicate_code_date_raises(self):
        with self.assertRaises(ValueError):
            smoke.index_prices([price("000001", "2025-01-01", "10"), price("000001", "2025-01-01", "11")])

    def test_missing_close_is_unavailable_without_forward_fill(self):
        universe = ["000001", "000002"]
        prices = smoke.index_prices(
            [
                price("000001", "2025-01-01", "10"),
                price("000001", "2025-01-21", ""),
                price("000002", "2025-01-01", "20"),
                price("000002", "2025-01-21", "22"),
            ]
        )
        row, weights, qa = smoke.period_row(
            universe,
            prices,
            "expanded_only_v1_2",
            0.0,
            "2025-01-01",
            "2025-01-21",
            {},
        )
        self.assertEqual(row["available_count"], 1)
        self.assertEqual(weights, {"000002": 1.0})
        self.assertEqual(qa["missing_close_count"], 1)
        self.assertIn("000001", qa["dropped_codes"])

    def test_drifted_weight_turnover(self):
        previous = {"000001": 0.5, "000002": 0.5}
        returns = {"000001": 0.2, "000002": 0.0}
        target = {"000001": 0.5, "000002": 0.5}
        drifted = smoke.drifted_weights(previous, returns)
        self.assertAlmostEqual(drifted["000001"], 0.6 / 1.1)
        self.assertAlmostEqual(smoke.turnover_from_drift(target, drifted), 0.04545454545454547)

    def test_report_metadata(self):
        report = smoke.render_report([], [], "caveat text")
        self.assertIn("smoke_only=true", report)
        self.assertIn("performance_conclusion_allowed=false", report)
        self.assertIn("no investment conclusion", report)


if __name__ == "__main__":
    unittest.main()
