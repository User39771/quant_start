"""Audit signal-time covariates represented by the frozen H5A activity states."""

# ruff: noqa: E501 -- the generated technical report is embedded as readable Markdown.

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from scripts.run_h5a_trading_activity_reversal_timing_v1 import (
        ACTIVITY_STATES,
        RETURN_STATES,
        _assign_states,
        code6,
        ordinal_groups,
    )
else:
    from run_h5a_trading_activity_reversal_timing_v1 import (
        ACTIVITY_STATES,
        RETURN_STATES,
        _assign_states,
        code6,
        ordinal_groups,
    )

OUTPUT = Path("reports/hypothesis_5a")
PRIMARY_PERIODS = range(1, 57)
NUMERIC_COVARIATES = {
    "amount_mean_20": "AMOUNT_MEAN20",
    "log_amount_mean_20": "log AMOUNT_MEAN20",
    "log_qfq_signal_price": "log signal-date QFQ close",
    "log_raw_signal_price": "log signal-date RAW close",
    "vol20": "VOL20",
    "log_total_market_cap": "log total market cap",
    "log_circulating_market_cap": "log circulating market cap",
    "return_60": "RETURN60",
}

IDENTITY = {
    "analysis_type": "post_h5a_explanatory_audit",
    "sample_role": "historical_seen",
    "causal_claim_allowed": False,
    "alpha_claim_allowed": False,
    "future_return_analysis_run": False,
    "H5A_reoptimized": False,
    "MCTS_run": False,
    "Phase_B_run": False,
}


def board_from_code(code: str) -> str:
    if code.startswith("688"):
        return "STAR"
    if code.startswith(("300", "301")):
        return "CHINEXT"
    if code.startswith("6"):
        return "SH_MAIN"
    return "SZ_MAIN"


def longest_true_run(values: np.ndarray) -> int:
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def exact_vol20(prices: pd.Series, expected_dates: pd.DatetimeIndex) -> float:
    """Reuse LOWVOL20's exact 21-price/20-return annualized sample std contract."""
    selected = prices.reindex(expected_dates)
    if len(selected) != 21 or selected.isna().any() or selected.le(0).any():
        return math.nan
    returns = selected.pct_change(fill_method=None).dropna()
    zero = np.isclose(returns.to_numpy(float), 0.0, atol=1e-12, rtol=0)
    reliable = selected.nunique() >= 3 and (~zero).sum() >= 5 and longest_true_run(zero) <= 5
    return float(returns.std(ddof=1) * math.sqrt(252)) if reliable else math.nan


def standardized_difference(high: pd.Series, low: pd.Series) -> float:
    high = pd.to_numeric(high, errors="coerce").dropna()
    low = pd.to_numeric(low, errors="coerce").dropna()
    if len(high) < 2 or len(low) < 2:
        return math.nan
    pooled = math.sqrt((high.var(ddof=1) + low.var(ddof=1)) / 2)
    return float((high.mean() - low.mean()) / pooled) if pooled > 0 else math.nan


def _load_states(root: Path) -> pd.DataFrame:
    features = pd.read_csv(
        root / "data/processed/h5a_broader_a_signal_features_v1.csv",
        dtype={"stock_code": str},
    )
    features["stock_code"] = features["stock_code"].map(code6)
    features["signal_as_of_date"] = pd.to_datetime(features["signal_as_of_date"], errors="raise")
    features["signal_ready"] = features["signal_ready"].astype(str).str.lower().eq("true")
    states = _assign_states(features)
    states = states.loc[states["period_index"].isin(PRIMARY_PERIODS)].copy()

    official = pd.read_csv(
        root / "reports/hypothesis_5a/h5a_period_state_returns.csv",
        usecols=["period_index", "return_state", "activity_state", "horizon", "stock_count"],
    )
    official = official.loc[official["horizon"].eq(20) & official["period_index"].isin(PRIMARY_PERIODS)]
    rebuilt = states.groupby(
        ["period_index", "return_state", "activity_state"], as_index=False
    ).agg(stock_count=("stock_code", "size"))
    check = rebuilt.merge(
        official.drop(columns="horizon"),
        on=["period_index", "return_state", "activity_state"],
        suffixes=("_audit", "_h5a"),
        validate="one_to_one",
    )
    if len(check) != 56 * 9 or not check["stock_count_audit"].eq(check["stock_count_h5a"]).all():
        raise ValueError("h5a_activity_membership_reconciliation_failed")
    return states


