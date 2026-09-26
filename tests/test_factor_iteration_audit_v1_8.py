import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from scripts.run_factor_iteration_audit_v1_8 import (
    append_log,
    assign_quantiles,
    choose_direction,
    evaluate_periods,
    failure_row,
    summarize,
)


def sample_panel() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "period_index": 1,
            "stock_code": [f"{index:06d}" for index in range(25)],
            "rebalance_date": pd.Timestamp("2023-12-01"),
            "baseline_eligible": True,
            "mom60": np.arange(25, dtype=float),
            "forward_return": np.arange(25, dtype=float) / 100,
        }
    )


class FactorIterationAuditTests(unittest.TestCase):
    def test_quantiles_are_assigned_before_label_availability(self):
        complete = assign_quantiles(sample_panel(), direction=1)
        missing = sample_panel()
        missing.loc[24, "forward_return"] = np.nan
        assigned = assign_quantiles(missing, direction=1)
        self.assertEqual(complete["quantile"].tolist(), assigned["quantile"].tolist())

    def test_only_development_summary_selects_the_direction(self):
        direction, _ = choose_direction({"mean_rank_ic": -0.1, "mean_q5_q1": -0.02})
        self.assertEqual(direction, -1)
        with self.assertRaisesRegex(ValueError, "no unique direction weakness"):
            choose_direction({"mean_rank_ic": 0.1, "mean_q5_q1": -0.02})

    def test_direction_inversion_flips_rank_ic_and_quantile_spread(self):
        baseline = summarize(evaluate_periods(sample_panel(), direction=1))
        candidate = summarize(evaluate_periods(sample_panel(), direction=-1))
        self.assertTrue(np.isclose(baseline["mean_rank_ic"], 1.0))
        self.assertTrue(np.isclose(candidate["mean_rank_ic"], -1.0))
        self.assertTrue(np.isclose(candidate["mean_q5_q1"], -baseline["mean_q5_q1"]))

    def test_failure_is_appended_to_the_audit_log(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "failure_log.csv"
            append_log(path, [failure_row(root, "start", "run-1", ValueError("bad period"))])
            logged = pd.read_csv(path)
        self.assertEqual(logged.loc[0, "row_type"], "failure")
        self.assertEqual(logged.loc[0, "status"], "failed")
        self.assertEqual(logged.loc[0, "error_message"], "bad period")


if __name__ == "__main__":
    unittest.main()
