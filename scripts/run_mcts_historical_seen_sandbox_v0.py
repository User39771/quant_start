"""Run the frozen historical-seen MCTS v0 sandbox and write its audit reports."""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from aq_factor_lab.mcts_sandbox import (  # noqa: E402
    MAX_DEPTH,
    PRIMITIVES,
    canonical,
    depth,
    evaluate_expression,
    formula,
    parse_formula,
    primitive_set,
    quantile_members,
    random_expression,
    run_mcts,
    score_candidate,
)
from aq_factor_lab.phase_a_evaluation import _turnover, endpoint_max_drawdown  # noqa: E402
from scripts.test_liquidity_filter_hypothesis_v1_6 import (  # noqa: E402
    build_liquidity_panel,
    load_inputs,
    validate_amount_contract,
)

IDENTITY = {
    "experiment_type": "mcts_search_sandbox",
    "sample_role": "historical_seen",
    "descriptive_only": True,
    "alpha_claim_allowed": False,
    "oos_claim_allowed": False,
    "prospective_data_accessed": False,
    "final_test_accessed": False,
    "result_type": "search_mechanism_diagnostic",
}
SEEDS = (20260721, 20260722, 20260723, 20260724, 20260725)
BUDGET = 1000
OUTPUT = Path("reports/mcts_sandbox_v0")
PROTECTED_TOKENS = ("prospective", "final_test")


