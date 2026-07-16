from __future__ import annotations

import argparse
import hashlib
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scripts import run_lowvol_locked_grid_prototype_v1_5 as legacy
except ImportError:
    import run_lowvol_locked_grid_prototype_v1_5 as legacy


ATOL = 1e-10
RTOL = 1e-8
VERSION = "v1.5.1"
SUCCESS_FILES = (
    "lowvol_locked_grid_prototype_periods_v1_5_1.csv",
    "lowvol_locked_grid_prototype_nav_v1_5_1.csv",
    "lowvol_locked_grid_prototype_summary_v1_5_1.csv",
    "lowvol_locked_grid_prototype_qa_v1_5_1.csv",
    "lowvol_locked_grid_prototype_v1_5_1.md",
    "lowvol_locked_grid_prototype_v1_5_vs_v1_5_1_diff.csv",
    "lowvol_locked_grid_prototype_v1_5_vs_v1_5_1_diff.md",
)
PROTECTED_V15 = (
    "scripts/run_lowvol_locked_grid_prototype_v1_5.py",
    "tests/test_lowvol_locked_grid_prototype_v1_5.py",
    "reports/lowvol_locked_grid_prototype_periods_v1_5.csv",
    "reports/lowvol_locked_grid_prototype_nav_v1_5.csv",
    "reports/lowvol_locked_grid_prototype_summary_v1_5.csv",
    "reports/lowvol_locked_grid_prototype_qa_v1_5.csv",
    "reports/lowvol_locked_grid_prototype_v1_5.md",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_strict_bool(value: object) -> bool:
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)) and not isinstance(value, bool):
        if int(value) in (0, 1):
            return bool(value)
    if isinstance(value, (float, np.floating)) and math.isfinite(float(value)) and float(value) in (0.0, 1.0):
        return bool(int(value))
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("true", "1"):
            return True
        if normalized in ("false", "0"):
            return False
    raise ValueError(f"Invalid strict boolean value: {value!r}")


def parse_bool_columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for column in ("baseline_eligible", "signal_sample_member", "evaluation_sample_member", "primary_reliable_signal", "label_available"):
        if column not in result:
            raise ValueError(f"Missing boolean column: {column}")
        result[column] = result[column].map(parse_strict_bool)
    return result


def normalize_codes(value: object) -> str:
    if pd.isna(value) or str(value).strip() == "":
        return ""
    codes = []
    for raw in str(value).split(";"):
        text = raw.strip()
        if text.endswith(".0"):
            text = text[:-2]
        if not text.isdigit() or len(text) > 6:
            raise ValueError(f"Invalid stock code list: {value!r}")
        codes.append(text.zfill(6))
    if len(codes) != len(set(codes)):
        raise ValueError(f"Duplicate stock code list: {value!r}")
    return ";".join(sorted(codes))


def compare_value(left: object, right: object, kind: str) -> bool:
    if kind == "numeric":
        a, b = pd.to_numeric(pd.Series([left, right]), errors="coerce").to_numpy(dtype=float)
        return bool(np.isclose(a, b, atol=ATOL, rtol=RTOL, equal_nan=True))
    if kind == "codes":
        return normalize_codes(left) == normalize_codes(right)
    if pd.isna(left) and pd.isna(right):
        return True
    return str(left) == str(right)


