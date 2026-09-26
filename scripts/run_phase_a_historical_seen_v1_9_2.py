"""Reproduce the fixed Phase A historical_seen example without configurable research inputs."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import platform
import subprocess
import sys
import traceback
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from aq_factor_lab.phase_a_evaluation import (
    FROZEN_HASHES,
    PRIMARY_COST_RATE,
    assign_contract_members,
    cross_sectional_diagnostics,
    lineage_audit,
    long_only_paths,
    primary_relative_wealth,
    rank_ic_periods,
    validate_official_period_mapping,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_BASE = ROOT / "reports" / "phase_a_historical_seen_reproduction_v1_9_2"
PANEL_PATH = ROOT / "data" / "processed" / "mom60_factor_panel_v1_3.csv"
OFFICIAL_IC_PATH = ROOT / "reports" / "factor_ic_periods_mom60_v1_3.csv"
READINESS_PATH = ROOT / "reports" / "factor_data_readiness_v1_3.csv"
MODULE_PATH = ROOT / "src" / "aq_factor_lab" / "phase_a_evaluation.py"
PROTOCOL_PATHS = (
    ROOT / "reports" / "research_execution_plan_v1_9_1.md",
    ROOT / "reports" / "research_execution_plan_v1_9_2_amendment.md",
)
EXPECTED_HASHES = {
    PROTOCOL_PATHS[0]: "37f2da99fc2b691dfff8d73201bfcf5ae0016ae5a07270411f538f36e87a533a",
    PROTOCOL_PATHS[1]: "3950bcf62f9cc7baf471795c35ec0dd4904f9f79259e520a3762ba488ead0e90",
    MODULE_PATH: "5e6062c15219e60e1d6e8991c952c59ce10909a2c6ba87927184008e55f9f062",
    PANEL_PATH: "2c25fb4196da19b24463cdfdb23fa821c85cf22e2d53576d8f13fe792c0aa341",
    OFFICIAL_IC_PATH: "a9aedc5a58d847bbd7443bdf8995045f8bb53efdb743d1f15c7cb84b8211e385",
    READINESS_PATH: "9803c6fba880f2a1679b7275c04cac5a9d1fd6438207e3911fea16b32e6d840e",
}
IDENTITY = {
    "sample_role": "historical_seen",
    "evidence_status": "historical_seen",
    "claim_status": "descriptive_only",
    "formal_alpha_conclusion_allowed": False,
    "orientation_alpha_increment": 0,
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def utc_now() -> datetime:
    return datetime.now(UTC)


def run_id(now: datetime) -> str:
    return now.strftime("%Y%m%dT%H%M%S%fZ")


def create_run_directory(base: Path, identifier: str) -> Path:
    path = base / identifier
    path.mkdir(parents=True, exist_ok=False)
    return path


def with_identity(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column, value in IDENTITY.items():
        result[column] = value
    return result


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    with_identity(frame).to_csv(path, index=False, encoding="utf-8-sig")


def verify_required_hashes() -> pd.DataFrame:
    rows = []
    for path, expected in EXPECTED_HASHES.items():
        actual = sha256(path) if path.is_file() else ""
        rows.append(
            {
                "path": path.relative_to(ROOT).as_posix(),
                "expected_sha256": expected,
                "actual_sha256": actual,
                "pass": actual == expected,
            }
        )
    result = pd.DataFrame(rows)
    if not result["pass"].all():
        failed = result.loc[~result["pass"], "path"].tolist()
        raise ValueError(f"required_hash_mismatch paths={failed}")
    return result


def frozen_hashes() -> dict[str, str]:
    return {
        relative: sha256(ROOT / relative) if (ROOT / relative).is_file() else ""
        for relative in FROZEN_HASHES
    }


def load_fixed_sample() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    panel = pd.read_csv(PANEL_PATH, dtype={"stock_code": str})
    official = pd.read_csv(OFFICIAL_IC_PATH)
    readiness = pd.read_csv(READINESS_PATH, dtype=str)
    primary = official.loc[
        official["factor_name"].eq("MOM60") & official["sample_basis"].eq("mom60_primary_sample")
    ]
    keys = set(pd.to_numeric(primary["period_index"], errors="raise").astype(int))
    period_index = pd.to_numeric(panel["period_index"], errors="raise").astype(int)
    selected = panel.loc[period_index.isin(keys)].copy()
    selected["period_index"] = period_index.loc[selected.index]
    return selected, official, readiness


def failure_log(
    rankics: pd.DataFrame, paths: pd.DataFrame, diagnostics: pd.DataFrame
) -> pd.DataFrame:
    rows = []
    for row in rankics.loc[~rankics["rank_ic_valid"]].itertuples(index=False):
        rows.append(
            {
                "component": "rank_ic",
                "period_index": row.period_index,
                "failure_reason": row.failure_reason,
            }
        )
    for row in paths.loc[~paths["period_portfolio_status"].eq("ok")].itertuples(index=False):
        rows.append(
            {
                "component": row.portfolio,
                "period_index": row.period_index,
                "failure_reason": row.period_portfolio_status,
            }
        )
    for row in diagnostics.loc[diagnostics["result_role"].eq("invalid_diagnostic")].itertuples(
        index=False
    ):
        rows.append(
            {
                "component": "q5_q1_diagnostic",
                "period_index": row.period_index,
                "failure_reason": "invalid_diagnostic",
            }
        )
    return pd.DataFrame(rows, columns=["component", "period_index", "failure_reason"])


def reproduce(output: Path, started: datetime) -> None:
    required_hashes = verify_required_hashes()
    frozen_before = frozen_hashes()
    selected, official, readiness = load_fixed_sample()
    assigned, coverage = assign_contract_members(selected)
    canonical_periods = validate_official_period_mapping(assigned, official, readiness)
    rankics = rank_ic_periods(assigned)
    paths = long_only_paths(assigned, PRIMARY_COST_RATE)
    diagnostics = cross_sectional_diagnostics(assigned)
    lineage = lineage_audit(assigned)
    failures = failure_log(rankics, paths, diagnostics)
    relative_wealth = primary_relative_wealth(paths)

    identity_error = (rankics["raw_rank_ic"] + rankics["oriented_rank_ic"]).abs().max()
    qa = pd.DataFrame(
        [
            ("official_period_mapping", len(canonical_periods) == 54, len(canonical_periods), 54),
            (
                "target_returns_complete",
                bool(assigned.loc[assigned["signal_target_member"], "label_available"].all()),
                int((~assigned.loc[assigned["signal_target_member"], "label_available"]).sum()),
                0,
            ),
            (
                "rankic_orientation_identity",
                bool(identity_error <= 1e-12),
                identity_error,
                0.0,
            ),
            (
                "primary_paths_complete",
                bool(paths["primary_portfolio_metric_valid"].all()),
                int((~paths["primary_portfolio_metric_valid"]).sum()),
                0,
            ),
            (
                "primary_relative_wealth_finite",
                bool(np.isfinite(relative_wealth)),
                relative_wealth,
                "finite",
            ),
            ("failure_log_empty", failures.empty, len(failures), 0),
        ],
        columns=["check", "pass", "actual", "expected"],
    )

    membership_columns = [
        "period_index",
        "stock_code",
        "signal_as_of_date",
        "rebalance_date",
        "next_rebalance_date",
        "baseline_eligible",
        "signal_sample_member",
        "signal_target_member",
        "label_available",
        "evaluation_sample_member",
        "mom60",
        "raw_quantile",
        "oriented_quantile",
    ]
    write_csv(required_hashes, output / "input_hashes.csv")
    write_csv(canonical_periods, output / "official_period_mapping.csv")
    write_csv(assigned[membership_columns], output / "membership_assignments.csv")
    write_csv(coverage, output / "period_coverage_ties.csv")
    write_csv(rankics, output / "rank_ic_periods.csv")
    write_csv(paths, output / "long_only_paths_20bps.csv")
    write_csv(diagnostics, output / "q5_q1_diagnostic_periods.csv")
    write_csv(lineage, output / "lineage_audit.csv")
    write_csv(failures, output / "failure_log.csv")
    write_csv(qa, output / "qa_checks.csv")

    metadata = pd.DataFrame(
        [
            {
                "run_id": output.name,
                "run_at_utc": started.isoformat(),
                "command": subprocess.list2cmdline([sys.executable, *sys.argv]),
                "python_version": platform.python_version(),
                "pandas_version": pd.__version__,
                "numpy_version": np.__version__,
                "cli_sha256": sha256(Path(__file__)),
                "module_sha256": sha256(MODULE_PATH),
                "input_sha256": sha256(PANEL_PATH),
                "official_period_sha256": sha256(OFFICIAL_IC_PATH),
                "readiness_sha256": sha256(READINESS_PATH),
                "primary_cost_rate": PRIMARY_COST_RATE,
                "primary_portfolio_metric": (
                    "oriented_Q5_long_only_net_relative_wealth_vs_universe_20bps"
                ),
                "primary_portfolio_metric_value": relative_wealth,
                **IDENTITY,
            }
        ]
    )
    write_csv(metadata, output / "run_metadata.csv")

    frozen_after = frozen_hashes()
    frozen = pd.DataFrame(
        [
            {
                "path": relative,
                "expected_sha256": FROZEN_HASHES[relative],
                "sha256_before": frozen_before[relative],
                "sha256_after": frozen_after[relative],
                "before_equals_after": frozen_before[relative] == frozen_after[relative],
                "matches_frozen_contract": frozen_after[relative] == FROZEN_HASHES[relative],
            }
            for relative in FROZEN_HASHES
        ]
    )
    write_csv(frozen, output / "frozen_hash_checks.csv")
    if (
        not qa["pass"].all()
        or not frozen[["before_equals_after", "matches_frozen_contract"]].all().all()
    ):
        raise RuntimeError("phase_a_reproduction_qa_failed")

    report = f"""# Phase A historical_seen reproduction

