import inspect
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts import run_h5b_vt20_diagnostic as h5b


class H5BVT20DiagnosticTests(unittest.TestCase):
    def test_cell_uses_fixed_membership_coverage_and_arithmetic_mean(self):
        states = pd.DataFrame(
            {
                "period_index": [1] * 50,
                "stock_code": [f"{value:06d}" for value in range(50)],
                "return_state": ["HIGH_RETURN"] * 50,
                "activity_state": ["LOW_VT"] * 25 + ["HIGH_VT"] * 25,
            }
        )
        outcomes = pd.concat(
            [
                states.assign(
                    horizon=horizon,
                    future_return=[1.0, 3.0] + [np.nan] * 5 + [2.0] * 18 + [4.0] * 25,
                    aligned_return=[1.0, 3.0] + [np.nan] * 5 + [2.0] * 18 + [4.0] * 25,
                    outcome_valid=[True] * 2 + [False] * 5 + [True] * 43,
                )
                for horizon in h5b.HORIZONS
            ],
            ignore_index=True,
        )
        cells = h5b.build_period_cells(states, outcomes)
        low = cells.loc[cells["vt20_state"].eq("LOW_VT")]
        self.assertTrue(low["cell_valid"].all())
        self.assertTrue(low["stock_count"].eq(25).all())
        self.assertTrue(low["valid_outcome_count"].eq(20).all())
        self.assertTrue(low["outcome_coverage"].eq(0.8).all())
        self.assertTrue(low["mean_future_return"].eq(2.0).all())

    def test_both_sides_must_be_valid_for_contrast(self):
        rows = []
        for period in (1, 2):
            for state, value in (("LOW_VT", 1.0), ("MID_VT", 2.0), ("HIGH_VT", 3.0)):
                for horizon in h5b.HORIZONS:
                    rows.append(
                        {
                            "period_index": period,
                            "return_state": "MID_RETURN",
                            "vt20_state": state,
                            "horizon": horizon,
                            "mean_future_return": value,
                            "mean_aligned_return": np.nan,
                            "cell_valid": not (period == 2 and state == "HIGH_VT"),
                        }
                    )
        summary, periods = h5b.build_contrasts(pd.DataFrame(rows))
        mid = summary.loc[summary["return_state"].eq("MID_RETURN")]
        self.assertTrue(mid["valid_periods"].eq(1).all())
        self.assertEqual(set(periods["period_index"]), {1})
        self.assertTrue(mid["mean_contrast"].eq(2.0).all())

    def test_formal_h5a_comparison_reads_existing_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            target = root / "reports/hypothesis_5a"
            target.mkdir(parents=True)
            h5a_rows = []
            h5b_rows = []
            for state in h5b.RETURN_STATES:
                for horizon in h5b.HORIZONS:
                    h5a_rows.append(
                        {
                            "contrast_type": (
                                "mid_activity_main_effect"
                                if state == "MID_RETURN"
                                else "activity_G"
                            ),
                            "return_state": state,
                            "horizon": horizon,
                            "mean_contrast": -2.0,
                        }
                    )
                    h5b_rows.append(
                        {"return_state": state, "horizon": horizon, "mean_contrast": -1.0}
                    )
            pd.DataFrame(h5a_rows).to_csv(target / "h5a_stability_summary.csv", index=False)
            comparison = h5b.compare_formal_h5a(root, pd.DataFrame(h5b_rows))
            self.assertTrue(comparison["direction_same"].all())
            self.assertTrue(comparison["magnitude_ratio"].eq(0.5).all())

    def test_runner_has_no_automatic_preservation_classification(self):
        source = inspect.getsource(h5b)
        self.assertNotIn("def classify_result", source)
        self.assertNotIn("alternative_proxy", source.replace("alternative_proxy_tested", ""))


if __name__ == "__main__":
    unittest.main()
