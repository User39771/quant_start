"""Focused synthetic/data-contract checks; never run H8 outcome models."""

import ast
import inspect
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from arch import arch_model

from scripts import resolve_h8_final_contract as m


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.index = pd.bdate_range("2021-01-01", periods=60)
        self.turn = pd.Series(1.0, index=self.index)
        self.active = pd.Series(True, index=self.index)

    def test_exact22_warmup(self):
        v = m.paper_v(self.turn, self.active)
        self.assertTrue(v.iloc[:22].isna().all())
        self.assertEqual(v.iloc[22], 0)

    def test_t_excluded(self):
        self.turn.iloc[22] = np.e
        self.assertAlmostEqual(m.paper_v(self.turn, self.active).iloc[22], 1)

    def test_gap_not_last_active(self):
        self.active.iloc[10] = False
        v = m.paper_v(self.turn, self.active)
        self.assertTrue(v.iloc[32:33].isna().all())
        self.assertEqual(v.iloc[33], 0)

    def test_zero_and_nonfinite_turnover_invalid(self):
        for value in (0, -1, np.inf, np.nan):
            turn = self.turn.copy()
            turn.iloc[25] = value
            self.assertTrue(np.isnan(m.paper_v(turn, self.active).iloc[26]))

    def test_low_turnover_retained(self):
        self.turn.iloc[22] = 0.5
        v = m.paper_v(self.turn, self.active)
        self.assertEqual(v.iloc[22], 0)
        self.assertEqual(len(v), 60)

    def test_no_future_turnover_dependency(self):
        original = m.paper_v(self.turn, self.active)
        self.turn.iloc[40:] = 100
        pd.testing.assert_series_equal(
            original.iloc[:40], m.paper_v(self.turn, self.active).iloc[:40]
        )

    def test_zero_in_positive(self):
        r = np.array([-1.0, 0.0, 1.0])
        np.testing.assert_array_equal(r >= 0, [False, True, True])
        x = m.synthetic_design(r / 100, np.ones(3), np.ones(3) * 0.0004, np.arange(3))
        self.assertEqual(x.iloc[1, 0], 1)
        self.assertTrue(x.iloc[1, 1:].eq(0).all())

    def test_simple_formulas_and_multiplicative_identity(self):
        close, opening, closing = 100, 102, 101
        cc, overnight, intraday = closing / close - 1, opening / close - 1, closing / opening - 1
        self.assertAlmostEqual(cc, 0.01)
        self.assertAlmostEqual(overnight, 0.02)
        self.assertAlmostEqual(1 + cc, (1 + overnight) * (1 + intraday))
        self.assertNotAlmostEqual(cc, overnight + intraday)

    def test_constant_ratio_no_flags(self):
        raw = pd.Series([10.0, 20.0, 15.0])
        factor, pair, flags = m.factor_transitions(raw, raw * 0.75)
        self.assertTrue(factor.eq(0.75).all())
        self.assertEqual(pair.sum(), 2)
        self.assertEqual(flags.sum(), 0)

    def test_transition_detected(self):
        _, pairs, flags = m.factor_transitions(
            pd.Series([10.0] * 5), pd.Series([5.0, 5.0, 8.0, 8.0, 8.0])
        )
        self.assertEqual(flags.tolist(), [False, False, True, False, False])
        clean = m.transition_clean_rows(pairs, flags)
        self.assertEqual(clean.tolist(), [False, False, False, True, False])

    def test_missing_factor_not_clean(self):
        _, pair, flags = m.factor_transitions(
            pd.Series([10.0] * 4), pd.Series([5.0, np.nan, 5.0, 5.0])
        )
        self.assertFalse(m.transition_clean_rows(pair, flags).any())

    def test_detector_no_future_shift(self):
        raw = pd.Series([10.0] * 5)
        q = pd.Series([5.0] * 5)
        before = m.factor_transitions(raw, q)[2]
        q.iloc[4] = 8
        pd.testing.assert_series_equal(before.iloc[:4], m.factor_transitions(raw, q)[2].iloc[:4])

    def test_fixed_tolerance_and_rounded_ratio_jitter(self):
        raw = pd.Series([18.85, 19.17, 19.20])
        q = pd.Series([15.06, 15.32, 15.34])
        self.assertEqual(m.factor_transitions(raw, q)[2].sum(), 2)
        source = inspect.getsource(m.factor_transitions)
        self.assertIn("rtol=1e-6, atol=1e-10", source)

    def test_no_mixed_raw_and_qfq_return(self):
        source = inspect.getsource(m.run)
        self.assertIn("raw.close / raw.close.shift(1) - 1", source)
        self.assertNotIn("qfq_close /", source)
        self.assertNotIn("synthetic_design(", source)

    def test_garch_fixed_model(self):
        self.assertEqual(
            m.GARCH_KWARGS, dict(mean="Zero", vol="GARCH", p=1, q=1, dist="normal", rescale=False)
        )

    def test_garch_decimal_input_not_rescaled(self):
        returns = pd.Series([0.01, -0.02, 0.015], index=self.index[:3])
        with patch.object(m, "arch_model", side_effect=RuntimeError("fixture")) as model:
            result = m.garch_probe(returns)
        pd.testing.assert_series_equal(model.call_args.args[0], returns)
        self.assertFalse(result["success"])
        self.assertIn("fixture", result["error"])

    def test_garch_synthetic_positive_aligned(self):
        returns = pd.Series(
            np.random.default_rng(7).normal(0, 0.02, 1500),
            index=pd.bdate_range("2000-01-03", periods=1500),
        )
        result = m.garch_probe(returns)
        self.assertTrue(result["success"], result)
        self.assertEqual(result["nobs"], 1500)
        self.assertTrue(result["date_alignment"])

    def test_variance_recursion_uses_past_with_fixed_backcast(self):
        r = np.random.default_rng(4).normal(0, 0.02, 100)
        model = arch_model(r, **m.GARCH_KWARGS)
        parameters = np.array([0.00001, 0.05, 0.90])
        bounds = np.tile([1e-12, 1.0], (len(r), 1))
        a, b = np.zeros(len(r)), np.zeros(len(r))
        model.volatility.compute_variance(parameters, r, a, 0.0004, bounds)
        modified = r.copy()
        modified[50:] *= 2
        model.volatility.compute_variance(parameters, modified, b, 0.0004, bounds)
        np.testing.assert_allclose(a[:51], b[:51], atol=0, rtol=0)
        self.assertNotEqual(a[51], b[51])
        self.assertAlmostEqual(a[51], 0.00001 + 0.05 * r[50] ** 2 + 0.9 * a[50])

    def test_garch_gap_not_compressed(self):
        r = pd.Series([0.01, 0.02, np.nan, 0.03, 0.04, 0.05], index=self.index[:6])
        pd.testing.assert_series_equal(m.longest_segment(r), r.iloc[3:])

    def test_scaling_and_cubic(self):
        x = m.synthetic_design(
            np.array([0.01, -0.01]),
            np.array([2.0, 2.0]),
            np.array([0.0004, 0.0004]),
            np.array([0, 1]),
        )
        self.assertEqual(x.MON_times_r_pp.iloc[0], 1)
        self.assertEqual(x.V_times_r_pp.iloc[0], 2)
        self.assertEqual(x.V2_times_r_pp.iloc[0], 4)
        self.assertEqual(x.D_POS_V_r_pp_cubed.iloc[0], 2)
        self.assertEqual(x.D_NEG_V_r_pp_cubed.iloc[1], -2)
        self.assertAlmostEqual(x.variance_interaction.iloc[0], 0.4)

    def test_weekday_full_rank_no_standalone(self):
        rng = np.random.default_rng(11)
        x = m.synthetic_design(
            rng.normal(0, 0.02, 500),
            rng.uniform(0, 2, 500),
            rng.uniform(0.0001, 0.001, 500),
            np.arange(500) % 5,
        )
        self.assertEqual(x.shape[1], 11)
        self.assertEqual(np.linalg.matrix_rank(x), 11)
        self.assertNotIn("r_pp", x.columns)

    def test_mainboards_only(self):
        self.assertEqual(m.board("000001"), "SZ_MAIN")
        self.assertEqual(m.board("603000"), "SH_MAIN")
        for code in ("300001", "301001", "688001", "900001", "200001", "830001"):
            self.assertEqual(m.board(code), "EXCLUDED_BOARD")

    def test_st_whole_stock_all_observed_history(self):
        source = inspect.getsource(m.load_raw)
        self.assertIn("raw.is_st.eq(1).any()", source)
        self.assertIn("~audit.observed_ever_st", inspect.getsource(m.run))

    def test_only_four_thresholds(self):
        self.assertEqual(m.THRESHOLDS, (750, 1000, 1250, 1500))
        self.assertNotIn("gamma", inspect.getsource(m.threshold_comparison))

    def test_upper_bounds_never_promoted_to_final_rows(self):
        n = 16
        frame = pd.DataFrame(
            {
                "raw_p1_upper_bound": np.arange(n) * 100 + 10,
                "overlap_p1_upper_bound": np.arange(n) * 80 + 10,
                "historical_mean_circulating_market_cap": np.arange(n) + 1.0,
                "board": ["SH_MAIN", "SZ_MAIN"] * 8,
                "size_quartile": list(m.QUARTILES) * 4,
                "overlap_first_formation": ["2020-12-29"] * n,
                "cache_first_date": ["2020-01-02"] * n,
                "active_ohlc_history_to_audit_cutoff": np.arange(n) * 100 + 30,
            }
        )
        table = m.threshold_comparison(frame)
        final = table.loc[table.basis.eq("FINAL_POTENTIAL_H8_ROWS")]
        self.assertEqual(len(table), 12)
        self.assertEqual(tuple(final.min_rows), m.THRESHOLDS)
        self.assertTrue(final.stock_count.eq("UNKNOWN").all())
        self.assertTrue(final.size_quartile_inclusion_spread.eq("UNKNOWN").all())

    def test_failed_garch_kept(self):
        result = m.garch_probe(pd.Series([np.nan, 0.01]))
        self.assertFalse(result["success"])
        self.assertEqual(result["nobs"], 2)
        self.assertIn("insufficient_or_nonfinite", result["error"])

    def test_no_h7_import_or_other_runner(self):
        tree = ast.parse(Path(m.__file__).read_text(encoding="utf-8"))
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        self.assertFalse(any("h7" in (i or "").lower() for i in imports))
        names = [n.id for n in ast.walk(tree) if isinstance(n, ast.Name)]
        for name in ("OLS", "WLS", "lstsq", "subprocess", "requests", "akshare", "backtest"):
            self.assertNotIn(name, names)
        fit_calls = [
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "fit"
        ]
        self.assertEqual(len(fit_calls), 1)

    def test_matched_raw_presence_cutoff(self):
        dates = pd.bdate_range("2026-03-01", "2026-05-15")
        raw = pd.DataFrame(
            dict(close=10.0, open=9.9, trading_status=1, baostock_circulating_turnover=1.0),
            index=dates,
        )
        a, b, _ = m.raw_presence(raw, dates)
        self.assertEqual(a.sum(), b.sum())
        self.assertFalse(a.loc[a.index > m.CUTOFF].any())
        raw.loc["2026-05-12", "open"] = np.nan
        a, b, _ = m.raw_presence(raw, dates)
        self.assertTrue(a.loc["2026-05-11"])
        self.assertFalse(b.loc["2026-05-11"])

    def test_no_fake_price_limit_or_ah(self):
        source = inspect.getsource(m.run)
        self.assertNotIn("limit_status", source)
        self.assertNotIn("H_share", source)
        self.assertNotIn("synthetic_design", source)

    def test_probe_budget_and_reproducibility(self):
        frame = pd.DataFrame(
            {
                "stock_code": [str(i) for i in range(100)],
                "board": ["SH_MAIN"] * 50 + ["SZ_MAIN"] * 50,
                "size_quartile": list(m.QUARTILES) * 25,
                "overlap_p1_upper_bound": np.arange(100),
            }
        )
        a = m.choose_probe(frame)
        self.assertEqual(len(a), 50)
        self.assertEqual(len(set(a)), 50)
        self.assertEqual(a, m.choose_probe(frame.sample(frac=1, random_state=4)))


if __name__ == "__main__":
    unittest.main()
