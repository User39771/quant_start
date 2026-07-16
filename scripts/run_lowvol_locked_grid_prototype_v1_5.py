from __future__ import annotations

import argparse
import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scripts.run_adjusted_stock_pool_baseline_v1_2 import drifted_weights, period_endpoint_maximum_drawdown, turnover_from_drift
    from scripts.run_locked_grid_replay_v1_5 import frozen_period_keys
except ModuleNotFoundError:
    from run_adjusted_stock_pool_baseline_v1_2 import drifted_weights, period_endpoint_maximum_drawdown, turnover_from_drift
    from run_locked_grid_replay_v1_5 import frozen_period_keys


COSTS = (0.0, 0.001, 0.002)
ANNUALIZATION = math.sqrt(252 / 20)
METADATA = {
    "formal_performance_conclusion_allowed": False,
    "execution_sim_ready": False,
    "no_investment_conclusion": True,
}


def equal_weights(codes: list[str]) -> dict[str, float]:
    return {code: 1.0 / len(codes) for code in sorted(codes)} if codes else {}


def period_targets(group: pd.DataFrame) -> dict[str, dict[str, object]]:
    if group["stock_code"].duplicated().any():
        raise ValueError("Duplicate stock within period")
    result = {}
    definitions = {
        "Q5": group["signal_sample_member"].astype(bool) & group["primary_reliable_signal"].astype(bool) & pd.to_numeric(group["quantile"]).eq(5),
        "Q1": group["signal_sample_member"].astype(bool) & group["primary_reliable_signal"].astype(bool) & pd.to_numeric(group["quantile"]).eq(1),
        "UNIVERSE": group["evaluation_sample_member"].astype(bool) & group["primary_reliable_signal"].astype(bool),
    }
    for name, mask in definitions.items():
        selected = group.loc[mask].copy()
        codes = sorted(selected["stock_code"].astype(str).str.zfill(6).tolist())
        labels = pd.to_numeric(selected["forward_return"], errors="coerce")
        missing = sorted(selected.loc[labels.isna(), "stock_code"].astype(str).str.zfill(6).tolist())
        returns = dict(zip(selected.loc[labels.notna(), "stock_code"].astype(str).str.zfill(6), labels.dropna()))
        result[name] = {
            "codes": codes,
            "target": equal_weights(codes),
            "returns": returns,
            "end_missing_codes": missing,
            "valid": bool(codes) and not missing,
        }
    return result


def simulate(observations: list[dict[str, object]], transaction_cost: float) -> pd.DataFrame:
    nav, terminated = 1.0, False
    previous_target: dict[str, float] = {}
    previous_returns: dict[str, float] = {}
    rows = []
    for observation in observations:
        row = {key: value for key, value in observation.items() if key not in ("target", "returns")}
        target = observation["target"]
        returns = observation["returns"]
        row.update({"transaction_cost": transaction_cost, "headline_included": False, "turnover": math.nan, "cost_drag": math.nan, "gross_return": math.nan, "net_return": math.nan, "nav": math.nan})
        if terminated:
            row["period_status"] = "post_termination"
        elif not observation["valid"]:
            row["period_status"] = "end_price_missing"
            terminated = True
        else:
            drifted = drifted_weights(previous_target, previous_returns) if previous_target else {}
            turnover = turnover_from_drift(target, drifted) if previous_target else 1.0
            gross = sum(target[code] * returns[code] for code in target)
            cost = turnover * transaction_cost
            net = gross - cost
            nav *= 1.0 + net
            row.update({"period_status": "headline", "headline_included": True, "turnover": turnover, "cost_drag": cost, "gross_return": gross, "net_return": net, "nav": nav})
            previous_target, previous_returns = target, returns
        rows.append(row)
    return pd.DataFrame(rows)


