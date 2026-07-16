import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import pandas as pd

from scripts.run_lowvol_locked_grid_prototype_v1_5 import (
    main,
    period_targets,
    simulate,
)


class LowVolLockedGridPrototypeV15Tests(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame({
            "stock_code": ["000001", "000002", "000003", "000004", "000005"],
            "signal_sample_member": [True] * 5,
            "evaluation_sample_member": [True, True, True, True, False],
            "primary_reliable_signal": [True] * 5,
            "quantile": [1, 2, 3, 4, 5],
            "forward_return": [0.01, 0.02, 0.03, 0.04, None],
        })

    def test_q5_selection_is_label_blind_and_missing_end_invalidates(self):
        targets = period_targets(self.fixture())
        self.assertEqual(targets["Q5"]["codes"], ["000005"])
        self.assertEqual(targets["Q5"]["end_missing_codes"], ["000005"])
        self.assertFalse(targets["Q5"]["valid"])

    def test_start_ineligible_never_enters_target(self):
        frame = self.fixture()
        frame.loc[4, "signal_sample_member"] = False
        self.assertEqual(period_targets(frame)["Q5"]["codes"], [])

    def test_drifted_turnover_cost_and_compounded_nav(self):
        observations = [
            {"period_index": 0, "target": {"000001": 0.5, "000002": 0.5}, "returns": {"000001": 0.10, "000002": 0.0}, "valid": True},
            {"period_index": 1, "target": {"000001": 0.5, "000002": 0.5}, "returns": {"000001": 0.0, "000002": 0.10}, "valid": True},
        ]
        result = simulate(observations, 0.01)
        self.assertAlmostEqual(result.loc[0, "turnover"], 1.0)
        self.assertAlmostEqual(result.loc[1, "turnover"], abs(0.5 - 0.55 / 1.05))
        self.assertAlmostEqual(result.loc[0, "net_return"], 0.04)
        self.assertAlmostEqual(result.loc[1, "nav"], (1.04) * (1 + 0.05 - result.loc[1, "turnover"] * 0.01))

    def test_invalid_period_stops_nav(self):
        observations = [
            {"period_index": 0, "target": {"000001": 1.0}, "returns": {"000001": 0.1}, "valid": True},
            {"period_index": 1, "target": {"000001": 1.0}, "returns": {}, "valid": False},
            {"period_index": 2, "target": {"000001": 1.0}, "returns": {"000001": 0.1}, "valid": True},
        ]
        result = simulate(observations, 0.0)
        self.assertEqual(result["headline_included"].tolist(), [True, False, False])
        self.assertTrue(pd.isna(result.loc[2, "nav"]))

    def test_critical_input_failure_returns_two(self):
        with TemporaryDirectory() as directory:
            self.assertEqual(main(["--project-root", directory]), 2)
            qa = pd.read_csv(Path(directory) / "reports/lowvol_locked_grid_prototype_qa_v1_5.csv")
            self.assertFalse(bool(qa.loc[0, "pass"]))


if __name__ == "__main__":
    unittest.main()
