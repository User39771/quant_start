from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_UNIVERSE = ROOT / "data" / "processed" / "backtest_universe_research_v1_2.csv"
EXPANDED_UNIVERSE = ROOT / "data" / "processed" / "backtest_universe_expanded_only_v1_2.csv"
PRICE_PANEL = ROOT / "data" / "processed" / "adjusted_price_panel_v1_2.csv"
BENCHMARK_PANEL = ROOT / "data" / "processed" / "hybrid_benchmark_panel_v1_2.csv"

OUT_REPORT = ROOT / "reports" / "adjusted_stock_pool_baseline_v1_2.md"
OUT_SUMMARY = ROOT / "reports" / "adjusted_stock_pool_baseline_summary_v1_2.csv"
OUT_PERIODS = ROOT / "reports" / "adjusted_stock_pool_baseline_periods_v1_2.csv"
OUT_NAV = ROOT / "reports" / "adjusted_stock_pool_baseline_nav_v1_2.csv"
OUT_QA = ROOT / "reports" / "adjusted_stock_pool_baseline_qa_v1_2.csv"

BENCHMARK_CODES = ("000300", "000852", "399006")
MIN_COVERAGE_RATIO = 0.80
REBALANCE_STEP = 20
ANNUALIZATION_FACTOR = math.sqrt(252 / REBALANCE_STEP)

METADATA = {
    "research_baseline_only": "true",
    "adjusted_return_source": "qfq",
    "current_universe_historical_performance": "true",
    "point_in_time_strategy_backtest": "false",
    "survivorship_or_future_universe_bias": "true",
    "close_to_close_execution_assumption": "true",
    "execution_sim_ready": "false",
    "formal_performance_conclusion_allowed": "false",
    "no_investment_conclusion": "true",
}


@dataclass(frozen=True)
class Boundary:
    start: pd.Timestamp
    end: pd.Timestamp
    trading_days: int
    period_type: str


def code6(value: object) -> str:
    text = "" if pd.isna(value) else str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        raise ValueError(f"invalid stock code: {value!r}")
    return digits.zfill(6)[-6:]


def normalize_universe(frame: pd.DataFrame) -> list[str]:
    column = "code" if "code" in frame.columns else "stock_code"
    if column not in frame.columns:
        raise ValueError("universe must include code or stock_code")
    return sorted({code6(value) for value in frame[column].dropna()})


def _flag_true(series: pd.Series) -> pd.Series:
    return series.fillna("").astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})


