"""Run MCTS historical-seen sandbox v1; never reads prospective/final paths."""

from __future__ import annotations

import argparse
import json
import math
import random
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from aq_factor_lab.mcts_sandbox import quantile_members  # noqa: E402
from aq_factor_lab.mcts_sandbox_v1 import (  # noqa: E402
    FAILED_TREE_REWARD,
    MAX_DEPTH,
    PRIMITIVES,
    RAW_PRIMITIVES,
    Node,
    backpropagate,
    build_common_signal_panel,
    canonical,
    depth,
    evaluate_expression,
    formula,
    mcts_proposal,
    primitive_set,
    q5_signature,
    random_expression,
    reward_from_identity,
    signal_identity,
)
from aq_factor_lab.phase_a_evaluation import _turnover, endpoint_max_drawdown  # noqa: E402
from scripts.run_mcts_historical_seen_sandbox_v0 import (  # noqa: E402
    guarded_read_csv,
    load_historical_panel,
)

IDENTITY = {
    "experiment_type": "mcts_search_sandbox",
    "version": "v1",
    "sample_role": "historical_seen",
    "descriptive_only": True,
    "alpha_claim_allowed": False,
    "oos_claim_allowed": False,
    "prospective_data_accessed": False,
    "final_test_accessed": False,
}
SEEDS = (20260721, 20260722, 20260723, 20260724, 20260725)
UNIQUE_BUDGET = 1000
MAX_PROPOSALS = 10000
OUTPUT = Path("reports/mcts_sandbox_v1")


def load_v1_panel(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]]]:
    panel, _ = load_historical_panel(root)
    labels = panel[["period_index", "stock_code", "forward_return"]].copy()
    signal_columns = [
        "period_index",
        "stock_code",
        "signal_as_of_date",
        "rebalance_date",
        "next_rebalance_date",
        "signal_sample_member",
        *RAW_PRIMITIVES,
    ]
    signal_panel, coverage = build_common_signal_panel(panel[signal_columns])
    result = signal_panel.merge(labels, on=["period_index", "stock_code"], validate="one_to_one")
    result = result.sort_values(["period_index", "stock_code"]).reset_index(drop=True)
    metadata = []
    for relative in (
        "data/processed/mom60_factor_panel_v1_3.csv",
        "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv",
        "data/processed/adjusted_price_panel_v1_2.csv",
    ):
        frame = guarded_read_csv(root, relative)
        date_columns = [name for name in frame.columns if "date" in name.lower()]
        dates = (
            pd.concat(
                [pd.to_datetime(frame[name], errors="coerce") for name in date_columns],
                ignore_index=True,
            )
            if date_columns
            else pd.Series(dtype="datetime64[ns]")
        )
        metadata.append(
            {
                "input_path": relative,
                "row_count": len(frame),
                "date_min": dates.min(),
                "date_max": dates.max(),
                "columns": ";".join(frame.columns),
            }
        )
    return result, coverage, metadata


def verify_rev60_identity(panel: pd.DataFrame) -> None:
    negative = ("NEG", ("P_RETURN_60",))
    normalized = evaluate_expression(negative, panel)
    raw = -panel["RETURN_60"]
    for _, group in panel.assign(_normalized=normalized, _raw=raw).groupby("period_index"):
        target = group.loc[group["common_period_valid"] & group["common_signal_member"]]
        if (
            not target["_normalized"]
            .rank(method="average")
            .equals(target["_raw"].rank(method="average"))
        ):
            raise ValueError("rev60_rank_order_mismatch")
        if set(quantile_members(target, "_normalized")[5]) != set(
            quantile_members(target, "_raw")[5]
        ):
            raise ValueError("rev60_q5_mismatch")
        normalized_rho = target["_normalized"].corr(target["forward_return"], method="spearman")
        raw_rho = target["_raw"].corr(target["forward_return"], method="spearman")
        if not np.isclose(normalized_rho, raw_rho, equal_nan=True):
            raise ValueError("rev60_rankic_direction_mismatch")


def _empty_result(reason: str) -> dict[str, object]:
    return {
        "evaluation_status": "failed",
        "failure_reason": reason,
        "reward": math.nan,
        "mean_rankic": math.nan,
        "median_rankic": math.nan,
        "positive_rankic_ratio": math.nan,
        "valid_periods": 0,
        "signal_rank_signature": "",
        "q5_membership_signature": "",
    }


