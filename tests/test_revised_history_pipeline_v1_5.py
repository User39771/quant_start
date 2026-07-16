import unittest

import pandas as pd

from scripts.run_revised_history_pipeline_v1_5 import classify_periods, versioned_name


class RevisedHistoryPipelineV15Tests(unittest.TestCase):
    def test_versioned_name_only_changes_version_suffix(self):
        self.assertEqual(
            versioned_name("adjusted_stock_pool_baseline_v1_2.md"),
            "adjusted_stock_pool_baseline_v1_5.md",
        )
        self.assertEqual(
            versioned_name("factor_ic_summary_lowvol20_v1_4.csv"),
            "factor_ic_summary_lowvol20_v1_5.csv",
        )

    def test_period_regimes_are_deterministic(self):
        frame = pd.DataFrame(
            {
                "rebalance_date": ["2026-06-01", "2026-06-20", "2026-07-14"],
                "next_rebalance_date": ["2026-06-16", "2026-07-10", "2026-08-10"],
            }
        )
        result = classify_periods(frame, "2026-06-16", "2026-07-11")
        self.assertEqual(
            result["sample_regime"].tolist(),
            ["revised_history", "pipeline_unseen_retrospective_extension", "prospective_holdout"],
        )
        self.assertEqual(result["prospective_flag"].tolist(), [False, False, True])

    def test_classification_does_not_relabel_post_freeze_period(self):
        frame = pd.DataFrame({"rebalance_date": ["2026-07-12"], "next_rebalance_date": ["2026-08-10"]})
        self.assertEqual(classify_periods(frame)["sample_regime"].iloc[0], "prospective_holdout")


if __name__ == "__main__":
    unittest.main()
