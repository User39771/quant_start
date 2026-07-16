"""Point-in-time MOM60 research inside the current Stock Pool v1.2 universe."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "processed"
REPORTS = ROOT / "reports"
PERIODS_PATH = REPORTS / "adjusted_stock_pool_baseline_periods_v1_2.csv"
PRICES_PATH = DATA / "adjusted_price_panel_v1_2.csv"
UNIVERSE_PATH = DATA / "backtest_universe_research_v1_2.csv"
BENCHMARK_PATH = DATA / "hybrid_benchmark_panel_v1_2.csv"

UNIVERSE_NAME = "research_universe_v1_2"
LOOKBACKS = (40, 60, 80)
PRIMARY_FACTOR = "MOM60"
MIN_EVALUATION_COUNT = 25
MIN_COVERAGE = 0.80
MIN_GROUP_SIGNAL_COUNT = 5
MIN_GROUP_LABEL_COUNT = 4
MIN_GROUP_LABEL_COVERAGE = 0.80
ANNUALIZATION = math.sqrt(252 / 20)
DIRECTION_EPSILON = 1e-12
ATOL = 1e-10
RTOL = 1e-8

METADATA = {
    "research_only": True,
    "primary_factor": PRIMARY_FACTOR,
    "primary_lookback_trading_days": 60,
    "forward_horizon_trading_days": 20,
    "signal_construction_point_in_time": True,
    "universe_point_in_time": False,
    "current_universe_historical_research": True,
    "formal_performance_conclusion_allowed": False,
    "execution_sim_ready": False,
    "no_investment_conclusion": True,
}


def code6(value: object) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    if not text.isdigit() or len(text) > 6:
        raise ValueError(f"Invalid stock code: {value!r}")
    return text.zfill(6)


def flag_true(series: pd.Series) -> pd.Series:
    return series.astype(str).str.strip().str.lower().isin({"true", "1", "yes"})


def parse_codes(value: object, expected_count: int) -> list[str]:
    codes = [part.strip() for part in str(value).split(";") if part.strip()]
    if len(codes) != expected_count:
        raise ValueError(f"eligible_count={expected_count}, parsed={len(codes)}")
    if any(len(code) != 6 or not code.isdigit() for code in codes):
        raise ValueError(f"Malformed eligible_codes: {codes}")
    if len(codes) != len(set(codes)):
        raise ValueError(f"Duplicate eligible_codes: {codes}")
    return codes


def market_calendar(benchmark: pd.DataFrame) -> list[pd.Timestamp]:
    frame = benchmark.copy()
    frame["benchmark_code"] = frame["benchmark_code"].map(code6)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    hs300 = frame.loc[frame["benchmark_code"].eq("000300") & (frame["close"] > 0)]
    if hs300.empty:
        raise ValueError("000300 has no valid market dates")
    if hs300["trade_date"].duplicated().any():
        raise ValueError("000300 market calendar contains duplicate dates")
    return sorted(hs300["trade_date"].tolist())


def lookback_endpoints(calendar: list[pd.Timestamp], rebalance_date: pd.Timestamp) -> dict[str, pd.Timestamp]:
    rebalance_date = pd.Timestamp(rebalance_date)
    try:
        rebalance_index = calendar.index(rebalance_date)
    except ValueError as error:
        raise ValueError(f"Rebalance date is not in market calendar: {rebalance_date.date()}") from error
    signal_index = rebalance_index - 1
    if signal_index < max(LOOKBACKS):
        raise ValueError(f"Insufficient calendar history before {rebalance_date.date()}")
    result = {"signal_as_of_date": calendar[signal_index]}
    for lookback in LOOKBACKS:
        result[f"lookback_{lookback}_date"] = calendar[signal_index - lookback]
    return result


def assign_signal_quantiles(frame: pd.DataFrame, factor_column: str) -> pd.DataFrame:
    result = frame.copy()
    result["signal_available"] = pd.to_numeric(result[factor_column], errors="coerce").notna()
    result["label_available"] = pd.to_numeric(result["forward_return"], errors="coerce").notna()
    result["signal_sample_member"] = result["baseline_eligible"].astype(bool) & result["signal_available"]
    result["evaluation_sample_member"] = result["signal_sample_member"] & result["label_available"]
    result["quantile"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    signal = result.loc[result["signal_sample_member"]].sort_values(
        [factor_column, "stock_code"], kind="stable"
    )
    if len(signal) < 5 or signal[factor_column].nunique() < 2:
        return result
    for quantile, indices in enumerate(np.array_split(signal.index.to_numpy(), 5), start=1):
        result.loc[indices, "quantile"] = quantile
    return result


def rank_ic(signal: pd.Series, label: pd.Series, minimum_count: int = MIN_EVALUATION_COUNT) -> float:
    pair = pd.DataFrame({"signal": signal, "label": label}).replace([np.inf, -np.inf], np.nan).dropna()
    if len(pair) < minimum_count or pair["signal"].nunique() < 2 or pair["label"].nunique() < 2:
        return math.nan
    return float(pair["signal"].rank(method="average").corr(pair["label"].rank(method="average")))


def quantile_monotonicity(means: pd.Series, universe_mean: float) -> dict[str, object]:
    ordered = means.reindex(range(1, 6))
    if ordered.isna().any():
        return {
            "quantile_return_spearman": math.nan,
            "q5_above_q1": False,
            "q5_above_universe": False,
            "strictly_monotonic": False,
        }
    return {
        "quantile_return_spearman": rank_ic(
            pd.Series(range(1, 6), dtype=float), ordered.reset_index(drop=True), minimum_count=5
        ),
        "q5_above_q1": bool(ordered.loc[5] > ordered.loc[1]),
        "q5_above_universe": bool(ordered.loc[5] > universe_mean),
        "strictly_monotonic": bool(np.all(np.diff(ordered.to_numpy()) > 0)),
    }


def q5_stock_contributions(q5_members: pd.DataFrame) -> pd.DataFrame:
    if q5_members.empty:
        return pd.DataFrame(
            columns=["stock_code", "q5_count", "q5_cumulative_arithmetic_contribution"]
        )
    detail = q5_members.copy()
    detail["q5_period_count"] = detail.groupby("period_index")["stock_code"].transform("count")
    detail["q5_contribution"] = detail["forward_return"] / detail["q5_period_count"]
    return detail.groupby("stock_code", as_index=False).agg(
        q5_count=("period_index", "count"),
        q5_cumulative_arithmetic_contribution=("q5_contribution", "sum"),
    )


def mark_continuous_interval(readiness: pd.DataFrame, confirmation_periods: int = 3) -> pd.DataFrame:
    result = readiness.copy().reset_index(drop=True)
    valid = result["primary_period_valid"].astype(bool).tolist()
    start = next(
        (
            index
            for index in range(len(valid) - confirmation_periods + 1)
            if all(valid[index : index + confirmation_periods])
        ),
        None,
    )
    phases = ["pre_start_diagnostic"] * len(result)
    if start is not None:
        terminated = False
        for index in range(start, len(result)):
            if terminated:
                phases[index] = "post_termination_diagnostic"
            elif valid[index]:
                phases[index] = "main"
            else:
                phases[index] = "termination_period"
                terminated = True
    result["period_phase"] = phases
    result["main_period_member"] = result["period_phase"].eq("main")
    return result


def assess_hypothesis(
    validation_mean_ic: float,
    validation_mean_spread: float,
    auxiliary_passes: list[bool],
) -> str:
    primary = [validation_mean_ic > DIRECTION_EPSILON, validation_mean_spread > DIRECTION_EPSILON]
    if all(primary) and sum(auxiliary_passes) >= 4:
        return "directionally_supported_for_strategy_prototyping"
    if not any(primary):
        return "not_supported"
    return "mixed"


def critical_exit_code(qa: pd.DataFrame) -> int:
    return 2 if bool((qa["critical"].astype(bool) & ~qa["pass"].astype(bool)).any()) else 0


def prepare_prices(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["stock_code"] = result["stock_code"].map(code6)
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="raise")
    if result.duplicated(["stock_code", "trade_date"]).any():
        raise ValueError("Duplicate stock_code/trade_date in adjusted panel")
    true_rows = flag_true(result["adjusted_flag"])
    for column in ("adjusted_close", "qfq_close"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    valid = result.loc[true_rows]
    if (valid[["adjusted_close", "qfq_close"]] <= 0).any().any():
        raise ValueError("Adjusted qfq rows contain non-positive price")
    if not np.allclose(valid["adjusted_close"], valid["qfq_close"], atol=ATOL, rtol=RTOL):
        raise ValueError("adjusted_close and qfq_close disagree")
    return valid[["stock_code", "trade_date", "adjusted_close"]].copy()


def build_factor_panel(
    periods: pd.DataFrame,
    universe: pd.DataFrame,
    prices: pd.DataFrame,
    calendar: list[pd.Timestamp],
) -> pd.DataFrame:
    codes = sorted(universe["code"].map(code6).unique())
    lookup = prices.set_index(["stock_code", "trade_date"])["adjusted_close"].to_dict()
    rows: list[dict[str, object]] = []
    for period_index, period in periods.reset_index(drop=True).iterrows():
        rebalance = pd.Timestamp(period["rebalance_date"])
        period_end = pd.Timestamp(period["next_rebalance_date"])
        endpoints = lookback_endpoints(calendar, rebalance)
        eligible = set(parse_codes(period["eligible_codes"], int(period["eligible_count"])))
        for code in codes:
            row: dict[str, object] = {
                "period_index": period_index,
                "stock_code": code,
                "rebalance_date": rebalance,
                "next_rebalance_date": period_end,
                **endpoints,
                "baseline_eligible": code in eligible,
            }
            as_of_price = lookup.get((code, endpoints["signal_as_of_date"]))
            row["signal_as_of_available"] = as_of_price is not None
            for lookback in LOOKBACKS:
                start_price = lookup.get((code, endpoints[f"lookback_{lookback}_date"]))
                row[f"lookback_{lookback}_available"] = start_price is not None
                row[f"mom{lookback}"] = (
                    as_of_price / start_price - 1.0
                    if as_of_price is not None and start_price is not None
                    else math.nan
                )
            start = lookup.get((code, rebalance))
            end = lookup.get((code, period_end))
            row["forward_return"] = start and end and end / start - 1.0
            rows.append(row)
    panel = pd.DataFrame(rows)
    grouped = []
    for _, group in panel.groupby("period_index", sort=True):
        grouped.append(assign_signal_quantiles(group, "mom60"))
    panel = pd.concat(grouped, ignore_index=True)
    panel["sample_basis"] = "mom60_primary_sample"
    for lookback in LOOKBACKS:
        panel[f"mom{lookback}_outlier"] = panel[f"mom{lookback}"].abs() > 2.0
    panel["forward_return_outlier"] = panel["forward_return"].abs() > 0.50
    reasons = []
    for row in panel.itertuples(index=False):
        reason = []
        if not row.baseline_eligible:
            reason.append("not_baseline_eligible")
        if pd.isna(row.mom60):
            reason.append("mom60_endpoint_missing")
        if pd.isna(row.forward_return):
            reason.append("forward_endpoint_missing")
        reasons.append(";".join(reason))
    panel["exclusion_reason"] = reasons
    return panel


def build_readiness(panel: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    period_rows: list[dict[str, object]] = []
    for period_index, group in panel.groupby("period_index", sort=True):
        eligible = group.loc[group["baseline_eligible"]]
        signal = group.loc[group["signal_sample_member"]]
        evaluation = group.loc[group["evaluation_sample_member"]]
        row: dict[str, object] = {
            "row_type": "period",
            "period_index": period_index,
            "rebalance_date": group.iloc[0]["rebalance_date"],
            "signal_as_of_date": group.iloc[0]["signal_as_of_date"],
            "lookback_start_date": group.iloc[0]["lookback_60_date"],
            "next_rebalance_date": group.iloc[0]["next_rebalance_date"],
            "baseline_eligible_count": len(eligible),
            "signal_available_count": len(signal),
            "forward_return_available_count": int(eligible["forward_return"].notna().sum()),
            "jointly_usable_count": len(evaluation),
            "signal_coverage_ratio": len(signal) / len(eligible) if len(eligible) else 0.0,
            "label_coverage_ratio": len(evaluation) / len(signal) if len(signal) else 0.0,
            "jointly_usable_ratio": len(evaluation) / len(eligible) if len(eligible) else 0.0,
        }
        group_valid = True
        for quantile in range(1, 6):
            q_signal = signal.loc[signal["quantile"].eq(quantile)]
            q_label = q_signal.loc[q_signal["label_available"]]
            coverage = len(q_label) / len(q_signal) if len(q_signal) else 0.0
            row[f"q{quantile}_signal_count"] = len(q_signal)
            row[f"q{quantile}_label_count"] = len(q_label)
            row[f"q{quantile}_label_coverage"] = coverage
            group_valid &= (
                len(q_signal) >= MIN_GROUP_SIGNAL_COUNT
                and len(q_label) >= MIN_GROUP_LABEL_COUNT
                and coverage >= MIN_GROUP_LABEL_COVERAGE
            )
        varied = evaluation["mom60"].nunique() >= 2 and evaluation["forward_return"].nunique() >= 2
        row["ic_valid"] = len(evaluation) >= MIN_EVALUATION_COUNT and varied
        row["quantile_valid"] = group_valid and signal["quantile"].notna().all()
        row["readiness_pass"] = (
            row["jointly_usable_ratio"] >= MIN_COVERAGE
            and len(evaluation) >= MIN_EVALUATION_COUNT
            and group_valid
        )
        row["primary_period_valid"] = row["readiness_pass"] and row["ic_valid"] and row["quantile_valid"]
        excluded = eligible.loc[~eligible["evaluation_sample_member"], "stock_code"].tolist()
        row["excluded_codes"] = ";".join(excluded)
        row["exclusion_reasons"] = ";".join(
            sorted(set(eligible.loc[~eligible["evaluation_sample_member"], "exclusion_reason"]) - {""})
        )
        period_rows.append(row)
    period = mark_continuous_interval(pd.DataFrame(period_rows))

    stock = panel.groupby("stock_code", as_index=False).agg(
        signal_availability_count=("signal_sample_member", "sum"),
        forward_label_availability_count=("evaluation_sample_member", "sum"),
        missing_lookback_endpoint_count=("lookback_60_available", lambda values: int((~values).sum())),
        missing_as_of_endpoint_count=("signal_as_of_available", lambda values: int((~values).sum())),
        missing_forward_endpoint_count=("forward_return", lambda values: int(values.isna().sum())),
    )
    usable = panel.loc[panel["signal_sample_member"]]
    dates = usable.groupby("stock_code")["signal_as_of_date"].agg(["min", "max"])
    stock = stock.join(dates, on="stock_code").rename(
        columns={"min": "first_usable_signal_date", "max": "last_usable_signal_date"}
    )
    stock.insert(0, "row_type", "stock")
    return period, stock


def evaluate_factor_periods(
    panel: pd.DataFrame,
    main_periods: set[int],
    factor_name: str,
    sample_basis: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    factor_column = factor_name.lower()
    ic_rows: list[dict[str, object]] = []
    quantile_rows: list[dict[str, object]] = []
    for period_index in sorted(main_periods):
        group = panel.loc[panel["period_index"].eq(period_index)].copy()
        if sample_basis == "mom60_primary_sample":
            assigned = group
        else:
            common = group["baseline_eligible"] & group[["mom40", "mom60", "mom80"]].notna().all(axis=1)
            temp = group.copy()
            temp["baseline_eligible"] = common
            assigned = assign_signal_quantiles(temp, factor_column)
        evaluation = assigned.loc[assigned["evaluation_sample_member"]]
        ic = rank_ic(evaluation[factor_column], evaluation["forward_return"])
        ic_rows.append(
            {
                "factor_name": factor_name,
                "sample_basis": sample_basis,
                "period_index": period_index,
                "rebalance_date": group.iloc[0]["rebalance_date"],
                "next_rebalance_date": group.iloc[0]["next_rebalance_date"],
                "evaluation_count": len(evaluation),
                "rank_ic": ic,
                "ic_valid": pd.notna(ic),
            }
        )
        returns: dict[int, float] = {}
        valid = True
        for quantile in range(1, 6):
            signal_q = assigned.loc[assigned["signal_sample_member"] & assigned["quantile"].eq(quantile)]
            label_q = signal_q.loc[signal_q["label_available"]]
            coverage = len(label_q) / len(signal_q) if len(signal_q) else 0.0
            q_valid = len(label_q) >= 4 and coverage >= 0.80
            valid &= q_valid
            returns[quantile] = float(label_q["forward_return"].mean()) if q_valid else math.nan
            quantile_rows.append(
                {
                    "factor_name": factor_name,
                    "sample_basis": sample_basis,
                    "period_index": period_index,
                    "rebalance_date": group.iloc[0]["rebalance_date"],
                    "next_rebalance_date": group.iloc[0]["next_rebalance_date"],
                    "portfolio": f"Q{quantile}",
                    "signal_count": len(signal_q),
                    "label_count": len(label_q),
                    "label_coverage": coverage,
                    "quantile_valid": q_valid,
                    "period_return": returns[quantile],
                }
            )
        universe_return = float(evaluation["forward_return"].mean()) if len(evaluation) else math.nan
        extras = {
            "UNIVERSE": universe_return,
            "Q5-Q1": returns[5] - returns[1] if valid else math.nan,
            "Q5-UNIVERSE": returns[5] - universe_return if valid else math.nan,
        }
        for portfolio, value in extras.items():
            quantile_rows.append(
                {
                    "factor_name": factor_name,
                    "sample_basis": sample_basis,
                    "period_index": period_index,
                    "rebalance_date": group.iloc[0]["rebalance_date"],
                    "next_rebalance_date": group.iloc[0]["next_rebalance_date"],
                    "portfolio": portfolio,
                    "signal_count": len(assigned.loc[assigned["signal_sample_member"]]),
                    "label_count": len(evaluation),
                    "label_coverage": len(evaluation) / max(1, len(assigned.loc[assigned["signal_sample_member"]])),
                    "quantile_valid": valid,
                    "period_return": value,
                }
            )
    return pd.DataFrame(ic_rows), pd.DataFrame(quantile_rows)


def endpoint_drawdown(returns: pd.Series) -> float:
    nav = (1.0 + returns).cumprod()
    return float((nav / pd.concat([pd.Series([1.0]), nav], ignore_index=True).cummax().iloc[1:].to_numpy() - 1.0).min()) if len(nav) else math.nan


def summarize_ic(ic: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (factor, basis), group in ic.groupby(["factor_name", "sample_basis"]):
        values = group["rank_ic"].dropna()
        std = float(values.std(ddof=1))
        rows.append(
            {
                "factor_name": factor,
                "sample_basis": basis,
                "period_count": len(values),
                "mean_rank_ic": float(values.mean()),
                "median_rank_ic": float(values.median()),
                "rank_ic_std": std,
                "rank_ic_positive_ratio": float((values > 0).mean()),
                "rank_ic_t_stat": float(values.mean() / (std / math.sqrt(len(values)))) if std and len(values) else math.nan,
                "annualized_icir": float(values.mean() / std * ANNUALIZATION) if std else math.nan,
            }
        )
    return pd.DataFrame(rows)


def summarize_quantiles(quantiles: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for keys, group in quantiles.groupby(["factor_name", "sample_basis", "portfolio"]):
        values = group.loc[group["quantile_valid"], "period_return"].dropna()
        rows.append(
            {
                "factor_name": keys[0],
                "sample_basis": keys[1],
                "portfolio": keys[2],
                "period_count": len(values),
                "mean_return": float(values.mean()),
                "median_return": float(values.median()),
                "positive_ratio": float((values > 0).mean()),
                "annualized_volatility": float(values.std(ddof=1) * ANNUALIZATION),
                "cumulative_nav": float((1.0 + values).prod()),
                "period_endpoint_drawdown": endpoint_drawdown(values.reset_index(drop=True)),
            }
        )
    summary = pd.DataFrame(rows)
    extra = []
    for (factor, basis), group in summary.loc[summary["portfolio"].str.match(r"Q[1-5]$")].groupby(
        ["factor_name", "sample_basis"]
    ):
        means = group.assign(number=group["portfolio"].str[1:].astype(int)).set_index("number")["mean_return"]
        universe = summary.loc[
            summary["factor_name"].eq(factor)
            & summary["sample_basis"].eq(basis)
            & summary["portfolio"].eq("UNIVERSE"),
            "mean_return",
        ]
        metrics = quantile_monotonicity(means, float(universe.iloc[0]) if len(universe) else math.nan)
        extra.append(
            {
                "factor_name": factor,
                "sample_basis": basis,
                "portfolio": "MONOTONICITY",
                **metrics,
            }
        )
    return pd.concat([summary, pd.DataFrame(extra)], ignore_index=True, sort=False)


def stability_rows(ic: pd.DataFrame, quantiles: pd.DataFrame, panel: pd.DataFrame) -> pd.DataFrame:
    primary_ic = ic.loc[(ic["factor_name"] == "MOM60") & (ic["sample_basis"] == "mom60_primary_sample")]
    primary_q = quantiles.loc[(quantiles["factor_name"] == "MOM60") & (quantiles["sample_basis"] == "mom60_primary_sample")]
    spread = primary_q.loc[primary_q["portfolio"].eq("Q5-Q1"), ["period_index", "period_return"]].rename(columns={"period_return": "spread"})
    q5 = primary_q.loc[primary_q["portfolio"].eq("Q5"), ["period_index", "period_return"]].rename(columns={"period_return": "q5"})
    universe = primary_q.loc[primary_q["portfolio"].eq("UNIVERSE"), ["period_index", "period_return"]].rename(columns={"period_return": "universe"})
    base = primary_ic.merge(spread, on="period_index").merge(q5, on="period_index").merge(universe, on="period_index")
    base["year"] = pd.to_datetime(base["rebalance_date"]).dt.year
    rows: list[dict[str, object]] = []
    segments = {
        "all_history": base,
        "development": base.loc[pd.to_datetime(base["rebalance_date"]) < pd.Timestamp("2024-01-01")],
        "historical_validation": base.loc[pd.to_datetime(base["rebalance_date"]) >= pd.Timestamp("2024-01-01")],
    }
    segments.update({f"year_{year}": group for year, group in base.groupby("year")})
    for segment, group in segments.items():
        valid_year = not segment.startswith("year_") or len(group) >= 6
        rows.append(
            {
                "row_type": "segment",
                "segment": segment,
                "status": "ok" if valid_year else "insufficient_periods",
                "period_count": len(group),
                "mean_rank_ic": float(group["rank_ic"].mean()),
                "rank_ic_positive_ratio": float((group["rank_ic"] > 0).mean()),
                "mean_q5_q1": float(group["spread"].mean()),
                "mean_q5_universe": float((group["q5"] - group["universe"]).mean()),
                "cumulative_q5_nav": float((1 + group["q5"]).prod()),
                "cumulative_universe_nav": float((1 + group["universe"]).prod()),
            }
        )
    for label, selected in (
        ("rank_ic_best", base.nlargest(5, "rank_ic")),
        ("rank_ic_worst", base.nsmallest(5, "rank_ic")),
        ("spread_best", base.nlargest(5, "spread")),
        ("spread_worst", base.nsmallest(5, "spread")),
    ):
        for row in selected.itertuples(index=False):
            rows.append({"row_type": "period_extreme", "segment": label, "period_index": row.period_index, "value": row.rank_ic if "rank_ic" in label else row.spread})
    q5_members = panel.loc[panel["quantile"].eq(5) & panel["evaluation_sample_member"]]
    q5_stock = q5_stock_contributions(q5_members)
    for row in q5_stock.itertuples(index=False):
        rows.append({"row_type": "q5_stock", "segment": "q5_concentration", "stock_code": row.stock_code, "q5_count": row.q5_count, "q5_cumulative_arithmetic_contribution": row.q5_cumulative_arithmetic_contribution})
    for row in base.itertuples(index=False):
        rows.append({"row_type": "spread_period", "segment": "q5_q1_arithmetic_contribution", "period_index": row.period_index, "value": row.spread})
    return pd.DataFrame(rows)


def qa_row(check: str, actual: float, expected: float, critical: bool = True, notes: str = "") -> dict[str, object]:
    absolute = abs(actual - expected)
    relative = absolute / abs(expected) if expected else (0.0 if not absolute else math.inf)
    return {
        "check": check,
        "actual": actual,
        "expected": expected,
        "absolute_error": absolute,
        "relative_error": relative,
        "atol": ATOL,
        "rtol": RTOL,
        "pass": bool(np.isclose(actual, expected, atol=ATOL, rtol=RTOL)),
        "critical": critical,
        "notes": notes,
    }


def eligibility_contract_probe() -> None:
    try:
        from scripts.run_adjusted_stock_pool_baseline_v1_2 import Boundary, evaluate_period
    except ModuleNotFoundError:
        from run_adjusted_stock_pool_baseline_v1_2 import Boundary, evaluate_period
    start, end = pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")
    result = evaluate_period(["000001"], {("000001", start): 1.0}, Boundary(start, end, 20, "full"))
    if result["eligible_codes"] != "000001" or result["end_price_missing_codes"] != "000001":
        raise ValueError("Baseline eligibility contract is not start-date-only")


def add_metadata(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for key, value in METADATA.items():
        result[key] = value
    return result


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    output = add_metadata(frame)
    for column in output.columns:
        if "date" in column:
            parsed = pd.to_datetime(output[column], errors="coerce")
            output[column] = parsed.dt.strftime("%Y-%m-%d").where(parsed.notna(), "")
        if column == "stock_code":
            populated = output[column].notna() & output[column].astype(str).str.strip().ne("")
            output.loc[populated, column] = output.loc[populated, column].map(code6)
    output.to_csv(path, index=False, encoding="utf-8-sig")


def empty_results() -> dict[str, pd.DataFrame]:
    return {
        "ic_periods": pd.DataFrame(columns=["factor_name", "sample_basis", "period_index", "rank_ic"]),
        "ic_summary": pd.DataFrame(columns=["factor_name", "sample_basis", "period_count", "mean_rank_ic"]),
        "quantile_returns": pd.DataFrame(columns=["factor_name", "sample_basis", "period_index", "portfolio", "period_return"]),
        "quantile_summary": pd.DataFrame(columns=["factor_name", "sample_basis", "portfolio", "mean_return"]),
        "stability": pd.DataFrame(columns=["row_type", "segment", "status"]),
        "hypothesis": pd.DataFrame(columns=["metric", "value", "status", "sample_basis"]),
    }


def render_report(
    status: str,
    verdict: str | None,
    period_count: int,
    validation_count: int,
    readiness: pd.DataFrame | None = None,
    ic_summary: pd.DataFrame | None = None,
    quantile_summary: pd.DataFrame | None = None,
    stability: pd.DataFrame | None = None,
    hypothesis: pd.DataFrame | None = None,
) -> str:
    def table(frame: pd.DataFrame | None, columns: list[str]) -> str:
        if frame is None or frame.empty:
            return "No result: readiness gate did not permit this analysis."
        available = [column for column in columns if column in frame]
        rows = ["| " + " | ".join(available) + " |", "|" + "---|" * len(available)]
        for row in frame[available].itertuples(index=False, name=None):
            rows.append("| " + " | ".join(str(value) for value in row) + " |")
        return "\n".join(rows)

    period_readiness = (
        readiness.loc[readiness["row_type"].eq("period")]
        if readiness is not None and not readiness.empty
        else pd.DataFrame()
    )
    stability_segments = (
        stability.loc[stability["row_type"].eq("segment")]
        if stability is not None and not stability.empty
        else pd.DataFrame()
    )
    decision = (
        "Proceed only to a separate validation prototype."
        if verdict == "directionally_supported_for_strategy_prototyping"
        else "Stop the momentum strategy direction."
        if verdict == "not_supported"
        else "Collect more independent evidence before strategy prototyping."
    )
    return f"""# MOM60 Factor Research v1.3

