from __future__ import annotations

import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from aq_factor_lab.cli import build_parser, db_cache_quality_metadata, main
from aq_factor_lab.config import ResearchConfig


class CliDefaultsTests(unittest.TestCase):
    def test_default_sleep_reduces_request_frequency_to_one_tenth(self):
        self.assertEqual(ResearchConfig.__dataclass_fields__["sleep_seconds"].default, 10.0)
        self.assertEqual(build_parser().parse_args([]).sleep, 10.0)

    def test_research_defaults_to_price_cache_only(self):
        args = build_parser().parse_args([])

        self.assertTrue(args.price_cache_only)
        self.assertFalse(args.cache_only)

    def test_backtest_cli_defaults_and_overrides(self):
        args = build_parser().parse_args([])

        self.assertTrue(args.run_backtest)
        self.assertEqual(args.backtest_top_n, 50)
        self.assertEqual(args.transaction_cost_rate, 0.002)

        disabled = build_parser().parse_args(
            ["--no-run-backtest", "--backtest-top-n", "20", "--transaction-cost-rate", "0.001"]
        )
        self.assertFalse(disabled.run_backtest)
        self.assertEqual(disabled.backtest_top_n, 20)
        self.assertEqual(disabled.transaction_cost_rate, 0.001)

    def test_fetch_missing_price_flag_allows_research_price_refresh(self):
        args = build_parser().parse_args(["--fetch-missing-price"])

        self.assertFalse(args.price_cache_only)

    def test_db_cache_quality_metadata_tolerates_empty_sync_summary(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            summary_path = root / "data" / "processed" / "db_sync_summary.csv"
            summary_path.parent.mkdir(parents=True)
            summary_path.write_text("\ufeff\r\n", encoding="utf-8")

            metadata = db_cache_quality_metadata(root)

            self.assertEqual(metadata["db_sync_summary_status"], "empty")
            self.assertNotIn("sync_counts", metadata)

    def test_cache_only_run_does_not_call_akshare(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            price_dir = root / "data" / "cache" / "price"
            price_dir.mkdir(parents=True)
            dates = pd.date_range("2025-01-01", periods=160, freq="D")
            pd.DataFrame(
                {
                    "date": dates,
                    "close": range(100, 260),
                    "amount": [1000.0] * len(dates),
                    "turnover": [0.5] * len(dates),
                }
            ).to_csv(price_dir / "600519.csv", index=False, encoding="utf-8-sig")
            argv = [
                "run_research.py",
                "--symbols",
                "600519",
                "--cache-only",
                "--years",
                "1",
                "--sleep",
                "0",
                "--root",
                str(root),
            ]

            with patch.object(sys, "argv", argv), patch(
                "aq_factor_lab.data.ak.stock_zh_a_hist",
                side_effect=AssertionError("AkShare price should not be called"),
            ), patch(
                "aq_factor_lab.data.ak.stock_cash_flow_sheet_by_report_em",
                side_effect=AssertionError("AkShare cashflow should not be called"),
            ), patch(
                "aq_factor_lab.data.ak.stock_profit_sheet_by_report_em",
                side_effect=AssertionError("AkShare profit should not be called"),
            ), patch(
                "aq_factor_lab.data.ak.stock_individual_fund_flow",
                side_effect=AssertionError("AkShare moneyflow should not be called"),
            ):
                main()

            self.assertTrue((root / "data" / "processed" / "factor_panel.csv").exists())

    def test_cache_only_moneyflow_missing_does_not_create_per_symbol_failures(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            price_dir = root / "data" / "cache" / "price"
            cashflow_dir = root / "data" / "cache" / "cashflow"
            profit_dir = root / "data" / "cache" / "profit"
            price_dir.mkdir(parents=True)
            cashflow_dir.mkdir(parents=True)
            profit_dir.mkdir(parents=True)
            dates = pd.date_range("2025-01-01", periods=160, freq="D")
            pd.DataFrame(
                {
                    "date": dates,
                    "close": range(100, 260),
                    "amount": [1000.0] * len(dates),
                    "turnover": [0.5] * len(dates),
                }
            ).to_csv(price_dir / "600519.csv", index=False, encoding="utf-8-sig")
            pd.DataFrame(
                {
                    "report_date": ["2024-03-31"],
                    "announce_date": ["2024-04-30"],
                    "operating_cashflow": [100.0],
                }
            ).to_csv(cashflow_dir / "600519.csv", index=False, encoding="utf-8-sig")
            pd.DataFrame(
                {
                    "report_date": ["2024-03-31"],
                    "announce_date": ["2024-04-30"],
                    "revenue": [200.0],
                    "parent_net_profit": [50.0],
                }
            ).to_csv(profit_dir / "600519.csv", index=False, encoding="utf-8-sig")
            argv = [
                "run_research.py",
                "--symbols",
                "600519",
                "--cache-only",
                "--years",
                "1",
                "--sleep",
                "0",
                "--root",
                str(root),
            ]

            with patch.object(sys, "argv", argv):
                main()

            failures = pd.read_csv(root / "data" / "processed" / "fetch_failures.csv")
            self.assertNotIn("moneyflow", set(failures.get("endpoint", pd.Series(dtype=str)).astype(str)))


if __name__ == "__main__":
    unittest.main()
