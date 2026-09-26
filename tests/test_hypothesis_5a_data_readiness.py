import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.audit_hypothesis_5a_data_readiness import (
    bool_series,
    code6,
    guarded_read_csv,
    stable_groups,
)


class Hypothesis5AReadinessTest(unittest.TestCase):
    def test_code_normalization(self):
        self.assertEqual(code6(pd.Series([63, "300339.0"])).tolist(), ["000063", "300339"])

    def test_stable_groups_are_signal_only_and_deterministic(self):
        frame = pd.DataFrame(
            {"stock_code": ["000003", "000001", "000002", "000004"], "value": [1, 1, 2, 3]}
        )
        first = stable_groups(frame, "value", 2)
        second = stable_groups(frame.sample(frac=1, random_state=2), "value", 2).sort_index()
        pd.testing.assert_series_equal(first.sort_index(), second)

    def test_boolean_and_no_fill(self):
        self.assertEqual(bool_series(pd.Series([True, False])).tolist(), [True, False])
        values = pd.Series([1.0, np.nan, 3.0])
        self.assertTrue(values.isna().any())

    def test_forbidden_paths(self):
        with self.assertRaises(PermissionError):
            guarded_read_csv(Path("."), "data/prospective/h5a.csv")
        with self.assertRaises(PermissionError):
            guarded_read_csv(Path("."), "reports/final_test/h5a.csv")


if __name__ == "__main__":
    unittest.main()
