from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts/audit_atr_measurement_feasibility.py"
SPEC = importlib.util.spec_from_file_location("atr_audit", MODULE_PATH)
assert SPEC and SPEC.loader
ATR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(ATR)


class AtrFeasibilityAuditTests(unittest.TestCase):
    def test_probe_is_bounded_and_deterministic(self) -> None:
        left = ATR.select_probe_sample(ROOT)
        right = ATR.select_probe_sample(ROOT)
        self.assertLessEqual(len(left), 30)
        self.assertEqual(left["stock_code"].tolist(), right["stock_code"].tolist())
        self.assertEqual(set(left["board"]), {"SH_MAIN", "SZ_MAIN", "CHINEXT", "STAR"})
        self.assertEqual(set(left["size_quartile"]), {"Q1_SMALL", "Q2", "Q3", "Q4_LARGE"})

    def test_title_classification_is_mechanical(self) -> None:
        found = ATR.classify_title("关于回购股份及聘任董事会秘书的公告")
        self.assertIn("repurchase", found)
        self.assertIn("managerial_turnover", found)

    def test_signed_residual_contract(self) -> None:
        residuals = np.array([0.03, -0.02, -0.01])
        self.assertAlmostEqual(float(residuals.sum()), 0.0)
        self.assertNotEqual(float(np.abs(residuals).sum()), float(residuals.sum()))

    def test_event_window_is_not_invented(self) -> None:
        self.assertEqual(ATR.EVENT_WINDOW_CONTRACT, "UNRESOLVED_FROM_TEXT")

    def test_resume_preserves_failed_requests_and_only_fills_missing_keys(self) -> None:
        sample = pd.DataFrame(
            [
                dict(
                    stock_code="000001",
                    board="SZ_MAIN",
                    size_quartile="Q1_SMALL",
                    sw_industry="bank",
                )
            ]
        )
        rows = [
            dict(
                row_type="stock_year_summary",
                stock_code="000001",
                year=year,
                status="FAILED" if year == 2020 else "SUCCESS",
                error="original failure" if year == 2020 else "",
            )
            for year in range(2020, 2026)
        ]
        rows += [
            dict(row_type="parameter_test", stock_code="000001", probe_type=kind, status="FAILED")
            for kind in ("keyword", "category")
        ]
        with tempfile.TemporaryDirectory() as directory:
            checkpoint = Path(directory) / "probe.csv"
            pd.DataFrame(rows).to_csv(checkpoint, index=False)
            with (
                patch.object(ATR, "_cninfo_session") as session,
                patch.object(ATR, "_cninfo_query") as query,
            ):
                session.return_value = (unittest.mock.Mock(), {"000001": "org"})
                query.return_value = {"announcements": [], "totalAnnouncement": 0}
                result = ATR.run_announcement_probe(sample, checkpoint)
                query.assert_called_once()
                self.assertEqual(query.call_args.args[3:5], ("2026-01-01", "2026-08-20"))
                self.assertEqual(
                    result.loc[result.error.eq("original failure"), "status"].tolist(), ["FAILED"]
                )
            before = checkpoint.read_bytes()
            with patch.object(
                ATR, "_cninfo_session", side_effect=AssertionError("network forbidden")
            ):
                resumed = ATR.run_announcement_probe(sample, checkpoint)
            self.assertEqual(len(resumed), 9)
            self.assertEqual(checkpoint.read_bytes(), before)

    def test_first_page_success_does_not_prove_scalability_or_count_nan_candidates(self) -> None:
        probe = pd.DataFrame(
            [
                dict(row_type="stock_year_summary", status="SUCCESS", stock_code="000001"),
                dict(
                    row_type="announcement_sample",
                    status="SUCCESS",
                    stock_code="000001",
                    event_candidates=np.nan,
                    announcement_date=np.nan,
                ),
            ]
        )
        events = ATR.event_feasibility(probe, {"stock_count": 3, "row_count": 260}).set_index(
            "event_category"
        )
        self.assertEqual(events.loc["probe_pipeline", "probe_candidate_rows"], 0)
        self.assertEqual(events.loc["probe_pipeline", "announcement_date_nonmissing_rate"], 0)
        self.assertEqual(
            events.loc["probe_pipeline", "feasibility_status"],
            "SCALABILITY_NOT_ESTABLISHED_BY_FIRST_PAGE_PROBE",
        )

    def test_source_has_no_forbidden_research_actions(self) -> None:
        source = MODULE_PATH.read_text(encoding="utf-8").lower()
        forbidden_calls = (
            "fama_macbeth",
            "portfolio_sort(",
            "sharpe_ratio(",
            "run_hypothesis_9",
        )
        for token in forbidden_calls:
            self.assertNotIn(token, source)


if __name__ == "__main__":
    unittest.main()