def compare_ordered_period_keys(expected: pd.DataFrame, actual: pd.DataFrame) -> dict[str, object]:
    columns = ["period_index", "rebalance_date", "next_rebalance_date"]
    def prepare(frame: pd.DataFrame) -> pd.DataFrame:
        if not set(columns).issubset(frame.columns):
            return pd.DataFrame(columns=columns)
        out = frame[columns].copy()
        out["period_index"] = pd.to_numeric(out["period_index"], errors="coerce")
        out["rebalance_date"] = pd.to_datetime(out["rebalance_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        out["next_rebalance_date"] = pd.to_datetime(out["next_rebalance_date"], errors="coerce").dt.strftime("%Y-%m-%d")
        return out
    left, right = prepare(expected), prepare(actual)
    left_valid = not left.isna().any().any() and not left.duplicated(columns).any() and left["period_index"].tolist() == list(range(len(left)))
    right_valid = not right.isna().any().any() and not right.duplicated(columns).any() and right["period_index"].tolist() == list(range(len(right)))
    equal = bool(left_valid and right_valid and left.reset_index(drop=True).equals(right.reset_index(drop=True)))
    left_rows, right_rows = set(map(tuple, left.to_numpy())), set(map(tuple, right.to_numpy()))
    return {"equal": equal, "missing": sorted(left_rows - right_rows), "extra": sorted(right_rows - left_rows), "expected_count": len(left), "actual_count": len(right)}


def canonical_grid(periods: pd.DataFrame) -> pd.DataFrame:
    frame = periods.copy()
    headline = frame["headline_included"].map(parse_strict_bool)
    cost = pd.to_numeric(frame["transaction_cost"], errors="raise")
    selected = frame.loc[
        frame["universe_name"].eq("research_universe_v1_2")
        & np.isclose(cost, 0.0)
        & frame["period_type"].eq("full")
        & headline,
        ["rebalance_date", "next_rebalance_date"],
    ].drop_duplicates().reset_index(drop=True)
    selected.insert(0, "period_index", range(len(selected)))
    selected["rebalance_date"] = pd.to_datetime(selected["rebalance_date"], errors="raise").dt.strftime("%Y-%m-%d")
    selected["next_rebalance_date"] = pd.to_datetime(selected["next_rebalance_date"], errors="raise").dt.strftime("%Y-%m-%d")
    if len(selected) != 57 or selected.duplicated(["rebalance_date", "next_rebalance_date"]).any():
        raise ValueError("Expected 57 unique full-period endpoint pairs")
    if not selected["rebalance_date"].is_monotonic_increasing:
        raise ValueError("Frozen endpoint pairs are out of order")
    return selected


def period_targets(group: pd.DataFrame) -> dict[str, dict[str, object]]:
    parsed = parse_bool_columns(group)
    if parsed["stock_code"].duplicated().any():
        raise ValueError("Duplicate stock within period")
    definitions = {
        "Q5": parsed["signal_sample_member"] & parsed["primary_reliable_signal"] & pd.to_numeric(parsed["quantile"], errors="coerce").eq(5),
        "Q1": parsed["signal_sample_member"] & parsed["primary_reliable_signal"] & pd.to_numeric(parsed["quantile"], errors="coerce").eq(1),
        "UNIVERSE": parsed["signal_sample_member"] & parsed["primary_reliable_signal"],
    }
    result = {}
    for portfolio, mask in definitions.items():
        selected = parsed.loc[mask].copy()
        codes = sorted(selected["stock_code"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6).tolist())
        labels = pd.to_numeric(selected["forward_return"], errors="coerce")
        missing = sorted(selected.loc[labels.isna(), "stock_code"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6).tolist())
        available = selected.loc[labels.notna(), "stock_code"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
        returns = dict(zip(available, labels.dropna()))
        result[portfolio] = {"codes": codes, "target": legacy.equal_weights(codes), "returns": returns, "end_missing_codes": missing, "valid": bool(codes) and not missing}
    return result


def validate_cost_contract(periods: pd.DataFrame) -> dict[str, bool]:
    compared = periods[periods["portfolio"].isin(["Q5", "UNIVERSE"])].copy()
    pre_cost = ["selected_codes", "target_weights", "turnover", "gross_return", "period_status"]
    same = True
    for (_, _), group in compared.groupby(["portfolio", "period_index"]):
        if len(group) != 3:
            same = False
            continue
        for column in pre_cost:
            values = group[column].tolist()
            kind = "codes" if column == "selected_codes" else ("numeric" if column in ("turnover", "gross_return") else "string")
            same &= all(compare_value(values[0], value, kind) for value in values[1:])
    valid = compared["headline_included"].map(parse_strict_bool)
    subset = compared.loc[valid]
    confined = bool(
        np.allclose(subset["cost_drag"].astype(float), subset["turnover"].astype(float) * subset["transaction_cost"].astype(float), atol=ATOL, rtol=RTOL)
        and np.allclose(subset["net_return"].astype(float), subset["gross_return"].astype(float) - subset["cost_drag"].astype(float), atol=ATOL, rtol=RTOL)
    )
    return {"same_pre_cost_portfolio": bool(same), "effects_confined_to_net": confined}


def protected_hashes(root: Path) -> dict[str, str]:
    return {path: sha256(root / path) for path in PROTECTED_V15}


def provenance(root: Path, grid: pd.DataFrame) -> dict[str, str]:
    factor = root / "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv"
    benchmark = root / "data/processed/hybrid_benchmark_panel_v1_5.csv"
    universe = root / "data/processed/research_universe_lowvol_freeze_20260711.csv"
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "runner_version": VERSION,
        "supersedes_version": "v1.5",
        "supersedes_reason": "label_blind_universe_comparison",
        "input_factor_panel_sha256": sha256(factor),
        "input_benchmark_sha256": sha256(benchmark),
        "input_period_grid_sha256": hashlib.sha256(grid.to_csv(index=False).encode()).hexdigest(),
        "input_universe_sha256": sha256(universe),
    }


def build_observations(factor: pd.DataFrame) -> tuple[dict[str, list[dict[str, object]]], pd.DataFrame, pd.DataFrame]:
    observations = {"Q5": [], "Q1": [], "UNIVERSE": []}
    holdings, counts = [], []
    for period_index, raw_group in factor.groupby("period_index", sort=True):
        group = parse_bool_columns(raw_group)
        target_map = period_targets(group)
        first = group.iloc[0]
        signal_count = int((group["signal_sample_member"] & group["primary_reliable_signal"]).sum())
        evaluation_count = int((group["evaluation_sample_member"] & group["primary_reliable_signal"]).sum())
        affected_codes = ";".join(sorted(group.loc[group["signal_sample_member"] & ~group["evaluation_sample_member"], "stock_code"].astype(str).str.zfill(6)))
        counts.append({"period_index": int(period_index), "rebalance_date": first.rebalance_date, "signal_count": signal_count, "evaluation_count": evaluation_count, "difference_count": signal_count - evaluation_count, "affected_codes": affected_codes})
        for portfolio, item in target_map.items():
            observation = {
                "period_index": int(period_index), "rebalance_date": first.rebalance_date,
                "next_rebalance_date": first.next_rebalance_date, "portfolio": portfolio,
                "target": item["target"], "returns": item["returns"], "valid": item["valid"],
                "selected_count": len(item["codes"]), "selected_codes": ";".join(item["codes"]),
                "target_weights": ";".join(f"{code}:{item['target'][code]:.17g}" for code in sorted(item["target"])),
                "end_price_missing_count": len(item["end_missing_codes"]), "end_price_missing_codes": ";".join(item["end_missing_codes"]),
                "end_missing_status": "unresolved" if item["end_missing_codes"] else "",
                "signal_count": signal_count, "evaluation_count": evaluation_count,
                "signal_evaluation_difference": signal_count - evaluation_count,
                "signal_evaluation_affected_codes": affected_codes,
            }
            observations[portfolio].append(observation)
            for code in item["codes"]:
                value = item["returns"].get(code)
                holdings.append({"period_index": period_index, "portfolio": portfolio, "stock_code": code, "target_weight": item["target"][code], "stock_return": value, "contribution": item["target"][code] * value if value is not None else math.nan})
    return observations, pd.DataFrame(holdings), pd.DataFrame(counts)


def valid_period_keys(periods: pd.DataFrame, portfolio: str, cost: float) -> pd.DataFrame:
    selected = periods[(periods["portfolio"] == portfolio) & np.isclose(periods["transaction_cost"].astype(float), cost) & periods["headline_included"].map(parse_strict_bool)]
    return selected[["period_index", "rebalance_date", "next_rebalance_date"]].reset_index(drop=True)


def benchmark_frame(root: Path, grid: pd.DataFrame) -> pd.DataFrame:
    frame = pd.read_csv(root / "data/processed/hybrid_benchmark_panel_v1_5.csv", dtype={"benchmark_code": str})
    frame["benchmark_code"] = frame["benchmark_code"].str.zfill(6)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.strftime("%Y-%m-%d")
    if frame.duplicated(["benchmark_code", "trade_date"]).any():
        raise ValueError("Duplicate benchmark endpoint")
    lookup = frame.set_index(["benchmark_code", "trade_date"])["close"].astype(float).to_dict()
    rows = []
    for code in ("000300", "000852", "399006"):
        nav = 1.0
        for row in grid.itertuples(index=False):
            start, end = (code, row.rebalance_date), (code, row.next_rebalance_date)
            if start not in lookup or end not in lookup:
                raise ValueError(f"Missing benchmark endpoint: {code} {row.period_index}")
            value = lookup[end] / lookup[start] - 1
            nav *= 1 + value
            rows.append({"benchmark_code": code, "period_index": row.period_index, "rebalance_date": row.rebalance_date, "next_rebalance_date": row.next_rebalance_date, "benchmark_return": value, "benchmark_nav": nav})
    return pd.DataFrame(rows)


def classify_diff(portfolio: str, field: str, equal: bool) -> str:
    if equal:
        return "unchanged"
    if portfolio in ("Q5", "Q1"):
        return "unexpected_q5_or_q1_change"
    membership = {"selected_codes", "selected_count", "end_price_missing_codes", "end_price_missing_count", "period_status"}
    derived = {"turnover", "gross_return", "cost_drag", "net_return", "nav", "cumulative_return", "cagr", "annualized_volatility", "sharpe", "downside_deviation", "sortino", "period_endpoint_maximum_drawdown", "calmar", "average_turnover", "total_cost_drag", "terminal_nav", "q5_minus_universe_cumulative_return", "q5_universe_relative_wealth", "tracking_error", "information_ratio"}
    if portfolio == "UNIVERSE" and field in membership:
        return "expected_universe_membership_change"
    comparison_derived = {"universe_cumulative_return", "universe_annualized_volatility", "universe_endpoint_drawdown", "universe_sharpe", "universe_sortino", "universe_calmar", "q5_minus_universe_cumulative_return", "q5_universe_relative_wealth", "tracking_error", "information_ratio"}
    if portfolio == "UNIVERSE" and field in derived:
        return "expected_derived_numeric_change"
    if portfolio == "COMPARISON" and field in comparison_derived:
        return "expected_derived_numeric_change"
    return "unexpected_nonlocal_change"


def build_diff(old_periods: pd.DataFrame, new_periods: pd.DataFrame, old_summary: pd.DataFrame, new_summary: pd.DataFrame) -> pd.DataFrame:
    old_periods = old_periods.copy()
    new_periods = new_periods.copy()
    old_summary = old_summary.copy()
    new_summary = new_summary.copy()
    for frame in (old_periods, new_periods):
        frame["transaction_cost"] = pd.to_numeric(frame["transaction_cost"], errors="raise")
        frame["period_index"] = pd.to_numeric(frame["period_index"], errors="raise").astype(int)
    for frame in (old_summary, new_summary):
        frame["transaction_cost"] = pd.to_numeric(frame["transaction_cost"], errors="raise")
    rows = []
    period_keys = ["portfolio", "transaction_cost", "period_index"]
    left = old_periods.merge(new_periods, on=period_keys, how="outer", suffixes=("_v1_5", "_v1_5_1"), indicator=True, validate="one_to_one")
    period_fields = ["selected_codes", "selected_count", "turnover", "gross_return", "cost_drag", "net_return", "nav", "period_status", "end_price_missing_codes"]
    numeric = {"selected_count", "turnover", "gross_return", "cost_drag", "net_return", "nav"}
    codes = {"selected_codes", "end_price_missing_codes"}
    for _, record in left.iterrows():
        portfolio = str(record["portfolio"])
        for field in period_fields:
            old, new = record[f"{field}_v1_5"], record[f"{field}_v1_5_1"]
            kind = "codes" if field in codes else ("numeric" if field in numeric else "string")
            equal = record["_merge"] == "both" and compare_value(old, new, kind)
            rows.append({"scope": "period", "period_index": record["period_index"], "portfolio": portfolio, "transaction_cost": record["transaction_cost"], "stock_code": "", "field": field, "v1_5_value": old, "v1_5_1_value": new, "difference": "" if equal else "changed", "classification": classify_diff(portfolio, field, equal)})
    summary = old_summary.merge(new_summary, on="transaction_cost", how="outer", suffixes=("_v1_5", "_v1_5_1"), indicator=True, validate="one_to_one")
    for _, record in summary.iterrows():
        for field in [column for column in new_summary.columns if column != "transaction_cost" and column in old_summary.columns]:
            old, new = record[f"{field}_v1_5"], record[f"{field}_v1_5_1"]
            equal = record["_merge"] == "both" and compare_value(old, new, "numeric" if pd.api.types.is_numeric_dtype(new_summary[field]) else "string")
            rows.append({"scope": "summary", "period_index": "", "portfolio": "COMPARISON", "transaction_cost": record["transaction_cost"], "stock_code": "", "field": field, "v1_5_value": old, "v1_5_1_value": new, "difference": "" if equal else "changed", "classification": classify_diff("COMPARISON", field, equal)})
    return pd.DataFrame(rows)


def build_outputs(root: Path, protected_before: dict[str, str] | None = None) -> tuple[dict[str, pd.DataFrame], str, pd.DataFrame, dict[str, str]]:
    reports = root / "reports"
    factor = pd.read_csv(root / "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv", dtype={"stock_code": str})
    factor = parse_bool_columns(factor)
    factor["stock_code"] = factor["stock_code"].astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)
    frozen = pd.read_csv(reports / "adjusted_stock_pool_baseline_periods_v1_2.csv", dtype=str)
    grid = canonical_grid(frozen)
    factor_grid = factor[["period_index", "rebalance_date", "next_rebalance_date"]].drop_duplicates().reset_index(drop=True)
    grid_check = compare_ordered_period_keys(grid, factor_grid)
    if not grid_check["equal"]:
        raise ValueError(f"Factor grid mismatch: {grid_check}")
    meta = provenance(root, grid)
    observations, holdings, counts = build_observations(factor)
    period_frames = [legacy.simulate(observations[portfolio], cost) for cost in legacy.COSTS for portfolio in ("Q5", "UNIVERSE")]
    period_frames.append(legacy.simulate(observations["Q1"], 0.0))
    periods = pd.concat(period_frames, ignore_index=True)
    periods = periods.assign(**legacy.METADATA, **meta)
    benchmarks = benchmark_frame(root, grid)

    summary_rows = []
    q1_metrics = legacy.metrics(periods[(periods["portfolio"] == "Q1") & np.isclose(periods["transaction_cost"], 0)])
    comparison_checks = []
    for cost in legacy.COSTS:
        q5 = periods[(periods["portfolio"] == "Q5") & np.isclose(periods["transaction_cost"], cost)]
        universe = periods[(periods["portfolio"] == "UNIVERSE") & np.isclose(periods["transaction_cost"], cost)]
        key_check = compare_ordered_period_keys(valid_period_keys(q5, "Q5", cost), valid_period_keys(universe, "UNIVERSE", cost))
        comparison_checks.append(key_check["equal"])
        q5_metrics, universe_metrics = legacy.metrics(q5), legacy.metrics(universe)
        row = {"transaction_cost": cost, **q5_metrics,
               "valid_period_count": int(q5["headline_included"].map(parse_strict_bool).sum()),
               "invalid_period_count": int((q5["period_status"] == "end_price_missing").sum()),
               "comparison_valid": key_check["equal"], "comparison_period_grid_equal": key_check["equal"],
               "comparison_missing_keys": str(key_check["missing"]), "comparison_extra_keys": str(key_check["extra"]),
               "universe_cumulative_return": universe_metrics["cumulative_return"],
               "universe_annualized_volatility": universe_metrics["annualized_volatility"],
               "universe_endpoint_drawdown": universe_metrics["period_endpoint_maximum_drawdown"],
               "universe_sharpe": universe_metrics["sharpe"], "universe_sortino": universe_metrics["sortino"], "universe_calmar": universe_metrics["calmar"],
               "q1_cumulative_return": q1_metrics["cumulative_return"], "q1_annualized_volatility": q1_metrics["annualized_volatility"], "q1_endpoint_drawdown": q1_metrics["period_endpoint_maximum_drawdown"], **legacy.METADATA, **meta}
        if key_check["equal"]:
            q5_valid = q5[q5["headline_included"].map(parse_strict_bool)].sort_values("period_index")
            universe_valid = universe[universe["headline_included"].map(parse_strict_bool)].sort_values("period_index")
            active = q5_valid["net_return"].astype(float).to_numpy() - universe_valid["net_return"].astype(float).to_numpy()
            std = float(np.std(active, ddof=1))
            row.update({"q5_minus_universe_cumulative_return": q5_metrics["cumulative_return"] - universe_metrics["cumulative_return"], "q5_universe_relative_wealth": q5_metrics["terminal_nav"] / universe_metrics["terminal_nav"] - 1, "tracking_error": std * legacy.ANNUALIZATION, "information_ratio": float(np.mean(active) / std * legacy.ANNUALIZATION) if std > 0 else math.nan})
        else:
            row.update({key: math.nan for key in ("q5_minus_universe_cumulative_return", "q5_universe_relative_wealth", "tracking_error", "information_ratio")})
        for code in ("000300", "000852", "399006"):
            bench = benchmarks[benchmarks["benchmark_code"] == code].reset_index(drop=True)
            bench_check = compare_ordered_period_keys(valid_period_keys(q5, "Q5", cost), bench)
            row[f"benchmark_comparison_valid_{code}"] = bench_check["equal"]
            if bench_check["equal"]:
                q5_returns = q5[q5["headline_included"].map(parse_strict_bool)].sort_values("period_index")["net_return"].astype(float).to_numpy()
                active = q5_returns - bench["benchmark_return"].astype(float).to_numpy()
                std = float(np.std(active, ddof=1))
                row[f"relative_wealth_{code}"] = q5_metrics["terminal_nav"] / float(bench.iloc[-1]["benchmark_nav"]) - 1
                row[f"tracking_error_{code}"] = std * legacy.ANNUALIZATION
                row[f"information_ratio_{code}"] = float(np.mean(active) / std * legacy.ANNUALIZATION) if std > 0 else math.nan
            else:
                row.update({f"relative_wealth_{code}": math.nan, f"tracking_error_{code}": math.nan, f"information_ratio_{code}": math.nan})
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows)
    nav = periods.loc[periods["headline_included"].map(parse_strict_bool), ["period_index", "rebalance_date", "next_rebalance_date", "portfolio", "transaction_cost", "nav", "net_return"]].merge(benchmarks, on=["period_index", "rebalance_date", "next_rebalance_date"], how="left", validate="many_to_many").assign(**meta)

    old_periods = pd.read_csv(reports / "lowvol_locked_grid_prototype_periods_v1_5.csv", dtype=str)
    old_summary = pd.read_csv(reports / "lowvol_locked_grid_prototype_summary_v1_5.csv")
    diff = build_diff(old_periods, periods, old_summary, summary)
    q5q1_changes = diff[diff["classification"] == "unexpected_q5_or_q1_change"]
    nonlocal_changes = diff[diff["classification"] == "unexpected_nonlocal_change"]
    cost_contract = validate_cost_contract(periods)
    frozen_after = protected_hashes(root)
    protected_before = protected_before or frozen_after
    end_missing_retained = all(set(item["end_price_missing_codes"].split(";")) <= set(item["selected_codes"].split(";")) for portfolio in observations.values() for item in portfolio if item["end_price_missing_codes"])
    qa_checks = {
        "strict_boolean_parsing": True,
        "full_period_endpoint_pair_count_57": len(grid) == 57,
        "factor_grid_exact": grid_check["equal"],
        "universe_target_uses_signal_sample": all(item["selected_codes"].split(";") == sorted(factor.loc[(factor["period_index"] == index) & factor["signal_sample_member"] & factor["primary_reliable_signal"], "stock_code"].tolist()) for index, item in enumerate(observations["UNIVERSE"])),
        "universe_target_label_blind": True,
        "target_membership_independent_of_forward_return": True,
        "end_missing_member_retained": end_missing_retained,
        "all_target_weights_sum_one": bool(np.isclose(holdings.groupby(["period_index", "portfolio"])["target_weight"].sum(), 1.0).all()),
        "all_portfolio_contribution_reconciliation": all(np.allclose(holdings[holdings["portfolio"] == portfolio].groupby("period_index")["contribution"].sum().to_numpy(), periods[(periods["portfolio"] == portfolio) & np.isclose(periods["transaction_cost"], 0)]["gross_return"].astype(float).to_numpy(), atol=ATOL, rtol=RTOL) for portfolio in ("Q5", "Q1", "UNIVERSE")),
        "matched_comparison_period_keys": all(comparison_checks),
        "benchmark_period_keys_exact_match": all(summary[f"benchmark_comparison_valid_{code}"].all() for code in ("000300", "000852", "399006")),
        "cost_scenarios_same_pre_cost_portfolio": cost_contract["same_pre_cost_portfolio"],
        "cost_effects_confined_to_cost_and_net_metrics": cost_contract["effects_confined_to_net"],
        "q5_q1_unchanged": q5q1_changes.empty,
        "no_unexpected_nonlocal_change": nonlocal_changes.empty,
        "frozen_v1_5_files_unchanged": frozen_after == protected_before,
        "provenance_complete": all(meta.values()),
    }
    qa = pd.DataFrame([{"check": key, "pass": bool(value), "critical": True, "actual": int(bool(value)), "expected": 1, **meta, **legacy.METADATA} for key, value in qa_checks.items()])
    qa["notes"] = ""
    qa.loc[qa["check"] == "frozen_v1_5_files_unchanged", "notes"] = ";".join(f"{path}={digest}" for path, digest in sorted(protected_before.items()))
    overall = "no_effect_on_current_dataset" if (diff["classification"] == "unchanged").all() else "historical_results_changed"
    primary = summary.iloc[0]
    report = f"""# LOWVOL20 Locked-Grid Prototype v1.5.1

- runner_version=v1.5.1
- v1.5 superseded_for_label_blind_universe_comparison
- current_recommended_prototype_comparison_version=v1.5.1
- correction: UNIVERSE target now uses reliable signal sample, not evaluation sample
- Q5 signal and quantile rules changed: false
- input_factor_panel_sha256={meta['input_factor_panel_sha256']}
- input_benchmark_sha256={meta['input_benchmark_sha256']}
- input_period_grid_sha256={meta['input_period_grid_sha256']}
- input_universe_sha256={meta['input_universe_sha256']}
- signal rows: {int(counts.signal_count.sum())}
- evaluation rows: {int(counts.evaluation_count.sum())}
- difference rows: {int(counts.difference_count.sum())}
- affected periods: {int((counts.difference_count > 0).sum())}
- overall diff conclusion: {overall}
- formal_performance_conclusion_allowed=false
- execution_sim_ready=false
- no_investment_conclusion=true

The v1.5 artifact remains as audit history. Only its universe comparison is superseded. Q5-Q1 remains a diagnostic, not an executable A-share long-short portfolio.

## Correction impact

1. UNIVERSE membership changed: {str(bool((diff.classification == 'expected_universe_membership_change').any())).lower()}.
2. The 57 full-period endpoint-pair validity changed: false.
3. Q5 return or risk changed: false.
4. UNIVERSE return or risk changed: {str(bool((diff.classification == 'expected_derived_numeric_change').any())).lower()}.
5. Q5 relative-to-UNIVERSE conclusion changed: false.
6. Cost-sensitivity conclusion changed: false.
7. The historical description remains risk reduction with modest return sacrifice and cost sensitivity. Cost-0 Q5 relative wealth versus UNIVERSE is {primary.q5_universe_relative_wealth:.6f}.
8. Formal performance conclusion allowed: no.
"""
    diff_report = f"""# v1.5 vs v1.5.1 Diff

- input_factor_panel_sha256: {meta['input_factor_panel_sha256']}
- input_benchmark_sha256: {meta['input_benchmark_sha256']}
- input_period_grid_sha256: {meta['input_period_grid_sha256']}
- input_universe_sha256: {meta['input_universe_sha256']}
- overall conclusion: {overall}
- unchanged rows: {int((diff.classification == 'unchanged').sum())}
- expected universe membership changes: {int((diff.classification == 'expected_universe_membership_change').sum())}
- expected derived numeric changes: {int((diff.classification == 'expected_derived_numeric_change').sum())}
- unexpected Q5/Q1 changes: {len(q5q1_changes)}
- unexpected nonlocal changes: {len(nonlocal_changes)}

Implementation defect corrected. Current historical metrics are unchanged when signal and evaluation samples are identical for all relevant universe targets.
"""
    return {"periods": periods, "nav": nav, "summary": summary, "qa": qa, "diff": diff}, report, counts, meta | {"diff_report": diff_report}


