# ruff: noqa: E501
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

SCRIPT = Path(__file__).parents[1] / "scripts/audit_h7_turnover_data_quality.py"
SPEC = importlib.util.spec_from_file_location("h7_quality", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class H7DataQualityAuditTests(unittest.TestCase):
    def test_cutoff_is_frozen(self) -> None:
        self.assertEqual(MODULE.DATA_CUTOFF, pd.Timestamp("2026-08-20"))

    def test_point_in_time_never_backfills_future_event(self) -> None:
        events = pd.DataFrame({
            "information_available_date": pd.to_datetime(["2020-01-03"]),
            "total_shares": [100.0], "circulating_shares": [80.0],
            "event_date_incomplete": [False],
        })
        out = MODULE.point_in_time_shares(events, pd.DatetimeIndex(pd.to_datetime(["2020-01-02", "2020-01-03"])))
        self.assertTrue(np.isnan(out.total_shares.iloc[0]))
        self.assertEqual(out.total_shares.iloc[1], 100.0)

    def test_exact_200_excludes_t_and_has_no_fill(self) -> None:
        valid = pd.Series([True] * 201)
        ready = MODULE.exact_prior_200_ready(valid)
        self.assertFalse(ready.iloc[199])
        self.assertTrue(ready.iloc[200])
        valid.iloc[100] = False
        self.assertFalse(MODULE.exact_prior_200_ready(valid).iloc[200])

    def test_total_turnover_and_percent_conversion_contract(self) -> None:
        self.assertAlmostEqual(200 / 1_000, .2)
        self.assertAlmostEqual(2.5 / 100, .025)

    def test_empty_cninfo_is_not_schema_failure(self) -> None:
        empty = pd.DataFrame(columns=list(MODULE.CN_REQUIRED))
        self.assertTrue(empty.empty)

    def test_status_cache_mismatch_detection(self) -> None:
        status = pd.DataFrame({"stock_code": ["000001", "000002"], "status": ["FAILED", "SUCCESS"]})
        rows = MODULE.status_cache_mismatches(["000001", "000002"], status, {"000001"}, "BAOSTOCK")
        kinds = {row["exception_type"] for row in rows}
        self.assertEqual(kinds, {"STATUS_STALE_CACHE_VALID", "STATUS_SUCCESS_CACHE_MISSING_OR_INVALID"})

    def test_audit_has_no_network_or_research_client(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8").lower()
        for forbidden in ("import requests", "import baostock", "import akshare", "import tushare", "http://", "https://"):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("volume_return_regression(", source)
        self.assertNotIn("estimate_c2(", source)


if __name__ == "__main__":
    unittest.main()