def search_seed(
    method: str,
    seed: int,
    panel: pd.DataFrame,
    *,
    unique_budget: int = UNIQUE_BUDGET,
    max_proposals: int = MAX_PROPOSALS,
) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    root = Node(None)
    canonical_cache: dict[str, dict] = {}
    rank_cache: dict[str, dict] = {}
    rows = []
    unique_count = 0
    started = time.perf_counter()
    common = panel.loc[panel["common_period_valid"] & panel["common_signal_member"]]
    period_counts = common.groupby("period_index").size()
    for proposal_index in range(1, max_proposals + 1):
        if unique_count >= unique_budget:
            break
        if method == "mcts":
            node = mcts_proposal(root, rng)
            expr = node.expr
            parent = formula(node.parent.expr) if node.parent and node.parent.expr else ""
        else:
            node = None
            expr = random_expression(rng)
            parent = ""
        candidate_id = f"{method}_{seed}_{proposal_index:05d}"
        canonical_formula = canonical(expr)
        base = {
            **IDENTITY,
            "candidate_id": candidate_id,
            "search_method": method,
            "seed": seed,
            "proposal_index": proposal_index,
            "unique_evaluation_index": math.nan,
            "formula": formula(expr),
            "canonical_formula": canonical_formula,
            "depth": depth(expr),
            "primitive_set": ";".join(primitive_set(expr)),
            "parent_id": parent,
            "common_periods": int(
                panel.loc[panel["common_period_valid"], "period_index"].nunique()
            ),
            "minimum_common_stock_count": int(period_counts.min()),
            "median_common_stock_count": float(period_counts.median()),
            "canonical_cache_hit": False,
            "rank_cache_hit": False,
            "representative_candidate_id": "",
        }
        if canonical_formula in canonical_cache:
            representative = canonical_cache[canonical_formula]
            result = representative["result"].copy()
            base["canonical_cache_hit"] = True
            base["representative_candidate_id"] = representative["candidate_id"]
        else:
            identity = signal_identity(expr, panel)
            if not identity["valid"]:
                result = _empty_result(str(identity["failure_reason"]))
            elif identity["signal_rank_signature"] in rank_cache:
                representative = rank_cache[identity["signal_rank_signature"]]
                result = representative["result"].copy()
                base["rank_cache_hit"] = True
                base["representative_candidate_id"] = representative["candidate_id"]
            else:
                result = {**reward_from_identity(identity), **identity}
                if result["evaluation_status"] == "ok":
                    result["q5_membership_signature"] = q5_signature(identity)
                    result = {
                        key: value for key, value in result.items() if not key.startswith("_")
                    }
                    unique_count += 1
                    base["unique_evaluation_index"] = unique_count
                    rank_cache[result["signal_rank_signature"]] = {
                        "candidate_id": candidate_id,
                        "result": result.copy(),
                    }
            canonical_cache[canonical_formula] = {
                "candidate_id": candidate_id,
                "result": result.copy(),
            }
        row = {**base, **result}
        rows.append(row)
        if method == "mcts":
            observed = result.get("reward", math.nan)
            backpropagate(node, float(observed) if np.isfinite(observed) else FAILED_TREE_REWARD)
    summary = {
        "search_method": method,
        "seed": seed,
        "proposal_attempts": len(rows),
        "unique_reward_evaluations": unique_count,
        "canonical_cache_hits": sum(row["canonical_cache_hit"] for row in rows),
        "rank_cache_hits": sum(row["rank_cache_hit"] for row in rows),
        "invalid_attempts": sum(row["evaluation_status"] == "failed" for row in rows),
        "runtime_seconds": time.perf_counter() - started,
        "search_status": (
            "complete"
            if unique_count == unique_budget
            else "search_space_exhaustion_or_high_redundancy"
        ),
    }
    return rows, summary


def top_diagnostic(expr, panel: pd.DataFrame) -> dict[str, object]:
    signal = evaluate_expression(expr, panel)
    weights = None
    previous_returns: dict[str, float] = {}
    nav_gross = nav_net = 1.0
    turnovers, period_returns, selected_counts = [], [], []
    group_returns = {number: [] for number in range(1, 6)}
    for _, group in panel.assign(_signal=signal).groupby("period_index", sort=True):
        target = group.loc[group["common_period_valid"] & group["common_signal_member"]]
        if target["forward_return"].isna().any():
            continue
        quantiles = quantile_members(target, "_signal")
        for number, indices in quantiles.items():
            group_returns[number].append(float(target.loc[indices, "forward_return"].mean()))
        selected = target.loc[quantiles[5]]
        current = dict.fromkeys(selected["stock_code"], 1 / len(selected))
        turnover = _turnover(current, weights, previous_returns)
        returns = dict(zip(group["stock_code"], group["forward_return"], strict=True))
        gross = sum(current[code] * returns[code] for code in current)
        nav_gross *= 1 + gross
        nav_net *= 1 + gross - turnover * 0.002
        turnovers.append(turnover)
        period_returns.append(gross)
        selected_counts.append(len(selected))
        weights, previous_returns = current, returns
    return {
        "q5_gross_cumulative_return": nav_gross - 1,
        "q5_net_cumulative_return_20bps": nav_net - 1,
        "average_turnover": float(np.mean(turnovers)),
        "endpoint_maximum_drawdown_gross": endpoint_max_drawdown(pd.Series(period_returns)),
        "average_selected_count": float(np.mean(selected_counts)),
        "portfolio_valid_periods": len(period_returns),
        "period_coverage": len(period_returns) / panel["period_index"].nunique(),
        **{
            f"q{number}_mean_period_return": float(np.mean(values))
            for number, values in group_returns.items()
        },
    }