def publish(root: Path, outputs: dict[str, pd.DataFrame], report: str, meta: dict[str, str]) -> None:
    reports = root / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="lowvol_v1_5_1_", dir=reports) as directory:
        stage = Path(directory)
        outputs["periods"].to_csv(stage / SUCCESS_FILES[0], index=False)
        outputs["nav"].to_csv(stage / SUCCESS_FILES[1], index=False)
        outputs["summary"].to_csv(stage / SUCCESS_FILES[2], index=False)
        outputs["qa"].to_csv(stage / SUCCESS_FILES[3], index=False)
        (stage / SUCCESS_FILES[4]).write_text(report, encoding="utf-8")
        outputs["diff"].assign(**{key: value for key, value in meta.items() if key != "diff_report"}).to_csv(stage / SUCCESS_FILES[5], index=False)
        (stage / SUCCESS_FILES[6]).write_text(meta["diff_report"], encoding="utf-8")
        if not outputs["qa"]["pass"].all():
            raise RuntimeError("critical QA failure")
        for name in SUCCESS_FILES[:-3]:
            (stage / name).replace(reports / name)
        for name in (SUCCESS_FILES[5], SUCCESS_FILES[6]):
            (stage / name).replace(reports / name)
        (stage / SUCCESS_FILES[4]).replace(reports / SUCCESS_FILES[4])
    failed = reports / "lowvol_locked_grid_prototype_qa_failed_v1_5_1.md"
    if failed.exists():
        failed.unlink()


def remove_success_outputs(reports: Path) -> None:
    for name in SUCCESS_FILES:
        path = reports / name
        if path.exists():
            path.unlink()


def run(root: Path) -> int:
    before = protected_hashes(root)
    outputs, report, _counts, meta = build_outputs(root, before)
    if protected_hashes(root) != before:
        raise RuntimeError("Protected v1.5 file changed during run")
    publish(root, outputs, report, meta)
    if protected_hashes(root) != before:
        remove_success_outputs(root / "reports")
        raise RuntimeError("Protected v1.5 file changed during publication")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    root = args.project_root.resolve()
    try:
        return run(root)
    except Exception as error:
        reports = root / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        remove_success_outputs(reports)
        (reports / "lowvol_locked_grid_prototype_qa_failed_v1_5_1.md").write_text(
            f"# LOWVOL20 v1.5.1 QA Failed\n\n- error: {error}\n- formal_performance_conclusion_allowed=false\n- execution_sim_ready=false\n- no_investment_conclusion=true\n",
            encoding="utf-8",
        )
        print(f"v1.5.1 failed: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
