"""Research-only LOWVOL20 hypothesis test inside the frozen v1.2 universe."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd


UNIVERSE_NAME = "research_universe_v1_2"
LOOKBACKS = (10, 20, 40)
PRIMARY_FACTOR = "LOWVOL20"
MIN_COUNT = 25
MIN_COVERAGE = 0.80
MIN_GROUP_SIGNAL = 5
MIN_GROUP_LABEL = 4
MIN_GROUP_COVERAGE = 0.80
DIRECTION_EPSILON = 1e-12
ATOL = 1e-10
RTOL = 1e-8
BOOTSTRAP_REPLICATIONS = 2000
BOOTSTRAP_BLOCK_LENGTH = 3
BOOTSTRAP_SEED = 20260711

OUTPUT_FILES = (
    "data/processed/lowvol20_factor_panel_v1_4.csv",
    "reports/factor_data_readiness_lowvol20_v1_4.csv",
    "reports/factor_ic_periods_lowvol20_v1_4.csv",
    "reports/factor_ic_summary_lowvol20_v1_4.csv",
    "reports/factor_quantile_returns_lowvol20_v1_4.csv",
    "reports/factor_quantile_summary_lowvol20_v1_4.csv",
    "reports/factor_risk_summary_lowvol20_v1_4.csv",
    "reports/factor_stability_lowvol20_v1_4.csv",
    "reports/factor_hypothesis_summary_lowvol20_v1_4.csv",
    "reports/factor_research_qa_lowvol20_v1_4.csv",
    "reports/factor_lowvol20_v1_4.md",
)

METADATA = {
    "research_only": True,
    "primary_factor": PRIMARY_FACTOR,
    "underlying_measure": "VOL20",
    "primary_lookback_return_intervals": 20,
    "required_price_observations": 21,
    "target_rebalance_step": "20_baseline_calendar_entries",
    "forward_horizon_trading_days_approx": 20,
    "signal_construction_point_in_time": True,
    "universe_point_in_time": False,
    "current_universe_historical_research": True,
    "suspension_status_available": False,
    "execution_sim_ready": False,
    "formal_performance_conclusion_allowed": False,
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


def longest_true_run(values: np.ndarray) -> int:
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def window_statistics(
    prices: pd.Series,
    calendar: list[pd.Timestamp],
    signal_as_of_date: pd.Timestamp,
    lookback: int,
) -> dict[str, object]:
    position = {pd.Timestamp(date): index for index, date in enumerate(calendar)}
    end = pd.Timestamp(signal_as_of_date)
    if end not in position or position[end] < lookback:
        return {
            "window_start_date": pd.NaT,
            "price_observation_count": 0,
            "return_interval_count": 0,
            "volatility": math.nan,
            "lowvol": math.nan,
            "signal_available": False,
            "primary_reliable_signal": False,
            "zero_return_count": 0,
            "zero_return_ratio": math.nan,
            "longest_zero_return_run": 0,
            "unique_close_count": 0,
            "nonzero_return_count": 0,
            "price_change_range": math.nan,
            "flat_price_risk_flag": True,
            "daily_return_outlier": False,
            "volatility_outlier": False,
        }
    expected = calendar[position[end] - lookback : position[end] + 1]
    selected = prices.reindex(expected)
    exact = len(selected) == lookback + 1 and selected.notna().all() and (selected > 0).all()
    if not exact:
        result = window_statistics(pd.Series(dtype=float), [], pd.NaT, lookback)
        result["window_start_date"] = expected[0]
        result["price_observation_count"] = int(selected.notna().sum())
        return result
    returns = selected.pct_change().dropna()
    volatility = float(returns.std(ddof=1) * math.sqrt(252))
    zero = np.isclose(returns.to_numpy(dtype=float), 0.0, atol=ATOL, rtol=0)
    unique_close = int(selected.nunique())
    nonzero = int((~zero).sum())
    longest = longest_true_run(zero)
    reliable = (
        math.isfinite(volatility)
        and unique_close >= 3
        and nonzero >= 5
        and longest <= 5
    )
    return {
        "window_start_date": expected[0],
        "price_observation_count": len(selected),
        "return_interval_count": len(returns),
        "volatility": volatility,
        "lowvol": -volatility,
        "signal_available": math.isfinite(volatility),
        "primary_reliable_signal": reliable,
        "zero_return_count": int(zero.sum()),
        "zero_return_ratio": float(zero.mean()),
        "longest_zero_return_run": longest,
        "unique_close_count": unique_close,
        "nonzero_return_count": nonzero,
        "price_change_range": float(selected.max() / selected.min() - 1),
        "flat_price_risk_flag": not reliable,
        "daily_return_outlier": bool((returns.abs() > 0.25).any()),
        "volatility_outlier": volatility > 1.0,
    }


def forward_risk_statistics(
    prices: pd.Series,
    calendar: list[pd.Timestamp],
    start_date: pd.Timestamp,
    end_date: pd.Timestamp,
) -> dict[str, object]:
    position = {pd.Timestamp(date): index for index, date in enumerate(calendar)}
    start, end = pd.Timestamp(start_date), pd.Timestamp(end_date)
    if start not in position or end not in position or position[end] <= position[start]:
        raise ValueError("Invalid forward market endpoints")
    expected = calendar[position[start] : position[end] + 1]
    selected = prices.reindex(expected)
    exact = len(selected) == len(expected) and selected.notna().all() and (selected > 0).all()
    result = {
        "forward_market_interval_count": len(expected) - 1,
        "forward_price_observation_count": len(expected),
        "forward_exact_stock_price_count": int(selected.notna().sum()),
        "forward_realized_volatility": math.nan,
        "forward_risk_available": False,
    }
    if exact:
        returns = selected.pct_change().dropna()
        result["forward_realized_volatility"] = float(returns.std(ddof=1) * math.sqrt(252))
        result["forward_risk_available"] = True
    return result


def period_annualization(interval_counts: list[int]) -> dict[str, object]:
    if not interval_counts or min(interval_counts) <= 0:
        raise ValueError("Forward interval counts must be positive")
    median = float(np.median(interval_counts))
    return {
        "factor": math.sqrt(252 / median),
        "approximate": len(set(interval_counts)) != 1 or interval_counts[0] != 20,
        "minimum": int(min(interval_counts)),
        "median": median,
        "maximum": int(max(interval_counts)),
        "distribution": ";".join(
            f"{value}:{interval_counts.count(value)}" for value in sorted(set(interval_counts))
        ),
    }


def assign_quantiles(
    frame: pd.DataFrame,
    factor_column: str,
    reliable: bool,
) -> tuple[pd.DataFrame, dict[str, object]]:
    result = frame.copy()
    factor = pd.to_numeric(result[factor_column], errors="coerce")
    result["signal_available"] = factor.notna()
    result["label_available"] = pd.to_numeric(
        result["forward_return"], errors="coerce"
    ).notna()
    result["risk_label_available"] = result["forward_risk_available"].astype(bool)
    base = result["baseline_eligible"].astype(bool) & result["signal_available"]
    if reliable:
        base &= result["primary_reliable_signal"].astype(bool)
    result["signal_sample_member"] = base
    result["evaluation_sample_member"] = base & result["label_available"]
    result["risk_evaluation_sample_member"] = base & result["risk_label_available"]
    result["quantile"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    signal = result.loc[base].sort_values([factor_column, "stock_code"], kind="stable")
    counts = signal[factor_column].value_counts(dropna=False)
    diagnostics = {
        "signal_unique_value_count": int(signal[factor_column].nunique()),
        "largest_tie_group_count": int(counts.max()) if len(counts) else 0,
        "largest_tie_group_ratio": float(counts.max() / len(signal)) if len(signal) else math.nan,
        "quantile_valid": len(signal) >= 5 and signal[factor_column].nunique() >= 5,
    }
    if diagnostics["quantile_valid"]:
        for quantile, indices in enumerate(np.array_split(signal.index.to_numpy(), 5), 1):
            result.loc[indices, "quantile"] = quantile
    return result, diagnostics


def rank_ic(signal: pd.Series, label: pd.Series, minimum_count: int = MIN_COUNT) -> float:
    pair = pd.DataFrame({"signal": signal, "label": label}).replace(
        [np.inf, -np.inf], np.nan
    ).dropna()
    if (
        len(pair) < minimum_count
        or pair["signal"].nunique() < 2
        or pair["label"].nunique() < 2
    ):
        return math.nan
    return float(pair["signal"].rank().corr(pair["label"].rank()))


def mark_continuous_interval(
    readiness: pd.DataFrame, confirmation_periods: int = 3
) -> pd.DataFrame:
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


def assess_hypothesis(primary: list[bool], auxiliary: list[bool]) -> str:
    if len(primary) != 4 or len(auxiliary) != 8:
        raise ValueError("Assessment requires 4 primary and 8 auxiliary checks")
    if all(primary) and sum(auxiliary) >= 5:
        return "directionally_supported_for_strategy_prototyping"
    if not primary[0] and not primary[1] and primary[2] and primary[3]:
        return "mixed_risk_reduction_only"
    if not primary[0] and not primary[1] and not (primary[2] and primary[3]):
        return "not_supported"
    return "mixed"


def eligibility_contract_probe() -> None:
    try:
        from scripts.run_adjusted_stock_pool_baseline_v1_2 import Boundary, evaluate_period
    except ModuleNotFoundError:
        from run_adjusted_stock_pool_baseline_v1_2 import Boundary, evaluate_period
    start, end = pd.Timestamp("2024-01-01"), pd.Timestamp("2024-02-01")
    observed = evaluate_period(
        ["000001"], {("000001", start): 1.0}, Boundary(start, end, 20, "full")
    )
    if (
        observed["eligible_codes"] != "000001"
        or observed["end_price_missing_codes"] != "000001"
    ):
        raise ValueError("Baseline eligibility contract is not start-date-only")


def prepare_prices(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"stock_code", "trade_date", "adjusted_close", "qfq_close", "adjusted_flag"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Adjusted panel missing columns: {sorted(missing)}")
    result = frame.copy()
    result["stock_code"] = result["stock_code"].map(code6)
    result["trade_date"] = pd.to_datetime(result["trade_date"], errors="raise")
    if result.duplicated(["stock_code", "trade_date"]).any():
        raise ValueError("Duplicate stock_code/trade_date")
    result["adjusted_close"] = pd.to_numeric(result["adjusted_close"], errors="coerce")
    result["qfq_close"] = pd.to_numeric(result["qfq_close"], errors="coerce")
    valid_flag = flag_true(result["adjusted_flag"])
    conflict = valid_flag & (
        (result["adjusted_close"] <= 0)
        | (result["qfq_close"] <= 0)
        | ~np.isclose(
            result["adjusted_close"],
            result["qfq_close"],
            atol=ATOL,
            rtol=RTOL,
            equal_nan=False,
        )
    )
    if conflict.any():
        raise ValueError("Adjusted/QFQ price conflict")
    return result.loc[
        valid_flag & (result["adjusted_close"] > 0),
        ["stock_code", "trade_date", "adjusted_close"],
    ]


def signal_dates(
    calendar: list[pd.Timestamp], rebalance_date: pd.Timestamp
) -> dict[str, pd.Timestamp]:
    positions = {date: index for index, date in enumerate(calendar)}
    rebalance = pd.Timestamp(rebalance_date)
    if rebalance not in positions:
        raise ValueError(f"Rebalance date missing from 000300 calendar: {rebalance.date()}")
    signal_index = positions[rebalance] - 1
    if signal_index < max(LOOKBACKS):
        raise ValueError(f"Insufficient signal history before {rebalance.date()}")
    result = {"signal_as_of_date": calendar[signal_index]}
    for lookback in LOOKBACKS:
        result[f"vol_window_{lookback}_start_date"] = calendar[signal_index - lookback]
    return result


def build_factor_panel(
    periods: pd.DataFrame,
    universe: pd.DataFrame,
    prices: pd.DataFrame,
    calendar: list[pd.Timestamp],
) -> pd.DataFrame:
    codes = sorted(universe["code"].map(code6).unique())
    price_series = {
        code: group.set_index("trade_date")["adjusted_close"].sort_index()
        for code, group in prices.groupby("stock_code")
    }
    rows: list[dict[str, object]] = []
    for period_index, period in periods.reset_index(drop=True).iterrows():
        start = pd.Timestamp(period["rebalance_date"])
        end = pd.Timestamp(period["next_rebalance_date"])
        dates = signal_dates(calendar, start)
        eligible = set(parse_codes(period["eligible_codes"], int(period["eligible_count"])))
        risk_template = forward_risk_statistics(
            pd.Series(dtype=float), calendar, start, end
        )
        for code in codes:
            series = price_series.get(code, pd.Series(dtype=float))
            row: dict[str, object] = {
                "period_index": period_index,
                "stock_code": code,
                "rebalance_date": start,
                "next_rebalance_date": end,
                **dates,
                "baseline_eligible": code in eligible,
            }
            for lookback in LOOKBACKS:
                stats = window_statistics(series, calendar, dates["signal_as_of_date"], lookback)
                row.update(
                    {
                        f"vol{lookback}": stats["volatility"],
                        f"lowvol{lookback}": stats["lowvol"],
                        f"exact_price_observation_count_{lookback}": stats[
                            "price_observation_count"
                        ],
                        f"exact_return_interval_count_{lookback}": stats[
                            "return_interval_count"
                        ],
                        f"signal_available_{lookback}": stats["signal_available"],
                    }
                )
                if lookback == 20:
                    row.update(
                        {
                            "primary_reliable_signal": stats["primary_reliable_signal"],
                            "zero_return_count": stats["zero_return_count"],
                            "zero_return_ratio": stats["zero_return_ratio"],
                            "longest_zero_return_run": stats["longest_zero_return_run"],
                            "unique_close_count": stats["unique_close_count"],
                            "nonzero_return_count": stats["nonzero_return_count"],
                            "price_change_range": stats["price_change_range"],
                            "flat_price_risk_flag": stats["flat_price_risk_flag"],
                            "daily_return_outlier": stats["daily_return_outlier"],
                            "volatility_outlier": stats["volatility_outlier"],
                        }
                    )
            start_price = series.get(start, math.nan)
            end_price = series.get(end, math.nan)
            row["forward_return"] = (
                float(end_price / start_price - 1)
                if pd.notna(start_price)
                and pd.notna(end_price)
                and start_price > 0
                and end_price > 0
                else math.nan
            )
            row["forward_return_outlier"] = bool(
                pd.notna(row["forward_return"]) and abs(row["forward_return"]) > 0.50
            )
            risk = (
                forward_risk_statistics(series, calendar, start, end)
                if len(series)
                else risk_template
            )
            row.update(risk)
            reasons = []
            if code not in eligible:
                reasons.append("not_baseline_eligible")
            if not row["signal_available_20"]:
                reasons.append("missing_exact_lowvol20")
            elif not row["primary_reliable_signal"]:
                reasons.append("flat_price_reliability_fail")
            if pd.isna(row["forward_return"]):
                reasons.append("missing_forward_return")
            if not row["forward_risk_available"]:
                reasons.append("missing_forward_risk_path")
            row["exclusion_reason"] = ";".join(reasons)
            rows.append(row)
    panel = pd.DataFrame(rows)
    assigned = []
    diagnostics = []
    for period_index, group in panel.groupby("period_index", sort=True):
        part, diag = assign_quantiles(group, "lowvol20", reliable=True)
        for key, value in diag.items():
            part[key] = value
        assigned.append(part)
        diagnostics.append({"period_index": period_index, **diag})
    result = pd.concat(assigned, ignore_index=True)
    result["all_exact_signal_sample_member"] = (
        result["baseline_eligible"] & result["signal_available_20"]
    )
    result["common_exact_signal_sample_member"] = result["baseline_eligible"] & result[
        [f"signal_available_{lookback}" for lookback in LOOKBACKS]
    ].all(axis=1)
    result["sample_basis"] = "lowvol20_primary_reliable_sample"
    return result


def build_readiness(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for period_index, group in panel.groupby("period_index", sort=True):
        eligible = group["baseline_eligible"].sum()
        signal = group["signal_sample_member"].sum()
        evaluation = group["evaluation_sample_member"].sum()
        risk_evaluation = group["risk_evaluation_sample_member"].sum()
        group_checks, risk_checks = [], []
        for quantile in range(1, 6):
            q = group.loc[group["quantile"].eq(quantile)]
            signal_count = int(q["signal_sample_member"].sum())
            label_count = int(q["evaluation_sample_member"].sum())
            risk_count = int(q["risk_evaluation_sample_member"].sum())
            group_checks.append(
                signal_count >= MIN_GROUP_SIGNAL
                and label_count >= MIN_GROUP_LABEL
                and label_count / max(1, signal_count) >= MIN_GROUP_COVERAGE
            )
            risk_checks.append(
                signal_count >= MIN_GROUP_SIGNAL
                and risk_count >= MIN_GROUP_LABEL
                and risk_count / max(1, signal_count) >= MIN_GROUP_COVERAGE
            )
        evaluation_frame = group.loc[group["evaluation_sample_member"]]
        risk_frame = group.loc[group["risk_evaluation_sample_member"]]
        ic_valid = (
            len(evaluation_frame) >= MIN_COUNT
            and evaluation_frame["lowvol20"].nunique() >= 2
            and evaluation_frame["forward_return"].nunique() >= 2
        )
        risk_ic_valid = (
            len(risk_frame) >= MIN_COUNT
            and risk_frame["lowvol20"].nunique() >= 2
            and risk_frame["forward_realized_volatility"].nunique() >= 2
        )
        quantile_valid = bool(group["quantile_valid"].iloc[0] and all(group_checks))
        risk_quantile_valid = bool(group["quantile_valid"].iloc[0] and all(risk_checks))
        readiness = (
            signal / max(1, eligible) >= MIN_COVERAGE
            and evaluation / max(1, eligible) >= MIN_COVERAGE
            and evaluation >= MIN_COUNT
            and ic_valid
            and quantile_valid
        )
        rows.append(
            {
                "period_index": period_index,
                "rebalance_date": group["rebalance_date"].iloc[0],
                "next_rebalance_date": group["next_rebalance_date"].iloc[0],
                "eligible_count": int(eligible),
                "signal_count": int(signal),
                "evaluation_count": int(evaluation),
                "risk_evaluation_count": int(risk_evaluation),
                "signal_coverage_ratio": signal / max(1, eligible),
                "evaluation_coverage_ratio": evaluation / max(1, eligible),
                "flat_price_contamination_ratio": float(
                    group.loc[group["baseline_eligible"], "flat_price_risk_flag"].mean()
                ),
                "signal_unique_value_count": int(group["signal_unique_value_count"].iloc[0]),
                "largest_tie_group_count": int(group["largest_tie_group_count"].iloc[0]),
                "largest_tie_group_ratio": group["largest_tie_group_ratio"].iloc[0],
                "readiness_pass": readiness,
                "ic_valid": ic_valid,
                "quantile_valid": quantile_valid,
                "risk_ic_valid": risk_ic_valid,
                "risk_quantile_valid": risk_quantile_valid,
                "primary_period_valid": readiness,
            }
        )
    return mark_continuous_interval(pd.DataFrame(rows))


def evaluate_factor(
    panel: pd.DataFrame,
    period_ids: set[int],
    factor: str,
    sample_basis: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    ic_rows, quantile_rows, member_rows = [], [], []
    for period_index, original in panel.loc[panel["period_index"].isin(period_ids)].groupby(
        "period_index", sort=True
    ):
        group = original.copy()
        if sample_basis == "lowvol20_primary_reliable_sample":
            reliable = True
        elif sample_basis == "common_10_20_40_exact_sample":
            common = group[[f"signal_available_{n}" for n in LOOKBACKS]].all(axis=1)
            group["baseline_eligible"] &= common
            reliable = False
        else:
            reliable = False
        group, diagnostics = assign_quantiles(group, factor, reliable)
        evaluation = group.loc[group["evaluation_sample_member"]]
        risk_evaluation = group.loc[group["risk_evaluation_sample_member"]]
        return_ic = rank_ic(evaluation[factor], evaluation["forward_return"])
        risk_ic = rank_ic(
            risk_evaluation[factor], -risk_evaluation["forward_realized_volatility"]
        )
        ic_rows.append(
            {
                "factor_name": factor.upper(),
                "sample_basis": sample_basis,
                "period_index": period_index,
                "rebalance_date": group["rebalance_date"].iloc[0],
                "rank_ic": return_ic,
                "risk_persistence_rank_ic": risk_ic,
                "evaluation_count": len(evaluation),
                "risk_evaluation_count": len(risk_evaluation),
                **diagnostics,
            }
        )
        portfolio_returns, risk_means = {}, {}
        for quantile in range(1, 6):
            signal_q = group.loc[group["quantile"].eq(quantile)]
            labeled = signal_q.loc[signal_q["evaluation_sample_member"]]
            risk_labeled = signal_q.loc[signal_q["risk_evaluation_sample_member"]]
            name = f"Q{quantile}"
            portfolio_returns[name] = float(labeled["forward_return"].mean())
            risk_means[name] = float(risk_labeled["forward_realized_volatility"].mean())
            quantile_rows.append(
                {
                    "factor_name": factor.upper(),
                    "sample_basis": sample_basis,
                    "period_index": period_index,
                    "rebalance_date": group["rebalance_date"].iloc[0],
                    "portfolio": name,
                    "period_return": portfolio_returns[name],
                    "mean_forward_realized_volatility": risk_means[name],
                    "signal_count": len(signal_q),
                    "label_count": len(labeled),
                    "label_coverage": len(labeled) / max(1, len(signal_q)),
                    "risk_label_count": len(risk_labeled),
                    "risk_label_coverage": len(risk_labeled) / max(1, len(signal_q)),
                }
            )
            if quantile == 5:
                for stock in signal_q.itertuples():
                    member_rows.append(
                        {
                            "factor_name": factor.upper(),
                            "sample_basis": sample_basis,
                            "period_index": period_index,
                            "stock_code": stock.stock_code,
                            "forward_return": stock.forward_return,
                            "q5_contribution": (
                                stock.forward_return / len(labeled)
                                if stock.evaluation_sample_member and len(labeled)
                                else math.nan
                            ),
                            "flat_price_risk_flag": stock.flat_price_risk_flag,
                        }
                    )
        universe_return = float(evaluation["forward_return"].mean())
        universe_risk = float(risk_evaluation["forward_realized_volatility"].mean())
        extra = {
            "UNIVERSE": (universe_return, universe_risk),
            "Q5-Q1": (
                portfolio_returns["Q5"] - portfolio_returns["Q1"],
                risk_means["Q5"] - risk_means["Q1"],
            ),
            "Q5-UNIVERSE": (
                portfolio_returns["Q5"] - universe_return,
                risk_means["Q5"] - universe_risk,
            ),
        }
        for name, (period_return, risk_value) in extra.items():
            quantile_rows.append(
                {
                    "factor_name": factor.upper(),
                    "sample_basis": sample_basis,
                    "period_index": period_index,
                    "rebalance_date": group["rebalance_date"].iloc[0],
                    "portfolio": name,
                    "period_return": period_return,
                    "mean_forward_realized_volatility": risk_value,
                    "signal_count": len(group.loc[group["signal_sample_member"]]),
                    "label_count": len(evaluation),
                    "label_coverage": len(evaluation)
                    / max(1, len(group.loc[group["signal_sample_member"]])),
                    "risk_label_count": len(risk_evaluation),
                    "risk_label_coverage": len(risk_evaluation)
                    / max(1, len(group.loc[group["signal_sample_member"]])),
                }
            )
    return pd.DataFrame(ic_rows), pd.DataFrame(quantile_rows), pd.DataFrame(member_rows)


def endpoint_drawdown(returns: pd.Series) -> float:
    nav = (1 + returns.fillna(0)).cumprod()
    return float((nav / nav.cummax() - 1).min()) if len(nav) else math.nan


def summarize_ic(ic: pd.DataFrame, annualization_factor: float) -> pd.DataFrame:
    rows = []
    for (factor, basis), group in ic.groupby(["factor_name", "sample_basis"]):
        values = group["rank_ic"].dropna()
        risk = group["risk_persistence_rank_ic"].dropna()
        n = len(values)
        std = values.std(ddof=1)
        se = std / math.sqrt(n) if n > 1 else math.nan
        rows.append(
            {
                "factor_name": factor,
                "sample_basis": basis,
                "period_count": n,
                "mean_rank_ic": values.mean(),
                "median_rank_ic": values.median(),
                "rank_ic_std": std,
                "rank_ic_positive_ratio": (values > 0).mean(),
                "rank_ic_standard_error": se,
                "rank_ic_ci_lower": values.mean() - 1.96 * se,
                "rank_ic_ci_upper": values.mean() + 1.96 * se,
                "rank_ic_t_stat": values.mean() / se if se and se > 0 else math.nan,
                "annualized_icir": values.mean() / std * annualization_factor
                if std and std > 0
                else math.nan,
                "mean_risk_persistence_rank_ic": risk.mean(),
            }
        )
    return pd.DataFrame(rows)


def summarize_quantiles(
    returns: pd.DataFrame, annualization_factor: float
) -> pd.DataFrame:
    rows = []
    for keys, group in returns.groupby(["factor_name", "sample_basis", "portfolio"]):
        values = group["period_return"].dropna()
        rows.append(
            {
                "factor_name": keys[0],
                "sample_basis": keys[1],
                "portfolio": keys[2],
                "period_count": len(values),
                "mean_return": values.mean(),
                "median_return": values.median(),
                "cumulative_nav": (1 + values).prod(),
                "positive_period_ratio": (values > 0).mean(),
                "annualized_volatility": values.std(ddof=1) * annualization_factor,
                "downside_deviation": math.sqrt(
                    float(np.mean(np.minimum(values.to_numpy(), 0) ** 2))
                )
                * annualization_factor
                if len(values)
                else math.nan,
                "period_endpoint_maximum_drawdown": endpoint_drawdown(values),
                "worst_period_return": values.min(),
                "mean_forward_realized_volatility": group[
                    "mean_forward_realized_volatility"
                ].mean(),
            }
        )
    return pd.DataFrame(rows)


def moving_block_bootstrap(
    q1: np.ndarray,
    q5: np.ndarray,
    annualization_factor: float,
    replications: int = BOOTSTRAP_REPLICATIONS,
) -> dict[str, float]:
    if len(q1) != len(q5) or len(q1) < BOOTSTRAP_BLOCK_LENGTH:
        return {key: math.nan for key in ("vol_se", "vol_lo", "vol_hi", "dd_se", "dd_lo", "dd_hi")}
    rng = np.random.default_rng(BOOTSTRAP_SEED)
    n = len(q1)
    vol, dd = [], []
    for _ in range(replications):
        sample = []
        while len(sample) < n:
            start = int(rng.integers(0, n))
            sample.extend((start + offset) % n for offset in range(BOOTSTRAP_BLOCK_LENGTH))
        indices = np.asarray(sample[:n])
        left, right = q1[indices], q5[indices]
        vol.append(np.std(right, ddof=1) * annualization_factor - np.std(left, ddof=1) * annualization_factor)
        dd.append(endpoint_drawdown(pd.Series(right)) - endpoint_drawdown(pd.Series(left)))
    vol_array, dd_array = np.asarray(vol), np.asarray(dd)
    return {
        "vol_se": float(vol_array.std(ddof=1)),
        "vol_lo": float(np.quantile(vol_array, 0.025)),
        "vol_hi": float(np.quantile(vol_array, 0.975)),
        "dd_se": float(dd_array.std(ddof=1)),
        "dd_lo": float(np.quantile(dd_array, 0.025)),
        "dd_hi": float(np.quantile(dd_array, 0.975)),
    }


def qa_row(check: str, actual: float, expected: float, critical: bool = True, notes: str = "") -> dict[str, object]:
    absolute = abs(actual - expected)
    relative = absolute / max(abs(expected), ATOL)
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


def add_metadata(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    for key, value in METADATA.items():
        result[key] = value
    return result


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    output = add_metadata(frame)
    path.parent.mkdir(parents=True, exist_ok=True)
    output.to_csv(path, index=False, encoding="utf-8-sig")


def render_report(
    status: str,
    verdict: str | None,
    annualization: dict[str, object],
    readiness: pd.DataFrame,
    ic_summary: pd.DataFrame,
    quantile_summary: pd.DataFrame,
    risk_summary: pd.DataFrame,
    hypothesis: pd.DataFrame,
) -> str:
    def table(frame: pd.DataFrame, columns: list[str]) -> str:
        if frame.empty:
            return "_No primary result: research not ready._"
        use = frame[[column for column in columns if column in frame]].copy()
        return use.to_markdown(index=False)

    return f"""# LOWVOL20 Factor Research v1.4