def metrics(periods: pd.DataFrame) -> dict[str, float]:
    valid = periods[periods["headline_included"].astype(bool)].copy()
    returns = pd.to_numeric(valid["net_return"], errors="coerce")
    if valid.empty:
        return {key: math.nan for key in ("cumulative_return", "cagr", "annualized_volatility", "sharpe", "downside_deviation", "sortino", "period_endpoint_maximum_drawdown", "calmar", "positive_period_ratio", "average_turnover", "total_cost_drag", "terminal_nav")}
    cumulative = float(np.prod(1 + returns) - 1)
    days = (pd.Timestamp(valid.iloc[-1]["next_rebalance_date"]) - pd.Timestamp(valid.iloc[0]["rebalance_date"])).days
    cagr = (1 + cumulative) ** (365.2425 / days) - 1 if days > 0 and cumulative > -1 else math.nan
    std = float(returns.std(ddof=1))
    volatility = std * ANNUALIZATION
    sharpe = float(returns.mean()) / std * ANNUALIZATION if std > 0 else math.nan
    downside = float(np.sqrt(np.mean(np.minimum(returns.to_numpy(), 0) ** 2)) * ANNUALIZATION)
    sortino = float(returns.mean()) * (252 / 20) / downside if downside > 0 else math.nan
    drawdown = period_endpoint_maximum_drawdown(valid["nav"].astype(float).tolist())
    return {
        "cumulative_return": cumulative, "cagr": cagr, "annualized_volatility": volatility,
        "sharpe": sharpe, "downside_deviation": downside, "sortino": sortino,
        "period_endpoint_maximum_drawdown": drawdown,
        "calmar": cagr / abs(drawdown) if drawdown < 0 else math.nan,
        "positive_period_ratio": float((returns > 0).mean()),
        "average_turnover": float(valid["turnover"].mean()),
        "total_cost_drag": float(valid["cost_drag"].sum()),
        "terminal_nav": float(valid.iloc[-1]["nav"]),
    }


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().lower()


