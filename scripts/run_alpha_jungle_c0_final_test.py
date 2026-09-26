"""Consume the one-time frozen Final Test for ALPHA_JUNGLE_QLIB_C0."""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

os.environ.setdefault("SETUPTOOLS_SCM_PRETEND_VERSION", "0.9.7")

import numpy as np
import pandas as pd
import qlib
from qlib.config import REG_CN
from qlib.data import D

from aq_factor_lab.alpha_jungle_c0.contract import (
    C0,
    assert_period_allowed,
    label_eligible_sessions,
)
from aq_factor_lab.alpha_jungle_c0.evaluation import (
    daily_coverage_required,
    formula_session_coverage,
    rank_ic_summary,
)
from aq_factor_lab.alpha_jungle_c0.formula import (
    FIELDS,
    parse_formula,
    required_historical_lookback,
)
from run_alpha_jungle_c0_train_search import Panel, _rank_ic, _turnover, evaluate_ast


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "alpha_jungle_c0"
PROVIDER = Path(r"D:\qlib_data\cn_data")
ARMS = ("GRAMMAR_RANDOM", "DIRECT_LLM", "LLM_GUIDED_MCTS", "ALPHA158_BENCHMARK")
EXPECTED = {
    "GRAMMAR_RANDOM": "Add(Vari(Neg(Less(volume,volume)),30),Vari(Sub(Med(close,30),Std(close,20)),3))",
    "DIRECT_LLM": "Neg(Corr(Pct(close,5),Pct(volume,5),20))",
    "LLM_GUIDED_MCTS": "Neg(Ma(Corr(Pct(close,5),Pct(volume,5),20),5))",
}
YEARS = (2021, 2022, 2023, 2024)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def write_json(path: Path, value: dict[str, object]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)


def load_test_panel() -> Panel:
    # The only controlled unlock: no search code receives this override.
    assert_period_allowed(C0.final_test_start, C0.final_test_end, final_test_locked=False)
    qlib.init(provider_uri=str(PROVIDER.resolve()), region=REG_CN)
    calendar = [
        pd.Timestamp(day)
        for day in D.calendar(
            C0.final_test_start.isoformat(), C0.final_test_end.isoformat(), freq="day"
        )
    ]
    eligible = label_eligible_sessions(
        [day.date() for day in calendar], C0.final_test_start, C0.final_test_end
    )
    if not eligible or eligible[-1].isoformat() != "2024-11-14":
        raise RuntimeError("Final-Test label-horizon isolation mismatch")
    universe = D.instruments(C0.universe)
    instruments = sorted(
        D.list_instruments(
            universe,
            start_time=C0.final_test_start.isoformat(),
            end_time=C0.final_test_end.isoformat(),
            freq="day",
            as_list=True,
        )
    )
    fields = tuple(sorted(FIELDS))
    raw_frame = D.features(
        instruments,
        [f"${name}" for name in fields],
        start_time="2008-01-01",
        end_time=C0.final_test_end.isoformat(),
        freq="day",
    ).rename(columns={f"${name}": name for name in fields})
    raw = {
        name: raw_frame[name].unstack("instrument").sort_index().sort_index(axis=1)
        for name in fields
    }
    all_dates = raw["close"].index
    membership = D.features(
        universe,
        ["$factor"],
        start_time=C0.final_test_start.isoformat(),
        end_time=C0.final_test_end.isoformat(),
        freq="day",
    )
    marker = pd.Series(True, index=membership.index).unstack("instrument")
    active = marker.reindex(index=all_dates, columns=raw["close"].columns, fill_value=False)
    active = active.fillna(False).astype(bool)
    label = raw["close"].shift(-11) / raw["close"].shift(-1) - 1
    return Panel(raw, active, label, [pd.Timestamp(day) for day in eligible], all_dates)


