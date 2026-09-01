import unittest

import pandas as pd

from scripts.audit_h5a_vol20_control import assign_vol_states, vol_controlled_period


class H5AVOL20ControlTests(unittest.TestCase):
    def test_vol_groups_are_deterministic_and_preserve_activity(self):
        states = pd.DataFrame(
            {
                "period_index": [1] * 6,
                "stock_code": ["000006", "000005", "000004", "000003", "000002", "000001"],
                "activity_state": ["HIGH_ACTIVITY", "LOW_ACTIVITY"] * 3,
            }
        )
        qfq = states[["period_index", "stock_code"]].copy()
        qfq["vol20"] = [0.30, 0.20, 0.20, 0.10, 0.10, 0.10]
        raw = states[["period_index", "stock_code"]].copy()
        raw["total_market_cap"] = 100.0
        result = assign_vol_states(states, qfq, raw)
        ordered = result.sort_values(["vol20", "stock_code"])
        self.assertEqual(
            ordered["vol_state"].tolist(),
            ["LOW_VOL", "LOW_VOL", "MID_VOL", "MID_VOL", "HIGH_VOL", "HIGH_VOL"],
        )
        self.assertEqual(result["activity_state"].tolist(), states["activity_state"].tolist())

    def test_controlled_average_requires_two_strata(self):
        values = pd.DataFrame(
            {
                "period_index": [1, 1, 1, 2],
                "return_state": ["HIGH_RETURN"] * 4,
                "horizon": [20] * 4,
                "contrast": [-0.01, -0.03, -0.20, -0.50],
            }
        )
        result = vol_controlled_period(values)
        first = result.loc[result["period_index"].eq(1), "vol20_controlled_contrast"].iloc[0]
        second = result.loc[result["period_index"].eq(2), "vol20_controlled_contrast"].iloc[0]
        self.assertAlmostEqual(first, -0.08)
        self.assertTrue(pd.isna(second))


if __name__ == "__main__":
    unittest.main()