def prepare_price_panel(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"stock_code", "trade_date", "adjusted_flag", "adjusted_close", "qfq_close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"adjusted price panel missing columns: {sorted(missing)}")

    data = frame.copy()
    data["stock_code"] = data["stock_code"].map(code6)
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce")
    if data["trade_date"].isna().any():
        raise ValueError("invalid trade_date in adjusted price panel")
    if data.duplicated(["stock_code", "trade_date"]).any():
        raise ValueError("duplicate stock_code/trade_date in adjusted price panel")

    data["adjusted_close"] = pd.to_numeric(data["adjusted_close"], errors="coerce")
    data["qfq_close"] = pd.to_numeric(data["qfq_close"], errors="coerce")
    adjusted = _flag_true(data["adjusted_flag"])
    equal_close = np.isclose(data["adjusted_close"], data["qfq_close"], rtol=1e-10, atol=1e-10, equal_nan=False)
    invalid_adjusted = adjusted & (
        ~(data["adjusted_close"] > 0) | ~(data["qfq_close"] > 0) | ~equal_close
    )
    if invalid_adjusted.any():
        raise ValueError("adjusted_flag=true requires positive equal adjusted_close and qfq_close")

    valid = adjusted & (data["adjusted_close"] > 0) & (data["qfq_close"] > 0) & equal_close
    return data.loc[valid, ["stock_code", "trade_date", "adjusted_close"]].sort_values(
        ["stock_code", "trade_date"]
    )


def make_price_index(frame: pd.DataFrame) -> dict[tuple[str, pd.Timestamp], float]:
    return {
        (str(row.stock_code), pd.Timestamp(row.trade_date)): float(row.adjusted_close)
        for row in frame.itertuples(index=False)
    }


def prepare_benchmark_panel(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"benchmark_code", "trade_date", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"benchmark panel missing columns: {sorted(missing)}")
    data = frame.copy()
    data["benchmark_code"] = data["benchmark_code"].map(code6)
    data["trade_date"] = pd.to_datetime(data["trade_date"], errors="coerce")
    if data["trade_date"].isna().any():
        raise ValueError("invalid trade_date in benchmark panel")
    if data.duplicated(["benchmark_code", "trade_date"]).any():
        raise ValueError("duplicate benchmark_code/trade_date in benchmark panel")
    data["close"] = pd.to_numeric(data["close"], errors="coerce")
    return data[["benchmark_code", "trade_date", "close"]].sort_values(["benchmark_code", "trade_date"])


def make_benchmark_index(frame: pd.DataFrame) -> dict[tuple[str, pd.Timestamp], float]:
    return {
        (str(row.benchmark_code), pd.Timestamp(row.trade_date)): float(row.close)
        for row in frame.itertuples(index=False)
        if pd.notna(row.close) and float(row.close) > 0
    }


def common_calendar(prices: pd.DataFrame, benchmarks: pd.DataFrame) -> list[pd.Timestamp]:
    stock_dates = set(prices["trade_date"])
    hs300_dates = set(
        benchmarks.loc[
            benchmarks["benchmark_code"].eq("000300") & (benchmarks["close"] > 0), "trade_date"
        ]
    )
    if not hs300_dates:
        raise ValueError("000300 benchmark has no valid dates")
    return sorted(stock_dates & hs300_dates)


def rebalance_boundaries(dates: list[pd.Timestamp], step: int = REBALANCE_STEP) -> list[Boundary]:
    dates = sorted(dict.fromkeys(pd.Timestamp(date) for date in dates))
    boundaries: list[Boundary] = []
    start_index = 0
    while start_index < len(dates) - 1:
        end_index = min(start_index + step, len(dates) - 1)
        trading_days = end_index - start_index
        boundaries.append(
            Boundary(
                dates[start_index],
                dates[end_index],
                trading_days,
                "full" if trading_days == step else "partial",
            )
        )
        start_index = end_index
    return boundaries


def equal_weights(codes: list[str]) -> dict[str, float]:
    if not codes:
        return {}
    weight = 1.0 / len(codes)
    return {code: weight for code in sorted(codes)}


def evaluate_period(
    universe: list[str],
    prices: dict[tuple[str, pd.Timestamp], float],
    boundary: Boundary,
    min_coverage_ratio: float = MIN_COVERAGE_RATIO,
) -> dict[str, object]:
    eligible = sorted(code for code in universe if (code, boundary.start) in prices)
    ineligible = sorted(set(universe) - set(eligible))
    target = equal_weights(eligible)
    coverage_ratio = len(eligible) / len(universe) if universe else 0.0
    coverage_pass = coverage_ratio >= min_coverage_ratio

    end_missing = sorted(code for code in eligible if (code, boundary.end) not in prices)
    returns = {
        code: prices[(code, boundary.end)] / prices[(code, boundary.start)] - 1.0
        for code in eligible
        if code not in end_missing
    }
    period_valid = bool(eligible) and coverage_pass and not end_missing
    gross_return = (
        sum(target[code] * returns[code] for code in eligible) if period_valid else math.nan
    )
    stock_outliers = sorted(code for code, value in returns.items() if abs(value) > 0.50)

    return {
        "rebalance_date": boundary.start,
        "next_rebalance_date": boundary.end,
        "period_trading_days": boundary.trading_days,
        "period_type": boundary.period_type,
        "universe_count": len(universe),
        "eligible_count": len(eligible),
        "eligible_codes": ";".join(eligible),
        "start_ineligible_codes": ";".join(ineligible),
        "coverage_ratio": coverage_ratio,
        "coverage_pass": coverage_pass,
        "end_price_missing_count": len(end_missing),
        "end_price_missing_codes": ";".join(end_missing),
        "period_valid": period_valid,
        "invalid_period": not period_valid,
        "gross_return": gross_return,
        "stock_return_outlier_codes": ";".join(stock_outliers),
        "portfolio_return_outlier": bool(period_valid and abs(gross_return) > 0.50),
        "_target_weights": target,
        "_stock_returns": returns,
    }


def find_baseline_start(observations: list[dict[str, object]], confirmation_periods: int = 3) -> int | None:
    for start in range(0, len(observations) - confirmation_periods + 1):
        window = observations[start : start + confirmation_periods]
        if all(row["period_type"] == "full" and bool(row["period_valid"]) for row in window):
            return start
    return None


def drifted_weights(previous_weights: dict[str, float], previous_returns: dict[str, float]) -> dict[str, float]:
    gross = {
        code: weight * (1.0 + previous_returns[code])
        for code, weight in previous_weights.items()
        if code in previous_returns
    }
    total = sum(gross.values())
    if total <= 0:
        return {}
    return {code: value / total for code, value in gross.items()}


def turnover_from_drift(target: dict[str, float], drifted: dict[str, float]) -> float:
    return 0.5 * sum(
        abs(target.get(code, 0.0) - drifted.get(code, 0.0)) for code in set(target) | set(drifted)
    )


def run_scenario(
    universe: list[str],
    prices: dict[tuple[str, pd.Timestamp], float],
    boundaries: list[Boundary],
    universe_name: str,
    transaction_cost: float,
) -> pd.DataFrame:
    observations = [evaluate_period(universe, prices, boundary) for boundary in boundaries]
    start_index = find_baseline_start(observations)
    previous_target: dict[str, float] = {}
    previous_returns: dict[str, float] = {}
    headline_nav = 1.0
    terminated = False

    rows: list[dict[str, object]] = []
    for index, observation in enumerate(observations):
        row = dict(observation)
        target = row.pop("_target_weights")
        stock_returns = row.pop("_stock_returns")
        row.update(
            {
                "universe_name": universe_name,
                "transaction_cost": transaction_cost,
                "period_phase": "pre_start_diagnostic",
                "headline_included": False,
                "provisional": row["period_type"] == "partial",
                "turnover": math.nan,
                "cost_drag": math.nan,
                "net_return": math.nan,
                "nav": math.nan,
                "termination_reason": "",
            }
        )

        if start_index is None:
            row["period_phase"] = "partial_diagnostic" if row["period_type"] == "partial" else "pre_start_diagnostic"
            rows.append(row)
            continue
        if index < start_index:
            rows.append(row)
            continue
        if terminated:
            row["period_phase"] = "post_termination_diagnostic"
            rows.append(row)
            continue

        if row["period_type"] == "partial":
            row["period_phase"] = "provisional_partial" if row["period_valid"] else "invalid_partial"
            if row["period_valid"]:
                drifted = drifted_weights(previous_target, previous_returns) if previous_target else {}
                turnover = turnover_from_drift(target, drifted) if previous_target else 1.0
                cost_drag = turnover * transaction_cost
                net_return = float(row["gross_return"]) - cost_drag
                row.update(
                    {
                        "turnover": turnover,
                        "cost_drag": cost_drag,
                        "net_return": net_return,
                        "nav": headline_nav * (1.0 + net_return),
                    }
                )
            rows.append(row)
            continue

        if not row["period_valid"]:
            row["period_phase"] = "termination_period"
            reasons = []
            if not row["coverage_pass"]:
                reasons.append("coverage_below_0.80")
            if row["end_price_missing_count"]:
                reasons.append("end_price_missing")
            row["termination_reason"] = ";".join(reasons) or "invalid_period"
            terminated = True
            rows.append(row)
            continue

        drifted = drifted_weights(previous_target, previous_returns) if previous_target else {}
        turnover = turnover_from_drift(target, drifted) if previous_target else 1.0
        cost_drag = turnover * transaction_cost
        net_return = float(row["gross_return"]) - cost_drag
        headline_nav *= 1.0 + net_return
        row.update(
            {
                "period_phase": "headline",
                "headline_included": True,
                "turnover": turnover,
                "cost_drag": cost_drag,
                "net_return": net_return,
                "nav": headline_nav,
            }
        )
        previous_target = target
        previous_returns = stock_returns
        rows.append(row)

    return pd.DataFrame(rows)


def period_endpoint_maximum_drawdown(nav_values: list[float]) -> float:
    if not nav_values:
        return math.nan
    nav = np.asarray([1.0, *nav_values], dtype=float)
    drawdown = nav / np.maximum.accumulate(nav) - 1.0
    return float(drawdown.min())


def _return_metrics(returns: pd.Series, nav: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> dict[str, float]:
    values = pd.to_numeric(returns, errors="coerce").dropna()
    if values.empty:
        return {
            "cumulative_return": math.nan,
            "annualized_return": math.nan,
            "annualized_volatility": math.nan,
            "sharpe_ratio": math.nan,
            "period_endpoint_maximum_drawdown": math.nan,
            "calmar_ratio": math.nan,
        }
    cumulative = float(np.prod(1.0 + values.to_numpy()) - 1.0)
    calendar_days = (pd.Timestamp(end) - pd.Timestamp(start)).days
    annualized = (
        (1.0 + cumulative) ** (365.2425 / calendar_days) - 1.0
        if calendar_days > 0 and cumulative > -1.0
        else math.nan
    )
    std = float(values.std(ddof=1)) if len(values) > 1 else math.nan
    volatility = std * ANNUALIZATION_FACTOR if math.isfinite(std) else math.nan
    sharpe = (
        float(values.mean()) / std * ANNUALIZATION_FACTOR
        if math.isfinite(std) and std > 0
        else math.nan
    )
    max_drawdown = period_endpoint_maximum_drawdown(pd.to_numeric(nav, errors="coerce").dropna().tolist())
    calmar = annualized / abs(max_drawdown) if math.isfinite(max_drawdown) and max_drawdown < 0 else math.nan
    return {
        "cumulative_return": cumulative,
        "annualized_return": annualized,
        "annualized_volatility": volatility,
        "sharpe_ratio": sharpe,
        "period_endpoint_maximum_drawdown": max_drawdown,
        "calmar_ratio": calmar,
    }


def portfolio_metrics(periods: pd.DataFrame) -> dict[str, object]:
    headline = periods.loc[periods.get("headline_included", False).eq(True)].copy() if not periods.empty else pd.DataFrame()
    partial = periods.loc[
        periods.get("provisional", False).eq(True) & periods.get("net_return", pd.Series(index=periods.index, dtype=float)).notna()
    ].copy() if not periods.empty else pd.DataFrame()
    termination = periods.loc[periods.get("period_phase", "").eq("termination_period")].copy() if not periods.empty else pd.DataFrame()
    invalid_full_count = int(
        ((periods.get("period_type", "") == "full") & periods.get("invalid_period", False).eq(True)).sum()
    ) if not periods.empty else 0

    result: dict[str, object] = {
        "scenario_status": "insufficient_contiguous_history" if headline.empty else "completed_to_last_full_period",
        "baseline_start_date": "",
        "last_full_period_end": "",
        "termination_date": "",
        "termination_reason": "",
        "valid_period_count": len(headline),
        "invalid_period_count": invalid_full_count,
        "average_coverage_ratio": math.nan,
        "minimum_coverage_ratio": math.nan,
        "positive_period_ratio": math.nan,
        "average_turnover": math.nan,
        "total_cost_drag": math.nan,
        "dropped_stock_period_count": int(periods.get("end_price_missing_count", pd.Series(dtype=float)).sum()) if not periods.empty else 0,
        "latest_partial_period_return": float(partial.iloc[-1]["net_return"]) if not partial.empty else math.nan,
    }
    if headline.empty:
        result.update(_return_metrics(pd.Series(dtype=float), pd.Series(dtype=float), pd.Timestamp("2000-01-01"), pd.Timestamp("2000-01-01")))
        return result

    headline = headline.sort_values("rebalance_date")
    start = pd.Timestamp(headline.iloc[0]["rebalance_date"])
    end = pd.Timestamp(headline.iloc[-1]["next_rebalance_date"])
    result.update(_return_metrics(headline["net_return"], headline["nav"], start, end))
    result.update(
        {
            "baseline_start_date": start,
            "last_full_period_end": end,
            "average_coverage_ratio": float(headline["coverage_ratio"].mean()),
            "minimum_coverage_ratio": float(headline["coverage_ratio"].min()),
            "positive_period_ratio": float((headline["net_return"] > 0).mean()),
            "average_turnover": float(headline["turnover"].mean()),
            "total_cost_drag": float(headline["cost_drag"].sum()),
        }
    )
    if not termination.empty:
        result["scenario_status"] = "terminated_on_invalid_period"
        result["termination_date"] = pd.Timestamp(termination.iloc[0]["rebalance_date"])
        result["termination_reason"] = termination.iloc[0]["termination_reason"]
    return result


def benchmark_comparison(
    periods: pd.DataFrame,
    benchmark_prices: dict[tuple[str, pd.Timestamp], float],
    benchmark_code: str,
) -> tuple[pd.DataFrame, dict[str, object]]:
    headline = periods.loc[periods.get("headline_included", False).eq(True)].copy() if not periods.empty else pd.DataFrame()
    partial = periods.loc[
        periods.get("provisional", False).eq(True) & periods.get("net_return", pd.Series(index=periods.index, dtype=float)).notna()
    ].copy() if not periods.empty else pd.DataFrame()
    selected = pd.concat([headline, partial], ignore_index=True)
    rows: list[dict[str, object]] = []
    benchmark_nav = 1.0
    headline_missing = False

    for row in selected.itertuples(index=False):
        start = pd.Timestamp(row.rebalance_date)
        end = pd.Timestamp(row.next_rebalance_date)
        start_price = benchmark_prices.get((benchmark_code, start))
        end_price = benchmark_prices.get((benchmark_code, end))
        benchmark_return = (
            end_price / start_price - 1.0 if start_price and end_price and start_price > 0 and end_price > 0 else math.nan
        )
        if row.headline_included and not math.isfinite(benchmark_return):
            headline_missing = True
        if math.isfinite(benchmark_return):
            next_benchmark_nav = benchmark_nav * (1.0 + benchmark_return)
        else:
            next_benchmark_nav = math.nan
        active_return = float(row.net_return) - benchmark_return if math.isfinite(benchmark_return) else math.nan
        rows.append(
            {
                "rebalance_date": start,
                "next_rebalance_date": end,
                "period_type": row.period_type,
                "headline_included": bool(row.headline_included),
                "provisional": bool(row.provisional),
                "portfolio_net_return": row.net_return,
                "portfolio_nav": row.nav,
                "benchmark_code": benchmark_code,
                "benchmark_return": benchmark_return,
                "benchmark_nav": next_benchmark_nav,
                "active_return": active_return,
                "benchmark_period_valid": math.isfinite(benchmark_return),
            }
        )
        if row.headline_included and math.isfinite(next_benchmark_nav):
            benchmark_nav = next_benchmark_nav

    nav = pd.DataFrame(rows)
    comparison_valid = bool(not headline.empty and not headline_missing)
    metrics: dict[str, object] = {
        "benchmark_comparison_valid": comparison_valid,
        "benchmark_cumulative_return": math.nan,
        "benchmark_annualized_return": math.nan,
        "benchmark_annualized_volatility": math.nan,
        "benchmark_period_endpoint_maximum_drawdown": math.nan,
        "portfolio_minus_benchmark_cumulative_return": math.nan,
        "tracking_error": math.nan,
        "information_ratio": math.nan,
        "latest_partial_benchmark_return": math.nan,
    }
    if not partial.empty and not nav.empty:
        partial_nav = nav.loc[nav["provisional"].eq(True)]
        if not partial_nav.empty:
            metrics["latest_partial_benchmark_return"] = partial_nav.iloc[-1]["benchmark_return"]
    if not comparison_valid:
        nav["benchmark_comparison_valid"] = False
        return nav, metrics

    headline_nav = nav.loc[nav["headline_included"].eq(True)].copy()
    start = pd.Timestamp(headline_nav.iloc[0]["rebalance_date"])
    end = pd.Timestamp(headline_nav.iloc[-1]["next_rebalance_date"])
    benchmark_metrics = _return_metrics(
        headline_nav["benchmark_return"], headline_nav["benchmark_nav"], start, end
    )
    active = headline_nav["active_return"]
    active_std = float(active.std(ddof=1)) if len(active) > 1 else math.nan
    tracking_error = active_std * ANNUALIZATION_FACTOR if math.isfinite(active_std) else math.nan
    information_ratio = (
        float(active.mean()) / active_std * ANNUALIZATION_FACTOR
        if math.isfinite(active_std) and active_std > 0
        else math.nan
    )
    portfolio_cumulative = float(np.prod(1.0 + headline_nav["portfolio_net_return"].astype(float)) - 1.0)
    metrics.update(
        {
            "benchmark_cumulative_return": benchmark_metrics["cumulative_return"],
            "benchmark_annualized_return": benchmark_metrics["annualized_return"],
            "benchmark_annualized_volatility": benchmark_metrics["annualized_volatility"],
            "benchmark_period_endpoint_maximum_drawdown": benchmark_metrics["period_endpoint_maximum_drawdown"],
            "portfolio_minus_benchmark_cumulative_return": portfolio_cumulative - benchmark_metrics["cumulative_return"],
            "tracking_error": tracking_error,
            "information_ratio": information_ratio,
        }
    )
    nav["benchmark_comparison_valid"] = True
    return nav, metrics


def collect_qa(periods: pd.DataFrame, nav: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in periods.itertuples(index=False):
        common = {
            "universe_name": row.universe_name,
            "transaction_cost": row.transaction_cost,
            "rebalance_date": row.rebalance_date,
            "next_rebalance_date": row.next_rebalance_date,
        }
        if row.end_price_missing_count:
            rows.append({**common, "severity": "High", "issue_type": "end_price_missing", "stock_code": row.end_price_missing_codes, "details": "Target stock missing end qfq; period not reweighted."})
        if row.period_phase == "termination_period":
            rows.append({**common, "severity": "High", "issue_type": "baseline_terminated", "stock_code": "", "details": row.termination_reason})
        if row.period_phase == "pre_start_diagnostic":
            rows.append({**common, "severity": "Info", "issue_type": "pre_baseline_diagnostic", "stock_code": "", "details": f"coverage={row.coverage_ratio:.6f}"})
        if row.period_type == "partial":
            rows.append({**common, "severity": "Info", "issue_type": "partial_final_period", "stock_code": "", "details": "Excluded from headline metrics."})
        if row.stock_return_outlier_codes:
            rows.append({**common, "severity": "Medium", "issue_type": "stock_return_outlier", "stock_code": row.stock_return_outlier_codes, "details": "abs(return)>50%; retained in metrics when period is valid."})
        if row.portfolio_return_outlier:
            rows.append({**common, "severity": "Medium", "issue_type": "portfolio_return_outlier", "stock_code": "", "details": f"gross_return={row.gross_return}; retained in metrics."})

    if not nav.empty:
        missing = nav[nav["benchmark_return"].isna()]
        for row in missing.itertuples(index=False):
            rows.append(
                {
                    "universe_name": row.universe_name,
                    "transaction_cost": row.transaction_cost,
                    "rebalance_date": row.rebalance_date,
                    "next_rebalance_date": row.next_rebalance_date,
                    "severity": "High" if row.headline_included else "Medium",
                    "issue_type": "benchmark_endpoint_missing",
                    "stock_code": row.benchmark_code,
                    "details": "Benchmark comparison invalid; periods were not shortened.",
                }
            )
        bad_nav = nav[nav["portfolio_nav"].notna() & (~np.isfinite(nav["portfolio_nav"].astype(float)) | (nav["portfolio_nav"].astype(float) <= 0))]
        for row in bad_nav.itertuples(index=False):
            rows.append(
                {
                    "universe_name": row.universe_name,
                    "transaction_cost": row.transaction_cost,
                    "rebalance_date": row.rebalance_date,
                    "next_rebalance_date": row.next_rebalance_date,
                    "severity": "High",
                    "issue_type": "invalid_nav",
                    "stock_code": "",
                    "details": f"portfolio_nav={row.portfolio_nav}",
                }
            )
    return pd.DataFrame(rows)


def render_report(summary: pd.DataFrame, qa: pd.DataFrame) -> str:
    lines = [
        "# Adjusted Stock Pool Research Baseline v1.2",
        "",
        "- research_baseline_only=true",
        "- adjusted_return_source=qfq",
        "- current_universe_historical_performance=true",
        "- point_in_time_strategy_backtest=false",
        "- survivorship_or_future_universe_bias=true",
        "- close_to_close_execution_assumption=true",
        "- execution_sim_ready=false",
        "- formal_performance_conclusion_allowed=false",
        "- no_investment_conclusion=true",
        "- no investment conclusion",
        "",
        "## Method",
        "",
        "Eligibility uses rebalance-date qfq data only. A missing target end price invalidates the whole period; survivors are not reweighted.",
        "No full-sample effective-universe filter is applied; the complete deduplicated stock pool remains the coverage denominator.",
        "The baseline starts at the first of three consecutive valid 20-trading-day periods. This ex-post continuity choice is disclosed and is not point-in-time.",
        "The final partial period is provisional and excluded from all headline metrics.",
        "Annualized volatility, Sharpe, tracking error, and information ratio use sqrt(252/20). CAGR uses actual calendar days from baseline start to last full-period end.",
        "`period_endpoint_maximum_drawdown` uses rebalance-period endpoint NAV and can understate daily intraperiod maximum drawdown.",
        "",
        "## Scenario Summary",
        "",
    ]
    if summary.empty:
        lines.append("- no scenario results")
    else:
        for row in summary.itertuples(index=False):
            start = "" if pd.isna(row.baseline_start_date) else pd.Timestamp(row.baseline_start_date).strftime("%Y-%m-%d")
            end = "" if pd.isna(row.last_full_period_end) else pd.Timestamp(row.last_full_period_end).strftime("%Y-%m-%d")
            lines.append(
                f"- {row.universe_name}, cost={row.transaction_cost}, benchmark={row.benchmark_code}: "
                f"status={row.scenario_status}, start={start}, last_full_period_end={end}, "
                f"termination_reason={row.termination_reason or 'none'}, universe_count={row.universe_count}, "
                f"average_coverage={row.average_coverage_ratio}, minimum_coverage={row.minimum_coverage_ratio}, "
                f"cumulative_return={row.cumulative_return}, latest_partial_return={row.latest_partial_period_return}, "
                f"benchmark_comparison_valid={str(row.benchmark_comparison_valid).lower()}"
            )
    lines.extend(
        [
            "",
            "## QA",
            "",
            f"- qa_issue_rows={len(qa)}",
        ]
    )
    if not qa.empty:
        for issue_type, count in qa["issue_type"].value_counts().items():
            lines.append(f"- {issue_type}={count}")
    lines.extend(
        [
            "",
            "## Caveats",
            "",
            "- The universe was built with 2026 information, creating current-universe and survivorship-like bias.",
            "- Historical ST, suspension, limit-up/down, and complete execution status are unavailable.",
            "- Close-to-close returns are not executable trade prices.",
            "- Extreme returns are flagged but retained unless a hard price/date/key QA rule fails.",
            "- This output validates data and research plumbing only; it does not establish strategy effectiveness.",
        ]
    )
    return "\n".join(lines) + "\n"


def _with_metadata(frame: pd.DataFrame) -> pd.DataFrame:
    output = frame.copy()
    for key, value in METADATA.items():
        output[key] = value
    for column in ("rebalance_date", "next_rebalance_date", "baseline_start_date", "last_full_period_end", "termination_date"):
        if column in output.columns:
            parsed = pd.to_datetime(output[column], errors="coerce")
            output[column] = parsed.dt.strftime("%Y-%m-%d").fillna("")
    for column in output.columns:
        if pd.api.types.is_bool_dtype(output[column]):
            output[column] = output[column].map(lambda value: str(bool(value)).lower())
    return output


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _with_metadata(frame).to_csv(path, index=False, encoding="utf-8-sig")


def main() -> int:
    price_frame = prepare_price_panel(pd.read_csv(PRICE_PANEL, dtype=str, low_memory=False))
    benchmark_frame = prepare_benchmark_panel(pd.read_csv(BENCHMARK_PANEL, dtype=str, low_memory=False))
    price_lookup = make_price_index(price_frame)
    benchmark_lookup = make_benchmark_index(benchmark_frame)
    boundaries = rebalance_boundaries(common_calendar(price_frame, benchmark_frame))

    universe_inputs = [("research_universe_v1_2", RESEARCH_UNIVERSE)]
    if EXPANDED_UNIVERSE.exists():
        universe_inputs.append(("expanded_only_v1_2", EXPANDED_UNIVERSE))

    all_periods: list[pd.DataFrame] = []
    all_nav: list[pd.DataFrame] = []
    summary_rows: list[dict[str, object]] = []

    for universe_name, path in universe_inputs:
        universe = normalize_universe(pd.read_csv(path, dtype=str))
        for transaction_cost in (0.0, 0.001):
            periods = run_scenario(universe, price_lookup, boundaries, universe_name, transaction_cost)
            all_periods.append(periods)
            portfolio = portfolio_metrics(periods)
            for benchmark_code in BENCHMARK_CODES:
                nav, benchmark = benchmark_comparison(periods, benchmark_lookup, benchmark_code)
                if not nav.empty:
                    nav["universe_name"] = universe_name
                    nav["transaction_cost"] = transaction_cost
                    all_nav.append(nav)
                summary_rows.append(
                    {
                        "universe_name": universe_name,
                        "transaction_cost": transaction_cost,
                        "benchmark_code": benchmark_code,
                        "universe_count": len(universe),
                        **portfolio,
                        **benchmark,
                    }
                )

    periods_output = pd.concat(all_periods, ignore_index=True) if all_periods else pd.DataFrame()
    nav_output = pd.concat(all_nav, ignore_index=True) if all_nav else pd.DataFrame()
    summary_output = pd.DataFrame(summary_rows)
    qa_output = collect_qa(periods_output, nav_output)

    write_csv(periods_output, OUT_PERIODS)
    write_csv(nav_output, OUT_NAV)
    write_csv(summary_output, OUT_SUMMARY)
    write_csv(qa_output, OUT_QA)
    OUT_REPORT.write_text(render_report(summary_output, qa_output), encoding="utf-8")

    print(f"scenarios={len(universe_inputs) * 2}")
    print(f"period_rows={len(periods_output)}")
    print(f"summary_rows={len(summary_output)}")
    print(f"qa_rows={len(qa_output)}")
    print("research_baseline_only=true")
    print("formal_performance_conclusion_allowed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
