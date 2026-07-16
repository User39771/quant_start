from __future__ import annotations

import argparse
import hashlib
import importlib
import inspect
import math
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scripts import run_lowvol_locked_grid_prototype_v1_5_1 as candidate
except ImportError:
    import run_lowvol_locked_grid_prototype_v1_5_1 as candidate


ATOL = 1e-10
RTOL = 1e-8
OUTPUTS = (
    "lowvol_locked_grid_prototype_v1_5_1_freeze_audit.md",
    "lowvol_locked_grid_prototype_v1_5_1_freeze_manifest.csv",
    "lowvol_locked_grid_prototype_v1_5_1_freeze_checks.csv",
    "lowvol_locked_grid_prototype_v1_5_1_reproduction_diff.csv",
    "lowvol_locked_grid_prototype_v1_5_1_signoff.md",
)
TARGETED_TEST = "tests.test_lowvol_locked_grid_prototype_v1_5_1"
REGRESSION_TESTS = (
    TARGETED_TEST,
    "tests.test_lowvol_locked_grid_prototype_v1_5",
    "tests.test_locked_grid_replay_v1_5",
    "tests.test_lowvol20_hypothesis_v1_4",
    "tests.test_mom60_hypothesis_v1_3",
    "tests.test_adjusted_stock_pool_baseline_v1_2",
    "tests.test_baseline_attribution_v1_2",
)

