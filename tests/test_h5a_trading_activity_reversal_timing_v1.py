import unittest

import numpy as np
import pandas as pd

from scripts.run_h5a_trading_activity_reversal_timing_v1 import (
    ACTIVITY_STATES,
    BLOCK_LENGTH,
    _build_stock_outcomes,
    classify_result,
    continuation_aligned,
    moving_block_interval,
    ordinal_groups,
    path_category,
)


class H5ATradingActivityTests(unittest.TestCase):
    def test_ordinal_assignment_is_deterministic_and_ties_do_not_change_counts(self):
        frame = pd.DataFrame(
            {
                "stock_code": ["000003", "000001", "000002", "000006", "000005", "000004"],
                "value": [1.0, 1.0, 1.0, 2.0, 3.0, 3.0],
            }
        )
        first = ordinal_groups(frame, "value", ACTIVITY_STATES)
        second = ordinal_groups(frame, "value", ACTIVITY_STATES)
        self.assertTrue(first.equals(second))
        self.assertEqual(first.value_counts().to_dict(), {state: 2 for state in ACTIVITY_STATES})
        self.assertEqual(first.loc[frame["stock_code"].eq("000001")].iloc[0], "LOW_ACTIVITY")

    def test_continuation_alignment_and_coarse_path_categories(self):
        states = pd.Series(["HIGH_RETURN", "LOW_RETURN", "MID_RETURN"])
        returns = pd.Series([0.10, -0.20, 0.05])
        aligned = continuation_aligned(states, returns)
        self.assertAlmostEqual(aligned.iloc[0], 0.10)
        self.assertAlmostEqual(aligned.iloc[1], 0.20)
        self.assertTrue(np.isnan(aligned.iloc[2]))
        self.assertEqual(path_category([0.03, 0.01, -0.02]), "REVERSAL_OBSERVED")
        self.assertEqual(path_category([0.03, 0.02, 0.01]), "ATTENUATES")
        self.assertEqual(path_category([0.01, 0.02, 0.03]), "CONTINUATION_PERSISTS")
        self.assertEqual(path_category([0.01, -0.01, 0.02]), "NO_CLEAR_PATH")

    def test_moving_block_interval_is_reproducible(self):
        self.assertEqual(BLOCK_LENGTH, 6)
        values = pd.Series(np.linspace(-0.02, 0.04, 56))
        first = moving_block_interval(values, repetitions=500)
        second = moving_block_interval(values, repetitions=500)
        self.assertEqual(first, second)
        self.assertLess(first[0], first[1])

    def test_classification_requires_stable_multi_horizon_evidence(self):
        rows = []
        for state in ("LOW_RETURN", "HIGH_RETURN"):
            for horizon in (20, 60, 120):
                rows.append(
                    {
                        "contrast_type": "activity_G",
                        "return_state": state,
                        "horizon": horizon,
                        "valid_periods": 56,
                        "mean_contrast": 0.01,
                        "activity_ordered": True,
                        "stability_flag": state == "HIGH_RETURN" and horizon in (20, 60),
                    }
                )
        contrast = pd.DataFrame(rows)
        categories = {
            ("HIGH_RETURN", "LOW_ACTIVITY"): "CONTINUATION_PERSISTS",
            ("HIGH_RETURN", "MID_ACTIVITY"): "ATTENUATES",
            ("HIGH_RETURN", "HIGH_ACTIVITY"): "REVERSAL_OBSERVED",
            ("LOW_RETURN", "LOW_ACTIVITY"): "NO_CLEAR_PATH",
            ("LOW_RETURN", "MID_ACTIVITY"): "NO_CLEAR_PATH",
            ("LOW_RETURN", "HIGH_ACTIVITY"): "NO_CLEAR_PATH",
        }
        self.assertEqual(
            classify_result(contrast, categories), "H5A_DIAGNOSTICALLY_SUPPORTED"
        )
        contrast["stability_flag"] = False
        contrast["activity_ordered"] = False
        self.assertEqual(classify_result(contrast, categories), "H5A_NOT_SUPPORTED")
        contrast.loc[0, "valid_periods"] = 44
        self.assertEqual(classify_result(contrast, categories), "H5A_INCONCLUSIVE")

    def test_future_return_uses_rebalance_close_and_exact_endpoint(self):
        states = pd.DataFrame(
            {
                "period_index": [1],
                "signal_as_of_date": pd.to_datetime(["2026-01-02"]),
                "stock_code": ["000001"],
                "return_state": ["HIGH_RETURN"],
                "activity_state": ["LOW_ACTIVITY"],
            }
        )
        dates = pd.DataFrame(
            {
                "period_index": [1],
                "signal_as_of_date": pd.to_datetime(["2026-01-02"]),
                "return_start_date": pd.to_datetime(["2026-01-05"]),
                "endpoint_20d_date": pd.to_datetime(["2026-02-02"]),
                "endpoint_60d_date": pd.to_datetime(["2026-04-01"]),
                "endpoint_120d_date": pd.to_datetime(["2026-06-26"]),
            }
        )
        prices = pd.DataFrame(
            {
                "stock_code": ["000001", "000001", "000001"],
                "trade_date": pd.to_datetime(["2026-01-05", "2026-02-02", "2026-04-01"]),
                "qfq_close": [10.0, 11.0, 12.0],
            }
        )
        outcomes = _build_stock_outcomes(states, dates, prices).set_index("horizon")
        self.assertAlmostEqual(outcomes.loc[20, "future_return"], 0.1)
        self.assertAlmostEqual(outcomes.loc[60, "future_return"], 0.2)
        self.assertFalse(outcomes.loc[120, "outcome_valid"])

    def test_generated_outputs_keep_primary_and_theme_contracts(self):
        period_path = "reports/hypothesis_5a/h5a_period_state_returns.csv"
        contrast_path = "reports/hypothesis_5a/h5a_stability_summary.csv"
        theme_path = "reports/hypothesis_5a/h5a_theme_transfer.csv"
        try:
            periods = pd.read_csv(period_path)
            contrasts = pd.read_csv(contrast_path)
            theme = pd.read_csv(theme_path, dtype={"stock_code": str})
        except FileNotFoundError:
            self.skipTest("generated H5A outputs not present")
        self.assertEqual(len(periods), 57 * 9 * 3)
        self.assertFalse(
            periods.duplicated(
                ["period_index", "return_state", "activity_state", "horizon"]
            ).any()
        )
        self.assertTrue(periods.loc[periods["period_index"].between(1, 56), "cell_valid"].all())
        core = contrasts.loc[contrasts["acceptance_used"]]
        self.assertTrue(core["valid_periods"].ge(45).all())
        space = theme.loc[theme["row_type"].eq("commercial_space_stock")]
        self.assertFalse(space.duplicated(["period_index", "stock_code", "horizon"]).any())


if __name__ == "__main__":
    unittest.main()