## Research status

- status: {status}
- verdict: {verdict or 'not_available'}
- research_only=true
- primary_factor=LOWVOL20
- current-universe historical research
- universe_point_in_time=false
- suspension_status_available=false
- execution_sim_ready=false
- formal_performance_conclusion_allowed=false
- no_investment_conclusion=true

The primary estimand is the low-volatility effect conditional on minimum observed
price activity. Flat-price rules are data-quality filters, not suspension
identification or proof of tradability. Results do not generalize to the entire
nominal universe.

## Calendar and horizon

- target_rebalance_step=20_baseline_calendar_entries
- forward interval min/median/max: {annualization['minimum']}/{annualization['median']}/{annualization['maximum']}
- interval distribution: {annualization['distribution']}
- approximate_annualization={str(annualization['approximate']).lower()}

## Readiness

{table(readiness.tail(8), ['rebalance_date', 'signal_count', 'evaluation_count', 'readiness_pass', 'ic_valid', 'quantile_valid', 'risk_ic_valid', 'period_phase'])}

## Return effect and risk persistence

{table(ic_summary, ['factor_name', 'sample_basis', 'period_count', 'mean_rank_ic', 'rank_ic_standard_error', 'rank_ic_ci_lower', 'rank_ic_ci_upper', 'mean_risk_persistence_rank_ic'])}

