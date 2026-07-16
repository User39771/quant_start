"""Explain the existing Stock Pool v1.2 research baseline.

This script attributes an already-produced baseline.  It does not alter the
portfolio, fetch data, or make an investment recommendation.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "reports"
PERIODS_PATH = REPORTS / "adjusted_stock_pool_baseline_periods_v1_2.csv"
NAV_PATH = REPORTS / "adjusted_stock_pool_baseline_nav_v1_2.csv"
PRICES_PATH = ROOT / "data" / "processed" / "adjusted_price_panel_v1_2.csv"
UNIVERSE_PATH = ROOT / "data" / "processed" / "backtest_universe_research_v1_2.csv"

UNIVERSE_NAME = "research_universe_v1_2"
PRIMARY_COST = 0.0
ATOL = 1e-10
RTOL = 1e-8
ANNUALIZATION = math.sqrt(252 / 20)
SCENARIO_ID = "research_universe_v1_2__cost_0"


def code6(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit() or len(text) > 6:
        raise ValueError(f"Invalid six-digit code: {value!r}")
    return text.zfill(6)


def flag_true(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def parse_eligible_codes(value: object, expected_count: int) -> list[str]:
    codes = [part.strip() for part in str(value).split(";") if part.strip()]
    if len(codes) != expected_count:
        raise ValueError(f"eligible_count={expected_count}, parsed={len(codes)}")
    if any(len(code) != 6 or not code.isdigit() for code in codes):
        raise ValueError(f"eligible_codes contains non-six-digit code: {codes}")
    if len(codes) != len(set(codes)):
        raise ValueError(f"eligible_codes contains duplicates: {codes}")
    return codes


def select_headline_periods(frame: pd.DataFrame) -> pd.DataFrame:
    selected = frame.loc[
        flag_true(frame["headline_included"])
        & frame["period_type"].eq("full")
        & frame["period_phase"].eq("headline")
    ].copy()
    if selected.empty:
        raise ValueError("No headline full periods found for the requested scenario.")
    return selected.sort_values("rebalance_date").reset_index(drop=True)


def theme_map_from_universe(universe: pd.DataFrame) -> pd.Series:
    invalid = universe["theme"].isna() | universe["theme"].astype(str).str.strip().isin({"", "nan"})
    if invalid.any():
        codes = ";".join(universe.loc[invalid, "code"].astype(str))
        raise ValueError(f"Missing theme for universe codes: {codes}")
    return universe.groupby("code")["theme"].agg(
        lambda values: list(dict.fromkeys(value.strip() for value in values.astype(str)))
    )


def attribution_coverage(universe: pd.DataFrame, detail: pd.DataFrame) -> dict[str, object]:
    universe_codes = set(universe["code"].map(code6))
    attributed_codes = set(detail["stock_code"].map(code6))
    never = sorted(universe_codes - attributed_codes)
    return {
        "universe_unique_stock_count": len(universe_codes),
        "attributed_stock_count": len(attributed_codes),
        "never_eligible_in_headline_count": len(never),
        "never_eligible_in_headline_codes": ";".join(never),
    }


PERIOD_KEYS = ["rebalance_date", "next_rebalance_date"]


def align_benchmark_periods(
    expected: pd.DataFrame, benchmark: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, object]]:
    expected_keys = expected[PERIOD_KEYS].drop_duplicates()
    if len(expected_keys) != len(expected):
        raise ValueError("Expected headline periods contain duplicate endpoint keys.")
    duplicate_count = int(benchmark.duplicated(PERIOD_KEYS, keep="first").sum())
    actual_keys = benchmark[PERIOD_KEYS].drop_duplicates()
    key_check = expected_keys.merge(actual_keys, on=PERIOD_KEYS, how="outer", indicator=True)
    missing_count = int(key_check["_merge"].eq("left_only").sum())
    extra_count = int(key_check["_merge"].eq("right_only").sum())
    period_flags_valid = bool(flag_true(benchmark["benchmark_period_valid"]).all())
    comparison_flags_valid = bool(flag_true(benchmark["benchmark_comparison_valid"]).all())
    valid = not any(
        (duplicate_count, missing_count, extra_count)
    ) and period_flags_valid and comparison_flags_valid
    aligned = (
        expected_keys.merge(benchmark, on=PERIOD_KEYS, how="left", validate="one_to_one")
        if valid
        else pd.DataFrame()
    )
    return aligned, {
        "valid": valid,
        "expected_count": len(expected_keys),
        "actual_count": len(actual_keys),
        "missing_count": missing_count,
        "extra_count": extra_count,
        "duplicate_count": duplicate_count,
        "benchmark_period_valid": period_flags_valid,
        "benchmark_comparison_valid": comparison_flags_valid,
    }


def align_cost_scenarios(left: pd.DataFrame, right: pd.DataFrame) -> pd.DataFrame:
    if left.duplicated(PERIOD_KEYS).any() or right.duplicated(PERIOD_KEYS).any():
        raise ValueError("Cost scenario contains duplicate period endpoint keys.")
    merged = left.merge(
        right,
        on=PERIOD_KEYS,
        how="outer",
        suffixes=("_cost_0", "_cost_0.001"),
        indicator=True,
        validate="one_to_one",
    )
    if len(left) != len(right) or not merged["_merge"].eq("both").all():
        raise ValueError("Cost scenarios do not contain identical period endpoint keys.")
    return merged.sort_values(PERIOD_KEYS).drop(columns="_merge").reset_index(drop=True)


def positive_contributor_code(stock: pd.DataFrame) -> str | None:
    positive = stock.loc[stock["linked_gross_contribution"].gt(0)]
    if positive.empty:
        return None
    return str(positive.sort_values("linked_gross_contribution", ascending=False).iloc[0]["stock_code"])


def critical_qa_exit_code(qa: pd.DataFrame) -> int:
    failures = qa.loc[qa["critical"].astype(bool) & ~qa["pass"].astype(bool)]
    return 1 if not failures.empty else 0


def link_contributions(detail: pd.DataFrame, gross_returns: pd.Series) -> pd.DataFrame:
    """Link additive period contributions to terminal compounded wealth."""
    later_growth: dict[int, float] = {}
    multiplier = 1.0
    for period_index in reversed(list(gross_returns.index)):
        later_growth[int(period_index)] = multiplier
        multiplier *= 1.0 + float(gross_returns.loc[period_index])
    result = detail.copy()
    result["linked_contribution"] = result.apply(
        lambda row: float(row["stock_contribution"]) * later_growth[int(row["period_index"])],
        axis=1,
    )
    return result


def concentration_metrics(values: pd.Series) -> dict[str, float]:
    values = pd.to_numeric(values, errors="coerce").dropna()
    positive = values.loc[values > 0]
    absolute = values.abs()
    positive_total = float(positive.sum())
    absolute_total = float(absolute.sum())

    def share(series: pd.Series, total: float, count: int) -> float:
        return float(series.nlargest(count).sum() / total) if total else math.nan

    return {
        "positive_contribution_hhi": (
            float(((positive / positive_total) ** 2).sum()) if positive_total else math.nan
        ),
        "absolute_contribution_hhi": (
            float(((absolute / absolute_total) ** 2).sum()) if absolute_total else math.nan
        ),
        "top5_share_of_positive_contribution": share(positive, positive_total, 5),
        "top10_share_of_positive_contribution": share(positive, positive_total, 10),
        "top5_share_of_absolute_contribution": share(absolute, absolute_total, 5),
        "top10_share_of_absolute_contribution": share(absolute, absolute_total, 10),
    }


def fractional_theme_contributions(
    detail: pd.DataFrame, theme_map: dict[str, list[str]] | pd.Series
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row in detail.itertuples(index=False):
        themes = theme_map[row.stock_code]
        allocation = 1.0 / len(themes)
        for theme in themes:
            rows.append(
                {
                    "period_index": row.period_index,
                    "stock_code": row.stock_code,
                    "theme": theme,
                    "theme_allocation": allocation,
                    "theme_contribution": row.stock_contribution * allocation,
                    "linked_contribution": row.linked_contribution * allocation,
                }
            )
    return pd.DataFrame(rows)


def benchmark_metrics(group: pd.DataFrame) -> dict[str, float]:
    active = group["portfolio_net_return"] - group["benchmark_return"]
    active_std = float(active.std(ddof=1))
    portfolio_cumulative = float(group.iloc[-1]["portfolio_nav"] - 1.0)
    benchmark_cumulative = float(group.iloc[-1]["benchmark_nav"] - 1.0)
    return {
        "relative_wealth": float(
            group.iloc[-1]["portfolio_nav"] / group.iloc[-1]["benchmark_nav"] - 1.0
        ),
        "arithmetic_active_return_sum": float(active.sum()),
        "cumulative_return_difference": portfolio_cumulative - benchmark_cumulative,
        "positive_active_period_ratio": float((active > 0).mean()),
        "negative_active_period_ratio": float((active < 0).mean()),
        "tracking_error": active_std * ANNUALIZATION,
        "information_ratio": (
            float(active.mean()) / active_std * ANNUALIZATION if active_std else math.nan
        ),
    }


def drawdown_window(nav: pd.DataFrame, initial_date: pd.Timestamp) -> dict[str, object]:
    series = pd.concat(
        [
            pd.DataFrame({"period_end": [initial_date], "nav": [1.0]}),
            nav[["period_end", "nav"]],
        ],
        ignore_index=True,
    ).sort_values("period_end", kind="stable").reset_index(drop=True)
    running_peak = series["nav"].cummax()
    drawdown = series["nav"] / running_peak - 1.0
    trough_index = int(drawdown.idxmin())
    peak_index = int(series.loc[:trough_index, "nav"].idxmax())
    peak_nav = float(series.loc[peak_index, "nav"])
    recovery = series.loc[(series.index > trough_index) & (series["nav"] >= peak_nav)]
    return {
        "peak_date": pd.Timestamp(series.loc[peak_index, "period_end"]),
        "peak_nav": peak_nav,
        "trough_date": pd.Timestamp(series.loc[trough_index, "period_end"]),
        "trough_nav": float(series.loc[trough_index, "nav"]),
        "recovery_date": (
            pd.Timestamp(recovery.iloc[0]["period_end"]) if not recovery.empty else pd.NaT
        ),
        "period_endpoint_drawdown": float(drawdown.loc[trough_index]),
        "drawdown_duration_periods": trough_index - peak_index,
    }


def leave_one_out_returns(stock_returns: pd.DataFrame, excluded_code: str) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    nav = 1.0
    for period_index, group in stock_returns.groupby("period_index", sort=True):
        remaining = group.loc[group["stock_code"].ne(excluded_code)]
        valid = not remaining.empty
        period_return = float(remaining["stock_return"].mean()) if valid else math.nan
        if valid:
            nav *= 1.0 + period_return
        rows.append(
            {
                "period_index": int(period_index),
                "period_return": period_return,
                "nav": nav if valid else math.nan,
                "valid": valid,
            }
        )
    return pd.DataFrame(rows)


def reconciliation_row(check: str, actual: float, expected: float, critical: bool = True) -> dict[str, object]:
    absolute_error = abs(actual - expected)
    relative_error = absolute_error / abs(expected) if expected else (0.0 if not absolute_error else math.inf)
    passed = bool(np.isclose(actual, expected, atol=ATOL, rtol=RTOL))
    return {
        "scenario_id": SCENARIO_ID,
        "universe_name": UNIVERSE_NAME,
        "transaction_cost": PRIMARY_COST,
        "check": check,
        "actual": actual,
        "expected": expected,
        "absolute_error": absolute_error,
        "relative_error": relative_error,
        "atol": ATOL,
        "rtol": RTOL,
        "pass": passed,
        "critical": critical,
        "notes": "",
    }


def summary_row(section: str, metric: str, value: object, denominator: object = "", notes: str = "", cost: float = PRIMARY_COST) -> dict[str, object]:
    return {
        "scenario_id": f"{UNIVERSE_NAME}__cost_{cost:g}",
        "universe_name": UNIVERSE_NAME,
        "transaction_cost": cost,
        "section": section,
        "metric": metric,
        "value": value,
        "denominator": denominator,
        "status": "not_available" if pd.isna(value) else "ok",
        "notes": notes,
    }


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    periods = pd.read_csv(PERIODS_PATH, dtype=str)
    nav = pd.read_csv(NAV_PATH, dtype=str)
    prices = pd.read_csv(PRICES_PATH, dtype={"stock_code": str})
    universe = pd.read_csv(UNIVERSE_PATH, dtype={"code": str})

    for frame in (periods, nav):
        for column in ("rebalance_date", "next_rebalance_date"):
            if column in frame:
                frame[column] = pd.to_datetime(frame[column], errors="raise")
    for column in ("transaction_cost", "gross_return", "net_return", "turnover", "cost_drag", "nav"):
        if column in periods:
            periods[column] = pd.to_numeric(periods[column], errors="coerce")
    for column in ("transaction_cost", "portfolio_net_return", "portfolio_nav", "benchmark_return", "benchmark_nav"):
        if column in nav:
            nav[column] = pd.to_numeric(nav[column], errors="coerce")

    prices["stock_code"] = prices["stock_code"].map(code6)
    prices["trade_date"] = pd.to_datetime(prices["trade_date"], errors="raise")
    prices["adjusted_close"] = pd.to_numeric(prices["adjusted_close"], errors="coerce")
    prices = prices.loc[flag_true(prices["adjusted_flag"]) & (prices["adjusted_close"] > 0)]
    if prices.duplicated(["stock_code", "trade_date"]).any():
        raise ValueError("adjusted panel has duplicate stock_code/trade_date rows")
    universe["code"] = universe["code"].map(code6)
    return periods, nav, prices, universe


def build_period_stock(periods: pd.DataFrame, prices: pd.DataFrame, universe: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    primary = periods.loc[
        periods["universe_name"].eq(UNIVERSE_NAME)
        & np.isclose(periods["transaction_cost"], PRIMARY_COST, equal_nan=False)
    ]
    primary = select_headline_periods(primary)
    lookup = prices.set_index(["stock_code", "trade_date"])["adjusted_close"].to_dict()
    theme_map = theme_map_from_universe(universe)
    metadata = universe.groupby("code", sort=False).agg(stock_name=("name", "first"))
    metadata["themes"] = theme_map.map(";".join)
    rows: list[dict[str, object]] = []
    qa: list[dict[str, object]] = []

    for period_index, period in primary.iterrows():
        codes = parse_eligible_codes(period["eligible_codes"], int(period["eligible_count"]))
        qa.append(reconciliation_row(f"eligible_count_{period_index}", len(codes), int(period["eligible_count"])))
        qa.append(reconciliation_row(f"eligible_code_format_{period_index}", float(all(len(code) == 6 and code.isdigit() for code in codes)), 1.0))
        qa.append(reconciliation_row(f"eligible_code_uniqueness_{period_index}", len(set(codes)), len(codes)))
        weight = 1.0 / len(codes)
        for code in codes:
            start_key = (code, period["rebalance_date"])
            end_key = (code, period["next_rebalance_date"])
            if start_key not in lookup or end_key not in lookup:
                raise ValueError(f"Missing qfq endpoint for headline holding {code}, period {period_index}")
            stock_return = float(lookup[end_key] / lookup[start_key] - 1.0)
            meta = metadata.loc[code]
            rows.append(
                {
                    "scenario_id": SCENARIO_ID,
                    "universe_name": UNIVERSE_NAME,
                    "transaction_cost": PRIMARY_COST,
                    "period_index": period_index,
                    "rebalance_date": period["rebalance_date"],
                    "period_end": period["next_rebalance_date"],
                    "stock_code": code,
                    "stock_name": meta["stock_name"],
                    "theme": meta["themes"],
                    "target_weight": weight,
                    "stock_return": stock_return,
                    "stock_contribution": weight * stock_return,
                }
            )
        actual = sum(row["stock_contribution"] for row in rows if row["period_index"] == period_index)
        qa.append(reconciliation_row(f"period_stock_contribution_{period_index}", actual, float(period["gross_return"])))

    detail = pd.DataFrame(rows)
    gross = primary["gross_return"].reset_index(drop=True)
    detail = link_contributions(detail, gross)
    gross_cumulative = float(np.prod(1.0 + gross) - 1.0)
    qa.append(reconciliation_row("linked_stock_contribution_total", float(detail["linked_contribution"].sum()), gross_cumulative))
    return detail, qa


def build_theme_attribution(detail: pd.DataFrame, universe: pd.DataFrame) -> tuple[pd.DataFrame, list[dict[str, object]]]:
    theme_map = theme_map_from_universe(universe)
    period_theme = fractional_theme_contributions(detail, theme_map)
    qa: list[dict[str, object]] = []
    stock_period = detail.groupby("period_index")["stock_contribution"].sum()
    for period_index, actual in period_theme.groupby("period_index")["theme_contribution"].sum().items():
        qa.append(reconciliation_row(f"period_theme_contribution_{period_index}", float(actual), float(stock_period.loc[period_index])))
    for (period_index, stock_code), allocation in period_theme.groupby(["period_index", "stock_code"])["theme_allocation"].sum().items():
        qa.append(reconciliation_row(f"theme_allocation_{period_index}_{stock_code}", float(allocation), 1.0))
    summary = period_theme.groupby("theme", as_index=False).agg(
        arithmetic_contribution_sum=("theme_contribution", "sum"),
        linked_gross_contribution=("linked_contribution", "sum"),
    )
    summary.insert(0, "transaction_cost", PRIMARY_COST)
    summary.insert(0, "universe_name", UNIVERSE_NAME)
    summary.insert(0, "scenario_id", SCENARIO_ID)
    summary["contribution_rank"] = summary["linked_gross_contribution"].rank(method="min", ascending=False).astype(int)
    return summary.sort_values("contribution_rank"), qa


def build_stock_summary(detail: pd.DataFrame) -> pd.DataFrame:
    grouped = detail.groupby(["stock_code", "stock_name", "theme"], as_index=False).agg(
        valid_period_count=("period_index", "count"),
        average_target_weight=("target_weight", "mean"),
        arithmetic_contribution_sum=("stock_contribution", "sum"),
        linked_gross_contribution=("linked_contribution", "sum"),
        positive_contribution_periods=("stock_contribution", lambda values: int((values > 0).sum())),
        negative_contribution_periods=("stock_contribution", lambda values: int((values < 0).sum())),
        best_period_contribution=("stock_contribution", "max"),
        worst_period_contribution=("stock_contribution", "min"),
    )
    grouped.insert(0, "transaction_cost", PRIMARY_COST)
    grouped.insert(0, "universe_name", UNIVERSE_NAME)
    grouped.insert(0, "scenario_id", SCENARIO_ID)
    grouped["contribution_rank"] = grouped["linked_gross_contribution"].rank(method="min", ascending=False).astype(int)
    return grouped.sort_values("contribution_rank")


def add_concentration_rows(summary: list[dict[str, object]], section: str, prefix: str, values: pd.Series) -> None:
    positive_total = float(values.loc[values > 0].sum())
    absolute_total = float(values.abs().sum())
    for metric, value in concentration_metrics(values).items():
        denominator = positive_total if "positive" in metric else absolute_total
        summary.append(
            summary_row(
                section,
                f"{prefix}_{metric}",
                value,
                denominator,
                "Denominator is zero." if not denominator else "",
            )
        )


def analyze_benchmarks(
    nav: pd.DataFrame,
    expected_periods: pd.DataFrame,
    summary: list[dict[str, object]],
    qa: list[dict[str, object]],
) -> None:
    scenario = nav.loc[
        nav["universe_name"].eq(UNIVERSE_NAME)
        & np.isclose(nav["transaction_cost"], PRIMARY_COST, equal_nan=False)
        & flag_true(nav["headline_included"])
    ].copy()
    scenario["benchmark_code"] = scenario["benchmark_code"].map(code6)
    for code, group in scenario.groupby("benchmark_code"):
        aligned, diagnostic = align_benchmark_periods(expected_periods, group)
        qa.extend(
            [
                reconciliation_row(f"benchmark_{code}_endpoint_count", diagnostic["actual_count"], diagnostic["expected_count"]),
                reconciliation_row(f"benchmark_{code}_missing_endpoints", diagnostic["missing_count"], 0.0),
                reconciliation_row(f"benchmark_{code}_extra_endpoints", diagnostic["extra_count"], 0.0),
                reconciliation_row(f"benchmark_{code}_duplicate_endpoints", diagnostic["duplicate_count"], 0.0),
                reconciliation_row(f"benchmark_{code}_period_valid_flags", float(diagnostic["benchmark_period_valid"]), 1.0),
                reconciliation_row(f"benchmark_{code}_comparison_valid_flags", float(diagnostic["benchmark_comparison_valid"]), 1.0),
            ]
        )
        if not diagnostic["valid"]:
            for metric in (
                "relative_wealth",
                "arithmetic_active_return_sum",
                "cumulative_return_difference",
                "positive_active_period_ratio",
                "negative_active_period_ratio",
                "tracking_error",
                "information_ratio",
            ):
                summary.append(summary_row("benchmark", f"{code}_{metric}", math.nan, notes="Invalid benchmark endpoint alignment."))
            continue

        aligned = aligned.sort_values("next_rebalance_date")
        for metric, value in benchmark_metrics(aligned).items():
            summary.append(summary_row("benchmark", f"{code}_{metric}", value, notes="Active return is arithmetic; cumulative relative performance uses relative wealth."))
        aligned["active_return"] = aligned["portfolio_net_return"] - aligned["benchmark_return"]
        for label, rows in (
            ("best", aligned.nlargest(5, "active_return")),
            ("worst", aligned.nsmallest(5, "active_return")),
        ):
            for rank, row in enumerate(rows.itertuples(index=False), start=1):
                summary.append(
                    summary_row(
                        "benchmark",
                        f"{code}_{label}_active_period_{rank}",
                        float(row.active_return),
                        notes=f"{row.rebalance_date.date()} to {row.next_rebalance_date.date()}",
                    )
                )


def analyze_costs(periods: pd.DataFrame, summary: list[dict[str, object]], qa: list[dict[str, object]]) -> None:
    scenarios: dict[float, pd.DataFrame] = {}
    for cost in (0.0, 0.001):
        frame = periods.loc[
            periods["universe_name"].eq(UNIVERSE_NAME)
            & np.isclose(periods["transaction_cost"], cost, equal_nan=False)
        ]
        scenarios[cost] = select_headline_periods(frame)
    left, right = scenarios[0.0], scenarios[0.001]
    try:
        aligned = align_cost_scenarios(left, right)
    except ValueError as error:
        row = reconciliation_row("cost_scenario_period_alignment", 1.0, 0.0)
        row["notes"] = str(error)
        qa.append(row)
        for metric in (
            "gross_cumulative_return",
            "net_cumulative_return_cost_0",
            "net_cumulative_return_cost_0.001",
            "arithmetic_cost_sum",
            "compounded_terminal_nav_difference",
            "average_turnover",
            "highest_turnover",
            "cost_impact_as_share_of_gross_return",
        ):
            summary.append(summary_row("cost", metric, math.nan, notes=str(error), cost=0.001))
        return
    qa.append(reconciliation_row("cost_scenario_period_alignment", len(aligned), len(left)))
    qa.append(
        reconciliation_row(
            "cost_scenarios_gross_returns",
            float(
                np.max(
                    np.abs(
                        aligned["gross_return_cost_0"].to_numpy()
                        - aligned["gross_return_cost_0.001"].to_numpy()
                    )
                )
            ),
            0.0,
        )
    )

    gross_cumulative = float(np.prod(1.0 + left["gross_return"]) - 1.0)
    net_zero = float(np.prod(1.0 + left["net_return"]) - 1.0)
    net_cost = float(np.prod(1.0 + right["net_return"]) - 1.0)
    highest = right.loc[right["turnover"].idxmax()]
    metrics = {
        "gross_cumulative_return": gross_cumulative,
        "net_cumulative_return_cost_0": net_zero,
        "net_cumulative_return_cost_0.001": net_cost,
        "arithmetic_cost_sum": float(right["cost_drag"].sum()),
        "compounded_terminal_nav_difference": net_zero - net_cost,
        "average_turnover": float(right["turnover"].mean()),
        "highest_turnover": float(highest["turnover"]),
        "cost_impact_as_share_of_gross_return": ((net_zero - net_cost) / gross_cumulative if gross_cumulative else math.nan),
    }
    for metric, value in metrics.items():
        notes = f"Highest turnover period starts {highest['rebalance_date'].date()}." if metric == "highest_turnover" else ""
        summary.append(summary_row("cost", metric, value, notes=notes, cost=0.001))


def analyze_drawdown(
    detail: pd.DataFrame,
    periods: pd.DataFrame,
    nav: pd.DataFrame,
    universe: pd.DataFrame,
    summary: list[dict[str, object]],
    qa: list[dict[str, object]],
) -> dict[str, object]:
    primary = select_headline_periods(
        periods.loc[
            periods["universe_name"].eq(UNIVERSE_NAME)
            & np.isclose(periods["transaction_cost"], PRIMARY_COST, equal_nan=False)
        ]
    )
    nav_frame = primary.rename(columns={"next_rebalance_date": "period_end"})[["period_end", "nav"]]
    result = drawdown_window(nav_frame, pd.Timestamp(primary.iloc[0]["rebalance_date"]))
    window = detail.loc[
        detail["period_end"].gt(result["peak_date"])
        & detail["period_end"].le(result["trough_date"])
    ]
    stock_window = window.groupby("stock_code")["stock_contribution"].sum().sort_values()
    if not stock_window.empty:
        summary.append(summary_row("drawdown", "largest_negative_stock_code", stock_window.index[0]))
        summary.append(summary_row("drawdown", "largest_negative_stock_contribution", float(stock_window.iloc[0])))
        summary.append(summary_row("drawdown", "largest_positive_stock_code", stock_window.index[-1]))
        summary.append(summary_row("drawdown", "largest_positive_stock_contribution", float(stock_window.iloc[-1])))

    theme_map = theme_map_from_universe(universe)
    theme_window = fractional_theme_contributions(window, theme_map).groupby("theme")["theme_contribution"].sum()
    for theme, value in theme_window.items():
        summary.append(summary_row("drawdown", f"theme_contribution_{theme}", float(value)))

    nav_window = nav.loc[
        nav["universe_name"].eq(UNIVERSE_NAME)
        & np.isclose(nav["transaction_cost"], PRIMARY_COST, equal_nan=False)
        & flag_true(nav["headline_included"])
        & nav["next_rebalance_date"].gt(result["peak_date"])
        & nav["next_rebalance_date"].le(result["trough_date"])
    ].copy()
    nav_window["benchmark_code"] = nav_window["benchmark_code"].map(code6)
    for code, group in nav_window.groupby("benchmark_code"):
        portfolio_return = float(np.prod(1.0 + group["portfolio_net_return"]) - 1.0)
        benchmark_return = float(np.prod(1.0 + group["benchmark_return"]) - 1.0)
        summary.append(summary_row("drawdown", f"{code}_benchmark_return", benchmark_return))
        summary.append(summary_row("drawdown", f"{code}_portfolio_active_return", portfolio_return - benchmark_return))

    cost_window: dict[float, float] = {}
    for cost in (0.0, 0.001):
        frame = select_headline_periods(
            periods.loc[
                periods["universe_name"].eq(UNIVERSE_NAME)
                & np.isclose(periods["transaction_cost"], cost, equal_nan=False)
            ]
        )
        frame = frame.loc[
            frame["next_rebalance_date"].gt(result["peak_date"])
            & frame["next_rebalance_date"].le(result["trough_date"])
        ]
        cost_window[cost] = float(np.prod(1.0 + frame["net_return"]) - 1.0)
    summary.append(summary_row("drawdown", "transaction_cost_terminal_return_impact", cost_window[0.0] - cost_window[0.001], cost=0.001))
    for metric, value in result.items():
        summary.append(summary_row("drawdown", metric, value))
    summary.append(
        summary_row(
            "drawdown",
            "peak_to_trough_stock_contribution_sum",
            float(window["stock_contribution"].sum()),
            notes="Arithmetic sum; it is not expected to equal compounded period_endpoint_drawdown.",
        )
    )
    window_gross = window.groupby("period_index")["stock_contribution"].sum().sort_index()
    if window_gross.empty:
        linked_total = compounded_gross = 0.0
    else:
        linked_window = link_contributions(window, window_gross)
        linked_total = float(linked_window["linked_contribution"].sum())
        compounded_gross = float(np.prod(1.0 + window_gross) - 1.0)
    summary.append(summary_row("drawdown", "peak_to_trough_linked_contribution_sum", linked_total))
    summary.append(summary_row("drawdown", "peak_to_trough_compounded_gross_return", compounded_gross))
    qa.append(reconciliation_row("drawdown_window_linked_contribution", linked_total, compounded_gross))
    return result


def render_report(stock: pd.DataFrame, theme: pd.DataFrame, summary: pd.DataFrame, qa: pd.DataFrame) -> str:
    top_code = positive_contributor_code(stock)
    top_stock_text = "not available"
    if top_code is not None:
        top_stock = stock.loc[stock["stock_code"].astype(str).eq(top_code)].iloc[0]
        top_stock_text = f"{top_stock.stock_code} {top_stock.stock_name}"
    top_theme = theme.iloc[0]
    failed = int((~qa["pass"].astype(bool)).sum())
    max_error = float(pd.to_numeric(qa["absolute_error"], errors="coerce").max())

    def contributor_table(rows: pd.DataFrame) -> str:
        table = ["| Rank | Code | Name | Linked contribution |", "|---:|---|---|---:|"]
        for rank, row in enumerate(rows.itertuples(index=False), start=1):
            table.append(f"| {rank} | {row.stock_code} | {row.stock_name} | {row.linked_gross_contribution} |")
        return "\n".join(table)

    positive_table = contributor_table(
        stock.loc[stock["linked_gross_contribution"].gt(0)].nlargest(10, "linked_gross_contribution")
    )
    negative_table = contributor_table(
        stock.loc[stock["linked_gross_contribution"].lt(0)].nsmallest(10, "linked_gross_contribution")
    )
    theme_table = ["| Theme | Arithmetic contribution | Linked contribution |", "|---|---:|---:|"]
    for row in theme.sort_values("contribution_rank").itertuples(index=False):
        theme_table.append(f"| {row.theme} | {row.arithmetic_contribution_sum} | {row.linked_gross_contribution} |")
    coverage = summary.loc[
        summary["metric"].isin(
            {
                "universe_unique_stock_count",
                "attributed_stock_count",
                "never_eligible_in_headline_count",
                "never_eligible_in_headline_codes",
            }
        )
    ]
    coverage_lines = "\n".join(f"- {row.metric}: `{row.value}`" for row in coverage.itertuples(index=False))
    sections = []
    for section in ("concentration", "period_concentration", "drawdown", "benchmark", "cost", "leave_one_out"):
        rows = summary.loc[summary["section"].eq(section)]
        table = ["| Metric | Value | Notes |", "|---|---:|---|"]
        for row in rows.itertuples(index=False):
            table.append(f"| {row.metric} | {row.value} | {row.notes} |")
        sections.append(f"## {section.replace('_', ' ').title()}\n\n" + "\n".join(table))
    section_text = "\n\n".join(sections)
    return f"""# Stock Pool v1.2 Baseline Attribution

