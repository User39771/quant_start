import unittest

import numpy as np
import pandas as pd

from scripts.run_theme_breadth_diagnostic_v1_7 import (
    association_statistics,
    circular_shift_pvalue,
    classify_acceptance,
    portfolio_daily_stats,
    stable_core,
    tie_aware_terciles,
)


class ThemeBreadthHypothesisV17Tests(unittest.TestCase):
    def test_tie_aware_terciles_never_split_equal_values(self):
        values = pd.Series([0.1, 0.2, 0.2, 0.2, 0.7, 0.8])
        states, lower, upper = tie_aware_terciles(values)
        self.assertLess(lower, upper)
        self.assertEqual(states.loc[values.eq(0.2)].nunique(), 1)
        self.assertEqual(states.tolist(), ["low", "middle", "middle", "middle", "high", "high"])
        equal_states, equal_lower, equal_upper = tie_aware_terciles(pd.Series([0.5] * 6))
        self.assertEqual(equal_lower, equal_upper)
        self.assertEqual(equal_states.value_counts().to_dict(), {"middle": 6})

    def test_circular_shift_is_exact_and_deterministic(self):
        x = pd.Series([1, 2, 3, 4, 5], dtype=float)
        y = pd.Series([1, 2, 3, 4, 5], dtype=float)
        first = circular_shift_pvalue(x, y)
        self.assertEqual(first, circular_shift_pvalue(x, y))
        self.assertEqual(first, 0.2)

    def test_daily_nav_has_positive_mdd_magnitude(self):
        dates = pd.date_range("2024-01-01", periods=4, freq="D")
        lookup = pd.DataFrame(
            {"000001": [10.0, 12.0, 9.0, 11.0], "000002": [20.0, 20.0, 18.0, 22.0]}, index=dates
        )
        stats = portfolio_daily_stats(
            ["000001", "000002"], dates[0], dates[-1], list(dates), lookup
        )
        self.assertTrue(stats["daily_risk_valid"])
        self.assertLessEqual(stats["raw_mdd"], 0)
        self.assertGreaterEqual(stats["mdd_magnitude"], 0)
        self.assertAlmostEqual(stats["mdd_magnitude"], -stats["raw_mdd"])

    def test_acceptance_hierarchy_requires_stable_overall_core(self):
        n = 50
        base = {
            "n": n,
            "spearman": 0.30,
            "exclude_top1_spearman": 0.29,
            "exclude_top3_spearman": 0.28,
            "loo_sign_match_ratio": 1.0,
            "top3_abs_contribution_share": 0.20,
        }
        weak = {**base, "spearman": 0.0, "exclude_top1_spearman": 0.0, "exclude_top3_spearman": 0.0}
        supporting = {
            **base,
            "spearman": -0.20,
            "exclude_top1_spearman": -0.19,
            "exclude_top3_spearman": -0.18,
        }
        associations = {}
        for scope in ("overall", "ai", "commercial_space"):
            for outcome in (
                "baseline_gross_return",
                "baseline_mdd_magnitude",
                "baseline_daily_volatility",
                "baseline_negative_return",
                "q5_gross_return",
                "q5_relative_return",
                "q5_volatility_reduction",
                "q5_mdd_reduction",
            ):
                associations[(scope, outcome)] = weak.copy()
        associations[("overall", "baseline_gross_return")] = base.copy()
        associations[("overall", "baseline_negative_return")] = supporting
        self.assertTrue(stable_core(base))
        self.assertEqual(classify_acceptance(associations, {}), "diagnostically_supported")
        associations[("overall", "baseline_gross_return")] = weak.copy()
        associations[("ai", "baseline_gross_return")] = base.copy()
        self.assertEqual(classify_acceptance(associations, {}), "mixed")

    def test_contribution_and_leave_one_out_statistics(self):
        stats = association_statistics(pd.Series(np.arange(50)), pd.Series(np.arange(50)))
        self.assertEqual(stats["n"], 50)
        self.assertAlmostEqual(stats["spearman"], 1.0)
        self.assertEqual(stats["loo_sign_match_ratio"], 1.0)


if __name__ == "__main__":
    unittest.main()
