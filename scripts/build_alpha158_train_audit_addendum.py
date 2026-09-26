"""Materialize the authorized Train-only Alpha158 pre-Validation addendum."""

from __future__ import annotations

import csv
import hashlib
import json
import os
from pathlib import Path

os.environ.setdefault("SETUPTOOLS_SCM_PRETEND_VERSION", "0.9.7")

import numpy as np
import pandas as pd
from qlib.contrib.data.handler import Alpha158DL
from qlib.data import D

from aq_factor_lab.alpha_jungle_c0.contract import C0
from aq_factor_lab.alpha_jungle_c0.evaluation import (
    daily_coverage_required,
    formula_session_coverage,
    rank_ic_summary,
)
from run_alpha_jungle_c0_train_search import _rank_ic, _turnover, load_panel


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "alpha_jungle_c0"
PROVIDER = Path(r"D:\qlib_data\cn_data")
METRIC_FIELDS = [
    "feature_order",
    "feature_id",
    "expression",
    "mean_rank_ic",
    "rank_ir",
    "positive_day_ratio",
    "train_subperiod_direction_consistency",
    "turnover",
    "coverage_usable_sessions",
    "coverage_eligible_sessions",
    "valid_session_coverage",
]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_csv(path: Path, fields: list[str], rows: list[dict[str, object]]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def evaluate_feature(
    order: int,
    feature_id: str,
    expression: str,
    wide: pd.DataFrame,
    panel: object,
) -> dict[str, object]:
    eligible = panel.eligible_dates
    wide = wide.reindex(index=eligible, columns=panel.active.columns)
    active = panel.active.reindex(index=eligible, columns=wide.columns, fill_value=False)
    label = panel.label.reindex(index=eligible, columns=wide.columns)
    finite = np.isfinite(wide)
    valid = active & finite & np.isfinite(label)
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
        raise RuntimeError(
            f"Alpha158 {feature_id} fails frozen coverage: {usable}/{len(eligible)}={coverage}"
        )
    wide = wide.loc[usable_mask].where(valid.loc[usable_mask])
    label = label.loc[usable_mask].where(valid.loc[usable_mask])
    rank_ic = _rank_ic(wide, label)
    mean_ic, rank_ir, positive, direction = rank_ic_summary(rank_ic)
    return {
        "feature_order": order,
        "feature_id": feature_id,
        "expression": expression,
        "mean_rank_ic": mean_ic,
        "rank_ir": rank_ir,
        "positive_day_ratio": positive,
        "train_subperiod_direction_consistency": direction,
        "turnover": _turnover(wide),
        "coverage_usable_sessions": usable,
        "coverage_eligible_sessions": len(eligible),
        "valid_session_coverage": coverage,
    }


def main() -> None:
    manifest = json.loads((REPORT / "search_run_manifest.json").read_text(encoding="utf-8"))
    resume = json.loads((REPORT / "FORMAL_SEARCH_RESUME_STATE.json").read_text(encoding="utf-8"))
    assert manifest["validation_accessed"] is False
    assert manifest["final_test_accessed"] is False
    assert manifest["final_test_locked"] is True
    assert resume["validation_accessed"] is False
    assert resume["final_test_accessed"] is False
    assert resume["final_test_locked"] is True

    protected = [
        REPORT / "PRE_VALIDATION_AUDIT.md",
        REPORT / "best_train_candidates.csv",
        REPORT / "COMMON_CHECKPOINT_LEADERS.csv",
        REPORT / "TRAIN_TOP10_BY_ARM.csv",
    ]
    before = {path: digest(path) for path in protected}

    panel = load_panel(PROVIDER)
    expressions, names = Alpha158DL.get_feature_config()
    assert len(expressions) == len(names) == 158
    universe = D.instruments(C0.universe)
    metrics: list[dict[str, object]] = []
    chunk_size = 16
    for offset in range(0, 158, chunk_size):
        chunk_expressions = expressions[offset : offset + chunk_size]
        frame = D.features(
            universe,
            chunk_expressions,
            start_time=C0.train_start.isoformat(),
            end_time=C0.train_end.isoformat(),
            freq="day",
        )
        for local_index, expression in enumerate(chunk_expressions):
            order = offset + local_index + 1
            feature_id = names[order - 1]
            wide = frame[expression].unstack("instrument").sort_index().sort_index(axis=1)
            metrics.append(evaluate_feature(order, feature_id, expression, wide, panel))

    if len(metrics) != 158 or len({row["feature_id"] for row in metrics}) != 158:
        raise AssertionError("Alpha158 feature count or stable identifiers are inconsistent")
    ranking = sorted(
        metrics,
        key=lambda row: (
            -float(row["mean_rank_ic"]),
            -float(row["rank_ir"]),
            float(row["turnover"]),
            int(row["feature_order"]),
        ),
    )
    top10 = [{"train_rank": rank, **row} for rank, row in enumerate(ranking[:10], 1)]
    write_csv(REPORT / "ALPHA158_TRAIN_METRICS.csv", METRIC_FIELDS, metrics)
    write_csv(REPORT / "ALPHA158_TRAIN_TOP10.csv", ["train_rank", *METRIC_FIELDS], top10)

    alpha_manifest_fields = ["candidate_id", "source_type", "status", "train_rank", *METRIC_FIELDS]
    alpha_manifest = [
        {
            "candidate_id": f"ALPHA158-{int(row['train_rank']):03d}",
            "source_type": "ALPHA158",
            "status": "FROZEN_TRAIN_TOP10",
            **row,
        }
        for row in top10
    ]
    write_csv(REPORT / "ALPHA158_VALIDATION_MANIFEST.csv", alpha_manifest_fields, alpha_manifest)

    candidate_path = REPORT / "VALIDATION_CANDIDATE_MANIFEST.csv"
    with candidate_path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        candidate_fields = list(reader.fieldnames or [])
        existing = list(reader)
    if any(row["source_type"] == "ALPHA158" for row in existing):
        raise RuntimeError("VALIDATION_CANDIDATE_MANIFEST.csv already contains Alpha158 rows")
    with candidate_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=candidate_fields, extrasaction="ignore")
        for row in alpha_manifest:
            writer.writerow(
                {
                    "candidate_id": row["candidate_id"],
                    "source_type": "ALPHA158",
                    "arm": "ALPHA158_BENCHMARK",
                    "candidate_role": "ALPHA158_TRAIN_TOP10",
                    "formula": row["expression"],
                    "canonical_formula": row["expression"],
                    "mean_rank_ic": row["mean_rank_ic"],
                    "rank_ir": row["rank_ir"],
                    "positive_ratio": row["positive_day_ratio"],
                    "subperiod_direction_ratio": row[
                        "train_subperiod_direction_consistency"
                    ],
                    "turnover": row["turnover"],
                }
            )

    if before != {path: digest(path) for path in protected}:
        raise AssertionError("a protected historical or R/L/M artifact changed")
    with candidate_path.open(newline="", encoding="utf-8-sig") as handle:
        final_candidates = list(csv.DictReader(handle))
    search_rows = [row for row in final_candidates if row["source_type"] == "SEARCH"]
    alpha_rows = [row for row in final_candidates if row["source_type"] == "ALPHA158"]
    assert search_rows == existing
    assert len(alpha_rows) == 10
    assert all("validation" not in field.lower() for field in alpha_manifest_fields)

    top_lines = [
        f"| {row['train_rank']} | {row['feature_id']} | `{row['expression']}` | "
        f"{float(row['mean_rank_ic']):.12g} | {float(row['rank_ir']):.12g} | "
        f"{float(row['turnover']):.12g} |"
        for row in top10
    ]
    addendum = f"""# PRE_VALIDATION_AUDIT addendum: Alpha158 Train preparation

## Result

`PRE_VALIDATION_AUDIT_STATUS=PASS`

`READY_TO_RUN_VALIDATION=YES`

This addendum repairs only the earlier procedural blocker. The historical `PRE_VALIDATION_AUDIT.md` remains unchanged. Its R/L/M consistency findings, legacy `best_train_candidates.csv` defect, authoritative R/L/M replacement artifacts, common checkpoints, metric definitions, tie-breaking rules, and final selection rules remain in force.

## Authorized Train-only preparation

All 158 frozen Alpha158 features were evaluated only on `TRAIN_SEARCH` (2011-01-01 through 2018-12-31), using the frozen historical CSI300 membership, 10-day label construction, label-horizon endpoint isolation, daily coverage threshold, formula-session coverage threshold, four contiguous Train subperiods, and top-decile turnover calculation. No Validation outcomes or Final Test data were loaded.

Ranking is deterministic: higher Train mean RankIC, then higher Train RankIR, then lower turnover, then stable Alpha158 feature order.

## ALPHA158_TRAIN_TOP10

| Rank | Feature | Frozen expression | Train mean RankIC | Train RankIR | Turnover |
|---:|---|---|---:|---:|---:|
{chr(10).join(top_lines)}

The exact identities and Train metrics are frozen in `ALPHA158_TRAIN_TOP10.csv`; `ALPHA158_VALIDATION_MANIFEST.csv` contains these ten identities without later-period metric columns. The authoritative candidate manifest now includes ten Alpha158 benchmark memberships while all pre-existing R/L/M rows remain unchanged.

## Readiness checks

- Alpha158 Train metrics: 158/158
- Alpha158 Train top 10: frozen
- R/L/M top-10 shortlists: unchanged, 10 per arm
- Common checkpoint leaders: unchanged, budgets 10/20/50
- Historical failed audit: unchanged, SHA-256 `{before[REPORT / 'PRE_VALIDATION_AUDIT.md']}`
- Validation outcomes accessed: false
- Final Test accessed: false
- `FINAL_TEST_LOCKED=true`
"""
    addendum_path = REPORT / "PRE_VALIDATION_AUDIT_ADDENDUM_ALPHA158.md"
    temporary = addendum_path.with_suffix(addendum_path.suffix + ".tmp")
    temporary.write_text(addendum, encoding="utf-8")
    temporary.replace(addendum_path)

    print(
        json.dumps(
            {
                "alpha158_train_features": len(metrics),
                "alpha158_train_top10": True,
                "search_manifest_rows_unchanged": len(search_rows),
                "validation_accessed": False,
                "final_test_locked": True,
                "pre_validation_audit_status": "PASS",
                "ready_to_run_validation": True,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