## Research question

Does higher 60-market-day momentum predict higher forward approximately 20-day
cross-sectional returns inside the current AI and commercial-space universe?

## Status

- research_status: `{status}`
- verdict: `{verdict or 'not_available'}`
- primary factor: `MOM60`
- main period count: `{period_count}`
- historical validation period count: `{validation_count}`

## Hypothesis registration

- Primary: MOM60 predicts higher forward approximately 20-day cross-sectional returns.
- MOM40 and MOM80 are secondary robustness checks on a common signal sample.
- Direction epsilon: `{DIRECTION_EPSILON}`

## Data readiness

{table(period_readiness.tail(8), ['rebalance_date', 'jointly_usable_count', 'jointly_usable_ratio', 'readiness_pass', 'ic_valid', 'quantile_valid', 'period_phase'])}

## Leakage controls

Signals end on the market day before rebalance. Quantiles are assigned on the
signal sample before forward-label availability is applied. Exact market-calendar
endpoints are required; no forward-fill, backfill, or raw-close fallback is used.

## Universe and period selection

The complete panel contains every current-universe stock for every baseline headline
period. Baseline eligible codes are inherited unchanged. Signal samples are formed
before label availability; evaluation samples are used only after quantile assignment.

## Rank IC results

{table(ic_summary, ['factor_name', 'sample_basis', 'period_count', 'mean_rank_ic', 'median_rank_ic', 'rank_ic_positive_ratio', 'rank_ic_t_stat', 'annualized_icir'])}

