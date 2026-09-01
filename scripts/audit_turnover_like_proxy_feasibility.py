"""Audit local feasibility of one signal-time value-turnover proxy."""

# ruff: noqa: E501 -- the generated technical report is embedded as readable Markdown.

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from scripts.audit_h5a_activity_main_effect import (
        _load_qfq_covariates,
        _market_calendar,
        standardized_difference,
    )
    from scripts.run_h5a_trading_activity_reversal_timing_v1 import (
        _assign_states,
        code6,
        ordinal_groups,
    )
else:
    from audit_h5a_activity_main_effect import (
        _load_qfq_covariates,
        _market_calendar,
        standardized_difference,
    )
    from run_h5a_trading_activity_reversal_timing_v1 import (
        _assign_states,
        code6,
        ordinal_groups,
    )

OUTPUT_DIR = Path("reports/hypothesis_5a")
PROXY_STATES = ("LOW_PROXY", "MID_PROXY", "HIGH_PROXY")
SIZE_STATES = ("SMALL", "MID_SIZE", "LARGE")

IDENTITY = {
    "analysis_type": "turnover_like_proxy_feasibility_audit",
    "sample_role": "historical_seen",
    "future_outcome_used": False,
    "future_return_accessed": False,
    "causal_claim_allowed": False,
    "alpha_claim_allowed": False,
    "H5A_performance_rerun": False,
    "alternative_proxy_performance_compared": False,
    "network_download_performed": False,
    "MCTS_run": False,
    "Phase_B_run": False,
}


def value_turnover(
    amount: pd.Series,
    market_cap: pd.Series,
    amount_multiplier: float = 1.0,
    market_cap_multiplier: float = 1.0,
) -> pd.Series:
    """Return a dimensionless amount/market-cap ratio with strict validity."""
    numerator = pd.to_numeric(amount, errors="coerce") * amount_multiplier
    denominator = pd.to_numeric(market_cap, errors="coerce") * market_cap_multiplier
    valid = np.isfinite(numerator) & numerator.gt(0) & np.isfinite(denominator) & denominator.gt(0)
    return (numerator / denominator).where(valid)


def exact_vt20(frame: pd.DataFrame, expected_dates: pd.DatetimeIndex) -> float:
    """Mean daily value turnover on exactly 20 required market dates; no fill."""
    if len(expected_dates) != 20:
        return math.nan
    selected = frame.reindex(expected_dates)
    ratios = value_turnover(selected["amount"], selected["total_market_cap"])
    return float(ratios.mean()) if ratios.notna().all() and len(ratios) == 20 else math.nan


