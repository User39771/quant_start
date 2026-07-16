import unittest

import pandas as pd

from scripts.test_liquidity_filter_hypothesis_v1_6 import (
    classify_conclusion,
    median_filter,
    valid_amount_mean,
)


class LiquidityFilterHypothesisV16Tests(unittest.TestCase):
    def test_amount_window_and_median_ties(self):
        self.assertEqual(valid_amount_mean(pd.Series(range(1, 21))), 10.5)
        self.assertTrue(pd.isna(valid_amount_mean(pd.Series([1.0] * 19 + [0.0]))))
        self.assertTrue(pd.isna(valid_amount_mean(pd.Series([1.0] * 19 + [None]))))
        median, passed = median_filter(pd.Series([10.0, 20.0, 20.0, 30.0, None]))
        self.assertEqual(median, 20.0)
        self.assertEqual(passed.tolist(), [False, True, True, True, False])

    def test_pre_registered_conclusions(self):
        self.assertEqual(
            classify_conclusion(56 / 57, 0.30, 0.25, [0.01, 0.02]),
            "supported_for_implementability",
        )
        self.assertEqual(
            classify_conclusion(56 / 57, 0.30, 0.35, [-0.01, -0.02]),
            "not_supported",
        )
        self.assertEqual(
            classify_conclusion(56 / 57, 0.30, 0.25, [-0.01, 0.01]),
            "mixed",
        )
        self.assertEqual(
            classify_conclusion(0.50, 0.30, 0.20, [0.10, 0.10]),
            "not_supported",
        )


if __name__ == "__main__":
    unittest.main()
