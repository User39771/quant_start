"""Build the Train-only pre-Validation audit artifacts for ALPHA_JUNGLE_QLIB_C0."""

from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "reports" / "alpha_jungle_c0"
TRACE_DIR = REPORT / "search_traces"
CHECKPOINT_DIR = REPORT / "checkpoints"
COMMON_BUDGETS = (10, 20, 50)
ARMS = ("GRAMMAR_RANDOM", "DIRECT_LLM", "LLM_GUIDED_MCTS")
TRACE_FILES = {
    "GRAMMAR_RANDOM": TRACE_DIR / "random_search_trace.csv",
    "DIRECT_LLM": TRACE_DIR / "direct_llm_trace.csv",
    "LLM_GUIDED_MCTS": TRACE_DIR / "mcts_trace.csv",
}
CHECKPOINT_FILES = {
    "GRAMMAR_RANDOM": CHECKPOINT_DIR / "random_checkpoints.csv",
    "DIRECT_LLM": CHECKPOINT_DIR / "direct_llm_checkpoints.csv",
    "LLM_GUIDED_MCTS": CHECKPOINT_DIR / "mcts_checkpoints.csv",
}
METRIC_FIELDS = (
    "composite_reward",
    "mean_rank_ic",
    "rank_ir",
    "positive_ratio",
    "subperiod_direction_ratio",
    "turnover",
    "diversity",
    "ors_proxy",
)


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


def float_value(row: dict[str, str], name: str) -> float:
    return float(row[name])


def accepted_rows(path: Path) -> list[dict[str, str]]:
    rows = [row for row in read_csv(path) if row["parse_validation_status"] == "accepted"]
    for index, row in enumerate(rows, 1):
        persisted = row.get("accepted_index") or row.get("accepted_formula_count")
        if persisted and int(persisted) != index:
            raise AssertionError(f"{path}: accepted index {persisted} != reconstructed {index}")
        row["_accepted_index"] = str(index)
    return rows


def top_key(row: dict[str, str]) -> tuple[float, float, float, float, int]:
    return (
        -float_value(row, "composite_reward"),
        -float_value(row, "mean_rank_ic"),
        -float_value(row, "rank_ir"),
        float_value(row, "turnover"),
        int(row["_accepted_index"]),
    )


def leader_key(row: dict[str, str]) -> tuple[float, float, float, float, int]:
    # The first element implements the frozen checkpoint rule; the rest only
    # make a numerically exact reward tie deterministic without using Validation.
    return top_key(row)


def proposal_index(row: dict[str, str]) -> str:
    return row.get("charged_call_index") or row["proposal_index"]


def output_row(arm: str, row: dict[str, str]) -> dict[str, object]:
    result: dict[str, object] = {
        "arm": arm,
        "accepted_candidate_index": int(row["_accepted_index"]),
        "raw_proposal_call_index": int(proposal_index(row)),
        "formula": row["formula"],
        "canonical_formula": row["canonical_formula"],
    }
    for field in METRIC_FIELDS:
        result[field] = row[field]
    return result


def assert_close(actual: str, expected: str, context: str) -> None:
    if abs(float(actual) - float(expected)) > 1e-12:
        raise AssertionError(f"{context}: {actual} != {expected}")


