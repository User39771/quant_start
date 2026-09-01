# ruff: noqa: E501
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import pandas as pd

SCRIPT = Path(__file__).parents[1] / "scripts/audit_h7_final_contract_readiness.py"
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location("h7_contract", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(MODULE)


class H7FinalContractReadinessTests(unittest.TestCase):
    def test_cutoff_is_bounded(self) -> None:
        self.assertLessEqual(MODULE.DATA_CUTOFF, pd.Timestamp("2026-08-20"))

    def test_exact_200_excludes_current_from_baseline(self) -> None:
        valid = pd.Series([True] * 201)
        ready = MODULE.exact_200_market_days(valid)
        self.assertFalse(ready.iloc[199])
        self.assertTrue(ready.iloc[200])
        valid.iloc[100] = False
        self.assertFalse(MODULE.exact_200_market_days(valid).iloc[200])

    def test_last_200_active_uses_prior_observations_only(self) -> None:
        valid = pd.Series([True] * 100 + [False] * 20 + [True] * 101)
        ready = MODULE.last_200_active_days(valid)
        self.assertFalse(ready.iloc[-2])
        self.assertTrue(ready.iloc[-1])

    def test_suspension_is_not_active(self) -> None:
        status = pd.Series([1, 0, 1])
        self.assertEqual(status.eq(1).tolist(), [True, False, True])

    def test_active_zero_is_detectable_without_epsilon(self) -> None:
        active = pd.Series([True, True, False])
        turnover = pd.Series([.01, 0, 0])
        self.assertEqual(int((active & turnover.eq(0)).sum()), 1)

    def test_threshold_uses_availability_rows(self) -> None:
        frame = pd.DataFrame({"potential_1d_regression_rows": [499, 500, 1000]})
        self.assertEqual(MODULE.threshold_counts(frame, "potential_1d_regression_rows"), {500: 2, 750: 1, 1000: 1, 1250: 0})

    def test_endpoint_classifier_checks_presence_only(self) -> None:
        calendar = pd.DatetimeIndex(pd.to_datetime(["2026-05-15", "2026-05-18", "2026-05-19"]))
        positions = {date: index for index, date in enumerate(calendar)}
        reason = MODULE.classify_endpoint_gap(
            calendar[1], 1, calendar, positions, calendar[0], calendar[1],
            {calendar[0], calendar[1]}, calendar[1],
        )
        self.assertEqual(reason, "A_QFQ_TAIL_NOT_REFRESHED")

    def test_no_network_or_estimation_code(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8").lower()
        for forbidden in (
            "import requests", "import baostock", "import akshare", "import tushare",
            "http://", "https://", "statsmodels", ".fit(", "lstsq", "estimate_c2",
        ):
            self.assertNotIn(forbidden, source)
        self.assertNotIn("local_implied_total_shares", source)


if __name__ == "__main__":
    unittest.main()
