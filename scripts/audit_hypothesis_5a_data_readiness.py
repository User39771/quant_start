# ruff: noqa: E501
"""Read-only data-readiness audit for Hypothesis 5A; no outcome analysis."""

from __future__ import annotations

import argparse
import math
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = Path("reports/hypothesis_5a_readiness")
PROJECT_DATE = date(2026, 8, 13)
FORBIDDEN = ("prospective", "final_test")


def guarded_read_csv(root: Path, relative: str, **kwargs) -> pd.DataFrame:
    normalized = relative.replace("\\", "/").lower()
    if any(token in normalized for token in FORBIDDEN):
        raise PermissionError(f"forbidden_path={relative}")
    path = (root / relative).resolve()
    if root.resolve() not in path.parents:
        raise PermissionError(f"outside_project={relative}")
    return pd.read_csv(path, **kwargs)


def code6(values: pd.Series) -> pd.Series:
    return values.astype(str).str.replace(r"\.0$", "", regex=True).str.zfill(6)


def bool_series(values: pd.Series) -> pd.Series:
    return values.astype(str).str.lower().map({"true": True, "false": False}).fillna(False)


def exact_rolling_mean(
    panel: pd.DataFrame, calendar: pd.DatetimeIndex, signal_dates: dict[int, pd.Timestamp]
) -> pd.DataFrame:
    lookup = panel.set_index(["stock_code", "trade_date"])["amount"]
    stocks = sorted(panel["stock_code"].unique())
    rows = []
    for period, signal_date in signal_dates.items():
        position = calendar.get_indexer([signal_date])[0]
        dates = calendar[max(0, position - 19) : position + 1]
        for stock in stocks:
            values = lookup.reindex(pd.MultiIndex.from_product([[stock], dates]))
            finite_positive = np.isfinite(values) & values.gt(0)
            rows.append(
                {
                    "period_index": period,
                    "stock_code": stock,
                    "amount_mean_20": (
                        float(values.mean())
                        if len(dates) == 20 and finite_positive.all()
                        else math.nan
                    ),
                }
            )
    return pd.DataFrame(rows)


def stable_groups(frame: pd.DataFrame, column: str, groups: int) -> pd.Series:
    ordered = frame.sort_values([column, "stock_code"], ascending=[True, True])
    labels = pd.Series(index=frame.index, dtype="Int64")
    for number, indices in enumerate(np.array_split(ordered.index.to_numpy(), groups), 1):
        labels.loc[indices] = number
    return labels


def cell_sizes(signal: pd.DataFrame, groups: int, scope: str) -> pd.DataFrame:
    rows = []
    for period, period_frame in signal.groupby("period_index", sort=True):
        valid = period_frame.loc[
            period_frame["signal_sample_member"]
            & np.isfinite(period_frame["RETURN_60"])
            & np.isfinite(period_frame["amount_mean_20"])
        ].copy()
        target_count = int(period_frame["signal_sample_member"].sum())
        if target_count == 0 or len(valid) / target_count < 0.9 or len(valid) < groups**2:
            continue
        valid["return_group"] = stable_groups(valid, "RETURN_60", groups)
        valid["activity_group"] = stable_groups(valid, "amount_mean_20", groups)
        for return_group in range(1, groups + 1):
            for activity_group in range(1, groups + 1):
                count = int(
                    (
                        valid["return_group"].eq(return_group)
                        & valid["activity_group"].eq(activity_group)
                    ).sum()
                )
                rows.append(
                    {
                        "scope": scope,
                        "state_structure": f"{groups}x{groups}",
                        "period_index": period,
                        "cell": f"R{return_group}_A{activity_group}",
                        "stock_count": count,
                    }
                )
    return pd.DataFrame(rows)


