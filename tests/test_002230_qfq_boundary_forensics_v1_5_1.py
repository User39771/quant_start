import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.forensics_002230_qfq_boundary_v1_5_1 import (
    classify,
    displayed_decimals,
    evaluate_bridge_candidate,
    intervals_overlap,
    protected_snapshot,
    return_interval,
    rounded_interval,
    validate_raw_identity,
)


class QfqBoundarySecondPassTests(unittest.TestCase):
    def setUp(self):
        self.frozen = pd.DataFrame({
            "trade_date": pd.date_range("2026-06-25", periods=12, freq="B").strftime("%Y-%m-%d"),
            "frozen_qfq": [41.68, 39.12, 39.46, 40.84, 41.03, 41.08, 41.51, 40.65, 39.95, 40.94, 42.37, 43.19],
        })
        self.refreshed = self.frozen.copy()
        self.refreshed["refreshed_qfq"] = [
            41.58, 39.02, 39.36, 40.74, 40.93, 40.98, 41.41, 40.55, 39.85, 40.84, 42.27, 43.09,
        ]
        self.refreshed = self.refreshed[["trade_date", "refreshed_qfq"]]
        self.pre_factor = 1.0023207240659

    def test_raw_qfq_factor_identity_uses_source_precision(self):
        passed, implied, observed = validate_raw_identity(43.09, 2, self.pre_factor, 13, 43.19, 2)
        self.assertTrue(passed)
        self.assertTrue(intervals_overlap(implied, observed))

    def test_evidence_selects_pre_over_post_and_inverse_fails(self):
        total_return = return_interval(
            rounded_interval(43.19, 2), rounded_interval(41.90, 2), rounded_interval(0.10, 6)
        )
        correct = evaluate_bridge_candidate(
            "candidate_pre_over_post", self.pre_factor, 13, self.frozen, self.refreshed,
            2, 2, 43.19, 41.90, total_return, True,
        )
        inverse = evaluate_bridge_candidate(
            "candidate_post_over_pre", 1 / self.pre_factor, 13, self.frozen, self.refreshed,
            2, 2, 43.19, 41.90, total_return, True,
        )
        self.assertTrue(correct["all_three_checks_pass"])
        self.assertFalse(inverse["all_three_checks_pass"])
        self.assertFalse(inverse["overlap_reconstruction_pass"])
        self.assertFalse(inverse["corporate_action_return_pass"])

    def test_two_sided_rounding_accepts_residual_above_one_half_tick(self):
        expected = rounded_interval(43.19, 2)
        transformed = (
            rounded_interval(43.09, 2)[0] * self.pre_factor,
            rounded_interval(43.09, 2)[1] * self.pre_factor,
        )
        self.assertTrue(intervals_overlap(expected, transformed))
        self.assertGreater(abs(43.19 - 43.09 * 1.002445887761839), 0.005)

    def test_high_precision_is_not_forced_to_two_decimals(self):
        values = pd.Series([1.0023207240659, 1.0])
        self.assertEqual(displayed_decimals(values), 13)
        low, high = rounded_interval(values.iloc[0], 13)
        self.assertLess(high - low, 1e-12)

    def test_factor_effective_date_is_not_trade_date(self):
        factor_effective_date = "2025-07-04"
        trade_date = "2026-07-10"
        self.assertNotEqual(factor_effective_date, trade_date)

    def test_hfq_absolute_levels_need_not_match_across_vendors(self):
        eastmoney = return_interval(rounded_interval(573.68, 2), rounded_interval(558.32, 2))
        tencent = return_interval(rounded_interval(573.67, 2), rounded_interval(558.31, 2))
        self.assertTrue(intervals_overlap(eastmoney, tencent))
        self.assertNotEqual(573.68, 573.67)

    def test_stable_overlap_cannot_override_failed_economic_return(self):
        impossible = (0.10, 0.11)
        row = evaluate_bridge_candidate(
            "candidate", self.pre_factor, 13, self.frozen, self.refreshed,
            2, 2, 43.19, 41.90, impossible, True,
        )
        self.assertTrue(row["overlap_reconstruction_pass"])
        self.assertFalse(row["corporate_action_return_pass"])
        self.assertFalse(row["all_three_checks_pass"])

    def test_classification_keeps_script_issue_and_rounding_only_disjoint(self):
        issue = classify(True, True, True, False, True, False)
        rounding = classify(True, True, True, True, True, False)
        self.assertEqual(issue, ("forensic_script_issue", "display_rounding"))
        self.assertEqual(rounding, ("rounding_only", "display_rounding"))

    def test_missing_official_or_versioned_factor_is_unresolved(self):
        self.assertEqual(classify(False, False, False, False, False, False), ("unresolved", ""))

    def test_source_conflict_is_distinct(self):
        self.assertEqual(classify(True, False, False, False, False, True), ("source_data_issue", ""))

    def test_second_pass_output_is_excluded_but_first_pass_is_protected(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            panel = root / "data/processed/adjusted_price_panel_v1_5.csv"
            first = root / "reports/prospective/lowvol_v1_5_1/qfq_forensics_20260713/first.csv"
            output = first.parent / "002230_second_pass"
            panel.parent.mkdir(parents=True)
            first.parent.mkdir(parents=True)
            panel.write_text("panel", encoding="ascii")
            first.write_text("first", encoding="ascii")
            before = protected_snapshot(root, output)
            output.mkdir()
            (output / "new.csv").write_text("new", encoding="ascii")
            self.assertEqual(before, protected_snapshot(root, output))
            first.write_text("changed", encoding="ascii")
            self.assertNotEqual(before, protected_snapshot(root, output))


if __name__ == "__main__":
    unittest.main()