def guarded_read_csv(root: Path, relative: str, **kwargs) -> pd.DataFrame:
    lowered = relative.replace("\\", "/").lower()
    if any(token in lowered for token in PROTECTED_TOKENS):
        raise PermissionError(f"sandbox_forbidden_path={relative}")
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise PermissionError(f"outside_project_root={relative}")
    return pd.read_csv(path, **kwargs)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_historical_panel(root: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    mom_path = "data/processed/mom60_factor_panel_v1_3.csv"
    lowvol_path = "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv"
    mom = guarded_read_csv(root, mom_path, dtype={"stock_code": str})
    lowvol = guarded_read_csv(root, lowvol_path, dtype={"stock_code": str})
    factor, amount, calendar = load_inputs(root)
    validate_amount_contract(amount, factor)
    liquidity, _ = build_liquidity_panel(factor, amount, calendar)

    for frame in (mom, lowvol, liquidity):
        frame["stock_code"] = frame["stock_code"].str.zfill(6)
    keys = ["period_index", "stock_code"]
    panel = mom.merge(lowvol[keys + ["vol20"]], on=keys, how="left", validate="one_to_one")
    panel = panel.merge(
        liquidity[keys + ["mean_amount_20d"]], on=keys, how="left", validate="one_to_one"
    )
    panel = panel.rename(
        columns={"mom60": "RETURN_60", "vol20": "VOL_20", "mean_amount_20d": "AMOUNT_MEAN_20"}
    )
    official = guarded_read_csv(root, "reports/factor_ic_periods_mom60_v1_3.csv")
    official = official.loc[
        official["factor_name"].eq("MOM60") & official["sample_basis"].eq("mom60_primary_sample"),
        "period_index",
    ]
    panel = panel.loc[panel["period_index"].isin(set(official.astype(int)))].copy()
    for column in ("signal_sample_member",):
        panel[column] = panel[column].astype(str).str.lower().map({"true": True, "false": False})
    for column in ("signal_as_of_date", "rebalance_date", "next_rebalance_date"):
        panel[column] = pd.to_datetime(panel[column], errors="raise")
    if not (
        (panel["signal_as_of_date"] < panel["rebalance_date"])
        & (panel["rebalance_date"] < panel["next_rebalance_date"])
    ).all():
        raise ValueError("invalid_date_order")
    if panel.duplicated(keys).any() or panel["period_index"].nunique() != 54:
        raise ValueError("historical_panel_key_mismatch")
    evidence = {
        mom_path: sha256(root / mom_path),
        lowvol_path: sha256(root / lowvol_path),
        "data/processed/adjusted_price_panel_v1_2.csv": sha256(
            root / "data/processed/adjusted_price_panel_v1_2.csv"
        ),
    }
    return panel, evidence


def registry_row(
    result: dict[str, object], *, method: str, seed: int, index: int, expr, parent: str
) -> dict[str, object]:
    return {
        **IDENTITY,
        "candidate_id": f"{method}_{seed}_{index:04d}",
        "search_method": method,
        "seed": seed,
        "evaluation_index": index,
        "formula": formula(expr),
        "canonical_formula": canonical(expr),
        "depth": depth(expr),
        "primitive_set": ";".join(primitive_set(expr)),
        "parent_id": parent,
        **result,
        "selected_direction": "formula_as_written",
        "direction_rule": "fixed_expression_no_future_sign_flip",
        "duplicate_formula_of": "",
        "information_equivalent_to": "",
        "rank_equivalent": False,
        "portfolio_equivalent": False,
    }


def mark_equivalence(registry: pd.DataFrame) -> pd.DataFrame:
    result = registry.copy()
    for column, output, flag in (
        ("canonical_formula", "duplicate_formula_of", None),
        ("rank_signature_hash", "information_equivalent_to", "rank_equivalent"),
        ("portfolio_signature_hash", None, "portfolio_equivalent"),
    ):
        first: dict[str, str] = {}
        for index, row in result.iterrows():
            value = row[column]
            if not value:
                continue
            if value in first:
                if output:
                    result.at[index, output] = first[value]
                if flag:
                    result.at[index, flag] = True
            else:
                first[value] = row["candidate_id"]
    return result


def top_diagnostic(expr, panel: pd.DataFrame) -> dict[str, object]:
    signal = evaluate_expression(expr, panel)
    periods = []
    weights = None
    previous_returns: dict[str, float] = {}
    nav_gross = nav_net = 1.0
    turnovers = []
    selected_counts = []
    group_returns = {quantile: [] for quantile in range(1, 6)}
    for _period, group in panel.assign(_signal=signal).groupby("period_index", sort=True):
        target = group.loc[group["signal_sample_member"] & np.isfinite(group["_signal"])]
        if target.empty or target["forward_return"].isna().any():
            continue
        quantiles = quantile_members(target, "_signal")
        selected = target.loc[quantiles[5]]
        for quantile, indices in quantiles.items():
            group_returns[quantile].append(float(target.loc[indices, "forward_return"].mean()))
        current = dict.fromkeys(selected["stock_code"], 1.0 / len(selected))
        turnover = _turnover(current, weights, previous_returns)
        returns = dict(zip(group["stock_code"], group["forward_return"], strict=True))
        gross = sum(current[code] * returns[code] for code in current)
        net = gross - turnover * 0.002
        nav_gross *= 1 + gross
        nav_net *= 1 + net
        periods.append(gross)
        turnovers.append(turnover)
        selected_counts.append(len(selected))
        weights, previous_returns = current, returns
    return {
        "q5_gross_cumulative_return": nav_gross - 1,
        "q5_net_cumulative_return_20bps": nav_net - 1,
        "average_turnover": float(np.mean(turnovers)),
        "endpoint_maximum_drawdown_gross": endpoint_max_drawdown(pd.Series(periods)),
        "average_selected_count": float(np.mean(selected_counts)),
        "portfolio_valid_periods": len(periods),
        "period_coverage": len(periods) / panel["period_index"].nunique(),
        **{
            f"q{quantile}_mean_period_return": float(np.mean(values))
            for quantile, values in group_returns.items()
        },
    }


def search(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, str]]:
    panel, evidence = load_historical_panel(root)
    rows: list[dict[str, object]] = []
    runtimes: list[dict[str, object]] = []
    for seed in SEEDS:
        for method in ("mcts", "random"):
            started = time.perf_counter()
            if method == "mcts":
                evaluated = run_mcts(seed, BUDGET, lambda expr: score_candidate(expr, panel))
                rows.extend(
                    registry_row(
                        result,
                        method=method,
                        seed=seed,
                        index=index,
                        expr=expr,
                        parent=parent,
                    )
                    for index, (expr, parent, result) in enumerate(evaluated, 1)
                )
            else:
                import random

                rng = random.Random(seed)
                for index in range(1, BUDGET + 1):
                    expr = random_expression(rng)
                    rows.append(
                        registry_row(
                            score_candidate(expr, panel),
                            method=method,
                            seed=seed,
                            index=index,
                            expr=expr,
                            parent="",
                        )
                    )
            runtimes.append(
                {
                    "search_method": method,
                    "seed": seed,
                    "runtime_seconds": time.perf_counter() - started,
                }
            )
    registry = mark_equivalence(pd.DataFrame(rows))
    valid_rewards = registry.loc[registry["evaluation_status"].eq("ok"), "reward"]
    target = float(valid_rewards.quantile(0.90))
    summary_rows = []
    for (method, seed), group in registry.groupby(["search_method", "seed"], sort=True):
        valid = group.loc[group["evaluation_status"].eq("ok")]
        hits = valid.loc[valid["reward"].ge(target), "evaluation_index"]
        summary_rows.append(
            {
                "search_method": method,
                "seed": seed,
                "candidate_evaluations": len(group),
                "best_reward": valid["reward"].max(),
                "common_reward_p90_target": target,
                "evaluations_to_target": int(hits.min()) if not hits.empty else math.nan,
                "syntactically_unique_count": group["formula"].nunique(),
                "canonical_formula_count": group["canonical_formula"].nunique(),
                "unique_rank_signal_count": valid["rank_signature_hash"].nunique(),
                "unique_portfolio_count": valid["portfolio_signature_hash"].nunique(),
                "portfolio_equivalent_count": int(valid["portfolio_equivalent"].sum()),
                "redundancy_rate": 1 - valid["rank_signature_hash"].nunique() / len(valid),
                "failed_count": int(group["evaluation_status"].eq("failed").sum()),
            }
        )
    summary = pd.DataFrame(summary_rows).merge(pd.DataFrame(runtimes), on=["search_method", "seed"])
    top_ids = (
        registry.loc[registry["evaluation_status"].eq("ok")]
        .sort_values("reward", ascending=False)
        .groupby("search_method")
        .head(5)["candidate_id"]
    )
    diagnostics = []
    for _, row in registry.loc[registry["candidate_id"].isin(top_ids)].iterrows():
        diagnostics.append(
            {
                "candidate_id": row["candidate_id"],
                "search_method": row["search_method"],
                "formula": row["formula"],
                "mean_rankic": row["mean_rankic"],
                "median_rankic": row["median_rankic"],
                "positive_rankic_ratio": row["positive_rankic_ratio"],
                "valid_periods": row["valid_periods"],
                **top_diagnostic(parse_formula(row["formula"]), panel),
            }
        )
    return registry, summary, pd.DataFrame(diagnostics), evidence