## Quantile results

{table(quantile_summary, ['factor_name', 'sample_basis', 'portfolio', 'period_count', 'mean_return', 'median_return', 'cumulative_nav', 'period_endpoint_drawdown', 'quantile_return_spearman', 'strictly_monotonic'])}

Q5-Q1 is a research diagnostic, not an executable A-share long-short strategy.

## Time stability

{table(stability_segments, ['segment', 'status', 'period_count', 'mean_rank_ic', 'rank_ic_positive_ratio', 'mean_q5_q1', 'mean_q5_universe', 'cumulative_q5_nav', 'cumulative_universe_nav'])}

## MOM40/60/80 sensitivity

The MOM60 primary sample and the common 40/60/80 robustness sample are reported
separately through `sample_basis`. Robustness results cannot replace MOM60.

## Concentration diagnostics

Best/worst Rank IC periods, best/worst Q5-Q1 periods, all period spreads, and
equal-weighted Q5 stock contributions are stored in `factor_stability_mom60_v1_3.csv`.

## Hypothesis assessment

{table(hypothesis, ['metric', 'value', 'status', 'sample_basis'])}

## Limitations

- current-universe / survivorship-like bias remains.
- This is historical chronological validation, not clean preregistered OOS confirmation.
- Q5-Q1 is a research diagnostic, not an executable A-share long-short portfolio.
- formal_performance_conclusion_allowed=false
- execution_sim_ready=false
- no_investment_conclusion=true