def test_metrics(wide: pd.DataFrame, panel: Panel) -> dict[str, object]:
    eligible = panel.eligible_dates
    wide = wide.reindex(index=eligible, columns=panel.active.columns)
    active = panel.active.reindex(index=eligible, columns=wide.columns, fill_value=False)
    label = panel.label.reindex(index=eligible, columns=wide.columns)
    valid = active & np.isfinite(wide) & np.isfinite(label)
    usable_mask = pd.Series(
        [
            int(valid_n) >= daily_coverage_required(int(active_n))
            for active_n, valid_n in zip(active.sum(axis=1), valid.sum(axis=1), strict=True)
        ],
        index=wide.index,
    )
    usable = int(usable_mask.sum())
    coverage, passes = formula_session_coverage(usable, len(eligible))
    if not passes:
        raise RuntimeError(f"Final-Test coverage failed: {usable}/{len(eligible)}={coverage}")
    wide = wide.loc[usable_mask].where(valid.loc[usable_mask])
    label = label.loc[usable_mask].where(valid.loc[usable_mask])
    rank_ic = _rank_ic(wide, label)
    mean_ic, rank_ir, positive, _ = rank_ic_summary(rank_ic)
    year_means = rank_ic.groupby(rank_ic.index.year).mean()
    if set(year_means.index) != set(YEARS):
        raise RuntimeError("Final-Test yearly RankIC split is incomplete")
    yearly = {year: float(year_means.loc[year]) for year in YEARS}
    sign_count = sum(np.sign(value) == np.sign(mean_ic) for value in yearly.values())
    return {
        "test_mean_rank_ic": mean_ic,
        "test_rank_ir": rank_ir,
        "test_positive_day_ratio": positive,
        **{f"test_{year}_mean_rank_ic": value for year, value in yearly.items()},
        "test_years_sharing_full_sign": sign_count,
        "test_turnover": _turnover(wide),
        "test_coverage_usable_sessions": usable,
        "test_coverage_eligible_sessions": len(eligible),
        "test_valid_session_coverage": coverage,
    }


def same_sign(left: float, right: float) -> bool:
    return bool(np.sign(left) == np.sign(right))


