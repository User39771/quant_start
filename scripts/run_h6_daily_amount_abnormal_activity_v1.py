"""Run only the preregistered historical-seen H6 amount diagnostic."""

# ruff: noqa: E501 -- compact, auditable report text.
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import rankdata

if __package__:
    from scripts.audit_h6_abnormal_activity_readiness import _load_states, _market_calendar
    from scripts.run_h5a_trading_activity_reversal_timing_v1 import (
        direction_consistency,
        loo_sign_consistency,
        moving_block_interval,
    )
else:
    from audit_h6_abnormal_activity_readiness import _load_states, _market_calendar
    from run_h5a_trading_activity_reversal_timing_v1 import (
        direction_consistency,
        loo_sign_consistency,
        moving_block_interval,
    )

OUT = Path("reports/hypothesis_6")
PERIODS = tuple(range(3, 57))
HORIZONS = (5, 10, 20)
RETURNS = ("LOW_RETURN", "MID_RETURN", "HIGH_RETURN")
SHOCKS = ("LOW_SHOCK", "NORMAL", "HIGH_SHOCK")
IDENTITY = {
    "sample_role": "historical_seen",
    "research_type": "mechanism_diagnostic",
    "descriptive_only": True,
    "alpha_claim_allowed": False,
    "oos_claim_allowed": False,
    "causal_claim_allowed": False,
    "strategy_claim_allowed": False,
    "execution_claim_allowed": False,
    "D04_replication_claim_allowed": False,
    "human_interpretation_required": True,
}


def write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.assign(**IDENTITY).to_csv(path, index=False, encoding="utf-8")


def exact_window(
    calendar: pd.DatetimeIndex, signal: pd.Timestamp, size: int = 50
) -> pd.DatetimeIndex:
    end = calendar.get_loc(signal)
    if end < size - 1:
        raise ValueError("insufficient_calendar_history")
    return calendar[end - size + 1 : end + 1]


