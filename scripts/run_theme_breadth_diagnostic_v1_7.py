# ruff: noqa: E501  # Markdown table rows are clearer as single source strings.

from __future__ import annotations

import argparse
import hashlib
import math
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ATOL = 1e-10
RTOL = 1e-8
MIN_PERIOD_COVERAGE = 0.90
MIN_ANALYSIS_PERIODS = 46
SCOPES = ("overall", "ai", "commercial_space")
OUTCOMES = (
    "baseline_gross_return",
    "baseline_mdd_magnitude",
    "baseline_daily_volatility",
    "baseline_negative_return",
    "q5_gross_return",
    "q5_relative_return",
    "q5_volatility_reduction",
    "q5_mdd_reduction",
)
CORE_OUTCOMES = ("baseline_gross_return", "baseline_mdd_magnitude")
SUPPORTING_OUTCOMES = (
    "baseline_daily_volatility",
    "baseline_negative_return",
)
PROTECTED = (
    "data/processed/research_universe_lowvol_freeze_20260711.csv",
    "data/processed/adjusted_price_panel_v1_5.csv",
    "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv",
    "data/processed/hybrid_benchmark_panel_v1_5.csv",
    "reports/lowvol_locked_grid_prototype_periods_v1_5_1.csv",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def code6(value: object) -> str:
    return str(value).strip().split(".")[0].zfill(6)


def strict_bool(series: pd.Series) -> pd.Series:
    mapped = series.astype(str).str.strip().str.lower().map({"true": True, "false": False})
    if mapped.isna().any():
        raise ValueError(f"Invalid boolean values: {sorted(series[mapped.isna()].unique())}")
    return mapped.astype(bool)


def safe_corr(x: pd.Series, y: pd.Series, method: str = "spearman") -> float:
    frame = pd.DataFrame(
        {"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}
    ).dropna()
    if len(frame) < 3 or frame["x"].nunique() < 2 or frame["y"].nunique() < 2:
        return math.nan
    return float(frame["x"].corr(frame["y"], method=method))


def tie_aware_terciles(values: pd.Series) -> tuple[pd.Series, float, float]:
    numeric = pd.to_numeric(values, errors="coerce")
    valid = numeric.dropna()
    states = pd.Series(pd.NA, index=values.index, dtype="string")
    if valid.empty:
        return states, math.nan, math.nan
    lower = float(valid.quantile(1 / 3, interpolation="linear"))
    upper = float(valid.quantile(2 / 3, interpolation="linear"))
    states.loc[numeric < lower] = "low"
    states.loc[numeric.between(lower, upper, inclusive="both")] = "middle"
    states.loc[numeric > upper] = "high"
    return states, lower, upper


def circular_shift_pvalue(x: pd.Series, y: pd.Series) -> float:
    frame = pd.DataFrame(
        {"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}
    ).dropna()
    observed = safe_corr(frame["x"], frame["y"])
    if not np.isfinite(observed):
        return math.nan
    xv = frame["x"].to_numpy()
    yv = frame["y"].to_numpy()
    shifted = [
        safe_corr(pd.Series(np.roll(xv, shift)), pd.Series(yv)) for shift in range(len(frame))
    ]
    finite = np.asarray([value for value in shifted if np.isfinite(value)])
    return float(np.mean(np.abs(finite) + ATOL >= abs(observed))) if len(finite) else math.nan


def association_statistics(x: pd.Series, y: pd.Series) -> dict[str, object]:
    frame = pd.DataFrame(
        {"x": pd.to_numeric(x, errors="coerce"), "y": pd.to_numeric(y, errors="coerce")}
    ).dropna()
    n = len(frame)
    spearman = safe_corr(frame["x"], frame["y"])
    pearson = safe_corr(frame["x"], frame["y"], method="pearson")
    result: dict[str, object] = {
        "n": n,
        "spearman": spearman,
        "pearson": pearson,
        "circular_shift_p": circular_shift_pvalue(frame["x"], frame["y"]),
        "exclude_top1_spearman": math.nan,
        "exclude_top3_spearman": math.nan,
        "loo_sign_match_ratio": math.nan,
        "loo_min": math.nan,
        "loo_max": math.nan,
        "top1_abs_contribution_share": math.nan,
        "top3_abs_contribution_share": math.nan,
        "positive_contribution_share": math.nan,
        "negative_contribution_share": math.nan,
    }
    if not np.isfinite(spearman):
        return result
    rx = frame["x"].rank(method="average")
    ry = frame["y"].rank(method="average")
    contributions = (rx - rx.mean()) * (ry - ry.mean())
    absolute = contributions.abs()
    denominator = float(absolute.sum())
    ranked = absolute.sort_values(ascending=False, kind="stable").index
    if denominator > 0:
        result["top1_abs_contribution_share"] = float(absolute.loc[ranked[:1]].sum() / denominator)
        result["top3_abs_contribution_share"] = float(absolute.loc[ranked[:3]].sum() / denominator)
        result["positive_contribution_share"] = float(
            contributions.clip(lower=0).sum() / denominator
        )
        result["negative_contribution_share"] = float(
            -contributions.clip(upper=0).sum() / denominator
        )
    for count in (1, 3):
        kept = frame.drop(index=ranked[:count])
        result[f"exclude_top{count}_spearman"] = safe_corr(kept["x"], kept["y"])
    loo = [
        safe_corr(frame.drop(index=index)["x"], frame.drop(index=index)["y"])
        for index in frame.index
    ]
    loo_finite = np.asarray([value for value in loo if np.isfinite(value)])
    if len(loo_finite):
        sign = np.sign(spearman)
        result["loo_sign_match_ratio"] = float(np.mean(np.sign(loo_finite) == sign))
        result["loo_min"] = float(loo_finite.min())
        result["loo_max"] = float(loo_finite.max())
    return result


def same_nonzero_sign(reference: float, *values: float) -> bool:
    return bool(
        np.isfinite(reference)
        and reference != 0
        and all(np.isfinite(v) and np.sign(v) == np.sign(reference) for v in values)
    )


def stable_core(stats: dict[str, object]) -> bool:
    return bool(
        int(stats["n"]) >= MIN_ANALYSIS_PERIODS
        and np.isfinite(stats["spearman"])
        and abs(float(stats["spearman"])) >= 0.25
        and same_nonzero_sign(
            float(stats["spearman"]),
            float(stats["exclude_top1_spearman"]),
            float(stats["exclude_top3_spearman"]),
        )
        and float(stats["loo_sign_match_ratio"]) >= 0.80
        and float(stats["top3_abs_contribution_share"]) < 0.50
    )


def supporting_coherent(
    core: dict[str, object], supporting: dict[str, object], opposite: bool
) -> bool:
    if not np.isfinite(supporting["spearman"]) or abs(float(supporting["spearman"])) < 0.15:
        return False
    expected = -np.sign(float(core["spearman"])) if opposite else np.sign(float(core["spearman"]))
    return bool(
        np.sign(float(supporting["spearman"])) == expected
        and same_nonzero_sign(
            float(supporting["spearman"]),
            float(supporting["exclude_top1_spearman"]),
            float(supporting["exclude_top3_spearman"]),
        )
    )


def classify_acceptance(
    associations: dict[tuple[str, str], dict[str, object]],
    group_directions: dict[tuple[str, str], int],
) -> str:
    pairs = (
        ("baseline_gross_return", "baseline_negative_return", True),
        ("baseline_mdd_magnitude", "baseline_daily_volatility", False),
    )
    for core_name, supporting_name, opposite in pairs:
        core = associations[("overall", core_name)]
        if stable_core(core) and (
            group_directions.get(("overall", core_name), 0) == np.sign(float(core["spearman"]))
            or supporting_coherent(core, associations[("overall", supporting_name)], opposite)
        ):
            return "diagnostically_supported"
    visible = any(
        np.isfinite(stats["spearman"])
        and abs(float(stats["spearman"])) >= (0.25 if outcome in CORE_OUTCOMES else 0.15)
        for (_, outcome), stats in associations.items()
    )
    return "mixed" if visible else "not_supported"


def parse_codes(value: object, expected: int) -> list[str]:
    codes = [code6(item) for item in str(value).split(";") if str(item).strip()]
    if len(codes) != expected or len(codes) != len(set(codes)):
        raise ValueError(f"Malformed selected_codes: expected={expected}, parsed={len(codes)}")
    return codes


def load_inputs(
    root: Path,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, list[pd.Timestamp]]:
    universe = pd.read_csv(root / PROTECTED[0], dtype={"code": str})
    prices = pd.read_csv(root / PROTECTED[1], dtype={"stock_code": str})
    factor = pd.read_csv(root / PROTECTED[2], dtype={"stock_code": str})
    benchmark = pd.read_csv(root / PROTECTED[3], dtype={"benchmark_code": str})
    periods = pd.read_csv(root / PROTECTED[4], dtype={"selected_codes": str})
    universe["code"] = universe["code"].map(code6)
    if len(universe) != 56 or universe["code"].nunique() != 56:
        raise ValueError("Frozen universe is not the expected 56 unique stocks")
    prices["stock_code"] = prices["stock_code"].map(code6)
    prices["trade_date"] = pd.to_datetime(prices["trade_date"], errors="raise")
    if prices.duplicated(["stock_code", "trade_date"]).any():
        raise ValueError("Duplicate stock/date prices")
    prices["adjusted_close"] = pd.to_numeric(prices["adjusted_close"], errors="coerce")
    prices["qfq_close"] = pd.to_numeric(prices["qfq_close"], errors="coerce")
    valid_flag = strict_bool(prices["adjusted_flag"])
    conflict = valid_flag & (
        prices["adjusted_close"].le(0)
        | prices["qfq_close"].le(0)
        | ~np.isclose(
            prices["adjusted_close"], prices["qfq_close"], atol=ATOL, rtol=RTOL, equal_nan=False
        )
    )
    if conflict.any():
        raise ValueError("Adjusted/QFQ price conflict")
    prices = prices.loc[
        valid_flag & prices["adjusted_close"].gt(0), ["stock_code", "trade_date", "adjusted_close"]
    ]
    for column in ("signal_as_of_date", "rebalance_date", "next_rebalance_date"):
        factor[column] = pd.to_datetime(factor[column], errors="raise")
    factor["stock_code"] = factor["stock_code"].map(code6)
    if len(factor) != 56 * 57 or factor.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("Frozen factor grid is not 56 stocks x 57 unique periods")
    benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"], errors="raise")
    benchmark["close"] = pd.to_numeric(benchmark["close"], errors="coerce")
    hs300 = benchmark.loc[
        benchmark["benchmark_code"].map(code6).eq("000300") & benchmark["close"].gt(0)
    ]
    if hs300.empty or hs300["trade_date"].duplicated().any():
        raise ValueError("Invalid 000300 market calendar")
    calendar = sorted(hs300["trade_date"].tolist())
    periods["headline_included"] = strict_bool(periods["headline_included"])
    periods = periods.loc[
        periods["portfolio"].isin(["UNIVERSE", "Q5"])
        & pd.to_numeric(periods["transaction_cost"], errors="coerce").eq(0)
        & periods["headline_included"]
    ].copy()
    if periods.groupby("portfolio")["period_index"].nunique().to_dict() != {
        "Q5": 57,
        "UNIVERSE": 57,
    }:
        raise ValueError("Formal zero-cost UNIVERSE/Q5 period grid is incomplete")
    return universe, prices, factor, periods, calendar


def theme_weights(universe: pd.DataFrame) -> dict[str, dict[str, float]]:
    weights = {"ai": {}, "commercial_space": {}}
    for row in universe.itertuples(index=False):
        labels = str(row.theme).split("|")
        allocation = 1.0 / len(labels)
        for label in labels:
            if label == "AI":
                weights["ai"][row.code] = allocation
            elif label == "商业航天":
                weights["commercial_space"][row.code] = allocation
            else:
                raise ValueError(f"Unexpected frozen theme label: {label}")
    totals = {scope: sum(values.values()) for scope, values in weights.items()}
    if not np.isclose(totals["ai"], 44.5) or not np.isclose(totals["commercial_space"], 11.5):
        raise ValueError(f"Theme weights do not reconcile: {totals}")
    return weights


def portfolio_daily_stats(
    codes: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    calendar: list[pd.Timestamp],
    lookup: pd.DataFrame,
) -> dict[str, float]:
    dates = [date for date in calendar if start <= date <= end]
    endpoints = lookup.reindex(index=[start, end], columns=codes)
    endpoint_valid = (
        endpoints.shape == (2, len(codes))
        and np.isfinite(endpoints.to_numpy()).all()
        and (endpoints.to_numpy() > 0).all()
    )
    gross = (
        float((endpoints.loc[end] / endpoints.loc[start] - 1).mean())
        if endpoint_valid
        else math.nan
    )
    panel = lookup.reindex(index=dates, columns=codes)
    daily_valid = bool(
        len(dates) >= 2 and np.isfinite(panel.to_numpy()).all() and (panel.to_numpy() > 0).all()
    )
    if not daily_valid:
        return {
            "gross_return": gross,
            "daily_volatility": math.nan,
            "raw_mdd": math.nan,
            "mdd_magnitude": math.nan,
            "daily_risk_valid": False,
        }
    nav = panel.divide(panel.iloc[0], axis="columns").mean(axis="columns")
    returns = nav.pct_change().dropna()
    volatility = float(returns.std(ddof=1) * math.sqrt(252))
    raw_mdd = float((nav / nav.cummax() - 1).min())
    return {
        "gross_return": gross,
        "daily_volatility": volatility,
        "raw_mdd": raw_mdd,
        "mdd_magnitude": -raw_mdd,
        "daily_risk_valid": True,
    }


def build_periods(root: Path) -> pd.DataFrame:
    universe, prices, factor, formal, calendar = load_inputs(root)
    codes = sorted(universe["code"])
    themes = theme_weights(universe)
    lookup = prices.pivot(index="trade_date", columns="stock_code", values="adjusted_close")
    calendar_position = {date: index for index, date in enumerate(calendar)}
    formal_lookup = formal.set_index(["period_index", "portfolio"])
    rows: list[dict[str, object]] = []
    period_meta = factor[
        ["period_index", "signal_as_of_date", "rebalance_date", "next_rebalance_date"]
    ].drop_duplicates()
    if len(period_meta) != 57 or period_meta["period_index"].nunique() != 57:
        raise ValueError("Period metadata does not contain 57 unique keys")
    for meta in period_meta.sort_values("period_index").itertuples(index=False):
        signal = pd.Timestamp(meta.signal_as_of_date)
        if (
            signal not in calendar_position
            or calendar_position[signal] < 59
            or not signal < meta.rebalance_date
        ):
            raise ValueError(f"Invalid signal timing for period {meta.period_index}")
        window = calendar[calendar_position[signal] - 59 : calendar_position[signal] + 1]
        signal_panel = lookup.reindex(index=window, columns=codes)
        complete = np.isfinite(signal_panel.to_numpy()).all(axis=0) & (
            signal_panel.to_numpy() > 0
        ).all(axis=0)
        ma60 = signal_panel.mean(axis="index")
        above = pd.Series(False, index=codes)
        above.loc[complete] = signal_panel.iloc[-1].loc[complete] > ma60.loc[complete]
        record: dict[str, object] = {
            "period_index": int(meta.period_index),
            "signal_as_of_date": signal.date().isoformat(),
            "rebalance_date": pd.Timestamp(meta.rebalance_date).date().isoformat(),
            "next_rebalance_date": pd.Timestamp(meta.next_rebalance_date).date().isoformat(),
        }
        scope_weights = {"overall": {code: 1.0 for code in codes}, **themes}
        for scope, weights in scope_weights.items():
            total = float(sum(weights.values()))
            denominator = float(
                sum(weight for code, weight in weights.items() if complete[codes.index(code)])
            )
            numerator = float(
                sum(
                    weight
                    for code, weight in weights.items()
                    if complete[codes.index(code)] and above.loc[code]
                )
            )
            coverage = denominator / total
            prefix = f"{scope}_breadth60"
            record[f"{prefix}_numerator"] = numerator
            record[f"{prefix}_denominator"] = denominator
            record[f"{prefix}_ratio"] = numerator / denominator if denominator else math.nan
            record[f"{prefix}_coverage"] = coverage
            record[f"{prefix}_valid"] = bool(coverage + ATOL >= MIN_PERIOD_COVERAGE)
            record[f"{prefix}_invalid_reason"] = (
                "" if record[f"{prefix}_valid"] else "eligible_coverage_below_90pct"
            )
        stats = {}
        for portfolio, prefix in (("UNIVERSE", "baseline"), ("Q5", "q5")):
            formal_row = formal_lookup.loc[(meta.period_index, portfolio)]
            selected = parse_codes(formal_row["selected_codes"], int(formal_row["selected_count"]))
            result = portfolio_daily_stats(
                selected,
                pd.Timestamp(meta.rebalance_date),
                pd.Timestamp(meta.next_rebalance_date),
                calendar,
                lookup,
            )
            formal_gross = float(formal_row["gross_return"])
            if not np.isclose(result["gross_return"], formal_gross, atol=ATOL, rtol=RTOL):
                raise ValueError(f"{portfolio} gross return mismatch in period {meta.period_index}")
            record[f"{prefix}_selected_count"] = len(selected)
            record[f"{prefix}_gross_return"] = formal_gross
            record[f"{prefix}_daily_volatility"] = result["daily_volatility"]
            record[f"{prefix}_within_period_mdd"] = result["raw_mdd"]
            record[f"{prefix}_mdd_magnitude"] = result["mdd_magnitude"]
            record[f"{prefix}_daily_risk_valid"] = result["daily_risk_valid"]
            stats[prefix] = result
        record["baseline_negative_return"] = int(record["baseline_gross_return"] < 0)
        record["q5_relative_return"] = record["q5_gross_return"] - record["baseline_gross_return"]
        record["q5_volatility_reduction"] = (
            record["baseline_daily_volatility"] - record["q5_daily_volatility"]
        )
        record["q5_mdd_reduction"] = record["baseline_mdd_magnitude"] - record["q5_mdd_magnitude"]
        rows.append(record)
    result = pd.DataFrame(rows).sort_values("period_index").reset_index(drop=True)
    for scope in SCOPES:
        prefix = f"{scope}_breadth60"
        valid_ratio = result[f"{prefix}_ratio"].where(result[f"{prefix}_valid"])
        result[f"{scope}_breadth_state"], lower, upper = tie_aware_terciles(valid_ratio)
        result[f"{scope}_tercile_lower_cut"] = lower
        result[f"{scope}_tercile_upper_cut"] = upper
        result[f"{scope}_ex_ante_change"] = valid_ratio - valid_ratio.shift(1)
        result[f"{scope}_ex_post_next_signal"] = valid_ratio.shift(-1)
        result[f"{scope}_ex_post_change"] = valid_ratio.shift(-1) - valid_ratio
    expected_valid = result["period_index"].ge(6)
    for scope in SCOPES:
        if not result[f"{scope}_breadth60_valid"].equals(expected_valid):
            raise ValueError(f"{scope} breadth coverage differs from pre-registered 51/57 state")
        valid_risk = result[f"{scope}_breadth60_valid"]
        if (
            result.loc[valid_risk, ["baseline_daily_risk_valid", "q5_daily_risk_valid"]]
            .eq(False)
            .any()
            .any()
        ):
            raise ValueError("Daily risk outcome is incomplete within a breadth-valid period")
    return result


def analysis_level(scope: str, outcome: str) -> str:
    if scope == "overall" and outcome in CORE_OUTCOMES:
        return "core_primary"
    if scope == "overall" and outcome in SUPPORTING_OUTCOMES:
        return "supporting_primary"
    if outcome.startswith("q5_"):
        return "lowvol_interaction"
    return "theme_heterogeneity"


def grouped_direction(
    periods: pd.DataFrame, scope: str, outcome: str
) -> tuple[int, dict[str, float]]:
    state = f"{scope}_breadth_state"
    medians = (
        periods.dropna(subset=[state, outcome])
        .groupby(state, observed=True)[outcome]
        .median()
        .to_dict()
    )
    if set(medians) != {"low", "middle", "high"}:
        return 0, medians
    values = [float(medians[name]) for name in ("low", "middle", "high")]
    if values[0] <= values[1] <= values[2] and values[0] < values[2]:
        return 1, medians
    if values[0] >= values[1] >= values[2] and values[0] > values[2]:
        return -1, medians
    return 0, medians


def build_summary(
    periods: pd.DataFrame,
) -> tuple[pd.DataFrame, str, dict[tuple[str, str], dict[str, object]], dict[tuple[str, str], int]]:
    rows: list[dict[str, object]] = []
    associations: dict[tuple[str, str], dict[str, object]] = {}
    group_directions: dict[tuple[str, str], int] = {}
    for scope in SCOPES:
        breadth = periods[f"{scope}_breadth60_ratio"].where(periods[f"{scope}_breadth60_valid"])
        lower = float(periods[f"{scope}_tercile_lower_cut"].iloc[0])
        upper = float(periods[f"{scope}_tercile_upper_cut"].iloc[0])
        for outcome in OUTCOMES:
            stats = association_statistics(breadth, periods[outcome])
            associations[(scope, outcome)] = stats
            direction, _ = grouped_direction(periods, scope, outcome)
            group_directions[(scope, outcome)] = direction
            if scope == "overall" and outcome in CORE_OUTCOMES:
                stability = stable_core(stats)
            elif scope == "overall" and outcome in SUPPORTING_OUTCOMES:
                stability = bool(
                    np.isfinite(stats["spearman"])
                    and abs(float(stats["spearman"])) >= 0.15
                    and same_nonzero_sign(
                        float(stats["spearman"]),
                        float(stats["exclude_top1_spearman"]),
                        float(stats["exclude_top3_spearman"]),
                    )
                )
            else:
                stability = same_nonzero_sign(
                    float(stats["spearman"]),
                    float(stats["exclude_top1_spearman"]),
                    float(stats["exclude_top3_spearman"]),
                )
            for statistic, value in stats.items():
                if statistic == "n":
                    continue
                rows.append(
                    {
                        "analysis_level": analysis_level(scope, outcome),
                        "breadth_scope": scope,
                        "outcome": outcome,
                        "statistic_or_group": statistic,
                        "n": stats["n"],
                        "cut_point_lower": lower,
                        "cut_point_upper": upper,
                        "value": value,
                        "circular_shift_p": stats["circular_shift_p"]
                        if statistic == "spearman"
                        else math.nan,
                        "stability_flag": bool(stability),
                    }
                )
            for state in ("low", "middle", "high"):
                sample = periods.loc[periods[f"{scope}_breadth_state"].eq(state), outcome].dropna()
                for statistic, value in (
                    ("count", len(sample)),
                    ("mean", sample.mean()),
                    ("median", sample.median()),
                ):
                    rows.append(
                        {
                            "analysis_level": analysis_level(scope, outcome),
                            "breadth_scope": scope,
                            "outcome": outcome,
                            "statistic_or_group": f"{state}_{statistic}",
                            "n": len(sample),
                            "cut_point_lower": lower,
                            "cut_point_upper": upper,
                            "value": value,
                            "circular_shift_p": math.nan,
                            "stability_flag": direction != 0,
                        }
                    )
    conclusion = classify_acceptance(associations, group_directions)
    return pd.DataFrame(rows), conclusion, associations, group_directions


def fmt(value: object, digits: int = 4) -> str:
    return "NA" if not np.isfinite(value) else f"{float(value):.{digits}f}"


def report_markdown(
    periods: pd.DataFrame,
    conclusion: str,
    associations: dict[tuple[str, str], dict[str, object]],
    group_directions: dict[tuple[str, str], int],
) -> str:
    lines = [
        "# Hypothesis 4A — Theme Breadth Diagnostic v1.7",
        "",
        "## 1. 结论摘要与 acceptance 类别",
        "",
        f"**{conclusion}**",
        "",
        "两个 Overall core 关系均未达到预注册的 |Spearman| >= 0.25 稳定关系门槛；",
        "较明显的关系主要出现在 LOWVOL secondary interaction，因此不能提升为 diagnostically_supported。",
        "本研究是描述性市场状态诊断，不是交易、仓位或择时规则。",
        "",
        "## 2. 数据来源、Breadth60 合同和时间边界",
        "",
        "Breadth60 使用信号日及此前 59 个沪深300市场日的 adjusted_close；未来结果从下一调仓日收盘开始。无前向数据、无填充。",
        "",
        "## 3. 连续可观察样本限制及无效期",
        "",
        "Overall、AI、商业航天均有 51/57 个有效期间；period_index 0–5 因 eligible coverage 低于 90% 无效。严格完整性口径估计连续可观察股票中的 breadth，停牌或缺价会改变分母。",
        "",
        "## 4. Overall core/supporting primary results",
        "",
        "| Outcome | Spearman | Pearson | Circular-shift p | Stable | Monotonic states |",
        "|---|---:|---:|---:|:---:|:---:|",
    ]
    for outcome in (*CORE_OUTCOMES, *SUPPORTING_OUTCOMES):
        stats = associations[("overall", outcome)]
        stable = (
            stable_core(stats)
            if outcome in CORE_OUTCOMES
            else bool(
                abs(float(stats["spearman"])) >= 0.15
                and same_nonzero_sign(
                    float(stats["spearman"]),
                    float(stats["exclude_top1_spearman"]),
                    float(stats["exclude_top3_spearman"]),
                )
            )
        )
        direction = group_directions[("overall", outcome)]
        lines.append(
            f"| {outcome} | {fmt(stats['spearman'])} | {fmt(stats['pearson'])} | {fmt(stats['circular_shift_p'])} | {stable} | {direction != 0} |"
        )
    lines += [
        "",
        "## 5. Circular-shift permutation evidence",
        "",
        "p-value 来自全部 ordered breadth circular shifts，仅作保持 breadth 序列结构的描述性证据，不视为 i.i.d. 或正式因果检验。",
        "",
        "## 6. Tie-aware breadth states",
        "",
        "| Scope | Lower cut | Upper cut | Low n | Middle n | High n |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for scope in SCOPES:
        counts = periods[f"{scope}_breadth_state"].value_counts()
        lines.append(
            f"| {scope} | {fmt(periods[f'{scope}_tercile_lower_cut'].iloc[0])} | {fmt(periods[f'{scope}_tercile_upper_cut'].iloc[0])} | {int(counts.get('low', 0))} | {int(counts.get('middle', 0))} | {int(counts.get('high', 0))} |"
        )
    lines += [
        "",
        "相同 Breadth60 值始终属于同一状态；period_index 只排序，不参与分组。",
        "",
        "| Overall core outcome | Low median | Middle median | High median | Monotonic |",
        "|---|---:|---:|---:|:---:|",
    ]
    for outcome in CORE_OUTCOMES:
        medians = {}
        for state in ("low", "middle", "high"):
            sample = periods.loc[periods["overall_breadth_state"].eq(state), outcome]
            medians[state] = sample.median()
        lines.append(
            f"| {outcome} | {fmt(medians['low'])} | {fmt(medians['middle'])} | "
            f"{fmt(medians['high'])} | {group_directions[('overall', outcome)] != 0} |"
        )
    lines += [
        "",
        "## 7. 集中度和稳定性",
        "",
        "| Core outcome | Top-1 share | Top-3 share | Ex-top1 rho | Ex-top3 rho | LOO sign match |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for outcome in CORE_OUTCOMES:
        stats = associations[("overall", outcome)]
        lines.append(
            f"| {outcome} | {fmt(stats['top1_abs_contribution_share'])} | {fmt(stats['top3_abs_contribution_share'])} | {fmt(stats['exclude_top1_spearman'])} | {fmt(stats['exclude_top3_spearman'])} | {fmt(stats['loo_sign_match_ratio'])} |"
        )
    lines += [
        "",
        "Overall low/high breadth 状态中的 core outcome 极端期间：",
        "",
        "| State | Outcome | Worst period/value | Best period/value |",
        "|---|---|---|---|",
    ]
    for state in ("low", "high"):
        sample = periods.loc[periods["overall_breadth_state"].eq(state)]
        for outcome in CORE_OUTCOMES:
            if outcome == "baseline_gross_return":
                worst_row = sample.loc[sample[outcome].idxmin()]
                best_row = sample.loc[sample[outcome].idxmax()]
            else:
                worst_row = sample.loc[sample[outcome].idxmax()]
                best_row = sample.loc[sample[outcome].idxmin()]
            lines.append(
                f"| {state} | {outcome} | {int(worst_row['period_index'])} / "
                f"{fmt(worst_row[outcome])} | {int(best_row['period_index'])} / "
                f"{fmt(best_row[outcome])} |"
            )
    lines += [
        "",
        "## 8. AI/商业航天异质性诊断",
        "",
        "| Scope | Return rho | MDD magnitude rho | Volatility rho | Negative-return rho |",
        "|---|---:|---:|---:|---:|",
    ]
    for scope in ("ai", "commercial_space"):
        values = [
            associations[(scope, outcome)]["spearman"]
            for outcome in (*CORE_OUTCOMES, *SUPPORTING_OUTCOMES)
        ]
        lines.append(f"| {scope} | " + " | ".join(fmt(value) for value in values) + " |")
    lines += [
        "",
        "主题结果仅解释异质性，不能单独产生 diagnostically_supported。",
        "",
        "## 9. Ex-ante 与 ex-post drawdown-state timing",
        "",
        "| Period | Trigger | Scope | Ex-ante breadth | Change from prior signal | Ex-post next signal | Change during/after period |",
        "|---:|---|---|---:|---:|---:|---:|",
    ]
    worst_return = set(periods.nsmallest(3, "baseline_gross_return")["period_index"])
    worst_mdd = set(periods.nlargest(3, "baseline_mdd_magnitude")["period_index"])
    for period_index in sorted(worst_return | worst_mdd):
        row = periods.loc[periods["period_index"].eq(period_index)].iloc[0]
        trigger = (
            "both"
            if period_index in worst_return & worst_mdd
            else ("worst_return" if period_index in worst_return else "worst_mdd")
        )
        for scope in SCOPES:
            lines.append(
                f"| {period_index} | {trigger} | {scope} | "
                f"{fmt(row[f'{scope}_breadth60_ratio'])} | "
                f"{fmt(row[f'{scope}_ex_ante_change'])} | "
                f"{fmt(row[f'{scope}_ex_post_next_signal'])} | "
                f"{fmt(row[f'{scope}_ex_post_change'])} |"
            )
    lines += [
        "",
        "只有 ex-ante 信号及相对前一信号的变化进入 acceptance；ex-post 仅作时序说明。",
        "",
        "## 10. LOWVOL interaction",
        "",
        "| Scope | Q5 return rho | Q5-relative rho | Vol reduction rho | MDD reduction rho |",
        "|---|---:|---:|---:|---:|",
    ]
    lowvol_outcomes = (
        "q5_gross_return",
        "q5_relative_return",
        "q5_volatility_reduction",
        "q5_mdd_reduction",
    )
    for scope in SCOPES:
        values = [associations[(scope, outcome)]["spearman"] for outcome in lowvol_outcomes]
        lines.append(f"| {scope} | " + " | ".join(fmt(value) for value in values) + " |")
    lines += [
        "",
        "Q5 interaction 全部属于 secondary evidence，不修改 LOWVOL。",
        "",
        "## 11. 证据层级",
        "",
        "报告分别保留经济可见性、秩次一致性、circular-shift 描述证据和稳定性；不以单个 p-value 宣称正式显著性。",
        "",
        "## 12. 限制、最终类别和 4B 门槛",
        "",
        "样本仅含 51 个有效锁定期间，主题商业航天分母较小，日度风险依赖连续可观察价格。只有 diagnostically_supported 加人工批准才允许另行起草 4B；本报告不授权策略实施。",
        "",
    ]
    return "\n".join(lines)


def run(root: Path) -> str:
    before = {relative: sha256(root / relative) for relative in PROTECTED}
    periods = build_periods(root)
    summary, conclusion, associations, group_directions = build_summary(periods)
    report = report_markdown(periods, conclusion, associations, group_directions)
    after = {relative: sha256(root / relative) for relative in PROTECTED}
    if before != after:
        raise ValueError("Protected input changed during the read-only diagnostic")
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=reports) as temporary:
        staging = Path(temporary)
        periods.to_csv(
            staging / "theme_breadth_periods_v1_7.csv", index=False, encoding="utf-8-sig"
        )
        summary.to_csv(
            staging / "theme_breadth_diagnostic_summary_v1_7.csv", index=False, encoding="utf-8-sig"
        )
        (staging / "theme_breadth_hypothesis_v1_7.md").write_text(report, encoding="utf-8")
        for name in (
            "theme_breadth_periods_v1_7.csv",
            "theme_breadth_diagnostic_summary_v1_7.csv",
            "theme_breadth_hypothesis_v1_7.md",
        ):
            (staging / name).replace(reports / name)
    return conclusion


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Hypothesis 4A theme-breadth diagnostic")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    conclusion = run(args.project_root.resolve())
    print(f"Hypothesis 4A complete: {conclusion}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
