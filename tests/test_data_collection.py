from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

import pandas as pd

from aq_factor_lab.data_collection import (
    DataCollectionError,
    ThematicCollectionConfig,
    collect_thematic_dataset,
)
from aq_factor_lab.data_collection.cli import load_config, main


def concept_frame(rows: list[tuple[str, str]], concept_name: str = "concept") -> pd.DataFrame:
    return pd.DataFrame(
        {
            "concept_name": concept_name,
            "symbol": [row[0] for row in rows],
            "name": [row[1] for row in rows],
            "date": ["2026-06-23"] * len(rows),
            "requested_date": [""] * len(rows),
            "asof_quality": ["current_snapshot"] * len(rows),
            "source": ["mock"] * len(rows),
        }
    )


def price_frame(symbol: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": [symbol],
            "date": [pd.Timestamp("2026-06-01")],
            "open": [10.0],
            "high": [11.0],
            "low": [9.5],
            "close": [10.5],
            "volume": [1000.0],
            "amount": [100000.0],
            "turnover": [1.0],
            "adjusted": [True],
            "source": ["mock"],
        }
    )


def index_frame(index_code: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "index_code": [index_code],
            "symbol": [index_code],
            "date": [pd.Timestamp("2026-06-01")],
            "open": [3000.0],
            "high": [3010.0],
            "low": [2990.0],
            "close": [3005.0],
            "volume": [1000.0],
            "amount": [100000000.0],
            "turnover": [pd.NA],
            "adjusted": [False],
            "source": ["mock"],
        }
    )


class ThematicDataCollectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def config(self, **overrides) -> ThematicCollectionConfig:
        payload = {
            "theme_name": "commercial aerospace",
            "concept_names": ["concept_a", "concept_b"],
            "start": "2026-06-01",
            "end": "2026-06-05",
            "output_root": self.root,
            "benchmark_indices": ["000001"],
            "max_symbols": 3,
            "adjusted": True,
            "cache_only": False,
            "dry_run": False,
            "max_requests_per_run": 50,
            "sleep_seconds": 0,
        }
        payload.update(overrides)
        return ThematicCollectionConfig(**payload)

    @patch("aq_factor_lab.data_collection.thematic.data_layer")
    def test_collect_unions_deduplicates_sorts_and_caps_symbols(self, data_layer):
        data_layer.get_concept_members.side_effect = [
            concept_frame([("300750", "宁德时代"), ("600519", "贵州茅台")], "concept_a"),
            concept_frame([("000001", "平安银行"), ("300750", "宁德时代")], "concept_b"),
        ]
        data_layer.get_stock_universe.return_value = pd.DataFrame(
            {
                "symbol": ["000001", "300750", "600519"],
                "name": ["平安银行", "宁德时代", "贵州茅台"],
                "exchange": ["SZ", "SZ", "SH"],
                "market": [pd.NA, pd.NA, pd.NA],
                "industry": ["bank", "battery", "liquor"],
                "list_date": [pd.NaT, pd.NaT, pd.NaT],
                "delist_date": [pd.NaT, pd.NaT, pd.NaT],
                "listing_status": [pd.NA, pd.NA, pd.NA],
                "asof_quality": ["current_snapshot"] * 3,
                "source": ["mock"] * 3,
            }
        )
        data_layer.get_daily_price.side_effect = lambda symbol, *_args, **_kwargs: price_frame(symbol)
        data_layer.get_index_price.side_effect = lambda index_code, *_args: index_frame(index_code)

        result = collect_thematic_dataset(self.config(max_symbols=2))

        self.assertEqual(result.symbols_requested, 2)
        self.assertEqual(result.symbols_succeeded, 2)
        self.assertEqual(result.symbols_failed, 0)
        self.assertEqual(
            [call.args[0] for call in data_layer.get_daily_price.call_args_list],
            ["000001", "300750"],
        )
        manifest = json.loads((result.output_dir / "collection_manifest.json").read_text("utf-8"))
        self.assertEqual(manifest["selected_symbols"], ["000001", "300750"])
        self.assertIn("current_snapshot", manifest["membership_warning"])
        self.assertTrue((result.output_dir / "concept_members_snapshot.csv").exists())
        self.assertTrue((result.output_dir / "stock_universe_snapshot.csv").exists())
        self.assertTrue((result.output_dir / "daily_prices.csv").exists())
        self.assertTrue((result.output_dir / "index_prices.csv").exists())
        self.assertTrue((result.output_dir / "failures.csv").exists())

    @patch("aq_factor_lab.data_collection.thematic.data_layer")
    def test_failed_symbol_price_request_is_recorded_and_collection_continues(self, data_layer):
        data_layer.get_concept_members.return_value = concept_frame(
            [("000001", "平安银行"), ("300750", "宁德时代")],
            "concept_a",
        )
        data_layer.get_stock_universe.return_value = pd.DataFrame()

        def fetch_price(symbol: str, *_args, **_kwargs):
            if symbol == "300750":
                raise RuntimeError("price blocked")
            return price_frame(symbol)

        data_layer.get_daily_price.side_effect = fetch_price
        data_layer.get_index_price.side_effect = lambda index_code, *_args: index_frame(index_code)

        result = collect_thematic_dataset(self.config(concept_names=["concept_a"]))

        self.assertEqual(result.symbols_succeeded, 1)
        self.assertEqual(result.symbols_failed, 1)
        failures = pd.read_csv(result.output_dir / "failures.csv")
        self.assertIn("daily_price", set(failures["stage"]))
        self.assertIn("300750", set(failures["symbol"].astype(str)))

    @patch("aq_factor_lab.data_collection.thematic.data_layer")
    def test_no_symbols_found_raises_data_collection_error(self, data_layer):
        data_layer.get_concept_members.return_value = concept_frame([], "concept_a")

        with self.assertRaises(DataCollectionError):
            collect_thematic_dataset(self.config(concept_names=["concept_a"], benchmark_indices=None))

    @patch("aq_factor_lab.data_collection.thematic.data_layer")
    def test_dry_run_configures_data_layer_and_writes_minimal_outputs(self, data_layer):
        result = collect_thematic_dataset(
            self.config(dry_run=True, benchmark_indices=["000001"], max_symbols=5)
        )

        data_layer.configure_data_layer.assert_called_once()
        configured = data_layer.configure_data_layer.call_args.args[0]
        self.assertTrue(configured.dry_run)
        self.assertEqual(configured.max_requests_per_run, 50)
        data_layer.get_concept_members.assert_not_called()
        self.assertEqual(result.run_id, "dry_run")
        self.assertTrue((result.output_dir / "run_config.json").exists())
        self.assertTrue((result.output_dir / "collection_manifest.json").exists())
        self.assertTrue((result.output_dir / "daily_prices.csv").exists())
        self.assertTrue((result.output_dir / "failures.csv").exists())

    def test_cli_config_loading_and_overrides(self):
        config_path = self.root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "theme_name": "sample_theme",
                    "concept_names": ["concept_a"],
                    "start": "2026-06-01",
                    "end": "2026-06-05",
                    "output_root": str(self.root),
                    "benchmark_indices": ["000001"],
                    "max_symbols": 5,
                    "sleep_seconds": 10,
                    "max_requests_per_run": 20,
                }
            ),
            encoding="utf-8",
        )

        config = load_config(
            config_path,
            dry_run=True,
            cache_only=False,
            max_symbols=2,
            start="2026-06-02",
            end=None,
            theme_name="override_theme",
        )

        self.assertEqual(config.theme_name, "override_theme")
        self.assertEqual(config.max_symbols, 2)
        self.assertEqual(config.start, "2026-06-02")
        self.assertTrue(config.dry_run)

    @patch("aq_factor_lab.data_collection.cli.collect_thematic_dataset")
    def test_cli_main_invokes_collector_with_temp_config(self, collect):
        config_path = self.root / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "theme_name": "sample_theme",
                    "concept_names": ["concept_a"],
                    "start": "2026-06-01",
                    "end": "2026-06-05",
                    "output_root": str(self.root),
                    "max_symbols": 5,
                }
            ),
            encoding="utf-8",
        )
        collect.return_value = Mock(output_dir=self.root / "out", run_id="dry_run")

        with patch("builtins.print"):
            main(["--config", str(config_path), "--dry-run", "--max-symbols", "1"])

        called_config = collect.call_args.args[0]
        self.assertTrue(called_config.dry_run)
        self.assertEqual(called_config.max_symbols, 1)


if __name__ == "__main__":
    unittest.main()