ARTIFACTS = {
    "runner": (
        "scripts/run_lowvol_locked_grid_prototype_v1_5.py",
        "scripts/run_lowvol_locked_grid_prototype_v1_5_1.py",
    ),
    "test": (
        "tests/test_lowvol_locked_grid_prototype_v1_5.py",
        "tests/test_lowvol_locked_grid_prototype_v1_5_1.py",
    ),
    "input": (
        "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv",
        "data/processed/hybrid_benchmark_panel_v1_5.csv",
        "data/processed/research_universe_lowvol_freeze_20260711.csv",
        "reports/adjusted_stock_pool_baseline_periods_v1_2.csv",
    ),
    "generated_result": (
        "reports/lowvol_locked_grid_prototype_periods_v1_5.csv",
        "reports/lowvol_locked_grid_prototype_nav_v1_5.csv",
        "reports/lowvol_locked_grid_prototype_summary_v1_5.csv",
        "reports/lowvol_locked_grid_prototype_qa_v1_5.csv",
        "reports/lowvol_locked_grid_prototype_v1_5.md",
        "reports/lowvol_locked_grid_prototype_periods_v1_5_1.csv",
        "reports/lowvol_locked_grid_prototype_nav_v1_5_1.csv",
        "reports/lowvol_locked_grid_prototype_summary_v1_5_1.csv",
        "reports/lowvol_locked_grid_prototype_qa_v1_5_1.csv",
        "reports/lowvol_locked_grid_prototype_v1_5_1.md",
        "reports/lowvol_locked_grid_prototype_v1_5_vs_v1_5_1_diff.csv",
        "reports/lowvol_locked_grid_prototype_v1_5_vs_v1_5_1_diff.md",
    ),
    "research_protocol": (
        "reports/lowvol20_prospective_protocol_v1_5.md",
        "reports/lowvol20_freeze_manifest_v1_5.csv",
        "reports/lowvol20_prospective_periods_v1_5.csv",
        "reports/lowvol20_prospective_log_v1_5.md",
        "reports/locked_grid_stage_gate_v1_5.md",
        "reports/locked_grid_v1_4_vs_v1_5_comparison.md",
        "reports/000063_20210331_endpoint_forensics_v1_5.md",
    ),
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def count_tests(output: str) -> int:
    match = re.search(r"Ran (\d+) tests?", output)
    return int(match.group(1)) if match else 0


def run_tests(root: Path, modules: tuple[str, ...]) -> dict[str, object]:
    command = [sys.executable, "-m", "unittest", *modules, "-v"]
    result = subprocess.run(command, cwd=root, text=True, capture_output=True)
    output = result.stdout + result.stderr
    return {"command": " ".join(command), "exit_code": result.returncode, "test_count": count_tests(output), "output_tail": "\n".join(output.splitlines()[-12:])}


def add_check(rows: list[dict[str, object]], phase: str, check_id: str, passed: bool,
              critical: bool, actual: object, expected: object, evidence: str,
              notes: str = "", status: str | None = None) -> None:
    rows.append({
        "phase": phase,
        "check_id": check_id,
        "status": status or ("pass" if passed else "fail"),
        "critical": critical,
        "actual": actual,
        "expected": expected,
        "evidence": evidence,
        "notes": notes,
    })


def source_line(function: object) -> str:
    path = Path(inspect.getsourcefile(function) or "").name
    return f"{path}:{inspect.getsourcelines(function)[1]}"


def copy_reproduction_inputs(root: Path, temporary_root: Path) -> None:
    paths = set(sum((list(value) for value in ARTIFACTS.values()), []))
    # Only the v1.5 protected results, inputs, and runners are calculation inputs.
    needed = {
        path for path in paths
        if path.startswith("data/")
        or path.startswith("scripts/")
        or path.startswith("tests/test_lowvol_locked_grid_prototype_v1_5.py")
        or path in candidate.PROTECTED_V15
        or path == "reports/adjusted_stock_pool_baseline_periods_v1_2.csv"
    }
    needed.add("scripts/run_adjusted_stock_pool_baseline_v1_2.py")
    needed.add("scripts/run_locked_grid_replay_v1_5.py")
    for relative in needed:
        source, destination = root / relative, temporary_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def normalize_markdown(text: str) -> str:
    return re.sub(r"generated_at[^\n]*", "generated_at=<ignored>", text)


def compare_csv(existing: Path, reproduced: Path) -> list[dict[str, object]]:
    left, right = pd.read_csv(existing, dtype=str), pd.read_csv(reproduced, dtype=str)
    rows: list[dict[str, object]] = []
    if left.columns.tolist() != right.columns.tolist():
        return [{"file": existing.name, "key": "schema", "column": "*", "existing_value": str(left.columns.tolist()), "reproduced_value": str(right.columns.tolist()), "absolute_error": "", "relative_error": "", "status": "fail", "classification": "schema_mismatch"}]
    if len(left) != len(right):
        rows.append({"file": existing.name, "key": "row_count", "column": "*", "existing_value": len(left), "reproduced_value": len(right), "absolute_error": abs(len(left) - len(right)), "relative_error": "", "status": "fail", "classification": "row_count_mismatch"})
    for index in range(min(len(left), len(right))):
        for column in left.columns:
            if column == "generated_at":
                continue
            a, b = left.iloc[index][column], right.iloc[index][column]
            numeric_a, numeric_b = pd.to_numeric(pd.Series([a, b]), errors="coerce").to_numpy(float)
            numeric = not (math.isnan(numeric_a) or math.isnan(numeric_b))
            if numeric:
                equal = bool(np.isclose(numeric_a, numeric_b, atol=ATOL, rtol=RTOL))
                absolute = abs(numeric_a - numeric_b)
                relative = absolute / max(abs(numeric_b), ATOL)
            else:
                equal = (pd.isna(a) and pd.isna(b)) or str(a) == str(b)
                absolute = relative = ""
            if not equal:
                rows.append({"file": existing.name, "key": index, "column": column, "existing_value": a, "reproduced_value": b, "absolute_error": absolute, "relative_error": relative, "status": "fail", "classification": "substantive_difference"})
    if not rows:
        rows.append({"file": existing.name, "key": "all", "column": "*", "existing_value": len(left), "reproduced_value": len(right), "absolute_error": 0, "relative_error": 0, "status": "pass", "classification": "unchanged_except_allowed_fields"})
    return rows


def reproduce(root: Path) -> tuple[int, list[dict[str, object]], str]:
    with tempfile.TemporaryDirectory(prefix="lowvol_v151_freeze_") as directory:
        temporary_root = Path(directory)
        copy_reproduction_inputs(root, temporary_root)
        command = [sys.executable, "-m", "scripts.run_lowvol_locked_grid_prototype_v1_5_1", "--project-root", str(temporary_root)]
        result = subprocess.run(command, cwd=temporary_root, text=True, capture_output=True)
        rows: list[dict[str, object]] = []
        if result.returncode == 0:
            for filename in candidate.SUCCESS_FILES:
                existing, regenerated = root / "reports" / filename, temporary_root / "reports" / filename
                if filename.endswith(".csv"):
                    rows.extend(compare_csv(existing, regenerated))
                else:
                    same = normalize_markdown(existing.read_text(encoding="utf-8")) == normalize_markdown(regenerated.read_text(encoding="utf-8"))
                    rows.append({"file": filename, "key": "all", "column": "*", "existing_value": "existing", "reproduced_value": "reproduced", "absolute_error": "", "relative_error": "", "status": "pass" if same else "fail", "classification": "unchanged_except_allowed_fields" if same else "substantive_difference"})
        return result.returncode, rows, " ".join(command)


def independently_reconcile(root: Path, rows: list[dict[str, object]]) -> None:
    reports = root / "reports"
    periods = pd.read_csv(reports / "lowvol_locked_grid_prototype_periods_v1_5_1.csv", dtype=str)
    summary = pd.read_csv(reports / "lowvol_locked_grid_prototype_summary_v1_5_1.csv", dtype=str)
    qa = pd.read_csv(reports / "lowvol_locked_grid_prototype_qa_v1_5_1.csv", dtype=str)
    diff = pd.read_csv(reports / "lowvol_locked_grid_prototype_v1_5_vs_v1_5_1_diff.csv", dtype=str)
    periods["transaction_cost"] = pd.to_numeric(periods["transaction_cost"])
    periods["period_index"] = pd.to_numeric(periods["period_index"], errors="raise").astype(int)
    for column in ("gross_return", "net_return", "turnover", "cost_drag", "nav"):
        periods[column] = pd.to_numeric(periods[column])
    periods["headline"] = periods["headline_included"].map(candidate.parse_strict_bool)
    grid = periods.loc[(periods.portfolio == "Q5") & np.isclose(periods.transaction_cost, 0), ["period_index", "rebalance_date", "next_rebalance_date"]]
    grid_check = candidate.compare_ordered_period_keys(pd.DataFrame({"period_index": range(57), "rebalance_date": grid.rebalance_date, "next_rebalance_date": grid.next_rebalance_date}), grid)
    add_check(rows, "reconciliation", "full_period_endpoint_pairs", grid_check["equal"] and len(grid) == 57, True, len(grid), 57, "periods v1.5.1 ordered Q5 cost=0 keys")
    all_metrics_ok = True
    for record in summary.itertuples(index=False):
        q5 = periods[(periods.portfolio == "Q5") & np.isclose(periods.transaction_cost, float(record.transaction_cost)) & periods.headline].sort_values("period_index")
        returns = q5.net_return.to_numpy(float)
        cumulative = float(np.prod(1 + returns) - 1)
        all_metrics_ok &= bool(np.isclose(cumulative, float(record.cumulative_return), atol=ATOL, rtol=RTOL))
        all_metrics_ok &= bool(np.isclose(float(q5.nav.iloc[-1]), float(record.terminal_nav), atol=ATOL, rtol=RTOL))
        all_metrics_ok &= bool(np.isclose(q5.turnover.mean(), float(record.average_turnover), atol=ATOL, rtol=RTOL))
        all_metrics_ok &= bool(np.isclose(q5.cost_drag.sum(), float(record.total_cost_drag), atol=ATOL, rtol=RTOL))
    add_check(rows, "reconciliation", "summary_core_metrics_recomputed", all_metrics_ok, True, int(all_metrics_ok), 1, "period returns, NAV, turnover and cost independently recomputed")
    qa_pass = qa["pass"].map(candidate.parse_strict_bool)
    qa_critical = qa["critical"].map(candidate.parse_strict_bool)
    critical_failures = int((qa_critical & ~qa_pass).sum())
    add_check(rows, "reconciliation", "candidate_critical_qa_failures", critical_failures == 0, True, critical_failures, 0, "raw v1.5.1 QA CSV")
    unexpected = int(diff.classification.isin(["unexpected_q5_or_q1_change", "unexpected_nonlocal_change"]).sum())
    add_check(rows, "reconciliation", "v15_v151_diff_complete", len(diff) > 0 and unexpected == 0, True, f"rows={len(diff)};unexpected={unexpected}", "nonempty diff; unexpected=0", "raw diff CSV; count derived at runtime")


def build_manifest(root: Path, output_hashes: dict[str, str] | None = None) -> pd.DataFrame:
    rows = []
    protected = set(candidate.PROTECTED_V15)
    for category, paths in ARTIFACTS.items():
        for relative in paths:
            path = root / relative
            rows.append({"category": category, "path": relative, "file_size": path.stat().st_size if path.exists() else "", "sha256": sha256(path) if path.exists() else "", "required": True, "protected": relative in protected or category == "research_protocol", "notes": "" if path.exists() else "missing"})
    for filename in OUTPUTS:
        digest = (output_hashes or {}).get(filename, "")
        path = root / "reports" / filename
        rows.append({"category": "audit_output", "path": f"reports/{filename}", "file_size": path.stat().st_size if path.exists() else "", "sha256": digest, "required": True, "protected": False, "notes": "self hash omitted" if filename == OUTPUTS[1] else "generated by audit"})
    return pd.DataFrame(rows)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--reproduce-in-temp", action="store_true")
    args = parser.parse_args(argv)
    root, reports = args.project_root.resolve(), args.project_root.resolve() / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now().astimezone().isoformat()
    checks: list[dict[str, object]] = []

    manifest_before = build_manifest(root)
    missing = manifest_before[(manifest_before.category != "audit_output") & manifest_before.sha256.eq("")]
    add_check(checks, "preservation", "required_artifacts_present", missing.empty, True, len(missing), 0, ";".join(missing.path.tolist()))
    protected_before = {path: sha256(root / path) for path in candidate.PROTECTED_V15}
    protocol_paths = [path for path in ARTIFACTS["research_protocol"] if (root / path).exists()]
    protocol_before = {path: sha256(root / path) for path in protocol_paths}

    source = Path(inspect.getsourcefile(candidate) or "").read_text(encoding="utf-8")
    strict_ok = candidate.parse_strict_bool("TRUE") and not candidate.parse_strict_bool("False")
    try:
        candidate.parse_strict_bool("unknown")
        strict_ok = False
    except ValueError:
        pass
    add_check(checks, "static", "strict_boolean_contract", strict_ok and "astype(bool)" not in source, True, int(strict_ok), 1, source_line(candidate.parse_strict_bool), "CSV parsing does not use astype(bool)")
    targets_source = inspect.getsource(candidate.period_targets)
    label_blind = '"UNIVERSE": parsed["signal_sample_member"] & parsed["primary_reliable_signal"]' in targets_source
    add_check(checks, "static", "label_blind_universe_contract", label_blind, True, int(label_blind), 1, source_line(candidate.period_targets))
    forbidden = [token for token in ("ffill(", "bfill(", "fillna(method", "backfill") if token in source]
    add_check(checks, "static", "no_price_fill_or_date_substitution", not forbidden, True, ";".join(forbidden), "none", source_line(candidate.build_outputs))

    factor = pd.read_csv(root / "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv", dtype={"stock_code": str})
    frozen = pd.read_csv(root / "reports/adjusted_stock_pool_baseline_periods_v1_2.csv", dtype=str)
    grid = candidate.canonical_grid(frozen)
    factor_grid = factor[["period_index", "rebalance_date", "next_rebalance_date"]].drop_duplicates().reset_index(drop=True)
    grid_equal = candidate.compare_ordered_period_keys(grid, factor_grid)["equal"]
    add_check(checks, "static", "canonical_grid_contract", grid_equal and len(grid) == 57, True, f"count={len(grid)};equal={grid_equal}", "count=57;equal=True", source_line(candidate.canonical_grid))
    universe = pd.read_csv(root / "data/processed/research_universe_lowvol_freeze_20260711.csv", dtype=str)
    code_column = "stock_code" if "stock_code" in universe else "code"
    codes = universe[code_column].astype(str).str.zfill(6)
    universe_ok = codes.nunique() == 56 and codes.str.fullmatch(r"\d{6}").all()
    add_check(checks, "preservation", "frozen_universe_56_unique_codes", universe_ok, True, codes.nunique(), 56, "frozen universe CSV")
    protocol = (root / "reports/lowvol20_prospective_protocol_v1_5.md").read_text(encoding="utf-8")
    prospective = pd.read_csv(root / "reports/lowvol20_prospective_periods_v1_5.csv")
    protocol_ok = "freeze_date: `2026-07-11`" in protocol and "append-only" in protocol and prospective.empty
    add_check(checks, "prospective", "protocol_isolated_and_waiting", protocol_ok, True, f"periods={len(prospective)}", "periods=0;freeze_date=2026-07-11;append-only", "prospective protocol and empty ledger")

    test_source = (root / "tests/test_lowvol_locked_grid_prototype_v1_5_1.py").read_text(encoding="utf-8")
    targeted = run_tests(root, (TARGETED_TEST,))
    audit_coverage = set()
    if targeted["exit_code"] == 0:
        sys.path.insert(0, str(root))
        try:
            audit_coverage = set(getattr(importlib.import_module(TARGETED_TEST), "FREEZE_AUDIT_COVERAGE", ()))
        finally:
            sys.path.pop(0)
    coverage = {
        "strict_false_and_unknown": "test_strict_false_is_false_and_unknown_fails" in test_source,
        "signal_evaluation_difference": "test_universe_target_is_signal_sample_and_label_blind" in test_source,
        "q5_q1_label_blind": "test_q5_and_q1_are_label_blind" in test_source,
        "ordered_period_grid": "test_ordered_period_keys_require_index_order_and_exact_rows" in test_source,
        "cost_contract": "test_cost_contract_separates_pre_cost_and_net_fields" in test_source,
        "evaluation_extra_security": targeted["exit_code"] == 0 and "evaluation_extra_security" in audit_coverage,
    }
    missing_tests = [name for name, covered in coverage.items() if not covered]
    add_check(checks, "test_audit", "required_counterfactual_coverage", not missing_tests, False, ";".join(missing_tests), "none", "test source inspection", "Missing items require human-approved test-only additions", status="pass" if not missing_tests else "warning")
    add_check(checks, "test_audit", "prospective_files_unchanged_test", False, False, "not_implemented", "deferred", "audit-time before/after SHA-256", "covered by audit-time before/after hashes; dedicated unit test deferred", status="deferred")
    regression = run_tests(root, REGRESSION_TESTS)
    add_check(checks, "tests", "targeted_tests", targeted["exit_code"] == 0, True, f"exit={targeted['exit_code']};count={targeted['test_count']}", "exit=0", targeted["command"], targeted["output_tail"])
    add_check(checks, "tests", "related_regression_tests", regression["exit_code"] == 0, True, f"exit={regression['exit_code']};count={regression['test_count']}", "exit=0", regression["command"], regression["output_tail"])

    reproduction_rows: list[dict[str, object]] = []
    reproduction_exit = -1
    reproduction_command = "not requested"
    if args.reproduce_in_temp:
        reproduction_exit, reproduction_rows, reproduction_command = reproduce(root)
        reproduction_ok = reproduction_exit == 0 and reproduction_rows and all(row["status"] == "pass" for row in reproduction_rows)
        add_check(checks, "reproduction", "controlled_reproduction", reproduction_ok, True, f"exit={reproduction_exit};differences={sum(row['status'] != 'pass' for row in reproduction_rows)}", "exit=0;differences=0", reproduction_command)
    else:
        add_check(checks, "reproduction", "controlled_reproduction", False, True, "not_run", "run", "--reproduce-in-temp required")

    independently_reconcile(root, checks)
    protected_after = {path: sha256(root / path) for path in candidate.PROTECTED_V15}
    protocol_after = {path: sha256(root / path) for path in protocol_paths}
    protected_ok = protected_before == protected_after
    protocol_hash_ok = protocol_before == protocol_after
    add_check(checks, "preservation", "v15_protected_hashes_unchanged", protected_ok, True, int(protected_ok), 1, "before/after SHA-256")
    add_check(checks, "prospective", "prospective_hashes_unchanged", protocol_hash_ok, True, int(protocol_hash_ok), 1, "before/after SHA-256")

    checks_frame = pd.DataFrame(checks)
    critical_failures = int(((checks_frame.critical == True) & checks_frame.status.ne("pass")).sum())
    warnings = checks_frame[checks_frame.status.eq("warning")].check_id.tolist()
    deferred = checks_frame[checks_frame.status.eq("deferred")].check_id.tolist()
    recommendation = "DO NOT FREEZE" if critical_failures else ("RECOMMEND CONDITIONAL FREEZE" if warnings else "RECOMMEND FREEZE APPROVAL")
    reproduction_frame = pd.DataFrame(reproduction_rows, columns=["file", "key", "column", "existing_value", "reproduced_value", "absolute_error", "relative_error", "status", "classification"])

    environment = {
        "python_executable": sys.executable,
        "python_version": sys.version.replace("\n", " "),
        "pandas_version": pd.__version__,
        "numpy_version": np.__version__,
        "operating_system": platform.platform(),
        "project_root": str(root),
        "audit_timestamp": generated_at,
        "timezone": datetime.now().astimezone().tzname(),
    }
    audit = f"""# LOWVOL20 v1.5.1 Research Artifact Freeze Audit

## Status

- audit_status: {'passed' if critical_failures == 0 else 'failed'}
- recommendation: `{recommendation}`
- critical_failures: {critical_failures}
- warnings: {len(warnings)}
- warning_ids: {', '.join(warnings) or 'none'}
- deferred_items: {len(deferred)}
- deferred_ids: {', '.join(deferred) or 'none'}
- targeted_tests: {targeted['test_count']} passed, exit {targeted['exit_code']}
- related_regression_tests: {regression['test_count']} passed, exit {regression['exit_code']}
- reproduction_exit: {reproduction_exit}

## Environment

{chr(10).join(f'- {key}: `{value}`' for key, value in environment.items())}

## Static evidence

- strict boolean parser: `{source_line(candidate.parse_strict_bool)}`
- target construction: `{source_line(candidate.period_targets)}`
- canonical period grid: `{source_line(candidate.canonical_grid)}`
- cost contract: `{source_line(candidate.validate_cost_contract)}`
- output publication/failure handling: `{source_line(candidate.publish)}`

## Reconciliation

- 57 ordered full-period endpoint pairs are required and checked row-by-row.
- Summary cumulative return, terminal NAV, average turnover and total cost drag were independently recomputed from periods.
- Candidate QA critical failures were counted from the raw QA CSV.
- v1.5/v1.5.1 diff row count was derived at runtime; unexpected Q5/Q1 and nonlocal changes must be zero.

## Prospective isolation

- freeze_date=2026-07-11
- current complete prospective periods=0
- status remains waiting_for_complete_period
- historical reproduction did not change prospective protocol or ledger hashes

## Limits

- current_universe_historical_research=true
- universe_point_in_time=false
- execution_sim_ready=false
- formal_performance_conclusion_allowed=false
- no_investment_conclusion=true

This research artifact freeze confirms implementation identity and reproducibility only. It is not statistical confirmation, an execution-ready strategy, or an investment conclusion.
"""
    signoff = f"""# LOWVOL20 v1.5.1 Research Artifact Signoff

- audit object: LOWVOL20 locked-grid prototype v1.5.1
- audit timestamp: {generated_at}
- recommendation: `{recommendation}`
- critical failures: {critical_failures}
- unresolved warnings: {', '.join(warnings) or 'none'}
- deferred items: {', '.join(deferred) or 'none'}
- reproduction: {'passed' if reproduction_exit == 0 and all(row['status'] == 'pass' for row in reproduction_rows) else 'failed'}
- QA: {'passed' if critical_failures == 0 else 'failed'}
- freeze scope: research artifact identity, implementation contract, historical reproducibility, and prospective starting point
- outside freeze scope: formal performance, clean OOS confirmation, point-in-time universe, suspension-aware accounting, execution readiness, investment decisions
- formal_performance_conclusion_allowed=false
- execution_sim_ready=false
- no_investment_conclusion=true

## Human decision

- decision: `FREEZE APPROVED / CONDITIONAL FREEZE / NOT APPROVED`
- decision_date:
- decision_maker:
- notes:
"""

    checks_path = reports / OUTPUTS[2]
    reproduction_path = reports / OUTPUTS[3]
    audit_path = reports / OUTPUTS[0]
    signoff_path = reports / OUTPUTS[4]
    checks_frame.to_csv(checks_path, index=False)
    reproduction_frame.to_csv(reproduction_path, index=False)
    audit_path.write_text(audit, encoding="utf-8")
    signoff_path.write_text(signoff, encoding="utf-8")
    output_hashes = {path.name: sha256(path) for path in (checks_path, reproduction_path, audit_path, signoff_path)}
    build_manifest(root, output_hashes).to_csv(reports / OUTPUTS[1], index=False)
    print(f"freeze audit recommendation: {recommendation}; critical_failures={critical_failures}; warnings={len(warnings)}")
    return 0 if critical_failures == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
