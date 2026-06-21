from __future__ import annotations

import unittest
from datetime import date
from http.client import RemoteDisconnected
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pandas as pd
import requests

from aq_factor_lab.config import ResearchConfig
from aq_factor_lab.data import (
    AkShareClient,
    moneyflow_empty,
    normalize_price,
    normalize_universe,
    safe_fetch,
)


class AkShareDataTests(unittest.TestCase):
    def test_safe_fetch_retries_network_errors_with_backoff_and_random_sleep(self):
        fetcher = Mock(
            side_effect=[
                RemoteDisconnected("closed"),
                requests.exceptions.SSLError("bad record mac"),
                pd.DataFrame({"ok": [1]}),
            ]
        )

        with patch("aq_factor_lab.data.random.uniform", return_value=0.2), patch(
            "aq_factor_lab.data.time.sleep"
        ) as sleep:
            out = safe_fetch(
                "price 600519",
                fetcher,
                max_attempts=3,
                base_sleep=0.5,
                random_sleep_range=(0.1, 0.3),
            )

        self.assertEqual(fetcher.call_count, 3)
        self.assertEqual(out.loc[0, "ok"], 1)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [0.7, 1.2])

    def test_safe_fetch_logs_and_raises_clear_error_after_retries(self):
        fetcher = Mock(side_effect=requests.exceptions.ConnectionError("eof"))
        logger = Mock()

        with patch("aq_factor_lab.data.time.sleep"):
            with self.assertRaises(RuntimeError) as exc:
                safe_fetch("price 600519", fetcher, max_attempts=2, logger=logger)

        self.assertEqual(fetcher.call_count, 2)
        self.assertIn("price 600519 AkShare request failed after 2 attempts", str(exc.exception))
        logger.warning.assert_called()

    def test_universe_uses_akshare_spot_endpoint(self):
        with TemporaryDirectory() as tmp:
            raw = pd.DataFrame(
                {
                    "code": ["600519"],
                    "name": ["贵州茅台"],
                    "market_cap": [2000000000000],
                    "float_market_cap": [1800000000000],
                }
            )

            with patch("aq_factor_lab.data.ak.stock_zh_a_spot_em", return_value=raw) as ak_spot:
                universe = make_client(tmp).universe()

            ak_spot.assert_called_once_with()
            self.assertEqual(list(universe["code"]), ["600519"])

    def test_normalize_universe_rejects_non_six_digit_codes(self):
        raw = pd.DataFrame(
            {
                "code": ["600519", "60086_L", "60519_LPX", "SZ_000001"],
                "name": ["贵州茅台", "bad1", "bad2", "平安银行"],
            }
        )

        universe = normalize_universe(raw)

        self.assertEqual(list(universe["code"]), ["000001", "600519"])

    def test_universe_falls_back_to_cache_when_akshare_spot_fails(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "data" / "cache"
            cache_dir.mkdir(parents=True)
            pd.DataFrame(
                {
                    "code": ["600519"],
                    "name": ["贵州茅台"],
                    "market_cap": [2000000000000],
                    "float_market_cap": [1800000000000],
                }
            ).to_csv(cache_dir / "universe_spot.csv", index=False, encoding="utf-8-sig")
            client = make_client(tmp)

            with patch("aq_factor_lab.data.ak.stock_zh_a_spot_em") as ak_spot:
                ak_spot.side_effect = RuntimeError("spot failed")
                universe = client.universe()

            self.assertEqual(list(universe["code"]), ["600519"])
            self.assertEqual(client.failures[0]["endpoint"], "universe")

    def test_price_history_uses_akshare_hist_with_timeout_and_qfq(self):
        with TemporaryDirectory() as tmp:
            raw = price_raw()
            client = make_client(tmp)

            with patch("aq_factor_lab.data.ak.stock_zh_a_hist", return_value=raw) as ak_hist:
                price = client.price_history("600519")

            ak_hist.assert_called_once_with(
                symbol="600519",
                period="daily",
                start_date="20250101",
                end_date="20251231",
                adjust="qfq",
                timeout=20,
            )
            self.assertEqual(price.loc[0, "close"], 101.5)

    def test_price_history_falls_back_to_cache_when_akshare_fails(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "data" / "cache" / "price"
            cache_dir.mkdir(parents=True)
            price_raw().to_csv(cache_dir / "600519.csv", index=False, encoding="utf-8-sig")
            client = make_client(tmp)

            with patch("aq_factor_lab.data.ak.stock_zh_a_hist") as ak_hist:
                ak_hist.side_effect = RuntimeError("hist failed")
                price = client.price_history("600519")

            self.assertEqual(price.loc[0, "close"], 101.5)
            self.assertEqual(client.failures[0]["endpoint"], "price")
            self.assertEqual(client.failures[0]["code"], "600519")
            self.assertEqual(client.failures[0]["attempts"], 5)
            self.assertTrue(client.failures[0]["cache_fallback"])
            summary = client.fetch_summary_frame().set_index("endpoint")
            self.assertEqual(summary.loc["price", "cache_fallback"], 1)

    def test_price_history_uses_existing_cache_without_calling_akshare(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "data" / "cache" / "price"
            cache_dir.mkdir(parents=True)
            price_raw().to_csv(cache_dir / "600519.csv", index=False, encoding="utf-8-sig")
            client = make_client(tmp, use_cache=True)

            with patch("aq_factor_lab.data.ak.stock_zh_a_hist") as ak_hist:
                price = client.price_history("600519")

            ak_hist.assert_not_called()
            self.assertEqual(price.loc[0, "close"], 101.5)

    def test_price_history_reads_db_style_cache_with_leading_zero_code(self):
        with TemporaryDirectory() as tmp:
            cache_dir = Path(tmp) / "data" / "cache" / "price"
            cache_dir.mkdir(parents=True)
            pd.DataFrame(
                {
                    "db_symbol": ["SZ_000001"],
                    "date": ["2026-06-15"],
                    "close": [11.06],
                    "amount": [1711561286.57],
                    "turnover": [1.23],
                    "updated_at": ["2026-06-15 07:45:56"],
                    "code": ["000001"],
                    "exchange": ["SZ"],
                }
            ).to_csv(cache_dir / "000001.csv", index=False, encoding="utf-8-sig")
            client = make_client(tmp, use_cache=True)

            with patch("aq_factor_lab.data.ak.stock_zh_a_hist") as ak_hist:
                price = client.price_history("000001")

            ak_hist.assert_not_called()
            self.assertEqual(price.loc[0, "close"], 11.06)
            self.assertEqual(price.loc[0, "turnover"], 1.23)

    def test_normalize_price_preserves_market_cap_columns(self):
        raw = pd.DataFrame(
            {
                "date": ["2026-06-15"],
                "close": [11.06],
                "amount": [1711561286.57],
                "turnover": [1.23],
                "total_market_cap": [110000000000.0],
                "circulating_market_cap": [90000000000.0],
            }
        )

        price = normalize_price(raw)

        self.assertEqual(price.loc[0, "total_market_cap"], 110000000000.0)
        self.assertEqual(price.loc[0, "circulating_market_cap"], 90000000000.0)

    def test_normalize_price_preserves_high_and_low_when_available(self):
        raw = pd.DataFrame(
            {
                "date": ["2026-06-15"],
                "close": [11.06],
                "high": [11.22],
                "low": [10.91],
                "amount": [1711561286.57],
            }
        )

        price = normalize_price(raw)

        self.assertEqual(price.loc[0, "high"], 11.22)
        self.assertEqual(price.loc[0, "low"], 10.91)

    def test_price_history_cache_only_missing_file_does_not_call_akshare(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp, price_cache_only=True)

            with patch("aq_factor_lab.data.ak.stock_zh_a_hist") as ak_hist:
                with self.assertRaises(FileNotFoundError):
                    client.price_history("600519")

            ak_hist.assert_not_called()

    def test_cache_only_missing_optional_endpoint_returns_empty_without_akshare(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp, cache_only=True)

            with patch("aq_factor_lab.data.ak.stock_individual_fund_flow") as ak_flow:
                out = client._optional_endpoint(
                    "600519",
                    "600519",
                    "moneyflow",
                    client.moneyflow_history,
                    moneyflow_empty(),
                )

            ak_flow.assert_not_called()
            self.assertTrue(out.empty)

    def test_precache_price_fetches_only_price_and_writes_cache(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp, use_cache=True, price_cache_only=False)

            with patch("aq_factor_lab.data.ak.stock_zh_a_hist", return_value=price_raw()) as ak_hist:
                ok = client.precache_price("600519", "600519")

            self.assertTrue(ok)
            ak_hist.assert_called_once()
            self.assertTrue((Path(tmp) / "data" / "cache" / "price" / "600519.csv").exists())

    def test_precache_price_failure_records_failed_symbol(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp, price_cache_only=False)
            client._retry_base_sleep = 0

            with patch("aq_factor_lab.data.ak.stock_zh_a_hist") as ak_hist:
                ak_hist.side_effect = requests.ConnectionError("eof")
                ok = client.precache_price("600519", "600519")

            self.assertFalse(ok)
            failed_symbols = client.failed_symbols_frame()
            self.assertEqual(list(failed_symbols["code"]), ["600519"])
            self.assertEqual(list(failed_symbols["endpoint"]), ["price"])

    def test_moneyflow_history_uses_akshare_individual_fund_flow(self):
        with TemporaryDirectory() as tmp:
            raw = pd.DataFrame(
                {
                    "date": ["2025-01-02"],
                    "main_net_inflow": [1000.0],
                    "main_net_pct": [1.1],
                    "close": [101.5],
                }
            )
            client = make_client(tmp)

            with patch("aq_factor_lab.data.ak.stock_individual_fund_flow", return_value=raw) as ak_flow:
                moneyflow = client.moneyflow_history("600519")

            ak_flow.assert_called_once_with(stock="600519", market="sh")
            self.assertEqual(moneyflow.loc[0, "main_net_inflow"], 1000.0)

    def test_akshare_retry_wrapper_retries_transient_failure(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp)
            client._retry_base_sleep = 0
            fetcher = Mock(
                side_effect=[
                    requests.ConnectionError("eof"),
                    requests.Timeout("timeout"),
                    pd.DataFrame({"ok": [1]}),
                ]
            )

            out = client._akshare_fetch("price", "600519", fetcher)

            self.assertEqual(fetcher.call_count, 3)
            self.assertEqual(out.loc[0, "ok"], 1)

    def test_price_endpoint_retries_five_times(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp)
            client._retry_base_sleep = 0
            fetcher = Mock(
                side_effect=[
                    requests.ConnectionError("eof"),
                    requests.ConnectionError("eof"),
                    requests.Timeout("timeout"),
                    requests.ConnectionError("eof"),
                    pd.DataFrame({"ok": [1]}),
                ]
            )

            out = client._akshare_fetch("price", "600519", fetcher)

            self.assertEqual(fetcher.call_count, 5)
            self.assertEqual(out.loc[0, "ok"], 1)
            self.assertEqual(client.fetch_stats["price"]["success"], 1)

    def test_non_price_endpoint_retries_three_times(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp)
            client._retry_base_sleep = 0
            fetcher = Mock(
                side_effect=[
                    requests.ConnectionError("eof"),
                    requests.Timeout("timeout"),
                    pd.DataFrame({"ok": [1]}),
                ]
            )

            out = client._akshare_fetch("moneyflow", "600519", fetcher)

            self.assertEqual(fetcher.call_count, 3)
            self.assertEqual(out.loc[0, "ok"], 1)
            self.assertEqual(client.fetch_stats["moneyflow"]["success"], 1)

    def test_retry_wrapper_sleeps_for_backoff_and_request_throttle(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp, sleep_seconds=1.0)
            client._retry_base_sleep = 0.5
            fetcher = Mock(
                side_effect=[
                    requests.ConnectionError("eof"),
                    pd.DataFrame({"ok": [1]}),
                ]
            )

            with patch("aq_factor_lab.data.random.uniform", return_value=0.25), patch(
                "aq_factor_lab.data.time.sleep"
            ) as sleep:
                client._akshare_fetch("moneyflow", "600519", fetcher)

            durations = [args[0][0] for args in sleep.call_args_list]
            self.assertEqual(fetcher.call_count, 2)
            self.assertIn(0.75, durations)
            self.assertEqual(durations.count(1.0), 2)

    def test_symbol_delay_uses_randomized_sleep(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp, sleep_seconds=1.0)

            with patch("aq_factor_lab.data.random.uniform", return_value=1.3) as uniform, patch(
                "aq_factor_lab.data.time.sleep"
            ) as sleep:
                client.sleep_between_symbols()

            sleep.assert_called_once_with(1.3)
            uniform.assert_called_once_with(0.5, 1.5)

    def test_default_symbol_delay_uses_ten_second_pacing_window(self):
        with TemporaryDirectory() as tmp:
            config = ResearchConfig(
                root_dir=Path(tmp),
                start_date=date(2025, 1, 1),
                end_date=date(2025, 12, 31),
                use_cache=False,
            )
            client = AkShareClient(config)

            with patch("aq_factor_lab.data.random.uniform", return_value=12.0) as uniform, patch(
                "aq_factor_lab.data.time.sleep"
            ) as sleep:
                client.sleep_between_symbols()

            sleep.assert_called_once_with(12.0)
            uniform.assert_called_once_with(5.0, 15.0)

    def test_price_failure_without_cache_marks_required_skip(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp)
            client._retry_base_sleep = 0
            row = pd.Series(
                {
                    "code": "600519",
                    "name": "600519",
                    "industry": None,
                    "market_cap": None,
                    "float_market_cap": None,
                }
            )

            with patch("aq_factor_lab.data.ak.stock_zh_a_hist") as ak_hist:
                ak_hist.side_effect = requests.ConnectionError("eof")
                with self.assertRaises(RuntimeError):
                    client.stock_data(row)

            self.assertEqual(ak_hist.call_count, 5)
            summary = client.fetch_summary_frame().set_index("endpoint")
            self.assertEqual(summary.loc["price", "failed"], 1)
            self.assertEqual(summary.loc["price", "skipped_required_price"], 1)
            self.assertFalse(client.failures[0]["cache_fallback"])
            failed_symbols = client.failed_symbols_frame()
            self.assertEqual(list(failed_symbols["code"]), ["600519"])
            self.assertEqual(list(failed_symbols["endpoint"]), ["price"])

    def test_optional_moneyflow_failure_records_endpoint_and_returns_empty_frame(self):
        with TemporaryDirectory() as tmp:
            client = make_client(tmp)
            row = pd.Series(
                {
                    "code": "600519",
                    "name": "600519",
                    "industry": None,
                    "market_cap": None,
                    "float_market_cap": None,
                }
            )
            client.price_history = Mock(
                return_value=pd.DataFrame(
                    {"date": pd.to_datetime(["2025-01-02"]), "close": [101.5]}
                )
            )
            client.cashflow_statement = Mock(return_value=pd.DataFrame())
            client.profit_statement = Mock(return_value=pd.DataFrame())
            client.moneyflow_history = Mock(side_effect=requests.ConnectionError("eof"))

            stock = client.stock_data(row)

            self.assertTrue(stock.moneyflow.empty)
            self.assertEqual(len(client.failures), 1)
            self.assertEqual(client.failures[0]["endpoint"], "moneyflow")
            self.assertEqual(client.failures[0]["code"], "600519")

    def test_normalize_universe_excludes_pt_names(self):
        raw = pd.DataFrame(
            {
                "code": ["000001", "000003"],
                "name": ["平安银行", "PT金田A"],
                "market_cap": [200000000000, 1],
                "float_market_cap": [190000000000, 1],
            }
        )

        out = normalize_universe(raw)

        self.assertEqual(list(out["code"]), ["000001"])


def price_raw() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "date": ["2025-01-02"],
            "close": [101.5],
            "amount": [678900.0],
            "turnover": [0.66],
        }
    )


def make_client(
    root: str,
    sleep_seconds: float = 0,
    use_cache: bool = False,
    price_cache_only: bool = False,
    cache_only: bool = False,
) -> AkShareClient:
    config = ResearchConfig(
        root_dir=Path(root),
        start_date=date(2025, 1, 1),
        end_date=date(2025, 12, 31),
        sleep_seconds=sleep_seconds,
        use_cache=use_cache,
        price_cache_only=price_cache_only,
        cache_only=cache_only,
    )
    return AkShareClient(config)


if __name__ == "__main__":
    unittest.main()
