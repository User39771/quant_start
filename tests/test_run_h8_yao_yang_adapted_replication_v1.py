"""H8 frozen algebra, sample, order and drift tests; synthetic only."""

import ast
import inspect
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import run_h8_yao_yang_adapted_replication_v1 as m


class H8V1Tests(unittest.TestCase):
    def test_time_threshold_and_model_contracts(self):
        self.assertEqual(str(m.ANALYSIS_START.date()), "2020-02-11")
        self.assertEqual(str(m.FORMATION_CUTOFF.date()), "2026-08-19")
        self.assertEqual(str(m.FINAL_ENDPOINT.date()), "2026-08-20")
        self.assertEqual((m.PRIMARY_MIN_ROWS, m.LONG_MIN_ROWS), (750, 1000))
        self.assertEqual(
            m.h8.GARCH_KWARGS,
            dict(mean="Zero", vol="GARCH", p=1, q=1, dist="normal", rescale=False),
        )

    def test_preregistration_complete_before_runner(self):
        root = Path(m.__file__).resolve().parents[1]
        stamp = m.require_preregistration(root)
        self.assertGreater(stamp, 0)
        text = (root / m.PREREG).read_text(encoding="utf-8")
        self.assertIn("PRIMARY_750_ROLE_FIXED_BEFORE_GAMMA=true", text)
        self.assertIn("LONG_HISTORY_1000_ROLE_FIXED_BEFORE_GAMMA=true", text)

    def test_sample_freeze_counts_and_nesting(self):
        root = Path(m.__file__).resolve().parents[1]
        source = pd.read_csv(
            root / m.ext.OUT / "h8_extended_final_clean_stock_rows.csv",
            dtype={"stock_code": str},
        )
        frame = m.build_membership(source)
        self.assertEqual(frame.primary_750_member.sum(), 474)
        self.assertEqual(frame.long_history_1000_member.sum(), 312)
        self.assertFalse((frame.long_history_1000_member & ~frame.primary_750_member).any())
        self.assertTrue(frame[frame.primary_750_member].board.isin(["SH_MAIN", "SZ_MAIN"]).all())

    def test_design_exactly_11_no_standalone_return(self):
        r = np.array([-1.0, 0.0, 1.0, 2.0, -2.0])
        x = m.design_matrix(r, np.ones(5) * 2, np.ones(5) * 0.0004, np.arange(5))
        self.assertEqual(x.shape, (5, 11))
        self.assertEqual(len(m.X_NAMES), 11)
        self.assertNotIn("r", m.X_NAMES)
        np.testing.assert_array_equal((x[:, 1:6] != 0).sum(axis=1), [1, 0, 1, 1, 1])

    def test_scaling_sign_and_zero_dpos(self):
        self.assertEqual(m.scaling_fixture(1.0, 2.0, 0.0004, False), (2.0, 4.0, 0.0, 2.0, 0.4))
        self.assertEqual(m.scaling_fixture(-1.0, 2.0, 0.0004, True), (-2.0, -4.0, -2.0, 0.0, -0.4))
        x = m.design_matrix([0.0], [2.0], [0.0004], [0])
        self.assertEqual(x[0, 8], 0)
        self.assertEqual(x[0, 9], 0)  # D_POS is one, but r^3 is exactly zero.

    def test_simple_return_decomposition_not_additive(self):
        out, intra = 0.02, -0.01
        cc = (1 + out) * (1 + intra) - 1
        self.assertAlmostEqual(cc, out + intra + out * intra)
        self.assertNotEqual(cc, out + intra)

    def test_exact22_is_past_only_low_state_preserved(self):
        turn = pd.Series([1.0] * 22 + [0.5, np.e])
        v = m.h8.paper_v(turn, pd.Series(True, index=turn.index))
        self.assertTrue(v.iloc[:22].isna().all())
        self.assertEqual(v.iloc[22], 0)
        self.assertGreater(v.iloc[23], 0)

    def test_ols_full_rank_success_and_singular_failure(self):
        rng = np.random.default_rng(7)
        x = rng.normal(size=(100, 11))
        x[:, 0] = 1
        y = x @ np.arange(11) + rng.normal(size=100)
        good = m.ols_row("600000", "CLOSE_TO_CLOSE", x, y)
        self.assertEqual(good["regression_status"], "SUCCESS")
        bad = m.ols_row("600000", "CLOSE_TO_CLOSE", np.ones((100, 11)), y)
        self.assertEqual(bad["regression_status"], "REGRESSION_NUMERIC_FAILURE")

    def test_wilcoxon_fixed_one_sided_and_nonzero(self):
        stat, pvalue, n = m.signed_rank([-3, -2, -1, 0, 1])
        self.assertEqual(n, 4)
        self.assertTrue(np.isfinite(stat) and np.isfinite(pvalue))
        source = inspect.getsource(m.signed_rank)
        self.assertIn('alternative="less"', source)
        self.assertIn('zero_method="wilcox"', source)

    def test_long_history_reuses_coefficient_rows(self):
        wide = pd.DataFrame(
            {
                "delta_gamma_CLOSE_TO_CLOSE": [-1.0, -2.0],
                "delta_gamma_OVERNIGHT": [-0.1, -0.2],
                "delta_gamma_INTRADAY": [-0.9, -1.8],
            },
            index=["1", "2"],
        )
        membership = pd.DataFrame(
            {"stock_code": ["1", "2"], "long_history_1000_member": [True, False]}
        )
        result = m.long_summary(wide, membership)
        self.assertTrue(result.N.eq(1).all())

    def test_no_drift_search_or_other_research(self):
        source = Path(m.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        for banned in ("winsorize", "gamma31_cutoff", "price_limit", "h_share"):
            self.assertNotIn(banned, names)
        self.assertNotIn("run_h7", source)
        self.assertNotIn("TOTAL_SHARE_TURNOVER", source)
        self.assertNotIn("1250", inspect.getsource(m.fit_primary))
        self.assertNotIn("1500", inspect.getsource(m.fit_primary))


if __name__ == "__main__":
    unittest.main()
