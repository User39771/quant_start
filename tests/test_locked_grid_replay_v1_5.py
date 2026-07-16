import unittest

import pandas as pd

from scripts.run_adjusted_stock_pool_baseline_v1_2 import Boundary, evaluate_period
from scripts.test_lowvol20_hypothesis_v1_4 import assign_quantiles
from scripts.run_locked_grid_replay_v1_5 import (
    comparison_flags,
    frozen_period_keys,
)


class LockedGridReplayV15Tests(unittest.TestCase):
    def test_frozen_keys_ignore_earlier_v15_prices(self):
        periods = pd.DataFrame(
            {
                "universe_name": ["research_universe_v1_2"] * 2,
                "transaction_cost": ["0", "0"],
                "period_type": ["full", "full"],
                "headline_included": ["true", "true"],
                "rebalance_date": ["2021-03-31", "2021-04-29"],
                "next_rebalance_date": ["2021-04-29", "2021-06-01"],
                "period_trading_days": [20, 20],
            }
        )
        keys = frozen_period_keys(periods)
        self.assertEqual(keys[0][0], pd.Timestamp("2021-03-31"))
        self.assertEqual(len(keys), 2)

    def test_comparison_requires_identical_period_keys(self):
        left = pd.DataFrame({"rebalance_date": ["2021-03-31"], "next_rebalance_date": ["2021-04-29"]})
        self.assertEqual(comparison_flags(left, left.copy()), (True, True))
        right = left.assign(next_rebalance_date="2021-04-30")
        self.assertEqual(comparison_flags(left, right), (False, False))

    def test_missing_start_price_is_only_start_ineligible(self):
        boundary = Boundary(pd.Timestamp("2021-03-31"), pd.Timestamp("2021-04-29"), 20, "full")
        result = evaluate_period(["000063", "000001"], {("000001", boundary.start): 10.0, ("000001", boundary.end): 11.0}, boundary, 0.5)
        self.assertEqual(result["start_ineligible_codes"], "000063")
        self.assertTrue(result["period_valid"])

    def test_future_label_does_not_change_quantile(self):
        frame = pd.DataFrame({
            "stock_code": [f"00000{i}" for i in range(1, 6)],
            "lowvol20": [1, 2, 3, 4, 5],
            "forward_return": [0.1, 0.2, 0.3, 0.4, None],
            "forward_risk_available": [True] * 5,
            "baseline_eligible": [True] * 5,
            "primary_reliable_signal": [True] * 5,
        })
        before, _ = assign_quantiles(frame, "lowvol20", True)
        frame.loc[4, "forward_return"] = 9.9
        after, _ = assign_quantiles(frame, "lowvol20", True)
        self.assertEqual(before["quantile"].tolist(), after["quantile"].tolist())


if __name__ == "__main__":
    unittest.main()
