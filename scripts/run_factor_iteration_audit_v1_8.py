"""One auditable, development-only MOM60 direction iteration."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SPLIT_DATE = pd.Timestamp("2024-01-01")
INPUT_PANEL = Path("data/processed/mom60_factor_panel_v1_3.csv")
INPUT_PERIODS = Path("reports/factor_ic_periods_mom60_v1_3.csv")
LOG_PATH = Path("reports/factor_experiment_log_v1_8.csv")
REPORT_PATH = Path("reports/factor_iteration_comparison_v1_8.md")
ITERATION_ID = "MOM60_DIRECTION_V1_8"
PARENT_RUN_ID = "MOM60_V1_3"
COMMAND = "python scripts/run_factor_iteration_audit_v1_8.py --project-root ."
METRICS = (
    "mean_rank_ic",
    "median_rank_ic",
    "rank_ic_positive_ratio",
    "mean_q5_q1",
    "median_q5_q1",
    "q5_q1_positive_ratio",
    "mean_q5_universe",
    "cumulative_q5_nav",
    "quantile_return_spearman",
)
LOG_COLUMNS = (
    "iteration_id",
    "run_id",
    "parent_run_id",
    "row_type",
    "trial_role",
    "status",
    "factor_name",
    "hypothesis",
    "started_at_utc",
    "ended_at_utc",
    "command",
    "script_sha256",
    "input_path",
    "input_sha256",
    "parameters_json",
    "weakest_dimension",
    "diagnosis_metric",
    "changed_parameter",
    "old_value",
    "new_value",
    "changed_parameter_count",
    "sample_role",
    "sample_start",
    "sample_end",
    "used_for_selection",
    "metric",
    "expected_direction",
    "value",
    "baseline_value",
    "delta_vs_baseline",
    "period_count",
    "failure_stage",
    "error_type",
    "error_message",
    "artifact_path",
    "artifact_sha256",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def flag_true(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def assign_quantiles(group: pd.DataFrame, direction: int) -> pd.DataFrame:
    signal = group.loc[group["baseline_eligible"] & group["mom60"].notna()].copy()
    signal["score"] = direction * signal["mom60"]
    signal = signal.sort_values(["score", "stock_code"], kind="stable")
    signal["quantile"] = pd.Series(pd.NA, index=signal.index, dtype="Int64")
    if len(signal) < 5 or signal["score"].nunique() < 2:
        raise ValueError(f"invalid signal cross-section for period {group.iloc[0]['period_index']}")
    for quantile, indices in enumerate(np.array_split(signal.index.to_numpy(), 5), start=1):
        signal.loc[indices, "quantile"] = quantile
    return signal


def evaluate_periods(panel: pd.DataFrame, direction: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for period_index, group in panel.groupby("period_index", sort=True):
        signal = assign_quantiles(group, direction)
        evaluation = signal.loc[signal["forward_return"].notna()].copy()
        if len(evaluation) < 25:
            raise ValueError(f"period {period_index}: evaluation_count={len(evaluation)} below 25")
        rank_ic = evaluation["score"].corr(evaluation["forward_return"], method="spearman")
        if not math.isfinite(rank_ic):
            raise ValueError(f"period {period_index}: invalid rank IC")
        quantile_returns: dict[int, float] = {}
        for quantile in range(1, 6):
            members = signal.loc[signal["quantile"].eq(quantile)]
            labelled = members.loc[members["forward_return"].notna()]
            coverage = len(labelled) / len(members) if len(members) else 0.0
            if len(labelled) < 4 or coverage < 0.80:
                raise ValueError(
                    f"period {period_index} Q{quantile}: labels={len(labelled)}, "
                    f"coverage={coverage:.3f}"
                )
            quantile_returns[quantile] = float(labelled["forward_return"].mean())
        universe_return = float(evaluation["forward_return"].mean())
        rows.append(
            {
                "period_index": int(period_index),
                "rebalance_date": group.iloc[0]["rebalance_date"],
                "rank_ic": float(rank_ic),
                **{f"q{q}_return": value for q, value in quantile_returns.items()},
                "universe_return": universe_return,
                "q5_q1": quantile_returns[5] - quantile_returns[1],
                "q5_universe": quantile_returns[5] - universe_return,
            }
        )
    return pd.DataFrame(rows)


def summarize(periods: pd.DataFrame) -> dict[str, object]:
    if periods.empty:
        raise ValueError("empty evaluation partition")
    quantile_means = pd.Series(
        {q: periods[f"q{q}_return"].mean() for q in range(1, 6)}, dtype=float
    )
    return {
        "sample_start": periods["rebalance_date"].min().date().isoformat(),
        "sample_end": periods["rebalance_date"].max().date().isoformat(),
        "period_count": len(periods),
        "mean_rank_ic": float(periods["rank_ic"].mean()),
        "median_rank_ic": float(periods["rank_ic"].median()),
        "rank_ic_positive_ratio": float((periods["rank_ic"] > 0).mean()),
        "mean_q5_q1": float(periods["q5_q1"].mean()),
        "median_q5_q1": float(periods["q5_q1"].median()),
        "q5_q1_positive_ratio": float((periods["q5_q1"] > 0).mean()),
        "mean_q5_universe": float(periods["q5_universe"].mean()),
        "cumulative_q5_nav": float((1.0 + periods["q5_return"]).prod()),
        "quantile_return_spearman": float(
            quantile_means.corr(pd.Series(range(1, 6), index=range(1, 6)), method="spearman")
        ),
    }


def choose_direction(development_baseline: dict[str, object]) -> tuple[int, str]:
    mean_ic = float(development_baseline["mean_rank_ic"])
    mean_spread = float(development_baseline["mean_q5_q1"])
    if mean_ic < 0 and mean_spread < 0:
        return -1, "development mean Rank IC and mean Q5-Q1 are both negative"
    raise ValueError(
        "no unique direction weakness: development Rank IC and Q5-Q1 are not both negative"
    )


def load_panel(root: Path) -> tuple[pd.DataFrame, Path, str]:
    panel_path = root / INPUT_PANEL
    periods_path = root / INPUT_PERIODS
    if not panel_path.is_file() or not periods_path.is_file():
        raise FileNotFoundError(f"required inputs missing: {panel_path}, {periods_path}")
    panel = pd.read_csv(panel_path, dtype={"stock_code": str})
    required = {
        "period_index",
        "stock_code",
        "rebalance_date",
        "next_rebalance_date",
        "signal_as_of_date",
        "baseline_eligible",
        "signal_sample_member",
        "evaluation_sample_member",
        "mom60",
        "forward_return",
    }
    missing = required - set(panel.columns)
    if missing:
        raise ValueError(f"factor panel missing columns: {sorted(missing)}")
    if panel.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("duplicate period_index/stock_code in factor panel")
    for column in ("rebalance_date", "next_rebalance_date", "signal_as_of_date"):
        panel[column] = pd.to_datetime(panel[column], errors="raise")
    for column in ("period_index", "mom60", "forward_return"):
        panel[column] = pd.to_numeric(panel[column], errors="coerce")
    for column in ("baseline_eligible", "signal_sample_member", "evaluation_sample_member"):
        panel[column] = flag_true(panel[column])
    official = pd.read_csv(periods_path)
    official = official.loc[
        official["factor_name"].eq("MOM60")
        & official["sample_basis"].eq("mom60_primary_sample")
        & flag_true(official["ic_valid"])
    ].copy()
    if official.empty or official["period_index"].duplicated().any():
        raise ValueError("official MOM60 main-period keys are empty or duplicated")
    main_periods = set(pd.to_numeric(official["period_index"], errors="raise").astype(int))
    panel = panel.loc[panel["period_index"].isin(main_periods)].copy()
    actual = set(panel["period_index"].dropna().astype(int))
    if actual != main_periods:
        raise ValueError("factor panel does not cover every official MOM60 main period")
    expected_signal = panel["baseline_eligible"] & panel["mom60"].notna()
    expected_evaluation = expected_signal & panel["forward_return"].notna()
    if not expected_signal.equals(panel["signal_sample_member"]):
        raise ValueError("stored signal_sample_member does not match the MOM60 contract")
    if not expected_evaluation.equals(panel["evaluation_sample_member"]):
        raise ValueError("stored evaluation_sample_member does not match the label contract")
    if not (
        (panel["signal_as_of_date"] < panel["rebalance_date"])
        & (panel["rebalance_date"] < panel["next_rebalance_date"])
    ).all():
        raise ValueError("signal/rebalance/forward dates are not strictly ordered")
    return panel, panel_path, sha256(panel_path)


def audit_rows(
    metadata: dict[str, object],
    summaries: dict[tuple[str, str], dict[str, object]],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for (trial_role, sample_role), values in summaries.items():
        baseline = summaries[("baseline", sample_role)]
        direction = 1 if trial_role == "baseline" else -1
        hypothesis = (
            "Higher MOM60 predicts higher forward return"
            if trial_role == "baseline"
            else "Lower MOM60 predicts higher forward return (60-day reversal)"
        )
        parameters = {
            "lookback_trading_days": 60,
            "forward_horizon_trading_days": 20,
            "quantile_count": 5,
            "signal_direction": direction,
            "split_date": SPLIT_DATE.date().isoformat(),
        }
        for metric in METRICS:
            value = float(values[metric])
            baseline_value = float(baseline[metric])
            rows.append(
                {
                    **metadata,
                    "row_type": "metric",
                    "trial_role": trial_role,
                    "status": "completed",
                    "factor_name": "MOM60",
                    "hypothesis": hypothesis,
                    "parameters_json": json.dumps(parameters, sort_keys=True),
                    "weakest_dimension": "directionality",
                    "diagnosis_metric": "development mean_rank_ic; development mean_q5_q1",
                    "changed_parameter": "signal_direction",
                    "old_value": 1,
                    "new_value": direction,
                    "changed_parameter_count": 0 if trial_role == "baseline" else 1,
                    "sample_role": sample_role,
                    "sample_start": values["sample_start"],
                    "sample_end": values["sample_end"],
                    "used_for_selection": trial_role == "baseline" and sample_role == "development",
                    "metric": metric,
                    "expected_direction": "higher",
                    "value": value,
                    "baseline_value": "" if trial_role == "baseline" else baseline_value,
                    "delta_vs_baseline": "" if trial_role == "baseline" else value - baseline_value,
                    "period_count": values["period_count"],
                    "failure_stage": "",
                    "error_type": "",
                    "error_message": "",
                }
            )
    return rows


def comparison_label(delta: float, tolerance: float = 1e-12) -> str:
    if delta > tolerance:
        return "improved"
    if delta < -tolerance:
        return "worsened"
    return "unchanged"


def render_report(
    run_id: str,
    input_hash: str,
    selection_reason: str,
    summaries: dict[tuple[str, str], dict[str, object]],
) -> str:
    lines = [
        "# MOM60 Auditable Single-Round Iteration v1.8",
        "",
        "## Outcome",
        "",
        "- status: `completed`",
        f"- run_id: `{run_id}`",
        "- weakest_dimension: `directionality`",
        "- only change: `signal_direction +1 -> -1`",
        f"- selection reason: {selection_reason}",
        "- final_test_used_for_selection: `false`",
        "- interpretation: a 60-day reversal diagnostic, not validation of the "
        "original momentum hypothesis or a trading strategy.",
        "",
        "## Audit contract",
        "",
        f"- source panel: `{INPUT_PANEL.as_posix()}`",
        f"- source SHA-256: `{input_hash}`",
        f"- development: rebalance date before `{SPLIT_DATE.date()}`; used to identify "
        "the weakness and lock the change.",
        f"- final test: rebalance date on/after `{SPLIT_DATE.date()}`; evaluated only "
        "after the direction was locked.",
        "- unchanged: 60-day lookback, 20-day forward label, official main periods, "
        "universe, eligibility, five quantiles, missing-label rules and equal-weight returns.",
        "",
        "## Baseline vs candidate",
        "",
        "| sample | metric | baseline MOM60 | candidate -MOM60 | delta | assessment |",
        "|---|---|---:|---:|---:|---|",
    ]
    for sample_role in ("development", "final_test"):
        baseline = summaries[("baseline", sample_role)]
        candidate = summaries[("candidate", sample_role)]
        for metric in METRICS:
            before = float(baseline[metric])
            after = float(candidate[metric])
            delta = after - before
            lines.append(
                f"| {sample_role} | {metric} | {before:.6f} | {after:.6f} | "
                f"{delta:+.6f} | {comparison_label(delta)} |"
            )
    lines.extend(
        [
            "",
            "## What changed and why",
            "",
            "The development sample showed negative mean Rank IC and negative mean Q5-Q1 "
            "for MOM60. The iteration changed only the score direction. No lookback, "
            "threshold, sample, period, cost or portfolio rule was searched.",
            "",
            "## Failure record",
            "",
            "This run recorded no invalid period or fatal error. Any future invalid "
            "cross-section, label-coverage failure or exception is appended to "
            "`factor_experiment_log_v1_8.csv` as `row_type=failure`; it is not skipped.",
            "",
            "## Unresolved risks",
            "",
            "- The current-universe history retains survivorship-like bias.",
            "- The final-test outcomes already existed in earlier reports, so this is a "
            "procedural holdout rather than pristine prospective evidence.",
            "- Direction reversal changes the economic interpretation from momentum to "
            "reversal; it does not rescue the original MOM60 hypothesis.",
            "- This factor diagnostic does not model turnover, transaction costs, "
            "tradability or execution.",
            "- Generic-pipeline risks found in the read-only audit remain unresolved: "
            "overlapping walk-forward boundaries, prior full-sample IC weights, untrimmed "
            "caches and same-close execution assumptions.",
            "- No MCTS, UCT, LLM formula generation or FSA was implemented.",
            "",
        ]
    )
    return "\n".join(lines)


def append_log(path: Path, rows: list[dict[str, object]]) -> None:
    frame = pd.DataFrame(rows).reindex(columns=LOG_COLUMNS)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing_columns = list(pd.read_csv(path, nrows=0).columns)
        if existing_columns != list(LOG_COLUMNS):
            raise ValueError("existing experiment log schema does not match v1.8")
    frame.to_csv(path, mode="a", header=not path.exists(), index=False, encoding="utf-8-sig")


def run(root: Path, started_at: str, run_id: str) -> None:
    panel, panel_path, input_hash = load_panel(root)
    development = panel.loc[panel["rebalance_date"] < SPLIT_DATE]
    final_test = panel.loc[panel["rebalance_date"] >= SPLIT_DATE]

    # Selection is structurally development-only; final-test metrics do not exist yet.
    baseline_development = summarize(evaluate_periods(development, direction=1))
    candidate_direction, selection_reason = choose_direction(baseline_development)

    summaries = {
        ("baseline", "development"): baseline_development,
        ("candidate", "development"): summarize(
            evaluate_periods(development, direction=candidate_direction)
        ),
        ("baseline", "final_test"): summarize(evaluate_periods(final_test, direction=1)),
        ("candidate", "final_test"): summarize(
            evaluate_periods(final_test, direction=candidate_direction)
        ),
    }
    ended_at = datetime.now(UTC).isoformat()
    report_path = root / REPORT_PATH
    report_path.write_text(
        render_report(run_id, input_hash, selection_reason, summaries), encoding="utf-8"
    )
    metadata = {
        "iteration_id": ITERATION_ID,
        "run_id": run_id,
        "parent_run_id": PARENT_RUN_ID,
        "started_at_utc": started_at,
        "ended_at_utc": ended_at,
        "command": COMMAND,
        "script_sha256": sha256(Path(__file__)),
        "input_path": str(panel_path.relative_to(root)).replace("\\", "/"),
        "input_sha256": input_hash,
        "artifact_path": REPORT_PATH.as_posix(),
        "artifact_sha256": sha256(report_path),
    }
    append_log(root / LOG_PATH, audit_rows(metadata, summaries))


def failure_row(root: Path, started_at: str, run_id: str, error: Exception) -> dict[str, object]:
    panel_path = root / INPUT_PANEL
    row = {column: "" for column in LOG_COLUMNS}
    row.update(
        {
            "iteration_id": ITERATION_ID,
            "run_id": run_id,
            "parent_run_id": PARENT_RUN_ID,
            "row_type": "failure",
            "trial_role": "run",
            "status": "failed",
            "factor_name": "MOM60",
            "started_at_utc": started_at,
            "ended_at_utc": datetime.now(UTC).isoformat(),
            "command": COMMAND,
            "script_sha256": sha256(Path(__file__)),
            "input_path": INPUT_PANEL.as_posix(),
            "input_sha256": sha256(panel_path) if panel_path.is_file() else "",
            "failure_stage": "factor_iteration",
            "error_type": type(error).__name__,
            "error_message": str(error),
        }
    )
    return row


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=ROOT)
    args = parser.parse_args()
    root = args.project_root.resolve()
    started_at = datetime.now(UTC).isoformat()
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    try:
        run(root, started_at, run_id)
    except Exception as error:
        try:
            append_log(root / LOG_PATH, [failure_row(root, started_at, run_id, error)])
        except Exception as log_error:
            print(f"MOM60 iteration failed: {error}; failure logging also failed: {log_error}")
            return 2
        print(f"MOM60 iteration failed and recorded: {error}")
        return 2
    print(f"MOM60 iteration completed: run_id={run_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
