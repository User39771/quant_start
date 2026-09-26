import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import numpy as np
import pandas as pd

from aq_factor_lab.phase_a_evaluation import (
    _bool,
    assign_contract_members,
    conclusion_status,
    cross_sectional_diagnostics,
    endpoint_max_drawdown,
    experiment_registry,
    lineage_audit,
    long_only_paths,
    primary_relative_wealth,
    rank_ic_periods,
    validate_official_period_mapping,
    verify_frozen_hashes,
)
from scripts.run_phase_a_historical_seen_v1_9_2 import create_run_directory


def panel(periods=2, members=25):
    rows = []
    for period in range(periods):
        month = pd.Timestamp("2024-01-01") + pd.DateOffset(months=period)
        for stock in range(members):
            rows.append(
                {
                    "period_index": period,
                    "stock_code": f"{stock + 1:06d}",
                    "signal_as_of_date": month,
                    "rebalance_date": month + pd.Timedelta(days=1),
                    "next_rebalance_date": month + pd.DateOffset(months=1, days=1),
                    "baseline_eligible": True,
                    "signal_sample_member": True,
                    "mom60": float(stock),
                    "forward_return": (stock - 12) / 100,
                }
            )
    return pd.DataFrame(rows)


def official_period_frames():
    selected = panel(54, 1)
    dates = selected[
        ["period_index", "signal_as_of_date", "rebalance_date", "next_rebalance_date"]
    ].drop_duplicates()
    official = dates[["period_index", "rebalance_date", "next_rebalance_date"]].copy()
    official["factor_name"] = "MOM60"
    official["sample_basis"] = "mom60_primary_sample"
    readiness = dates.copy()
    readiness["row_type"] = "period"
    readiness["main_period_member"] = "true"
    return selected, official, readiness


