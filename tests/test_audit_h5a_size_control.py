import unittest

import pandas as pd

from scripts.audit_h5a_size_control import assign_size_states, size_controlled_period


class H5ASizeControlTests(unittest.TestCase):
    def test_size_groups_are_deterministic_and_do_not_change_activity(self):
        states = pd.DataFrame(
            {
                "period_index": [1] * 6,
                "stock_code": ["000006", "000005", "000004", "000003", "000002", "000001"],
                "activity_state": ["HIGH_ACTIVITY", "LOW_ACTIVITY"] * 3,
            }
        )
        raw = states[["period_index", "stock_code"]].copy()
        raw["total_market_cap"] = [30, 20, 20, 10, 10, 10]
        raw["raw_signal_price"] = 1.0
        raw["circulating_market_cap"] = 1.0
        result = assign_size_states(states, raw)
        ordered = result.sort_values(["total_market_cap", "stock_code"])
        self.assertEqual(
            ordered["size_state"].tolist(),
            ["SMALL", "SMALL", "MID_SIZE", "MID_SIZE", "LARGE", "LARGE"],
        )
        self.assertEqual(result["activity_state"].tolist(), states["activity_state"].tolist())

    def test_controlled_average_requires_two_strata_and_is_equal_weighted(self):
        values = pd.DataFrame(
            {
                "period_index": [1, 1, 1, 2],
                "return_state": ["LOW_RETURN"] * 4,
                "horizon": [20] * 4,
                "contrast": [0.01, 0.03, 0.20, 0.50],
            }
        )
        result = size_controlled_period(values)
        first = result.loc[result["period_index"].eq(1), "size_controlled_contrast"].iloc[0]
        second = result.loc[result["period_index"].eq(2), "size_controlled_contrast"].iloc[0]
        self.assertAlmostEqual(first, 0.08)
        self.assertTrue(pd.isna(second))


if __name__ == "__main__":
    unittest.main()
