"""Offline H7 contract-readiness audit using availability flags only."""

# ruff: noqa: E501 -- fixed contract prose and explicit diagnostics are intentional.

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from scripts.audit_h7_turnover_data_quality import board, code6, point_in_time_shares
else:
    from audit_h7_turnover_data_quality import board, code6, point_in_time_shares

DATA_CUTOFF = pd.Timestamp("2026-08-20")
OUT = Path("reports/hypothesis_7/final_contract")
BAO = Path("data/cache/h7_turnover/baostock")
CN = Path("data/cache/h7_turnover/cninfo")
QFQ = Path("data/cache/h5a_broader_a_qfq_v1")


def exact_200_market_days(valid: pd.Series) -> pd.Series:
    current = valid.eq(True)
    return current & current.shift(1).rolling(200, min_periods=200).sum().eq(200)


def last_200_active_days(valid_active: pd.Series) -> pd.Series:
    current = valid_active.eq(True)
    return current & current.astype(int).cumsum().shift(1, fill_value=0).ge(200)


def load_events(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype={"stock_code": str})
    for column in ("change_date", "announcement_date", "information_available_date"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame["total_shares"] = pd.to_numeric(frame.total_shares, errors="coerce")
    frame["circulating_shares"] = pd.to_numeric(frame.circulating_shares, errors="coerce")
    frame["event_date_incomplete"] = frame.event_date_incomplete.astype(str).str.lower().eq("true")
    return frame


def load_qfq(path: Path) -> tuple[pd.Timestamp, pd.Timestamp, set[pd.Timestamp]]:
    if not path.exists():
        return pd.NaT, pd.NaT, set()
    frame = pd.read_csv(path, usecols=["trade_date", "qfq_close"])
    dates = pd.to_datetime(frame.trade_date, errors="coerce")
    valid = pd.to_numeric(frame.qfq_close, errors="coerce").gt(0) & dates.le(DATA_CUTOFF)
    values = set(dates[valid].dropna())
    return (min(values), max(values), values) if values else (pd.NaT, pd.NaT, set())


def threshold_counts(frame: pd.DataFrame, column: str) -> dict[int, int]:
    return {threshold: int(frame[column].ge(threshold).sum()) for threshold in (500, 750, 1000, 1250)}


def classify_endpoint_gap(
    date: pd.Timestamp, horizon: int, calendar: pd.DatetimeIndex,
    positions: dict[pd.Timestamp, int], qfq_min: pd.Timestamp, qfq_max: pd.Timestamp,
    qfq_dates: set[pd.Timestamp], practical_cutoff: pd.Timestamp,
) -> str | None:
    position = positions[date]
    if position == 0 or position + horizon >= len(calendar):
        return "F_OTHER"
    required = (calendar[position - 1], date, calendar[position + horizon])
    if all(item in qfq_dates for item in required):
        return None
    if any(item > practical_cutoff for item in required):
        return "A_QFQ_TAIL_NOT_REFRESHED"
    if not qfq_dates:
        return "E_TURNOVER_ROW_NOT_PRICE_ELIGIBLE"
    if any(item < qfq_min for item in required):
        return "E_TURNOVER_ROW_NOT_PRICE_ELIGIBLE"
    if qfq_max < practical_cutoff and any(item > qfq_max for item in required):
        return "C_STOCK_PRICE_SERIES_ENDED"
    if any(qfq_min <= item <= qfq_max and item not in qfq_dates for item in required):
        return "D_INTERNAL_QFQ_GAP"
    return "F_OTHER"


def run(root: Path) -> None:
    root = root.resolve()
    output = root / OUT
    output.mkdir(parents=True, exist_ok=True)
    universe_frame = pd.read_csv(root / "data/processed/h5a_broader_a_universe_v1.csv", dtype={"stock_code": str})
    universe = sorted(universe_frame.loc[universe_frame.universe_status.eq("INCLUDED"), "stock_code"].map(code6).unique())
    if len(universe) != 5195:
        raise ValueError(f"expected_5195_stocks_got={len(universe)}")
    reference = pd.read_csv(root / BAO / "000001.csv", usecols=["trade_date"])
    market_calendar = pd.DatetimeIndex(pd.to_datetime(reference.trade_date).sort_values().unique())
    positions = {date: index for index, date in enumerate(market_calendar)}
    qfq_profiles = []
    for code in universe:
        qfq_min, qfq_max, _ = load_qfq(root / QFQ / f"{code}.csv")
        qfq_profiles.append({"stock_code": code, "qfq_date_min": qfq_min, "qfq_date_max": qfq_max})
    qfq_profile = pd.DataFrame(qfq_profiles)
    latest_counts = qfq_profile.qfq_date_max.dropna().value_counts()
    practical_cutoff = latest_counts.index[0]
    practical_position = positions[practical_cutoff]
    common_cutoff = market_calendar[practical_position - 5]
    global_qfq_min = qfq_profile.qfq_date_min.min()
    global_qfq_max = qfq_profile.qfq_date_max.max()
    turnover_date_max = pd.NaT
    panel_rows = 0
    for chunk in pd.read_csv(root / "data/processed/h7_turnover_daily_panel_v1.csv", usecols=["trade_date"], chunksize=500_000):
        dates = pd.to_datetime(chunk.trade_date, errors="coerce")
        turnover_date_max = max(turnover_date_max, dates.max()) if pd.notna(turnover_date_max) else dates.max()
        panel_rows += len(chunk)

    prior_exceptions = pd.read_csv(root / "reports/hypothesis_7/data_quality/h7_turnover_quality_exceptions.csv", dtype={"stock_code": str})
    size = pd.read_csv(root / "reports/hypothesis_7/h7_history_sufficiency.csv", dtype={"stock_code": str})
    size = size.loc[size.row_type.eq("stock"), ["stock_code", "latest_total_market_cap"]]
    size["stock_code"] = size.stock_code.map(code6)
    size["log_size"] = np.log(pd.to_numeric(size.latest_total_market_cap, errors="coerce"))
    size_valid = size.log_size.notna()
    size.loc[size_valid, "size_quartile"] = pd.qcut(
        size.loc[size_valid, "log_size"].rank(method="first"), 4,
        labels=["Q1_SMALL", "Q2", "Q3", "Q4_LARGE"],
    ).astype(str)

    stock_rows = []
    gap_rows = []
    comparison_rows = []
    gap_counts = {horizon: Counter() for horizon in (1, 2, 5)}
    gap_stocks = {horizon: defaultdict(set) for horizon in (1, 2, 5)}
    common_endpoint_denominator = {horizon: 0 for horizon in (1, 2, 5)}
    common_endpoint_numerator = {horizon: 0 for horizon in (1, 2, 5)}
    suspended_rows = suspended_volume_zero = suspended_turn_zero = suspended_turn_missing = suspended_qfq = 0
    active_rows = active_zero_turnover = active_qfq = 0
    active_positive_primary = active_valid_primary = 0
    active_primary_values: list[np.ndarray] = []
    tail_refresh_stocks = 0
    tail_refresh_stock_days = 0
    st_potential_rows = total_potential_rows = 0

    for number, code in enumerate(universe, 1):
        bao = pd.read_csv(root / BAO / f"{code}.csv", dtype={"stock_code": str})
        bao["trade_date"] = pd.to_datetime(bao.trade_date)
        for column in ("volume_shares", "baostock_circulating_turnover", "trading_status", "is_st"):
            bao[column] = pd.to_numeric(bao[column], errors="coerce")
        events = load_events(root / CN / f"{code}.csv")
        lineage = point_in_time_shares(events, pd.DatetimeIndex(bao.trade_date))
        daily = bao.merge(lineage, on="trade_date", how="left", validate="one_to_one")
        primary = (daily.volume_shares / daily.total_shares.where(daily.total_shares.gt(0))).replace([np.inf, -np.inf], np.nan)
        secondary = daily.baostock_circulating_turnover.where(daily.baostock_circulating_turnover.ge(0))
        frame = pd.DataFrame({"trade_date": market_calendar}).merge(
            pd.DataFrame({
                "trade_date": daily.trade_date, "primary": primary, "secondary": secondary,
                "volume": daily.volume_shares, "trading_status": daily.trading_status,
                "is_st": daily.is_st,
            }), on="trade_date", how="left",
        )
        active = frame.trading_status.eq(1)
        active_primary = active & frame.primary.gt(0) & np.isfinite(frame.primary)
        active_secondary = active & frame.secondary.gt(0) & np.isfinite(frame.secondary)
        exact_primary = exact_200_market_days(active_primary)
        last_active_primary = last_200_active_days(active_primary)
        exact_secondary = exact_200_market_days(active_secondary)
        last_active_secondary = last_200_active_days(active_secondary)
        suspension_zero_valid = frame.trading_status.eq(0) & frame.volume.eq(0) & frame.primary.notna()
        calendar_zero_baseline = exact_200_market_days(active_primary | suspension_zero_valid) & active_primary
        qfq_min, qfq_max, qfq_dates = load_qfq(root / QFQ / f"{code}.csv")
        qfq_present = pd.Series(market_calendar.isin(qfq_dates), index=frame.index)
        valid_r_t = qfq_present & qfq_present.shift(1, fill_value=False)
        potential = {}
        potential_secondary = {}
        for horizon in (1, 2, 5):
            endpoint = qfq_present.shift(-horizon, fill_value=False)
            potential[horizon] = last_active_primary & valid_r_t & endpoint
            potential_secondary[horizon] = last_active_secondary & valid_r_t & endpoint
            common_scope = last_active_primary & frame.trade_date.le(common_cutoff)
            common_endpoint_denominator[horizon] += int(common_scope.sum())
            common_endpoint_numerator[horizon] += int((common_scope & valid_r_t & endpoint).sum())
            baseline_dates = frame.loc[last_active_primary, "trade_date"]
            for date in baseline_dates:
                reason = classify_endpoint_gap(
                    date, horizon, market_calendar, positions, qfq_min, qfq_max,
                    qfq_dates, practical_cutoff,
                )
                if reason:
                    gap_counts[horizon][reason] += 1
                    gap_stocks[horizon][reason].add(code)
        suspended = frame.trading_status.eq(0)
        suspended_rows += int(suspended.sum())
        suspended_volume_zero += int((suspended & frame.volume.eq(0)).sum())
        suspended_turn_zero += int((suspended & frame.secondary.eq(0)).sum())
        suspended_turn_missing += int((suspended & frame.secondary.isna()).sum())
        suspended_qfq += int((suspended & qfq_present).sum())
        active_rows += int(active.sum())
        active_zero_turnover += int((active & frame.primary.eq(0)).sum())
        active_qfq += int((active & qfq_present).sum())
        active_valid_primary += int((active & frame.primary.notna()).sum())
        active_positive_primary += int(active_primary.sum())
        active_primary_values.append(frame.loc[active_primary, "primary"].to_numpy(dtype=float))
        tail_rows = frame.trade_date.gt(practical_cutoff) & frame.trade_date.le(DATA_CUTOFF) & frame.trading_status.notna()
        tail_refresh_stocks += int(tail_rows.any() and bool(qfq_dates))
        tail_refresh_stock_days += int(tail_rows.sum() and len(qfq_dates) > 0) * int(tail_rows.sum())
        total_potential_rows += int(potential[1].sum())
        st_potential_rows += int((potential[1] & frame.is_st.eq(1)).sum())
        stock_rows.append({
            "stock_code": code, "board": board(code), "qfq_date_min": qfq_min,
            "qfq_date_max": qfq_max, "turnover_date_max": daily.trade_date.max(),
            "exact_200_primary_days": int(exact_primary.sum()),
            "last_200_active_primary_days": int(last_active_primary.sum()),
            "calendar_with_suspension_zero_primary_days": int(calendar_zero_baseline.sum()),
            "exact_200_secondary_days": int(exact_secondary.sum()),
            "last_200_active_secondary_days": int(last_active_secondary.sum()),
            "potential_1d_regression_rows": int(potential[1].sum()),
            "potential_2d_regression_rows": int(potential[2].sum()),
            "potential_5d_regression_rows": int(potential[5].sum()),
            "secondary_potential_1d_rows": int(potential_secondary[1].sum()),
            "secondary_potential_2d_rows": int(potential_secondary[2].sum()),
            "secondary_potential_5d_rows": int(potential_secondary[5].sum()),
            "st_potential_1d_rows": int((potential[1] & frame.is_st.eq(1)).sum()),
            "active_primary_zero_rows": int((active & frame.primary.eq(0)).sum()),
        })
        if number % 500 == 0:
            print(f"offline_contract_audit={number}/{len(universe)}", flush=True)

    availability = pd.DataFrame(stock_rows).merge(size, on="stock_code", how="left")
    for horizon in (1, 2, 5):
        total_missing = sum(gap_counts[horizon].values())
        for reason, count in sorted(gap_counts[horizon].items()):
            gap_rows.append({
                "row_type": "ENDPOINT_GAP", "horizon": horizon, "reason": reason,
                "missing_endpoint_rows": count, "missing_endpoint_stocks": len(gap_stocks[horizon][reason]),
                "reason_share": count / total_missing if total_missing else math.nan,
            })
        gap_rows.append({
            "row_type": "COMMON_CUTOFF_ENDPOINT", "horizon": horizon,
            "analysis_cutoff": common_cutoff, "eligible_turnover_rows": common_endpoint_denominator[horizon],
            "endpoint_ready_rows": common_endpoint_numerator[horizon],
            "endpoint_coverage": common_endpoint_numerator[horizon] / common_endpoint_denominator[horizon],
        })
    for date, count in latest_counts.items():
        gap_rows.append({"row_type": "QFQ_LATEST_DATE_DISTRIBUTION", "qfq_latest_date": date, "stock_count": count})
    for row in qfq_profile.to_dict("records"):
        gap_rows.append({"row_type": "STOCK_QFQ_COVERAGE", **row})
    gap_frame = pd.DataFrame(gap_rows)

    for label, column in (
        ("EXACT_200_MARKET_DAYS_PRIMARY", "exact_200_primary_days"),
        ("LAST_200_ACTIVE_TRADING_DAYS_PRIMARY", "last_200_active_primary_days"),
        ("CALENDAR_WITH_SUSPENSION_ZERO_PRIMARY", "calendar_with_suspension_zero_primary_days"),
        ("LAST_200_ACTIVE_TRADING_DAYS_SECONDARY", "last_200_active_secondary_days"),
        ("POTENTIAL_1D_PRIMARY", "potential_1d_regression_rows"),
        ("POTENTIAL_2D_PRIMARY", "potential_2d_regression_rows"),
        ("POTENTIAL_5D_PRIMARY", "potential_5d_regression_rows"),
        ("POTENTIAL_1D_SECONDARY", "secondary_potential_1d_rows"),
    ):
        counts = threshold_counts(availability, column)
        comparison_rows.append({
            "comparison": label, "stock_count_any": int(availability[column].gt(0).sum()),
            "median_valid_rows": availability[column].median(),
            **{f"stocks_ge_{threshold}": count for threshold, count in counts.items()},
        })
    for minimum in (750, 1000):
        included = availability.potential_1d_regression_rows.ge(minimum)
        sample = availability.loc[included]
        board_inclusion = availability.assign(included=included).groupby("board", observed=True).included.mean().to_dict()
        board_composition = sample.board.value_counts(normalize=True).to_dict()
        size_inclusion = availability.assign(included=included).groupby("size_quartile", observed=True).included.mean().to_dict()
        comparison_rows.append({
            "comparison": f"MIN_ROWS_{minimum}", "stock_count": int(included.sum()),
            "universe_share": float(included.mean()), "median_market_cap": sample.latest_total_market_cap.median(),
            "board_inclusion_rates": json.dumps(board_inclusion, ensure_ascii=False),
            "board_composition": json.dumps(board_composition, ensure_ascii=False),
            "size_quartile_inclusion_rates": json.dumps(size_inclusion, ensure_ascii=False),
            "history_length_log_size_spearman": sample[["potential_1d_regression_rows", "log_size"]].corr(method="spearman").iloc[0, 1],
        })
    comparison = pd.DataFrame(comparison_rows)
    active_values = np.concatenate(active_primary_values)
    active_q = {point: float(np.quantile(active_values, point)) for point in (0, .001, .01, .05, .5)}
    blocking = set(availability.loc[availability.potential_1d_regression_rows.eq(0), "stock_code"])
    blocking_types = {
        "SUCCESS_NO_EVENTS_NO_OPENING_LEVEL", "SCHEMA_ERROR", "CORRUPT_FILE",
        "CNINFO_INVALID_TOTAL_SHARES",
    }
    blocking.update(prior_exceptions.loc[prior_exceptions.exception_type.isin(blocking_types), "stock_code"].dropna())
    flagged = set(prior_exceptions.stock_code.dropna()) - blocking
    report = make_report(
        universe, global_qfq_min, global_qfq_max, turnover_date_max, practical_cutoff,
        common_cutoff, panel_rows, tail_refresh_stocks, tail_refresh_stock_days,
        suspended_rows, suspended_volume_zero, suspended_turn_zero, suspended_turn_missing,
        suspended_qfq, active_rows, active_zero_turnover, active_qfq,
        active_valid_primary, active_positive_primary, active_q, availability, comparison,
        gap_frame, market_calendar, st_potential_rows, total_potential_rows,
        len(blocking), len(flagged),
    )
    availability.to_csv(output / "h7_regression_row_availability_by_stock.csv", index=False, encoding="utf-8-sig")
    gap_frame.to_csv(output / "h7_qfq_gap_diagnostics.csv", index=False, encoding="utf-8-sig")
    comparison.to_csv(output / "h7_contract_comparison.csv", index=False, encoding="utf-8-sig")
    (output / "h7_final_contract_readiness.md").write_text(report, encoding="utf-8")
    print("PROPOSED_H7_CONTRACT_STATUS=FOR_HUMAN_REVIEW")


def make_report(
    universe: list[str], qfq_min: pd.Timestamp, qfq_max: pd.Timestamp,
    turnover_max: pd.Timestamp, practical_cutoff: pd.Timestamp,
    common_cutoff: pd.Timestamp, panel_rows: int, tail_stocks: int, tail_days: int,
    suspended_rows: int, suspended_volume_zero: int, suspended_turn_zero: int,
    suspended_turn_missing: int, suspended_qfq: int, active_rows: int,
    active_zero: int, active_qfq: int, active_valid: int, active_positive: int,
    active_q: dict, availability: pd.DataFrame, comparison: pd.DataFrame,
    gaps: pd.DataFrame, calendar: pd.DatetimeIndex, st_rows: int, potential_rows: int,
    blocking_count: int, flag_count: int,
) -> str:
    rows = comparison.set_index("comparison")
    exact = rows.loc["EXACT_200_MARKET_DAYS_PRIMARY"]
    active = rows.loc["LAST_200_ACTIVE_TRADING_DAYS_PRIMARY"]
    primary = rows.loc["POTENTIAL_1D_PRIMARY"]
    secondary = rows.loc["POTENTIAL_1D_SECONDARY"]
    one = rows.loc["POTENTIAL_1D_PRIMARY"]
    two = rows.loc["POTENTIAL_2D_PRIMARY"]
    five = rows.loc["POTENTIAL_5D_PRIMARY"]
    sample750 = rows.loc["MIN_ROWS_750"]
    sample1000 = rows.loc["MIN_ROWS_1000"]
    gap_only = gaps.loc[gaps.row_type.eq("ENDPOINT_GAP")]
    top_gap = gap_only.groupby("reason", observed=True).missing_endpoint_rows.sum().sort_values(ascending=False)
    primary_cause = top_gap.index[0] if len(top_gap) else "NONE"
    market_gap = int(((calendar > practical_cutoff) & (calendar <= turnover_max)).sum())
    common = gaps.loc[gaps.row_type.eq("COMMON_CUTOFF_ENDPOINT"), ["horizon", "eligible_turnover_rows", "endpoint_coverage"]]
    return f"""# H7 Final Contract Readiness Audit

## Decision

The existing offline data are sufficient to draft a contract for human review without estimating H7. The dominant endpoint issue is a synchronized QFQ tail: 5,175/5,180 existing QFQ files end on 2026-05-18, while turnover ends on 2026-08-20. A conservative common signal-date cutoff of **{common_cutoff.date()}** leaves five market days for the fixed 5D endpoint. The current history is already adequate for a 1,000-row Primary and 750-row sensitivity; an incremental tail refresh is optional, not required to preregister H7.

```text
QFQ_global_date_min={qfq_min.date()}
QFQ_global_date_max={qfq_max.date()}
turnover_date_max={turnover_max.date()}
turnover_panel_rows={panel_rows}
tail_gap_calendar_days={(turnover_max-practical_cutoff).days}
tail_gap_market_days={market_gap}
endpoint_gap_primary_cause={primary_cause}
COMMON_ANALYSIS_CUTOFF={common_cutoff.date()}
QFQ_TAIL_REFRESH_REQUIRED=false
QFQ_TAIL_REFRESH_SCOPE=OPTIONAL_INCREMENTAL_EXISTING_SERIES_{(practical_cutoff + pd.Timedelta(days=1)).date()}_TO_{DATA_CUTOFF.date()}
estimated_tail_refresh_stock_count={tail_stocks}
estimated_tail_refresh_stock_days={tail_days}
```

## QFQ gap decomposition

{gap_only.groupby(['horizon', 'reason'], observed=True).agg(missing_endpoint_rows=('missing_endpoint_rows','sum'), missing_endpoint_stocks=('missing_endpoint_stocks','max'), reason_share=('reason_share','sum')).reset_index().to_markdown(index=False)}

At the common signal cutoff, endpoint-presence coverage is:

{common.to_markdown(index=False)}

This cutoff removes the uniform tail while retaining the existing historical window. Remaining missing rows mainly reflect the bounded QFQ start, absent full QFQ series, the four early-ending files, or isolated internal gaps. Refreshing the 67-market-day tail is much smaller than a full-history reload, but it is not necessary merely to increase sample size.

## Suspension and zero contract

```text
suspended_rows={suspended_rows}
suspended_volume_zero_share={suspended_volume_zero/suspended_rows if suspended_rows else math.nan}
suspended_turnover_zero_share={suspended_turn_zero/suspended_rows if suspended_rows else math.nan}
suspended_turnover_missing_share={suspended_turn_missing/suspended_rows if suspended_rows else math.nan}
suspended_qfq_close_available_share={suspended_qfq/suspended_rows if suspended_rows else math.nan}
active_rows={active_rows}
active_zero_primary_turnover_rows={active_zero}
active_qfq_close_available_share={active_qfq/active_rows if active_rows else math.nan}
RECOMMENDED_SUSPENSION_TREATMENT=ACTIVE_DAYS_ONLY
```

A suspension is not an observed low-demand trading day: the market did not permit normal trading. Treating it as zero would mix non-comparable states into log turnover. The Primary recommendation is therefore `ACTIVE_DAYS_ONLY`; suspended dates are invalid observations, not zeros.

## 200-day availability contracts

| contract | stocks any | median valid days | >=500 | >=750 | >=1000 | >=1250 |
|---|---:|---:|---:|---:|---:|---:|
| EXACT_200_MARKET_DAYS | {int(exact.stock_count_any)} | {exact.median_valid_rows:.0f} | {int(exact.stocks_ge_500)} | {int(exact.stocks_ge_750)} | {int(exact.stocks_ge_1000)} | {int(exact.stocks_ge_1250)} |
| LAST_200_ACTIVE_TRADING_DAYS | {int(active.stock_count_any)} | {active.median_valid_rows:.0f} | {int(active.stocks_ge_500)} | {int(active.stocks_ge_750)} | {int(active.stocks_ge_1000)} | {int(active.stocks_ge_1250)} |

`EXACT_200_MARKET_DAYS` is closer to literal calendar fidelity but invalidates long spans after even a short suspension. `LAST_200_ACTIVE_TRADING_DAYS` preserves a 200-observation historical mean among comparable trading observations; its calendar span may exceed 200 market days, but it never uses future observations. For A-share economic comparability, the proposed Primary is **LAST_200_ACTIVE_TRADING_DAYS**. The exact-market-day definition remains a data-only comparison, not a searched alternative.

## Log contract

Among valid active Primary observations: positive rate={active_positive/active_valid if active_valid else math.nan:.8%}, zero count={active_zero:,}, smallest positive={active_q[0]:.8g}, p0.1={active_q[.001]:.8g}, p1={active_q[.01]:.8g}, p5={active_q[.05]:.8g}, median={active_q[.5]:.8g}. The data support `LOG_TURNOVER=log(TOTAL_SHARE_TURNOVER)` on positive active rows. `epsilon_required=false`; no D05 epsilon is copied.

## Potential regression-row availability (presence only)

| horizon | stocks any | median rows | >=500 | >=750 | >=1000 | >=1250 |
|---:|---:|---:|---:|---:|---:|---:|
| 1D | {int(one.stock_count_any)} | {one.median_valid_rows:.0f} | {int(one.stocks_ge_500)} | {int(one.stocks_ge_750)} | {int(one.stocks_ge_1000)} | {int(one.stocks_ge_1250)} |
| 2D | {int(two.stock_count_any)} | {two.median_valid_rows:.0f} | {int(two.stocks_ge_500)} | {int(two.stocks_ge_750)} | {int(two.stocks_ge_1000)} | {int(two.stocks_ge_1250)} |
| 5D | {int(five.stock_count_any)} | {five.median_valid_rows:.0f} | {int(five.stocks_ge_500)} | {int(five.stocks_ge_750)} | {int(five.stocks_ge_1000)} | {int(five.stocks_ge_1250)} |

Rows require positive active Primary turnover, the proposed past-only baseline, QFQ t-1/t presence, and the appropriate future price endpoint. These are availability flags; no price ratio, coefficient, sign, or outcome comparison was computed.

## 750 versus 1,000 rows

| minimum | stocks | universe share | median market cap | board inclusion rates | size-quartile inclusion rates |
|---:|---:|---:|---:|---|---|
| 750 | {int(sample750.stock_count)} | {sample750.universe_share:.2%} | {sample750.median_market_cap:.4g} | {sample750.board_inclusion_rates} | {sample750.size_quartile_inclusion_rates} |
| 1000 | {int(sample1000.stock_count)} | {sample1000.universe_share:.2%} | {sample1000.median_market_cap:.4g} | {sample1000.board_inclusion_rates} | {sample1000.size_quartile_inclusion_rates} |

`RECOMMENDED_PRIMARY_MIN_ROWS=1000` because it is closer to the D05 long-history design and offers more plausible stock-level estimation stability. `RECOMMENDED_SENSITIVITY_MIN_ROWS=750` makes the selection cost visible and improves retention. This recommendation uses no coefficient or return information.

## ST and limit-status contract

ST observations are {st_rows/potential_rows if potential_rows else math.nan:.6%} of otherwise potential 1D rows. Because ST stocks face special trading limits and microstructure, the proposed Primary excludes **ST observations**, while retaining the stock during non-ST intervals; excluding whole stocks would discard unrelated history. This remains for human approval. Historical limit-status is unavailable. That limitation is most material for 1D interpretation; 2D and 5D are retained as fixed microstructure-robustness horizons, not searched performance alternatives.

## Primary, Secondary, and exceptions

Primary availability: stocks any={int(primary.stock_count_any)}, median rows={primary.median_valid_rows:.0f}, >=750={int(primary.stocks_ge_750)}, >=1000={int(primary.stocks_ge_1000)}. Secondary availability: stocks any={int(secondary.stock_count_any)}, median rows={secondary.median_valid_rows:.0f}, >=750={int(secondary.stocks_ge_750)}, >=1000={int(secondary.stocks_ge_1000)}. They remain different measurements and are never substituted for one another.

`future_H7_blocking_exclusion_count={blocking_count}` includes no Primary/opening level, corrupt/impossible denominator, or zero potential 1D history. `future_H7_flag_only_stock_count={flag_count}` retains non-authoritative local discrepancies, circulating-denominator differences, deterministic duplicate-date warnings, and other lineage flags without deleting usable Primary rows.

## PROPOSED_H7_CONTRACT

```text
status=FOR_HUMAN_REVIEW
Primary turnover=TOTAL_SHARE_TURNOVER
Secondary turnover=BAOSTOCK_CIRCULATING_TURNOVER
Primary horizon=1D
Microstructure robustness horizons=2D,5D
Suspension treatment=ACTIVE_DAYS_ONLY
200D baseline definition=LAST_200_ACTIVE_TRADING_DAYS
Log zero handling=DIRECT_LOG_POSITIVE_ACTIVE_ROWS
ST treatment=EXCLUDE_ST_OBSERVATIONS; RETAIN_NON_ST_HISTORY
Primary minimum regression rows=1000
Sensitivity minimum regression rows=750
QFQ analysis cutoff={common_cutoff.date()}
QFQ tail refresh needed=false; optional incremental refresh only
Blocking data exclusions=no Primary/opening level; corrupt/impossible denominator; no potential 1D history
```

`C2_estimated=false`, `volume_return_regression_run=false`, `future_performance_accessed=false`, `network_download_performed=false`. Recommended next step: human review and approval or revision of this proposed contract, then create a separate formal preregistration before any H7 coefficient estimation.
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    run(parser.parse_args().project_root)
