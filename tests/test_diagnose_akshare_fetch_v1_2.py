from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_akshare_fetch_v1_2.py"
SPEC = importlib.util.spec_from_file_location("diagnose_akshare_fetch_v1_2", MODULE_PATH)
diag = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = diag
SPEC.loader.exec_module(diag)


class FakeAk:
    __version__ = "9.9.9"

    def stock_zh_a_hist(self, **_kwargs):
        return pd.DataFrame({"date": ["2026-01-01"], "close": [10.0]})

    def index_zh_a_hist(self, **_kwargs):
        raise RuntimeError("index failed")


class AkShareFetchDiagnosticsV12Tests(unittest.TestCase):
    def test_call_records_success_row_count_and_columns(self):
        row = diag.call_endpoint(
            lambda: pd.DataFrame({"date": ["2026-01-01"], "close": [10.0]}),
            symbol="000063",
            asset_type="stock",
            endpoint="ak.stock_zh_a_hist",
            adjust_type="raw",
            date_window="full",
        )
        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["row_count"], 1)
        self.assertEqual(row["columns"], "date,close")

    def test_call_records_exception(self):
        row = diag.call_endpoint(
            lambda: (_ for _ in ()).throw(ValueError("bad endpoint")),
            symbol="000681",
            asset_type="stock",
            endpoint="ak.stock_zh_a_hist",
            adjust_type="qfq",
            date_window="full",
        )
        self.assertEqual(row["status"], "error")
        self.assertEqual(row["error_type"], "ValueError")
        self.assertIn("bad endpoint", row["error_message"])

    def test_missing_fallback_function_records_function_missing(self):
        class NoFallback(FakeAk):
            pass

        if hasattr(NoFallback, "stock_zh_index_daily_tx"):
            delattr(NoFallback, "stock_zh_index_daily_tx")
        row = diag.fallback_index_call(NoFallback(), "000300")
        self.assertEqual(row["status"], "function_missing")
        self.assertEqual(row["endpoint"], "ak.stock_zh_index_daily_tx")

    def test_tx_symbol_mapping(self):
        self.assertEqual(diag.tx_symbol("000300"), "sh000300")
        self.assertEqual(diag.tx_symbol("000852"), "sh000852")
        self.assertEqual(diag.tx_symbol("399006"), "sz399006")

    def test_report_contains_version_and_status_counts(self):
        rows = [
            {
                "symbol": "000063",
                "asset_type": "stock",
                "endpoint": "ak.stock_zh_a_hist",
                "adjust_type": "raw",
                "date_window": "full",
                "status": "ok",
                "row_count": 1,
                "columns": "date,close",
                "elapsed_seconds": 0.1,
                "error_type": "",
                "error_message": "",
            },
            {
                "symbol": "000300",
                "asset_type": "benchmark",
                "endpoint": "ak.index_zh_a_hist",
                "adjust_type": "raw",
                "date_window": "full",
                "status": "error",
                "row_count": 0,
                "columns": "",
                "elapsed_seconds": 0.1,
                "error_type": "RuntimeError",
                "error_message": "index failed",
            },
        ]
        report = diag.render_report(rows, "9.9.9")
        self.assertIn("AkShare version: 9.9.9", report)
        self.assertIn("ak.stock_zh_a_hist", report)
        self.assertIn("ok", report)
        self.assertIn("error", report)


if __name__ == "__main__":
    unittest.main()