def write_outputs(root: Path, registry, summary, diagnostics, evidence) -> None:
    output = root / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    registry.to_csv(output / "candidate_registry.csv", index=False)
    summary.to_csv(output / "mcts_vs_random_summary.csv", index=False)
    diagnostics.to_csv(output / "top_candidate_diagnostics.csv", index=False)
    medians = summary.groupby("search_method").median(numeric_only=True)
    advantage = (
        medians.loc["mcts", "best_reward"] > medians.loc["random", "best_reward"]
        and medians.loc["mcts", "evaluations_to_target"]
        < medians.loc["random", "evaluations_to_target"]
        and medians.loc["mcts", "unique_rank_signal_count"]
        >= medians.loc["random", "unique_rank_signal_count"]
    )
    counts = {
        "formula": registry["formula"].nunique(),
        "canonical": registry["canonical_formula"].nunique(),
        "rank": registry.loc[registry.evaluation_status.eq("ok"), "rank_signature_hash"].nunique(),
        "portfolio": registry.loc[
            registry.evaluation_status.eq("ok"), "portfolio_signature_hash"
        ].nunique(),
    }
    identity_text = "\n".join(
        f"{key}={str(value).lower() if isinstance(value, bool) else value}"
        for key, value in IDENTITY.items()
    )
    mcts_evaluations = len(registry.loc[registry.search_method.eq("mcts")])
    random_evaluations = len(registry.loc[registry.search_method.eq("random")])
    valid_count = len(registry.loc[registry.evaluation_status.eq("ok")])
    redundancy = 1 - counts["rank"] / valid_count
    report = f"""# MCTS v0 versus Random Search — Historical-Seen Sandbox

```text
{identity_text}
```

## Result

MCTS {'showed' if advantage else 'did not show'} a search-efficiency advantage within this
historical_seen sandbox under the frozen three-part comparison rule. This is a
search-mechanism diagnostic, not Alpha discovery or OOS evidence.

## Search and redundancy

- primitives: `{', '.join(PRIMITIVES)}`; operators: `NEG, RANK, ADD, SUB, MUL`;
  maximum depth: `{MAX_DEPTH}`
- reward: mean per-period Spearman RankIC of the formula as written; no future-selected direction
- evaluations: MCTS `{mcts_evaluations}`; Random `{random_evaluations}`
- distinct formula strings: `{counts['formula']}`
- canonical formulas: `{counts['canonical']}`
- unique exact rank signals: `{counts['rank']}`
- unique Q5 portfolios: `{counts['portfolio']}`
- overall rank-information redundancy: `{redundancy:.2%}`

## Per-seed comparison

{summary.to_markdown(index=False)}

## Top historical diagnostics

{diagnostics.to_markdown(index=False)}

Return, turnover, 20bps cost, endpoint drawdown and selected-count fields above were
calculated only after search. They did not enter reward and did not trigger any
search-space or parameter change.

## Boundary and evidence

Inputs were restricted to previously viewed historical panels. Input hashes: `{evidence}`.
The runner rejects any path containing `prospective` or `final_test`. No Phase B file,
decision, threshold, or output was modified.
"""
    (output / "mcts_vs_random_report.md").write_text(report, encoding="utf-8")
    ideas = """# Next-round ideas (not executed)

- Compare canonical-expansion deduplication with the v0 evaluate-all registry.
- Test rank-normalizing unlike-scale primitives before ADD/SUB.
- Add a preregistered runtime-normalized comparison only after reviewing v0.

These are historical-seen sandbox ideas only. No v1 run is authorized.
"""
    (output / "next_round_ideas.md").write_text(ideas, encoding="utf-8")


