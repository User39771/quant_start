import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd

from scripts.run_lowvol_locked_grid_prototype_v1_5_1 import (
    compare_ordered_period_keys,
    compare_value,
    benchmark_frame,
    main,
    period_targets,
    parse_strict_bool,
    validate_cost_contract,
)


FREEZE_AUDIT_COVERAGE = frozenset({"evaluation_extra_security"})


class LowVolLockedGridPrototypeV151Tests(unittest.TestCase):
    def fixture(self):
        return pd.DataFrame({
            "stock_code": ["000001", "000002", "000003", "000004", "000005"],
            "baseline_eligible": ["true"] * 5,
            "signal_sample_member": ["true"] * 5,
            "evaluation_sample_member": ["true", "true", "true", "true", "false"],
            "primary_reliable_signal": ["1"] * 5,
            "label_available": ["true", "true", "true", "true", "false"],
            "quantile": [1, 2, 3, 4, 5],
            "forward_return": [0.01, 0.02, 0.03, 0.04, np.nan],
        })

    def test_strict_false_is_false_and_unknown_fails(self):
        self.assertFalse(parse_strict_bool("False"))
        self.assertTrue(parse_strict_bool(" 1 "))
        with self.assertRaises(ValueError):
            parse_strict_bool("yes")
        with self.assertRaises(ValueError):
            parse_strict_bool(np.nan)

    def test_universe_target_is_signal_sample_and_label_blind(self):
        before = period_targets(self.fixture())
        self.assertEqual(before["UNIVERSE"]["codes"], ["000001", "000002", "000003", "000004", "000005"])
        self.assertEqual(before["UNIVERSE"]["end_missing_codes"], ["000005"])
        self.assertFalse(before["UNIVERSE"]["valid"])
        changed = self.fixture()
        changed.loc[4, ["label_available", "forward_return"]] = ["true", 9.9]
        after = period_targets(changed)
        self.assertEqual(before["UNIVERSE"]["codes"], after["UNIVERSE"]["codes"])
        self.assertEqual(before["UNIVERSE"]["target"], after["UNIVERSE"]["target"])

    def test_evaluation_only_security_does_not_enter_universe_target(self):
        clean = self.fixture()
        clean.loc[4, ["signal_sample_member", "evaluation_sample_member"]] = ["false", "false"]
        contaminated = clean.copy()
        contaminated.loc[4, ["evaluation_sample_member", "label_available", "forward_return"]] = ["true", "true", 9.9]

        clean_target = period_targets(clean)["UNIVERSE"]
        contaminated_target = period_targets(contaminated)["UNIVERSE"]
        expected_codes = ["000001", "000002", "000003", "000004"]
        expected_weights = {code: 0.25 for code in expected_codes}

        self.assertEqual(clean_target["codes"], expected_codes)
        self.assertEqual(contaminated_target["codes"], expected_codes)
        self.assertEqual(clean_target["target"], expected_weights)
        self.assertEqual(contaminated_target["target"], expected_weights)
        self.assertNotIn("000005", contaminated_target["codes"])

    def test_q5_and_q1_are_label_blind(self):
        frame = self.fixture()
        q5 = period_targets(frame)["Q5"]
        self.assertEqual(q5["codes"], ["000005"])
        self.assertEqual(q5["target"], {"000005": 1.0})
        self.assertFalse(q5["valid"])
        frame.loc[0, ["label_available", "forward_return"]] = ["false", np.nan]
        q1 = period_targets(frame)["Q1"]
        self.assertEqual(q1["codes"], ["000001"])
        self.assertFalse(q1["valid"])

    def test_ordered_period_keys_require_index_order_and_exact_rows(self):
        left = pd.DataFrame({
            "period_index": [0, 1],
            "rebalance_date": ["2021-01-01", "2021-02-01"],
            "next_rebalance_date": ["2021-02-01", "2021-03-01"],
        })
        self.assertTrue(compare_ordered_period_keys(left, left.copy())["equal"])
        reversed_rows = left.iloc[::-1].reset_index(drop=True)
        self.assertFalse(compare_ordered_period_keys(left, reversed_rows)["equal"])
        duplicate = pd.concat([left, left.iloc[[1]]], ignore_index=True)
        self.assertFalse(compare_ordered_period_keys(left, duplicate)["equal"])

    def test_diff_comparison_is_nan_aware_and_normalizes_code_lists(self):
        self.assertTrue(compare_value(np.nan, np.nan, "numeric"))
        self.assertTrue(compare_value(1.0, 1.0 + 1e-12, "numeric"))
        self.assertTrue(compare_value("2;000001", "000001;000002", "codes"))
        self.assertFalse(compare_value("A", "a", "string"))

    def test_cost_contract_separates_pre_cost_and_net_fields(self):
        periods = pd.DataFrame({
            "period_index": [0, 0, 0],
            "portfolio": ["Q5"] * 3,
            "transaction_cost": [0, 0.001, 0.002],
            "selected_codes": ["000001"] * 3,
            "target_weights": ["000001:1"] * 3,
            "turnover": [1.0] * 3,
            "gross_return": [0.1] * 3,
            "period_status": ["headline"] * 3,
            "headline_included": ["true"] * 3,
            "cost_drag": [0, 0.001, 0.002],
            "net_return": [0.1, 0.099, 0.098],
            "nav": [1.1, 1.099, 1.098],
        })
        result = validate_cost_contract(periods)
        self.assertTrue(result["same_pre_cost_portfolio"])
        self.assertTrue(result["effects_confined_to_net"])

    def test_q5_or_q1_diff_is_critical_and_q5_summary_change_is_nonlocal(self):
        from scripts.run_lowvol_locked_grid_prototype_v1_5_1 import classify_diff
        self.assertEqual(classify_diff("Q5", "selected_codes", False), "unexpected_q5_or_q1_change")
        self.assertEqual(classify_diff("Q1", "gross_return", False), "unexpected_q5_or_q1_change")
        self.assertEqual(classify_diff("COMPARISON", "cumulative_return", False), "unexpected_nonlocal_change")

    def test_missing_or_noncontinuous_period_index_is_invalid(self):
        frame = pd.DataFrame({
            "period_index": [0, 2],
            "rebalance_date": ["2021-01-01", "2021-02-01"],
            "next_rebalance_date": ["2021-02-01", "2021-03-01"],
        })
        self.assertFalse(compare_ordered_period_keys(frame, frame.copy())["equal"])

    def test_duplicate_or_missing_benchmark_endpoint_fails(self):
        grid = pd.DataFrame({"period_index": [0], "rebalance_date": ["2021-01-01"], "next_rebalance_date": ["2021-02-01"]})
        with TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data/processed"
            data.mkdir(parents=True)
            rows = []
            for code in ("000300", "000852", "399006"):
                rows.extend([{"benchmark_code": code, "trade_date": "2021-01-01", "close": 100}, {"benchmark_code": code, "trade_date": "2021-02-01", "close": 101}])
            rows.append(dict(rows[0]))
            pd.DataFrame(rows).to_csv(data / "hybrid_benchmark_panel_v1_5.csv", index=False)
            with self.assertRaises(ValueError):
                benchmark_frame(root, grid)
            pd.DataFrame(rows[1:-1]).to_csv(data / "hybrid_benchmark_panel_v1_5.csv", index=False)
            with self.assertRaises(ValueError):
                benchmark_frame(root, grid)

    def test_failed_run_removes_success_outputs_and_keeps_only_failure_report(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            reports = root / "reports"
            reports.mkdir()
            stale = reports / "lowvol_locked_grid_prototype_summary_v1_5_1.csv"
            stale.write_text("stale", encoding="utf-8")
            self.assertEqual(main(["--project-root", str(root)]), 2)
            self.assertFalse(stale.exists())
            self.assertTrue((reports / "lowvol_locked_grid_prototype_qa_failed_v1_5_1.md").exists())


if __name__ == "__main__":
    unittest.main()
