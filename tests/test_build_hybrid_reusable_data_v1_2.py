from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_hybrid_reusable_data_v1_2.py"
SPEC = importlib.util.spec_from_file_location("build_hybrid_reusable_data_v1_2", MODULE_PATH)
hybrid = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = hybrid
SPEC.loader.exec_module(hybrid)


class HybridReusableDataV12Tests(unittest.TestCase):
    def test_code6_preserves_leading_zero(self):
        self.assertEqual(hybrid.code6("63"), "000063")

    def test_legacy_cache_frame_maps_raw_columns_and_adjusted_false(self):
        raw = pd.DataFrame(
            {
                "db_symbol": ["SZ_000063"],
                "date": ["2026-01-02"],
                "close": ["10.5"],
                "high": ["11"],
                "low": ["10"],
                "amount": ["1000000"],
                "total_market_cap": ["100"],
                "circulating_market_cap": ["90"],
            }
        )
        out = hybrid.normalize_legacy_price_cache("000063", raw, Path("cache.csv"))

        self.assertEqual(list(out.columns), hybrid.RAW_BASE_COLUMNS)
        self.assertEqual(out.loc[0, "stock_code"], "000063")
        self.assertEqual(out.loc[0, "trade_date"], "2026-01-02")
        self.assertEqual(out.loc[0, "adjusted_flag"], "false")
        self.assertEqual(out.loc[0, "data_layer"], "legacy_db_price_cache")

    def test_read_legacy_price_cache_does_not_forward_fill_missing_prices(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp)
            pd.DataFrame(
                {
                    "date": ["2026-01-02", "2026-01-03"],
                    "close": ["10", ""],
                    "high": ["11", ""],
                    "low": ["9", ""],
                    "amount": ["100", "200"],
                }
            ).to_csv(cache_dir / "000063.csv", index=False)

            panel, gaps, manifest = hybrid.build_raw_base_panel(["000063"], cache_dir)

        self.assertEqual(len(panel), 1)
        self.assertEqual(panel.loc[0, "close"], 10.0)
        self.assertTrue(any(row["gap_type"] == "dropped_missing_close" for row in gaps))
        self.assertEqual(manifest[0]["status"], "ok")

    def test_readiness_layers_do_not_treat_raw_close_as_formal_adjusted(self):
        raw_panel = pd.DataFrame(
            {
                "stock_code": ["000063", "300857"],
                "trade_date": ["2026-01-02", "2026-01-02"],
                "close": [10.0, 20.0],
                "high": [11.0, 21.0],
                "low": [9.0, 19.0],
                "amount": [100.0, 200.0],
                "adjusted_flag": ["false", "false"],
            }
        )
        benchmark = pd.DataFrame({"benchmark_code": ["000300", "000852"], "trade_date": ["2026-01-02", "2026-01-02"], "close": [1, 2]})
        readiness = hybrid.evaluate_readiness(raw_panel, benchmark, ["000063", "300857"], [])

        self.assertTrue(readiness["raw_base_ready"])
        self.assertTrue(readiness["benchmark_ready"])
        self.assertFalse(readiness["adjusted_return_ready"])
        self.assertFalse(readiness["execution_sim_ready"])
        self.assertFalse(readiness["formal_performance_conclusion_allowed"])

    def test_missing_required_benchmark_blocks_benchmark_ready(self):
        raw_panel = pd.DataFrame({"stock_code": ["000063"], "close": [10.0], "adjusted_flag": ["false"]})
        benchmark = pd.DataFrame({"benchmark_code": ["000300"], "close": [1.0]})
        readiness = hybrid.evaluate_readiness(raw_panel, benchmark, ["000063"], [])

        self.assertFalse(readiness["benchmark_ready"])
        self.assertEqual(readiness["missing_required_benchmarks"], "000852")

    def test_tx_symbol_mapping(self):
        self.assertEqual(hybrid.tx_symbol("000300"), "sh000300")
        self.assertEqual(hybrid.tx_symbol("000852"), "sh000852")
        self.assertEqual(hybrid.tx_symbol("399006"), "sz399006")

    def test_clip_date_window_keeps_only_requested_dates(self):
        frame = pd.DataFrame(
            {
                "trade_date": ["2025-12-31", "2026-01-02", "2026-01-03"],
                "close": [1, 2, 3],
            }
        )
        out = hybrid.clip_date_window(frame, "trade_date", "2026-01-01", "2026-01-02")

        self.assertEqual(out["trade_date"].tolist(), ["2026-01-02"])


if __name__ == "__main__":
    unittest.main()