class PhaseAEvaluationTests(unittest.TestCase):
    def test_strict_boolean_parser_accepts_only_registered_values(self):
        values = pd.Series(
            [
                True,
                np.bool_(True),
                " true ",
                "1",
                "YES",
                False,
                np.bool_(False),
                " false ",
                "0",
                "NO",
            ],
            name="flag",
        )
        self.assertEqual(
            _bool(values).tolist(),
            [True, True, True, True, True, False, False, False, False, False],
        )

    def test_strict_boolean_parser_reports_invalid_values_and_rows(self):
        keys = pd.DataFrame(
            {"period_index": [1, 1, 1], "stock_code": ["000001", "000002", "000003"]}
        )
        for value in (None, np.nan, "", "truth", 1, 0):
            values = pd.Series(["true", value, "false"], name="baseline_eligible")
            with self.assertRaisesRegex(
                ValueError,
                r"column=baseline_eligible count=1.*period_index.*stock_code",
            ):
                _bool(values, keys)

    def test_stock_code_validation_and_normalized_collision(self):
        source = panel(1)
        source.loc[0, "stock_code"] = "63"
        source.loc[1, "stock_code"] = "000063"
        with self.assertRaisesRegex(ValueError, "duplicate_period_stock_after_normalization"):
            assign_contract_members(source)
        for value in (None, "", "63.0", "A63", "１２３", "1234567"):
            bad = panel(1)
            bad.loc[0, "stock_code"] = value
            with self.assertRaisesRegex(ValueError, "invalid_stock_code"):
                assign_contract_members(bad)

    def test_no_lookahead_and_output_schema(self):
        bad = panel(1)
        bad["signal_as_of_date"] = bad["next_rebalance_date"]
        with self.assertRaisesRegex(ValueError, "invalid_date_order"):
            assign_contract_members(bad)
        assigned, audit = assign_contract_members(panel(1))
        self.assertTrue(
            {"signal_target_member", "raw_quantile", "oriented_quantile"}.issubset(assigned)
        )
        self.assertTrue({"tie_count", "boundary_tie_count", "tie_split"}.issubset(audit))

    def test_each_period_date_must_be_internally_consistent(self):
        for column in ("signal_as_of_date", "rebalance_date", "next_rebalance_date"):
            bad = panel(1)
            bad.loc[0, column] = bad.loc[0, column] + pd.Timedelta(days=1)
            with self.assertRaisesRegex(ValueError, f"inconsistent_period_date column={column}"):
                assign_contract_members(bad)

    def test_official_54_period_mapping_uses_both_frozen_shapes(self):
        selected, official, readiness = official_period_frames()
        assigned, _ = assign_contract_members(selected)
        mapped = validate_official_period_mapping(assigned, official, readiness)
        self.assertEqual(len(mapped), 54)

        missing = assigned.loc[assigned["period_index"].ne(53)]
        with self.assertRaisesRegex(ValueError, "panel_official_period_key_mismatch"):
            validate_official_period_mapping(missing, official, readiness)

        extra = pd.concat(
            [
                assigned,
                assigned.loc[assigned["period_index"].eq(53)].assign(period_index=54),
            ],
            ignore_index=True,
        )
        with self.assertRaisesRegex(ValueError, "panel_official_period_key_mismatch"):
            validate_official_period_mapping(extra, official, readiness)

        wrong_date = assigned.copy()
        wrong_date.loc[wrong_date["period_index"].eq(0), "signal_as_of_date"] += pd.Timedelta(
            days=1
        )
        with self.assertRaisesRegex(
            ValueError, "panel_official_period_date_mismatch column=signal_as_of_date"
        ):
            validate_official_period_mapping(wrong_date, official, readiness)

    def test_membership_is_label_blind_and_missing_worst_breaks_primary_path(self):
        complete, _ = assign_contract_members(panel(1))
        worst = panel(1)
        worst.loc[worst["forward_return"].idxmin(), "forward_return"] = np.nan
        missing, _ = assign_contract_members(worst)
        self.assertEqual(complete["raw_quantile"].tolist(), missing["raw_quantile"].tolist())
        paths = long_only_paths(missing)
        self.assertTrue(paths["period_portfolio_status"].eq("invalid_missing_target_return").all())
        self.assertTrue(np.isnan(primary_relative_wealth(paths)))

    def test_orientation_identity_quantiles_remainders_and_ties(self):
        source = panel(1, 27)
        source.loc[source.index[:7], "mom60"] = 0.0
        assigned, audit = assign_contract_members(source)
        counts = assigned.groupby("raw_quantile").size().to_dict()
        self.assertEqual(counts, {1: 6, 2: 6, 3: 5, 4: 5, 5: 5})
        self.assertTrue((assigned["oriented_quantile"] == 6 - assigned["raw_quantile"]).all())
        self.assertTrue(audit.iloc[0].tie_split)
        ic = rank_ic_periods(assigned)
        self.assertAlmostEqual(ic.iloc[0].oriented_rank_ic, -ic.iloc[0].raw_rank_ic)
        self.assertEqual(ic.iloc[0].orientation_alpha_increment, 0)

    def test_rankic_failure_logging_and_historical_label(self):
        small, _ = assign_contract_members(panel(1, 24))
        row = rank_ic_periods(small).iloc[0]
        self.assertEqual(row.failure_reason, "insufficient_joint_count")
        self.assertEqual(row.sample_role, "historical_seen")
        self.assertFalse(row.formal_alpha_conclusion_allowed)
        constant = panel(1)
        constant["mom60"] = 1.0
        assigned, _ = assign_contract_members(constant)
        self.assertEqual(rank_ic_periods(assigned).iloc[0].failure_reason, "constant_factor")

    def test_drifted_turnover_costs_and_primary_metric(self):
        assigned, _ = assign_contract_members(panel(2, 25))
        free = long_only_paths(assigned, 0.0)
        primary = long_only_paths(assigned, 0.002)
        expensive = long_only_paths(assigned, 0.003)
        self.assertTrue(free.loc[free.period_index.eq(0), "one_way_turnover"].eq(1.0).all())
        self.assertTrue(
            np.allclose(primary["transaction_cost"], primary["one_way_turnover"] * 0.002)
        )
        self.assertTrue((free.net_nav >= primary.net_nav).all())
        self.assertTrue((primary.net_nav >= expensive.net_nav).all())
        self.assertTrue(np.isfinite(primary_relative_wealth(primary)))

    def test_endpoint_drawdown_is_not_worst_period(self):
        returns = pd.Series([0.10, -0.10, -0.10])
        self.assertAlmostEqual(endpoint_max_drawdown(returns), -0.19)
        self.assertNotEqual(endpoint_max_drawdown(returns), returns.min())

    def test_coverage_counts_and_partial_labels_do_not_create_portfolio(self):
        source = panel(1)
        source.loc[[source.index[0], source.index[-1]], "forward_return"] = np.nan
        assigned, audit = assign_contract_members(source)
        self.assertEqual(audit.iloc[0].signal_target_count, 25)
        self.assertEqual(audit.iloc[0].jointly_valid_count, 23)
        self.assertAlmostEqual(audit.iloc[0].jointly_valid_coverage, 23 / 25)
        self.assertFalse(long_only_paths(assigned).primary_portfolio_metric_valid.any())
        diagnostic = cross_sectional_diagnostics(assigned).iloc[0]
        self.assertEqual(diagnostic.result_role, "partial_label_diagnostic")
        self.assertFalse(diagnostic.is_executable_strategy)

    def test_lineage_audit_keeps_label_and_membership_separate(self):
        source = panel(1)
        source.loc[0, "forward_return"] = np.nan
        assigned, _ = assign_contract_members(source)
        audit = lineage_audit(assigned)
        self.assertEqual(audit.row_count.sum(), len(source))
        missing = audit.loc[~audit.label_available]
        self.assertTrue(missing.signal_sample_member.all())
        self.assertFalse(missing.evaluation_sample_member.any())

    def test_broken_path_does_not_restart(self):
        source = panel(3)
        source.loc[
            (source.period_index == 1) & (source.stock_code == "000001"), "forward_return"
        ] = np.nan
        assigned, _ = assign_contract_members(source)
        paths = long_only_paths(assigned)
        self.assertTrue(
            paths.loc[paths.period_index.eq(1), "period_portfolio_status"]
            .eq("invalid_missing_target_return")
            .all()
        )
        self.assertTrue(
            paths.loc[paths.period_index.eq(2), "period_portfolio_status"]
            .eq("broken_prior_path")
            .all()
        )

    def test_conclusion_status_branches_and_boundaries(self):
        values = pd.Series([0.02] * 24)
        self.assertEqual(
            conclusion_status(
                values,
                0.01,
                sample_role="historical_seen",
                all_required_qa_passed=True,
                primary_portfolio_path_valid=True,
            ),
            "descriptive_only",
        )
        kwargs = {
            "sample_role": "prospective_test",
            "all_required_qa_passed": True,
            "primary_portfolio_path_valid": True,
        }
        with patch(
            "aq_factor_lab.phase_a_evaluation.moving_block_lower_bound",
            return_value=0.001,
        ):
            self.assertEqual(
                conclusion_status(pd.Series([0.015] * 24), 0.01, **kwargs),
                "supported",
            )
            self.assertEqual(
                conclusion_status(pd.Series([0.0] * 24), 0.01, **kwargs),
                "not_supported",
            )
            self.assertEqual(
                conclusion_status(pd.Series([0.03] * 12 + [0.0] * 12), 0.01, **kwargs),
                "not_supported",
            )
            self.assertEqual(conclusion_status(values, 0.0, **kwargs), "not_supported")
            self.assertEqual(
                conclusion_status(values.iloc[:-1], 0.01, **kwargs),
                "inconclusive",
            )
            self.assertEqual(
                conclusion_status(
                    values,
                    0.01,
                    **{**kwargs, "all_required_qa_passed": False},
                ),
                "inconclusive",
            )
            self.assertEqual(
                conclusion_status(
                    values,
                    0.01,
                    **{**kwargs, "primary_portfolio_path_valid": False},
                ),
                "inconclusive",
            )
            for relative in (np.nan, np.inf, -np.inf):
                self.assertEqual(conclusion_status(values, relative, **kwargs), "inconclusive")
        with patch(
            "aq_factor_lab.phase_a_evaluation.moving_block_lower_bound",
            return_value=0.0,
        ):
            self.assertEqual(conclusion_status(values, 0.01, **kwargs), "not_supported")
        with patch(
            "aq_factor_lab.phase_a_evaluation.moving_block_lower_bound",
            return_value=np.nan,
        ):
            self.assertEqual(conclusion_status(values, 0.01, **kwargs), "inconclusive")
        self.assertEqual(
            conclusion_status(
                pd.Series([np.inf] * 24),
                0.01,
                **kwargs,
            ),
            "inconclusive",
        )
        self.assertEqual(
            conclusion_status(pd.Series([np.nan] * 24), 0.01, **kwargs),
            "inconclusive",
        )

    def test_fixed_seed_bootstrap_is_reproducible(self):
        from aq_factor_lab.phase_a_evaluation import moving_block_lower_bound

        values = pd.Series(np.linspace(-0.02, 0.05, 24))
        self.assertEqual(
            moving_block_lower_bound(values),
            moving_block_lower_bound(values),
        )

    def test_registry_is_locked(self):
        registry = experiment_registry()
        self.assertFalse(registry.statistically_independent.any())
        self.assertEqual(registry.orientation_information_increment.unique().tolist(), [0])

    def test_cli_self_check_and_confirmation_gate_do_not_write_research_outputs(self):
        root = Path(__file__).resolve().parents[1]
        script = root / "scripts" / "run_phase_a_historical_seen_v1_9_2.py"
        output_base = root / "reports" / "phase_a_historical_seen_reproduction_v1_9_2"
        before = set(output_base.iterdir()) if output_base.exists() else set()
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root / "src")
        checked = subprocess.run(
            [sys.executable, str(script), "--self-check"],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertIn("self_check=pass", checked.stdout)
        missing = subprocess.run(
            [sys.executable, str(script)],
            cwd=root,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertNotEqual(missing.returncode, 0)
        after = set(output_base.iterdir()) if output_base.exists() else set()
        self.assertEqual(before, after)

    def test_run_directory_never_overwrites(self):
        with TemporaryDirectory() as directory:
            base = Path(directory)
            created = create_run_directory(base, "fixed")
            marker = created / "marker.txt"
            marker.write_text("preserve", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                create_run_directory(base, "fixed")
            self.assertEqual(marker.read_text(encoding="utf-8"), "preserve")

    def test_frozen_artifacts_are_unchanged(self):
        root = Path(__file__).resolve().parents[1]
        checks = verify_frozen_hashes(root)
        self.assertTrue(all(checks.values()), [path for path, ok in checks.items() if not ok])


if __name__ == "__main__":
    unittest.main()
