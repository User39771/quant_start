from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import pandas as pd


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "build_adjusted_price_panel_QA_v1_2.py"
SPEC = importlib.util.spec_from_file_location("build_adjusted_price_panel_QA_v1_2", MODULE_PATH)
qa = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = qa
SPEC.loader.exec_module(qa)


class AdjustedPricePanelQAV12Tests(unittest.TestCase):
    def base_panel(self) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "stock_code": ["000063", "300857"],
                "trade_date": ["2026-01-02", "2026-01-02"],
                "close": [10.0, 20.0],
                "qfq_close": [10.0, 20.0],
                "adjusted_close": [10.0, 20.0],
                "qfq_open": [9.5, 19.5],
                "qfq_high": [10.5, 20.5],
                "qfq_low": [9.0, 19.0],
                "source_qfq": ["ak.stock_zh_a_daily", None],
                "adjusted_flag": ["true", "true"],
            }
        )

    def test_duplicate_stock_date_is_identified(self):
        panel = pd.concat([self.base_panel().iloc[[0]], self.base_panel().iloc[[0]]], ignore_index=True)
        result = qa.analyze(panel, ["000063"], pd.DataFrame())

        self.assertTrue((result.issues["issue_type"] == "duplicate_stock_date").any())

    def test_leading_zero_loss_is_high_severity(self):
        panel = self.base_panel()
        panel.loc[0, "stock_code"] = "63"
        result = qa.analyze(panel, ["000063", "300857"], pd.DataFrame())
        hit = result.issues[result.issues["issue_type"].eq("stock_code_not_6_digit")]

        self.assertEqual(hit.iloc[0]["severity"], "High")

    def test_clean_code6_has_no_stock_code_issue(self):
        panel = self.base_panel()
        panel.loc[0, "stock_code"] = "000063"
        panel.loc[1, "stock_code"] = "002049"
        result = qa.analyze(panel, ["000063", "002049"], pd.DataFrame())

        self.assertFalse((result.issues["issue_type"] == "stock_code_not_6_digit").any())

    def test_invalid_date_is_identified_with_pandas_parse(self):
        panel = self.base_panel()
        panel.loc[0, "trade_date"] = "not-a-date"
        result = qa.analyze(panel, ["000063", "300857"], pd.DataFrame())

        self.assertTrue((result.issues["issue_type"] == "invalid_trade_date").any())

    def test_adjusted_flag_true_requires_positive_qfq_close(self):
        panel = self.base_panel()
        panel.loc[0, "qfq_close"] = 0
        result = qa.analyze(panel, ["000063", "300857"], pd.DataFrame())

        self.assertTrue((result.issues["issue_type"] == "invalid_qfq_close_when_adjusted").any())

    def test_adjusted_close_must_equal_qfq_close(self):
        panel = self.base_panel()
        panel.loc[0, "adjusted_close"] = 9
        result = qa.analyze(panel, ["000063", "300857"], pd.DataFrame())

        self.assertTrue((result.issues["issue_type"] == "adjusted_close_mismatch").any())

    def test_coverage_gate_allows_baseline_when_clean_and_above_threshold(self):
        result = qa.analyze(self.base_panel(), ["000063", "300857"], pd.DataFrame())

        self.assertTrue(result.decisions["adjusted_return_baseline_allowed"])

    def test_coverage_below_threshold_blocks_baseline(self):
        panel = self.base_panel()
        panel.loc[1, "adjusted_flag"] = "false"
        panel.loc[1, "adjusted_close"] = pd.NA
        panel.loc[1, "qfq_close"] = pd.NA
        result = qa.analyze(panel, ["000063", "300857"], pd.DataFrame())

        self.assertFalse(result.decisions["adjusted_return_baseline_allowed"])

    def test_latest_manifest_status_wins(self):
        manifest = pd.DataFrame(
            {
                "stock_code": ["000063", "000063"],
                "fetched_at": ["2026-01-01T00:00:00+00:00", "2026-01-02T00:00:00+00:00"],
                "run_id": ["a", "b"],
                "final_status": ["error", "ok"],
            }
        )
        latest = qa.latest_manifest_status(manifest)

        self.assertEqual(latest.loc["000063", "final_status"], "ok")

    def test_manifest_caveats_do_not_block_clean_baseline(self):
        manifest = pd.DataFrame(
            {
                "stock_code": ["000063", "300857"],
                "fetched_at": ["2026-01-02T00:00:00+00:00", "2026-01-02T00:00:00+00:00"],
                "run_id": ["a", "a"],
                "final_status": ["error", "partial_ok"],
            }
        )
        result = qa.analyze(self.base_panel(), ["000063", "300857"], manifest)
        caveats = result.issues[result.issues["issue_type"].isin(["manifest_error_status", "manifest_partial_ok_status"])]

        self.assertTrue(result.decisions["adjusted_return_baseline_allowed"])
        self.assertEqual(set(caveats["severity"]), {"Medium"})

    def test_source_distribution_labels_missing(self):
        result = qa.analyze(self.base_panel(), ["000063", "300857"], pd.DataFrame())

        self.assertIn("missing", set(result.source_distribution["source_qfq"]))


if __name__ == "__main__":
    unittest.main()
