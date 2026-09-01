"""Audit signal-time readiness for fixed 50-day abnormal-activity ranks."""

# ruff: noqa: E501 -- report prose is intentionally kept readable.

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from scripts.audit_h5a_activity_main_effect import _market_calendar
    from scripts.run_h5a_trading_activity_reversal_timing_v1 import code6
else:
    from audit_h5a_activity_main_effect import _market_calendar
    from run_h5a_trading_activity_reversal_timing_v1 import code6

OUTPUT_DIR = Path("reports/hypothesis_6")
CANDIDATES = ("DAILY_AMOUNT_OWN_HISTORY_RANK", "DAILY_VT_OWN_HISTORY_RANK")
SHOCK_STATES = ("LOW_SHOCK", "NORMAL", "HIGH_SHOCK")
RETURN_STATES = ("LOW_RETURN", "MID_RETURN", "HIGH_RETURN")

IDENTITY = {
    "analysis_type": "h6_abnormal_activity_data_readiness_audit",
    "sample_role": "historical_seen",
    "future_return_accessed": False,
    "H6_performance_run": False,
    "proxy_selected_using_future_returns": False,
    "network_download_performed": False,
    "MCTS_run": False,
    "Phase_B_run": False,
}


def own_history_rank(values: pd.Series, dates: pd.DatetimeIndex) -> dict:
    """Rank formation day within exactly 50 dates; date ascending breaks value ties."""
    if len(dates) != 50:
        return {"valid": False}
    selected = pd.to_numeric(values.reindex(dates), errors="coerce")
    if not (np.isfinite(selected).all() and selected.gt(0).all()):
        return {"valid": False}
    ordered = pd.DataFrame({"value": selected.to_numpy(), "date": dates}).sort_values(
        ["value", "date"], kind="stable"
    )
    rank = int(np.flatnonzero(ordered["date"].eq(dates[-1]).to_numpy())[0] + 1)
    state = "LOW_SHOCK" if rank <= 5 else "HIGH_SHOCK" if rank >= 46 else "NORMAL"
    trend = (
        pd.Series(selected.to_numpy()).corr(pd.Series(np.arange(50)), method="spearman")
        if selected.nunique() > 1
        else math.nan
    )
    tied = int(selected.eq(selected.iloc[-1]).sum())
    return {
        "valid": True,
        "own_history_rank": rank,
        "own_history_percentile": rank / 50,
        "shock_state": state,
        "trend_spearman": trend,
        "formation_tie_count": tied,
    }


def _load_states(root: Path) -> pd.DataFrame:
    states = pd.read_csv(
        root / "reports/hypothesis_5b/h5b_vt20_signal_panel.csv",
        usecols=["period_index", "signal_as_of_date", "stock_code", "RETURN60", "RETURN_STATE"],
        dtype={"stock_code": str},
    )
    states["stock_code"] = states["stock_code"].map(code6)
    states["signal_as_of_date"] = pd.to_datetime(states["signal_as_of_date"], errors="raise")
    if set(states["period_index"].unique()) != set(range(1, 57)):
        raise ValueError("primary_periods_not_1_to_56")
    if states.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("duplicate_signal_key")
    if not states["RETURN_STATE"].isin(RETURN_STATES).all():
        raise ValueError("invalid_reused_return_state")
    return states


def _windows(root: Path, states: pd.DataFrame) -> dict[int, pd.DatetimeIndex]:
    calendar = _market_calendar(root)
    positions = {date: index for index, date in enumerate(calendar)}
    windows = {}
    for row in states[["period_index", "signal_as_of_date"]].drop_duplicates().itertuples(index=False):
        end = positions[row.signal_as_of_date]
        window = calendar[end - 49 : end + 1]
        if len(window) != 50 or window[-1] != row.signal_as_of_date:
            raise ValueError(f"invalid_exact_50d_window={row.period_index}")
        windows[int(row.period_index)] = window
    return windows


