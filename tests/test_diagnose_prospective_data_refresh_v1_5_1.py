import hashlib
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.diagnose_prospective_data_refresh_v1_5_1 import (
    probe_with_fallback,
    refined_diagnosis,
    request_row,
    resolve_candidate,
    zero_attempt_diagnosis,
)
from scripts.refresh_research_data_v1_5 import normalize_stock
from scripts.run_lowvol_prospective_append_v1_5_1 import PROTECTED


class DataRefreshDiagnosticTests(unittest.TestCase):
    def test_zero_attempts_are_non_blocking_not_failures(self):
        result = zero_attempt_diagnosis(pd.DataFrame(columns=["endpoint", "success", "failed"]))
        self.assertEqual(result["attempts"], 0)
        self.assertEqual(result["issue_type"], "misleading_zero_attempt_success_rate")
        self.assertEqual(result["severity"], "non_blocking_engineering_issue")
        self.assertEqual(result["action"], "deferred")

    def test_failed_attempt_is_distinct_from_zero_attempt(self):
        result = zero_attempt_diagnosis(pd.DataFrame([{"endpoint": "price", "success": 0, "failed": 1}]))
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(result["issue_type"], "none")

    def test_explicit_candidate_date_is_preserved(self):
        date, source = resolve_candidate(Path("."), pd.DataFrame(), "2027-01-06")
        self.assertEqual((date, source), ("2027-01-06", "explicit_probe_date"))

    def test_dynamic_candidate_uses_frozen_twenty_entry_cadence(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "reports/prospective/lowvol_v1_5_1").mkdir(parents=True)
            dates = pd.bdate_range("2026-05-18", periods=41)
            pd.DataFrame([
                {"rebalance_date": dates[0], "next_rebalance_date": dates[20], "period_trading_days": 20, "period_type": "full", "universe_name": "research_universe_v1_2", "transaction_cost": 0},
                {"rebalance_date": dates[20], "next_rebalance_date": dates[39], "period_trading_days": 19, "period_type": "partial", "universe_name": "research_universe_v1_2", "transaction_cost": 0},
            ]).to_csv(root / "reports/adjusted_stock_pool_baseline_periods_v1_5.csv", index=False)
            pd.DataFrame(columns=["period_id", "status"]).to_csv(root / "reports/prospective/lowvol_v1_5_1/prospective_periods.csv", index=False)
            benchmark = pd.DataFrame({"benchmark_code": "000300", "trade_date": dates, "close": range(100, 141)})
            # Missing ledger is the normal pre-append state and avoids fixture schema coupling.
            (root / "reports/prospective/lowvol_v1_5_1/prospective_periods.csv").unlink()
            candidate, source = resolve_candidate(root, benchmark, None)
            self.assertEqual(candidate, dates[40].strftime("%Y-%m-%d"))
            self.assertEqual(source, "frozen_schedule")

    def test_raw_and_normalized_ranges_and_candidate_presence(self):
        raw = pd.DataFrame({"date": ["2026/07/10", "2026/07/13"], "close": [10, 11]})
        row = request_row("stock", "63", "fake", "2026-07-10", "2026-07-13", "2026-07-13", "present", lambda: raw, normalize_stock)
        self.assertEqual(row["response_min_date"], "2026-07-10")
        self.assertEqual(row["response_max_date"], "2026-07-13")
        self.assertEqual(row["normalized_min_date"], "2026-07-10")
        self.assertEqual(row["normalized_max_date"], "2026-07-13")
        self.assertTrue(row["candidate_date_present"])

    def test_candidate_presence_uses_normalized_dates(self):
        raw = pd.DataFrame({"date": ["not-a-date", "2026-07-13"], "close": [10, 11]})
        row = request_row("stock", "000063", "fake", "", "", "2026-07-13", "present", lambda: raw, normalize_stock)
        self.assertEqual(row["request_status"], "failed")
        self.assertFalse(row["candidate_date_present"])

    def test_probe_failure_is_recorded_and_does_not_call_fallback_after_success(self):
        calls = []
        good = lambda *_: pd.DataFrame({"date": ["2026-07-10"], "close": [10]})
        rows = probe_with_fallback("stock", "000063", "2026-07-10", "2026-07-13", "2026-07-13", "present", good, lambda *_: calls.append(1))
        self.assertEqual(len(rows), 1)
        self.assertFalse(calls)
        rows = probe_with_fallback("stock", "000063", "2026-07-10", "2026-07-13", "2026-07-13", "present", lambda *_: (_ for _ in ()).throw(RuntimeError("offline")), good)
        self.assertEqual([row["request_status"] for row in rows], ["failed", "success"])
        self.assertTrue(rows[1]["fallback_attempted"])

    def test_probe_diagnosis_identifies_stale_local_cutoff(self):
        rows = [
            {"request_attempted": True, "request_status": "success", "asset_type": "stock", "candidate_date_present": True},
            {"request_attempted": True, "request_status": "success", "asset_type": "benchmark", "candidate_date_present": True},
        ]
        self.assertEqual(refined_diagnosis(rows), "SOURCE_DATA_AVAILABLE_LOCAL_CUTOFF_STALE")

    def test_probe_helpers_do_not_write_or_modify_protected_files(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for name in PROTECTED:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(name, encoding="utf-8")
            before = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in PROTECTED}
            request_row("stock", "000063", "fake", "", "", "", "present", lambda: (_ for _ in ()).throw(RuntimeError("offline")), normalize_stock)
            after = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in PROTECTED}
            self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