def _market_calendar(root: Path) -> pd.DatetimeIndex:
    benchmark = pd.read_csv(root / "data/processed/hybrid_benchmark_panel_v1_5.csv")
    benchmark["benchmark_code"] = benchmark["benchmark_code"].map(code6)
    dates = pd.to_datetime(
        benchmark.loc[benchmark["benchmark_code"].eq("000300"), "trade_date"], errors="raise"
    )
    return pd.DatetimeIndex(dates.drop_duplicates().sort_values())


def _load_qfq_covariates(root: Path, states: pd.DataFrame) -> pd.DataFrame:
    calendar = _market_calendar(root)
    position = {date: index for index, date in enumerate(calendar)}
    signals = states[["period_index", "signal_as_of_date"]].drop_duplicates().sort_values("period_index")
    windows = {
        int(row.period_index): calendar[position[row.signal_as_of_date] - 20 : position[row.signal_as_of_date] + 1]
        for row in signals.itertuples(index=False)
    }
    signal_by_code = states.groupby("stock_code")["period_index"].apply(list).to_dict()
    resolution = pd.read_csv(
        root / "reports/hypothesis_5a_broader_a/source_resolution_report.csv",
        dtype={"stock_code": str},
    )
    resolution["stock_code"] = resolution["stock_code"].map(code6)
    paths = resolution.set_index("stock_code")["canonical_price_path"].dropna().to_dict()
    rows = []
    for code, periods in signal_by_code.items():
        path = paths.get(code)
        if not path:
            continue
        frame = pd.read_csv(root / path, usecols=["trade_date", "qfq_close"])
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
        frame["qfq_close"] = pd.to_numeric(frame["qfq_close"], errors="coerce")
        if frame["trade_date"].duplicated().any():
            raise ValueError(f"duplicate_qfq_date={code}")
        prices = frame.set_index("trade_date")["qfq_close"]
        for period in periods:
            expected = windows[int(period)]
            signal_price = prices.get(expected[-1], math.nan)
            rows.append(
                {
                    "period_index": period,
                    "stock_code": code,
                    "qfq_signal_price": signal_price,
                    "vol20": exact_vol20(prices, expected),
                }
            )
    return pd.DataFrame(rows)


def _load_raw_covariates(root: Path, states: pd.DataFrame) -> pd.DataFrame:
    signal_dates = states.set_index("period_index")["signal_as_of_date"].to_dict()
    periods_by_code = states.groupby("stock_code")["period_index"].apply(list).to_dict()
    rows = []
    for code, periods in periods_by_code.items():
        path = root / "data/cache/price" / f"{code}.csv"
        if not path.exists():
            continue
        header = pd.read_csv(path, nrows=0).columns
        wanted = [
            column
            for column in ["date", "close", "total_market_cap", "circulating_market_cap"]
            if column in header
        ]
        if "date" not in wanted:
            continue
        frame = pd.read_csv(path, usecols=wanted)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.drop_duplicates("date").set_index("date")
        for period in periods:
            date = signal_dates[int(period)]
            row = frame.loc[date] if date in frame.index else pd.Series(dtype=float)
            rows.append(
                {
                    "period_index": period,
                    "stock_code": code,
                    "raw_signal_price": row.get("close", math.nan),
                    "total_market_cap": row.get("total_market_cap", math.nan),
                    "circulating_market_cap": row.get("circulating_market_cap", math.nan),
                }
            )
    return pd.DataFrame(rows)


