from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import pandas as pd

from scripts.run_database_pipeline import load_universe_symbols, main


class DatabasePipelineTests(unittest.TestCase):
    def test_pipeline_batches_sync_and_writes_manifest(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            universe = root / "data" / "cache"
            universe.mkdir(parents=True)
            pd.DataFrame(
                {
                    "db_symbol": ["SZ_000001", "SH_600519", "SZ_300750"],
                    "code": ["000001", "600519", "300750"],
                    "exchange": ["SZ", "SH", "SZ"],
                    "name": ["a", "b", "c"],
                }
            ).to_csv(universe / "universe_spot.csv", index=False)
            calls: list[list[str]] = []

            def fake_run(command, **kwargs):
                calls.append(command)
                class Result:
                    returncode = 0
                return Result()

            argv = [
                "run_database_pipeline.py",
                "--root",
                str(root),
                "--endpoints",
                "price,cashflow,profit",
                "--chunk-size",
                "2",
                "--start-date",
                "2019-01-01",
                "--end-date",
                "2026-06-12",
                "--refresh-existing",
                "--years",
                "5",
            ]

            with patch("sys.argv", argv), patch("scripts.run_database_pipeline.subprocess.run", side_effect=fake_run):
                main()

            manifest = json.loads((root / "data" / "processed" / "pipeline_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["symbols_count"], 3)
            self.assertEqual(manifest["sync_batches"], 2)
            self.assertEqual(manifest["research_returncode"], 0)
            self.assertTrue(any("sync_database_cache.py" in command[1] for command in calls))
            self.assertTrue(any("run_research.py" in command[1] and "--cache-only" in command for command in calls))

    def test_load_universe_symbols_filters_non_a_share_database_symbols(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            cache = root / "data" / "cache"
            cache.mkdir(parents=True)
            pd.DataFrame(
                {
                    "db_symbol": ["SZ_000001", "SH_600519", "9999999_SPACEX", "93751_STT", "SZ_300750"],
                    "code": ["000001", "600519", "999999", "93751_STT", "300750"],
                    "exchange": ["SZ", "SH", "SH", "SH", "SZ"],
                    "name": ["a", "b", None, None, "c"],
                }
            ).to_csv(cache / "universe_spot.csv", index=False)

            symbols, stats = load_universe_symbols(root)

            self.assertEqual(symbols, ["SZ_000001", "SZ_300750", "SH_600519"])
            self.assertEqual(stats["raw_universe_count"], 5)
            self.assertEqual(stats["a_share_symbol_count"], 3)
            self.assertEqual(stats["excluded_symbol_count"], 2)


if __name__ == "__main__":
    unittest.main()
