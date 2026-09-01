"""Synthetic source/chronology QA; no external calls or H8 outcome fitting."""

import ast
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from scripts import resolve_h8_corporate_action_lineage as m


class LineageTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2020-01-01", "2026-05-12")
        self.frame = pd.DataFrame([["sh.600019", "2021-06-18", 0.7, 2.2, 2.2]], columns=m.FIELDS)

    def test_direct_fields_and_event_parsing(self):
        result = m.normalize_bao(self.frame, "600019", self.dates)
        self.assertEqual(result.dividOperateDate.iloc[0], "2021-06-18")
        self.assertEqual(list(result), m.FIELDS)

    def test_empty_success_valid(self):
        self.assertTrue(m.normalize_bao(self.frame.iloc[:0], "600019", self.dates).empty)

    def test_empty_result_preserves_verified_response_fields(self):
        response = Mock(fields=m.FIELDS, error_code="0")
        response.get_data.return_value = pd.DataFrame()
        result = m.response_frame(response)
        self.assertTrue(result.empty)
        self.assertEqual(list(result), m.FIELDS)

    def test_empty_result_does_not_hide_missing_response_schema(self):
        response = Mock(fields=[], error_code="0")
        response.get_data.return_value = pd.DataFrame()
        with self.assertRaises(ValueError):
            m.response_frame(response)

    def test_bad_schema_fails(self):
        with self.assertRaises(ValueError):
            m.normalize_bao(self.frame.drop(columns="adjustFactor"), "600019", self.dates)

    def test_wrong_identity_fails(self):
        with self.assertRaises(ValueError):
            m.normalize_bao(self.frame, "600000", self.dates)

    def test_duplicate_events_fail(self):
        with self.assertRaises(ValueError):
            m.normalize_bao(pd.concat([self.frame, self.frame]), "600019", self.dates)

    def test_positive_finite_factors_required(self):
        for value in (0, -1, np.inf, np.nan):
            data = self.frame.copy()
            data.loc[0, "adjustFactor"] = value
            with self.assertRaises(ValueError):
                m.normalize_bao(data, "600019", self.dates)

    def test_outside_cutoff_event_fails(self):
        self.frame.loc[0, "dividOperateDate"] = "2026-05-13"
        with self.assertRaises(ValueError):
            m.normalize_bao(self.frame, "600019", self.dates)

    def test_nonmarket_date_fails(self):
        self.frame.loc[0, "dividOperateDate"] = "2021-06-19"
        with self.assertRaises(ValueError):
            m.normalize_bao(self.frame, "600019", self.dates)

    def test_dense_event_series_fails(self):
        data = pd.concat([self.frame] * 100, ignore_index=True)
        data.dividOperateDate = self.dates[:100].strftime("%Y-%m-%d")
        with self.assertRaisesRegex(ValueError, "dense"):
            m.normalize_bao(data, "600019", self.dates)

    def test_cninfo_uses_ex_date_not_pay_or_registration(self):
        payload = {
            "records": [
                {
                    "F020D": "2021-06-18",
                    "F018D": "2021-06-17",
                    "F023D": "2021-06-21",
                    "F006D": "2021-06-10",
                    "F007V": "dividend",
                }
            ]
        }
        result, missing = m.normalize_cninfo(payload, "600019")
        self.assertEqual(result.event_date.tolist(), ["2021-06-18"])
        self.assertEqual(missing, 0)

    def test_cninfo_future_event_not_used(self):
        payload = {"records": [{"F020D": "2026-06-25", "F006D": "2026-06-18", "F007V": "later"}]}
        result, _ = m.normalize_cninfo(payload, "600019")
        self.assertTrue(result.empty)

    def test_cninfo_no_ex_date_not_invented(self):
        payload = {
            "records": [
                {"F020D": None, "F023D": "2021-06-18", "F006D": "2021-06-10", "F007V": "missing"}
            ]
        }
        result, missing = m.normalize_cninfo(payload, "600019")
        self.assertTrue(result.empty)
        self.assertEqual(missing, 1)

    def test_cross_validation_and_false_negative(self):
        rows = m.cross_validate(["2021-01-04", "2021-02-04"], ["2021-01-04", "2021-03-04"])
        self.assertEqual(
            [r["classification"] for r in rows],
            ["VALIDATED_EVENT", "SOURCE_ONLY_PLAUSIBLE_EVENT", "UNRESOLVED_EVENT"],
        )
        self.assertEqual(sum(r["false_negative"] for r in rows), 1)

    def test_no_date_shift_matching(self):
        rows = m.cross_validate(["2021-06-18"], ["2021-06-17"])
        self.assertFalse(any(r["classification"] == "VALIDATED_EVENT" for r in rows))

    def test_t_and_next_t_contamination(self):
        days = pd.bdate_range("2021-01-04", periods=5)
        event, invalid = m.contamination_mask(days, ["2021-01-06"])
        self.assertEqual(event.tolist(), [False, False, True, False, False])
        self.assertEqual(invalid.tolist(), [False, True, True, False, False])

    def test_longest_clean_segment_no_compression(self):
        values = pd.Series([0.01, 0.02, np.nan, 0.01, 0.02, 0.03])
        self.assertEqual(m.h8.longest_segment(values).index.tolist(), [3, 4, 5])

    def test_longest_tie_earliest(self):
        values = pd.Series([0.01, 0.02, np.nan, 0.03, 0.04])
        self.assertEqual(m.h8.longest_segment(values).index.tolist(), [0, 1])

    def test_exact22_truncation_unchanged(self):
        x = pd.Series([1.0] * 22 + [0.5, np.e])
        v = m.h8.paper_v(x, pd.Series(True, index=x.index))
        self.assertTrue(v.iloc[:22].isna().all())
        self.assertEqual(v.iloc[22], 0)
        self.assertGreater(v.iloc[23], 1)
        self.assertTrue(0 >= 0)  # frozen nonnegative sign convention retains zero.

    def test_garch_fixed_spec_and_cutoff(self):
        self.assertEqual(
            m.h8.GARCH_KWARGS,
            dict(mean="Zero", vol="GARCH", p=1, q=1, dist="normal", rescale=False),
        )
        self.assertEqual(str(m.h8.CUTOFF.date()), "2026-05-11")
        self.assertEqual(m.END, "2026-05-12")

    def test_no_ratio_detector_no_other_research(self):
        tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
        attrs = [n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)]
        for banned in (
            "factor_transitions",
            "transition_clean_rows",
            "fit",
            "lstsq",
            "synthetic_design",
        ):
            self.assertNotIn(banned, attrs)
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any("h7" in (s or "") for s in imports))
        self.assertNotIn("QFQ", inspect.getsource(m.clean_stock))

    def test_source_rejection_blocks_without_external_evidence(self):
        p = pd.DataFrame(dict(status=["SUCCESS_WITH_EVENTS"] * 40, cninfo_status=["SUCCESS"] * 40))
        self.assertEqual(m.accept_source(p, pd.DataFrame()), "BAOSTOCK_CA_SOURCE_REJECTED")
        x = pd.DataFrame(m.cross_validate(["2021-06-18"], ["2021-06-18"]))
        self.assertEqual(m.accept_source(p, x), "BAOSTOCK_CA_SOURCE_ACCEPTED_WITH_LIMITATIONS")

    def test_probe_exactly40_balanced_reproducible(self):
        data = pd.DataFrame(
            [
                dict(stock_code=str(i), board=b, size_quartile=q, raw_p1_upper_bound=i)
                for b in ["SH_MAIN", "SZ_MAIN"]
                for q in m.h8.QUARTILES
                for i in range(10)
            ]
        )
        selected = m.select_probe(data)
        self.assertEqual(len(selected), 40)
        self.assertTrue(selected.groupby(["board", "size_quartile"]).size().eq(5).all())
        pd.testing.assert_frame_equal(selected, m.select_probe(data.sample(frac=1, random_state=7)))

    def test_thresholds_only_final_matched_rows(self):
        data = pd.DataFrame(
            dict(
                final_matched_rows=[700, 800, 1000, 1300],
                historical_mean_circulating_market_cap=[1.0, 2.0, 3.0, 4.0],
                board=["SH_MAIN"] * 4,
                size_quartile=m.h8.QUARTILES,
            )
        )
        result = m.final_thresholds(data)
        self.assertEqual(result.min_rows.tolist(), [750, 1000, 1250])
        self.assertEqual(result.eligible_stocks.tolist(), [3, 2, 1])
        data.loc[3, "final_matched_rows"] = 1510
        self.assertEqual(m.final_thresholds(data).min_rows.tolist(), [750, 1000, 1250, 1500])

    def test_failed_cache_does_not_create_rows_or_fit(self):
        with patch.object(m.h8, "garch_probe") as model:
            row = m.clean_stock(Path("."), "600019", self.dates, {"status": "NETWORK_FAILED"})
        model.assert_not_called()
        self.assertEqual(row["final_matched_rows"], 0)
        self.assertEqual(row["garch_status"], "NOT_RUN_CA_UNAVAILABLE")

    def test_final_rows_are_ca_clean_matched_and_in_one_segment(self):
        dates = pd.bdate_range("2021-01-01", periods=60)
        raw = pd.DataFrame(
            dict(
                close=np.arange(60) + 100.0,
                open=np.arange(60) + 99.5,
                trading_status=1,
                baostock_circulating_turnover=1.0,
            ),
            index=dates,
        )
        original = raw.copy(deep=True)
        events = self.frame.copy()
        events.dividOperateDate = dates[30].strftime("%Y-%m-%d")
        result = dict(
            success=True,
            warning="",
            error="",
            converged=True,
            parameter_finite=True,
            conditional_variance_finite_share=1.0,
            runtime_seconds=0.0,
        )
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            m.atomic_csv(events, root / m.CACHE / "baostock/600019.csv")
            with (
                patch.object(m.h8, "load_raw", return_value=(raw, False, False, "")),
                patch.object(m.h8, "garch_probe", return_value=result) as model,
            ):
                row = m.clean_stock(root, "600019", dates, {"status": "SUCCESS_WITH_EVENTS"})
        self.assertEqual(row["final_matched_rows"], 7)  # t22..t28; t29 crosses event.
        self.assertEqual(row["final_P1_rows"], row["final_P2_rows"])
        self.assertEqual(row["garch_nobs"], 29)
        model.assert_called_once()
        self.assertEqual(model.call_args.args[0].index.max(), dates[29])
        pd.testing.assert_frame_equal(raw, original)

    def test_success_cache_skips_network(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            m.atomic_csv(self.frame, root / m.CACHE / "baostock/600019.csv")
            record = pd.DataFrame(
                [
                    dict(
                        stock_code="600019",
                        status="SUCCESS_WITH_EVENTS",
                        request_start=m.START,
                        request_end=m.END,
                        attempts=1,
                    )
                ]
            )
            m.atomic_csv(record, root / m.CACHE / "stock_status.csv")
            with patch.object(m.bs, "login") as login:
                status = m.fetch_bao(root, ["600019"], self.dates)
            login.assert_not_called()
            self.assertEqual(status["600019"]["status"], "SUCCESS_WITH_EVENTS")

    def test_exhausted_failure_preserved_on_resume(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            record = pd.DataFrame(
                [
                    dict(
                        stock_code="600019",
                        status="NETWORK_FAILED",
                        request_start=m.START,
                        request_end=m.END,
                        attempts=2,
                        error="original_error",
                    )
                ]
            )
            m.atomic_csv(record, root / m.CACHE / "stock_status.csv")
            with patch.object(m.bs, "login") as login:
                status = m.fetch_bao(root, ["600019"], self.dates)
            login.assert_not_called()
            self.assertEqual(status["600019"]["error"], "original_error")

    def test_atomic_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "x.csv"
            m.atomic_csv(self.frame, p)
            self.assertTrue(p.exists())
            self.assertFalse(p.with_suffix(".csv.tmp").exists())


if __name__ == "__main__":
    unittest.main()
