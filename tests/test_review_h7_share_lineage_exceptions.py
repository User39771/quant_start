from __future__ import annotations

import inspect
import unittest
from pathlib import Path

import pandas as pd

from scripts import review_h7_share_lineage_exceptions as review


class H7ShareLineageExceptionReviewTests(unittest.TestCase):
    def test_review_sample_is_fixed_bounded_and_deterministic(self) -> None:
        root = Path(__file__).resolve().parents[1]
        first = review.select_review_sample(root)
        second = review.select_review_sample(root)
        pd.testing.assert_frame_equal(first, second)
        self.assertLessEqual(len(first), 15)
        self.assertTrue(set(review.FAILURE_CODES).issubset(set(first.stock_code)))
        self.assertTrue({"688004", "301683"}.issubset(set(first.stock_code)))

    def test_empty_raw_response_is_not_schema_mapped(self) -> None:
        result = review.normalize_raw_events({"records": []}, "000004")
        self.assertTrue(result.empty)
        self.assertIn("announcement_date", result)

    def test_normalization_uses_max_date_and_keeps_pre_event_unknown(self) -> None:
        payload = {"records": [{
            "SECCODE": "000001", "DECLAREDATE": "2020-01-05", "VARYDATE": "2020-01-02",
            "F003N": 10.0, "F021N": 8.0, "F028N": 2.0,
        }]}
        events = review.normalize_raw_events(payload, "000001")
        self.assertEqual(events.information_available_date.iloc[0], pd.Timestamp("2020-01-05"))
        self.assertEqual(events.total_shares.iloc[0], 100_000)
        lineage = review.build_point_in_time_shares(
            events, pd.Series(pd.to_datetime(["2020-01-04", "2020-01-05"]))
        )
        self.assertTrue(pd.isna(lineage.total_shares.iloc[0]))
        self.assertEqual(lineage.total_shares.iloc[1], 100_000)

    def test_post_cutoff_event_is_removed(self) -> None:
        payload = {"records": [{
            "SECCODE": "000001", "DECLAREDATE": "2026-08-21", "VARYDATE": "2026-08-20",
            "F003N": 10.0, "F021N": 8.0,
        }]}
        self.assertTrue(review.normalize_raw_events(payload, "000001").empty)

    def test_baostock_implied_circulating_formula(self) -> None:
        volume = 2_000_000.0
        turn_decimal = 0.02
        self.assertEqual(volume / turn_decimal, 100_000_000.0)

    def test_simple_ratio_feature_is_diagnostic_only(self) -> None:
        self.assertEqual(review.simple_ratio_label(4 / 3), "4/3")
        self.assertEqual(review.simple_ratio_label(1.23), "NO_SIMPLE_RATIO_WITHIN_2PCT")

    def test_root_cause_prefers_cross_source_evidence(self) -> None:
        row = pd.Series({
            "total_ratio_median": 1.4,
            "local_circulating_ratio_median": 1.4,
            "baostock_circ_vs_cninfo_median_error": 0.001,
            "large_total_error_fraction_in_change_announcement_gap": 0.0,
            "total_ratio_p95": 1.42,
        })
        self.assertEqual(
            review.root_cause(row),
            "LOCAL_TOTAL_AND_CIRCULATING_MARKET_CAP_LINEAGE_DISCREPANCY",
        )

    def test_no_forbidden_research_or_security_bypass(self) -> None:
        source = inspect.getsource(review).lower()
        for forbidden in (
            "verify=false", "verify = false", "statsmodels", "sklearn", "c2_hat",
            "c2_sign", "sharpe", "5195",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