{table(quantile_summary, ['factor_name', 'sample_basis', 'portfolio', 'mean_return', 'annualized_volatility', 'period_endpoint_maximum_drawdown', 'mean_forward_realized_volatility'])}

{table(risk_summary, ['segment', 'q5_minus_q1_volatility', 'vol_se', 'vol_lo', 'vol_hi', 'q5_minus_q1_drawdown', 'dd_se', 'dd_lo', 'dd_hi'])}

Future-return effects and forward realized-volatility persistence are reported
separately. A missing forward risk path never changes the original quantile.

## Primary versus diagnostic samples

LOWVOL20 primary results use lowvol20_primary_reliable_sample. The
lowvol20_all_exact_windows_diagnostic reports direction before flat-price
screening. LOWVOL10/20/40 use common_10_20_40_exact_sample only and cannot
replace the primary conclusion.

## Hypothesis assessment

{table(hypothesis, ['metric', 'value', 'status', 'sample_basis'])}

Epsilon is only numerical zero handling, not an economic materiality threshold.
Confidence intervals are descriptive historical-sample uncertainty, not clean
out-of-sample confirmation.

## Limitations

- This is historical chronological validation, not clean preregistered OOS confirmation.
- Current-universe / survivorship-like bias remains.
- Close-only flat-price diagnostics cannot prove continuous tradability.
- Period-end drawdown is not daily maximum drawdown.
- Q5-Q1 is not an executable A-share long-short strategy.
- formal_performance_conclusion_allowed=false
- execution_sim_ready=false
- no_investment_conclusion=true
"""


def load_inputs(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data, reports = root / "data" / "processed", root / "reports"
    periods = pd.read_csv(
        reports / "adjusted_stock_pool_baseline_periods_v1_2.csv", dtype=str
    )
    prices = pd.read_csv(data / "adjusted_price_panel_v1_2.csv", dtype={"stock_code": str})
    universe = pd.read_csv(
        data / "backtest_universe_research_v1_2.csv", dtype={"code": str}
    )
    benchmark = pd.read_csv(
        data / "hybrid_benchmark_panel_v1_2.csv", dtype={"benchmark_code": str}
    )
    periods["transaction_cost"] = pd.to_numeric(periods["transaction_cost"], errors="coerce")
    periods["rebalance_date"] = pd.to_datetime(periods["rebalance_date"], errors="raise")
    periods["next_rebalance_date"] = pd.to_datetime(
        periods["next_rebalance_date"], errors="raise"
    )
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


def run_research(root: Path) -> tuple[int, str]:
    eligibility_contract_probe()
    periods, prices, universe, benchmark = load_inputs(root)
    calendar = market_calendar(benchmark)
    calendar_set = set(calendar)
    endpoints = set(periods["rebalance_date"]) | set(periods["next_rebalance_date"])
    if not endpoints.issubset(calendar_set):
        raise ValueError("Baseline endpoint missing from 000300 calendar")
    panel = build_factor_panel(periods, universe, prices, calendar)
    readiness = build_readiness(panel)
    main_ids = set(
        readiness.loc[readiness["main_period_member"], "period_index"].astype(int)
    )
    validation_count = int(
        readiness.loc[
            readiness["main_period_member"]
            & (pd.to_datetime(readiness["rebalance_date"]) >= pd.Timestamp("2024-01-01"))
        ].shape[0]
    )
    research_ready = len(main_ids) >= 12 and validation_count >= 6
    interval_counts = readiness.loc[
        readiness["main_period_member"], "period_index"
    ].map(panel.groupby("period_index")["forward_market_interval_count"].first()).tolist()
    if not interval_counts:
        interval_counts = panel.groupby("period_index")[
            "forward_market_interval_count"
        ].first().tolist()
    annualization = period_annualization([int(value) for value in interval_counts])

    qa = [
        qa_row("factor_panel_row_count", len(panel), universe["code"].nunique() * len(periods)),
        qa_row(
            "factor_panel_unique_keys",
            panel.drop_duplicates(["period_index", "stock_code"]).shape[0],
            len(panel),
        ),
        qa_row("baseline_endpoints_in_000300", float(endpoints.issubset(calendar_set)), 1.0),
        qa_row(
            "signal_before_rebalance",
            float((panel["signal_as_of_date"] < panel["rebalance_date"]).all()),
            1.0,
        ),
        qa_row(
            "lowvol20_negative_vol20",
            float(
                np.isclose(
                    panel["lowvol20"],
                    -panel["vol20"],
                    atol=ATOL,
                    rtol=RTOL,
                    equal_nan=True,
                ).all()
            ),
            1.0,
        ),
        qa_row(
            "evaluation_subset_signal",
            float((~panel["evaluation_sample_member"] | panel["signal_sample_member"]).all()),
            1.0,
        ),
    ]
    empty = pd.DataFrame()
    ic_periods = quantile_returns = ic_summary = quantile_summary = risk_summary = stability = hypothesis = empty
    verdict = None
    if research_ready:
        evaluations = [
            ("lowvol20", "lowvol20_primary_reliable_sample"),
            ("lowvol20", "lowvol20_all_exact_windows_diagnostic"),
            ("lowvol10", "common_10_20_40_exact_sample"),
            ("lowvol20", "common_10_20_40_exact_sample"),
            ("lowvol40", "common_10_20_40_exact_sample"),
        ]
        ic_frames, q_frames, member_frames = [], [], []
        for factor, basis in evaluations:
            ic, quantiles, members = evaluate_factor(panel, main_ids, factor, basis)
            ic_frames.append(ic)
            q_frames.append(quantiles)
            member_frames.append(members)
        ic_periods = pd.concat(ic_frames, ignore_index=True)
        quantile_returns = pd.concat(q_frames, ignore_index=True)
        members = pd.concat(member_frames, ignore_index=True)
        ic_summary = summarize_ic(ic_periods, annualization["factor"])
        quantile_summary = summarize_quantiles(
            quantile_returns, annualization["factor"]
        )

        primary_ic = ic_periods.loc[
            ic_periods["factor_name"].eq("LOWVOL20")
            & ic_periods["sample_basis"].eq("lowvol20_primary_reliable_sample")
        ]
        primary_q = quantile_returns.loc[
            quantile_returns["factor_name"].eq("LOWVOL20")
            & quantile_returns["sample_basis"].eq("lowvol20_primary_reliable_sample")
        ]
        validation_ic = primary_ic.loc[
            pd.to_datetime(primary_ic["rebalance_date"]) >= pd.Timestamp("2024-01-01")
        ]
        validation_q = primary_q.loc[
            pd.to_datetime(primary_q["rebalance_date"]) >= pd.Timestamp("2024-01-01")
        ]
        pivot = validation_q.pivot(
            index="period_index", columns="portfolio", values="period_return"
        )
        mean_ic = float(validation_ic["rank_ic"].mean())
        mean_spread = float(pivot["Q5-Q1"].mean())
        q1_vol = float(pivot["Q1"].std(ddof=1) * annualization["factor"])
        q5_vol = float(pivot["Q5"].std(ddof=1) * annualization["factor"])
        q1_dd, q5_dd = endpoint_drawdown(pivot["Q1"]), endpoint_drawdown(pivot["Q5"])
        primary_checks = [
            mean_ic > DIRECTION_EPSILON,
            mean_spread > DIRECTION_EPSILON,
            q5_vol < q1_vol,
            q5_dd > q1_dd,
        ]
        year_rows = []
        for year, group in validation_ic.groupby(
            pd.to_datetime(validation_ic["rebalance_date"]).dt.year
        ):
            q_year = validation_q.loc[
                pd.to_datetime(validation_q["rebalance_date"]).dt.year.eq(year)
            ].pivot(index="period_index", columns="portfolio", values="period_return")
            year_rows.append(
                {
                    "row_type": "year",
                    "segment": f"year_{year}",
                    "status": "ok" if len(group) >= 6 else "insufficient_periods",
                    "period_count": len(group),
                    "mean_rank_ic": group["rank_ic"].mean(),
                    "mean_q5_q1": q_year["Q5-Q1"].mean(),
                }
            )
        valid_years = pd.DataFrame(year_rows)
        yearly_direction = (
            float(
                (
                    (valid_years.loc[valid_years["status"].eq("ok"), "mean_rank_ic"] > 0)
                    & (valid_years.loc[valid_years["status"].eq("ok"), "mean_q5_q1"] > 0)
                ).mean()
            )
            if len(valid_years) and valid_years["status"].eq("ok").any()
            else 0.0
        )
        q5_universe = float(pivot["Q5-UNIVERSE"].mean())
        universe_vol = float(pivot["UNIVERSE"].std(ddof=1) * annualization["factor"])
        universe_dd = endpoint_drawdown(pivot["UNIVERSE"])
        common = ic_periods.loc[
            ic_periods["sample_basis"].eq("common_10_20_40_exact_sample")
            & pd.to_datetime(ic_periods["rebalance_date"]).ge(pd.Timestamp("2024-01-01"))
        ]
        common_q = quantile_returns.loc[
            quantile_returns["sample_basis"].eq("common_10_20_40_exact_sample")
            & quantile_returns["portfolio"].eq("Q5-Q1")
            & pd.to_datetime(quantile_returns["rebalance_date"]).ge(pd.Timestamp("2024-01-01"))
        ]
        robustness_negative = []
        for factor in ("LOWVOL10", "LOWVOL40"):
            robustness_negative.append(
                common.loc[common["factor_name"].eq(factor), "rank_ic"].mean() < -DIRECTION_EPSILON
                and common_q.loc[common_q["factor_name"].eq(factor), "period_return"].mean()
                < -DIRECTION_EPSILON
            )
        leave_best = (
            pivot["Q5-Q1"].drop(pivot["Q5-Q1"].idxmax()).mean()
            if len(pivot) > 1
            else math.nan
        )
        diagnostic_ic = ic_periods.loc[
            ic_periods["factor_name"].eq("LOWVOL20")
            & ic_periods["sample_basis"].eq("lowvol20_all_exact_windows_diagnostic")
            & pd.to_datetime(ic_periods["rebalance_date"]).ge(pd.Timestamp("2024-01-01")),
            "rank_ic",
        ].mean()
        diagnostic_spread = quantile_returns.loc[
            quantile_returns["factor_name"].eq("LOWVOL20")
            & quantile_returns["sample_basis"].eq("lowvol20_all_exact_windows_diagnostic")
            & quantile_returns["portfolio"].eq("Q5-Q1")
            & pd.to_datetime(quantile_returns["rebalance_date"]).ge(pd.Timestamp("2024-01-01")),
            "period_return",
        ].mean()
        direction_consistent = not (
            np.sign(mean_ic) == -np.sign(diagnostic_ic)
            and np.sign(mean_spread) == -np.sign(diagnostic_spread)
        )
        auxiliary = [
            float((validation_ic["rank_ic"] > 0).mean()) > 0.5,
            q5_universe > DIRECTION_EPSILON,
            q5_vol < universe_vol,
            q5_dd > universe_dd,
            yearly_direction >= 0.60,
            not all(robustness_negative),
            leave_best > DIRECTION_EPSILON,
            direction_consistent,
        ]
        verdict = assess_hypothesis(primary_checks, auxiliary)
        bootstrap = moving_block_bootstrap(
            pivot["Q1"].to_numpy(), pivot["Q5"].to_numpy(), annualization["factor"]
        )
        risk_summary = pd.DataFrame(
            [
                {
                    "sample_basis": "lowvol20_primary_reliable_sample",
                    "segment": "historical_validation",
                    "q1_annualized_volatility": q1_vol,
                    "q5_annualized_volatility": q5_vol,
                    "q5_minus_q1_volatility": q5_vol - q1_vol,
                    "q1_period_endpoint_drawdown": q1_dd,
                    "q5_period_endpoint_drawdown": q5_dd,
                    "q5_minus_q1_drawdown": q5_dd - q1_dd,
                    **bootstrap,
                }
            ]
        )
        stability = pd.concat(
            [
                valid_years,
                pd.DataFrame(
                    [
                        {
                            "row_type": "period_extreme",
                            "segment": "best_rank_ic",
                            "period_count": 1,
                            "mean_rank_ic": value,
                        }
                        for value in validation_ic.nlargest(5, "rank_ic")["rank_ic"]
                    ]
                    + [
                        {
                            "row_type": "period_extreme",
                            "segment": "worst_rank_ic",
                            "period_count": 1,
                            "mean_rank_ic": value,
                        }
                        for value in validation_ic.nsmallest(5, "rank_ic")["rank_ic"]
                    ]
                ),
                members.loc[
                    members["factor_name"].eq("LOWVOL20")
                    & members["sample_basis"].eq("lowvol20_primary_reliable_sample")
                ]
                .groupby("stock_code", as_index=False)
                .agg(
                    q5_count=("period_index", "count"),
                    q5_arithmetic_contribution=("q5_contribution", "sum"),
                    flat_price_risk_frequency=("flat_price_risk_flag", "mean"),
                )
                .assign(row_type="q5_stock", segment="q5_members"),
            ],
            ignore_index=True,
            sort=False,
        )
        effect_se = validation_ic["rank_ic"].std(ddof=1) / math.sqrt(len(validation_ic))
        spread_se = pivot["Q5-Q1"].std(ddof=1) / math.sqrt(len(pivot))
        hypothesis = pd.DataFrame(
            [
                {"metric": "historical_validation_mean_rank_ic", "value": mean_ic},
                {"metric": "rank_ic_standard_error", "value": effect_se},
                {"metric": "rank_ic_ci_lower", "value": mean_ic - 1.96 * effect_se},
                {"metric": "rank_ic_ci_upper", "value": mean_ic + 1.96 * effect_se},
                {"metric": "historical_validation_mean_q5_q1", "value": mean_spread},
                {"metric": "q5_q1_standard_error", "value": spread_se},
                {"metric": "q5_q1_ci_lower", "value": mean_spread - 1.96 * spread_se},
                {"metric": "q5_q1_ci_upper", "value": mean_spread + 1.96 * spread_se},
                {"metric": "primary_evidence_pass_count", "value": sum(primary_checks)},
                {"metric": "auxiliary_evidence_pass_count", "value": sum(auxiliary)},
                {"metric": "all_exact_validation_mean_rank_ic", "value": diagnostic_ic},
                {"metric": "all_exact_validation_mean_q5_q1", "value": diagnostic_spread},
                {"metric": "primary_and_all_exact_direction_consistent", "value": direction_consistent},
                {"metric": "verdict", "value": verdict},
            ]
        ).assign(status="ok", sample_basis="lowvol20_primary_reliable_sample")

        q_pivot = primary_q.pivot(
            index="period_index", columns="portfolio", values="period_return"
        )
        qa.extend(
            [
                qa_row(
                    "q5_q1_reconciliation",
                    float((q_pivot["Q5-Q1"] - (q_pivot["Q5"] - q_pivot["Q1"])).abs().max()),
                    0.0,
                ),
                qa_row(
                    "primary_factor_locked",
                    float(PRIMARY_FACTOR == "LOWVOL20"),
                    1.0,
                ),
            ]
        )

    qa_frame = pd.DataFrame(qa)
    critical_failure = bool(
        ((qa_frame["critical"] == True) & (qa_frame["pass"] == False)).any()
    )
    if critical_failure:
        return 2, "critical_qa_failure"

    data, reports = root / "data" / "processed", root / "reports"
    write_csv(panel, data / "lowvol20_factor_panel_v1_4.csv")
    write_csv(readiness, reports / "factor_data_readiness_lowvol20_v1_4.csv")
    write_csv(ic_periods, reports / "factor_ic_periods_lowvol20_v1_4.csv")
    write_csv(ic_summary, reports / "factor_ic_summary_lowvol20_v1_4.csv")
    write_csv(quantile_returns, reports / "factor_quantile_returns_lowvol20_v1_4.csv")
    write_csv(quantile_summary, reports / "factor_quantile_summary_lowvol20_v1_4.csv")
    write_csv(risk_summary, reports / "factor_risk_summary_lowvol20_v1_4.csv")
    write_csv(stability, reports / "factor_stability_lowvol20_v1_4.csv")
    write_csv(hypothesis, reports / "factor_hypothesis_summary_lowvol20_v1_4.csv")
    write_csv(qa_frame, reports / "factor_research_qa_lowvol20_v1_4.csv")
    status = "completed" if research_ready else "research_not_ready"
    (reports / "factor_lowvol20_v1_4.md").write_text(
        render_report(
            status,
            verdict,
            annualization,
            readiness,
            ic_summary,
            quantile_summary,
            risk_summary,
            hypothesis,
        ),
        encoding="utf-8",
    )
    return (0 if research_ready else 1), status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--project-root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args(argv)
    try:
        code, status = run_research(args.project_root.resolve())
        print(f"LOWVOL20 v1.4 status={status}")
        return code
    except Exception as error:
        reports = args.project_root.resolve() / "reports"
        write_csv(
            pd.DataFrame(
                [qa_row("fatal_input_validation", 1.0, 0.0, notes=str(error))]
            ),
            reports / "factor_research_qa_lowvol20_v1_4.csv",
        )
        reports.mkdir(parents=True, exist_ok=True)
        (reports / "factor_lowvol20_v1_4.md").write_text(
            render_report(
                "input_error",
                None,
                {
                    "minimum": math.nan,
                    "median": math.nan,
                    "maximum": math.nan,
                    "distribution": "",
                    "approximate": True,
                },
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
                pd.DataFrame(),
            )
            + f"\nFatal validation error: {error}\n",
            encoding="utf-8",
        )
        print(f"LOWVOL20 v1.4 input error: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
