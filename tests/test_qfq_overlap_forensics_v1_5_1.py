import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from scripts.forensics_qfq_overlap_v1_5_1 import (
    classify_evidence,
    fit_overlap,
    raw_total_return,
    reconcile_explicit_qfq_factor,
    raw_implied_by_qfq_factor,
    protected_snapshot,
    reconcile_return,
    source_tolerance,
)


class QfqOverlapForensicsTests(unittest.TestCase):
    @staticmethod
    def prices(values, name):
        return pd.DataFrame({
            "trade_date": pd.date_range("2026-06-25", periods=len(values), freq="D").strftime("%Y-%m-%d"),
            name: values,
        })

    def test_stable_multiplicative_rebasing_uses_every_date_and_preserves_returns(self):
        refreshed = self.prices([10, 11, 12, 13, 14, 15, 16], "refreshed_qfq")
        frozen = self.prices(np.array([10, 11, 12, 13, 14, 15, 16]) * 1.25, "frozen_qfq")
        rows, fit = fit_overlap(frozen, refreshed, source_tolerance(2, 10))
        self.assertEqual(fit["common_date_count"], 7)
        self.assertEqual(len(rows), 7)
        self.assertTrue(fit["multiplicative_fit_pass"])
        self.assertTrue(np.allclose(
            rows["scaled_refreshed_qfq"].pct_change().dropna(),
            rows["frozen_qfq"].pct_change().dropna(),
        ))

    def test_stable_fit_does_not_override_failed_post_event_reconciliation(self):
        fit = {"multiplicative_fit_pass": True}
        status, allowed = classify_evidence(fit, False, False, True, True)
        self.assertEqual(status, "unresolved")
        self.assertFalse(allowed)

    def test_explicit_auditable_factor_can_support_tier1(self):
        raw = self.prices([20, 22, 24, 26, 28, 30], "raw")
        qfq = self.prices([10, 11, 12, 13, 14, 15], "qfq")
        factors = pd.DataFrame({"trade_date": ["2026-06-01"], "factor": [2.0]})
        result = reconcile_explicit_qfq_factor(raw, qfq, factors, "raw", "qfq", "factor", 1e-10)
        self.assertTrue(result["explicit_factor_reconciles"])
        status, allowed = classify_evidence({}, True, True, True, True)
        self.assertEqual(status, "tier1_factor_bridge_supported")
        self.assertTrue(allowed)

    def test_fewer_than_five_common_dates_fails(self):
        refreshed = self.prices([10, 11, 12, 13], "refreshed_qfq")
        frozen = self.prices([20, 22, 24, 26], "frozen_qfq")
        _, fit = fit_overlap(frozen, refreshed, source_tolerance(2, 10))
        self.assertFalse(fit["minimum_common_dates_pass"])
        self.assertFalse(fit["multiplicative_fit_pass"])

    def test_source_precision_changes_tolerance(self):
        self.assertGreater(source_tolerance(2, 10), source_tolerance(4, 10))

    def test_additive_relation_is_not_multiplicative(self):
        refreshed = self.prices([10, 20, 30, 40, 50, 60], "refreshed_qfq")
        frozen = self.prices([11, 21, 31, 41, 51, 61], "frozen_qfq")
        _, fit = fit_overlap(frozen, refreshed, source_tolerance(2, 10))
        self.assertTrue(fit["additive_fit_pass"])
        self.assertFalse(fit["multiplicative_fit_pass"])

    def test_missing_official_action_remains_unresolved(self):
        status, allowed = classify_evidence({"multiplicative_fit_pass": True}, False, True, True, False)
        self.assertEqual(status, "unresolved")
        self.assertFalse(allowed)

    def test_independent_source_disagreement_blocks_tier1(self):
        status, allowed = classify_evidence({"multiplicative_fit_pass": True}, False, True, False, True)
        self.assertEqual(status, "tier2_only_supported")
        self.assertFalse(allowed)

    def test_two_stocks_can_have_different_conclusions(self):
        good = classify_evidence({"multiplicative_fit_pass": True}, False, True, True, True)
        bad = classify_evidence({"multiplicative_fit_pass": False}, False, False, False, True)
        self.assertEqual(good, ("tier1_rescaling_supported", True))
        self.assertEqual(bad, ("unresolved", False))

    def test_tier2_evidence_cannot_authorize_v1_5_1(self):
        status, allowed = classify_evidence({"multiplicative_fit_pass": False}, False, True, True, True)
        self.assertEqual(status, "tier2_only_supported")
        self.assertFalse(allowed)

    def test_corporate_action_total_return_and_reconciliation(self):
        expected = raw_total_return(10.0, 9.0, cash_per_10=1.0, bonus_per_10=1.0)
        self.assertAlmostEqual(expected, 0.0)
        self.assertTrue(reconcile_return(0.0, expected, 1e-8))
        self.assertFalse(reconcile_return(0.02, expected, 1e-4))

    def test_qfq_factor_implies_raw_boundary_prices(self):
        qfq = pd.DataFrame({"trade_date": ["2026-07-10", "2026-07-13"], "qfq": [43.09, 41.90]})
        factors = pd.DataFrame({
            "trade_date": ["2025-07-04", "2026-07-13"],
            "factor": [1.0023207240659, 1.0],
        })
        implied = raw_implied_by_qfq_factor(qfq, factors, "qfq", "factor")
        self.assertAlmostEqual(implied.iloc[0]["factor_implied_raw_close"], 43.19, places=2)
        self.assertEqual(implied.iloc[1]["factor_implied_raw_close"], 41.90)

    def test_forensic_output_does_not_change_protected_snapshot(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            frozen = root / "data/processed/adjusted_price_panel_v1_5.csv"
            failed = root / "reports/prospective/lowvol_v1_5_1/refresh_runs/failed"
            output = root / "reports/prospective/lowvol_v1_5_1/qfq_forensics_20260713"
            frozen.parent.mkdir(parents=True)
            failed.mkdir(parents=True)
            frozen.write_text("frozen", encoding="ascii")
            (failed / "manifest.csv").write_text("failed", encoding="ascii")
            before = protected_snapshot(root, failed, output)
            output.mkdir(parents=True)
            (output / "report.md").write_text("evidence", encoding="ascii")
            self.assertEqual(before, protected_snapshot(root, failed, output))
            frozen.write_text("changed", encoding="ascii")
            self.assertNotEqual(before, protected_snapshot(root, failed, output))


if __name__ == "__main__":
    unittest.main()