def inventory_row(root: Path, role: str, relative: str, fields: list[str], notes: str) -> dict:
    frame = guarded_read_csv(root, relative, nrows=0)
    full = guarded_read_csv(root, relative)
    date_columns = [name for name in full if "date" in name.lower()]
    dates = (
        pd.concat([pd.to_datetime(full[name], errors="coerce") for name in date_columns])
        if date_columns
        else pd.Series(dtype="datetime64[ns]")
    )
    return {
        "data_role": role,
        "file_path": relative,
        "rows": len(full),
        "date_min": dates.min(),
        "date_max": dates.max(),
        "key_columns": "stock_code;trade_date"
        if {"stock_code", "trade_date"}.issubset(frame)
        else "",
        "relevant_fields": ";".join(field for field in fields if field in frame.columns),
        "source": "local_project_artifact",
        "status": "AVAILABLE",
        "notes": notes,
    }


def run(root: Path) -> None:
    output = root / OUTPUT
    output.mkdir(parents=True, exist_ok=True)
    universe_path = "data/processed/research_universe_lowvol_freeze_20260711.csv"
    price_path = "data/processed/adjusted_price_panel_v1_2.csv"
    mom_path = "data/processed/mom60_factor_panel_v1_3.csv"
    lowvol_path = "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv"
    benchmark_path = "data/processed/hybrid_benchmark_panel_v1_5.csv"
    amount_report_path = "reports/liquidity_filter_amount_readiness_v1_6.csv"

    universe = guarded_read_csv(root, universe_path, dtype={"code": str})
    universe["code"] = code6(universe["code"])
    price = guarded_read_csv(root, price_path, dtype={"stock_code": str})
    price["stock_code"] = code6(price["stock_code"])
    price["trade_date"] = pd.to_datetime(price["trade_date"], errors="raise")
    if price.duplicated(["stock_code", "trade_date"]).any():
        raise ValueError("duplicate_price_key")
    price = price.sort_values(["stock_code", "trade_date"])
    mom_columns = [
        "period_index",
        "stock_code",
        "signal_as_of_date",
        "rebalance_date",
        "next_rebalance_date",
        "signal_sample_member",
        "mom60",
        "lookback_60_date",
    ]
    mom = guarded_read_csv(root, mom_path, usecols=mom_columns, dtype={"stock_code": str})
    mom["stock_code"] = code6(mom["stock_code"])
    mom["signal_sample_member"] = bool_series(mom["signal_sample_member"])
    for column in (
        "signal_as_of_date",
        "rebalance_date",
        "next_rebalance_date",
        "lookback_60_date",
    ):
        mom[column] = pd.to_datetime(mom[column], errors="coerce")
    mom = mom.rename(columns={"mom60": "RETURN_60"})
    if mom.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("duplicate_signal_key")
    if not (mom["signal_as_of_date"] < mom["rebalance_date"]).all():
        raise ValueError("invalid_signal_timing")
    benchmark = guarded_read_csv(root, benchmark_path, dtype={"benchmark_code": str})
    benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"], errors="raise")
    calendar = pd.DatetimeIndex(
        benchmark.loc[benchmark["benchmark_code"].astype(str).eq("000300"), "trade_date"]
        .drop_duplicates()
        .sort_values()
    )
    signal_dates = (
        mom[["period_index", "signal_as_of_date"]]
        .drop_duplicates()
        .set_index("period_index")["signal_as_of_date"]
        .to_dict()
    )
    amount = exact_rolling_mean(price, calendar, signal_dates)
    signal = mom.merge(amount, on=["period_index", "stock_code"], validate="one_to_one")

    inventory = [
        inventory_row(
            root,
            "frozen_theme_universe",
            universe_path,
            ["code", "theme"],
            "56-stock frozen current universe",
        ),
        inventory_row(
            root,
            "adjusted_price_amount",
            price_path,
            ["adjusted_close", "amount", "total_market_cap", "circulating_market_cap"],
            "historical_seen; amount available; no volume field",
        ),
        inventory_row(
            root,
            "return60_signal",
            mom_path,
            ["mom60", "signal_sample_member", "signal_as_of_date"],
            "signal fields only read; outcome columns excluded",
        ),
        inventory_row(
            root,
            "vol20_signal",
            lowvol_path,
            ["vol20", "baseline_eligible"],
            "LOWVOL-specific eligibility differs from Phase A",
        ),
        inventory_row(
            root,
            "market_calendar",
            benchmark_path,
            ["benchmark_code", "trade_date"],
            "CSI300 dates define exact windows",
        ),
        inventory_row(
            root,
            "amount_readiness",
            amount_report_path,
            ["complete_windows", "missing_windows"],
            "existing Hypothesis 3 readiness evidence",
        ),
    ]
    inventory.append(
        {
            "data_role": "broader_a_share_raw_cache",
            "file_path": "data/cache/price/*.csv",
            "rows": "not_loaded_in_audit",
            "date_min": "2021-03-22_typical",
            "date_max": "2026-06-16",
            "key_columns": "code;date",
            "relevant_fields": "close;amount;turnover;total_market_cap;circulating_market_cap",
            "source": "pipeline_manifest: local synced cache",
            "status": "PARTIAL_5197_FILES_UNADJUSTED",
            "notes": (
                "not suitable for returns without adjustment; turnover denominator lineage absent"
            ),
        }
    )
    pd.DataFrame(inventory).to_csv(output / "input_inventory.csv", index=False)

    share_rows = []
    for code in universe["code"]:
        for field, history, limitation in (
            (
                "total_shares_outstanding",
                True,
                "only inferable from market_cap/price; no effective/report dates",
            ),
            (
                "circulating_shares",
                True,
                "only inferable from circulating_market_cap/price; no effective/report dates",
            ),
            ("free_float_shares", False, "field absent"),
        ):
            stock = price.loc[price["stock_code"].eq(code)]
            share_rows.append(
                {
                    "stock_code": code,
                    "share_field": field,
                    "history_available": history,
                    "point_in_time_usable": False,
                    "first_date": stock["trade_date"].min() if history else pd.NaT,
                    "last_date": stock["trade_date"].max() if history else pd.NaT,
                    "coverage_status": "HISTORICAL_BUT_NOT_POINT_IN_TIME" if history else "UNKNOWN",
                    "source": price_path if history else "",
                    "limitation": limitation,
                }
            )
    pd.DataFrame(share_rows).to_csv(output / "shares_outstanding_readiness.csv", index=False)

    proxy_rows = [
        {
            "proxy": "true_point_in_time_turnover",
            "definition": "traded_shares / point-in-time shares outstanding",
            "input_fields": "volume;dated shares outstanding",
            "lookback_requirement": "to be frozen by human",
            "signal_time_availability": False,
            "coverage": 0.0,
            "scale": "ratio",
            "known_size_exposure": "denominator-adjusted in principle",
            "known_price_exposure": "low in principle",
            "point_in_time_issue": "no auditable dated share-count history",
            "interpretation_limit": "not computable locally",
        },
        {
            "proxy": "raw_volume",
            "definition": "traded shares from AkShare daily price",
            "input_fields": "volume",
            "lookback_requirement": "candidate only; not frozen",
            "signal_time_availability": False,
            "coverage": "5 public-clean files only; not the 56-stock panel",
            "scale": "shares",
            "known_size_exposure": "high",
            "known_price_exposure": "lower than amount",
            "point_in_time_issue": "none for raw daily volume; coverage insufficient",
            "interpretation_limit": "not turnover and not theme-panel ready",
        },
        {
            "proxy": "AMOUNT_MEAN_20",
            "definition": "mean amount over exact 20 CSI300 market dates through signal date",
            "input_fields": "amount",
            "lookback_requirement": "20 market dates; no fill",
            "signal_time_availability": True,
            "coverage": "computed below",
            "scale": "CNY inferred, source unit not certified",
            "known_size_exposure": "high",
            "known_price_exposure": "high",
            "point_in_time_issue": "daily observations are historical",
            "interpretation_limit": "not D03 turnover; mixes activity, price and size",
        },
        {
            "proxy": "amount_percentile",
            "definition": "cross-sectional percentile rank of AMOUNT_MEAN_20",
            "input_fields": "AMOUNT_MEAN_20",
            "lookback_requirement": "same exact 20 dates",
            "signal_time_availability": True,
            "coverage": "same as AMOUNT_MEAN_20",
            "scale": "unitless rank",
            "known_size_exposure": "ranking does not remove size exposure",
            "known_price_exposure": "ranking does not remove price exposure",
            "point_in_time_issue": "none beyond amount source",
            "interpretation_limit": "state proxy only; not turnover",
        },
    ]
    pd.DataFrame(proxy_rows).to_csv(output / "trading_activity_proxy_inventory.csv", index=False)

    period_rows = []
    horizon_rows = []
    close_lookup = price.set_index(["stock_code", "trade_date"])["adjusted_close"]
    for period, group in signal.groupby("period_index", sort=True):
        targets = group.loc[group["signal_sample_member"]]
        return_valid = np.isfinite(targets["RETURN_60"])
        amount_valid = np.isfinite(targets["amount_mean_20"])
        row = {
            "period_index": period,
            "signal_as_of_date": group["signal_as_of_date"].iloc[0],
            "signal_target_count": len(targets),
            "return60_available_count": int(return_valid.sum()),
            "return60_coverage": float(return_valid.mean()) if len(targets) else 0,
            "amount20_available_count": int(amount_valid.sum()),
            "amount20_coverage": float(amount_valid.mean()) if len(targets) else 0,
            "true_turnover_joint_count": 0,
            "true_turnover_joint_coverage": 0.0,
        }
        rebalance = group["rebalance_date"].iloc[0]
        start_position = calendar.get_indexer([rebalance])[0]
        for horizon in (20, 60, 120):
            endpoint_position = start_position + horizon
            endpoint = (
                calendar[endpoint_position] if 0 <= endpoint_position < len(calendar) else pd.NaT
            )
            if pd.isna(endpoint):
                endpoint_valid = pd.Series(False, index=targets.index)
            else:
                keys = pd.MultiIndex.from_arrays([targets["stock_code"], [endpoint] * len(targets)])
                endpoint_values = close_lookup.reindex(keys)
                endpoint_valid = pd.Series(
                    (np.isfinite(endpoint_values) & endpoint_values.gt(0)).to_numpy(),
                    index=targets.index,
                )
            count = int(endpoint_valid.sum())
            row[f"horizon_{horizon}d_endpoint"] = endpoint
            row[f"horizon_{horizon}d_available_count"] = count
            row[f"horizon_{horizon}d_coverage"] = count / len(targets) if len(targets) else 0
            row[f"horizon_{horizon}d_amount_joint_count"] = int(
                (return_valid & amount_valid & endpoint_valid).sum()
            )
        period_rows.append(row)
    period_detail = pd.DataFrame(period_rows)
    period_detail.to_csv(output / "signal_period_readiness.csv", index=False)

    for horizon in (20, 60, 120):
        endpoint_column = f"horizon_{horizon}d_endpoint"
        coverage_column = f"horizon_{horizon}d_coverage"
        usable = period_detail.loc[period_detail[endpoint_column].notna()]
        horizon_rows.append(
            {
                "horizon": f"{horizon}D",
                "valid_periods": int((usable[coverage_column] > 0).sum()),
                "median_stock_coverage": usable[coverage_column].median(),
                "minimum_stock_coverage": usable[coverage_column].min(),
                "first_usable_period": usable.loc[
                    usable[coverage_column] > 0, "period_index"
                ].min(),
                "last_usable_period": usable.loc[usable[coverage_column] > 0, "period_index"].max(),
                "major_missingness_reason": "endpoint stock-date absent; no fill",
            }
        )
    pd.DataFrame(horizon_rows).to_csv(output / "future_horizon_readiness.csv", index=False)

    joint_rows = []
    for activity, activity_column in (
        ("true_turnover", None),
        ("volume_proxy", None),
        ("amount_proxy", "amount20_available_count"),
    ):
        for horizon in (20, 60, 120):
            counts = []
            coverages = []
            valid_periods = 0
            for _, row in period_detail.iterrows():
                if activity_column is None:
                    joint = 0
                else:
                    joint = int(row[f"horizon_{horizon}d_amount_joint_count"])
                counts.append(joint)
                coverage = joint / row["signal_target_count"] if row["signal_target_count"] else 0
                coverages.append(coverage)
                valid_periods += joint >= 25 and coverage >= 0.8
            joint_rows.append(
                {
                    "activity_definition": activity,
                    "future_horizon": f"{horizon}D",
                    "candidate_periods": len(period_detail),
                    "valid_periods": valid_periods,
                    "median_joint_stock_count": float(np.median(counts)),
                    "minimum_joint_stock_count": min(counts),
                    "median_coverage": float(np.median(coverages)),
                }
            )
    pd.DataFrame(joint_rows).to_csv(output / "joint_readiness_matrix.csv", index=False)

    theme_cells = []
    full_codes = set(universe["code"])
    theme_cells.extend(
        cell_sizes(signal.loc[signal["stock_code"].isin(full_codes)], 2, "full_theme_pool").to_dict(
            "records"
        )
    )
    theme_cells.extend(
        cell_sizes(signal.loc[signal["stock_code"].isin(full_codes)], 3, "full_theme_pool").to_dict(
            "records"
        )
    )
    for theme in ("AI", "商业航天"):
        codes = set(universe.loc[universe["theme"].str.contains(theme, regex=False), "code"])
        theme_cells.extend(
            cell_sizes(signal.loc[signal["stock_code"].isin(codes)], 2, theme).to_dict("records")
        )
    cells = pd.DataFrame(theme_cells)
    summary = (
        cells.groupby(["scope", "state_structure", "cell"])["stock_count"]
        .agg(
            median="median",
            p10=lambda values: values.quantile(0.10),
            minimum="min",
            periods_with_count_lt_3=lambda values: int((values < 3).sum()),
            periods_with_count_lt_5=lambda values: int((values < 5).sum()),
        )
        .reset_index()
    )
    cells = cells.merge(summary, on=["scope", "state_structure", "cell"], validate="many_to_one")
    cells.to_csv(output / "theme_pool_state_cell_sizes.csv", index=False)

    latest_adjusted = price["trade_date"].max().date()
    broader = """# Broader A-share Universe Readiness

**Status: PARTIALLY_READY.** The local cache contains 5,197 per-stock price files and the pipeline
manifest identifies 5,195 A-share symbols over a requested 2019-01-01 to 2026-06-12 range. Typical
cached histories begin 2021-03-22 and end 2026-06-16. The cache includes close, amount, a vendor
turnover field and market-cap fields, but the pipeline explicitly marks prices as unadjusted and
the attempted sandbox refresh produced no completed broad-market dataset.

It therefore provides inventory and possible activity-source groundwork, not a ready H5A return
panel. Historical point-in-time share-count records with effective/report dates remain absent;
the current-stock-file universe also carries survivorship/current-universe risk. A broader study
would require a frozen historical universe, adjusted prices, verified volume units, dated share
capital history and documented corporate-action handling. No data was downloaded in this audit.
"""
    (output / "broader_universe_readiness.md").write_text(broader, encoding="utf-8")

    full_2 = cells.loc[(cells.scope == "full_theme_pool") & (cells.state_structure == "2x2")]
    full_3 = cells.loc[(cells.scope == "full_theme_pool") & (cells.state_structure == "3x3")]
    theme_summary = (
        cells.loc[cells.scope.isin(["AI", "商业航天"])]
        .groupby("scope")["stock_count"]
        .agg(["median", "min"])
    )
    horizons = pd.DataFrame(horizon_rows)
    horizon_table = "\n".join(
        f"| {row.horizon} | {row.valid_periods} | {row.median_stock_coverage:.2%} | "
        f"{row.minimum_stock_coverage:.2%} |"
        for row in horizons.itertuples()
    )
    decision = f"""# Hypothesis 5A Human Decision Table

## Decision 1 — Trading activity variable

| Option | Data support | Advantages | Limitations | D03 comparability |
|---|---|---|---|---|
| A. True point-in-time turnover | Not supported locally | Conceptually closest | No dated shares; volume incomplete | Potentially closest, unavailable |
| B. Volume-based proxy | Insufficient for 56 stocks | Avoids price multiplication | Five clean files; size exposure | Low |
| C. Amount-based proxy | Exact 20-day history | Existing high-coverage contract | Mixes activity, price and size | Low; not turnover |
| D. Pause H5A | Always feasible | Avoids proxy substitution | Research remains untested | Not applicable |

## Decision 2 — Research universe

| Option | Availability evidence |
|---|---|
| A. Current 56-stock theme pool | Adjusted panel ready; current-universe limitation remains |
| B. Broader A-share cross-section | PARTIALLY_READY; adjusted history and PIT inputs not ready |
| C. Theme case study plus broader methods study | Requires preparing the broader panel first |

## Decision 3 — State granularity

| Option | Signal-only cell-size evidence |
|---|---|
| A. 2x2 | Median cell {full_2.stock_count.median():.1f}; minimum {full_2.stock_count.min()} |
| B. 3x3 | Median cell {full_3.stock_count.median():.1f}; minimum {full_3.stock_count.min()} |

## Decision 4 — Future horizons

| Horizon | Valid periods | Median stock coverage | Minimum stock coverage |
|---|---:|---:|---:|
{horizon_table}

These are availability facts only. No option is selected here.
"""
    (output / "human_decision_table.md").write_text(decision, encoding="utf-8")

    return_ready = (period_detail["return60_available_count"] >= 25) & (
        period_detail["return60_coverage"] >= 0.8
    )
    return_periods = int(return_ready.sum())
    return_min = period_detail.loc[return_ready, "return60_coverage"].min()
    amount_periods = int((period_detail["amount20_coverage"] >= 0.9).sum())
    stale_days = (PROJECT_DATE - latest_adjusted).days
    report = f"""# Hypothesis 5A — Trading-Activity State and Reversal-Timing Data Readiness Audit

```text
audit_type=hypothesis_5a_data_readiness
research_execution=false
historical_outcome_analysis=false
alpha_claim_allowed=false
oos_claim_allowed=false
mcts_run=false
phase_b_run=false
```

## 1. Executive summary

True point-in-time turnover is **not ready**: traded-volume coverage is incomplete and no local
dataset provides historical shares outstanding together with auditable effective/report dates.
The daily vendor `turnover` field cannot repair that lineage gap. RETURN60 is ready with the known
current-universe limitation. AMOUNT_MEAN_20 is the only theme-panel-wide activity proxy currently
supported, but it is not turnover and embeds size and price exposure. This audit does not select it.

All three requested horizon endpoints can be inspected from existing adjusted prices. The 56-stock
pool is workable for coarse 2x2 availability cells, while 3x3 cells are materially thinner and a
D03-style 10x3 design is plainly incompatible with this cross-section. Commercial-space-only cells
are especially thin. The wider A-share cache is `PARTIALLY_READY`, not research-ready.

## 2. Research question and D03 distinction

H5A asks whether signal-time activity states alter later continuation/reversal timing among similar
past-return states. This audit examines inputs and sample sizes only. D03-style turnover requires
shares traded divided by contemporaneous shares outstanding. Amount and vendor turnover without
denominator lineage are not equivalent.

## 3. Data inventory and definitions

The frozen pool has {len(universe)} stocks. The authoritative signal-time return field is MOM60's
`mom60`, renamed here as RETURN60: signal-date adjusted close divided by the adjusted close 60 exact
market days earlier minus one. No fill is used. Activity availability is based on amount over the
20 exact CSI300 dates ending at the signal date. Future readiness uses only endpoint presence at
20, 60 and 120 market days after rebalance; no future-return values are calculated.

See `input_inventory.csv` for row counts, fields, dates and lineage.

## 4. Point-in-time shares and true turnover are not ready

Daily total/circulating market-cap fields exist, so share counts can be algebraically inferred, but
there are no share-capital effective dates, report dates, announcement dates or revision history.
That is `HISTORICAL_BUT_NOT_POINT_IN_TIME`, not a usable denominator. Free-float shares are absent.
Consequently `true_turnover_ready=false`, reason `NO_POINT_IN_TIME_SHARES`; per-period joint true
turnover coverage is zero under an auditable definition.

## 5. Proxy inventory leaves an explicit human choice

Raw volume exists only in five public-clean files, not across the theme panel. AMOUNT_MEAN_20 passes
the existing 90% availability threshold in {amount_periods}/57 periods, but amount is denominated in
currency and co-moves mechanically with price and company scale. An amount percentile removes units,
not those exposures. No proxy is approved by this audit.

## 6. RETURN60 is ready with limitations

`RETURN60_READY_WITH_LIMITATIONS`: {return_periods}/57 periods contain signal targets with RETURN60;
the first three periods lack the exact historical endpoint. Across usable periods the minimum
stock coverage is {return_min:.2%}. Phase A and MCTS use the same source definition. The signal is
point-in-time, but the frozen 56-stock universe is a current-universe historical study rather than
a historical point-in-time constituent universe.

## 7. Future endpoint availability

{horizons.to_markdown(index=False)}

These counts describe adjusted-close endpoint presence only. They do not compare horizon returns or
identify a preferred horizon.

## 8. Joint readiness

`joint_readiness_matrix.csv` intersects RETURN60, activity availability and endpoint availability
without calculating returns. True turnover and volume-proxy rows remain zero because their required
local inputs are not ready; amount-proxy rows are availability diagnostics, not approval.

## 9. Theme-pool state cells

For the full pool, 2x2 cells have an across-cell/period median of
{full_2.stock_count.median():.1f} stocks and minimum {full_2.stock_count.min()}; 3x3 cells have median
{full_3.stock_count.median():.1f} and minimum {full_3.stock_count.min()}. A 10x3 design would average
fewer than two stocks per cell even before irregular intersections, so it is not credible here.
These partitions use deterministic signal-only ordering and exist solely to measure cell sizes.

AI's median 2x2 cell is {theme_summary.loc["AI", "median"]:.1f} and its minimum is
{theme_summary.loc["AI", "min"]}; commercial space's median is
{theme_summary.loc["商业航天", "median"]:.1f} and minimum {theme_summary.loc["商业航天", "min"]}.
Commercial-space-specific H5A therefore has `theme_specific_analysis_low_power=true`.

## 10. Broader A-share readiness and staleness

The local cache contains 5,197 stock files, but its documented prices are unadjusted and the later
sandbox refresh did not complete. It also lacks a historical PIT universe and dated share counts.
Status: `PARTIALLY_READY`.

The theme adjusted/amount panel ends {latest_adjusted}; it is {stale_days} days behind the project
date. The benchmark calendar extends to 2026-07-10. This staleness does not invalidate the locked
historical readiness window, but it is insufficient for a new prospective study and was not refreshed.

## 11. What cannot be claimed

No state-conditioned return, RankIC, continuation/reversal spread, transaction cost, Sharpe, MDD,
p-value, Alpha, strategy or best proxy/horizon result was calculated. Readiness is not a hypothesis
result and this is not a Lee–Swaminathan replication.

## 12. Human decisions and next step

The user must decide: (1) activity variable, (2) universe, (3) 2x2 versus 3x3 granularity, and
(4) which of 20D/60D/120D to preregister. See `human_decision_table.md`. After those choices, a
separate H5A preregistration would be required before any outcome analysis.

## Limitations and QA

Stock codes were normalized to six digits; signal and price keys are unique; signal dates precede
future endpoints; exact windows use no fill. MOM outcome columns were excluded at read time. Cell
sizes use signal fields only. No MCTS or Phase B runner was invoked.
"""
    (output / "hypothesis_5a_data_readiness_audit.md").write_text(report, encoding="utf-8")
    print("hypothesis_5a_readiness completed; outcome_analysis=false; mcts=false; phase_b=false")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=ROOT)
    args = parser.parse_args()
    run(args.project_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
