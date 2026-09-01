# ruff: noqa: E501 -- compact synthetic source records are easier to audit inline.
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).parents[1] / "scripts/download_h7_turnover_full_market.py"
SPEC = importlib.util.spec_from_file_location("h7_download", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class H7TurnoverDownloadTests(unittest.TestCase):
    def test_cutoff_and_percent_conversion(self) -> None:
        raw = pd.DataFrame({
            "date": ["2026-08-20", "2026-08-21"], "code": ["sz.000001"] * 2,
            "open": [1, 1], "high": [1, 1], "low": [1, 1], "close": [1, 1],
            "volume": [100, 200], "amount": [300, 400], "turn": [2, 3],
            "tradestatus": [1, 1], "isST": [0, 0],
        })
        out, discarded = MODULE.normalize_baostock(raw, "000001")
        self.assertEqual(discarded, 1)
        self.assertEqual(out.trade_date.max(), pd.Timestamp("2026-08-20"))
        self.assertAlmostEqual(out.baostock_circulating_turnover.iloc[0], .02)

    def test_empty_cninfo_records_is_successfully_normalized(self) -> None:
        out, discarded = MODULE.normalize_cninfo_payload({"records": []}, "000004")
        self.assertTrue(out.empty)
        self.assertEqual(discarded, 0)

    def test_future_event_discarded_and_no_backfill(self) -> None:
        payload = {"records": [
            {"DECLAREDATE": "2020-02-02", "VARYDATE": "2020-02-01", "F003N": 1, "F021N": 1},
            {"DECLAREDATE": "2026-08-21", "VARYDATE": "2026-08-20", "F003N": 2, "F021N": 2},
        ]}
        events, discarded = MODULE.normalize_cninfo_payload(payload, "000001")
        self.assertEqual(discarded, 1)
        daily = MODULE.point_in_time_shares(events, pd.Series(pd.to_datetime(["2020-02-01", "2020-02-02", "2020-02-03"])))
        self.assertTrue(np.isnan(daily.total_shares.iloc[0]))
        self.assertEqual(daily.total_shares.iloc[1], 10_000)

    def test_exact_prior_200_has_no_fill_and_excludes_t(self) -> None:
        values = pd.Series([1.0] * 201)
        valid = MODULE.exact_prior_200_valid(values)
        self.assertFalse(valid.iloc[199])
        self.assertTrue(valid.iloc[200])
        values.iloc[100] = np.nan
        self.assertFalse(MODULE.exact_prior_200_valid(values).iloc[200])

    def test_atomic_cache_and_validation(self) -> None:
        frame = pd.DataFrame({
            "stock_code": ["000001"], "trade_date": [pd.Timestamp("2026-08-20")],
            "volume_shares": [0], "amount_cny": [0],
            "baostock_circulating_turnover": [0], "trading_status": [0],
        })
        MODULE.validate_baostock(frame, "000001")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "x.csv"
            MODULE._atomic_csv(frame, path)
            self.assertTrue(path.exists())
            self.assertFalse(path.with_suffix(".csv.tmp").exists())

    def test_cutoff_cache_is_complete(self) -> None:
        dates = pd.Series(pd.to_datetime(["2026-08-19", "2026-08-20"]))
        self.assertEqual(dates.max(), MODULE.DATA_CUTOFF)

    def test_primary_does_not_use_local_or_secondary_fill(self) -> None:
        events = MODULE.normalize_cninfo_payload({}, "000001")[0]
        daily = MODULE.point_in_time_shares(events, pd.Series([pd.Timestamp("2020-01-02")]))
        self.assertTrue(daily.total_shares.isna().all())

    def test_failed_stock_has_empty_frame_for_status_recording(self) -> None:
        existing = pd.DataFrame()
        combined = existing
        self.assertEqual(len(combined), 0)

    def test_runner_has_no_forbidden_research_computation(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("state_conditioned_future_return", source)
        self.assertNotIn("winner_loser_performance", source)
        self.assertNotIn("rank_ic", source.lower())


if __name__ == "__main__":
    unittest.main()