## Next-stage decision

{decision}
"""


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    periods = pd.read_csv(PERIODS_PATH, dtype=str)
    prices = pd.read_csv(PRICES_PATH, dtype={"stock_code": str})
    universe = pd.read_csv(UNIVERSE_PATH, dtype={"code": str})
    benchmark = pd.read_csv(BENCHMARK_PATH, dtype={"benchmark_code": str})
    periods["transaction_cost"] = pd.to_numeric(periods["transaction_cost"], errors="coerce")
    periods["rebalance_date"] = pd.to_datetime(periods["rebalance_date"], errors="raise")
    periods["next_rebalance_date"] = pd.to_datetime(periods["next_rebalance_date"], errors="raise")
    periods = periods.loc[
        periods["universe_name"].eq(UNIVERSE_NAME)
        & np.isclose(periods["transaction_cost"], 0.0, equal_nan=False)
        & flag_true(periods["headline_included"])
        & periods["period_type"].eq("full")
        & periods["period_phase"].eq("headline")
    ].sort_values("rebalance_date").reset_index(drop=True)
    if periods.empty:
        raise ValueError("No research-universe cost=0 headline full periods")
    universe["code"] = universe["code"].map(code6)
    return periods, prepare_prices(prices), universe, benchmark


def run_research() -> tuple[int, str]:
    eligibility_contract_probe()
    periods, prices, universe, benchmark = load_inputs()
    calendar = market_calendar(benchmark)
    calendar_set = set(calendar)
    endpoints = set(periods["rebalance_date"]) | set(periods["next_rebalance_date"])
    if not endpoints.issubset(calendar_set):
        raise ValueError("Baseline period endpoint missing from 000300 market calendar")

    panel = build_factor_panel(periods, universe, prices, calendar)
    period_readiness, stock_readiness = build_readiness(panel)
    readiness = pd.concat([period_readiness, stock_readiness], ignore_index=True, sort=False)
    qa = [
        qa_row("factor_panel_row_count", len(panel), universe["code"].nunique() * len(periods)),
        qa_row("factor_panel_unique_key_count", len(panel.drop_duplicates(["stock_code", "period_index"])), len(panel)),
        qa_row("baseline_endpoints_in_market_calendar", float(endpoints.issubset(calendar_set)), 1.0),
        qa_row("signal_dates_before_rebalance", float((panel["signal_as_of_date"] < panel["rebalance_date"]).all()), 1.0),
        qa_row("lookback_before_signal", float((panel["lookback_60_date"] < panel["signal_as_of_date"]).all()), 1.0),
        qa_row("forward_end_after_rebalance", float((panel["next_rebalance_date"] > panel["rebalance_date"]).all()), 1.0),
        qa_row("signal_sample_subset_eligible", float((~panel["signal_sample_member"] | panel["baseline_eligible"]).all()), 1.0),
        qa_row("evaluation_sample_subset_signal", float((~panel["evaluation_sample_member"] | panel["signal_sample_member"]).all()), 1.0),
        qa_row("primary_factor_locked", float(PRIMARY_FACTOR == "MOM60"), 1.0),
    ]

    main_periods = set(period_readiness.loc[period_readiness["main_period_member"], "period_index"].astype(int))
    validation_count = int(
        period_readiness.loc[
            period_readiness["main_period_member"]
            & (pd.to_datetime(period_readiness["rebalance_date"]) >= pd.Timestamp("2024-01-01"))
        ].shape[0]
    )
    research_ready = len(main_periods) >= 12 and validation_count >= 6
    results = empty_results()
    verdict: str | None = None
    if research_ready:
        ic_frames, quantile_frames = [], []
        primary_ic, primary_q = evaluate_factor_periods(panel, main_periods, "MOM60", "mom60_primary_sample")
        ic_frames.append(primary_ic)
        quantile_frames.append(primary_q)
        for factor in ("MOM40", "MOM60", "MOM80"):
            ic_frame, q_frame = evaluate_factor_periods(panel, main_periods, factor, "common_40_60_80_robustness_sample")
            ic_frames.append(ic_frame)
            quantile_frames.append(q_frame)
        results["ic_periods"] = pd.concat(ic_frames, ignore_index=True)
        results["quantile_returns"] = pd.concat(quantile_frames, ignore_index=True)
        results["ic_summary"] = summarize_ic(results["ic_periods"])
        results["quantile_summary"] = summarize_quantiles(results["quantile_returns"])
        results["stability"] = stability_rows(results["ic_periods"], results["quantile_returns"], panel.loc[panel["period_index"].isin(main_periods)])

        primary_panel = panel.loc[panel["period_index"].isin(main_periods)]
        signal_counts = primary_panel.groupby("period_index")["signal_sample_member"].sum()
        assigned_counts = primary_panel.loc[primary_panel["quantile"].notna()].groupby("period_index").size().reindex(signal_counts.index, fill_value=0)
        evaluation_counts = primary_panel.groupby("period_index")["evaluation_sample_member"].sum()
        q_primary = results["quantile_returns"].loc[
            results["quantile_returns"]["factor_name"].eq("MOM60")
            & results["quantile_returns"]["sample_basis"].eq("mom60_primary_sample")
        ]
        q_label_counts = q_primary.loc[q_primary["portfolio"].str.match(r"Q[1-5]$")].groupby("period_index")["label_count"].sum().reindex(evaluation_counts.index, fill_value=0)
        spread_pivot = q_primary.pivot(index="period_index", columns="portfolio", values="period_return")
        spread_error = (spread_pivot["Q5-Q1"] - (spread_pivot["Q5"] - spread_pivot["Q1"])).abs().max()
        qa.extend(
            [
                qa_row("quantile_signal_count_reconciliation", float((assigned_counts - signal_counts).abs().max()), 0.0),
                qa_row("quantile_label_count_reconciliation", float((q_label_counts - evaluation_counts).abs().max()), 0.0),
                qa_row("q5_q1_reconciliation", float(spread_error), 0.0),
                qa_row("robustness_factor_set", float(set(results["ic_periods"]["factor_name"]) == {"MOM40", "MOM60", "MOM80"}), 1.0),
                qa_row("sample_basis_separation", float(set(results["ic_periods"]["sample_basis"]) == {"mom60_primary_sample", "common_40_60_80_robustness_sample"}), 1.0),
            ]
        )

        validation_ic = primary_ic.loc[pd.to_datetime(primary_ic["rebalance_date"]) >= pd.Timestamp("2024-01-01")]
        primary_spread = primary_q.loc[primary_q["portfolio"].eq("Q5-Q1")]
        validation_spread = primary_spread.loc[pd.to_datetime(primary_spread["rebalance_date"]) >= pd.Timestamp("2024-01-01"), "period_return"].dropna()
        validation_q5u = primary_q.loc[
            primary_q["portfolio"].eq("Q5-UNIVERSE")
            & (pd.to_datetime(primary_q["rebalance_date"]) >= pd.Timestamp("2024-01-01")),
            "period_return",
        ].dropna()
        valid_years = results["stability"].loc[
            results["stability"]["segment"].astype(str).str.startswith("year_")
            & results["stability"]["status"].eq("ok")
        ]
        yearly_direction = float(
            ((valid_years["mean_rank_ic"] > DIRECTION_EPSILON) & (valid_years["mean_q5_q1"] > DIRECTION_EPSILON)).mean()
        ) if len(valid_years) else 0.0
        robustness = {}
        for factor in ("MOM40", "MOM80"):
            f_ic = results["ic_periods"].loc[
                results["ic_periods"]["factor_name"].eq(factor)
                & (pd.to_datetime(results["ic_periods"]["rebalance_date"]) >= pd.Timestamp("2024-01-01")),
                "rank_ic",
            ].mean()
            f_spread = results["quantile_returns"].loc[
                results["quantile_returns"]["factor_name"].eq(factor)
                & results["quantile_returns"]["portfolio"].eq("Q5-Q1")
                & (pd.to_datetime(results["quantile_returns"]["rebalance_date"]) >= pd.Timestamp("2024-01-01")),
                "period_return",
            ].mean()
            robustness[factor] = (f_ic, f_spread)
        mean_ic = float(validation_ic["rank_ic"].mean())
        mean_spread = float(validation_spread.mean())
        leave_best = float(validation_spread.drop(validation_spread.idxmax()).mean()) if len(validation_spread) > 1 else math.nan
        auxiliary = [
            float((validation_ic["rank_ic"] > 0).mean()) > 0.5,
            float(validation_q5u.mean()) > DIRECTION_EPSILON,
            yearly_direction >= 0.60,
            not all(ic < -DIRECTION_EPSILON and spread < -DIRECTION_EPSILON for ic, spread in robustness.values()),
            leave_best > DIRECTION_EPSILON,
        ]
        verdict = assess_hypothesis(mean_ic, mean_spread, auxiliary)
        hypothesis_rows = [
            ("historical_validation_mean_rank_ic", mean_ic),
            ("historical_validation_mean_q5_q1", mean_spread),
            ("auxiliary_pass_count", sum(auxiliary)),
            ("leave_best_period_mean_q5_q1", leave_best),
            ("verdict", verdict),
        ]
        results["hypothesis"] = pd.DataFrame(
            [{"metric": metric, "value": value, "status": "ok", "sample_basis": "mom60_primary_sample"} for metric, value in hypothesis_rows]
        )

    qa_frame = pd.DataFrame(qa)
    if critical_exit_code(qa_frame):
        return 2, "critical_qa_failure"
    write_csv(panel, DATA / "mom60_factor_panel_v1_3.csv")
    write_csv(readiness, REPORTS / "factor_data_readiness_v1_3.csv")
    write_csv(results["ic_periods"], REPORTS / "factor_ic_periods_mom60_v1_3.csv")
    write_csv(results["ic_summary"], REPORTS / "factor_ic_summary_mom60_v1_3.csv")
    write_csv(results["quantile_returns"], REPORTS / "factor_quantile_returns_mom60_v1_3.csv")
    write_csv(results["quantile_summary"], REPORTS / "factor_quantile_summary_mom60_v1_3.csv")
    write_csv(results["stability"], REPORTS / "factor_stability_mom60_v1_3.csv")
    write_csv(results["hypothesis"], REPORTS / "factor_hypothesis_summary_v1_3.csv")
    write_csv(qa_frame, REPORTS / "factor_research_qa_v1_3.csv")
    status = "completed" if research_ready else "research_not_ready"
    (REPORTS / "factor_mom60_v1_3.md").write_text(
        render_report(
            status,
            verdict,
            len(main_periods),
            validation_count,
            readiness,
            results["ic_summary"],
            results["quantile_summary"],
            results["stability"],
            results["hypothesis"],
        ),
        encoding="utf-8",
    )
    return (0 if research_ready else 1), status


def main() -> int:
    try:
        code, status = run_research()
        print(f"MOM60 v1.3 status={status}")
        return code
    except Exception as error:
        qa = pd.DataFrame([qa_row("fatal_input_validation", 1.0, 0.0, notes=str(error))])
        write_csv(qa, REPORTS / "factor_research_qa_v1_3.csv")
        (REPORTS / "factor_mom60_v1_3.md").write_text(
            render_report("input_error", None, 0, 0) + f"\n\nFatal validation error: `{error}`\n",
            encoding="utf-8",
        )
        print(f"MOM60 v1.3 input error: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