def main() -> None:
    manifest = json.loads((REPORT / "search_run_manifest.json").read_text(encoding="utf-8"))
    resume = json.loads((REPORT / "FORMAL_SEARCH_RESUME_STATE.json").read_text(encoding="utf-8"))
    assert manifest["validation_accessed"] is False
    assert manifest["final_test_accessed"] is False
    assert manifest["final_test_locked"] is True
    assert resume["validation_accessed"] is False
    assert resume["final_test_accessed"] is False
    assert resume["final_test_locked"] is True
    assert manifest["formal"]["GRAMMAR_RANDOM"]["accepted"] == 100
    assert manifest["formal"]["DIRECT_LLM"]["accepted"] == 51
    assert manifest["formal"]["DIRECT_LLM"]["llm_calls"] == 150
    assert manifest["formal"]["LLM_GUIDED_MCTS"]["accepted"] == 100
    assert manifest["formal"]["LLM_GUIDED_MCTS"]["llm_calls"] == 143

    accepted = {arm: accepted_rows(TRACE_FILES[arm]) for arm in ARMS}
    assert {arm: len(rows) for arm, rows in accepted.items()} == {
        "GRAMMAR_RANDOM": 100,
        "DIRECT_LLM": 51,
        "LLM_GUIDED_MCTS": 100,
    }

    leaders: list[dict[str, object]] = []
    leader_sources: dict[tuple[str, int], dict[str, str]] = {}
    for arm in ARMS:
        checkpoints = {int(row["accepted_count"]): row for row in read_csv(CHECKPOINT_FILES[arm])}
        for budget in COMMON_BUDGETS:
            if budget not in checkpoints:
                raise AssertionError(f"{arm}: missing checkpoint {budget}")
            candidates = accepted[arm][:budget]
            leader = min(candidates, key=leader_key)
            checkpoint = checkpoints[budget]
            comparisons = {
                "best_reward": "composite_reward",
                "best_mean_rank_ic": "mean_rank_ic",
                "best_rank_ir": "rank_ir",
                "best_turnover": "turnover",
                "best_diversity": "diversity",
                "best_ors_proxy": "ors_proxy",
            }
            for checkpoint_field, trace_field in comparisons.items():
                assert_close(
                    checkpoint[checkpoint_field],
                    leader[trace_field],
                    f"{arm}@{budget} {checkpoint_field}",
                )
            if int(checkpoint["raw_proposal_count"]) != int(proposal_index(candidates[-1])):
                raise AssertionError(f"{arm}@{budget}: raw proposal count mismatch")
            item = output_row(arm, leader)
            item["accepted_budget"] = budget
            leaders.append(item)
            leader_sources[(arm, budget)] = leader

    if leader_sources[("DIRECT_LLM", 10)]["canonical_formula"] != leader_sources[
        ("LLM_GUIDED_MCTS", 10)
    ]["canonical_formula"]:
        raise AssertionError("Direct@10 and MCTS@10 are not the same canonical formula")

    leader_arms: dict[str, set[str]] = defaultdict(set)
    for row in leaders:
        leader_arms[str(row["canonical_formula"])].add(str(row["arm"]))
    duplicate_canonicals = sorted(c for c, arms in leader_arms.items() if len(arms) > 1)
    checkpoint_duplicate_ids = {
        canonical: f"CHECKPOINT-DUP-{index:03d}"
        for index, canonical in enumerate(duplicate_canonicals, 1)
    }
    for row in leaders:
        row["cross_arm_duplicate_group_id"] = checkpoint_duplicate_ids.get(
            str(row["canonical_formula"]), ""
        )

    top10: list[dict[str, object]] = []
    for arm in ARMS:
        for rank, row in enumerate(sorted(accepted[arm], key=top_key)[:10], 1):
            item = output_row(arm, row)
            item["train_rank_within_arm"] = rank
            top10.append(item)
    assert Counter(row["arm"] for row in top10) == Counter({arm: 10 for arm in ARMS})

    historical = read_csv(REPORT / "best_train_candidates.csv")
    historical_counts = Counter(row["arm"] for row in historical)
    best_artifact_incomplete = set(historical_counts) != set(ARMS)
    assert best_artifact_incomplete
    assert historical_counts["DIRECT_LLM"] == 0

    membership: dict[tuple[str, str], dict[str, object]] = {}
    for row in leaders:
        key = (str(row["arm"]), str(row["canonical_formula"]))
        item = membership.setdefault(key, dict(row))
        item.setdefault("roles", set()).add(f"CHECKPOINT_LEADER_{row['accepted_budget']}")
        item.setdefault("budgets", set()).add(int(row["accepted_budget"]))
    for row in top10:
        key = (str(row["arm"]), str(row["canonical_formula"]))
        item = membership.setdefault(key, dict(row))
        item.setdefault("roles", set()).add("TRAIN_TOP10")
        item.setdefault("budgets", set())

    formula_arms: dict[str, set[str]] = defaultdict(set)
    for arm, canonical in membership:
        formula_arms[canonical].add(arm)
    all_duplicate_ids = {
        canonical: f"CROSS-ARM-DUP-{index:03d}"
        for index, canonical in enumerate(sorted(c for c, arms in formula_arms.items() if len(arms) > 1), 1)
    }
    candidate_manifest: list[dict[str, object]] = []
    for index, ((arm, canonical), item) in enumerate(sorted(membership.items()), 1):
        record = dict(item)
        record.update(
            {
                "candidate_id": f"SEARCH-{index:03d}",
                "source_type": "SEARCH",
                "arm": arm,
                "candidate_role": ";".join(sorted(item["roles"])),
                "accepted_budget": ";".join(str(x) for x in sorted(item["budgets"])),
                "cross_arm_duplicate_group_id": all_duplicate_ids.get(canonical, ""),
            }
        )
        candidate_manifest.append(record)

    common_fields = [
        "arm",
        "accepted_budget",
        "accepted_candidate_index",
        "raw_proposal_call_index",
        "formula",
        "canonical_formula",
        *METRIC_FIELDS,
        "cross_arm_duplicate_group_id",
    ]
    top_fields = [
        "arm",
        "train_rank_within_arm",
        "accepted_candidate_index",
        "raw_proposal_call_index",
        "formula",
        "canonical_formula",
        *METRIC_FIELDS,
    ]
    candidate_fields = [
        "candidate_id",
        "source_type",
        "arm",
        "candidate_role",
        "accepted_budget",
        "accepted_candidate_index",
        "raw_proposal_call_index",
        "formula",
        "canonical_formula",
        *METRIC_FIELDS,
        "cross_arm_duplicate_group_id",
    ]

    write_csv(REPORT / "COMMON_CHECKPOINT_LEADERS.csv", common_fields, leaders)
    write_csv(REPORT / "TRAIN_TOP10_BY_ARM.csv", top_fields, top10)
    write_csv(REPORT / "VALIDATION_CANDIDATE_MANIFEST.csv", candidate_fields, candidate_manifest)
    write_csv(
        REPORT / "ALPHA158_VALIDATION_MANIFEST.csv",
        ["benchmark_id", "status", "selection_source", "frozen_train_selection_rule", "requested_count"],
        [
            {
                "benchmark_id": "ALPHA158",
                "status": "BLOCKED_NO_FROZEN_TRAIN_RANKING_ARTIFACT",
                "selection_source": "NOT_AVAILABLE_IN_AUTHORIZED_FROZEN_TRAIN_ARTIFACTS",
                "frozen_train_selection_rule": "TOP_10_BY_TRAIN_MEAN_RANK_IC",
                "requested_count": 10,
            }
        ],
    )

    formula_lines = [
        f"- {row['arm']}@{row['accepted_budget']}: `{row['canonical_formula']}`"
        for row in leaders
    ]
    duplicate_lines = [
        f"- {checkpoint_duplicate_ids[canonical]}: `{canonical}`"
        for canonical in duplicate_canonicals
    ] or ["- None"]
    audit = f"""# ALPHA_JUNGLE_QLIB_C0 final pre-Validation audit

## Result

**PRE_VALIDATION_AUDIT_FAIL**

The three formal Train traces and checkpoint files are internally consistent. The exact search-candidate manifest is frozen without any Validation or Final Test access. The audit cannot set `READY_TO_RUN_VALIDATION=YES`, because no already-frozen, Train-only Alpha158 factor ranking artifact exists from which to identify the required top 10 Alpha158 factors. Computing that ranking now would violate this audit's restriction to already-frozen Train-search artifacts.

## Existing historical candidate artifact

`BEST_TRAIN_CANDIDATES_ARTIFACT_INCOMPLETE=true`. The historical `best_train_candidates.csv` contains {historical_counts['GRAMMAR_RANDOM']} Random rows, {historical_counts['LLM_GUIDED_MCTS']} MCTS rows, and {historical_counts['DIRECT_LLM']} Direct rows. It was not changed. This is an archival/artifact-generation defect, not a Train-search defect; Direct's accepted trace remains complete.

## Frozen checkpoint design

`PRIMARY_COMMON_ACCEPTED_BUDGETS=[10,20,50]`. Random@100 and MCTS@100 are secondary only. Direct@51 is not treated as an equal-budget comparison with either @100 observation.

### Exact best-so-far Train checkpoint leaders

{chr(10).join(formula_lines)}

All nine checkpoint metrics match their corresponding accepted formal trace rows. The checkpoint raw proposal/call counts also match the proposal that reached each accepted budget.

### Cross-arm checkpoint duplicates

{chr(10).join(duplicate_lines)}

Direct@10 and MCTS@10 are the same canonical formula. When later evaluated on the same frozen sample, their arm-independent metrics must be identical; equality is a tie, not a win.

## Authoritative Train shortlist

The top 10 accepted formal candidates per arm are frozen in `TRAIN_TOP10_BY_ARM.csv`. Smoke, the aborted interface segment, rejected proposals, and invalid proposals are excluded. Ranking and tie-breaking are: higher Train composite reward, higher Train mean RankIC, higher Train RankIR, lower turnover, then earlier accepted index.

Cross-arm rediscoveries are retained as separate arm memberships. A shared canonical formula may later be evaluated once on the same data and its arm-independent metrics reused identically. The historical Train composite reward is unchanged and remains **search-time guidance only**, because its diversity term depends on the arm-local evolving Alpha Zoo.

## Frozen future comparison and selection rules

- Primary metric: mean daily cross-sectional Spearman RankIC on the same historical CSI300 universe and frozen 10-day label.
- Secondary metrics: RankIR, positive-day ratio, fixed yearly direction consistency, daily/top-decile turnover, and valid-session coverage.
- Stability interval: 2019-01-01 through 2020-12-31 under the frozen label-endpoint rule, split only into calendar 2019 and calendar 2020. Record the full-period mean, both yearly means, and whether both yearly means share the full-period sign.
- MCTS has a search-efficiency advantage over both baselines only if it is at least as good as each baseline at two of three common checkpoints, strictly better than each at checkpoint 50, and both arithmetic mean checkpoint differences (MCTS minus Random; MCTS minus Direct) are positive.
- Per-arm final selection: highest full-period mean RankIC; then RankIR; then 2019/2020 sign consistency; then lower turnover; then higher Train composite reward; then earlier Train accepted index. A Train-to-later-period sign reversal remains visible and is not filtered.
- Exactly one selected formula per search arm may later enter Final Test.
- Alpha158 is a benchmark, not a search arm. `B_MEDIAN` is the complete-library factor-level performance distribution/median. `B_SELECTED` must start from the top 10 Alpha158 factors ranked by Train mean RankIC, and later use the same hierarchy except that the fifth tie-break is Train mean RankIC. No LightGBM/MLP is authorized.

The formal call ledger is preserved: Random 100/194, Direct 51/150 (frozen call cap), and MCTS 100/143. Accepted-per-call is `OPERATIONAL_SECONDARY`, not clean causal evidence, because provider-failure counts differ materially.

## Locks and readiness

- Validation accessed: false
- Final Test accessed: false
- `FINAL_TEST_LOCKED=true`
- `READY_TO_RUN_VALIDATION=NO`
- Blocker: `ALPHA158_VALIDATION_MANIFEST.csv` records `BLOCKED_NO_FROZEN_TRAIN_RANKING_ARTIFACT`.
"""
    temporary = REPORT / "PRE_VALIDATION_AUDIT.md.tmp"
    temporary.write_text(audit, encoding="utf-8")
    temporary.replace(REPORT / "PRE_VALIDATION_AUDIT.md")

    # Final output QA: no later-period result columns and no loss of arm membership.
    assert len(leaders) == 9
    assert len(top10) == 30
    assert all("validation" not in field.lower() for field in candidate_fields)
    assert set(row["arm"] for row in candidate_manifest) == set(ARMS)
    assert any(row["cross_arm_duplicate_group_id"] for row in candidate_manifest)
    print(
        json.dumps(
            {
                "audit": "FAIL",
                "checkpoint_leaders": len(leaders),
                "top10_rows": len(top10),
                "candidate_memberships": len(candidate_manifest),
                "checkpoint_duplicate_formulas": duplicate_canonicals,
                "alpha158": "BLOCKED_NO_FROZEN_TRAIN_RANKING_ARTIFACT",
                "ready_to_run_validation": False,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
