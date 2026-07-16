from __future__ import annotations

import importlib.util
import argparse
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "enrich_qfq_slow_v1_2.py"
SPEC = importlib.util.spec_from_file_location("enrich_qfq_slow_v1_2", MODULE_PATH)
enrich = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = enrich
SPEC.loader.exec_module(enrich)


class EnrichQfqSlowV12Tests(unittest.TestCase):
    def test_code6_preserves_leading_zero(self):
        self.assertEqual(enrich.code6("63"), "000063")

    def test_sina_symbol_mapping(self):
        self.assertEqual(enrich.sina_symbol("000063"), "sz000063")
        self.assertEqual(enrich.sina_symbol("600519"), "sh600519")

    def test_resume_complete_cache_skips_fetch(self):
        raw = pd.DataFrame(
            {
                "stock_code": ["000063", "000063"],
                "trade_date": ["2026-01-02", "2026-01-03"],
                "close": [10, 11],
            }
        )
        qfq = pd.DataFrame(
            {
                "stock_code": ["000063", "000063"],
                "trade_date": ["2026-01-02", "2026-01-03"],
                "qfq_open": [9, 10],
                "qfq_high": [10, 11],
                "qfq_low": [8, 9],
                "qfq_close": [9.5, 10.5],
            }
        )
        with TemporaryDirectory() as tmp:
            cache = Path(tmp)
            qfq.to_csv(cache / "000063.csv", index=False)
            self.assertTrue(enrich.cache_is_complete("000063", raw, cache))
            qfq_out, manifest, failure = enrich.fetch_or_cache_symbol(
                "000063",
                raw,
                cache,
                "run",
                "2026-07-07T00:00:00+00:00",
                "2026-01-02",
                "2026-01-03",
                5,
                resume=True,
            )

        self.assertEqual(manifest["source_endpoint"], "cached:qfq_enrichment_v1_2")
        self.assertIsNone(failure)
        self.assertEqual(len(qfq_out), 2)

    def test_fetch_failure_writes_manifest_and_failure_without_raising(self):
        def failing_fetcher(_symbol: str, _raw_symbol: pd.DataFrame, _start: str, _end: str, _attempts: int) -> tuple[pd.DataFrame, str]:
            raise RuntimeError("boom")

        run_id = "run"
        fetched_at = "2026-07-07T00:00:00+00:00"
        qfq, manifest, failure = enrich.fetch_or_cache_symbol(
            "000063",
            pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "close": [10]}),
            Path("unused"),
            run_id,
            fetched_at,
            "2026-01-02",
            "2026-01-03",
            5,
            fetcher=failing_fetcher,
            resume=False,
        )

        self.assertTrue(qfq.empty)
        self.assertEqual(manifest["final_status"], "error")
        self.assertEqual(failure["error_type"], "RuntimeError")

    def test_sina_success_does_not_call_eastmoney(self):
        calls: list[str] = []
        raw_symbol = pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "close": [10]})

        def sina(_symbol: str, _start: str, _end: str) -> pd.DataFrame:
            calls.append("sina")
            return pd.DataFrame({"date": ["2026-01-02"], "open": [9], "high": [10], "low": [8], "close": [9.5]})

        def eastmoney(_symbol: str, _start: str, _end: str) -> pd.DataFrame:
            calls.append("eastmoney")
            raise AssertionError("eastmoney should not be called")

        qfq, source = enrich.fetch_qfq_with_fallback("000063", raw_symbol, "2026-01-02", "2026-01-03", 5, sina_fetch=sina, eastmoney_fetch=eastmoney)

        self.assertEqual(calls, ["sina"])
        self.assertEqual(source, "ak.stock_zh_a_daily")
        self.assertEqual(qfq.loc[0, "source_qfq"], "ak.stock_zh_a_daily")

    def test_sina_invalid_qfq_falls_back_to_eastmoney(self):
        raw_symbol = pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "close": [10]})

        def sina(_symbol: str, _start: str, _end: str) -> pd.DataFrame:
            return pd.DataFrame({"date": ["2026-01-02"], "close": [0]})

        def eastmoney(_symbol: str, _start: str, _end: str) -> pd.DataFrame:
            return pd.DataFrame({"date": ["2026-01-02"], "open": [8], "high": [10], "low": [7], "close": [9]})

        qfq, source = enrich.fetch_qfq_with_fallback("000063", raw_symbol, "2026-01-02", "2026-01-03", 5, sina_fetch=sina, eastmoney_fetch=eastmoney)

        self.assertEqual(source, "ak.stock_zh_a_hist")
        self.assertEqual(qfq.loc[0, "source_qfq"], "ak.stock_zh_a_hist")

    def test_sina_zero_raw_date_coverage_falls_back_to_eastmoney(self):
        raw_symbol = pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "close": [10]})

        def sina(_symbol: str, _start: str, _end: str) -> pd.DataFrame:
            return pd.DataFrame({"date": ["2026-02-02"], "open": [9], "high": [10], "low": [8], "close": [9]})

        def eastmoney(_symbol: str, _start: str, _end: str) -> pd.DataFrame:
            return pd.DataFrame({"date": ["2026-01-02"], "open": [8], "high": [10], "low": [7], "close": [9]})

        qfq, source = enrich.fetch_qfq_with_fallback("000063", raw_symbol, "2026-01-02", "2026-02-03", 5, sina_fetch=sina, eastmoney_fetch=eastmoney)

        self.assertEqual(source, "ak.stock_zh_a_hist")
        self.assertEqual(qfq.loc[0, "trade_date"], "2026-01-02")

    def test_sina_exception_falls_back_to_eastmoney(self):
        raw_symbol = pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "close": [10]})

        def sina(_symbol: str, _start: str, _end: str) -> pd.DataFrame:
            raise RuntimeError("sina down")

        def eastmoney(_symbol: str, _start: str, _end: str) -> pd.DataFrame:
            return pd.DataFrame({"date": ["2026-01-02"], "open": [8], "high": [10], "low": [7], "close": [9]})

        qfq, source = enrich.fetch_qfq_with_fallback("000063", raw_symbol, "2026-01-02", "2026-01-03", 5, sina_fetch=sina, eastmoney_fetch=eastmoney)

        self.assertEqual(source, "ak.stock_zh_a_hist")
        self.assertEqual(len(qfq), 1)

    def test_both_sources_fail_error_mentions_both(self):
        raw_symbol = pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "close": [10]})

        def sina(_symbol: str, _start: str, _end: str) -> pd.DataFrame:
            raise RuntimeError("sina bad")

        def eastmoney(_symbol: str, _start: str, _end: str) -> pd.DataFrame:
            raise RuntimeError("eastmoney bad")

        with self.assertRaises(RuntimeError) as ctx:
            enrich.fetch_qfq_with_fallback("000063", raw_symbol, "2026-01-02", "2026-01-03", 5, sina_fetch=sina, eastmoney_fetch=eastmoney)

        self.assertIn("ak.stock_zh_a_daily", str(ctx.exception))
        self.assertIn("ak.stock_zh_a_hist", str(ctx.exception))

    def test_latest_manifest_status_wins(self):
        manifest = pd.DataFrame(
            {
                "stock_code": ["000063", "000063"],
                "fetched_at": ["2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00"],
                "final_status": ["error", "cached_ok"],
            }
        )
        latest = enrich.latest_manifest_status(manifest)

        self.assertEqual(latest.loc["000063", "final_status"], "cached_ok")

    def test_adjusted_flag_false_when_qfq_missing_or_invalid(self):
        raw = pd.DataFrame(
            {
                "stock_code": ["000063", "000063"],
                "trade_date": ["2026-01-02", "2026-01-03"],
                "close": [10, 11],
                "amount": [100, 110],
                "total_market_cap": [1000, 1100],
                "circulating_market_cap": [900, 1000],
                "source": ["raw.csv", "raw.csv"],
            }
        )
        qfq = pd.DataFrame(
            {
                "stock_code": ["000063"],
                "trade_date": ["2026-01-02"],
                "qfq_close": [0],
                "qfq_open": [0],
                "qfq_high": [0],
                "qfq_low": [0],
                "source_qfq": ["qfq.csv"],
            }
        )
        adjusted = enrich.build_adjusted_panel(raw, qfq)

        self.assertEqual(adjusted["adjusted_flag"].tolist(), ["false", "false"])
        self.assertTrue(adjusted["adjusted_close"].isna().all())

    def test_coverage_uses_raw_rows_and_requires_both_thresholds(self):
        raw = pd.DataFrame(
            {
                "stock_code": ["000063", "000063", "300857", "300857"],
                "trade_date": ["2026-01-02", "2026-01-03", "2026-01-02", "2026-01-03"],
                "close": [10, 11, 20, 21],
            }
        )
        adjusted = pd.DataFrame(
            {
                "stock_code": ["000063", "000063", "300857", "300857"],
                "trade_date": ["2026-01-02", "2026-01-03", "2026-01-02", "2026-01-03"],
                "qfq_close": [9, 10, None, None],
                "adjusted_flag": ["true", "true", "false", "false"],
            }
        )
        qa = enrich.evaluate_readiness(raw, adjusted, ["000063", "300857"], pd.DataFrame())

        self.assertEqual(qa["stock_coverage_ratio"], 0.5)
        self.assertEqual(qa["row_coverage_ratio"], 0.5)
        self.assertFalse(qa["adjusted_return_ready"])

    def test_alignment_warning_for_latest_common_date_ratio_outside_band(self):
        raw = pd.DataFrame(
            {
                "stock_code": ["000063"],
                "trade_date": ["2026-01-02"],
                "close": [10.0],
            }
        )
        adjusted = pd.DataFrame(
            {
                "stock_code": ["000063"],
                "trade_date": ["2026-01-02"],
                "qfq_close": [8.0],
                "adjusted_flag": ["true"],
            }
        )

        warnings = enrich.alignment_warnings(raw, adjusted)

        self.assertEqual(warnings[0]["warning_type"], "qfq_raw_alignment_warning")
        self.assertEqual(warnings[0]["stock_code"], "000063")

    def test_duplicate_stock_date_is_flagged(self):
        raw = pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "close": [10]})
        adjusted = pd.DataFrame(
            {
                "stock_code": ["000063", "000063"],
                "trade_date": ["2026-01-02", "2026-01-02"],
                "qfq_close": [9, 9],
                "adjusted_flag": ["true", "true"],
            }
        )
        qa = enrich.evaluate_readiness(raw, adjusted, ["000063"], pd.DataFrame())

        self.assertEqual(qa["duplicate_stock_date_rows"], 2)

    def test_write_csv_preserves_code6_date_and_lowercase_flag(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "adjusted.csv"
            frame = pd.DataFrame(
                {
                    "stock_code": ["63", "2049"],
                    "trade_date": ["2026/1/2", "2026-01-03"],
                    "adjusted_flag": ["TRUE", False],
                }
            )

            enrich.write_csv(path, frame, ["stock_code", "trade_date", "adjusted_flag"])
            text = path.read_text(encoding="utf-8-sig")
            saved = pd.read_csv(path, dtype={"stock_code": str})

        self.assertIn("000063,2026-01-02,true", text)
        self.assertIn("002049,2026-01-03,false", text)
        self.assertEqual(saved["stock_code"].tolist(), ["000063", "002049"])

    def test_load_qfq_cache_for_universe_reads_all_cache(self):
        raw = pd.DataFrame(
            {
                "stock_code": ["000063", "000063", "300857", "300857"],
                "trade_date": ["2026-01-02", "2026-01-03", "2026-01-02", "2026-01-03"],
                "close": [10, 11, 20, 21],
            }
        )
        with TemporaryDirectory() as tmp:
            cache = Path(tmp)
            pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "qfq_close": [9]}).to_csv(cache / "000063.csv", index=False)
            pd.DataFrame({"stock_code": ["300857"], "trade_date": ["2026-01-02"], "qfq_close": [19]}).to_csv(cache / "300857.csv", index=False)

            panel, invalid = enrich.load_qfq_cache_for_universe(["000063", "300857"], raw, cache)

        self.assertEqual(set(panel["stock_code"]), {"000063", "300857"})
        self.assertEqual(invalid, [])

    def test_invalid_cache_is_excluded(self):
        raw = pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "close": [10]})
        with TemporaryDirectory() as tmp:
            cache = Path(tmp)
            pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "qfq_close": [0]}).to_csv(cache / "000063.csv", index=False)

            panel, invalid = enrich.load_qfq_cache_for_universe(["000063"], raw, cache)

        self.assertTrue(panel.empty)
        self.assertEqual(invalid, ["000063"])

    def test_rebuild_from_cache_false_when_full_cache_below_threshold(self):
        raw = pd.DataFrame(
            {
                "stock_code": ["000063", "000063", "300857", "300857"],
                "trade_date": ["2026-01-02", "2026-01-03", "2026-01-02", "2026-01-03"],
                "close": [10, 11, 20, 21],
            }
        )
        with TemporaryDirectory() as tmp:
            cache = Path(tmp)
            out = Path(tmp) / "out"
            pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "qfq_close": [9]}).to_csv(cache / "000063.csv", index=False)

            qa = enrich.rebuild_outputs_from_cache(raw, ["000063", "300857"], pd.DataFrame(), cache_dir=cache, output_dir=out, report_path=out / "report.md")

        self.assertFalse(qa["adjusted_return_ready"])

    def test_rebuild_from_cache_true_when_full_cache_reaches_threshold(self):
        raw = pd.DataFrame(
            {
                "stock_code": ["000063", "000063", "300857", "300857"],
                "trade_date": ["2026-01-02", "2026-01-03", "2026-01-02", "2026-01-03"],
                "close": [10, 11, 20, 21],
            }
        )
        with TemporaryDirectory() as tmp:
            cache = Path(tmp)
            out = Path(tmp) / "out"
            pd.DataFrame({"stock_code": ["000063", "000063"], "trade_date": ["2026-01-02", "2026-01-03"], "qfq_close": [9, 10]}).to_csv(cache / "000063.csv", index=False)
            pd.DataFrame({"stock_code": ["300857", "300857"], "trade_date": ["2026-01-02", "2026-01-03"], "qfq_close": [19, 20]}).to_csv(cache / "300857.csv", index=False)

            qa = enrich.rebuild_outputs_from_cache(raw, ["000063", "300857"], pd.DataFrame(), cache_dir=cache, output_dir=out, report_path=out / "report.md")

        self.assertTrue(qa["adjusted_return_ready"])

    def test_rebuild_from_cache_only_does_not_call_live_fetch(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            raw_path = root / "raw.csv"
            universe_path = root / "universe.csv"
            cache = root / "cache"
            cache.mkdir()
            raw = pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "close": [10]})
            raw.to_csv(raw_path, index=False)
            pd.DataFrame({"code": ["000063"]}).to_csv(universe_path, index=False)
            pd.DataFrame({"stock_code": ["000063"], "trade_date": ["2026-01-02"], "qfq_close": [9]}).to_csv(cache / "000063.csv", index=False)

            old = (enrich.RAW_BASE_PATH, enrich.UNIVERSE_PATH, enrich.QFQ_CACHE_DIR, enrich.QFQ_PANEL_OUT, enrich.ADJUSTED_PANEL_OUT, enrich.READINESS_OUT)
            old_fetch = enrich.fetch_or_cache_symbol
            enrich.RAW_BASE_PATH = raw_path
            enrich.UNIVERSE_PATH = universe_path
            enrich.QFQ_CACHE_DIR = cache
            enrich.QFQ_PANEL_OUT = root / "qfq.csv"
            enrich.ADJUSTED_PANEL_OUT = root / "adjusted.csv"
            enrich.READINESS_OUT = root / "report.md"
            enrich.fetch_or_cache_symbol = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("live fetch called"))
            try:
                qa = enrich.run(
                    argparse.Namespace(
                        dry_run=False,
                        symbols=None,
                        limit=None,
                        resume=False,
                        start_date=None,
                        end_date=None,
                        sleep_min=0,
                        sleep_max=0,
                        max_attempts=1,
                        rebuild_from_cache_only=True,
                    )
                )
            finally:
                enrich.RAW_BASE_PATH, enrich.UNIVERSE_PATH, enrich.QFQ_CACHE_DIR, enrich.QFQ_PANEL_OUT, enrich.ADJUSTED_PANEL_OUT, enrich.READINESS_OUT = old
                enrich.fetch_or_cache_symbol = old_fetch

        self.assertTrue(qa["adjusted_return_ready"])


if __name__ == "__main__":
    unittest.main()
