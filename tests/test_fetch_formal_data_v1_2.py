from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "fetch_formal_data_v1_2.py"
SPEC = importlib.util.spec_from_file_location("fetch_formal_data_v1_2", MODULE_PATH)
fetcher = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = fetcher
SPEC.loader.exec_module(fetcher)


def frame(symbol: str, closes: list[float], *, adjusted: bool) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol] * len(closes),
            "date": pd.to_datetime(["2026-01-01", "2026-01-02"][: len(closes)]),
            "open": closes,
            "high": [value + 1 for value in closes],
            "low": [value - 1 for value in closes],
            "close": closes,
            "volume": [1000.0] * len(closes),
            "amount": [10000.0] * len(closes),
            "turnover": [1.0] * len(closes),
            "adjusted": [adjusted] * len(closes),
            "source": ["akshare.stock_zh_a_hist"] * len(closes),
        }
    )


class FetchFormalDataV12Tests(unittest.TestCase):
    def test_code6_preserves_leading_zero(self):
        self.assertEqual(fetcher.code6("63"), "000063")

    def test_infer_date_range_from_price_panel(self):
        df = pd.DataFrame({"trade_date": ["2026-01-03", "2026-01-01", "2026-01-02"]})
        self.assertEqual(fetcher.infer_date_range(df), ("2026-01-01", "2026-01-03"))

    def test_merge_raw_and_qfq_stock_frames_outputs_required_schema(self):
        out = fetcher.merge_stock_frames(
            "000001",
            frame("000001", [10.0, 11.0], adjusted=False),
            frame("000001", [9.0, 10.0], adjusted=True),
            fetched_at="2026-07-05T00:00:00+00:00",
        )
        self.assertEqual(list(out.columns), fetcher.PRICE_COLUMNS)
        self.assertEqual(out.loc[0, "stock_code"], "000001")
        self.assertEqual(out.loc[0, "close"], 10.0)
        self.assertEqual(out.loc[0, "qfq_close"], 9.0)
        self.assertEqual(out.loc[0, "adjusted_close"], 9.0)
        self.assertTrue(pd.isna(out.loc[0, "pre_close"]))
        self.assertEqual(out.loc[1, "pre_close"], 9.0)
        self.assertEqual(out.loc[0, "adjust_type"], "raw+qfq")

    def test_benchmark_frame_generates_pre_close(self):
        out = fetcher.format_benchmark_frame(
            "000300",
            frame("000300", [3000.0, 3010.0], adjusted=False),
            fetched_at="2026-07-05T00:00:00+00:00",
        )
        self.assertEqual(list(out.columns), fetcher.BENCHMARK_COLUMNS)
        self.assertEqual(out.loc[0, "benchmark_code"], "000300")
        self.assertTrue(pd.isna(out.loc[0, "pre_close"]))
        self.assertEqual(out.loc[1, "pre_close"], 3000.0)

    def test_qa_flags_duplicate_rows_and_critical_failures(self):
        panel = fetcher.merge_stock_frames(
            "000001",
            frame("000001", [10.0], adjusted=False),
            frame("000001", [9.0], adjusted=True),
            fetched_at="2026-07-05T00:00:00+00:00",
        )
        panel = pd.concat([panel, panel], ignore_index=True)
        failures = pd.DataFrame(
            [
                {
                    "symbol": "000002",
                    "asset_type": "stock",
                    "endpoint": "daily_price",
                    "adjust_type": "qfq",
                    "attempts": 3,
                    "critical": "true",
                    "error_type": "RuntimeError",
                    "error_message": "boom",
                }
            ]
        )
        qa = fetcher.evaluate_readiness(
            panel,
            pd.DataFrame(columns=fetcher.BENCHMARK_COLUMNS),
            ["000001", "000002"],
            failures,
            required_benchmarks=["000300", "000852"],
            target_end_date="2026-01-01",
        )
        self.assertFalse(qa["formal_ready"])
        self.assertEqual(qa["duplicate_stock_date_rows"], 2)
        self.assertEqual(qa["critical_failure_count"], 1)

    def test_report_contains_no_investment_conclusion_and_caveats(self):
        report = fetcher.render_report(
            {"formal_ready": False, "stock_coverage_ratio": 0.5, "covered_stock_count": 1, "universe_count": 2},
            [],
            [],
        )
        self.assertIn("no investment conclusion", report)
        self.assertIn("not a point-in-time strategy backtest", report)
        self.assertIn("Historical ST", report)

    def test_select_symbols_prefers_explicit_symbols_then_limit(self):
        self.assertEqual(
            fetcher.select_symbols(["000001", "000002", "300857"], "63,300857", None),
            ["000063", "300857"],
        )
        self.assertEqual(
            fetcher.select_symbols(["000001", "000002", "300857"], None, 2),
            ["000001", "000002"],
        )

    def test_completed_manifest_pairs_only_ok_rows(self):
        manifest = pd.DataFrame(
            [
                {"symbol": "000063", "asset_type": "stock", "adjust_type": "raw", "status": "ok"},
                {"symbol": "000063", "asset_type": "stock", "adjust_type": "qfq", "status": "error"},
                {"symbol": "000300", "asset_type": "benchmark", "adjust_type": "raw", "status": "ok"},
            ]
        )
        self.assertEqual(fetcher.completed_manifest_pairs(manifest), {("000063", "stock", "raw"), ("000300", "benchmark", "raw")})

    def test_append_csv_writes_header_once(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "rows.csv"
            fetcher.append_csv_rows(path, [{"symbol": "000063", "status": "ok"}], ["symbol", "status"])
            fetcher.append_csv_rows(path, [{"symbol": "300857", "status": "ok"}], ["symbol", "status"])
            out = pd.read_csv(path, dtype={"symbol": str})

        self.assertEqual(list(out["symbol"]), ["000063", "300857"])
        self.assertEqual(list(out.columns), ["symbol", "status"])

    def test_dry_run_plan_lists_counts_symbols_and_dates(self):
        plan = fetcher.dry_run_plan(["000063", "300857"], ["000300"], ["399006"], "2026-01-01", "2026-01-31")
        self.assertIn("stock_count=2", plan)
        self.assertIn("000063,300857", plan)
        self.assertIn("benchmarks=000300", plan)
        self.assertIn("optional_benchmarks=399006", plan)
        self.assertIn("date_range=2026-01-01..2026-01-31", plan)

    def test_fetch_stock_symbol_does_not_duplicate_completed_adjust_manifest(self):
        class FakeService:
            def get_daily_price(self, symbol, start, end, adjusted=True):
                return frame(symbol, [9.0, 10.0] if adjusted else [10.0, 11.0], adjusted=adjusted)

        panel, manifests, failures = fetcher.fetch_stock_symbol(
            FakeService(),
            "000063",
            "2026-01-01",
            "2026-01-02",
            "2026-07-05T00:00:00+00:00",
            2,
            completed_adjusts={"raw"},
        )
        self.assertEqual([row["adjust_type"] for row in manifests], ["qfq"])
        self.assertEqual(failures, [])
        self.assertFalse(panel.empty)


if __name__ == "__main__":
    unittest.main()
