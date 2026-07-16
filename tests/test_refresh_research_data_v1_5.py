import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.refresh_research_data_v1_5 import (
    INDEX_IDENTITIES,
    normalize_benchmark,
    refresh_stock,
    run,
)


class RefreshResearchDataV15Tests(unittest.TestCase):
    def test_stock_source_order_prefers_sina(self):
        calls = []

        def sina(*_):
            calls.append("sina")
            return pd.DataFrame({"date": ["2024-01-02"], "close": [10.0]})

        def eastmoney(*_):
            calls.append("eastmoney")
            raise AssertionError("fallback should not run")

        frame, source, seeded, errors = refresh_stock(
            "000001", "2024-01-01", "2024-01-31", sina, eastmoney, None
        )
        self.assertEqual(calls, ["sina"])
        self.assertEqual(source, "ak.stock_zh_a_daily")
        self.assertFalse(seeded)
        self.assertFalse(errors)
        self.assertEqual(frame.loc[0, "stock_code"], "000001")

    def test_stock_uses_seed_only_after_both_sources_fail(self):
        with TemporaryDirectory() as directory:
            seed = Path(directory) / "000001.csv"
            pd.DataFrame(
                {
                    "stock_code": ["000001"],
                    "trade_date": ["2024-01-02"],
                    "qfq_close": [10.0],
                }
            ).to_csv(seed, index=False)

            def fail(*_):
                raise RuntimeError("offline")

            frame, source, seeded, errors = refresh_stock(
                "000001", "2024-01-01", "2024-01-31", fail, fail, seed
            )
            self.assertTrue(seeded)
            self.assertEqual(source, "seeded_from_v1_2")
            self.assertEqual(len(errors), 2)
            self.assertEqual(len(frame), 1)

    def test_benchmark_identity_is_index_only(self):
        raw = pd.DataFrame(
            {
                "date": ["2024-01-02", "2024-01-03"],
                "close": [3000.0, 3010.0],
            }
        )
        result = normalize_benchmark("000852", raw, "ak.stock_zh_index_daily_tx")
        self.assertEqual(INDEX_IDENTITIES["000852"]["name"], "CSI 1000")
        self.assertEqual(result["benchmark_code"].unique().tolist(), ["000852"])
        self.assertEqual(result["instrument_type"].unique().tolist(), ["index"])

    def test_run_writes_only_v15_paths_with_mock_fetchers(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data" / "processed"
            reports = root / "reports"
            old_cache = root / "data" / "cache" / "qfq_enrichment_v1_2"
            data.mkdir(parents=True)
            reports.mkdir()
            old_cache.mkdir(parents=True)
            pd.DataFrame({"code": ["000001", "000002"]}).to_csv(
                data / "research_universe_lowvol_freeze_20260711.csv", index=False
            )
            pd.DataFrame(
                columns=["stock_code", "trade_date", "qfq_close"]
            ).to_csv(data / "adjusted_price_panel_v1_2.csv", index=False)
            pd.DataFrame(
                columns=["benchmark_code", "trade_date", "close"]
            ).to_csv(data / "hybrid_benchmark_panel_v1_2.csv", index=False)

            def stock_fetch(code, *_):
                return pd.DataFrame(
                    {
                        "date": ["2024-01-02", "2024-01-03"],
                        "close": [10.0, 10.1],
                    }
                )

            def index_fetch(code, *_):
                return pd.DataFrame(
                    {
                        "date": ["2024-01-02", "2024-01-03"],
                        "close": [3000.0, 3010.0],
                    }
                )

            result = run(
                root,
                start_date="2024-01-01",
                end_date="2024-01-31",
                stock_primary=stock_fetch,
                stock_fallback=stock_fetch,
                index_primary=index_fetch,
                index_fallback=index_fetch,
                sleep_seconds=0,
            )
            self.assertTrue(result["qa"]["critical_qa_pass"])
            self.assertTrue(
                (data / "adjusted_price_panel_v1_5.csv").exists()
            )
            self.assertTrue(
                (data / "hybrid_benchmark_panel_v1_5.csv").exists()
            )
            self.assertFalse(
                (root / "data" / "cache" / "qfq_enrichment_v1_2" / "000001.csv").exists()
            )


if __name__ == "__main__":
    unittest.main()
