from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "diagnose_qfq_sources_v1_2.py"
SPEC = importlib.util.spec_from_file_location("diagnose_qfq_sources_v1_2", MODULE_PATH)
diag = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = diag
SPEC.loader.exec_module(diag)


class QfqSourceDiagnosticsV12Tests(unittest.TestCase):
    def test_sina_symbol_mapping(self):
        self.assertEqual(diag.sina_symbol("000063"), "sz000063")
        self.assertEqual(diag.sina_symbol("300857"), "sz300857")
        self.assertEqual(diag.sina_symbol("600519"), "sh600519")

    def test_successful_call_records_dates_and_latest_close(self):
        row = diag.call_endpoint(
            lambda: pd.DataFrame({"date": ["2026-01-01", "2026-01-02"], "close": [10.0, 11.0]}),
            stock_code="000063",
            source_name="sina_daily",
            symbol_used="sz000063",
            window_type="short",
            start_date="2026-01-01",
            end_date="2026-01-02",
        )

        self.assertEqual(row["status"], "ok")
        self.assertEqual(row["row_count"], 2)
        self.assertEqual(row["first_date"], "2026-01-01")
        self.assertEqual(row["last_date"], "2026-01-02")
        self.assertEqual(row["latest_close"], 11.0)

    def test_invalid_schema_when_date_or_close_missing(self):
        row = diag.call_endpoint(
            lambda: pd.DataFrame({"foo": ["2026-01-01"], "bar": [10.0]}),
            stock_code="000063",
            source_name="sina_daily",
            symbol_used="sz000063",
            window_type="short",
            start_date="2026-01-01",
            end_date="2026-01-02",
        )

        self.assertEqual(row["status"], "invalid_schema")

    def test_invalid_schema_when_latest_close_not_positive(self):
        row = diag.call_endpoint(
            lambda: pd.DataFrame({"date": ["2026-01-01"], "close": [0]}),
            stock_code="000063",
            source_name="sina_daily",
            symbol_used="sz000063",
            window_type="short",
            start_date="2026-01-01",
            end_date="2026-01-02",
        )

        self.assertEqual(row["status"], "invalid_schema")

    def test_exception_records_error(self):
        row = diag.call_endpoint(
            lambda: (_ for _ in ()).throw(RuntimeError("push2his.eastmoney.com failed")),
            stock_code="000063",
            source_name="eastmoney_hist",
            symbol_used="000063",
            window_type="short",
            start_date="2026-01-01",
            end_date="2026-01-02",
        )

        self.assertEqual(row["status"], "error")
        self.assertEqual(row["error_type"], "RuntimeError")
        self.assertIn("push2his", row["error_message"])

    def test_short_window_start(self):
        self.assertEqual(diag.short_start_date("2026-06-16", 180), "2025-12-18")

    def test_call_plan_order(self):
        plan = diag.build_call_plan(["000063"], "2020-01-02", "2026-06-16", 180)
        self.assertEqual(
            [(row["source_name"], row["window_type"]) for row in plan],
            [("sina_daily", "short"), ("eastmoney_hist", "short"), ("sina_daily", "full"), ("eastmoney_hist", "full")],
        )

    def test_report_mentions_push2his_concentration_and_sina_fallback(self):
        rows = [
            {
                "stock_code": "000063",
                "source_name": "eastmoney_hist",
                "symbol_used": "000063",
                "adjust_type": "qfq",
                "window_type": "short",
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
                "status": "error",
                "row_count": 0,
                "columns": "",
                "first_date": "",
                "last_date": "",
                "latest_close": "",
                "elapsed_seconds": 0.1,
                "error_type": "RuntimeError",
                "error_message": "push2his.eastmoney.com failed",
            },
            {
                "stock_code": "000063",
                "source_name": "sina_daily",
                "symbol_used": "sz000063",
                "adjust_type": "qfq",
                "window_type": "short",
                "start_date": "2026-01-01",
                "end_date": "2026-01-02",
                "status": "ok",
                "row_count": 1,
                "columns": "date,close",
                "first_date": "2026-01-01",
                "last_date": "2026-01-01",
                "latest_close": 10.0,
                "elapsed_seconds": 0.1,
                "error_type": "",
                "error_message": "",
            },
        ]

        report = diag.render_report(rows)

        self.assertIn("push2his.eastmoney.com", report)
        self.assertIn("Sina daily fallback candidate: yes", report)


if __name__ == "__main__":
    unittest.main()