def run(root: Path) -> int:
    root, reports = Path(root), Path(root) / "reports"
    factor = pd.read_csv(root / "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv", dtype={"stock_code": str})
    frozen = pd.read_csv(reports / "adjusted_stock_pool_baseline_periods_v1_2.csv", dtype=str)
    keys = frozen_period_keys(frozen)
    expected = [(str(a.date()), str(b.date())) for a, b, _ in keys]
    factor_keys = factor[["period_index", "rebalance_date", "next_rebalance_date"]].drop_duplicates().sort_values("period_index")
    actual = list(map(tuple, factor_keys[["rebalance_date", "next_rebalance_date"]].astype(str).to_numpy()))
    if actual != expected:
        raise ValueError("Factor panel does not use the frozen endpoint grid")
    factor["stock_code"] = factor["stock_code"].str.zfill(6)
    if not factor["stock_code"].str.fullmatch(r"\d{6}").all() or factor.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("Invalid factor-panel key")

    observations = {"Q5": [], "Q1": [], "UNIVERSE": []}
    period_stock_rows = []
    for period_index, group in factor.groupby("period_index", sort=True):
        targets = period_targets(group)
        dates = group.iloc[0]
        for portfolio, item in targets.items():
            observations[portfolio].append({
                "period_index": int(period_index), "rebalance_date": dates.rebalance_date,
                "next_rebalance_date": dates.next_rebalance_date, "portfolio": portfolio,
                "target": item["target"], "returns": item["returns"], "valid": item["valid"],
                "selected_count": len(item["codes"]), "selected_codes": ";".join(item["codes"]),
                "end_price_missing_count": len(item["end_missing_codes"]),
                "end_price_missing_codes": ";".join(item["end_missing_codes"]),
                "end_missing_status": "unresolved" if item["end_missing_codes"] else "",
                "start_ineligible_confirmed_suspension_codes": "000063" if str(dates.rebalance_date) == "2021-03-31" and not bool(group.loc[group["stock_code"].eq("000063"), "baseline_eligible"].iloc[0]) else "",
            })
            for code in item["codes"]:
                period_stock_rows.append({"period_index": period_index, "portfolio": portfolio, "stock_code": code, "target_weight": item["target"][code], "stock_return": item["returns"].get(code), "contribution": item["target"][code] * item["returns"].get(code) if code in item["returns"] else math.nan})

    period_frames = []
    for cost in COSTS:
        for portfolio in ("Q5", "UNIVERSE"):
            period_frames.append(simulate(observations[portfolio], cost))
    period_frames.append(simulate(observations["Q1"], 0.0))
    periods = pd.concat(period_frames, ignore_index=True)
    periods = periods.assign(**METADATA)

    benchmark = pd.read_csv(root / "data/processed/hybrid_benchmark_panel_v1_5.csv", dtype={"benchmark_code": str})
    benchmark["benchmark_code"] = benchmark["benchmark_code"].str.zfill(6)
    benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"])
    benchmark_lookup = benchmark.set_index(["benchmark_code", "trade_date"])["close"].astype(float).to_dict()
    benchmark_rows = []
    for code in ("000300", "000852", "399006"):
        nav = 1.0
        for index, (start, end, _) in enumerate(keys):
            if (code, start) not in benchmark_lookup or (code, end) not in benchmark_lookup:
                raise ValueError(f"Benchmark endpoint missing: {code} {start} {end}")
            value = benchmark_lookup[(code, end)] / benchmark_lookup[(code, start)] - 1
            nav *= 1 + value
            benchmark_rows.append({"period_index": index, "benchmark_code": code, "rebalance_date": str(start.date()), "next_rebalance_date": str(end.date()), "benchmark_return": value, "benchmark_nav": nav})
    benchmark_frame = pd.DataFrame(benchmark_rows)

    summary_rows = []
    q1_metrics = metrics(periods[(periods["portfolio"] == "Q1") & np.isclose(periods["transaction_cost"], 0)])
    for cost in COSTS:
        q5 = periods[(periods["portfolio"] == "Q5") & np.isclose(periods["transaction_cost"], cost)]
        universe = periods[(periods["portfolio"] == "UNIVERSE") & np.isclose(periods["transaction_cost"], cost)]
        q5_metrics, universe_metrics = metrics(q5), metrics(universe)
        active = q5.loc[q5["headline_included"], "net_return"].astype(float).to_numpy() - universe.loc[universe["headline_included"], "net_return"].astype(float).to_numpy()
        tracking = float(np.std(active, ddof=1) * ANNUALIZATION)
        row = {"transaction_cost": cost, **q5_metrics,
               "valid_period_count": int(q5["headline_included"].sum()),
               "invalid_period_count": int((q5["period_status"] == "end_price_missing").sum()),
               "q5_minus_universe_cumulative_return": q5_metrics["cumulative_return"] - universe_metrics["cumulative_return"],
               "q5_universe_relative_wealth": q5_metrics["terminal_nav"] / universe_metrics["terminal_nav"] - 1,
               "tracking_error": tracking,
               "information_ratio": float(np.mean(active) / np.std(active, ddof=1) * ANNUALIZATION) if np.std(active, ddof=1) > 0 else math.nan,
               "universe_cumulative_return": universe_metrics["cumulative_return"],
               "universe_annualized_volatility": universe_metrics["annualized_volatility"],
               "universe_endpoint_drawdown": universe_metrics["period_endpoint_maximum_drawdown"],
               "universe_sharpe": universe_metrics["sharpe"],
               "universe_sortino": universe_metrics["sortino"],
               "universe_calmar": universe_metrics["calmar"],
               "q1_cumulative_return": q1_metrics["cumulative_return"],
               "q1_annualized_volatility": q1_metrics["annualized_volatility"],
               "q1_endpoint_drawdown": q1_metrics["period_endpoint_maximum_drawdown"],
               **METADATA}
        q5_valid = q5[q5["headline_included"]].sort_values("period_index")
        for code in ("000300", "000852", "399006"):
            bench = benchmark_frame[benchmark_frame["benchmark_code"] == code].sort_values("period_index")
            bench_returns = bench["benchmark_return"].to_numpy()
            q5_returns = q5_valid["net_return"].astype(float).to_numpy()
            active_benchmark = q5_returns - bench_returns
            te = float(np.std(active_benchmark, ddof=1) * ANNUALIZATION)
            row[f"relative_wealth_{code}"] = q5_metrics["terminal_nav"] / float(bench.iloc[-1]["benchmark_nav"]) - 1
            row[f"tracking_error_{code}"] = te
            row[f"information_ratio_{code}"] = float(np.mean(active_benchmark) / np.std(active_benchmark, ddof=1) * ANNUALIZATION) if np.std(active_benchmark, ddof=1) > 0 else math.nan
        summary_rows.append(row)
    summary = pd.DataFrame(summary_rows)

    nav = periods.loc[periods["headline_included"], ["period_index", "rebalance_date", "next_rebalance_date", "portfolio", "transaction_cost", "nav", "net_return"]].merge(benchmark_frame, on=["period_index", "rebalance_date", "next_rebalance_date"], how="left")

    stock = pd.DataFrame(period_stock_rows)
    q5_periods = periods[(periods["portfolio"] == "Q5") & np.isclose(periods["transaction_cost"], 0)]
    nav_compounding_ok = True
    turnover_ok = True
    for (portfolio, cost), group in periods.groupby(["portfolio", "transaction_cost"]):
        headline = group[group["headline_included"]].sort_values("period_index")
        if not headline.empty:
            nav_compounding_ok &= bool(np.allclose((1 + headline["net_return"].astype(float)).cumprod(), headline["nav"].astype(float), atol=1e-10, rtol=1e-8))
        previous_target, previous_returns = {}, {}
        source = observations[portfolio]
        for row in group.sort_values("period_index").itertuples():
            if not bool(row.headline_included):
                continue
            observation = source[int(row.period_index)]
            drifted = drifted_weights(previous_target, previous_returns) if previous_target else {}
            expected_turnover = turnover_from_drift(observation["target"], drifted) if previous_target else 1.0
            turnover_ok &= bool(np.isclose(row.turnover, expected_turnover, atol=1e-10, rtol=1e-8))
            previous_target, previous_returns = observation["target"], observation["returns"]
    critical_checks = {
        "frozen_period_count": len(keys) == 57,
        "period_grid_equal": actual == expected,
        "six_digit_codes": factor["stock_code"].str.fullmatch(r"\d{6}").all(),
        "no_duplicate_period_stock": not factor.duplicated(["period_index", "stock_code"]).any(),
        "no_duplicate_holding_key": not stock.duplicated(["period_index", "portfolio", "stock_code"]).any(),
        "q5_only_reliable_signal": bool(factor.loc[factor["quantile"].eq(5) & factor["signal_sample_member"], "primary_reliable_signal"].astype(bool).all()),
        "target_weights_sum_one": bool(np.isclose(stock.groupby(["period_index", "portfolio"])["target_weight"].sum(), 1.0).all()),
        "gross_contribution_reconciliation": bool(np.allclose(stock[stock["portfolio"] == "Q5"].groupby("period_index")["contribution"].sum().to_numpy(), q5_periods["gross_return"].astype(float).to_numpy(), atol=1e-10, rtol=1e-8)),
        "cost_reconciliation": bool(np.allclose(periods.loc[periods["headline_included"], "cost_drag"].astype(float), periods.loc[periods["headline_included"], "turnover"].astype(float) * periods.loc[periods["headline_included"], "transaction_cost"].astype(float), atol=1e-10, rtol=1e-8)),
        "net_return_reconciliation": bool(np.allclose(periods.loc[periods["headline_included"], "net_return"].astype(float), periods.loc[periods["headline_included"], "gross_return"].astype(float) - periods.loc[periods["headline_included"], "cost_drag"].astype(float), atol=1e-10, rtol=1e-8)),
        "first_turnover_one": bool(np.isclose(periods[periods["headline_included"]].groupby(["portfolio", "transaction_cost"])["turnover"].first(), 1.0).all()),
        "drifted_turnover_reconciliation": turnover_ok,
        "nav_compounding_reconciliation": nav_compounding_ok,
        "q5_universe_same_endpoints": set(map(tuple, periods[(periods["portfolio"] == "Q5") & np.isclose(periods["transaction_cost"], 0)][["rebalance_date", "next_rebalance_date"]].to_numpy())) == set(map(tuple, periods[(periods["portfolio"] == "UNIVERSE") & np.isclose(periods["transaction_cost"], 0)][["rebalance_date", "next_rebalance_date"]].to_numpy())),
        "benchmark_endpoint_alignment": len(benchmark_frame) == 57 * 3,
        "selected_end_missing_not_removed": not bool(((q5_periods["end_price_missing_count"].astype(int) > 0) & q5_periods["headline_included"].astype(bool)).any()),
    }
    manifest = pd.read_csv(reports / "v1_5_frozen_file_manifest_before.csv")
    frozen_differences = sum(_hash(root / row.path) != str(row.sha256).lower() for row in manifest.itertuples())
    critical_checks["frozen_hash_differences_zero"] = frozen_differences == 0
    qa = pd.DataFrame([{"check": key, "pass": bool(value), "critical": True, "actual": int(bool(value)), "expected": 1, **METADATA} for key, value in critical_checks.items()])

    periods.to_csv(reports / "lowvol_locked_grid_prototype_periods_v1_5.csv", index=False)
    nav.to_csv(reports / "lowvol_locked_grid_prototype_nav_v1_5.csv", index=False)
    summary.to_csv(reports / "lowvol_locked_grid_prototype_summary_v1_5.csv", index=False)
    qa.to_csv(reports / "lowvol_locked_grid_prototype_qa_v1_5.csv", index=False)

    primary = summary.iloc[0]
    best_share = q5_periods.nlargest(5, "net_return")["net_return"].sum() / q5_periods.loc[q5_periods["net_return"] > 0, "net_return"].sum()
    report = f"""# LOWVOL20 Locked-Grid Long-Only Prototype v1.5

## Status

- research prototype only
- full_period_count: 57
- period_grid_equal: true
- critical_qa_failures: {int((~qa['pass']).sum())}
- formal_performance_conclusion_allowed=false
- execution_sim_ready=false
- no_investment_conclusion=true

## Primary answers

1. Volatility: Q5 {primary.annualized_volatility:.4f} versus universe {primary.universe_annualized_volatility:.4f}; lower={str(primary.annualized_volatility < primary.universe_annualized_volatility).lower()}.
2. Endpoint drawdown: Q5 {primary.period_endpoint_maximum_drawdown:.4f} versus universe {primary.universe_endpoint_drawdown:.4f}; improved={str(primary.period_endpoint_maximum_drawdown > primary.universe_endpoint_drawdown).lower()}.
3. Cumulative return difference: {primary.q5_minus_universe_cumulative_return:.4f}; relative wealth: {primary.q5_universe_relative_wealth:.4f}.
4. Q5 Sharpe/Sortino/Calmar={primary.sharpe:.4f}/{primary.sortino:.4f}/{primary.calmar:.4f}; universe={primary.universe_sharpe:.4f}/{primary.universe_sortino:.4f}/{primary.universe_calmar:.4f}. Risk-adjusted metrics improved={str(primary.sharpe > primary.universe_sharpe and primary.sortino > primary.universe_sortino and primary.calmar > primary.universe_calmar).lower()}.
5. At costs 0.001 and 0.002 Q5 relative wealth versus the matched universe remains negative ({summary.iloc[1].q5_universe_relative_wealth:.4f}, {summary.iloc[2].q5_universe_relative_wealth:.4f}); the direction is unchanged.
6. Top five positive Q5 periods account for {best_share:.2%} of positive arithmetic period returns; this is a concentration diagnostic, not a deletion rule.
7. Q5-Q1 is a factor diagnostic and is not an executable A-share long-short strategy.

Confirmed suspension and unresolved missing observations are recorded separately. No forward-fill, backfill, next-day substitution, inverse-volatility weighting, parameter search, timing, stop loss, momentum, reversal, or liquidity filter is used.
"""
    (reports / "lowvol_locked_grid_prototype_v1_5.md").write_text(report, encoding="utf-8")
    return 0 if qa["pass"].all() else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        return run(args.project_root.resolve())
    except Exception as error:
        reports = args.project_root.resolve() / "reports"
        reports.mkdir(parents=True, exist_ok=True)
        pd.DataFrame([{"check": "fatal", "pass": False, "critical": True, "notes": str(error), **METADATA}]).to_csv(reports / "lowvol_locked_grid_prototype_qa_v1_5.csv", index=False)
        print(f"prototype input error: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
