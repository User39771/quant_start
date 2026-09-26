import unittest

import numpy as np
import pandas as pd

from scripts.audit_mcts_primitive_viability_v0 import (
    assert_signal_only,
    code6,
    combination_coverage,
    period_coverage,
)


class PrimitiveViabilityAuditTest(unittest.TestCase):
    def signal(self):
        rows = []
        for period in range(2):
            for stock in range(25):
                rows.append(
                    {
                        "period_index": period,
                        "stock_code": f"{stock:06d}",
                        "signal_as_of_date": pd.Timestamp("2021-01-01") + pd.Timedelta(days=period),
                        "RETURN_60": float(stock),
                        "VOL_20": np.nan if period == 0 and stock == 0 else stock + 1.0,
                        "AMOUNT_MEAN_20": stock + 100.0,
                    }
                )
        return pd.DataFrame(rows)

    def test_code_normalization(self):
        self.assertEqual(code6(pd.Series(["63", "000063"])).tolist(), ["000063", "000063"])
        with self.assertRaises(ValueError):
            code6(pd.Series(["000063.SZ"]))

    def test_coverage_no_fill(self):
        result = period_coverage(self.signal())
        row = result.loc[result["primitive"].eq("VOL_20") & result["period_index"].eq(0)].iloc[0]
        self.assertEqual(row["finite_count"], 24)
        self.assertFalse(row["period_valid_under_v0_contract"])

    def test_counterfactual_is_signal_only(self):
        combos, counter = combination_coverage(self.signal(), thresholds=(1.0, 0.95))
        self.assertEqual(len(combos), 10)
        row = counter.loc[
            counter["coverage_threshold"].eq(0.95) & counter["expression"].eq("VOL_20")
        ].iloc[0]
        self.assertEqual(row["valid_periods"], 1)

    def test_label_access_rejected(self):
        frame = self.signal().assign(forward_return=0.1)
        with self.assertRaises(ValueError):
            assert_signal_only(frame)


if __name__ == "__main__":
    unittest.main()