def midrank_rows(values: np.ndarray, nonnegative: bool = True) -> pd.DataFrame:
    """Each row is exactly 50 dates; formation is the final column, ties are neutral."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 2 or values.shape[1] != 50:
        raise ValueError("exact_50_observations_required")
    finite = np.isfinite(values)
    valid = finite.all(axis=1)
    if nonnegative:
        valid &= (values >= 0).all(axis=1)
    last = values[:, -1:]
    equal = (values == last).sum(axis=1)
    ranks = (values < last).sum(axis=1) + (equal + 1) / 2
    ranks = np.where(valid, ranks, np.nan)
    shocks = np.where(ranks <= 5, "LOW_SHOCK", np.where(ranks >= 46, "HIGH_SHOCK", "NORMAL"))
    shocks = np.where(valid, shocks, "INVALID")
    return pd.DataFrame(
        {
            "valid_50d": valid,
            "midrank": ranks,
            "own_history_percentile": (ranks - 0.5) / 50,
            "shock_state": shocks,
            "formation_tie_count": equal,
            "amount_zero_flag": (values == 0).any(axis=1),
            "amount_zero_days": (values == 0).sum(axis=1),
            "missing_nonfinite_days": (~finite).sum(axis=1),
            "negative_days": (values < 0).sum(axis=1),
        }
    )


def trend_rows(values: np.ndarray) -> np.ndarray:
    result = np.full(len(values), np.nan)
    valid = np.isfinite(values).all(axis=1) & (values >= 0).all(axis=1)
    ranks = rankdata(values[valid], axis=1, method="average")
    centered = ranks - ranks.mean(axis=1, keepdims=True)
    time = np.arange(1, 51, dtype=float) - 25.5
    denominator = np.sqrt((centered**2).sum(axis=1) * (time**2).sum())
    result[valid] = np.divide(
        centered @ time, denominator, out=np.full(len(ranks), np.nan), where=denominator > 0
    )
    return result


def normal_formation(prices: np.ndarray) -> pd.DataFrame:
    if prices.shape[1] != 51:
        raise ValueError("51_exact_closes_required")
    valid = np.isfinite(prices).all(axis=1) & (prices > 0).all(axis=1)
    daily = np.full((len(prices), 50), np.nan)
    daily[valid] = prices[valid, 1:] / prices[valid, :-1] - 1
    ranked = midrank_rows(daily, nonnegative=False)
    return pd.DataFrame(
        {
            "formation_return": daily[:, -1],
            "formation_history_valid": valid,
            "formation_return_percentile": ranked["own_history_percentile"],
            "normal_formation_return": valid & ranked["own_history_percentile"].between(0.30, 0.70),
        }
    )


def market_denominators(
    amount: np.ndarray, reference_indices: np.ndarray
) -> tuple[np.ndarray, np.ndarray, float, np.ndarray]:
    valid = np.isfinite(amount) & (amount >= 0)
    participants = valid.sum(axis=0)
    totals = np.where(valid, amount, 0).sum(axis=0)
    median = float(np.median(participants[reference_indices]))
    usable = (participants >= 0.8 * median) & np.isfinite(totals) & (totals > 0)
    return totals, participants, median, usable


def load_matrix(
    root: Path, resolution: pd.DataFrame, dates: pd.DatetimeIndex, *, price: bool = False
) -> np.ndarray:
    column = "canonical_price_path" if price else "canonical_amount_path"
    date_col, value_col = ("trade_date", "qfq_close") if price else ("date", "amount")
    allowed = (
        root / ("data/cache/h5a_broader_a_qfq_v1" if price else "data/cache/price")
    ).resolve()
    matrix = np.full((len(resolution), len(dates)), np.nan)
    for i, row in enumerate(resolution.itertuples(index=False)):
        text = getattr(row, column)
        if pd.isna(text):
            continue
        path = (root / str(text)).resolve()
        if path.parent != allowed or path.name != f"{row.stock_code}.csv":
            raise ValueError(f"noncanonical_input_path={row.stock_code}")
        frame = pd.read_csv(path, usecols=[date_col, value_col])
        frame[date_col] = pd.to_datetime(frame[date_col], errors="raise")
        if frame[date_col].duplicated().any():
            raise ValueError(f"duplicate_date={row.stock_code}")
        series = pd.to_numeric(frame.set_index(date_col)[value_col], errors="coerce")
        matrix[i] = series.reindex(dates).to_numpy(float)
        if (i + 1) % 500 == 0:
            print(f"{'qfq' if price else 'amount'} files scanned={i + 1}", flush=True)
    return matrix


def build_signals(
    states: pd.DataFrame,
    codes: list[str],
    amount: np.ndarray,
    dates: pd.DatetimeIndex,
    calendar: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, dict]:
    lookup = {code: i for i, code in enumerate(codes)}
    windows = {
        int(p): exact_window(calendar, g["signal_as_of_date"].iloc[0])
        for p, g in states.groupby("period_index")
    }
    primary_dates = pd.DatetimeIndex(sorted(set().union(*(set(windows[p]) for p in PERIODS))))
    totals, participants, median, usable = market_denominators(
        amount, dates.get_indexer(primary_dates)
    )
    outputs = []
    for period, group in states.groupby("period_index", sort=True):
        rows = [lookup[code] for code in group["stock_code"]]
        cols = dates.get_indexer(windows[period])
        values = amount[np.ix_(rows, cols)]
        result = midrank_rows(values)
        result["trend_spearman"] = trend_rows(values)
        normalized = np.full_like(values, np.nan)
        np.divide(values, totals[cols], out=normalized, where=usable[cols])
        secondary = midrank_rows(normalized)
        result["market_normalized_valid"] = secondary["valid_50d"]
        result["market_normalized_midrank"] = secondary["midrank"]
        result["market_normalized_shock_state"] = secondary["shock_state"]
        result["market_denominator_bad_days"] = int((~usable[cols]).sum())
        result["market_window_min_participants"] = int(participants[cols].min())
        result["market_reference_median_participants"] = median
        result["invalid_reason"] = np.where(
            result["valid_50d"], "", "missing_nonfinite_or_negative_amount_in_exact_window"
        )
        result["primary_period"] = period in PERIODS
        result["period_role"] = "primary" if period in PERIODS else "early_history_diagnostic_only"
        result["period_exclusion_reason"] = (
            "" if period in PERIODS else "insufficient_pre_signal_50d_activity_history"
        )
        outputs.append(pd.concat([group.reset_index(drop=True), result], axis=1))
    signals = pd.concat(outputs, ignore_index=True)
    reference = dates.get_indexer(primary_dates)
    details = {
        "market_reference_median_participants": median,
        "market_reference_min_participants": int(participants[reference].min()),
        "market_reference_bad_dates": int((~usable[reference]).sum()),
        "unique_amount_zero_stock_dates": int((amount[:, reference] == 0).sum()),
        "market_reference_start": str(primary_dates.min().date()),
        "market_reference_end": str(primary_dates.max().date()),
    }
    return signals, details


def signal_qa(signals: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if signals.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("duplicate_signal_membership")
    primary = signals.loc[signals["primary_period"]]
    if set(primary["period_index"]) != set(PERIODS):
        raise ValueError("primary_period_keys_mismatch")
    coverage = signals.groupby("period_index").agg(
        eligible_count=("stock_code", "size"), valid_50d_count=("valid_50d", "sum")
    )
    coverage["coverage"] = coverage["valid_50d_count"] / coverage["eligible_count"]
    counts = pd.crosstab(
        signals.loc[signals["valid_50d"], "period_index"],
        signals.loc[signals["valid_50d"], "shock_state"],
    )
    coverage = coverage.join(counts.reindex(columns=SHOCKS, fill_value=0)).fillna(0)
    keys = pd.MultiIndex.from_product(
        [PERIODS, RETURNS, SHOCKS], names=["period_index", "RETURN_STATE", "shock_state"]
    )
    cells = (
        primary.loc[primary["valid_50d"]]
        .groupby(["period_index", "RETURN_STATE", "shock_state"])
        .size()
        .reindex(keys, fill_value=0)
        .rename("count")
        .reset_index()
    )
    return coverage, cells


def outcome_dates(
    calendar: pd.DatetimeIndex, signal: pd.Timestamp
) -> tuple[pd.Timestamp, dict[int, pd.Timestamp]]:
    start = calendar.get_loc(signal) + 1
    if start + max(HORIZONS) >= len(calendar):
        raise ValueError("endpoint_calendar_unavailable")
    return calendar[start], {h: calendar[start + h] for h in HORIZONS}


def add_price_observations(
    signals: pd.DataFrame,
    codes: list[str],
    prices: np.ndarray,
    dates: pd.DatetimeIndex,
    calendar: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    lookup = {code: i for i, code in enumerate(codes)}
    updated, outcomes = [], []
    for period, group in signals.groupby("period_index", sort=True):
        group = group.reset_index(drop=True).copy()
        signal = group["signal_as_of_date"].iloc[0]
        rows = [lookup[code] for code in group["stock_code"]]
        cols = dates.get_indexer(exact_window(calendar, signal, 51))
        normal = normal_formation(prices[np.ix_(rows, cols)])
        updated.append(pd.concat([group, normal], axis=1))
        if period not in PERIODS:
            continue
        start, ends = outcome_dates(calendar, signal)
        first = prices[rows, dates.get_loc(start)]
        for horizon, endpoint in ends.items():
            last = prices[rows, dates.get_loc(endpoint)]
            valid = np.isfinite(first) & (first > 0) & np.isfinite(last) & (last > 0)
            returns = np.full(len(rows), np.nan)
            returns[valid] = last[valid] / first[valid] - 1
            outcomes.append(
                group[["period_index", "stock_code"]].assign(
                    horizon=horizon,
                    return_start_date=start,
                    endpoint_date=endpoint,
                    future_return=returns,
                )
            )
    return pd.concat(updated, ignore_index=True), pd.concat(outcomes, ignore_index=True)


def build_cells(signals: pd.DataFrame, outcomes: pd.DataFrame, variant: str) -> pd.DataFrame:
    states = signals.loc[signals["primary_period"] & signals["valid_50d"]].copy()
    if variant == "normal_formation_return":
        states = states.loc[states["normal_formation_return"]]
    elif variant == "market_normalized":
        states = states.loc[states["market_normalized_valid"]].copy()
        states["shock_state"] = states["market_normalized_shock_state"]
    elif variant != "primary":
        raise ValueError("unknown_variant")
    keys = ["period_index", "RETURN_STATE", "shock_state"]
    membership = states.groupby(keys).size().rename("signal_membership_count")
    combined = states[[*keys, "stock_code"]].merge(
        outcomes, on=["period_index", "stock_code"], validate="one_to_many"
    )
    grouped = combined.groupby([*keys, "horizon"])["future_return"].agg(
        valid_outcome_count="count",
        mean_future_return="mean",
        median_future_return="median",
        q25=lambda x: x.quantile(0.25),
        q75=lambda x: x.quantile(0.75),
    )
    grid = pd.MultiIndex.from_product(
        [PERIODS, RETURNS, SHOCKS, HORIZONS], names=[*keys, "horizon"]
    )
    result = (
        grouped.reindex(grid)
        .reset_index()
        .merge(membership.reset_index(), on=keys, how="left", validate="many_to_one")
    )
    for column in ("signal_membership_count", "valid_outcome_count"):
        result[column] = result[column].fillna(0).astype(int)
    result["outcome_coverage"] = result["valid_outcome_count"] / result[
        "signal_membership_count"
    ].replace(0, np.nan)
    result["iqr_future_return"] = result["q75"] - result["q25"]
    result["cell_valid"] = result["signal_membership_count"].ge(25) & result["outcome_coverage"].ge(
        0.8
    )
    result["variant"] = variant
    timing = outcomes[
        ["period_index", "horizon", "return_start_date", "endpoint_date"]
    ].drop_duplicates()
    return result.merge(timing, on=["period_index", "horizon"], validate="many_to_one")


def summarize(values: pd.Series) -> dict:
    data = values.dropna()
    lower, upper = moving_block_interval(data, block_length=3, repetitions=10000, seed=20260721)
    return {
        "valid_periods": len(data),
        "mean_contrast": data.mean(),
        "median_contrast": data.median(),
        "positive_share": float(data.gt(0).mean()) if len(data) else math.nan,
        "direction_consistency": direction_consistency(data),
        "loo_sign_consistency": loo_sign_consistency(data),
        "bootstrap_lower_90": lower,
        "bootstrap_upper_90": upper,
        "missing_periods": "|".join(str(p) for p in values.index[values.isna()]),
        "block_length": 3,
        "bootstrap_repetitions": 10000,
        "bootstrap_seed": 20260721,
    }


def build_contrasts(cells: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for variant, frame in cells.groupby("variant", sort=False):
        for horizon in HORIZONS:
            series = {}
            for state in RETURNS:
                part = frame.loc[
                    frame["RETURN_STATE"].eq(state) & frame["horizon"].eq(horizon)
                ].copy()
                part["usable_mean"] = part["mean_future_return"].where(part["cell_valid"])
                pivot = part.pivot(
                    index="period_index", columns="shock_state", values="usable_mean"
                ).reindex(PERIODS)
                series[state] = pivot["HIGH_SHOCK"] - pivot["LOW_SHOCK"]
            series["LOSER_MINUS_WINNER"] = series["LOW_RETURN"] - series["HIGH_RETURN"]
            for state, values in series.items():
                base = {"variant": variant, "RETURN_STATE": state, "horizon": horizon}
                rows.append({**base, "row_type": "summary", **summarize(values)})
                rows.extend(
                    {
                        **base,
                        "row_type": "period",
                        "period_index": p,
                        "period_contrast": v,
                        "contrast_valid": np.isfinite(v),
                    }
                    for p, v in values.items()
                )
    return pd.DataFrame(rows)


def table(frame: pd.DataFrame) -> str:
    display = frame.copy()
    for column in display.select_dtypes(include=["object", "string"]):
        display[column] = display[column].map(
            lambda value: value.replace("|", ", ") if isinstance(value, str) else value
        )
    if "missing_periods" in display:
        display["missing_periods"] = display["missing_periods"].fillna("")
    return display.to_markdown(index=False, floatfmt=".6f")


def qa_report(coverage: pd.DataFrame, cells: pd.DataFrame, details: dict) -> str:
    primary = coverage.loc[list(PERIODS)]
    sizes = (
        cells.groupby(["RETURN_STATE", "shock_state"])["count"]
        .agg(median="median", minimum="min", p10=lambda x: x.quantile(0.1))
        .reset_index()
    )
    return (
        "## Signal-time QA (saved before outcome loading)\n\n"
        f"Primary periods=54; median signal coverage={primary.coverage.median():.8%}; minimum={primary.coverage.min():.8%}. "
        f"3×3 cell count median={cells['count'].median():.1f}, minimum={cells['count'].min()}, p10={cells['count'].quantile(0.1):.1f}.\n\n"
        + table(coverage.reset_index())
        + "\n\n"
        + table(sizes)
        + "\n\n"
        + "\n".join(f"- {key}={value}" for key, value in details.items())
        + "\n"
    )


def write_report(
    path: Path, signals: pd.DataFrame, cells: pd.DataFrame, contrasts: pd.DataFrame, qa_text: str
) -> None:
    summary = contrasts.loc[contrasts.row_type.eq("summary")]
    primary = summary.loc[summary.variant.eq("primary")]
    columns = [
        "RETURN_STATE",
        "horizon",
        "valid_periods",
        "mean_contrast",
        "median_contrast",
        "positive_share",
        "direction_consistency",
        "loo_sign_consistency",
        "bootstrap_lower_90",
        "bootstrap_upper_90",
        "missing_periods",
    ]
    valid_signals = signals.loc[signals.primary_period & signals.valid_50d]
    trend = (
        valid_signals.loc[valid_signals.shock_state.isin(["HIGH_SHOCK", "LOW_SHOCK"])]
        .groupby("shock_state")
        .agg(
            observations=("stock_code", "size"),
            undefined_trend=("trend_spearman", lambda x: x.isna().sum()),
            strong_trend_share=("trend_spearman", lambda x: x.abs().ge(0.5).mean()),
            median_trend=("trend_spearman", "median"),
        )
        .reset_index()
    )
    p20 = primary.loc[primary.horizon.eq(20)]
    text = "# H6 — Daily Amount Abnormal Activity Diagnostic\n\n## Technical summary\n\n"
    text += "以下为 historical_seen、period-level 等权的 raw HIGH_SHOCK−LOW_SHOCK 差异，20D是Primary；数字为小数收益（0.01=1个百分点），不是可执行策略收益。Runner不自动给出supported/rejected或机制标签；human_interpretation_required=true。\n\n"
    text += table(p20[columns]) + "\n\n"
    text += "## Scope and definitions\n\n54期固定为3–56；1/2只作早期信号诊断。50个精确市场日amount使用date-neutral midrank，零值保留。RETURN_STATE直接继承H5，未读取VT值。未来收益从信号后下一市场日close起算，端点在起点后5/10/20市场日。Primary及两个robustness均使用cell arithmetic mean；median/IQR只作描述。成员>=25且outcome coverage>=80%的两侧cell才形成contrast。\n\n"
    text += qa_text + "\n## Primary paths and stability\n\n"
    text += table(primary[columns]) + "\n\n"
    text += "LOW/MID/HIGH均是raw return差值，LOW_RETURN没有翻转收益符号。LOSER_MINUS_WINNER是同一期G_LOW−G_HIGH，只在两个G同时有效时计算。5D/10D是嵌套累计路径，不是独立Primary检验。\n\n"
    path_means = (
        cells.loc[cells.variant.eq("primary") & cells.cell_valid]
        .groupby(["RETURN_STATE", "shock_state", "horizon"])
        .agg(
            valid_periods=("mean_future_return", "count"),
            period_equal_mean=("mean_future_return", "mean"),
            period_equal_median=("mean_future_return", "median"),
        )
        .reset_index()
    )
    text += table(path_means) + "\n\n## Fixed robustness comparisons\n\n"
    for variant in ("normal_formation_return", "market_normalized"):
        subset = summary.loc[summary.variant.eq(variant)]
        comparison = subset.merge(
            primary[["RETURN_STATE", "horizon", "mean_contrast"]].rename(
                columns={"mean_contrast": "primary_mean"}
            ),
            on=["RETURN_STATE", "horizon"],
            validate="one_to_one",
        )
        comparison["same_direction"] = (
            np.sign(comparison.mean_contrast).eq(np.sign(comparison.primary_mean))
            & comparison.mean_contrast.notna()
        )
        comparison["magnitude_ratio"] = comparison.mean_contrast / comparison.primary_mean.replace(
            0, np.nan
        )
        core = comparison.loc[comparison.RETURN_STATE.isin(RETURNS)]
        text += f"### {variant}\n\n在9个state×horizon对比中，同方向{int(core.same_direction.sum())}/9；这是描述，不是保留模式自动分类。\n\n"
        text += table(comparison[[*columns, "same_direction", "magnitude_ratio"]]) + "\n\n"
    text += "Middle40使用formation日50日收益分布的[30%,70%]，需要51个完整价格；小cell与无效期不补足。Market-normalized分母是当前broader-A所有可用amount的日合计，仅使用参与数>=参考中位数80%的日期。两者不改变Primary成员或定义，也不因方向变化调参。\n\n"
    quality = (
        cells.groupby("variant")
        .agg(
            cell_horizons=("cell_valid", "size"),
            valid_cell_horizons=("cell_valid", "sum"),
            minimum_members=("signal_membership_count", "min"),
            minimum_outcome_coverage=("outcome_coverage", "min"),
            missing_stock_outcomes=("valid_outcome_count", "sum"),
        )
        .reset_index()
    )
    quality = quality.drop(columns="missing_stock_outcomes")
    text += table(quality) + "\n\n"
    text += f"Primary valid stock-period windows with zero amount={int(valid_signals.amount_zero_flag.sum())}; summed zero-days across overlapping windows={int(valid_signals.amount_zero_days.sum())}. Unique stock-date zeros are separately reported in QA; these are different denominators.\n\n"
    text += "## Local trend diagnostic\n\n" + table(trend) + "\n\n"
    text += "以上比例按全部相应shock observations计算，undefined列单独披露。不能把持续趋势与独立冲击严格分离；本轮没有去趋势、剔除趋势股票或做第三套搜索。\n\n"
    text += "## Statistical and execution limitations\n\nCircular moving-block bootstrap: block=3, repetitions=10000, seed=20260721, 90% interval。有效period按时间排序；缺失期列出，压缩有效序列可能改变跨缺口邻接。区间仅为描述性不确定性，不控制多重检验、不代表Alpha/OOS显著性。Primary与robustness的有效样本不同，幅度比不具因果含义。\n\n"
    text += "当前股票池非point-in-time，存在幸存者与构成偏差；QFQ为当前vintage。amount单位沿用既有CNY推定而非源认证。amount不是share volume，不能称D04复制。没有可靠历史涨跌停/ST/停牌/次日可交易性；不能保证这些close-to-close收益可执行。H5横截面活动水平与H6个股自身异常活动是不同问题，不据绝对效应大小选更好因子。\n\n"
    text += "## Human interpretation and stop\n\n人工应结合三个RETURN_STATE、20D区间、5/10D路径及两项robustness判断关联广泛、状态集中、弱/不稳定或存在alternative explanation。Runner不自动决定这四种描述。完成后停止，不自动进入新研究。\n\n"
    text += "来源：本目录预注册与四份结果CSV；signal-time H5面板、broader-A source resolution、canonical amount/QFQ及CSI300 calendar。表格用于精确核对，未额外创建图表或报告平台。\n\n```text\n"
    flags = {
        **IDENTITY,
        "primary_measurement": "DAILY_AMOUNT_OWN_HISTORY_RANK",
        "share_volume_used": False,
        "VT_used_as_primary": False,
        "future_information_used_in_signal": False,
        "period_1_2_primary": False,
        "same_day_close_entry_assumed": False,
        "execution_claim_made": False,
        "network_download_performed": False,
        "MCTS_run": False,
        "Phase_B_run": False,
        "prospective_data_accessed": False,
        "final_test_accessed": False,
        "historical_future_outcome_accessed": True,
    }
    text += (
        "\n".join(
            f"{key}={str(value).lower() if isinstance(value, bool) else value}"
            for key, value in flags.items()
        )
        + "\n```\n"
    )
    path.write_text(text, encoding="utf-8")


def run(root: Path) -> None:
    output = root / OUT
    if not (output / "h6_daily_amount_preregistration.md").exists():
        raise ValueError("preregistration_required_before_outcomes")
    states = _load_states(root)
    calendar = _market_calendar(root)
    resolution = pd.read_csv(
        root / "reports/hypothesis_5a_broader_a/source_resolution_report.csv",
        dtype={"stock_code": str},
    )
    if len(resolution) != 5195 or resolution.stock_code.duplicated().any():
        raise ValueError("broader_a_universe_mismatch")
    codes = resolution.stock_code.tolist()
    if not set(states.stock_code).issubset(codes):
        raise ValueError("signal_member_outside_universe")
    dates = pd.DatetimeIndex(
        sorted(
            set().union(
                *(set(exact_window(calendar, t)) for t in states.signal_as_of_date.unique())
            )
        )
    )
    amount = load_matrix(root, resolution, dates)
    signals, details = build_signals(states, codes, amount, dates, calendar)
    del amount
    coverage, signal_cells = signal_qa(signals)
    qa_text = qa_report(coverage, signal_cells, details)
    write_csv(signals, output / "h6_signal_states.csv")
    (output / "h6_diagnostic_report.md").write_text(
        "# H6 signal-only QA\n\nfuture_outcome_analysis_started=false\n\n" + qa_text,
        encoding="utf-8",
    )
    if coverage.loc[list(PERIODS), "coverage"].lt(0.8).any():
        raise ValueError("primary_signal_coverage_below_80pct; outcomes_not_read")
    print("Signal QA saved and passed; now loading approved historical QFQ outcomes", flush=True)
    needed = set()
    for period, group in signals.groupby("period_index"):
        signal = group.signal_as_of_date.iloc[0]
        needed.update(exact_window(calendar, signal, 51))
        if period in PERIODS:
            start, endpoints = outcome_dates(calendar, signal)
            needed.add(start)
            needed.update(endpoints.values())
    price_dates = pd.DatetimeIndex(sorted(needed))
    prices = load_matrix(root, resolution, price_dates, price=True)
    signals, outcomes = add_price_observations(signals, codes, prices, price_dates, calendar)
    del prices
    write_csv(signals, output / "h6_signal_states.csv")
    cells = pd.concat(
        [
            build_cells(signals, outcomes, variant)
            for variant in ("primary", "normal_formation_return", "market_normalized")
        ],
        ignore_index=True,
    )
    contrasts = build_contrasts(cells)
    write_csv(cells, output / "h6_period_state_returns.csv")
    write_csv(contrasts.loc[contrasts.variant.eq("primary")], output / "h6_primary_contrasts.csv")
    write_csv(contrasts.loc[~contrasts.variant.eq("primary")], output / "h6_robustness_summary.csv")
    write_report(output / "h6_diagnostic_report.md", signals, cells, contrasts, qa_text)
    print(
        contrasts.loc[
            contrasts.row_type.eq("summary") & contrasts.horizon.eq(20),
            [
                "variant",
                "RETURN_STATE",
                "valid_periods",
                "mean_contrast",
                "bootstrap_lower_90",
                "bootstrap_upper_90",
            ],
        ].to_string(index=False),
        flush=True,
    )
    print("H6 complete; human_interpretation_required=true", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    run(parser.parse_args().project_root.resolve())
