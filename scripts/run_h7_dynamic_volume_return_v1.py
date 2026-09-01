"""Run the preregistered, offline H7 dynamic volume-return diagnostic."""

# ruff: noqa: E501 -- explicit research-contract fields and report prose are intentional.

from __future__ import annotations

import argparse
import math
import time
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import spearmanr

ANALYSIS_CUTOFF = pd.Timestamp("2026-05-11")
PRIMARY_MIN_ROWS = 750
LONG_HISTORY_MIN_ROWS = 1000
BASELINE_LENGTH = 200
HAC_MAXLAGS = 5
CONDITION_NUMBER_LIMIT = 1e12
UNIVERSE_SIZE = 5195

TURNOVER_PANEL = Path("data/processed/h7_turnover_daily_panel_v1.csv")
UNIVERSE_FILE = Path("data/processed/h5a_broader_a_universe_v1.csv")
QFQ_DIR = Path("data/cache/h5a_broader_a_qfq_v1")
RAW_PRICE_DIR = Path("data/cache/price")
CALENDAR_FILE = Path("data/processed/hybrid_benchmark_panel_v1_5.csv")
OUTPUT_DIR = Path("reports/hypothesis_7")
PREREGISTRATION = OUTPUT_DIR / "h7_dynamic_volume_return_preregistration_v1.md"


def code6(value: object) -> str:
    digits = "".join(char for char in str(value) if char.isdigit())
    return digits[-6:].zfill(6)


def board(code: str) -> str:
    if code.startswith("688"):
        return "STAR"
    if code.startswith("300"):
        return "CHINEXT"
    if code.startswith(("600", "601", "603", "605")):
        return "SH_MAIN"
    return "SZ_MAIN"