def _scan_local_daily(
    root: Path, states: pd.DataFrame, windows: dict[int, pd.DatetimeIndex]
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    resolution = pd.read_csv(
        root / "reports/hypothesis_5a_broader_a/source_resolution_report.csv",
        dtype={"stock_code": str},
    )
    resolution["stock_code"] = resolution["stock_code"].map(code6)
    paths = resolution.set_index("stock_code")["canonical_amount_path"].dropna().to_dict()
    periods_by_code = states.groupby("stock_code")["period_index"].apply(list).to_dict()
    signal_lookup = states.set_index("period_index")["signal_as_of_date"].to_dict()
    needed_dates = pd.DatetimeIndex(sorted(set().union(*(set(window) for window in windows.values()))))
    needed_set = set(needed_dates)
    observations = []
    profiles = []
    market_rows = []

    for code, path_text in paths.items():
        period_ids = periods_by_code.get(code, [])
        path = root / str(path_text)
        raw = pd.read_csv(path, usecols=["date", "amount", "total_market_cap", "close"])
        raw["date"] = pd.to_datetime(raw["date"], errors="raise")
        if raw["date"].duplicated().any():
            raise ValueError(f"duplicate_raw_date={code}")
        for column in ("amount", "total_market_cap", "close"):
            raw[column] = pd.to_numeric(raw[column], errors="coerce")
        full_amount_valid = np.isfinite(raw["amount"]) & raw["amount"].gt(0)
        full_cap_valid = np.isfinite(raw["total_market_cap"]) & raw["total_market_cap"].gt(0)
        profiles.append(
            {
                "stock_code": code,
                "rows": len(raw),
                "amount_valid_rows": int(full_amount_valid.sum()),
                "cap_valid_rows": int(full_cap_valid.sum()),
                "date_min": raw["date"].min() if len(raw) else pd.NaT,
                "date_max": raw["date"].max() if len(raw) else pd.NaT,
            }
        )
        raw = raw.loc[raw["date"].isin(needed_set)].set_index("date").sort_index()
        amount_valid = np.isfinite(raw["amount"]) & raw["amount"].gt(0)
        cap_valid = np.isfinite(raw["total_market_cap"]) & raw["total_market_cap"].gt(0)
        market_rows.append(
            pd.DataFrame(
                {
                    "trade_date": raw.index[amount_valid],
                    "amount": raw.loc[amount_valid, "amount"].to_numpy(),
                }
            )
        )
        amount_series = raw["amount"]
        vt_series = (raw["amount"] / raw["total_market_cap"]).where(amount_valid & cap_valid)
        for period in period_ids:
            for candidate, series in zip(CANDIDATES, (amount_series, vt_series), strict=True):
                result = own_history_rank(series, windows[period])
                observations.append(
                    {
                        "period_index": period,
                        "signal_as_of_date": signal_lookup[period],
                        "stock_code": code,
                        "candidate": candidate,
                        "valid_50d": result.get("valid", False),
                        "own_history_rank": result.get("own_history_rank", math.nan),
                        "own_history_percentile": result.get("own_history_percentile", math.nan),
                        "shock_state": result.get("shock_state", pd.NA),
                        "trend_spearman": result.get("trend_spearman", math.nan),
                        "formation_tie_count": result.get("formation_tie_count", math.nan),
                    }
                )
    for code in set(periods_by_code) - set(paths):
        for period in periods_by_code[code]:
            for candidate in CANDIDATES:
                observations.append(
                    {
                        "period_index": period,
                        "signal_as_of_date": signal_lookup[period],
                        "stock_code": code,
                        "candidate": candidate,
                        "valid_50d": False,
                    }
                )
    market = pd.concat(market_rows, ignore_index=True).groupby("trade_date", as_index=False).agg(
        market_total_amount=("amount", "sum"), participants=("amount", "size")
    )
    market = pd.DataFrame({"trade_date": needed_dates}).merge(market, on="trade_date", how="left")
    market[["market_total_amount", "participants"]] = market[
        ["market_total_amount", "participants"]
    ].fillna(0)
    return pd.DataFrame(observations), pd.DataFrame(profiles), market


def build_counts(states: pd.DataFrame, observations: pd.DataFrame) -> pd.DataFrame:
    merged = observations.merge(
        states[["period_index", "stock_code", "RETURN_STATE"]],
        on=["period_index", "stock_code"],
        how="left",
        validate="many_to_one",
    )
    rows = []
    members = states.groupby("period_index")["stock_code"].size()
    for candidate in CANDIDATES:
        part = merged.loc[merged["candidate"].eq(candidate)]
        valid = part.loc[part["valid_50d"]]
        counts = valid.groupby("period_index")["stock_code"].size()
        for period in range(1, 57):
            rows.append(
                {
                    "row_type": "period_coverage",
                    "candidate": candidate,
                    "period_index": period,
                    "return_state": "ALL",
                    "shock_state": "ALL",
                    "signal_members": int(members.loc[period]),
                    "count": int(counts.get(period, 0)),
                    "percentage": counts.get(period, 0) / members.loc[period],
                }
            )
        shock = valid.groupby(["period_index", "shock_state"]).size()
        cells = valid.groupby(["period_index", "RETURN_STATE", "shock_state"]).size()
        for period in range(1, 57):
            valid_count = int(counts.get(period, 0))
            for shock_state in SHOCK_STATES:
                count = int(shock.get((period, shock_state), 0))
                rows.append(
                    {
                        "row_type": "period_shock_state",
                        "candidate": candidate,
                        "period_index": period,
                        "return_state": "ALL",
                        "shock_state": shock_state,
                        "signal_members": valid_count,
                        "count": count,
                        "percentage": count / valid_count if valid_count else math.nan,
                    }
                )
                for return_state in RETURN_STATES:
                    rows.append(
                        {
                            "row_type": "period_3x3_cell",
                            "candidate": candidate,
                            "period_index": period,
                            "return_state": return_state,
                            "shock_state": shock_state,
                            "signal_members": valid_count,
                            "count": int(cells.get((period, return_state, shock_state), 0)),
                            "percentage": math.nan,
                        }
                    )
    return pd.DataFrame(rows)


def build_inventory(profiles: pd.DataFrame, market: pd.DataFrame) -> pd.DataFrame:
    amount_stocks = int(profiles["amount_valid_rows"].gt(0).sum())
    cap_stocks = int(profiles["cap_valid_rows"].gt(0).sum())
    date_min = profiles["date_min"].min()
    date_max = profiles["date_max"].max()
    raw_rows = int(profiles["rows"].sum())
    amount_rows = int(profiles["amount_valid_rows"].sum())
    cap_rows = int(profiles["cap_valid_rows"].sum())
    market_min = int(market["participants"].min())
    market_median = float(market["participants"].median())
    records = [
        ["daily_share_volume", "volume", "canonical broader-A raw cache", "shares; unit unavailable", 0, "", "", 1.0, False, True, "No canonical broader-A volume field; five legacy public-clean files are insufficient"],
        ["daily_amount", "amount", "data/cache/price/*.csv", "CNY inferred; not source-certified", amount_stocks, date_min, date_max, 1 - amount_rows / raw_rows if raw_rows else 1, True, False, "Direct trading-value field used by existing AMOUNT_MEAN20"],
        ["daily_total_market_cap", "total_market_cap", "data/cache/price/*.csv", "CNY inferred; not source-certified", cap_stocks, date_min, date_max, 1 - cap_rows / raw_rows if raw_rows else 1, True, False, "Daily historical dated; vintage lineage not audited"],
        ["daily_value_turnover", "amount / total_market_cap", "constructed from data/cache/price/*.csv", "dimensionless", min(amount_stocks, cap_stocks), date_min, date_max, math.nan, True, False, "Turnover-like; not D04 firm-specific volume or true turnover"],
        ["market_total_amount", "sum(amount)", "cross-sectional aggregate of canonical broader-A raw cache", "CNY inferred", int(market["participants"].max()), market["trade_date"].min(), market["trade_date"].max(), math.nan, True, False, f"Participant count median={market_median:.0f}, minimum={market_min}; early history limitation retained"],
        ["market_total_volume", "sum(volume)", "unavailable", "shares", 0, "", "", 1.0, False, True, "Cannot construct without broad daily share volume"],
        ["formation_day_qfq_return", "qfq_close_t / qfq_close_t-1 - 1", "data/processed/h5a_broader_a_daily_v1/*.csv", "decimal return", 5180, "2020-12-28", "2026-06-16", math.nan, True, False, "Signal-time QFQ closes support a future normal-formation-return robustness audit"],
        ["price_limit_and_trade_status", "limit/ST/tradability fields", "unavailable; raw cache has OHLC only", "status", 0, "", "", 1.0, False, True, "OHLC cannot certify limit status, ST status or next-day tradability"],
    ]
    return pd.DataFrame(
        records,
        columns=[
            "candidate",
            "field_or_formula",
            "path",
            "unit",
            "stock_coverage",
            "date_min",
            "date_max",
            "missing_rate",
            "signal_time_legal",
            "network_download_needed",
            "notes",
        ],
    )


def _summary_stats(counts: pd.DataFrame, candidate: str) -> dict:
    coverage = counts.loc[
        counts["row_type"].eq("period_coverage") & counts["candidate"].eq(candidate),
        "percentage",
    ]
    cells = counts.loc[
        counts["row_type"].eq("period_3x3_cell") & counts["candidate"].eq(candidate),
        "count",
    ]
    return {
        "coverage_median": coverage.median(),
        "coverage_min": coverage.min(),
        "coverage_p10": coverage.quantile(0.10),
        "cell_median": cells.median(),
        "cell_min": cells.min(),
        "cell_p10": cells.quantile(0.10),
    }


def write_report(
    path: Path,
    inventory: pd.DataFrame,
    observations: pd.DataFrame,
    counts: pd.DataFrame,
    market: pd.DataFrame,
) -> None:
    amount = _summary_stats(counts, CANDIDATES[0])
    vt = _summary_stats(counts, CANDIDATES[1])
    valid = observations.loc[observations["valid_50d"]]
    trend = valid.loc[valid["shock_state"].isin(["LOW_SHOCK", "HIGH_SHOCK"])].groupby(
        ["candidate", "shock_state"]
    )["trend_spearman"].agg(
        observations="size",
        median="median",
        strong_trend_share=lambda values: values.abs().ge(0.50).mean(),
    ).reset_index()
    state_summary = counts.loc[counts["row_type"].eq("period_shock_state")].groupby(
        ["candidate", "shock_state"]
    ).agg(
        median_count=("count", "median"),
        minimum_count=("count", "min"),
        maximum_count=("count", "max"),
        median_percentage=("percentage", "median"),
    ).reset_index()
    participants = market["participants"]
    low_participation_days = int(participants.lt(participants.median() * 0.80).sum())
    report = f"""# Hypothesis 6 — Abnormal Trading Activity Data Readiness Audit

## Technical summary

**H6_DATA_READY_WITH_EARLY_WINDOW_AND_EXECUTION_LIMITATIONS.** Local data can construct exact 50-market-day own-history shocks for daily amount and daily value turnover without a network download. Canonical broader-A share volume is unavailable, so a direct D04-style share-volume shock is not ready. Both usable candidates have median Primary-period coverage of **{amount['coverage_median']:.2%}**; periods 1 and 2 have only about 1.7% coverage because their 50-day windows predate broad raw-activity history.

The recommended Primary measurement candidate is `DAILY_AMOUNT_OWN_HISTORY_RANK`: it is the most direct broadly available trading-activity field, and own-stock ranking removes permanent cross-stock scale without importing the market-cap lineage and strong VOL20 exposure already documented for VT. This recommendation uses only definition and signal-time data quality, never future performance. `MARKET_NORMALIZED_AMOUNT_OWN_HISTORY_RANK` is the secondary robustness candidate, subject to the same early-history limitation.

## Amount and VT are ready; share volume is not

{inventory.to_markdown(index=False)}

The raw `turnover` column is not selected because its denominator and unit are undocumented. VT is `Amount / TotalMarketCap`, not D04 firm-specific volume and not true shares turnover.

## Exact 50-day coverage retains two early-period shortfalls

| candidate | median coverage | minimum coverage | p10 coverage | median 3×3 cell | minimum 3×3 cell | p10 3×3 cell |
|---|---:|---:|---:|---:|---:|---:|
| Amount own-history rank | {amount['coverage_median']:.2%} | {amount['coverage_min']:.2%} | {amount['coverage_p10']:.2%} | {amount['cell_median']:.1f} | {amount['cell_min']:.0f} | {amount['cell_p10']:.1f} |
| VT own-history rank | {vt['coverage_median']:.2%} | {vt['coverage_min']:.2%} | {vt['coverage_p10']:.2%} | {vt['cell_median']:.1f} | {vt['cell_min']:.0f} | {vt['cell_p10']:.1f} |

Every window is the formation day plus its preceding 49 exact CSI300 market dates. Missing observations invalidate the stock-period; no earlier-date substitution or fill is used. The deterministic ordinal tie rule sorts by `(activity value ascending, trade_date ascending)`, then labels ranks 1–5 LOW_SHOCK, 46–50 HIGH_SHOCK and the remainder NORMAL.

## Shock states remain populated outside the two early incomplete periods

{state_summary.to_markdown(index=False, floatfmt='.4f')}

The full 56-period minimum includes the two early incomplete windows and is therefore not evidence that the shock rule itself produces empty states. Counts, percentages and all period × RETURN_STATE × shock-state cells are retained in `h6_shock_state_counts.csv` for review.

## Own-history extremes often coexist with local trends

{trend.to_markdown(index=False, floatfmt='.4f')}

`strong_trend_share` is the descriptive share with `|Spearman(activity, time index)| >= 0.50`. This does not change the shock rule, but it makes slow local trend a worthwhile preregistered robustness concern. No recent-weighted, z-score or residual alternative is constructed here.

## Market-wide amount normalization is feasible with an early-history limitation

Across the required calendar span, daily broader-A amount aggregation has median participant count **{participants.median():.0f}**, minimum **{participants.min():.0f}**, and **{low_participation_days}** dates below 80% of the median participant count. Market-wide share-volume normalization is not feasible because canonical share volume is absent. The current-universe aggregate is not point-in-time and must retain survivorship/composition limitations.

## Formation-return robustness is supported; execution research is not

Daily QFQ closes can construct a formation-day return and locate it within a prior signal-time return history. This audit does not create a normal-return subsample. Reliable limit-up/down, ST, suspension/trading-status and next-day tradability fields are absent; OHLC alone is not an authoritative substitute.

```text
mechanism_research_ready=true_with_periods_1_2_50d_history_limitation
execution_research_ready=false
```

Formation-day activity is observable only after the close, and the locked calendar supports evaluation beginning no earlier than the next market day. No future outcome is read in this audit.

## Measurement recommendation

- **Primary:** `DAILY_AMOUNT_OWN_HISTORY_RANK`. It is directly observed, broadly covered and closer to abnormal trading activity than a market-cap-normalized proxy whose denominator adds lineage and covariate exposure.
- **Secondary robustness:** `MARKET_NORMALIZED_AMOUNT_OWN_HISTORY_RANK`, using stock amount divided by the same-day broader-A total amount before applying the same fixed 50-day own-history rank. It is closer to D04's market-normalization idea but inherits current-universe aggregation and early-history limitations.
- **Additional named candidate:** `DAILY_VT_OWN_HISTORY_RANK` remains feasible but is not selected as Primary; it is turnover-like rather than D04 firm-specific volume and retains size, VOL20 and market-cap-lineage limitations.

No performance comparison was used to make this recommendation. A future H6 preregistration must decide whether to retain all locked periods or formally treat periods 1 and 2 before opening any outcome.

## Further questions

- Can a source-certified share-volume field be added in a separate future data task if closer D04 replication becomes important?
- Should a future H6 contract include a non-result-driven slow-trend robustness diagnostic?
- Is execution research needed? If so, authoritative historical limit/ST/tradability fields are a separate data requirement.

## Audit identity

{'; '.join(f'{key}={str(value).lower() if isinstance(value, bool) else value}' for key, value in IDENTITY.items())}
"""
    path.write_text(report, encoding="utf-8")


def run(root: Path) -> None:
    root = root.resolve()
    output = root / OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    states = _load_states(root)
    windows = _windows(root, states)
    observations, profiles, market = _scan_local_daily(root, states, windows)
    counts = build_counts(states, observations)
    inventory = build_inventory(profiles, market)
    inventory.to_csv(output / "h6_activity_measurement_inventory.csv", index=False, encoding="utf-8-sig")
    counts.to_csv(output / "h6_shock_state_counts.csv", index=False, encoding="utf-8-sig")
    write_report(
        output / "h6_abnormal_activity_data_readiness.md",
        inventory,
        observations,
        counts,
        market,
    )
    print("H6_DATA_READINESS_COMPLETE future_return_accessed=false")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    run(args.project_root)


if __name__ == "__main__":
    main()