```text
sample_role=historical_seen
evidence_status=historical_seen
claim_status=descriptive_only
formal_alpha_conclusion_allowed=false
orientation_alpha_increment=0
```

- run_id: `{output.name}`
- official periods: `{len(canonical_periods)}`
- invalid RankIC periods: `{int((~rankics["rank_ic_valid"]).sum())}`
- invalid portfolio rows: `{int((~paths["primary_portfolio_metric_valid"]).sum())}`
- primary relative wealth: `{relative_wealth:.12f}`
- failure rows: `{len(failures)}`
- QA: `pass`

REV60 is only the fixed negative orientation of MOM60. This output is a historical
reproduction and cannot establish clean validation, OOS performance, or an Alpha claim.
"""
    (output / "report.md").write_text(report, encoding="utf-8")


def self_check() -> None:
    rows = []
    for period in range(2):
        signal = pd.Timestamp("2024-01-01") + pd.DateOffset(months=period)
        for stock in range(25):
            rows.append(
                {
                    "period_index": period,
                    "stock_code": f"{stock + 1:06d}",
                    "signal_as_of_date": signal,
                    "rebalance_date": signal + pd.Timedelta(days=1),
                    "next_rebalance_date": signal + pd.DateOffset(months=1, days=1),
                    "baseline_eligible": "true",
                    "signal_sample_member": "true",
                    "mom60": float(stock),
                    "forward_return": (12 - stock) / 100,
                }
            )
    assigned, _ = assign_contract_members(pd.DataFrame(rows))
    rankics = rank_ic_periods(assigned)
    paths = long_only_paths(assigned)
    assert len(rankics) == 2
    assert paths["primary_portfolio_metric_valid"].all()
    assert np.isfinite(primary_relative_wealth(paths))
    assert (rankics["raw_rank_ic"] + rankics["oriented_rank_ic"]).abs().max() <= 1e-12
    print("phase_a_historical_seen_self_check=pass")


def write_output_hashes(output: Path) -> None:
    rows = [
        {
            "path": path.relative_to(output).as_posix(),
            "sha256": sha256(path),
            "bytes": path.stat().st_size,
        }
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "output_hashes.csv"
    ]
    pd.DataFrame(rows).to_csv(output / "output_hashes.csv", index=False, encoding="utf-8-sig")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-check", action="store_true")
    mode.add_argument("--confirm-historical-seen", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_check:
        self_check()
        return 0

    started = utc_now()
    output = create_run_directory(OUTPUT_BASE, run_id(started))
    command = subprocess.list2cmdline([sys.executable, *sys.argv])
    (output / "command.txt").write_text(command + "\n", encoding="utf-8")
    stdout, stderr = io.StringIO(), io.StringIO()
    exit_code = 0
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        try:
            reproduce(output, started)
            print("phase_a_historical_seen_reproduction=pass")
        except Exception as error:
            traceback.print_exc()
            exit_code = 2
            if not (output / "failure_log.csv").exists():
                write_csv(
                    pd.DataFrame(
                        [
                            {
                                "component": "run",
                                "period_index": "",
                                "failure_reason": f"{type(error).__name__}: {error}",
                            }
                        ]
                    ),
                    output / "failure_log.csv",
                )
            if not (output / "qa_checks.csv").exists():
                write_csv(
                    pd.DataFrame(
                        [
                            {
                                "check": "run_completed",
                                "pass": False,
                                "actual": type(error).__name__,
                                "expected": "completed",
                            }
                        ]
                    ),
                    output / "qa_checks.csv",
                )
            if not (output / "report.md").exists():
                (output / "report.md").write_text(
                    "# Phase A historical_seen reproduction\n\n"
                    f"- status: `blocked`\n- failure: `{type(error).__name__}: {error}`\n",
                    encoding="utf-8",
                )
    (output / "stdout.log").write_text(stdout.getvalue(), encoding="utf-8")
    (output / "stderr.log").write_text(stderr.getvalue(), encoding="utf-8")
    (output / "exit_code.txt").write_text(f"{exit_code}\n", encoding="ascii")
    write_output_hashes(output)
    sys.stdout.write(stdout.getvalue())
    sys.stderr.write(stderr.getvalue())
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