def previous_active_log_baseline(turnover: pd.Series, active: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return direct-log turnover and a strictly prior 200-active-observation mean."""
    numeric = pd.to_numeric(turnover, errors="coerce")
    valid = active.eq(True) & numeric.gt(0) & np.isfinite(numeric)
    logs = pd.Series(np.nan, index=turnover.index, dtype=float)
    logs.loc[valid] = np.log(numeric.loc[valid])
    active_logs = logs.loc[valid]
    baseline = active_logs.shift(1).rolling(BASELINE_LENGTH, min_periods=BASELINE_LENGTH).mean()
    expanded = pd.Series(np.nan, index=turnover.index, dtype=float)
    expanded.loc[baseline.index] = baseline
    return logs, expanded


def exact_returns(prices: pd.Series, horizons: tuple[int, ...] = (1, 2, 5)) -> pd.DataFrame:
    """Use exact adjacent market-calendar rows; missing prices stay missing."""
    clean = pd.to_numeric(prices, errors="coerce").where(lambda value: value.gt(0) & np.isfinite(value))
    result = pd.DataFrame(index=clean.index)
    result["current_return"] = clean / clean.shift(1) - 1.0
    for horizon in horizons:
        result[f"future_{horizon}d_return"] = clean.shift(-horizon) / clean - 1.0
    return result


def load_calendar(root: Path) -> pd.DatetimeIndex:
    frame = pd.read_csv(root / CALENDAR_FILE, dtype={"benchmark_code": str})
    codes = frame.benchmark_code.map(code6)
    dates = pd.to_datetime(frame.loc[codes.eq("000300"), "trade_date"], errors="coerce")
    calendar = pd.DatetimeIndex(dates.dropna().drop_duplicates().sort_values())
    if ANALYSIS_CUTOFF not in calendar:
        raise ValueError("analysis_cutoff_missing_from_csi300_calendar")
    cutoff_position = calendar.get_loc(ANALYSIS_CUTOFF)
    if cutoff_position + 5 >= len(calendar):
        raise ValueError("calendar_missing_5d_endpoint_after_cutoff")
    return calendar


def load_universe(root: Path) -> list[str]:
    frame = pd.read_csv(root / UNIVERSE_FILE, dtype={"stock_code": str})
    included = frame.loc[frame.universe_status.eq("INCLUDED"), "stock_code"].map(code6)
    universe = sorted(included.drop_duplicates())
    if len(universe) != UNIVERSE_SIZE:
        raise ValueError(f"expected_{UNIVERSE_SIZE}_stocks_got={len(universe)}")
    return universe


def iter_turnover_stocks(path: Path, chunksize: int = 250_000) -> Iterator[tuple[str, pd.DataFrame]]:
    columns = [
        "stock_code", "trade_date", "trading_status", "is_st",
        "total_share_turnover", "baostock_circulating_turnover",
    ]
    carry = pd.DataFrame(columns=columns)
    prior_code = ""
    for chunk in pd.read_csv(path, usecols=columns, dtype={"stock_code": str}, chunksize=chunksize):
        chunk["stock_code"] = chunk.stock_code.map(code6)
        combined = chunk.reset_index(drop=True) if carry.empty else pd.concat([carry, chunk], ignore_index=True)
        if combined.empty:
            continue
        if prior_code and combined.stock_code.iloc[0] < prior_code:
            raise ValueError("turnover_panel_not_sorted_by_stock_code")
        last_code = combined.stock_code.iloc[-1]
        complete = combined.loc[combined.stock_code.ne(last_code)]
        for code, group in complete.groupby("stock_code", sort=False):
            if prior_code and code < prior_code:
                raise ValueError("turnover_panel_not_sorted_by_stock_code")
            prior_code = code
            yield code, group.reset_index(drop=True)
        carry = combined.loc[combined.stock_code.eq(last_code)].copy()
    if not carry.empty:
        code = str(carry.stock_code.iloc[0])
        if prior_code and code < prior_code:
            raise ValueError("turnover_panel_not_sorted_by_stock_code")
        yield code, carry.reset_index(drop=True)


def load_qfq(root: Path, code: str, calendar: pd.DatetimeIndex) -> pd.Series:
    path = root / QFQ_DIR / f"{code}.csv"
    result = pd.Series(np.nan, index=calendar, dtype=float)
    if not path.exists():
        return result
    frame = pd.read_csv(path, usecols=["trade_date", "qfq_close"])
    frame["trade_date"] = pd.to_datetime(frame.trade_date, errors="coerce")
    frame["qfq_close"] = pd.to_numeric(frame.qfq_close, errors="coerce")
    if frame.trade_date.duplicated().any():
        raise ValueError(f"duplicate_qfq_date={code}")
    valid = frame.trade_date.isin(calendar) & frame.qfq_close.gt(0) & np.isfinite(frame.qfq_close)
    values = frame.loc[valid].set_index("trade_date").qfq_close
    result.loc[values.index] = values
    return result


def prepare_stock_rows(group: pd.DataFrame, prices: pd.Series, calendar: pd.DatetimeIndex) -> pd.DataFrame:
    frame = pd.DataFrame(index=calendar)
    source = group.copy()
    source["trade_date"] = pd.to_datetime(source.trade_date, errors="coerce")
    if source.trade_date.duplicated().any():
        raise ValueError(f"duplicate_turnover_date={source.stock_code.iloc[0]}")
    source = source.set_index("trade_date")
    for column in ("trading_status", "is_st", "total_share_turnover", "baostock_circulating_turnover"):
        frame[column] = pd.to_numeric(source[column], errors="coerce").reindex(calendar)
    active = frame.trading_status.eq(1)
    primary_log, primary_baseline = previous_active_log_baseline(frame.total_share_turnover, active)
    secondary_log, secondary_baseline = previous_active_log_baseline(frame.baostock_circulating_turnover, active)
    frame["primary_v"] = primary_log - primary_baseline
    frame["secondary_v"] = secondary_log - secondary_baseline
    frame = frame.join(exact_returns(prices))
    frame["formation_base"] = (
        frame.index.to_series().le(ANALYSIS_CUTOFF).to_numpy()
        & active.to_numpy()
        & frame.is_st.eq(0).to_numpy()
        & np.isfinite(frame.current_return.to_numpy())
    )
    for horizon in (1, 2, 5):
        future = frame[f"future_{horizon}d_return"]
        frame[f"primary_valid_{horizon}d"] = frame.formation_base & np.isfinite(frame.primary_v) & np.isfinite(future)
    frame["secondary_matched_valid_1d"] = (
        frame.primary_valid_1d & np.isfinite(frame.secondary_v) & np.isfinite(frame.future_1d_return)
    )
    return frame


def fit_stock(rows: pd.DataFrame, v_column: str, future_column: str) -> dict[str, object]:
    data = rows[["current_return", v_column, future_column]].copy()
    data["interaction"] = data[v_column] * data.current_return
    array = data[["current_return", "interaction", future_column]].to_numpy(dtype=float)
    if len(data) == 0 or not np.isfinite(array).all():
        return {"evaluation_status": "REGRESSION_NUMERIC_FAILURE", "failure_reason": "NONFINITE_X_OR_Y"}
    if np.ptp(data.current_return.to_numpy()) == 0:
        return {"evaluation_status": "REGRESSION_NUMERIC_FAILURE", "failure_reason": "CONSTANT_R"}
    if np.ptp(data.interaction.to_numpy()) == 0:
        return {"evaluation_status": "REGRESSION_NUMERIC_FAILURE", "failure_reason": "CONSTANT_INTERACTION"}
    x = np.column_stack([np.ones(len(data)), data.current_return, data.interaction])
    rank_value = int(np.linalg.matrix_rank(x))
    condition_number = float(np.linalg.cond(x))
    if rank_value < 3 or not math.isfinite(condition_number) or condition_number > CONDITION_NUMBER_LIMIT:
        return {
            "evaluation_status": "REGRESSION_NUMERIC_FAILURE",
            "failure_reason": "SINGULAR_OR_ILL_CONDITIONED",
            "matrix_rank": rank_value,
            "condition_number": condition_number,
        }
    fitted = sm.OLS(data[future_column].to_numpy(), x).fit(
        cov_type="HAC", cov_kwds={"maxlags": HAC_MAXLAGS}, use_t=False,
    )
    v_values = data[v_column].to_numpy()
    v10, v50, v90 = np.quantile(v_values, [0.1, 0.5, 0.9])
    return {
        "evaluation_status": "SUCCESS", "failure_reason": "", "nobs": int(fitted.nobs),
        "C0": float(fitted.params[0]), "C1": float(fitted.params[1]), "C2": float(fitted.params[2]),
        "se_C0_hac5": float(fitted.bse[0]), "se_C1_hac5": float(fitted.bse[1]), "se_C2_hac5": float(fitted.bse[2]),
        "t_C0_hac5": float(fitted.tvalues[0]), "t_C1_hac5": float(fitted.tvalues[1]), "t_C2_hac5": float(fitted.tvalues[2]),
        "matrix_rank": rank_value, "condition_number": condition_number,
        "V_p10": float(v10), "V_p50": float(v50), "V_p90": float(v90),
        "effective_slope_p10": float(fitted.params[1] + fitted.params[2] * v10),
        "effective_slope_p50": float(fitted.params[1] + fitted.params[2] * v50),
        "effective_slope_p90": float(fitted.params[1] + fitted.params[2] * v90),
    }


def historical_size(root: Path, code: str, valid_dates: pd.DatetimeIndex) -> tuple[float, int]:
    path = root / RAW_PRICE_DIR / f"{code}.csv"
    if not path.exists():
        return np.nan, 0
    frame = pd.read_csv(path, usecols=lambda name: name in {"date", "trade_date", "total_market_cap"})
    date_column = "trade_date" if "trade_date" in frame else "date"
    if date_column not in frame or "total_market_cap" not in frame:
        return np.nan, 0
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    cap = pd.to_numeric(frame.total_market_cap, errors="coerce")
    valid = dates.isin(valid_dates) & dates.le(ANALYSIS_CUTOFF) & cap.gt(0) & np.isfinite(cap)
    logs = np.log(cap.loc[valid].to_numpy())
    return (float(np.median(logs)), int(len(logs))) if len(logs) else (np.nan, 0)


def distribution(values: pd.Series) -> dict[str, float | int]:
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if clean.empty:
        return {"count": 0}
    result: dict[str, float | int] = {
        "count": int(len(clean)), "mean": float(clean.mean()), "median": float(clean.median()),
        "std": float(clean.std(ddof=1)), "positive_share": float(clean.gt(0).mean()),
        "negative_share": float(clean.lt(0).mean()),
    }
    for quantile in (0.01, 0.05, 0.10, 0.25, 0.75, 0.90, 0.95, 0.99):
        result[f"p{int(quantile * 100)}"] = float(clean.quantile(quantile))
    return result


def slope_summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for column in ("effective_slope_p10", "effective_slope_p50", "effective_slope_p90"):
        values = pd.to_numeric(frame[column], errors="coerce").dropna()
        rows.append({
            "V_point": column.removeprefix("effective_slope_"), "n": len(values), "mean": values.mean(),
            "median": values.median(), "p10": values.quantile(0.1), "p90": values.quantile(0.9),
            "positive_share": values.gt(0).mean(),
        })
    return pd.DataFrame(rows)


def paired_metrics(left: pd.Series, right: pd.Series) -> dict[str, float | int]:
    paired = pd.concat([left.rename("left"), right.rename("right")], axis=1).dropna()
    if paired.empty:
        return {"n": 0, "correlation": np.nan, "sign_agreement": np.nan, "mean_difference": np.nan, "median_difference": np.nan}
    correlation = paired.corr(method="pearson").iloc[0, 1] if len(paired) > 1 else np.nan
    difference = paired.right - paired.left
    return {
        "n": int(len(paired)), "correlation": float(correlation),
        "sign_agreement": float(np.sign(paired.left).eq(np.sign(paired.right)).mean()),
        "mean_difference": float(difference.mean()), "median_difference": float(difference.median()),
    }


def markdown_table(frame: pd.DataFrame, digits: int = 6) -> str:
    if frame.empty:
        return "_No valid observations._"
    display = frame.copy()
    for column in display.select_dtypes(include=[np.number]).columns:
        display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.{digits}g}")
    headers = [str(column) for column in display.columns]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines.extend("| " + " | ".join(map(str, row)) + " |" for row in display.itertuples(index=False, name=None))
    return "\n".join(lines)


def size_diagnostic(primary: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, float | int]]:
    sample = primary.loc[np.isfinite(primary.size_metric) & np.isfinite(primary.C2)].copy()
    if len(sample) < 4 or sample.size_metric.std(ddof=0) == 0:
        return pd.DataFrame(), {"N": int(len(sample)), "status": "INSUFFICIENT_HISTORICAL_SIZE_COVERAGE"}
    sample["standardized_size"] = (sample.size_metric - sample.size_metric.mean()) / sample.size_metric.std(ddof=0)
    x = sm.add_constant(sample.standardized_size.to_numpy())
    fit = sm.OLS(sample.C2.to_numpy(), x).fit(cov_type="HC3")
    ci90 = fit.conf_int(alpha=0.10)[1]
    ci95 = fit.conf_int(alpha=0.05)[1]
    rho = spearmanr(sample.C2, sample.size_metric).statistic
    sample["size_quartile"] = pd.qcut(
        sample.size_metric.rank(method="first"), 4, labels=["Q1_SMALL", "Q2", "Q3", "Q4_LARGE"],
    ).astype(str)
    rows = [{
        "section": "cross_sectional_regression", "group": "ALL", "N": len(sample),
        "C2_mean": sample.C2.mean(), "C2_median": sample.C2.median(), "C2_positive_share": sample.C2.gt(0).mean(),
        "b_size": fit.params[1], "HC3_SE": fit.bse[1], "CI90_low": ci90[0], "CI90_high": ci90[1],
        "CI95_low": ci95[0], "CI95_high": ci95[1], "R_squared": fit.rsquared, "spearman_C2_size": rho,
    }]
    for quartile, group in sample.groupby("size_quartile", observed=True):
        rows.append({
            "section": "size_quartile", "group": quartile, "N": len(group), "C2_mean": group.C2.mean(),
            "C2_median": group.C2.median(), "C2_positive_share": group.C2.gt(0).mean(),
        })
    summary = {
        "N": int(len(sample)), "b_size": float(fit.params[1]), "HC3_SE": float(fit.bse[1]),
        "CI90_low": float(ci90[0]), "CI90_high": float(ci90[1]), "CI95_low": float(ci95[0]),
        "CI95_high": float(ci95[1]), "R_squared": float(fit.rsquared), "spearman_C2_size": float(rho),
        "D05_consistent_direction": bool(fit.params[1] < 0), "status": "SUCCESS",
    }
    return pd.DataFrame(rows), summary


def render_report(
    primary: pd.DataFrame, long_history: pd.DataFrame, horizons: pd.DataFrame,
    secondary: pd.DataFrame, size_rows: pd.DataFrame, size_summary: dict[str, object],
    membership: pd.DataFrame, elapsed: float,
) -> str:
    primary_ok = primary.loc[primary.evaluation_status.eq("SUCCESS")]
    long_ok = long_history.loc[long_history.evaluation_status.eq("SUCCESS")]
    d_primary = distribution(primary_ok.C2)
    t_primary = distribution(primary_ok.t_C2_hac5)
    d_long = distribution(long_ok.C2)
    slopes_primary = slope_summary(primary_ok)
    slopes_long = slope_summary(long_ok)
    long_compare = paired_metrics(primary_ok.set_index("stock_code").C2, long_ok.set_index("stock_code").C2)
    horizon_summary_rows = []
    for horizon, group in horizons.loc[horizons.evaluation_status.eq("SUCCESS")].groupby("horizon"):
        item = {"horizon": horizon, **distribution(group.C2)}
        compared = paired_metrics(
            primary_ok.set_index("stock_code").C2,
            group.set_index("stock_code").C2,
        )
        item.update({"corr_with_1D": compared["correlation"], "sign_agreement_with_1D": compared["sign_agreement"]})
        horizon_summary_rows.append(item)
    horizon_summary = pd.DataFrame(horizon_summary_rows)
    secondary_ok = secondary.loc[secondary.evaluation_status.eq("SUCCESS")]
    secondary_compare = paired_metrics(secondary_ok.C2_primary_matched, secondary_ok.C2_secondary_matched)
    board_rows = []
    for role, frame in (("PRIMARY_750", primary_ok), ("LONG_HISTORY_1000", long_ok)):
        for board_name, group in frame.groupby("board"):
            board_rows.append({"sample": role, "board": board_name, "stocks": len(group), "share": len(group) / len(frame) if len(frame) else np.nan, "C2_mean": group.C2.mean(), "C2_median": group.C2.median(), "C2_positive_share": group.C2.gt(0).mean()})
    board_summary = pd.DataFrame(board_rows)
    failures = int(membership.regression_numeric_failure.eq(True).sum())
    lines = [
        "# Hypothesis 7 — Dynamic Volume–Return Relation Diagnostic v1",
        "",
        "## Status and identity",
        "",
        "This is a D05-inspired, historical-seen individual-stock mechanism diagnostic, not an exact replication, strategy test, Alpha claim, causal identification, or OOS result. `human_interpretation_required=true`.",
        "",
        "Interpretation order is fixed: Primary 750 1D; long-history 1,000 1D; 2D/5D; Secondary matched turnover; size heterogeneity. Later diagnostics do not replace Primary.",
        "",
        "## Frozen contract and realized sample",
        "",
        f"- Analysis cutoff: {ANALYSIS_CUTOFF.date()}.",
        "- Primary turnover: TOTAL_SHARE_TURNOVER; Secondary: BAOSTOCK_CIRCULATING_TURNOVER.",
        "- Baseline: last 200 strictly prior active observations; direct natural log; no epsilon.",
        "- Formation: active and non-ST; historical active ST observations remain eligible in the baseline.",
        f"- Primary 750 members: {int(membership.primary_750_member.sum())}/{UNIVERSE_SIZE} ({membership.primary_750_member.mean():.2%}).",
        f"- Long-history 1,000 members: {int(membership.long_history_1000_member.sum())}/{UNIVERSE_SIZE} ({membership.long_history_1000_member.mean():.2%}); nested in Primary: {bool((~membership.long_history_1000_member | membership.primary_750_member).all())}.",
        f"- Primary successful regressions: {len(primary_ok)}; numerical failures among eligible regressions: {failures}.",
        "",
        "## Primary 750: 1D C2 distribution",
        "",
        markdown_table(pd.DataFrame([d_primary])),
        "",
        "### HAC(5) t-statistic distribution (descriptive only)",
        "",
        markdown_table(pd.DataFrame([t_primary])),
        "",
        "No per-stock significance count is used because the individual regressions create a large multiple-testing problem.",
        "",
        "C2 above zero means higher relative turnover moves the current/future-return conditional slope in a more positive direction; it does not by itself mean momentum or identify private information.",
        "",
        "### Effective slopes",
        "",
        markdown_table(slopes_primary),
        "",
        "## Long-history 1,000 robustness",
        "",
        markdown_table(pd.DataFrame([d_long])),
        "",
        markdown_table(slopes_long),
        "",
        markdown_table(pd.DataFrame([long_compare])),
        "",
        "The 1,000-row subset prioritizes longer estimation history but has stronger listing-age/board selection. It is not an alternate Primary and is not more correct.",
        "",
        "## 2D/5D microstructure robustness",
        "",
        markdown_table(horizon_summary),
        "",
        "Attenuation at 2D/5D increases the relevance of a short-horizon microstructure explanation. Persistence only means the relation is not obviously confined to one-day mechanical noise; it does not rule microstructure out.",
        "",
        "## Secondary turnover exact-matched robustness",
        "",
        markdown_table(pd.DataFrame([{"stock_count": len(secondary_ok), **secondary_compare, "primary_matched_C2_mean": secondary_ok.C2_primary_matched.mean(), "secondary_matched_C2_mean": secondary_ok.C2_secondary_matched.mean()}])),
        "",
        "TOTAL_SHARE_TURNOVER and BAOSTOCK_CIRCULATING_TURNOVER have different denominators. These estimates use exact matched rows so that measurement and sample changes are not conflated.",
        "",
        "## Size heterogeneity",
        "",
        markdown_table(size_rows),
        "",
        f"Size diagnostic status: `{size_summary.get('status')}`. Historical size is measured only on valid Primary dates at or before the cutoff. Missing size never removes a stock from Primary. A negative b_size is only directionally consistent with D05 size heterogeneity; size is not a pure information-asymmetry measure.",
        "",
        "C2_hat is a generated first-stage dependent variable. HC3 does not fully account for first-stage estimation error or cross-stock dependence.",
        "",
        "## Board composition",
        "",
        markdown_table(board_summary),
        "",
        "Board results are descriptive and help expose listing-age selection; no board-specific hypothesis or model is tested.",
        "",
        "## Limitations",
        "",
        "- The sample is the current broader-A universe applied historically, with survivorship and future-universe bias; it is not point-in-time.",
        "- QFQ uses the current adjustment vintage. CNINFO total-share lineage has documented exceptions; BaoStock Secondary uses a different circulating-share denominator.",
        "- Authoritative historical price-limit status, quoted bid–ask spreads, and direct analyst-coverage identification are unavailable.",
        "- China's T+1 and market microstructure differ from the U.S. setting studied by D05.",
        "- Size is not a pure information-asymmetry measure; first-stage C2 has estimation error; stocks are not cross-sectionally independent.",
        "- Evidence is sample-internal and historical-seen, not causal, OOS, or an investment conclusion.",
        "",
        "## QA and prohibited actions",
        "",
        f"- elapsed_seconds={elapsed:.2f}",
        f"- regression_numeric_failure_count={failures}",
        "- C2_based_exclusion_count=0",
        "- parameter_search_performed=false",
        "- winsorization_performed=false",
        "- strategy_backtest_run=false",
        "- future_performance_selection_used=false",
        "- MCTS_run=false",
        "- Phase_B_run=false",
        "- PRIMARY_750_ROLE_FIXED_BEFORE_C2=true",
        "- LONG_HISTORY_1000_ROLE_FIXED_BEFORE_C2=true",
        "- 1000_ALLOWED_TO_REPLACE_PRIMARY=false",
        "",
        "STOP AFTER H7 REPORT.",
    ]
    return "\n".join(lines) + "\n"


def run(root: Path) -> None:
    start = time.perf_counter()
    root = root.resolve()
    prereg = root / PREREGISTRATION
    if not prereg.exists():
        raise RuntimeError("preregistration_must_exist_before_C2_estimation")
    prereg_text = prereg.read_text(encoding="utf-8")
    required_freeze = [
        "COMMON_ANALYSIS_CUTOFF=2026-05-11", "PRIMARY_MIN_VALID_REGRESSION_ROWS=750",
        "LONG_HISTORY_D05_FIDELITY_MIN_ROWS=1000", "PRIMARY_750_ROLE_FIXED_BEFORE_C2=true",
        "1000_ALLOWED_TO_REPLACE_PRIMARY=false",
    ]
    if any(token not in prereg_text for token in required_freeze):
        raise RuntimeError("preregistration_contract_incomplete")

    universe = load_universe(root)
    universe_set = set(universe)
    calendar = load_calendar(root)
    membership_rows: list[dict[str, object]] = []
    primary_rows: list[dict[str, object]] = []
    long_rows: list[dict[str, object]] = []
    horizon_rows: list[dict[str, object]] = []
    secondary_rows: list[dict[str, object]] = []
    seen: set[str] = set()

    for code, group in iter_turnover_stocks(root / TURNOVER_PANEL):
        if code not in universe_set:
            continue
        seen.add(code)
        prices = load_qfq(root, code, calendar)
        rows = prepare_stock_rows(group, prices, calendar)
        counts = {h: int(rows[f"primary_valid_{h}d"].sum()) for h in (1, 2, 5)}
        primary_member = counts[1] >= PRIMARY_MIN_ROWS
        long_member = counts[1] >= LONG_HISTORY_MIN_ROWS
        valid_primary_dates = pd.DatetimeIndex(rows.index[rows.primary_valid_1d])
        size_metric, size_observations = historical_size(root, code, valid_primary_dates)
        blocking_reason = "" if primary_member else ("QFQ_OR_TURNOVER_UNAVAILABLE" if counts[1] == 0 else "VALID_1D_ROWS_BELOW_750")
        member = {
            "stock_code": code, "valid_1d_rows": counts[1], "valid_2d_rows": counts[2], "valid_5d_rows": counts[5],
            "primary_750_member": primary_member, "long_history_1000_member": long_member,
            "blocking_reason": blocking_reason, "board": board(code), "size_metric": size_metric,
            "size_observation_count": size_observations, "regression_numeric_failure": False,
        }
        if primary_member:
            fit1 = fit_stock(rows.loc[rows.primary_valid_1d], "primary_v", "future_1d_return")
            fit1.update({"stock_code": code, "board": board(code), "sample_role": "PRIMARY_750", "horizon": "1D", "size_metric": size_metric})
            primary_rows.append(fit1)
            member["regression_numeric_failure"] = fit1["evaluation_status"] != "SUCCESS"
            if long_member:
                fit_long = fit_stock(rows.loc[rows.primary_valid_1d], "primary_v", "future_1d_return")
                fit_long.update({"stock_code": code, "board": board(code), "sample_role": "LONG_HISTORY_D05_FIDELITY_ROBUSTNESS", "horizon": "1D", "size_metric": size_metric})
                long_rows.append(fit_long)
            for horizon in (2, 5):
                if counts[horizon] >= PRIMARY_MIN_ROWS:
                    fit_h = fit_stock(rows.loc[rows[f"primary_valid_{horizon}d"]], "primary_v", f"future_{horizon}d_return")
                    fit_h.update({"stock_code": code, "board": board(code), "sample_role": "PRIMARY_750_HORIZON_ROBUSTNESS", "horizon": f"{horizon}D"})
                    horizon_rows.append(fit_h)
            matched = rows.loc[rows.secondary_matched_valid_1d]
            if len(matched) >= PRIMARY_MIN_ROWS:
                primary_matched = fit_stock(matched, "primary_v", "future_1d_return")
                secondary_matched = fit_stock(matched, "secondary_v", "future_1d_return")
                status = "SUCCESS" if primary_matched["evaluation_status"] == secondary_matched["evaluation_status"] == "SUCCESS" else "REGRESSION_NUMERIC_FAILURE"
                secondary_rows.append({
                    "stock_code": code, "board": board(code), "matched_rows": len(matched), "evaluation_status": status,
                    "failure_reason_primary": primary_matched.get("failure_reason", ""), "failure_reason_secondary": secondary_matched.get("failure_reason", ""),
                    "C2_primary_matched": primary_matched.get("C2", np.nan), "C2_secondary_matched": secondary_matched.get("C2", np.nan),
                    "C2_difference_secondary_minus_primary": secondary_matched.get("C2", np.nan) - primary_matched.get("C2", np.nan),
                    "C1_primary_matched": primary_matched.get("C1", np.nan), "C1_secondary_matched": secondary_matched.get("C1", np.nan),
                    "t_C2_primary_hac5": primary_matched.get("t_C2_hac5", np.nan), "t_C2_secondary_hac5": secondary_matched.get("t_C2_hac5", np.nan),
                })
        membership_rows.append(member)

    for code in sorted(universe_set - seen):
        membership_rows.append({
            "stock_code": code, "valid_1d_rows": 0, "valid_2d_rows": 0, "valid_5d_rows": 0,
            "primary_750_member": False, "long_history_1000_member": False,
            "blocking_reason": "TURNOVER_PANEL_MISSING", "board": board(code), "size_metric": np.nan,
            "size_observation_count": 0, "regression_numeric_failure": False,
        })

    membership = pd.DataFrame(membership_rows).sort_values("stock_code").reset_index(drop=True)
    primary = pd.DataFrame(primary_rows).sort_values("stock_code").reset_index(drop=True)
    long_history = pd.DataFrame(long_rows).sort_values("stock_code").reset_index(drop=True)
    horizons = pd.DataFrame(horizon_rows).sort_values(["horizon", "stock_code"]).reset_index(drop=True)
    secondary = pd.DataFrame(secondary_rows).sort_values("stock_code").reset_index(drop=True)

    if len(membership) != UNIVERSE_SIZE or membership.stock_code.duplicated().any():
        raise RuntimeError("sample_membership_universe_reconciliation_failed")
    if not (~membership.long_history_1000_member | membership.primary_750_member).all():
        raise RuntimeError("long_history_not_nested_in_primary")
    if primary.stock_code.duplicated().any() or long_history.stock_code.duplicated().any():
        raise RuntimeError("duplicate_stock_coefficient")

    successful_primary = primary.loc[primary.evaluation_status.eq("SUCCESS")].copy()
    if not successful_primary.empty:
        threshold = successful_primary.C2.abs().quantile(0.99)
        primary["extreme_C2_flag"] = primary.C2.abs().ge(threshold) & primary.evaluation_status.eq("SUCCESS")
    else:
        primary["extreme_C2_flag"] = False
    long_history["extreme_C2_flag"] = long_history.stock_code.isin(primary.loc[primary.extreme_C2_flag, "stock_code"])

    size_rows, size_summary = size_diagnostic(primary.loc[primary.evaluation_status.eq("SUCCESS")])
    output = root / OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    membership.to_csv(output / "h7_sample_membership_v1.csv", index=False, encoding="utf-8-sig")
    primary.to_csv(output / "h7_stock_level_coefficients_primary_750.csv", index=False, encoding="utf-8-sig")
    long_history.to_csv(output / "h7_stock_level_coefficients_long_history_1000.csv", index=False, encoding="utf-8-sig")
    horizons.to_csv(output / "h7_horizon_robustness.csv", index=False, encoding="utf-8-sig")
    secondary.to_csv(output / "h7_secondary_turnover_matched_robustness.csv", index=False, encoding="utf-8-sig")
    size_rows.to_csv(output / "h7_size_heterogeneity.csv", index=False, encoding="utf-8-sig")
    elapsed = time.perf_counter() - start
    report = render_report(primary, long_history, horizons, secondary, size_rows, size_summary, membership, elapsed)
    (output / "h7_dynamic_volume_return_report_v1.md").write_text(report, encoding="utf-8")
    print(f"H7_COMPLETE primary={membership.primary_750_member.sum()} long_history={membership.long_history_1000_member.sum()} elapsed_seconds={elapsed:.2f}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    run(args.project_root)


if __name__ == "__main__":
    main()
