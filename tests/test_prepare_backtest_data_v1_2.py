from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "prepare_backtest_data_v1_2.py"
SPEC = importlib.util.spec_from_file_location("prepare_backtest_data_v1_2", MODULE_PATH)
prepare = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = prepare
SPEC.loader.exec_module(prepare)


class PrepareBacktestDataV12Tests(unittest.TestCase):
    def test_classifies_active_and_historical_stock_pool_outputs(self):
        category, version, status = prepare.classify_path(
            prepare.STOCK_POOL / "expanded_pool_v1_2.csv"
        )
        self.assertEqual(category, "active stock pool v1.2 outputs")
        self.assertEqual(version, "v1.2")
        self.assertEqual(status, "active")

        category, version, status = prepare.classify_path(
            prepare.STOCK_POOL / "pool_decision_suggestions_v1_1.csv"
        )
        self.assertEqual(category, "v1/v1.1 old stock pool outputs")
        self.assertEqual(version, "v1.1")
        self.assertEqual(status, "historical")

    def test_builds_two_universes_with_six_digit_codes(self):
        expanded, research = prepare.load_universes()

        self.assertEqual(len(expanded), len(prepare.read_csv(prepare.EXPANDED_POOL)))
        self.assertEqual(
            len(research),
            len(prepare.read_csv(prepare.DEFAULT_POOL)) + len(prepare.read_csv(prepare.EXPANDED_POOL)),
        )
        self.assertTrue(all(row["universe_name"] == "expanded_only_v1_2" for row in expanded))
        self.assertTrue(all(row["code"].isdigit() and len(row["code"]) == 6 for row in research))

    def test_price_coverage_flags_known_smoke_only_gaps(self):
        expanded, research = prepare.load_universes()
        expanded_cov = prepare.analyze_price_coverage(expanded, "expanded_only_v1_2")
        research_cov = prepare.analyze_price_coverage(research, "research_universe_v1_2")

        self.assertIn("300378", expanded_cov.missing_required_fields["high"])
        self.assertIn("300378", expanded_cov.missing_required_fields["low"])
        self.assertGreater(len(research_cov.missing_adjusted_fields), 0)
        self.assertEqual(research_cov.missing_price_files, [])


if __name__ == "__main__":
    unittest.main()
