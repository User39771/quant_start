from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pandas as pd
import requests

from aq_factor_lab.data_layer import (
    CacheMissError,
    DataLayerConfig,
    DataQualityError,
    PublicDataFetchError,
    RequestBudgetExceeded,
    configure_data_layer,
    get_concept_members,
    get_daily_price,
    get_index_price,
    get_stock_universe,
)
from aq_factor_lab.data_layer.akshare_client import AkSharePublicClient
from aq_factor_lab.data_layer.cache import build_query_payload, query_key


def stock_raw() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-06-01", "2026-06-02"],
            "开盘": [10.0, 10.5],
            "最高": [11.0, 11.5],
            "最低": [9.5, 10.1],
            "收盘": [10.8, 11.2],
            "成交量": [1234, 2000],
            "成交额": [1234000.0, 2500000.0],
            "换手率": [1.2, 1.4],
        }
    )


def index_raw() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "日期": ["2026-06-01"],
            "开盘": [3000.0],
            "最高": [3010.0],
            "最低": [2990.0],
            "收盘": [3005.0],
            "成交量": [500],
            "成交额": [300000000.0],
        }
    )


class DataLayerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)
        configure_data_layer(
            DataLayerConfig(
                root_dir=self.root,
                sleep_seconds=0,
                max_requests_per_run=20,
            )
        )

    def tearDown(self) -> None:
        configure_data_layer(None)
        self.tmp.cleanup()

    def test_daily_price_fetches_qfq_adjusted_ohlcv_and_writes_manifest(self):
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            ak_module.__version__ = "1.2.3"
            ak_module.stock_zh_a_hist.return_value = stock_raw()

            out = get_daily_price("600519", "2026-06-01", "2026-06-02", adjusted=True)

        ak_module.stock_zh_a_hist.assert_called_once_with(
            symbol="600519",
            period="daily",
            start_date="20260601",
            end_date="20260602",
            adjust="qfq",
            timeout=20,
        )
        self.assertEqual(
            list(out.columns),
            [
                "symbol",
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "turnover",
                "adjusted",
                "source",
            ],
        )
        self.assertEqual(out.loc[0, "symbol"], "600519")
        self.assertEqual(out.loc[0, "volume"], 123400.0)
        self.assertEqual(out.loc[0, "amount"], 1234000.0)
        self.assertTrue(bool(out.loc[0, "adjusted"]))
        self.assertNotIn("fetched_at", out.columns)

        manifests = list((self.root / "data" / "cache" / "public" / "manifests").rglob("*.json"))
        self.assertEqual(len(manifests), 1)
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
        self.assertEqual(manifest["akshare_version"], "1.2.3")
        self.assertEqual(manifest["endpoint"], "daily_price")
        self.assertEqual(manifest["adjust_mode"], "qfq")
        self.assertEqual(manifest["raw_row_count"], 2)
        self.assertEqual(manifest["clean_row_count"], 2)
        self.assertIn("query_key", manifest)

    def test_daily_price_raw_uses_empty_adjust_parameter(self):
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            ak_module.__version__ = "1.2.3"
            ak_module.stock_zh_a_hist.return_value = stock_raw()

            out = get_daily_price("600519", "2026-06-01", "2026-06-02", adjusted=False)

        self.assertEqual(ak_module.stock_zh_a_hist.call_args.kwargs["adjust"], "")
        self.assertFalse(bool(out.loc[0, "adjusted"]))

    def test_exact_clean_cache_hit_does_not_call_akshare_or_refresh_manifest(self):
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            ak_module.__version__ = "1.2.3"
            ak_module.stock_zh_a_hist.return_value = stock_raw()
            first = get_daily_price("600519", "2026-06-01", "2026-06-02", adjusted=True)

        manifest_path = next(
            (self.root / "data" / "cache" / "public" / "manifests").rglob("*.json")
        )
        before = manifest_path.read_text(encoding="utf-8")

        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            cached = get_daily_price("600519", "2026-06-01", "2026-06-02", adjusted=True)

        ak_module.stock_zh_a_hist.assert_not_called()
        self.assertEqual(before, manifest_path.read_text(encoding="utf-8"))
        pd.testing.assert_frame_equal(first, cached)

    def test_cache_only_miss_and_dry_run_do_not_call_akshare(self):
        configure_data_layer(DataLayerConfig(root_dir=self.root, cache_only=True, sleep_seconds=0))
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            with self.assertRaises(CacheMissError):
                get_daily_price("600519", "2026-06-01", "2026-06-02")
        ak_module.stock_zh_a_hist.assert_not_called()

        configure_data_layer(DataLayerConfig(root_dir=self.root, dry_run=True, sleep_seconds=0))
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            out = get_daily_price("600519", "2026-06-01", "2026-06-02")
        ak_module.stock_zh_a_hist.assert_not_called()
        self.assertTrue(out.empty)
        self.assertIn("adjusted", out.columns)

    def test_request_budget_zero_blocks_live_request(self):
        configure_data_layer(
            DataLayerConfig(root_dir=self.root, max_requests_per_run=0, sleep_seconds=0)
        )
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            with self.assertRaises(RequestBudgetExceeded):
                get_daily_price("600519", "2026-06-01", "2026-06-02")
        ak_module.stock_zh_a_hist.assert_not_called()

    def test_each_retry_attempt_consumes_request_budget(self):
        configure_data_layer(
            DataLayerConfig(
                root_dir=self.root,
                max_requests_per_run=1,
                max_attempts=2,
                sleep_seconds=0,
            )
        )
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            ak_module.stock_zh_a_hist.side_effect = requests.ConnectionError("reset")
            with self.assertRaises(RequestBudgetExceeded):
                get_daily_price("600519", "2026-06-01", "2026-06-02")

        self.assertEqual(ak_module.stock_zh_a_hist.call_count, 1)

    def test_final_fetch_failure_writes_failure_log(self):
        configure_data_layer(
            DataLayerConfig(
                root_dir=self.root,
                max_requests_per_run=5,
                max_attempts=2,
                sleep_seconds=0,
            )
        )
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            ak_module.stock_zh_a_hist.side_effect = requests.ConnectionError("reset")
            with self.assertRaises(PublicDataFetchError):
                get_daily_price("600519", "2026-06-01", "2026-06-02")

        failure_path = (
            self.root / "data" / "cache" / "public" / "logs" / "data_layer_failures.csv"
        )
        failures = pd.read_csv(failure_path)
        self.assertEqual(failures.loc[0, "endpoint"], "daily_price")
        self.assertEqual(failures.loc[0, "error_type"], "ConnectionError")

    def test_unparsable_price_dates_raise_data_quality_error(self):
        bad = stock_raw()
        bad.loc[0, "日期"] = "not-a-date"
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            ak_module.stock_zh_a_hist.return_value = bad
            with self.assertRaises(DataQualityError):
                get_daily_price("600519", "2026-06-01", "2026-06-02")

    def test_index_price_uses_index_endpoint_and_same_volume_convention(self):
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            ak_module.__version__ = "1.2.3"
            ak_module.index_zh_a_hist.return_value = index_raw()

            out = get_index_price("000001", "2026-06-01", "2026-06-01")

        ak_module.index_zh_a_hist.assert_called_once_with(
            symbol="000001",
            period="daily",
            start_date="20260601",
            end_date="20260601",
        )
        self.assertEqual(
            list(out.columns),
            [
                "index_code",
                "symbol",
                "date",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "amount",
                "turnover",
                "adjusted",
                "source",
            ],
        )
        self.assertEqual(out.loc[0, "index_code"], "000001")
        self.assertEqual(out.loc[0, "symbol"], "000001")
        self.assertEqual(out.loc[0, "volume"], 50000.0)
        self.assertFalse(bool(out.loc[0, "adjusted"]))
        self.assertEqual(out.loc[0, "source"], "akshare.index_zh_a_hist")

    def test_cache_key_uses_normalized_sorted_filters(self):
        config = DataLayerConfig(root_dir=self.root)
        left = build_query_payload(
            endpoint="stock_universe",
            config=config,
            requested_date="2026-06-01",
            filters={"industry": "AI", "min_amount": 50000000},
        )
        right = build_query_payload(
            endpoint="stock_universe",
            config=config,
            requested_date="2026-06-01",
            filters={"min_amount": 50000000, "industry": "AI"},
        )

        self.assertEqual(query_key(left), query_key(right))

    def test_universe_optional_metadata_warnings_and_current_snapshot(self):
        raw = pd.DataFrame({"代码": ["600519"], "名称": ["贵州茅台"]})
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            ak_module.__version__ = "1.2.3"
            ak_module.stock_zh_a_spot_em.return_value = raw

            out = get_stock_universe("2026-06-01")

        self.assertEqual(out.loc[0, "symbol"], "600519")
        self.assertEqual(out.loc[0, "name"], "贵州茅台")
        self.assertEqual(out.loc[0, "asof_quality"], "current_snapshot")
        warning_path = (
            self.root
            / "data"
            / "cache"
            / "public"
            / "logs"
            / "data_layer_quality_warnings.csv"
        )
        warnings = pd.read_csv(warning_path)
        self.assertIn("missing_optional_universe_metadata", set(warnings["warning_type"]))

    def test_concept_members_date_is_snapshot_and_requested_date_is_metadata(self):
        raw = pd.DataFrame({"代码": ["300750"], "名称": ["宁德时代"]})
        with patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module:
            ak_module.__version__ = "1.2.3"
            ak_module.stock_board_concept_cons_em.return_value = raw

            out = get_concept_members("商业航天", date="2024-01-31")

        ak_module.stock_board_concept_cons_em.assert_called_once_with(symbol="商业航天")
        self.assertEqual(out.loc[0, "concept_name"], "商业航天")
        self.assertEqual(out.loc[0, "symbol"], "300750")
        self.assertEqual(out.loc[0, "requested_date"], "2024-01-31")
        self.assertEqual(out.loc[0, "asof_quality"], "current_snapshot")

    def test_concept_names_falls_back_to_eastmoney_http(self):
        client = AkSharePublicClient()
        with (
            patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module,
            patch.object(client, "_eastmoney_clist") as clist,
        ):
            ak_module.stock_board_concept_name_em.side_effect = RuntimeError("https blocked")
            clist.return_value = pd.DataFrame(
                [{"f12": "BK0800", "f14": "人工智能"}],
            )

            out = client.concept_names()

        self.assertEqual(out.loc[0, "板块代码"], "BK0800")
        self.assertEqual(out.loc[0, "板块名称"], "人工智能")

    def test_concept_members_code_falls_back_to_eastmoney_http(self):
        client = AkSharePublicClient()
        with (
            patch("aq_factor_lab.data_layer.akshare_client.ak") as ak_module,
            patch.object(client, "_eastmoney_clist") as clist,
        ):
            ak_module.stock_board_concept_cons_em.side_effect = RuntimeError("https blocked")
            clist.return_value = pd.DataFrame(
                [{"f12": "300750", "f14": "宁德时代"}],
            )

            out = client.concept_members("BK0800")

        self.assertEqual(out.loc[0, "code"], "300750")
        self.assertEqual(out.loc[0, "name"], "宁德时代")

    def test_eastmoney_clist_uses_powershell_when_python_http_is_blocked(self):
        client = AkSharePublicClient()
        completed = Mock(
            returncode=0,
            stdout=(
                '{"rc":0,"data":{"total":1,'
                '"diff":[{"f12":"BK0800","f14":"人工智能"}]}}'
            ),
            stderr="",
        )
        with (
            patch("requests.Session.get", side_effect=requests.ConnectionError("blocked")),
            patch("subprocess.run", return_value=completed) as run,
        ):
            out = client._eastmoney_clist(fs="m:90 t:3 f:!50", fields="f12,f14")

        self.assertEqual(out.loc[0, "f12"], "BK0800")
        self.assertEqual(out.loc[0, "f14"], "人工智能")
        self.assertTrue(run.called)


if __name__ == "__main__":
    unittest.main()