def parse_registry_formula(text: str):
    """Parse only formulas emitted by this runner."""

    import ast

    def convert(node):
        if isinstance(node, ast.Name) and node.id in PRIMITIVES:
            return (node.id,)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            return (node.func.id, *(convert(arg) for arg in node.args))
        raise ValueError(f"invalid_registry_formula={text}")

    return convert(ast.parse(text, mode="eval").body)


def write_contract(output: Path) -> None:
    text = f"""# MCTS Historical-Seen Sandbox v1 — Frozen Search Contract

```text
experiment_type=mcts_search_sandbox
version=v1
sample_role=historical_seen
descriptive_only=true
alpha_claim_allowed=false
oos_claim_allowed=false
prospective_data_accessed=false
final_test_accessed=false
```

- Primitive information: `{", ".join(RAW_PRIMITIVES)}`; searched leaves: `{", ".join(PRIMITIVES)}`.
- Operators: `NEG, RANK, ADD, SUB, MUL`; maximum expression depth: `{MAX_DEPTH}`.
- Common signal mask is the Phase A signal target intersected with finite values of all three raw
  primitives.
- A period is common-valid at coverage >= 95% and at least 25 stocks. No imputation.
- Base primitives use deterministic average-tie cross-sectional percentile ranks within that mask.
- Reward is formula-as-written mean Spearman RankIC; no future-selected direction.
- Both methods use 5 seeds x 1,000 unique reward evaluations, with at most 10,000 proposals per
  seed.
- Canonical hits and signal-only rank-signature hits reuse reward and do not consume unique budget.
- MCTS retains v0 UCT: `mean_reward + sqrt(2)*sqrt(log(parent_visits)/child_visits)`.
- Common threshold is the pooled unique-evaluation reward 90th percentile.
- `MCTS_SEARCH_ADVANTAGE_OBSERVED` requires all three v0 conditions: MCTS median best reward
  > Random, MCTS median unique evaluations-to-threshold < Random, and MCTS median unique rank
  diversity >= Random. If evidence conflicts, classification is `MIXED_SEARCH_MECHANISM_RESULT`;
  otherwise `MCTS_SEARCH_ADVANTAGE_NOT_OBSERVED`.
"""
    (output / "search_advantage_contract_v1.md").write_text(text, encoding="utf-8")


