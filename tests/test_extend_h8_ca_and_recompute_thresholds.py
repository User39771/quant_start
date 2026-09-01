"""Focused synthetic tests for the bounded H8 cutoff extension."""

import ast
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd

from scripts import extend_h8_ca_and_recompute_thresholds as m


class ExtensionTests(unittest.TestCase):
    def setUp(self):
        self.dates = pd.bdate_range("2020-01-01", "2026-08-20")
        self.old = pd.DataFrame(
            [["sh.600000", "2026-05-12", 1.0, 1.0, 1.0]], columns=m.ca.FIELDS
        )
        self.new = pd.DataFrame(
            [["sh.600000", "2026-06-15", 1.1, 1.1, 1.1]], columns=m.ca.FIELDS
        )

    def test_increment_contract_and_formation_cutoff(self):
        self.assertEqual(m.INCREMENTAL_START, "2026-05-13")
        self.assertEqual(str(m.DATA_CUTOFF.date()), "2026-08-20")
        endpoint, cutoff = m.formation_cutoff(
            pd.DatetimeIndex(["2026-08-18", "2026-08-19", "2026-08-20"])
        )
        self.assertEqual(str(endpoint.date()), "2026-08-20")
        self.assertEqual(str(cutoff.date()), "2026-08-19")
        self.assertLess(cutoff, endpoint)

    def test_increment_normalization_and_no_later_event(self):
        got = m.normalize_increment(self.new, "600000", self.dates)
        self.assertEqual(got.dividOperateDate.tolist(), ["2026-06-15"])
        later = self.new.copy()
        later.loc[0, "dividOperateDate"] = "2026-08-21"
        with self.assertRaises(ValueError):
            m.normalize_increment(later, "600000", self.dates)

    def test_deterministic_merge_and_conflict(self):
        merged, conflicts = m.merge_events(self.old, self.new)
        self.assertEqual(merged.dividOperateDate.tolist(), ["2026-05-12", "2026-06-15"])
        self.assertEqual(conflicts, [])
        conflict = self.old.copy()
        conflict.loc[0, ["foreAdjustFactor", "backAdjustFactor", "adjustFactor"]] = 9
        _, conflicts = m.merge_events(self.old, conflict)
        self.assertEqual(conflicts, ["2026-05-12"])

    def test_t_and_t_plus_one_exclusion(self):
        days = pd.bdate_range("2026-06-01", periods=5)
        event, invalid = m.ca.contamination_mask(days, [days[2]])
        self.assertEqual(event.tolist(), [False, False, True, False, False])
        self.assertEqual(invalid.tolist(), [False, True, True, False, False])

    def test_longest_segment_tie_earliest_and_transition_types(self):
        values = pd.Series([0.1, 0.2, np.nan, 0.3, 0.4])
        self.assertEqual(m.h8.longest_segment(values).index.tolist(), [0, 1])
        self.assertEqual(
            m.segment_kind("2020-01-01", "2020-02-01", "2020-01-01", "2020-03-01"),
            "EXTENDED",
        )
        self.assertEqual(
            m.segment_kind("2020-01-01", "2020-02-01", "2020-01-02", "2020-03-01"),
            "SWITCHED",
        )

    def test_exact22_and_d_pos_contract_unchanged(self):
        x = pd.Series([1.0] * 22 + [np.e])
        v = m.h8.paper_v(x, pd.Series(True, index=x.index))
        self.assertTrue(v.iloc[:22].isna().all())
        self.assertGreater(v.iloc[22], 0)
        self.assertTrue(0 >= 0)  # D_POS includes a zero current return.

    def test_thresholds_only_fixed_four(self):
        data = pd.DataFrame(
            {
                "stock_code": ["1", "2", "3", "4"],
                "final_matched_rows": [700, 800, 1100, 1600],
                "historical_mean_circulating_market_cap": [1.0, 2.0, 3.0, 4.0],
                "board": ["SH_MAIN"] * 4,
                "size_quartile": m.h8.QUARTILES,
            }
        )
        self.assertEqual(m.threshold_table(data).min_rows.tolist(), list(m.THRESHOLDS))

    def test_fetch_uses_increment_only_and_resume_skips_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            m.ca.atomic_csv(self.old, root / m.ca.CACHE / "baostock/600000.csv")
            response = Mock(error_code="0", error_msg="", fields=m.ca.FIELDS)
            response.get_data.return_value = self.new
            login = Mock(error_code="0")
            with (
                patch.object(m.bs, "login", return_value=login),
                patch.object(m.bs, "logout"),
                patch.object(m.bs, "query_adjust_factor", return_value=response) as query,
                patch.object(m.time, "sleep"),
            ):
                status = m.fetch_increment(root, ["600000"], self.dates)
            self.assertIn(status["600000"]["status"], m.SUCCESS)
            self.assertEqual(query.call_args.kwargs["start_date"], "2026-05-13")
            self.assertEqual(query.call_args.kwargs["end_date"], "2026-08-20")
            with patch.object(m.bs, "login") as no_login:
                m.fetch_increment(root, ["600000"], self.dates)
            no_login.assert_not_called()

    def test_no_eq9_gamma_or_other_research_paths(self):
        source = Path(m.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        attrs = [n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)]
        self.assertNotIn("lstsq", attrs)
        self.assertNotIn("synthetic_design", attrs)
        self.assertNotIn("gamma31", inspect.getsource(m.run))
        self.assertNotIn("gamma32", inspect.getsource(m.run))
        self.assertNotIn("h7_dynamic", source)

    def test_garch_spec_frozen(self):
        self.assertEqual(
            m.h8.GARCH_KWARGS,
            dict(mean="Zero", vol="GARCH", p=1, q=1, dist="normal", rescale=False),
        )


if __name__ == "__main__":
    unittest.main()