def main() -> None:
    candidate_path = REPORT / "FINAL_CANDIDATES_FOR_TEST.csv"
    candidates = read_csv(candidate_path)
    if len(candidates) != 4 or {row["arm"] for row in candidates} != set(ARMS):
        raise RuntimeError("Final Test requires exactly one frozen candidate from each source")
    by_arm = {row["arm"]: row for row in candidates}
    for arm, canonical in EXPECTED.items():
        if by_arm[arm]["canonical_formula"] != canonical:
            raise RuntimeError(f"frozen identity mismatch for {arm}")
    if (
        by_arm["ALPHA158_BENCHMARK"]["alpha158_feature_id"] != "ROC20"
        or by_arm["ALPHA158_BENCHMARK"]["canonical_formula"].replace(" ", "")
        != "Ref($close,20)/$close"
    ):
        raise RuntimeError("frozen Alpha158 identity mismatch")

    manifest_path = REPORT / "search_run_manifest.json"
    resume_path = REPORT / "FORMAL_SEARCH_RESUME_STATE.json"
    validation_state = json.loads((REPORT / "VALIDATION_RUN_STATE.json").read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    resume = json.loads(resume_path.read_text(encoding="utf-8"))
    if validation_state.get("status") != "VALIDATION_COMPLETE":
        raise RuntimeError("Validation is not complete")
    if not validation_state.get("ready_for_test_unlock"):
        raise RuntimeError("READY_FOR_TEST_UNLOCK is false")
    if manifest.get("final_test_accessed") or resume.get("final_test_accessed"):
        raise RuntimeError("Final Test was already accessed; replay is forbidden")
    if not manifest.get("final_test_locked") or not resume.get("final_test_locked"):
        raise RuntimeError("Final Test must be locked before controlled unlock")

    unlock_text = """# ALPHA_JUNGLE_QLIB_C0 one-time Final Test unlock

```text
unlock_type = ONE_TIME_FINAL_TEST
candidate_count = 4
candidate_selection_complete = true
validation_complete = true
final_test_previously_accessed = false
formula_generation_allowed = false
candidate_reselection_allowed = false
```

The frozen MCTS Validation-advantage rule already **FAILED**. Therefore `MCTS_SEARCH_ADVANTAGE_OBSERVED` is no longer an attainable final classification. Final Test may assess candidate preservation only and cannot retroactively redefine the Validation result.
"""
    unlock_path = REPORT / "FINAL_TEST_UNLOCK_V1.md"
    temporary = unlock_path.with_suffix(unlock_path.suffix + ".tmp")
    temporary.write_text(unlock_text, encoding="utf-8")
    temporary.replace(unlock_path)

    started = datetime.now(timezone.utc).isoformat()
    run_state = {
        "experiment_id": C0.experiment_id,
        "status": "FINAL_TEST_IN_PROGRESS",
        "started_at_utc": started,
        "unlock_type": "ONE_TIME_FINAL_TEST",
        "candidate_count": 4,
        "controlled_evaluator_final_test_locked": False,
        "global_final_test_locked": True,
        "final_test_accessed": True,
        "final_test_consumed": False,
        "test_start": C0.final_test_start.isoformat(),
        "test_end": C0.final_test_end.isoformat(),
        "last_label_eligible_session": "2024-11-14",
    }
    write_json(REPORT / "FINAL_TEST_RUN_STATE.json", run_state)
    for state, path in ((manifest, manifest_path), (resume, resume_path)):
        state["final_test_accessed"] = True
        state["final_test_consumed"] = False
        state["final_test_status"] = "IN_PROGRESS"
        state["final_test_started_at_utc"] = started
        state["controlled_final_test_evaluator_unlocked"] = True
        state["final_test_locked"] = True
        write_json(path, state)

    panel = load_test_panel()
    results: list[dict[str, object]] = []
    for arm in ARMS[:3]:
        frozen = by_arm[arm]
        formula = parse_formula(frozen["formula"])
        if formula.canonical() != frozen["canonical_formula"]:
            raise RuntimeError(f"canonical identity changed for {arm}")
        lookback = required_historical_lookback(formula)
        if any(panel.all_dates.get_loc(day) < lookback for day in panel.eligible_dates):
            raise RuntimeError(f"unexpected Test history truncation for {arm}")
        metrics = test_metrics(evaluate_ast(formula, panel.raw), panel)
        results.append({**frozen, **metrics})

    alpha = by_arm["ALPHA158_BENCHMARK"]
    expression = alpha["formula"]
    alpha_frame = D.features(
        D.instruments(C0.universe),
        [expression],
        start_time=C0.final_test_start.isoformat(),
        end_time=C0.final_test_end.isoformat(),
        freq="day",
    )
    alpha_wide = alpha_frame[expression].unstack("instrument").sort_index().sort_index(axis=1)
    results.append({**alpha, **test_metrics(alpha_wide, panel)})

    if len(results) != 4 or len({row["candidate_id"] for row in results}) != 4:
        raise RuntimeError("Final-Test evaluation count mismatch")
    coverage_pairs = {
        (row["test_coverage_usable_sessions"], row["test_coverage_eligible_sessions"])
        for row in results
    }
    if len(coverage_pairs) != 1:
        raise RuntimeError("frozen candidates did not use the same Test sessions")

    for row in results:
        train = float(row["mean_rank_ic"])
        validation = float(row["validation_mean_rank_ic"])
        test = float(row["test_mean_rank_ic"])
        row["train_to_validation_sign_preserved"] = same_sign(train, validation)
        row["validation_to_test_sign_preserved"] = same_sign(validation, test)
        row["train_to_test_sign_preserved"] = same_sign(train, test)
        row["test_to_validation_rankic_ratio"] = test / validation

    by_result_arm = {str(row["arm"]): row for row in results}
    mcts = by_result_arm["LLM_GUIDED_MCTS"]
    mcts_preserved = bool(mcts["validation_to_test_sign_preserved"])
    mcts_positive = float(mcts["test_mean_rank_ic"]) > 0
    baseline_test_values = [
        float(by_result_arm[arm]["test_mean_rank_ic"])
        for arm in ("GRAMMAR_RANDOM", "DIRECT_LLM")
    ]
    mcts_beats_at_least_one_baseline = float(mcts["test_mean_rank_ic"]) > min(
        baseline_test_values
    )
    classification = (
        "MIXED"
        if mcts_preserved and mcts_positive and mcts_beats_at_least_one_baseline
        else "NO_SEARCH_ADVANTAGE_OBSERVED"
    )
    if classification == "MCTS_SEARCH_ADVANTAGE_OBSERVED":
        raise AssertionError("forbidden final classification")

    result_fields = [
        "source_type",
        "arm",
        "candidate_id",
        "formula",
        "canonical_formula",
        "alpha158_feature_id",
        "mean_rank_ic",
        "validation_mean_rank_ic",
        "test_mean_rank_ic",
        "test_rank_ir",
        "test_positive_day_ratio",
        *[f"test_{year}_mean_rank_ic" for year in YEARS],
        "test_years_sharing_full_sign",
        "test_turnover",
        "test_coverage_usable_sessions",
        "test_coverage_eligible_sessions",
        "test_valid_session_coverage",
        "train_to_validation_sign_preserved",
        "validation_to_test_sign_preserved",
        "train_to_test_sign_preserved",
        "test_to_validation_rankic_ratio",
    ]
    write_csv(REPORT / "FINAL_TEST_RESULTS.csv", result_fields, results)

    identity_lines = [
        f"- {row['arm']}: `{row.get('alpha158_feature_id') or row['canonical_formula']}`"
        for row in results
    ]
    metric_lines = [
        f"| {row['arm']} | {float(row['test_mean_rank_ic']):.12g} | "
        f"{float(row['test_rank_ir']):.12g} | {float(row['test_positive_day_ratio']):.12g} | "
        f"{float(row['test_turnover']):.12g} | {float(row['test_valid_session_coverage']):.12g} |"
        for row in results
    ]
    preservation_lines = [
        f"| {row['arm']} | {float(row['mean_rank_ic']):.12g} | "
        f"{float(row['validation_mean_rank_ic']):.12g} | {float(row['test_mean_rank_ic']):.12g} | "
        f"{row['train_to_validation_sign_preserved']} | {row['validation_to_test_sign_preserved']} | "
        f"{row['train_to_test_sign_preserved']} | {float(row['test_to_validation_rankic_ratio']):.12g} |"
        for row in results
    ]
    yearly_lines = [
        f"| {row['arm']} | "
        + " | ".join(f"{float(row[f'test_{year}_mean_rank_ic']):.12g}" for year in YEARS)
        + f" | {row['test_years_sharing_full_sign']}/4 |"
        for row in results
    ]
    report = f"""# ALPHA_JUNGLE_QLIB_C0 one-time Final Test report

## 1. Frozen candidate identities

{chr(10).join(identity_lines)}

No candidate was generated, edited, replaced, or selected using Final Test.

## 2. Final-Test metrics

| Source | Mean RankIC | RankIR | Positive-day ratio | Turnover | Coverage |
|---|---:|---:|---:|---:|---:|
{chr(10).join(metric_lines)}

## 3. Train → Validation → Test preservation

| Source | Train RankIC | Validation RankIC | Test RankIC | T→V sign | V→T sign | T→T sign | Test/Validation |
|---|---:|---:|---:|---|---|---|---:|
{chr(10).join(preservation_lines)}

## 4. Year-by-year stability

| Source | 2021 | 2022 | 2023 | 2024 through 11-14 | Years sharing full sign |
|---|---:|---:|---:|---:|---:|
{chr(10).join(yearly_lines)}

## 5. Alpha158 benchmark comparison

Only frozen `B_SELECTED=ROC20` was evaluated on Final Test. The other 157 Alpha158 features were not read for Test outcomes. Validation `B_MEDIAN` remains contextual Validation evidence; no Test-period Alpha158 median or Test-selected benchmark was created.

## 6. Search-method conclusion

Final classification: **{classification}**.

The frozen MCTS Validation-advantage rule had already failed before Test and remains failed. Final Test assesses only preservation of the selected candidate; it cannot reopen or convert the failed Validation criterion. Search-process evidence, checkpoint Validation evidence, and selected-candidate Test preservation remain separate.

## 7. Limitations

This is a historical benchmark experiment, not live out-of-sample evidence and not a trading-value claim. Accepted-per-call remains operational secondary because provider failures differed. No candidate was selected using Test, and no Test-based reselection, sign flip, parameter change, or formula variant is permitted.

`FINAL_TEST_ACCESSED=true`

`FINAL_TEST_CONSUMED=true`

`FINAL_TEST_LOCKED=true`
"""
    report_path = REPORT / "FINAL_TEST_REPORT.md"
    temporary = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary.write_text(report, encoding="utf-8")
    temporary.replace(report_path)

    verdict = f"""# ALPHA_JUNGLE_QLIB_C0 final verdict

`FINAL_C0_CLASSIFICATION={classification}`

`MCTS_SEARCH_ADVANTAGE_OBSERVED` is unattainable because the frozen Validation-advantage rule failed before Final Test. The classification combines that settled Validation conclusion with the preservation evidence of the already-selected MCTS candidate, without reopening selection or treating Test as search-efficiency evidence.

This historical benchmark is not live out-of-sample evidence and is not a trading-value claim. Final Test is consumed and re-locked.
"""
    verdict_path = REPORT / "FINAL_C0_VERDICT.md"
    temporary = verdict_path.with_suffix(verdict_path.suffix + ".tmp")
    temporary.write_text(verdict, encoding="utf-8")
    temporary.replace(verdict_path)

    completed = datetime.now(timezone.utc).isoformat()
    run_state.update(
        {
            "status": "FINAL_TEST_COMPLETE",
            "completed_at_utc": completed,
            "controlled_evaluator_final_test_locked": True,
            "global_final_test_locked": True,
            "final_test_consumed": True,
            "qa_passed": True,
            "classification": classification,
        }
    )
    write_json(REPORT / "FINAL_TEST_RUN_STATE.json", run_state)
    for state, path in ((manifest, manifest_path), (resume, resume_path)):
        state["final_test_accessed"] = True
        state["final_test_consumed"] = True
        state["final_test_status"] = "COMPLETE"
        state["final_test_completed_at_utc"] = completed
        state["controlled_final_test_evaluator_unlocked"] = False
        state["final_test_locked"] = True
        state["final_c0_classification"] = classification
        write_json(path, state)

    print(
        json.dumps(
            {
                "final_test_execution": "PASS",
                "classification": classification,
                "results": {
                    row["arm"]: {
                        "test_mean_rank_ic": row["test_mean_rank_ic"],
                        "yearly": {
                            str(year): row[f"test_{year}_mean_rank_ic"] for year in YEARS
                        },
                        "train_to_validation_sign_preserved": row[
                            "train_to_validation_sign_preserved"
                        ],
                        "validation_to_test_sign_preserved": row[
                            "validation_to_test_sign_preserved"
                        ],
                        "train_to_test_sign_preserved": row[
                            "train_to_test_sign_preserved"
                        ],
                    }
                    for row in results
                },
                "final_test_accessed": True,
                "final_test_consumed": True,
                "final_test_locked": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