def write_outputs(root: Path, panel, coverage, registry, seed_summary, metadata) -> None:
    output = root / OUTPUT
    registry.to_csv(output / "candidate_registry.csv", index=False)
    coverage.to_csv(output / "common_mask_coverage.csv", index=False)
    pd.DataFrame(metadata).assign(
        runner="run_mcts_historical_seen_sandbox_v1.py",
        search_contract_version="v1",
        generated_at=datetime.now(UTC).isoformat(),
        seeds=";".join(map(str, SEEDS)),
    ).to_csv(output / "input_manifest.csv", index=False)

    evaluated = registry.loc[registry["unique_evaluation_index"].notna()].copy()
    threshold = float(evaluated["reward"].quantile(0.90))
    summaries = []
    for (method, seed), group in registry.groupby(["search_method", "seed"], sort=True):
        unique = group.loc[group["unique_evaluation_index"].notna()].sort_values(
            "unique_evaluation_index"
        )
        hits = unique.loc[unique["reward"].ge(threshold), "unique_evaluation_index"]
        summaries.append(
            {
                **next(
                    item
                    for item in seed_summary
                    if item["search_method"] == method and item["seed"] == seed
                ),
                "best_reward": unique["reward"].max(),
                "common_reward_p90_target": threshold,
                "unique_evaluations_to_target": int(hits.min()) if len(hits) else math.nan,
                "unique_canonical_formulas": group["canonical_formula"].nunique(),
                "unique_rank_signals": group.loc[
                    group["evaluation_status"].eq("ok"), "signal_rank_signature"
                ].nunique(),
                "unique_q5_portfolios": group.loc[
                    group["evaluation_status"].eq("ok"), "q5_membership_signature"
                ].nunique(),
                "unique_information_per_100_evaluations": 100
                * unique["signal_rank_signature"].nunique()
                / max(len(unique), 1),
            }
        )
    summary = pd.DataFrame(summaries)
    summary.to_csv(output / "mcts_vs_random_summary_v1.csv", index=False)

    usage_rows = []
    for primitive_names, group in registry.loc[registry["evaluation_status"].eq("ok")].groupby(
        "primitive_set"
    ):
        usage_rows.append(
            {
                "primitive_set": primitive_names,
                "proposal_count": len(group),
                "unique_canonical_count": group["canonical_formula"].nunique(),
                "unique_rank_signal_count": group["signal_rank_signature"].nunique(),
                "reward_min": group["reward"].min(),
                "reward_median": group["reward"].median(),
                "reward_max": group["reward"].max(),
            }
        )
    usage = pd.DataFrame(usage_rows)
    usage.to_csv(output / "primitive_usage_v1.csv", index=False)

    recurrence_rows = []
    for method, method_group in evaluated.groupby("search_method"):
        top_sets = []
        for _, seed_group in method_group.groupby("seed"):
            top_sets.append(
                set(
                    seed_group.sort_values("reward", ascending=False)
                    .drop_duplicates("signal_rank_signature")
                    .head(10)["signal_rank_signature"]
                )
            )
        occurrences = {}
        for signatures in top_sets:
            for signature in signatures:
                occurrences[signature] = occurrences.get(signature, 0) + 1
        recurrence_rows.append(
            {
                "search_method": method,
                "top_information_distinct_per_seed": 10,
                "pooled_top_slots": sum(map(len, top_sets)),
                "distinct_top_signatures": len(occurrences),
                "signatures_seen_in_multiple_seeds": sum(
                    count > 1 for count in occurrences.values()
                ),
                "maximum_seed_recurrence": max(occurrences.values()),
                "recurring_slot_share": (
                    1 - len(occurrences) / sum(map(len, top_sets)) if top_sets else math.nan
                ),
            }
        )
    recurrence = pd.DataFrame(recurrence_rows)
    recurrence.to_csv(output / "cross_seed_top_recurrence_v1.csv", index=False)

    representatives = (
        evaluated.sort_values("reward", ascending=False)
        .drop_duplicates(["search_method", "signal_rank_signature"])
        .groupby("search_method")
        .head(5)
    )
    diagnostics = []
    for _, row in representatives.iterrows():
        diagnostics.append(
            {
                "candidate_id": row["candidate_id"],
                "search_method": row["search_method"],
                "formula": row["formula"],
                "primitive_set": row["primitive_set"],
                "mean_rankic": row["mean_rankic"],
                "median_rankic": row["median_rankic"],
                "positive_rankic_ratio": row["positive_rankic_ratio"],
                "valid_periods": row["valid_periods"],
                **top_diagnostic(parse_registry_formula(row["formula"]), panel),
            }
        )
    diagnostics = pd.DataFrame(diagnostics)
    diagnostics.to_csv(output / "top_candidate_diagnostics_v1.csv", index=False)

    medians = summary.groupby("search_method").median(numeric_only=True)
    conditions = {
        "median_best_higher": bool(
            medians.loc["mcts", "best_reward"] > medians.loc["random", "best_reward"]
        ),
        "median_evaluations_to_target_lower": bool(
            medians.loc["mcts", "unique_evaluations_to_target"]
            < medians.loc["random", "unique_evaluations_to_target"]
        ),
        "median_rank_diversity_not_lower": bool(
            medians.loc["mcts", "unique_rank_signals"]
            >= medians.loc["random", "unique_rank_signals"]
        ),
    }
    all_primitive_types = all(
        any(name in value for value in usage["primitive_set"]) for name in PRIMITIVES
    )
    if not all_primitive_types:
        classification = "SEARCH_SPACE_EFFECTIVE_VALIDITY_FAILURE"
    elif all(conditions.values()):
        classification = "MCTS_SEARCH_ADVANTAGE_OBSERVED"
    else:
        classification = "MCTS_SEARCH_ADVANTAGE_NOT_OBSERVED"

    successful = registry.loc[registry["evaluation_status"].eq("ok")]
    counts = {
        "formula": successful["formula"].nunique(),
        "canonical": successful["canonical_formula"].nunique(),
        "rank": successful["signal_rank_signature"].nunique(),
        "q5": successful["q5_membership_signature"].nunique(),
    }
    redundancy = 1 - counts["rank"] / len(successful)
    redundancy_rows = []
    for method, group in successful.groupby("search_method"):
        redundancy_rows.append(
            {
                "search_method": method,
                "successful_proposals": len(group),
                "distinct_formulas": group["formula"].nunique(),
                "canonical_formulas": group["canonical_formula"].nunique(),
                "unique_rank_signals": group["signal_rank_signature"].nunique(),
                "unique_q5_portfolios": group["q5_membership_signature"].nunique(),
                "rank_information_redundancy": 1
                - group["signal_rank_signature"].nunique() / len(group),
                "canonical_cache_hits": int(group["canonical_cache_hit"].sum()),
                "rank_cache_hits": int(group["rank_cache_hit"].sum()),
            }
        )
    redundancy_frame = pd.DataFrame(redundancy_rows)
    redundancy_frame.to_csv(output / "redundancy_summary_v1.csv", index=False)
    (output / "redundancy_report_v1.md").write_text(
        "# MCTS Sandbox v1 Redundancy\n\n"
        + redundancy_frame.to_markdown(index=False)
        + "\n\nCache hits are proposal-level search-mechanism evidence. Q5 equivalence is derived "
        "only from signal membership and never controls reward evaluation.\n",
        encoding="utf-8",
    )
    identity_text = "\n".join(
        f"{key}={str(value).lower() if isinstance(value, bool) else value}"
        for key, value in IDENTITY.items()
    )
    report = f"""# MCTS v1 versus Random Search — Historical-Seen Sandbox

```text
{identity_text}
classification={classification}
```

## Result

This is a search-mechanism diagnostic on historical-seen data. It is neither Alpha discovery nor
OOS evidence. The frozen v0 three-part rule produced: `{json.dumps(conditions)}`.

## Common mask

{coverage.to_markdown(index=False)}

## Per-seed comparison

{summary.to_markdown(index=False)}

## Primitive usage

{usage.to_markdown(index=False)}

## Cross-seed top-signal recurrence

{recurrence.to_markdown(index=False)}

## Redundancy

- successful proposals: {len(successful)}
- distinct formula strings: {counts["formula"]}
- canonical formulas: {counts["canonical"]}
- unique rank signals: {counts["rank"]}
- unique Q5 portfolios: {counts["q5"]}
- rank-information redundancy: {redundancy:.2%}

{redundancy_frame.to_markdown(index=False)}

## Top information-distinct historical diagnostics

{diagnostics.to_markdown(index=False)}

Diagnostics did not enter reward and did not alter the search. No prospective/final data was
accessed and no Phase B artifact was modified.
"""
    (output / "mcts_vs_random_report_v1.md").write_text(report, encoding="utf-8")
    (output / "next_round_ideas.md").write_text(
        "# Next-round ideas (not executed)\n\n"
        "Review v1 mechanics and evidence manually before any v2 contract.\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--finalize-existing", action="store_true")
    args = parser.parse_args()
    root = args.project_root.resolve()
    output = root / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    write_contract(output)
    panel, coverage, metadata = load_v1_panel(root)
    verify_rev60_identity(panel)
    if args.finalize_existing:
        registry = pd.read_csv(output / "candidate_registry.csv")
        existing_summary = pd.read_csv(output / "mcts_vs_random_summary_v1.csv")
        summary_columns = [
            "search_method",
            "seed",
            "proposal_attempts",
            "unique_reward_evaluations",
            "canonical_cache_hits",
            "rank_cache_hits",
            "invalid_attempts",
            "runtime_seconds",
            "search_status",
        ]
        write_outputs(
            root,
            panel,
            coverage,
            registry,
            existing_summary[summary_columns].to_dict("records"),
            metadata,
        )
        print("mcts_sandbox_v1 finalized existing search; search_not_run=true")
        return 0
    rows, summaries = [], []
    for seed in SEEDS:
        for method in ("mcts", "random"):
            method_rows, method_summary = search_seed(method, seed, panel)
            rows.extend(method_rows)
            summaries.append(method_summary)
            print(
                f"{method} seed={seed} proposals={method_summary['proposal_attempts']} "
                f"unique={method_summary['unique_reward_evaluations']}"
            )
    registry = pd.DataFrame(rows)
    write_outputs(root, panel, coverage, registry, summaries, metadata)
    print("mcts_sandbox_v1 completed; prospective=false; final_test=false; phase_b_modified=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