def _safe_log(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return np.log(numeric.where(numeric.gt(0)))


def _build_covariate_panel(root: Path, states: pd.DataFrame) -> pd.DataFrame:
    panel = states.merge(
        _load_qfq_covariates(root, states),
        on=["period_index", "stock_code"],
        how="left",
        validate="one_to_one",
    ).merge(
        _load_raw_covariates(root, states),
        on=["period_index", "stock_code"],
        how="left",
        validate="one_to_one",
    )
    panel["board"] = panel["stock_code"].map(board_from_code)
    panel["log_amount_mean_20"] = _safe_log(panel["amount_mean_20"])
    panel["log_qfq_signal_price"] = _safe_log(panel["qfq_signal_price"])
    panel["log_raw_signal_price"] = _safe_log(panel["raw_signal_price"])
    panel["log_total_market_cap"] = _safe_log(panel["total_market_cap"])
    panel["log_circulating_market_cap"] = _safe_log(panel["circulating_market_cap"])
    return panel


def _inventory(panel: pd.DataFrame) -> pd.DataFrame:
    definitions = [
        ("AMOUNT_MEAN_20", True, True, "HISTORICAL_SIGNAL_WINDOW", "h5a signal feature panel", "mean positive finite amount over exact 20 market dates", "Base proxy; mixes activity, size and price"),
        ("ACTIVITY_PCT", True, True, "HISTORICAL_SIGNAL_CROSS_SECTION", "h5a signal feature panel", "average percentile rank of AMOUNT_MEAN20 within signal-ready period", "Report value; membership uses deterministic ordinal assignment"),
        ("RETURN_60", True, True, "HISTORICAL_SIGNAL_WINDOW", "h5a signal feature panel", "QFQ endpoint return over exact 60 market-day interval ending at signal", "Frozen H5A return state input"),
        ("signal_qfq_close", True, True, "HISTORICAL_DATED_NOT_VINTAGE", "canonical Sina QFQ cache", "QFQ close on signal date", "Absolute QFQ scale depends on adjustment base"),
        ("signal_raw_close", True, True, "HISTORICAL_DATED_NOT_VINTAGE", "local RAW daily cache", "unadjusted close on signal date", "Used only for price-level description"),
        ("VOL20", True, True, "HISTORICAL_SIGNAL_WINDOW", "canonical Sina QFQ; existing LOWVOL20 contract", "annualized sample std of 20 exact daily returns ending at signal", "Requires 21 exact prices and existing flat-price reliability rule"),
        ("total_market_cap", True, True, "HISTORICAL_DATED_NOT_VINTAGE_AUDITED", "local RAW daily cache", "vendor total_market_cap on signal date", "Date-varying history exists; share/effective-date lineage not independently audited"),
        ("circulating_market_cap", True, True, "HISTORICAL_DATED_NOT_VINTAGE_AUDITED", "local RAW daily cache", "vendor circulating_market_cap on signal date", "Date-varying history exists; share/effective-date lineage not independently audited"),
        ("sw_industry", True, True, "CURRENT_MAPPING_NOT_POINT_IN_TIME", "theme_business_review_completed_001_200.csv", "current reviewed SW industry label for mapped stocks", "Only 200 mapped codes; not representative of broader-A"),
        ("board", True, True, "STATIC_CODE_DERIVED", "stock_code", "SH Main, SZ Main, ChiNext or STAR from code prefix", "Static descriptive category; not causal"),
        ("listing_age_at_signal", False, False, "UNAVAILABLE", "local project inventory", "signal date minus verified listing date", "No usable local listing-date table; no inference from first price date"),
        ("turnover", False, False, "DENOMINATOR_LINEAGE_UNRESOLVED", "local RAW daily cache", "vendor turnover field", "Not true audited point-in-time turnover; excluded"),
    ]
    coverage_map = {
        "AMOUNT_MEAN_20": panel["amount_mean_20"].notna().mean(),
        "ACTIVITY_PCT": panel["activity_pct"].notna().mean(),
        "RETURN_60": panel["return_60"].notna().mean(),
        "signal_qfq_close": panel["qfq_signal_price"].notna().mean(),
        "signal_raw_close": panel["raw_signal_price"].notna().mean(),
        "VOL20": panel["vol20"].notna().mean(),
        "total_market_cap": panel["total_market_cap"].notna().mean(),
        "circulating_market_cap": panel["circulating_market_cap"].notna().mean(),
        "sw_industry": 200 / 5195,
        "board": 1.0,
        "listing_age_at_signal": 0.0,
        "turnover": 0.0,
    }
    return pd.DataFrame(
        [
            {
                "covariate": covariate,
                "available": available,
                "signal_time_valid": valid,
                "point_in_time_status": status,
                "source": source,
                "definition": definition,
                "coverage": coverage_map[covariate],
                "limitation": limitation,
            }
            for covariate, available, valid, status, source, definition, limitation in definitions
        ]
    )


def _period_distribution(group: pd.DataFrame, covariate: str) -> dict[str, float | int]:
    values = pd.to_numeric(group[covariate], errors="coerce").dropna()
    return {
        "valid_count": len(values),
        "mean": values.mean(),
        "median": values.median(),
        "q25": values.quantile(0.25),
        "q75": values.quantile(0.75),
        "iqr": values.quantile(0.75) - values.quantile(0.25),
    }


def _characteristics(panel: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for period, group in panel.groupby("period_index", sort=True):
        amount = pd.to_numeric(group["amount_mean_20"], errors="coerce").dropna()
        rows.append(
            {
                "row_type": "amount_period_scale",
                "period_index": period,
                "return_state": "ALL",
                "activity_state": "ALL",
                "covariate": "AMOUNT_MEAN_20",
                "valid_count": len(amount),
                "mean": amount.mean(),
                "median": amount.median(),
                "q25": amount.quantile(0.10),
                "q75": amount.quantile(0.90),
                "iqr": amount.quantile(0.75) - amount.quantile(0.25),
            }
        )
        for activity_state, activity in group.groupby("activity_state"):
            for covariate in NUMERIC_COVARIATES:
                rows.append(
                    {
                        "row_type": "period_activity_characteristic",
                        "period_index": period,
                        "return_state": "ALL",
                        "activity_state": activity_state,
                        "covariate": covariate,
                        **_period_distribution(activity, covariate),
                    }
                )
        for (return_state, activity_state), cell in group.groupby(
            ["return_state", "activity_state"]
        ):
            for covariate in NUMERIC_COVARIATES:
                rows.append(
                    {
                        "row_type": "period_return_activity_characteristic",
                        "period_index": period,
                        "return_state": return_state,
                        "activity_state": activity_state,
                        "covariate": covariate,
                        **_period_distribution(cell, covariate),
                    }
                )
        for covariate in NUMERIC_COVARIATES:
            rows.append(
                {
                    "row_type": "period_standardized_difference",
                    "period_index": period,
                    "return_state": "ALL",
                    "activity_state": "HIGH_MINUS_LOW",
                    "covariate": covariate,
                    "valid_count": math.nan,
                    "mean": standardized_difference(
                        group.loc[group["activity_state"].eq("HIGH_ACTIVITY"), covariate],
                        group.loc[group["activity_state"].eq("LOW_ACTIVITY"), covariate],
                    ),
                    "median": math.nan,
                    "q25": math.nan,
                    "q75": math.nan,
                    "iqr": math.nan,
                }
            )

        return_activity = pd.DataFrame(rows)
        return_activity = return_activity.loc[
            return_activity["row_type"].eq("period_return_activity_characteristic")
            & return_activity["period_index"].eq(period)
        ]
        for (return_state, covariate), cells in return_activity.groupby(
            ["return_state", "covariate"]
        ):
            by_state = cells.set_index("activity_state")
            if {"HIGH_ACTIVITY", "LOW_ACTIVITY"}.issubset(by_state.index):
                high_low = (
                    by_state.loc["HIGH_ACTIVITY", "mean"]
                    - by_state.loc["LOW_ACTIVITY", "mean"]
                )
                rows.append(
                    {
                        "row_type": "period_return_state_high_minus_low",
                        "period_index": period,
                        "return_state": return_state,
                        "activity_state": "HIGH_MINUS_LOW",
                        "covariate": covariate,
                        "valid_count": math.nan,
                        "mean": high_low,
                        "median": math.nan,
                        "q25": math.nan,
                        "q75": math.nan,
                        "iqr": math.nan,
                        "high_minus_low": high_low,
                        "standardized_difference": standardized_difference(
                            group.loc[
                                group["return_state"].eq(return_state)
                                & group["activity_state"].eq("HIGH_ACTIVITY"),
                                covariate,
                            ],
                            group.loc[
                                group["return_state"].eq(return_state)
                                & group["activity_state"].eq("LOW_ACTIVITY"),
                                covariate,
                            ],
                        ),
                    }
                )

    detail = pd.DataFrame(rows)
    summary_rows = []
    selected = detail.loc[
        detail["row_type"].isin(
            ["period_activity_characteristic", "period_return_activity_characteristic"]
        )
    ]
    for keys, group in selected.groupby(
        ["row_type", "return_state", "activity_state", "covariate"], dropna=False
    ):
        row_type, return_state, activity_state, covariate = keys
        summary_rows.append(
            {
                "row_type": row_type.replace("period_", "across_period_"),
                "period_index": "ALL",
                "return_state": return_state,
                "activity_state": activity_state,
                "covariate": covariate,
                "valid_count": group["valid_count"].mean(),
                "mean": group["mean"].mean(),
                "median": group["median"].median(),
                "q25": group["q25"].mean(),
                "q75": group["q75"].mean(),
                "iqr": group["iqr"].mean(),
            }
        )
    std = detail.loc[detail["row_type"].eq("period_standardized_difference")]
    for covariate, group in std.groupby("covariate"):
        values = group["mean"].dropna()
        summary_rows.append(
            {
                "row_type": "across_period_standardized_difference",
                "period_index": "ALL",
                "return_state": "ALL",
                "activity_state": "HIGH_MINUS_LOW",
                "covariate": covariate,
                "valid_count": len(values),
                "mean": values.mean(),
                "median": values.median(),
                "q25": values.quantile(0.10),
                "q75": values.quantile(0.90),
                "iqr": math.nan,
                "direction_consistency": (
                    (np.sign(values) == np.sign(values.mean())).mean()
                    if len(values)
                    else math.nan
                ),
            }
        )

    conditional = detail.loc[detail["row_type"].eq("period_return_state_high_minus_low")]
    for (return_state, covariate), group in conditional.groupby(
        ["return_state", "covariate"]
    ):
        values = group["high_minus_low"].dropna()
        standardized = group["standardized_difference"].dropna()
        summary_rows.append(
            {
                "row_type": "across_period_return_state_high_minus_low",
                "period_index": "ALL",
                "return_state": return_state,
                "activity_state": "HIGH_MINUS_LOW",
                "covariate": covariate,
                "valid_count": len(values),
                "mean": values.mean(),
                "median": values.median(),
                "q25": values.quantile(0.10),
                "q75": values.quantile(0.90),
                "iqr": math.nan,
                "high_minus_low": values.mean(),
                "standardized_difference": standardized.mean(),
                "direction_consistency": (
                    (np.sign(values) == np.sign(values.mean())).mean()
                    if len(values)
                    else math.nan
                ),
            }
        )

    size_valid = panel.loc[panel["log_total_market_cap"].notna()].copy()
    size_valid["size_state"] = pd.NA
    for _, group in size_valid.groupby("period_index"):
        size_valid.loc[group.index, "size_state"] = ordinal_groups(
            group, "log_total_market_cap", ("SMALL", "MID_SIZE", "LARGE")
        )
    for size_state, group in size_valid.groupby("size_state"):
        for activity_state in ACTIVITY_STATES:
            periods = []
            for _, period in group.groupby("period_index"):
                values = period.loc[period["activity_state"].eq(activity_state), "activity_pct"]
                periods.append(
                    {
                        "count": len(values),
                        "median": values.median(),
                        "iqr": values.quantile(0.75) - values.quantile(0.25),
                    }
                )
            frame = pd.DataFrame(periods)
            summary_rows.append(
                {
                    "row_type": "size_tercile_activity_spread",
                    "period_index": "ALL",
                    "return_state": size_state,
                    "activity_state": activity_state,
                    "covariate": "activity_pct",
                    "valid_count": frame["count"].mean(),
                    "mean": frame["median"].mean(),
                    "median": frame["median"].median(),
                    "q25": math.nan,
                    "q75": math.nan,
                    "iqr": frame["iqr"].mean(),
                }
            )
    return pd.concat([detail, pd.DataFrame(summary_rows)], ignore_index=True)


def _correlations(panel: pd.DataFrame) -> pd.DataFrame:
    covariates = [
        "log_amount_mean_20",
        "log_qfq_signal_price",
        "log_raw_signal_price",
        "vol20",
        "log_total_market_cap",
        "log_circulating_market_cap",
        "return_60",
    ]
    rows = []
    for scope in ["ALL", *RETURN_STATES]:
        scoped = panel if scope == "ALL" else panel.loc[panel["return_state"].eq(scope)]
        for covariate in covariates:
            period_rows = []
            for period, group in scoped.groupby("period_index"):
                valid = group[["activity_pct", covariate]].replace([np.inf, -np.inf], np.nan).dropna()
                rho = (
                    valid["activity_pct"].corr(valid[covariate], method="spearman")
                    if len(valid) >= 25 and valid[covariate].nunique() > 1
                    else math.nan
                )
                period_rows.append({"period_index": period, "rho": rho, "valid_count": len(valid)})
            periods = pd.DataFrame(period_rows)
            values = periods["rho"].dropna()
            rows.append(
                {
                    "scope": scope,
                    "covariate": covariate,
                    "periods": len(values),
                    "mean_spearman": values.mean(),
                    "median_spearman": values.median(),
                    "p10_spearman": values.quantile(0.10),
                    "p90_spearman": values.quantile(0.90),
                    "positive_period_ratio": values.gt(0).mean(),
                    "median_valid_count": periods["valid_count"].median(),
                }
            )
    return pd.DataFrame(rows)


def _load_industry(root: Path) -> pd.DataFrame:
    path = root / "theme_business_review_completed_001_200.csv"
    mapping = pd.read_csv(path, dtype={"code": str}, usecols=["code", "sw_industry"])
    mapping["stock_code"] = mapping["code"].map(code6)
    mapping["sw_industry"] = mapping["sw_industry"].fillna("UNMAPPED")
    return mapping[["stock_code", "sw_industry"]].drop_duplicates("stock_code")


def _composition(panel: pd.DataFrame, industry: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for composition_type, category, working in (
        ("board", "board", panel),
        ("industry", "sw_industry", panel.merge(industry, on="stock_code", how="inner")),
    ):
        for period, group in working.groupby("period_index"):
            universe_weight = group[category].value_counts(normalize=True)
            mapping_coverage = len(group) / len(panel.loc[panel["period_index"].eq(period)])
            for activity_state, activity in group.groupby("activity_state"):
                weights = activity[category].value_counts(normalize=True)
                hhi = float((weights**2).sum())
                for label in sorted(set(universe_weight.index) | set(weights.index)):
                    rows.append(
                        {
                            "row_type": "period_composition",
                            "composition_type": composition_type,
                            "period_index": period,
                            "activity_state": activity_state,
                            "category": label,
                            "weight": weights.get(label, 0.0),
                            "universe_weight": universe_weight.get(label, 0.0),
                            "weight_difference": weights.get(label, 0.0)
                            - universe_weight.get(label, 0.0),
                            "hhi": hhi,
                            "mapping_coverage": mapping_coverage,
                        }
                    )
    detail = pd.DataFrame(rows)
    if detail.empty:
        raise ValueError("board_composition_unavailable")
    summary = detail.groupby(
        ["composition_type", "activity_state", "category"], as_index=False
    ).agg(
        weight=("weight", "mean"),
        universe_weight=("universe_weight", "mean"),
        weight_difference=("weight_difference", "mean"),
        hhi=("hhi", "mean"),
        mapping_coverage=("mapping_coverage", "mean"),
        periods=("period_index", "nunique"),
    )
    summary.insert(0, "row_type", "across_period_composition")
    summary.insert(2, "period_index", "ALL")
    return pd.concat([detail, summary], ignore_index=True)


def _interpretation(correlations: pd.DataFrame, inventory: pd.DataFrame) -> str:
    overall = correlations.loc[correlations["scope"].eq("ALL")].set_index("covariate")
    values = {
        "size": abs(overall.loc["log_total_market_cap", "mean_spearman"]),
        "price": abs(overall.loc["log_raw_signal_price", "mean_spearman"]),
        "volatility": abs(overall.loc["vol20", "mean_spearman"]),
    }
    material = sum(value >= 0.30 for value in values.values())
    size_coverage = float(
        inventory.loc[inventory["covariate"].eq("total_market_cap"), "coverage"].iloc[0]
    )
    if material >= 2:
        return "ACTIVITY_MULTI_FACTOR_PROXY"
    if values["size"] >= 0.50 and size_coverage >= 0.80:
        return "ACTIVITY_STRONGLY_SIZE_RELATED"
    if values["volatility"] >= 0.50:
        return "ACTIVITY_STRONGLY_VOLATILITY_RELATED"
    if size_coverage < 0.80:
        return "ACTIVITY_INTERPRETATION_INCONCLUSIVE"
    return "ACTIVITY_RELATIVELY_DISTINCT"


def _fmt(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value:.3f}"


def _write_report(
    path: Path,
    classification: str,
    inventory: pd.DataFrame,
    characteristics: pd.DataFrame,
    correlations: pd.DataFrame,
    composition: pd.DataFrame,
) -> None:
    overall = correlations.loc[correlations["scope"].eq("ALL")].set_index("covariate")
    state_corr = correlations.loc[
        correlations["scope"].isin(RETURN_STATES)
        & correlations["covariate"].isin(
            ["log_total_market_cap", "log_raw_signal_price", "vol20", "return_60"]
        )
    ]
    state_table = state_corr.pivot(index="covariate", columns="scope", values="mean_spearman")
    state_table = state_table.reindex(columns=RETURN_STATES)
    activity_summary = characteristics.loc[
        characteristics["row_type"].eq("across_period_activity_characteristic")
        & characteristics["covariate"].isin(
            ["log_amount_mean_20", "log_raw_signal_price", "vol20", "log_total_market_cap"]
        )
    ]
    activity_table = activity_summary.pivot(
        index="covariate", columns="activity_state", values="median"
    ).reindex(columns=ACTIVITY_STATES)
    amount_periods = characteristics.loc[characteristics["row_type"].eq("amount_period_scale")]
    raw_amount_states = characteristics.loc[
        characteristics["row_type"].eq("across_period_activity_characteristic")
        & characteristics["covariate"].eq("amount_mean_20")
    ].set_index("activity_state")
    board = composition.loc[
        composition["row_type"].eq("across_period_composition")
        & composition["composition_type"].eq("board")
    ]
    industry = composition.loc[
        composition["row_type"].eq("across_period_composition")
        & composition["composition_type"].eq("industry")
    ]
    board_extremes = board.sort_values("weight_difference").groupby("activity_state").agg(
        most_under=("category", "first"), most_over=("category", "last")
    )
    industry_top = industry.sort_values(
        ["activity_state", "weight"], ascending=[True, False]
    ).groupby("activity_state").head(3)
    size_status = inventory.loc[
        inventory["covariate"].eq("total_market_cap"), "point_in_time_status"
    ].iloc[0]
    size_coverage = inventory.loc[
        inventory["covariate"].eq("total_market_cap"), "coverage"
    ].iloc[0]
    report = f"""# H5A Activity Main Effect Decomposition Audit

## Technical summary

**{classification}.** The frozen H5A activity proxy is not a clean one-dimensional trading-activity measure. Across the 56 Primary signal periods, ACTIVITY_PCT has mean period Spearman correlations of **{_fmt(overall.loc['log_total_market_cap', 'mean_spearman'])}** with log total market cap, **{_fmt(overall.loc['log_raw_signal_price', 'mean_spearman'])}** with log RAW price, **{_fmt(overall.loc['vol20', 'mean_spearman'])}** with VOL20, and **{_fmt(overall.loc['return_60', 'mean_spearman'])}** with RETURN60. This audit uses signal-time characteristics only and does not recompute or inspect state-conditioned future performance.

The safest interpretation is that AMOUNT_MEAN20/ACTIVITY_PCT is an **amount-based multi-factor proxy** whose exposure must be separated from a pure turnover or liquidity interpretation. The largest observed confound is identified below from the absolute signal-time correlations. No causal claim follows.

## Raw amount ranks encode large scale separation

ACTIVITY_PCT is the within-period average rank of AMOUNT_MEAN20, so its Spearman relationship with log amount is mechanically one. Across periods, the raw amount cross-section had a median p10 of **{amount_periods['q25'].median():,.0f}**, median of **{amount_periods['median'].median():,.0f}**, and median p90 of **{amount_periods['q75'].median():,.0f}** currency units. The typical period median raw amount by frozen activity state was LOW **{raw_amount_states.loc['LOW_ACTIVITY', 'median']:,.0f}**, MID **{raw_amount_states.loc['MID_ACTIVITY', 'median']:,.0f}**, and HIGH **{raw_amount_states.loc['HIGH_ACTIVITY', 'median']:,.0f}**.

{activity_table.to_markdown(floatfmt='.3f')}

## Size is historically dated but not fully vintage-audited

Signal-date total and circulating market-cap fields are available for **{size_coverage:.1%}** of H5A Primary members. Their status is `{size_status}`: values vary by historical date, but the underlying share/effective-date lineage has not been independently audited. They are acceptable for this descriptive contamination audit, not for a claim of fully reconstructed point-in-time fundamentals or turnover.

Within size terciles, ACTIVITY_PCT retains spread; therefore activity is not exactly identical to size state. The detailed size-tercile occupancy and IQR are in `h5a_activity_characteristics.csv`.

## Price, volatility and return-state exposure remain visible

RAW signal-date close is the preferred price-level diagnostic; QFQ absolute price is also reported but its scale depends on the adjustment base. VOL20 exactly reuses the existing 21-price/20-return annualized sample-standard-deviation and flat-price reliability contract. No alternative window was calculated.

Mean period Spearman by frozen RETURN state:

{state_table.to_markdown(floatfmt='.3f')}

The conditional table shows whether size, price and volatility exposure remains after restricting comparisons to LOW/MID/HIGH_RETURN. It is descriptive and is not a controlled-return regression.

## Board composition is measurable; industry evidence is sparse

Board membership is fully code-derived. The most over- and underrepresented board in each activity state is:

{board_extremes.to_markdown()}

Current SW industry labels cover only **{industry['mapping_coverage'].mean():.1%}** of Primary members and are not point-in-time. The following are the largest industries inside that mapped subset only; they must not be generalized to broader-A:

{industry_top[['activity_state', 'category', 'weight', 'weight_difference']].to_markdown(index=False, floatfmt='.3f')}

## Listing age and other unavailable controls

No reliable local listing-date table exists. `listing_age_at_signal` is therefore unavailable and was not inferred from first price appearance. The local turnover field was also excluded because its denominator lineage is unresolved. No current snapshot was backfilled into historical periods.

## Interpretation boundary

H5A established a historical_seen association between frozen activity states and future paths. This audit shows what the signal-time activity proxy co-represents; it does not ask what future-return effect survives controls. The H5A result should currently be described as an association for an amount-ranked state that also carries size, price, volatility and composition exposures—not as evidence that trading activity alone causes continuation or reversal.

## Recommended next step

The most valuable next design step is to preregister one confound-control study beginning with the largest verified signal-time exposure, while retaining the frozen H5A states and without searching alternative proxies. Do not execute that control until the student approves a separate plan. Historical size lineage and broader-A point-in-time industry/listing data remain the highest-value data-quality improvements.

## Further questions

- Can the source owner document how historical total/circulating market cap and share counts were reconstructed?
- Can broader-A historical industry effective dates and listing dates be sourced without opening prospective/final data?
- Should a later, separately approved design distinguish activity from size using a single preregistered stratification rather than iterative neutralization?

## Method and limitations

- Primary periods: `period_index=1–56`; period 0 excluded by the existing low-coverage rule.
- Frozen H5A activity membership was reconstructed with the formal H5A function and reconciled exactly to official stock counts; no state was redefined.
- All numeric summaries first use within-period cross-sections and then give each period equal weight.
- Correlations are period-level Spearman summaries; no p-values, future returns, regressions, neutralization or proxy search are used.
- Industry uses a current, incomplete 200-code mapping (`industry_point_in_time=false`).
- Current-universe survivorship bias remains.

## Audit identity

{'; '.join(f'{key}={str(value).lower() if isinstance(value, bool) else value}' for key, value in IDENTITY.items())}
"""
    path.write_text(report, encoding="utf-8")


def run(root: Path) -> str:
    root = root.resolve()
    states = _load_states(root)
    panel = _build_covariate_panel(root, states)
    inventory = _inventory(panel)
    characteristics = _characteristics(panel)
    correlations = _correlations(panel)
    composition = _composition(panel, _load_industry(root))
    classification = _interpretation(correlations, inventory)

    output = root / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    inventory.to_csv(output / "h5a_activity_covariate_inventory.csv", index=False, encoding="utf-8-sig")
    characteristics.to_csv(output / "h5a_activity_characteristics.csv", index=False, encoding="utf-8-sig")
    correlations.to_csv(output / "h5a_activity_correlations.csv", index=False, encoding="utf-8-sig")
    composition.to_csv(
        output / "h5a_activity_industry_composition.csv", index=False, encoding="utf-8-sig"
    )
    _write_report(
        output / "h5a_activity_main_effect_audit.md",
        classification,
        inventory,
        characteristics,
        correlations,
        composition,
    )
    print(f"H5A_ACTIVITY_AUDIT_COMPLETE classification={classification}")
    return classification


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    run(args.project_root)


if __name__ == "__main__":
    main()
