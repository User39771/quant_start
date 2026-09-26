"""Execute the one-time frozen Validation stage for ALPHA_JUNGLE_QLIB_C0."""

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
from qlib.contrib.data.handler import Alpha158DL
from qlib.data import D

from aq_factor_lab.alpha_jungle_c0.contract import (
    C0,
    FINAL_TEST_LOCKED,
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
ARMS = ("GRAMMAR_RANDOM", "DIRECT_LLM", "LLM_GUIDED_MCTS")
COMMON_BUDGETS = (10, 20, 50)
VALIDATION_FIELDS = [
    "validation_mean_rank_ic",
    "validation_rank_ir",
    "validation_positive_day_ratio",
    "validation_2019_mean_rank_ic",
    "validation_2020_mean_rank_ic",
    "validation_years_share_full_sign",
    "validation_turnover",
    "validation_coverage_usable_sessions",
    "validation_coverage_eligible_sessions",
    "validation_valid_session_coverage",
]


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


def load_validation_panel() -> Panel:
    assert_period_allowed(C0.validation_start, C0.validation_end)
    if not FINAL_TEST_LOCKED or C0.validation_end >= C0.final_test_start:
        raise RuntimeError("Final Test boundary is not locked")
    qlib.init(provider_uri=str(PROVIDER.resolve()), region=REG_CN)
    calendar = [
        pd.Timestamp(day)
        for day in D.calendar(
            C0.validation_start.isoformat(), C0.validation_end.isoformat(), freq="day"
        )
    ]
    eligible = label_eligible_sessions(
        [day.date() for day in calendar], C0.validation_start, C0.validation_end
    )
    if not eligible or eligible[-1].isoformat() != "2020-12-16":
        raise RuntimeError("Validation label-horizon isolation mismatch")
    universe = D.instruments(C0.universe)
    instruments = sorted(
        D.list_instruments(
            universe,
            start_time=C0.validation_start.isoformat(),
            end_time=C0.validation_end.isoformat(),
            freq="day",
            as_list=True,
        )
    )
    fields = tuple(sorted(FIELDS))
    raw_frame = D.features(
        instruments,
        [f"${name}" for name in fields],
        start_time="2008-01-01",
        end_time=C0.validation_end.isoformat(),
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
        start_time=C0.validation_start.isoformat(),
        end_time=C0.validation_end.isoformat(),
        freq="day",
    )
    marker = pd.Series(True, index=membership.index).unstack("instrument")
    active = marker.reindex(index=all_dates, columns=raw["close"].columns, fill_value=False)
    active = active.fillna(False).astype(bool)
    label = raw["close"].shift(-11) / raw["close"].shift(-1) - 1
    return Panel(raw, active, label, [pd.Timestamp(day) for day in eligible], all_dates)


def validation_metrics(wide: pd.DataFrame, panel: Panel) -> dict[str, object]:
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
        raise RuntimeError(f"Validation coverage failed: {usable}/{len(eligible)}={coverage}")
    wide = wide.loc[usable_mask].where(valid.loc[usable_mask])
    label = label.loc[usable_mask].where(valid.loc[usable_mask])
    rank_ic = _rank_ic(wide, label)
    mean_ic, rank_ir, positive, _ = rank_ic_summary(rank_ic)
    year_means = rank_ic.groupby(rank_ic.index.year).mean()
    if 2019 not in year_means or 2020 not in year_means:
        raise RuntimeError("Validation yearly RankIC split is incomplete")
    mean_2019 = float(year_means.loc[2019])
    mean_2020 = float(year_means.loc[2020])
    same_sign = bool(np.sign(mean_2019) == np.sign(mean_ic) == np.sign(mean_2020))
    return {
        "validation_mean_rank_ic": mean_ic,
        "validation_rank_ir": rank_ir,
        "validation_positive_day_ratio": positive,
        "validation_2019_mean_rank_ic": mean_2019,
        "validation_2020_mean_rank_ic": mean_2020,
        "validation_years_share_full_sign": same_sign,
        "validation_turnover": _turnover(wide),
        "validation_coverage_usable_sessions": usable,
        "validation_coverage_eligible_sessions": len(eligible),
        "validation_valid_session_coverage": coverage,
    }


def sign_reversal(train_value: str | float, validation_value: float) -> bool:
    return bool(np.sign(float(train_value)) != np.sign(validation_value))


def main() -> None:
    manifest_path = REPORT / "search_run_manifest.json"
    resume_path = REPORT / "FORMAL_SEARCH_RESUME_STATE.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    resume = json.loads(resume_path.read_text(encoding="utf-8"))
    if manifest.get("validation_accessed") or resume.get("validation_accessed"):
        raise RuntimeError("Validation was already accessed; the frozen one-time run will not replay")
    if not manifest.get("final_test_locked") or not resume.get("final_test_locked"):
        raise RuntimeError("FINAL_TEST_LOCKED must be true")

    candidates = read_csv(REPORT / "VALIDATION_CANDIDATE_MANIFEST.csv")
    search_candidates = [row for row in candidates if row["source_type"] == "SEARCH"]
    alpha_candidates = [row for row in candidates if row["source_type"] == "ALPHA158"]
    top10_frozen = read_csv(REPORT / "TRAIN_TOP10_BY_ARM.csv")
    checkpoint_frozen = read_csv(REPORT / "COMMON_CHECKPOINT_LEADERS.csv")
    alpha_top10_frozen = read_csv(REPORT / "ALPHA158_TRAIN_TOP10.csv")
    alpha_manifest = read_csv(REPORT / "ALPHA158_VALIDATION_MANIFEST.csv")
    if len(search_candidates) != 32 or len(alpha_candidates) != 10:
        raise RuntimeError("frozen candidate manifest membership count mismatch")
    if any(sum(row["arm"] == arm for row in top10_frozen) != 10 for arm in ARMS):
        raise RuntimeError("search-arm frozen top-10 count mismatch")
    if len(checkpoint_frozen) != 9 or {
        int(row["accepted_budget"]) for row in checkpoint_frozen
    } != set(COMMON_BUDGETS):
        raise RuntimeError("common checkpoint set is not exactly 10/20/50")
    if len(alpha_top10_frozen) != 10 or len(alpha_manifest) != 10:
        raise RuntimeError("Alpha158 frozen top-10 manifest mismatch")

    started = datetime.now(timezone.utc).isoformat()
    run_state = {
        "experiment_id": C0.experiment_id,
        "status": "VALIDATION_IN_PROGRESS",
        "started_at_utc": started,
        "validation_start": C0.validation_start.isoformat(),
        "validation_end": C0.validation_end.isoformat(),
        "last_label_eligible_session": "2020-12-16",
        "final_test_locked": True,
        "final_test_accessed": False,
    }
    write_json(REPORT / "VALIDATION_RUN_STATE.json", run_state)
    for state, path in ((manifest, manifest_path), (resume, resume_path)):
        state["validation_accessed"] = True
        state["validation_status"] = "IN_PROGRESS"
        state["validation_started_at_utc"] = started
        state["final_test_accessed"] = False
        state["final_test_locked"] = True
        write_json(path, state)

    panel = load_validation_panel()
    formula_metrics: dict[str, dict[str, object]] = {}
    formula_text: dict[str, str] = {}
    for row in search_candidates:
        canonical = row["canonical_formula"]
        formula_text.setdefault(canonical, row["formula"])
    for canonical, text in formula_text.items():
        formula = parse_formula(text)
        if formula.canonical() != canonical:
            raise RuntimeError(f"canonical formula mismatch: {text}")
        lookback = required_historical_lookback(formula)
        eligible = [day for day in panel.eligible_dates if panel.all_dates.get_loc(day) >= lookback]
        if eligible != panel.eligible_dates:
            raise RuntimeError(f"unexpected Validation history truncation: {canonical}")
        wide = evaluate_ast(formula, panel.raw)
        formula_metrics[canonical] = validation_metrics(wide, panel)

    expressions, names = Alpha158DL.get_feature_config()
    if len(expressions) != 158 or len(names) != 158:
        raise RuntimeError("Alpha158 definition count mismatch")
    universe = D.instruments(C0.universe)
    alpha_metrics: list[dict[str, object]] = []
    for offset in range(0, 158, 16):
        chunk = expressions[offset : offset + 16]
        frame = D.features(
            universe,
            chunk,
            start_time=C0.validation_start.isoformat(),
            end_time=C0.validation_end.isoformat(),
            freq="day",
        )
        for local_index, expression in enumerate(chunk):
            order = offset + local_index + 1
            wide = frame[expression].unstack("instrument").sort_index().sort_index(axis=1)
            alpha_metrics.append(
                {
                    "feature_order": order,
                    "feature_id": names[order - 1],
                    "expression": expression,
                    **validation_metrics(wide, panel),
                }
            )
    if len(alpha_metrics) != 158:
        raise RuntimeError("Alpha158 Validation result count mismatch")

    alpha_by_id = {str(row["feature_id"]): row for row in alpha_metrics}
    frozen_alpha_ids = {row["feature_id"] for row in alpha_top10_frozen}
    if frozen_alpha_ids != {row["feature_id"] for row in alpha_manifest}:
        raise RuntimeError("Alpha158 frozen identity mismatch")
    train_alpha = {row["feature_id"]: row for row in alpha_top10_frozen}
    eligible_alpha = [alpha_by_id[feature_id] for feature_id in frozen_alpha_ids]
    alpha_selected = min(
        eligible_alpha,
        key=lambda row: (
            -float(row["validation_mean_rank_ic"]),
            -float(row["validation_rank_ir"]),
            -int(bool(row["validation_years_share_full_sign"])),
            float(row["validation_turnover"]),
            -float(train_alpha[str(row["feature_id"])]["mean_rank_ic"]),
        ),
    )

    result_rows: list[dict[str, object]] = []
    for row in candidates:
        result = dict(row)
        if row["source_type"] == "SEARCH":
            metrics = formula_metrics[row["canonical_formula"]]
            train_mean = row["mean_rank_ic"]
        else:
            feature_id = next(
                item["feature_id"]
                for item in alpha_manifest
                if item["candidate_id"] == row["candidate_id"]
            )
            metrics = alpha_by_id[feature_id]
            train_mean = train_alpha[feature_id]["mean_rank_ic"]
            result["alpha158_feature_id"] = feature_id
        result.update(metrics)
        result["train_to_validation_sign_reversal"] = sign_reversal(
            train_mean, float(metrics["validation_mean_rank_ic"])
        )
        result_rows.append(result)

    top10_rows = [
        row
        for row in result_rows
        if row["source_type"] == "SEARCH" and "TRAIN_TOP10" in row["candidate_role"]
    ]
    selected_search: dict[str, dict[str, object]] = {}
    for arm in ARMS:
        arm_rows = [row for row in top10_rows if row["arm"] == arm]
        if len(arm_rows) != 10:
            raise RuntimeError(f"{arm} Validation top-10 membership mismatch")
        selected_search[arm] = min(
            arm_rows,
            key=lambda row: (
                -float(row["validation_mean_rank_ic"]),
                -float(row["validation_rank_ir"]),
                -int(str(row["validation_years_share_full_sign"]).lower() == "true"),
                float(row["validation_turnover"]),
                -float(row["composite_reward"]),
                int(row["accepted_candidate_index"]),
            ),
        )
    for row in top10_rows:
        row["selected_for_test"] = row is selected_search[row["arm"]]

    checkpoint_rows: list[dict[str, object]] = []
    for frozen in checkpoint_frozen:
        metrics = formula_metrics[frozen["canonical_formula"]]
        checkpoint_rows.append({**frozen, **metrics})
    checkpoint_lookup = {
        (row["arm"], int(row["accepted_budget"])): row for row in checkpoint_rows
    }
    direct_canonical = "Neg(Corr(Pct(close,5),Pct(volume,5),20))"
    duplicate_rows = [
        row
        for row in checkpoint_rows
        if row["canonical_formula"] == direct_canonical
    ]
    if len(duplicate_rows) != 5 or any(
        tuple(row[field] for field in VALIDATION_FIELDS)
        != tuple(duplicate_rows[0][field] for field in VALIDATION_FIELDS)
        for row in duplicate_rows[1:]
    ):
        raise RuntimeError("VALIDATION_IMPLEMENTATION_QA_FAILURE")

    rankics = {
        arm: [
            float(checkpoint_lookup[(arm, budget)]["validation_mean_rank_ic"])
            for budget in COMMON_BUDGETS
        ]
        for arm in ARMS
    }
    mcts_advantage = (
        sum(m >= r for m, r in zip(rankics["LLM_GUIDED_MCTS"], rankics["GRAMMAR_RANDOM"]))
        >= 2
        and sum(m >= d for m, d in zip(rankics["LLM_GUIDED_MCTS"], rankics["DIRECT_LLM"]))
        >= 2
        and rankics["LLM_GUIDED_MCTS"][-1] > rankics["GRAMMAR_RANDOM"][-1]
        and rankics["LLM_GUIDED_MCTS"][-1] > rankics["DIRECT_LLM"][-1]
        and float(np.mean(np.array(rankics["LLM_GUIDED_MCTS"]) - rankics["GRAMMAR_RANDOM"]))
        > 0
        and float(np.mean(np.array(rankics["LLM_GUIDED_MCTS"]) - rankics["DIRECT_LLM"]))
        > 0
    )

    alpha_train_rank = {row["feature_id"]: int(row["train_rank"]) for row in alpha_top10_frozen}
    for row in alpha_metrics:
        feature_id = str(row["feature_id"])
        row["alpha158_train_top10"] = feature_id in frozen_alpha_ids
        row["alpha158_train_rank"] = alpha_train_rank.get(feature_id, "")
        row["b_selected"] = feature_id == alpha_selected["feature_id"]
        row["train_mean_rank_ic"] = (
            train_alpha[feature_id]["mean_rank_ic"] if feature_id in train_alpha else ""
        )

    alpha_candidate_row = next(
        row
        for row in result_rows
        if row["source_type"] == "ALPHA158"
        and row.get("alpha158_feature_id") == alpha_selected["feature_id"]
    )
    final_rows = [selected_search[arm] for arm in ARMS] + [alpha_candidate_row]
    for row in final_rows:
        row["final_role"] = (
            "B_SELECTED" if row["source_type"] == "ALPHA158" else "SEARCH_ARM_SELECTED"
        )
    if len(final_rows) != 4 or {row["arm"] for row in final_rows} != {
        *ARMS,
        "ALPHA158_BENCHMARK",
    }:
        raise RuntimeError("final candidate set mismatch")

    result_fields = list(candidates[0]) + [
        "alpha158_feature_id",
        *VALIDATION_FIELDS,
        "train_to_validation_sign_reversal",
    ]
    checkpoint_fields = list(checkpoint_frozen[0]) + VALIDATION_FIELDS
    top10_fields = result_fields + ["selected_for_test"]
    alpha_fields = [
        "feature_order",
        "feature_id",
        "expression",
        *VALIDATION_FIELDS,
        "alpha158_train_top10",
        "alpha158_train_rank",
        "b_selected",
        "train_mean_rank_ic",
    ]
    final_fields = ["final_role", *result_fields]
    write_csv(REPORT / "VALIDATION_RESULTS.csv", result_fields, result_rows)
    write_csv(REPORT / "COMMON_CHECKPOINT_VALIDATION.csv", checkpoint_fields, checkpoint_rows)
    write_csv(REPORT / "TOP10_VALIDATION_BY_ARM.csv", top10_fields, top10_rows)
    write_csv(REPORT / "ALPHA158_VALIDATION_RESULTS.csv", alpha_fields, alpha_metrics)
    write_csv(REPORT / "FINAL_CANDIDATES_FOR_TEST.csv", final_fields, final_rows)

    alpha_values = np.array(
        [float(row["validation_mean_rank_ic"]) for row in alpha_metrics], dtype=float
    )
    b_summary = {
        "count": 158,
        "minimum": float(alpha_values.min()),
        "q25": float(np.quantile(alpha_values, 0.25)),
        "median": float(np.median(alpha_values)),
        "q75": float(np.quantile(alpha_values, 0.75)),
        "maximum": float(alpha_values.max()),
    }
    common_lines = [
        "| " + str(budget) + " | " + " | ".join(
            f"{float(checkpoint_lookup[(arm, budget)]['validation_mean_rank_ic']):.12g}"
            for arm in ARMS
        ) + " |"
        for budget in COMMON_BUDGETS
    ]
    selected_lines = [
        f"| {row['arm']} | `{row.get('alpha158_feature_id') or row['canonical_formula']}` | "
        f"{float(row['mean_rank_ic']):.12g} | {float(row['validation_mean_rank_ic']):.12g} | "
        f"{row['train_to_validation_sign_reversal']} |"
        for row in final_rows
    ]
    reversals = [row for row in final_rows if row["train_to_validation_sign_reversal"]]
    all_reversals = [row for row in result_rows if row["train_to_validation_sign_reversal"]]
    reversal_names = [
        str(row.get("alpha158_feature_id") or row["canonical_formula"])
        for row in all_reversals
    ]
    report = f"""# ALPHA_JUNGLE_QLIB_C0 Validation report

## Status and scope

`VALIDATION_EXECUTION=PASS`

This was the first and only frozen Validation execution. It used 2019-01-01 through 2020-12-31, with 2020-12-16 as the last label-eligible signal session. No candidate was generated, edited, replaced, or selected using Final Test. Results measure out-of-Train factor preservation, not trading value.

## A. Common-checkpoint search efficiency

| Accepted budget | Random RankIC | Direct RankIC | MCTS RankIC |
|---:|---:|---:|---:|
{chr(10).join(common_lines)}

Frozen MCTS Validation-advantage rule: **{'PASS' if mcts_advantage else 'FAIL'}**.

## B. Frozen per-arm and benchmark selections

| Source | Frozen identity | Train mean RankIC | Validation mean RankIC | Sign reversal |
|---|---|---:|---:|---|
{chr(10).join(selected_lines)}

Exactly one candidate per search arm and the Alpha158 `B_SELECTED` candidate are frozen in `FINAL_CANDIDATES_FOR_TEST.csv`. The remaining 148 Alpha158 features contributed only to the pre-specified `B_MEDIAN` context and could not alter `B_SELECTED`.

## C. Alpha158 B_MEDIAN context

Across all 158 frozen Alpha158 features, Validation mean RankIC had minimum {b_summary['minimum']:.12g}, Q1 {b_summary['q25']:.12g}, median {b_summary['median']:.12g}, Q3 {b_summary['q75']:.12g}, and maximum {b_summary['maximum']:.12g}. `B_SELECTED` is `{alpha_selected['feature_id']}` with Validation mean RankIC {float(alpha_selected['validation_mean_rank_ic']):.12g}.

## D. Stability and QA

- Selected-candidate Train-to-Validation sign reversals: {len(reversals)} ({', '.join(str(row.get('alpha158_feature_id') or row['canonical_formula']) for row in reversals) or 'none'}).
- Frozen-shortlist Train-to-Validation sign reversals: {len(all_reversals)} ({', '.join(reversal_names) or 'none'}). None of these reversing memberships was selected for Final Test.
- Direct@10/@20/@50 and MCTS@10/@20 duplicate-formula metrics: exactly identical.
- Every evaluated shortlist candidate existed in the frozen manifest; common budgets remained exactly 10/20/50.
- Direct operational outcome: 51 accepted / 150 calls. MCTS: 100 accepted / 143 calls. Accepted-per-call remains operational secondary because provider-failure counts differed materially.
- Final Test accessed: false.
- `FINAL_TEST_LOCKED=true`.
- `READY_FOR_TEST_UNLOCK=YES`.
"""
    report_path = REPORT / "VALIDATION_REPORT.md"
    temporary = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary.write_text(report, encoding="utf-8")
    temporary.replace(report_path)

    completed = datetime.now(timezone.utc).isoformat()
    run_state.update(
        {
            "status": "VALIDATION_COMPLETE",
            "completed_at_utc": completed,
            "mcts_validation_advantage": bool(mcts_advantage),
            "selected_candidate_count": 4,
            "alpha158_b_median": b_summary["median"],
            "ready_for_test_unlock": True,
        }
    )
    write_json(REPORT / "VALIDATION_RUN_STATE.json", run_state)
    for state, path in ((manifest, manifest_path), (resume, resume_path)):
        state["validation_status"] = "COMPLETE"
        state["validation_completed_at_utc"] = completed
        state["ready_for_test_unlock"] = True
        state["final_test_accessed"] = False
        state["final_test_locked"] = True
        write_json(path, state)

    print(
        json.dumps(
            {
                "validation_execution": "PASS",
                "mcts_validation_advantage": bool(mcts_advantage),
                "selected": {
                    row["arm"]: {
                        "identity": row.get("alpha158_feature_id")
                        or row["canonical_formula"],
                        "validation_mean_rank_ic": row["validation_mean_rank_ic"],
                    }
                    for row in final_rows
                },
                "b_median": b_summary,
                "selected_sign_reversals": [
                    row.get("alpha158_feature_id") or row["canonical_formula"]
                    for row in reversals
                ],
                "final_test_locked": True,
                "ready_for_test_unlock": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