## Attribution scope

- universe: `{UNIVERSE_NAME}`
- primary transaction cost: `0`
- current-universe historical performance only
- formal_performance_conclusion_allowed=false

## Attribution Coverage

{coverage_lines}

## Contribution Overview

- Largest linked positive contributor: `{top_stock_text}`
- Largest theme linked contribution: `{top_theme.theme}`
- These are descriptive historical contributions, not removal or investment decisions.

### Top 10 Linked Positive Stock Contributors

{positive_table}

### Top 10 Linked Negative Stock Contributors

{negative_table}

### Theme Contribution Table

{chr(10).join(theme_table)}

## Interpretation boundaries

The report may motivate hypotheses about stock, theme, period concentration and
period-end drawdown sources. It does not attribute returns to market
capitalization, industry allocation, causality or historical tradability.

Benchmark active returns are arithmetic period differences used for tracking
error and information ratio. Cumulative relative performance is reported as
`portfolio_nav / benchmark_nav - 1`, never as compounded active returns.

The leave-one-out result is a reweighted counterfactual sensitivity diagnostic.
It is not evidence that the selected stock should be removed.

{section_text}

## QA

- reconciliation checks: `{len(qa)}`
- failed checks: `{failed}`
- maximum absolute reconciliation error: `{max_error}`
- tolerance: `atol={ATOL}`, `rtol={RTOL}`
- period_endpoint_drawdown is based on rebalance-period endpoints, not daily NAV.
- peak_to_trough_stock_contribution_sum is arithmetic and is not expected to equal compounded drawdown.
"""


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    output = frame.copy()
    for column in output.columns:
        if "date" in column:
            converted = pd.to_datetime(output[column], errors="coerce")
            output[column] = converted.dt.strftime("%Y-%m-%d").where(converted.notna(), "")
    output.to_csv(path, index=False, encoding="utf-8-sig")


def main() -> int:
    periods, nav, prices, universe = load_inputs()
    detail, qa = build_period_stock(periods, prices, universe)
    stock = build_stock_summary(detail)
    theme, theme_qa = build_theme_attribution(detail, universe)
    qa.extend(theme_qa)
    summary: list[dict[str, object]] = []

    add_concentration_rows(summary, "concentration", "stock", stock["linked_gross_contribution"])
    add_concentration_rows(summary, "concentration", "theme", theme["linked_gross_contribution"])
    period_linked = detail.groupby("period_index")["linked_contribution"].sum()
    add_concentration_rows(summary, "period_concentration", "period", period_linked)

    primary_periods = select_headline_periods(
        periods.loc[
            periods["universe_name"].eq(UNIVERSE_NAME)
            & np.isclose(periods["transaction_cost"], PRIMARY_COST, equal_nan=False)
        ]
    )
    coverage = attribution_coverage(universe, detail)
    for metric, value in coverage.items():
        summary.append(summary_row("concentration", metric, value, coverage["universe_unique_stock_count"], "attribution coverage"))
    analyze_drawdown(detail, periods, nav, universe, summary, qa)

    top_code = positive_contributor_code(stock)
    if top_code is None:
        loo_metrics = {
            "excluded_stock_code": None,
            "original_terminal_nav": math.nan,
            "counterfactual_terminal_nav": math.nan,
            "terminal_nav_difference": math.nan,
            "counterfactual_cumulative_return": math.nan,
            "counterfactual_period_endpoint_drawdown": math.nan,
            "invalid_period_count": math.nan,
        }
    else:
        counterfactual = leave_one_out_returns(detail[["period_index", "stock_code", "stock_return"]], top_code)
        invalid_count = int((~counterfactual["valid"]).sum())
        original_terminal = float(np.prod(1.0 + primary_periods["gross_return"]))
        counterfactual_terminal = float(counterfactual.iloc[-1]["nav"]) if not invalid_count else math.nan
        counterfactual_drawdown = (
            drawdown_window(
                pd.DataFrame({"period_end": primary_periods["next_rebalance_date"], "nav": counterfactual["nav"]}),
                pd.Timestamp(primary_periods.iloc[0]["rebalance_date"]),
            )["period_endpoint_drawdown"]
            if not invalid_count
            else math.nan
        )
        loo_metrics = {
            "excluded_stock_code": top_code,
            "original_terminal_nav": original_terminal,
            "counterfactual_terminal_nav": counterfactual_terminal,
            "terminal_nav_difference": counterfactual_terminal - original_terminal,
            "counterfactual_cumulative_return": counterfactual_terminal - 1.0,
            "counterfactual_period_endpoint_drawdown": counterfactual_drawdown,
            "invalid_period_count": invalid_count,
        }
    for metric, value in loo_metrics.items():
        summary.append(summary_row("leave_one_out", metric, value, notes="leave_one_out_counterfactual=true; ex-post sensitivity only."))

    analyze_benchmarks(nav, primary_periods[PERIOD_KEYS], summary, qa)
    analyze_costs(periods, summary, qa)
    qa_frame = pd.DataFrame(qa)
    summary_frame = pd.DataFrame(summary)

    write_csv(detail, REPORTS / "baseline_attribution_period_stock_v1_2.csv")
    write_csv(stock, REPORTS / "baseline_attribution_stock_v1_2.csv")
    write_csv(theme, REPORTS / "baseline_attribution_theme_v1_2.csv")
    write_csv(summary_frame, REPORTS / "baseline_attribution_summary_v1_2.csv")
    write_csv(qa_frame, REPORTS / "baseline_attribution_qa_v1_2.csv")
    (REPORTS / "baseline_attribution_v1_2.md").write_text(
        render_report(stock, theme, summary_frame, qa_frame), encoding="utf-8"
    )

    critical_failures = qa_frame.loc[qa_frame["critical"].astype(bool) & ~qa_frame["pass"].astype(bool)]
    print(f"period-stock rows={len(detail)}, stocks={len(stock)}, QA failures={len(critical_failures)}")
    return critical_qa_exit_code(qa_frame)


if __name__ == "__main__":
    raise SystemExit(main())