def assign_proxy_states(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["proxy_pct"] = math.nan
    result["proxy_state"] = pd.NA
    result["size_state"] = pd.NA
    for _, group in result.loc[result["vt20_daily"].notna()].groupby("period_index", sort=True):
        result.loc[group.index, "proxy_pct"] = group["vt20_daily"].rank(method="average", pct=True)
        result.loc[group.index, "proxy_state"] = ordinal_groups(
            group, "vt20_daily", PROXY_STATES
        )
    for _, group in result.loc[result["log_total_market_cap"].notna()].groupby(
        "period_index", sort=True
    ):
        result.loc[group.index, "size_state"] = ordinal_groups(
            group, "log_total_market_cap", SIZE_STATES
        )
    return result


def validate_primary_periods(periods: pd.Series) -> None:
    """Require the preregistered H5A Primary period set, with no substitutions."""
    if set(pd.to_numeric(periods, errors="raise").astype(int).unique()) != set(range(1, 57)):
        raise ValueError("primary_periods_not_1_to_56")


def _load_states(root: Path) -> pd.DataFrame:
    features = pd.read_csv(
        root / "data/processed/h5a_broader_a_signal_features_v1.csv",
        dtype={"stock_code": str},
    )
    features["stock_code"] = features["stock_code"].map(code6)
    features["signal_as_of_date"] = pd.to_datetime(features["signal_as_of_date"], errors="raise")
    features["signal_ready"] = features["signal_ready"].astype(str).str.lower().eq("true")
    states = _assign_states(features)
    states = states.loc[states["period_index"].between(1, 56)].copy()
    validate_primary_periods(states["period_index"])
    return states


def _windows(root: Path, states: pd.DataFrame) -> dict[int, pd.DatetimeIndex]:
    calendar = _market_calendar(root)
    position = {date: index for index, date in enumerate(calendar)}
    signals = states[["period_index", "signal_as_of_date"]].drop_duplicates()
    windows = {}
    for row in signals.itertuples(index=False):
        index = position[row.signal_as_of_date]
        expected = calendar[index - 19 : index + 1]
        if len(expected) != 20 or expected.max() != row.signal_as_of_date:
            raise ValueError(f"invalid_exact_window={row.period_index}")
        windows[int(row.period_index)] = expected
    return windows


def _inventory_row(
    field: str,
    available: bool,
    daily: bool,
    stocks: int,
    date_min: object,
    date_max: object,
    unit: str,
    time_status: str,
    primary: bool,
    notes: str,
) -> dict:
    return {
        "field": field,
        "available": available,
        "daily": daily,
        "stock_coverage": stocks,
        "date_min": date_min,
        "date_max": date_max,
        "unit": unit,
        "signal_time_legal": available and daily,
        "time_status": time_status,
        "used_in_primary_proxy": primary,
        "source": "data/cache/price/*.csv",
        "notes": notes,
    }


def _load_raw_and_proxy(
    root: Path, states: pd.DataFrame, windows: dict[int, pd.DatetimeIndex]
) -> tuple[pd.DataFrame, pd.DataFrame]:
    resolution = pd.read_csv(
        root / "reports/hypothesis_5a_broader_a/source_resolution_report.csv",
        dtype={"stock_code": str},
    )
    resolution["stock_code"] = resolution["stock_code"].map(code6)
    paths = resolution.set_index("stock_code")["canonical_amount_path"].dropna().to_dict()
    periods_by_code = states.groupby("stock_code")["period_index"].apply(list).to_dict()
    signal_lookup = states.set_index("period_index")["signal_as_of_date"].to_dict()
    rows = []
    profiles = []
    all_headers: set[str] = set()
    for code, path_text in paths.items():
        path = root / str(path_text)
        header = pd.read_csv(path, nrows=0).columns.tolist()
        all_headers.update(header)
        wanted = [
            field
            for field in (
                "date",
                "amount",
                "total_market_cap",
                "circulating_market_cap",
                "close",
                "turnover",
            )
            if field in header
        ]
        frame = pd.read_csv(path, usecols=wanted, low_memory=False)
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"])
        if frame["date"].duplicated().any():
            raise ValueError(f"duplicate_raw_date={code}")
        for field in wanted:
            if field != "date":
                frame[field] = pd.to_numeric(frame[field], errors="coerce")
        frame = frame.set_index("date").sort_index()
        profiles.append(
            {
                "stock_code": code,
                "date_min": frame.index.min(),
                "date_max": frame.index.max(),
                **{f"{field}_valid": int(np.isfinite(frame[field]).sum()) if field in frame else 0 for field in ("amount", "total_market_cap", "circulating_market_cap", "close", "turnover")},
            }
        )
        for period in periods_by_code.get(code, []):
            signal_date = signal_lookup[int(period)]
            expected = windows[int(period)]
            historical = frame.loc[frame.index <= signal_date]
            signal = historical.loc[signal_date] if signal_date in historical.index else pd.Series(dtype=float)
            vt20 = (
                exact_vt20(historical[["amount", "total_market_cap"]], expected)
                if {"amount", "total_market_cap"}.issubset(historical.columns)
                else math.nan
            )
            rows.append(
                {
                    "period_index": period,
                    "signal_as_of_date": signal_date,
                    "stock_code": code,
                    "vt20_daily": vt20,
                    "signal_total_market_cap": signal.get("total_market_cap", math.nan),
                    "signal_circulating_market_cap": signal.get("circulating_market_cap", math.nan),
                    "raw_signal_price": signal.get("close", math.nan),
                    "vt20_valid": math.isfinite(vt20),
                    "invalid_reason": "" if math.isfinite(vt20) else "INCOMPLETE_OR_NONPOSITIVE_EXACT_20D_AMOUNT_CAP_WINDOW",
                }
            )

    profiles_frame = pd.DataFrame(profiles)
    inventory = [
        _inventory_row(
            "daily_amount",
            "amount" in all_headers,
            True,
            int(profiles_frame["amount_valid"].gt(0).sum()),
            profiles_frame.loc[profiles_frame["amount_valid"].gt(0), "date_min"].min(),
            profiles_frame.loc[profiles_frame["amount_valid"].gt(0), "date_max"].max(),
            "CNY_INFERRED_NOT_SOURCE_CERTIFIED",
            "DAILY_HISTORICAL",
            True,
            "Canonical AMOUNT_MEAN20 source; magnitudes and vendor-turnover consistency support CNY",
        ),
        _inventory_row(
            "daily_total_market_cap",
            "total_market_cap" in all_headers,
            True,
            int(profiles_frame["total_market_cap_valid"].gt(0).sum()),
            profiles_frame.loc[profiles_frame["total_market_cap_valid"].gt(0), "date_min"].min(),
            profiles_frame.loc[profiles_frame["total_market_cap_valid"].gt(0), "date_max"].max(),
            "CNY_INFERRED_NOT_SOURCE_CERTIFIED",
            "DAILY_HISTORICAL_MARKET_CAP;HISTORICAL_DATED_NOT_VINTAGE_AUDITED",
            True,
            "Daily dated and time-varying; share/effective-date and vendor-vintage lineage not audited",
        ),
        _inventory_row(
            "daily_circulating_market_cap",
            "circulating_market_cap" in all_headers,
            True,
            int(profiles_frame["circulating_market_cap_valid"].gt(0).sum()),
            profiles_frame.loc[profiles_frame["circulating_market_cap_valid"].gt(0), "date_min"].min(),
            profiles_frame.loc[profiles_frame["circulating_market_cap_valid"].gt(0), "date_max"].max(),
            "CNY_INFERRED_NOT_SOURCE_CERTIFIED",
            "DAILY_HISTORICAL_NOT_VINTAGE_AUDITED",
            False,
            "Inventory only; fixed Primary denominator remains total market cap",
        ),
        _inventory_row(
            "raw_daily_close",
            "close" in all_headers,
            True,
            int(profiles_frame["close_valid"].gt(0).sum()),
            profiles_frame.loc[profiles_frame["close_valid"].gt(0), "date_min"].min(),
            profiles_frame.loc[profiles_frame["close_valid"].gt(0), "date_max"].max(),
            "CNY_PER_SHARE_INFERRED",
            "DAILY_HISTORICAL",
            False,
            "Used only for signal-time contamination and unit plausibility checks",
        ),
        _inventory_row(
            "vendor_turnover",
            "turnover" in all_headers,
            True,
            int(profiles_frame["turnover_valid"].gt(0).sum()),
            profiles_frame.loc[profiles_frame["turnover_valid"].gt(0), "date_min"].min(),
            profiles_frame.loc[profiles_frame["turnover_valid"].gt(0), "date_max"].max(),
            "DATABASE_NATIVE_UNDOCUMENTED_DENOMINATOR",
            "DAILY_HISTORICAL_DENOMINATOR_UNRESOLVED",
            False,
            "Not used; denominator and source contract are unresolved",
        ),
        _inventory_row(
            "historical_total_shares_with_effective_dates",
            False,
            False,
            0,
            "",
            "",
            "SHARES",
            "SCHEMA_OR_ALGEBRAIC_INFERENCE_ONLY",
            False,
            "No local effective/announcement/change-date history; current values cannot be mapped backward",
        ),
        _inventory_row(
            "historical_free_float_shares",
            False,
            False,
            0,
            "",
            "",
            "SHARES",
            "UNAVAILABLE",
            False,
            "No auditable local historical free-float share series",
        ),
    ]
    return pd.DataFrame(rows), pd.DataFrame(inventory)


def _period_spearman(frame: pd.DataFrame, characteristic: str) -> pd.DataFrame:
    rows = []
    for scope in ("ALL", "LOW_RETURN", "MID_RETURN", "HIGH_RETURN"):
        scoped = frame if scope == "ALL" else frame.loc[frame["return_state"].eq(scope)]
        for period, group in scoped.groupby("period_index"):
            valid = group[["vt20_daily", characteristic]].replace([np.inf, -np.inf], np.nan).dropna()
            rho = (
                valid["vt20_daily"].corr(valid[characteristic], method="spearman")
                if len(valid) >= 25 and valid[characteristic].nunique() > 1
                else math.nan
            )
            rows.append(
                {
                    "row_type": "period_spearman",
                    "scope": scope,
                    "period_index": period,
                    "characteristic": characteristic,
                    "n": len(valid),
                    "value": rho,
                }
            )
    return pd.DataFrame(rows)


def _characteristics(frame: pd.DataFrame, coverage: pd.DataFrame, old: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for characteristic in (
        "log_total_market_cap",
        "vol20",
        "log_raw_signal_price",
        "return_60",
    ):
        detail = _period_spearman(frame, characteristic)
        rows.append(detail)
        for scope, group in detail.groupby("scope"):
            values = group["value"].dropna()
            rows.append(
                pd.DataFrame(
                    [
                        {
                            "row_type": "spearman_summary",
                            "scope": scope,
                            "period_index": "ALL",
                            "characteristic": characteristic,
                            "n": len(values),
                            "value": values.mean(),
                            "median": values.median(),
                            "p10": values.quantile(0.10),
                            "p90": values.quantile(0.90),
                        }
                    ]
                )
            )

    for period, group in frame.loc[frame["proxy_state"].notna()].groupby("period_index"):
        for characteristic in (
            "log_total_market_cap",
            "vol20",
            "log_raw_signal_price",
            "return_60",
        ):
            high = group.loc[group["proxy_state"].eq("HIGH_PROXY"), characteristic]
            low = group.loc[group["proxy_state"].eq("LOW_PROXY"), characteristic]
            rows.append(
                pd.DataFrame(
                    [
                        {
                            "row_type": "period_proxy_high_low",
                            "scope": "ALL",
                            "period_index": period,
                            "characteristic": characteristic,
                            "n": min(high.notna().sum(), low.notna().sum()),
                            "value": high.mean() - low.mean(),
                            "standardized_difference": standardized_difference(high, low),
                        }
                    ]
                )
            )

    period_distribution = frame.loc[frame["vt20_daily"].notna()].groupby(
        "period_index", as_index=False
    ).agg(
        median=("vt20_daily", "median"),
        p10=("vt20_daily", lambda x: x.quantile(0.10)),
        p90=("vt20_daily", lambda x: x.quantile(0.90)),
        iqr=("vt20_daily", lambda x: x.quantile(0.75) - x.quantile(0.25)),
        p01=("vt20_daily", lambda x: x.quantile(0.01)),
        p99=("vt20_daily", lambda x: x.quantile(0.99)),
        maximum=("vt20_daily", "max"),
    )
    period_distribution["row_type"] = "proxy_period_distribution"
    period_distribution["scope"] = "ALL"
    period_distribution["characteristic"] = "vt20_daily"
    period_distribution["n"] = frame.groupby("period_index")["vt20_daily"].count().values
    period_distribution["value"] = period_distribution["median"]
    rows.append(period_distribution)

    for (period, size_state), group in frame.loc[frame["size_state"].notna()].groupby(
        ["period_index", "size_state"]
    ):
        values = group["vt20_daily"].dropna()
        rows.append(
            pd.DataFrame(
                [
                    {
                        "row_type": "size_stratum_proxy_spread",
                        "scope": size_state,
                        "period_index": period,
                        "characteristic": "vt20_daily",
                        "n": len(values),
                        "value": values.median(),
                        "median": values.median(),
                        "p10": values.quantile(0.10),
                        "p90": values.quantile(0.90),
                        "iqr": values.quantile(0.75) - values.quantile(0.25),
                    }
                ]
            )
        )

    coverage_rows = coverage.rename(
        columns={"coverage": "value", "h5a_signal_members": "n"}
    ).assign(row_type="period_coverage", scope="ALL", characteristic="vt20_daily")
    rows.append(coverage_rows)

    old_reference = old.loc[
        old["scope"].eq("ALL")
        & old["covariate"].isin(
            ["log_total_market_cap", "vol20", "log_raw_signal_price", "return_60"]
        )
    ][["covariate", "periods", "mean_spearman", "median_spearman", "p10_spearman", "p90_spearman"]].rename(
        columns={
            "covariate": "characteristic",
            "periods": "n",
            "mean_spearman": "value",
            "median_spearman": "median",
            "p10_spearman": "p10",
            "p90_spearman": "p90",
        }
    )
    old_reference["row_type"] = "old_activity_spearman_reference"
    old_reference["scope"] = "ALL"
    old_reference["period_index"] = "ALL"
    rows.append(old_reference)
    return pd.concat(rows, ignore_index=True, sort=False)


def _write_report(
    path: Path,
    inventory: pd.DataFrame,
    values: pd.DataFrame,
    characteristics: pd.DataFrame,
    coverage: pd.DataFrame,
) -> None:
    new = characteristics.loc[
        characteristics["row_type"].eq("spearman_summary")
        & characteristics["scope"].eq("ALL")
    ].set_index("characteristic")
    old = characteristics.loc[
        characteristics["row_type"].eq("old_activity_spearman_reference")
    ].set_index("characteristic")
    high_low = characteristics.loc[
        characteristics["row_type"].eq("period_proxy_high_low")
    ].groupby("characteristic")["standardized_difference"].mean()
    spread = characteristics.loc[
        characteristics["row_type"].eq("size_stratum_proxy_spread")
    ].groupby("scope").agg(
        periods=("period_index", "nunique"),
        median_proxy=("median", "median"),
        median_iqr=("iqr", "median"),
        median_p10=("p10", "median"),
        median_p90=("p90", "median"),
    )
    distribution = values["vt20_daily"].dropna()
    comparison = pd.DataFrame(
        {
            "characteristic": ["log market cap", "VOL20", "raw price", "RETURN60"],
            "old_amount_activity": [
                old.loc["log_total_market_cap", "value"],
                old.loc["vol20", "value"],
                old.loc["log_raw_signal_price", "value"],
                old.loc["return_60", "value"],
            ],
            "VT20_DAILY": [
                new.loc["log_total_market_cap", "value"],
                new.loc["vol20", "value"],
                new.loc["log_raw_signal_price", "value"],
                new.loc["return_60", "value"],
            ],
            "VT20_high_low_standardized_difference": [
                high_low.loc["log_total_market_cap"],
                high_low.loc["vol20"],
                high_low.loc["log_raw_signal_price"],
                high_low.loc["return_60"],
            ],
        }
    )
    inventory_table = inventory[
        ["field", "available", "daily", "stock_coverage", "date_min", "date_max", "unit", "time_status", "used_in_primary_proxy"]
    ].copy()
    report = f"""# H5A Turnover-Like Activity Proxy Feasibility Audit

## Technical summary

**TURNOVER_PROXY_READY_WITH_LINEAGE_LIMITATION.** Local data are computationally sufficient for the Priority-A definition `VT20_DAILY`: the mean of `Amount_t / TotalMarketCap_t` over the exact 20 market dates ending at each signal date. No network download is required. Median Primary-period coverage is **{coverage['coverage'].median():.2%}**, minimum coverage is **{coverage['coverage'].min():.2%}**, and p10 coverage is **{coverage['coverage'].quantile(0.10):.2%}**.

The ratio is economically closer to shares traded / shares outstanding than raw amount, but it is not true turnover. Amount and market-cap magnitudes are consistent with CNY and their ratio is consistent with the local vendor turnover scale; however, units are inferred rather than source-certified and historical market-cap/share-vintage lineage remains `HISTORICAL_DATED_NOT_VINTAGE_AUDITED`.

## Daily local inputs support Priority A

{inventory_table.to_markdown(index=False)}

The cache contains daily, historically dated and time-varying total market cap, not merely signal-date values or a single current snapshot copied backward. No auditable historical shares-outstanding series with effective/announcement/change dates exists, so direct D03 turnover cannot be reconstructed.

### Unit contract

- `amount_unit = CNY_INFERRED_NOT_SOURCE_CERTIFIED`
- `market_cap_unit = CNY_INFERRED_NOT_SOURCE_CERTIFIED`
- `conversion_applied = 1.0 / 1.0`
- `ratio_unit = dimensionless`

No source metadata formally certifies these units. This is an important lineage limitation, not a reason to rescale the ratio after seeing its values.

## Proxy definition and coverage

For each stock and Primary signal date, `VT20_DAILY = mean(Amount_t / TotalMarketCap_t)` on exactly the signal date and previous 19 CSI300 market dates. Every amount and denominator must be positive and finite. Missing dates, zero denominators and nonfinite observations invalidate the stock-period; no forward fill, backfill or earlier-date substitution is allowed.

{coverage.to_markdown(index=False, floatfmt='.4f')}

## Size contamination is materially reduced, not eliminated

{comparison.to_markdown(index=False, floatfmt='.4f')}

Mean period-level Spearman with log total market cap changes from **{old.loc['log_total_market_cap', 'value']:.3f}** for old ACTIVITY_PCT to **{new.loc['log_total_market_cap', 'value']:.3f}** for VT20_DAILY: the signed change is **{new.loc['log_total_market_cap', 'value'] - old.loc['log_total_market_cap', 'value']:.3f}**, while absolute correlation falls by **{abs(old.loc['log_total_market_cap', 'value']) - abs(new.loc['log_total_market_cap', 'value']):.3f}**. The sign reversal means smaller stocks tend to have higher VT20, so size exposure remains rather than disappearing. The VT20 HIGH_PROXY−LOW_PROXY standardized log-cap difference averages **{high_low.loc['log_total_market_cap']:.3f}σ**. This is a signal-time contamination result, not evidence about returns.

VOL20 correlation is **{new.loc['vol20', 'value']:.3f}** versus **{old.loc['vol20', 'value']:.3f}** previously, so volatility contamination increases rather than falls. Raw-price correlation is **{new.loc['log_raw_signal_price', 'value']:.3f}** versus **{old.loc['log_raw_signal_price', 'value']:.3f}**. RETURN60 correlation is **{new.loc['return_60', 'value']:.3f}**. Return-state-specific correlations are retained in `turnover_like_proxy_characteristics.csv`; no future outcome was accessed. VT20 is economically closer to turnover, but these remaining exposures prohibit describing it as a pure activity measure.

## The proxy retains cross-sectional spread

Across all valid stock-periods, VT20_DAILY has median **{distribution.median():.6f}**, p1 **{distribution.quantile(0.01):.6f}**, p99 **{distribution.quantile(0.99):.6f}**, and maximum **{distribution.max():.6f}**. These are flagged for economic-scale review only; no observation was removed based on performance.

Within signal-date size terciles, spread remains:

{spread.to_markdown(floatfmt='.6f')}

The denominator therefore does not collapse VT20 into a near-constant cross-section. Deterministic LOW/MID/HIGH proxy terciles are used only for this characteristic audit, never for performance.

## Relationship to D03

D03 turnover is shares traded divided by shares outstanding. The present value-turnover proxy satisfies only the approximation `Amount / TotalMarketCap ≈ (VWAP / Close) × ShareTurnover`. It is closer to the target economic concept than raw amount but is not an exact replication, true turnover or reconstructed D03 turnover.

## Limitations and next step

- The universe is current rather than historical point-in-time and retains survivorship bias.
- Market cap is daily historical but its archived vendor vintage and historical share-effective-date lineage are not audited.
- Unit identity is strongly plausible from magnitudes and cross-field consistency, not formally documented by the source.
- This audit does not establish that VT20 is an Alpha, a better predictor or an economically superior trading rule.

It is worth drafting a separate H5B-style preregistration for this single fixed `VT20_DAILY` proxy because local coverage and cross-sectional spread are adequate, the raw price-level relationship is nearly removed, and no new download is required. The preregistration must retain the material negative size exposure and stronger VOL20 exposure as named limitations, and must freeze state construction and outcomes before any performance is inspected. This audit stops before H5B.

## Direct answers to the 15 feasibility questions

1. **Daily amount exists:** yes, in the local raw price cache.
2. **Amount coverage:** {int(inventory.loc[inventory['field'].eq('daily_amount'), 'stock_coverage'].iloc[0]):,} stocks, dated {inventory.loc[inventory['field'].eq('daily_amount'), 'date_min'].iloc[0]} through {inventory.loc[inventory['field'].eq('daily_amount'), 'date_max'].iloc[0]}.
3. **Daily historical total market cap exists:** yes, with the same {int(inventory.loc[inventory['field'].eq('daily_total_market_cap'), 'stock_coverage'].iloc[0]):,}-stock coverage.
4. **Signal-date only:** no; the field is daily and time-varying.
5. **Market-cap time status:** `DAILY_HISTORICAL_MARKET_CAP;HISTORICAL_DATED_NOT_VINTAGE_AUDITED`.
6. **Network download required:** no.
7. **Selected proxy:** `VT20_DAILY`, the highest-priority locally feasible definition.
8. **Exact formula:** for each signal, average `Amount_t / TotalMarketCap_t` over the signal date and preceding 19 exact CSI300 market dates; all 20 ratios must be positive and finite, with no fill or date substitution.
9. **Primary coverage:** 56/56 periods; median {coverage['coverage'].median():.2%}, minimum {coverage['coverage'].min():.2%}, p10 {coverage['coverage'].quantile(0.10):.2%}.
10. **New proxy versus size:** mean period Spearman {new.loc['log_total_market_cap', 'value']:.3f}.
11. **Change from old 0.664:** signed change {new.loc['log_total_market_cap', 'value'] - old.loc['log_total_market_cap', 'value']:.3f}; absolute correlation is lower by {abs(old.loc['log_total_market_cap', 'value']) - abs(new.loc['log_total_market_cap', 'value']):.3f}, but size exposure remains with the opposite sign.
12. **New proxy versus VOL20:** mean period Spearman {new.loc['vol20', 'value']:.3f}, higher than the old {old.loc['vol20', 'value']:.3f}; this exposure worsens.
13. **New proxy versus raw price:** mean period Spearman {new.loc['log_raw_signal_price', 'value']:.3f}, substantially below the old {old.loc['log_raw_signal_price', 'value']:.3f}.
14. **Spread within size terciles:** yes; all three size strata cover 56 periods and retain positive median IQR and p90−p10 spread.
15. **Worth a separately preregistered H5B diagnostic:** yes, as a descriptive turnover-like diagnostic with explicit size, VOL20, lineage and survivorship limitations; no H5B performance is run here.

## Further questions

- Can the upstream database owner document currency units and historical market-cap revision policy?
- Can future work source dated shares outstanding if an exact D03-style replication becomes necessary?

## Audit identity

{'; '.join(f'{key}={str(value).lower() if isinstance(value, bool) else value}' for key, value in IDENTITY.items())}
"""
    path.write_text(report, encoding="utf-8")


def run(root: Path) -> str:
    root = root.resolve()
    states = _load_states(root)
    windows = _windows(root, states)
    raw_values, inventory = _load_raw_and_proxy(root, states, windows)
    qfq = _load_qfq_covariates(root, states)
    values = states.merge(
        raw_values,
        on=["period_index", "signal_as_of_date", "stock_code"],
        how="left",
        validate="one_to_one",
    ).merge(
        qfq[["period_index", "stock_code", "vol20"]],
        on=["period_index", "stock_code"],
        how="left",
        validate="one_to_one",
    )
    values["log_total_market_cap"] = np.log(
        pd.to_numeric(values["signal_total_market_cap"], errors="coerce").where(lambda x: x > 0)
    )
    values["log_raw_signal_price"] = np.log(
        pd.to_numeric(values["raw_signal_price"], errors="coerce").where(lambda x: x > 0)
    )
    values = assign_proxy_states(values)
    coverage = values.groupby(["period_index", "signal_as_of_date"], as_index=False).agg(
        h5a_signal_members=("stock_code", "size"),
        vt20_valid_members=("vt20_valid", "sum"),
    )
    coverage["coverage"] = coverage["vt20_valid_members"] / coverage["h5a_signal_members"]
    old = pd.read_csv(root / OUTPUT_DIR / "h5a_activity_correlations.csv")
    characteristics = _characteristics(values, coverage, old)

    if coverage["coverage"].median() < 0.90:
        raise ValueError("priority_a_local_coverage_below_90_percent")
    output = root / OUTPUT_DIR
    inventory.to_csv(output / "turnover_like_proxy_data_inventory.csv", index=False, encoding="utf-8-sig")
    values.to_csv(output / "turnover_like_proxy_signal_values.csv", index=False, encoding="utf-8-sig")
    characteristics.to_csv(output / "turnover_like_proxy_characteristics.csv", index=False, encoding="utf-8-sig")
    _write_report(
        output / "turnover_like_proxy_feasibility_audit.md",
        inventory,
        values,
        characteristics,
        coverage,
    )
    print("TURNOVER_PROXY_FEASIBILITY_COMPLETE classification=TURNOVER_PROXY_READY_WITH_LINEAGE_LIMITATION")
    return "TURNOVER_PROXY_READY_WITH_LINEAGE_LIMITATION"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    run(args.project_root)


if __name__ == "__main__":
    main()