def refresh_existing_diagnostics(root: Path) -> None:
    """Refresh portfolio equivalence/diagnostics without performing candidate search."""

    output = root / OUTPUT
    registry = pd.read_csv(output / "candidate_registry.csv").fillna("")
    summary = pd.read_csv(output / "mcts_vs_random_summary.csv")
    panel, evidence = load_historical_panel(root)
    valid = registry.loc[registry["evaluation_status"].eq("ok")]
    portfolio_by_rank = {}
    for rank_hash, group in valid.groupby("rank_signature_hash"):
        representative = parse_formula(group.iloc[0]["formula"])
        portfolio_by_rank[rank_hash] = score_candidate(representative, panel)[
            "portfolio_signature_hash"
        ]
    registry.loc[valid.index, "portfolio_signature_hash"] = valid["rank_signature_hash"].map(
        portfolio_by_rank
    )
    registry["portfolio_equivalent"] = False
    registry = mark_equivalence(registry)
    for index, row in summary.iterrows():
        group = registry.loc[
            registry["search_method"].eq(row["search_method"])
            & registry["seed"].eq(row["seed"])
            & registry["evaluation_status"].eq("ok")
        ]
        summary.at[index, "unique_portfolio_count"] = group[
            "portfolio_signature_hash"
        ].nunique()
        summary.at[index, "portfolio_equivalent_count"] = int(
            group["portfolio_equivalent"].sum()
        )
    top_ids = (
        valid.sort_values("reward", ascending=False)
        .groupby("search_method")
        .head(5)["candidate_id"]
    )
    diagnostics = []
    for _, row in registry.loc[registry["candidate_id"].isin(top_ids)].iterrows():
        diagnostics.append(
            {
                "candidate_id": row["candidate_id"],
                "search_method": row["search_method"],
                "formula": row["formula"],
                "mean_rankic": row["mean_rankic"],
                "median_rankic": row["median_rankic"],
                "positive_rankic_ratio": row["positive_rankic_ratio"],
                "valid_periods": row["valid_periods"],
                **top_diagnostic(parse_formula(row["formula"]), panel),
            }
        )
    write_outputs(root, registry, summary, pd.DataFrame(diagnostics), evidence)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    parser.add_argument("--refresh-existing-diagnostics", action="store_true")
    args = parser.parse_args()
    if args.refresh_existing_diagnostics:
        refresh_existing_diagnostics(args.project_root.resolve())
        print("mcts_sandbox_v0 refreshed existing diagnostics; search_not_run=true")
        return 0
    registry, summary, diagnostics, evidence = search(args.project_root.resolve())
    if len(registry) != 2 * len(SEEDS) * BUDGET:
        raise ValueError("budget_mismatch")
    write_outputs(args.project_root.resolve(), registry, summary, diagnostics, evidence)
    print(f"mcts_sandbox_v0 completed evaluations={len(registry)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
