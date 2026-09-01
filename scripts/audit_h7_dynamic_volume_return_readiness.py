"""Signal/data-only H7 readiness audit; never estimates a return-volume relation."""

# ruff: noqa: E501 -- report prose and source contracts are intentionally explicit.
from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from scripts.audit_h5a_activity_main_effect import _market_calendar
else:
    from audit_h5a_activity_main_effect import _market_calendar

OUT = Path("reports/hypothesis_7")
THRESHOLDS = (500, 750, 1000, 1250)
PROBE_CODES = (
    "600000", "600519", "601698", "603259", "605117", "000001", "000002", "000063",
    "002594", "003816", "300002", "300378", "300857", "301171", "301696", "688001",
    "688981", "688781", "688811", "001257", "603293", "688813", "600355", "300344", "002049",
)
IDENTITY = {
    "research_type": "data_readiness_audit", "sample_role": "historical_seen",
    "D05_inspired": True, "D05_replication": False, "C2_estimated": False,
    "volume_return_regression_run": False, "future_performance_used_for_design": False,
    "H5_run": False, "H6_run": False, "MCTS_run": False, "Phase_B_run": False,
    "prospective_data_accessed": False, "final_test_accessed": False,
    "network_download_performed": "true_small_25_stock_probe_no_data_returned",
}


def code6(value: object) -> str:
    digits = "".join(c for c in str(value) if c.isdigit())
    return digits[-6:].zfill(6)


def board(code: str) -> str:
    if code.startswith("688"):
        return "STAR"
    if code.startswith("30"):
        return "CHINEXT"
    if code.startswith(("60", "68")):
        return "SH_MAIN"
    return "SZ_MAIN"


def exact_prior_200_valid(values: pd.Series) -> pd.Series:
    """Availability only: current observation plus exactly 200 prior positions."""
    finite = pd.Series(np.isfinite(pd.to_numeric(values, errors="coerce")), index=values.index)
    prior = finite.shift(1).rolling(200, min_periods=200).sum().eq(200)
    return finite & prior


def potential_endpoint_valid(v_valid: pd.Series, prices: pd.Series, horizon: int) -> pd.Series:
    p = pd.to_numeric(prices, errors="coerce")
    legal = np.isfinite(p) & p.gt(0)
    return v_valid & legal.shift(1) & legal & legal.shift(-horizon)


def discontinuities(series: pd.Series, threshold: float = 0.20) -> int:
    values = pd.to_numeric(series, errors="coerce")
    return int(values.pct_change(fill_method=None).abs().gt(threshold).sum())


def safe_quantiles(values: list[np.ndarray]) -> dict[str, float]:
    data = np.concatenate(values) if values else np.array([], dtype=float)
    data = data[np.isfinite(data)]
    positive = data[data > 0]
    return {
        "observations": int(len(data)), "zero_count": int((data == 0).sum()),
        "zero_rate": float((data == 0).mean()) if len(data) else math.nan,
        "smallest_positive": float(positive.min()) if len(positive) else math.nan,
        "p1": float(np.quantile(data, .01)) if len(data) else math.nan,
        "p5": float(np.quantile(data, .05)) if len(data) else math.nan,
        "median": float(np.median(data)) if len(data) else math.nan,
        "p95": float(np.quantile(data, .95)) if len(data) else math.nan,
        "p99": float(np.quantile(data, .99)) if len(data) else math.nan,
        "maximum": float(data.max()) if len(data) else math.nan,
    }


def scan_local(root: Path) -> tuple[pd.DataFrame, dict, dict]:
    universe = pd.read_csv(root / "data/processed/h5a_broader_a_universe_v1.csv", dtype=str)
    universe = universe.loc[universe["universe_status"].eq("INCLUDED")].copy()
    universe["stock_code"] = universe["stock_code"].map(code6)
    if len(universe) != 5195 or universe.stock_code.duplicated().any():
        raise ValueError("expected_5195_unique_current_universe")
    calendar = _market_calendar(root)
    qfq_paths = {
        p.stem: p for p in (root / "data/cache/h5a_broader_a_qfq_v1").glob("*.csv")
    }
    histories, turnover_values = [], []
    totals = {key: 0 for key in (
        "rows", "amount_valid", "turnover_valid", "close_valid", "high_valid", "low_valid",
        "size_valid", "circ_valid", "qfq_rows", "qfq_valid", "amount_stocks",
        "turnover_stocks", "close_stocks", "ohlc_stocks", "size_stocks",
    )}
    date_min, date_max = pd.NaT, pd.NaT
    for n, code in enumerate(universe.stock_code, 1):
        path = root / f"data/cache/price/{code}.csv"
        wanted = [
            "date", "close", "amount", "high", "low", "turnover",
            "total_market_cap", "circulating_market_cap",
        ]
        raw = pd.read_csv(path, usecols=lambda name, columns=wanted: name in columns)
        if "date" not in raw:
            raise ValueError(f"missing_raw_date={code}")
        for missing in set(wanted) - set(raw.columns):
            raw[missing] = np.nan
        raw["date"] = pd.to_datetime(raw["date"], errors="raise")
        if raw.date.duplicated().any():
            raise ValueError(f"duplicate_raw_date={code}")
        raw = raw.set_index("date").sort_index()
        for col in raw.columns:
            raw[col] = pd.to_numeric(raw[col], errors="coerce")
        date_min = raw.index.min() if pd.isna(date_min) else min(date_min, raw.index.min())
        date_max = raw.index.max() if pd.isna(date_max) else max(date_max, raw.index.max())
        totals["rows"] += len(raw)
        for col, key in (("amount", "amount_valid"), ("turnover", "turnover_valid"), ("close", "close_valid"), ("high", "high_valid"), ("low", "low_valid"), ("total_market_cap", "size_valid"), ("circulating_market_cap", "circ_valid")):
            totals[key] += int(np.isfinite(raw[col]).sum())
        totals["amount_stocks"] += int(np.isfinite(raw.amount).any())
        totals["turnover_stocks"] += int(np.isfinite(raw.turnover).any())
        totals["close_stocks"] += int(np.isfinite(raw.close).any())
        totals["ohlc_stocks"] += int(
            np.isfinite(raw[["high", "low", "close"]]).all(axis=1).any()
        )
        totals["size_stocks"] += int(np.isfinite(raw.total_market_cap).any())
        turn = raw.turnover.to_numpy(float)
        turnover_values.append(turn[np.isfinite(turn)])
        dates = calendar[(calendar >= raw.index.min()) & (calendar <= raw.index.max())]
        turnover = raw.turnover.reindex(dates)
        v_valid = exact_prior_200_valid(turnover)
        prices = pd.Series(np.nan, index=dates)
        qpath = qfq_paths.get(code)
        if qpath:
            q = pd.read_csv(qpath, usecols=["trade_date", "qfq_close"])
            q["trade_date"] = pd.to_datetime(q.trade_date, errors="raise")
            if q.trade_date.duplicated().any():
                raise ValueError(f"duplicate_qfq_date={code}")
            totals["qfq_rows"] += len(q)
            totals["qfq_valid"] += int(np.isfinite(pd.to_numeric(q.qfq_close, errors="coerce")).sum())
            prices = pd.to_numeric(q.set_index("trade_date").qfq_close, errors="coerce").reindex(dates)
        latest_size = raw.total_market_cap.dropna().iloc[-1] if raw.total_market_cap.notna().any() else math.nan
        latest_circ = raw.circulating_market_cap.dropna().iloc[-1] if raw.circulating_market_cap.notna().any() else math.nan
        inferred_total = raw.total_market_cap / raw.close.where(raw.close > 0)
        inferred_circ = raw.circulating_market_cap / raw.close.where(raw.close > 0)
        valid_dates = dates[v_valid.to_numpy()]
        histories.append({
            "row_type": "stock", "stock_code": code, "board": board(code),
            "local_history_start": raw.index.min(), "local_history_end": raw.index.max(),
            "local_history_days": len(raw), "listing_date": pd.NaT, "listing_age_years": math.nan,
            "latest_total_market_cap": latest_size, "log_size": np.log(latest_size) if latest_size > 0 else math.nan,
            "size_quartile": "", "first_date_with_valid_200d_baseline": valid_dates.min() if len(valid_dates) else pd.NaT,
            "last_date": raw.index.max(), "number_of_valid_V_dates_upper_bound": int(v_valid.sum()),
            "potential_1d_rows_upper_bound": int(potential_endpoint_valid(v_valid, prices, 1).sum()),
            "potential_2d_rows_upper_bound": int(potential_endpoint_valid(v_valid, prices, 2).sum()),
            "potential_5d_rows_upper_bound": int(potential_endpoint_valid(v_valid, prices, 5).sum()),
            "exact_candidate_valid_days": 0, "history_status": "UPPER_BOUND_ONLY_VENDOR_TURNOVER_DEFINITION_AND_PRECISION_UNRESOLVED",
            "inferred_total_share_discontinuities_gt20pct": discontinuities(inferred_total),
            "inferred_circulating_share_discontinuities_gt20pct": discontinuities(inferred_circ),
            "latest_circulating_market_cap": latest_circ,
        })
        if n % 500 == 0:
            print(f"local files scanned={n}", flush=True)
    history = pd.DataFrame(histories)
    eligible_size = history.log_size.notna()
    history.loc[eligible_size, "size_quartile"] = pd.qcut(history.loc[eligible_size, "log_size"], 4, labels=["Q1_SMALL", "Q2", "Q3", "Q4_LARGE"]).astype(str)
    stats = safe_quantiles(turnover_values)
    stats.update({"date_min": date_min, "date_max": date_max, **totals})
    return history, stats, {"universe": len(universe), "qfq_stock_files": len(qfq_paths)}


def threshold_rows(history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, float, bool]:
    stock = history.loc[history.row_type.eq("stock")]
    rho = stock[["potential_1d_rows_upper_bound", "log_size"]].corr(method="spearman").iloc[0, 1]
    summaries, quartiles = [], []
    for threshold in THRESHOLDS:
        selected = stock.potential_1d_rows_upper_bound.ge(threshold)
        part = stock.loc[selected]
        summaries.append({
            "row_type": "threshold_summary", "threshold": threshold,
            "exact_candidate_stock_count": 0, "exact_candidate_percentage": 0.0,
            "upper_bound_stock_count": int(selected.sum()), "upper_bound_percentage": float(selected.mean()),
            "median_history_length_upper_bound": part.potential_1d_rows_upper_bound.median(),
            "minimum_local_history_days": part.local_history_days.min(), "maximum_local_history_days": part.local_history_days.max(),
            "median_market_cap": part.latest_total_market_cap.median(), "minimum_listing_age": math.nan,
            "maximum_listing_age": math.nan, "listing_year_distribution": "UNKNOWN_LOCAL_UNIVERSE_HAS_NO_LISTING_DATE",
            "industry_distribution": "UNKNOWN_NO_BROADER_A_INDUSTRY_MAP",
        })
        byq = stock.groupby("size_quartile", observed=True).agg(stock_count=("stock_code", "size"), median_history=("potential_1d_rows_upper_bound", "median"))
        inc = stock.assign(included=selected).groupby("size_quartile", observed=True).included.mean()
        for quartile, row in byq.iterrows():
            quartiles.append({"row_type": "size_quartile_threshold", "threshold": threshold, "size_quartile": quartile, "stock_count": row.stock_count, "median_history_length": row.median_history, "inclusion_rate": inc[quartile]})
    q = pd.DataFrame(quartiles)
    spread = q.groupby("threshold").inclusion_rate.agg(lambda x: x.max() - x.min()).max()
    material = bool(abs(rho) >= .20 or spread >= .10)
    return pd.DataFrame(summaries), q, float(rho), material


def inventory_rows(stats: dict) -> pd.DataFrame:
    rows = [
        ("daily_qfq_close_return", True, "data/cache/h5a_broader_a_qfq_v1/*.csv", "qfq_close", "CNY/share; vendor QFQ", 5180, "2020-12-28", "2026-05-18", "HISTORICAL_DATED_CURRENT_ADJUSTMENT_VINTAGE", True, False, "daily returns constructible; point-in-time adjustment vintage not audited"),
        ("daily_share_volume", False, "data/cache/price/*.csv", "field absent; db_schema only", "shares", 0, "", "", "SCHEMA_ONLY", False, True, "not present in canonical broader-A files"),
        ("daily_amount", True, "data/cache/price/*.csv", "amount", "CNY inferred", stats["amount_stocks"], stats["date_min"], stats["date_max"], "HISTORICAL_DATED_UNIT_NOT_CERTIFIED", True, False, "not share volume"),
        ("historical_total_shares", False, "data/cache/price/*.csv", "total_market_cap/close inference only", "shares inferred", 0, stats["date_min"], stats["date_max"], "INFERRED_NOT_VINTAGE_AUDITED", False, True, "no auditable direct shares/effective-date series"),
        ("historical_float_shares", False, "data/cache/price/*.csv", "circulating_market_cap/close inference only", "shares inferred", 0, stats["date_min"], stats["date_max"], "INFERRED_NOT_VINTAGE_AUDITED", False, True, "circulating is not source-certified free float"),
        ("historical_free_float_shares", False, "local search", "absent", "shares", 0, "", "", "UNAVAILABLE", False, True, "Tushare daily_basic offers free_share but needs token/points"),
        ("vendor_turnover", True, "data/cache/price/*.csv", "turnover", "decimal ratio inferred", stats["turnover_stocks"], stats["date_min"], stats["date_max"], "DENOMINATOR_UNRESOLVED_COARSE_PRECISION", False, True, f"zero_rate={stats['zero_rate']:.6f}; median unique values per stock=23 from pre-audit profile"),
        ("daily_total_market_cap_size", True, "data/cache/price/*.csv", "total_market_cap", "CNY inferred", stats["size_stocks"], stats["date_min"], stats["date_max"], "HISTORICAL_DATED_NOT_VINTAGE_AUDITED", True, False, "latest date used only for data-side size dependence"),
        ("daily_high_low_close", True, "data/cache/price/*.csv", "high;low;close", "CNY/share raw", stats["ohlc_stocks"], stats["date_min"], stats["date_max"], "HISTORICAL_DATED_RAW", True, False, "usable for inventory/proxy feasibility, not adjusted returns"),
        ("benchmark_market_calendar", True, "data/processed/hybrid_benchmark_panel_v1_5.csv", "benchmark_code;trade_date", "market dates", 1, "", "", "HISTORICAL_DATED", True, False, "CSI300 exact dates"),
    ]
    cols = ["measurement", "local_available", "exact_path", "exact_field", "unit", "stock_coverage", "date_min", "date_max", "historical_point_in_time_status", "signal_time_legal", "new_download_required", "notes"]
    out = pd.DataFrame(rows, columns=cols)
    out["row_type"] = "local_inventory"
    candidates = pd.DataFrame([
        {"row_type": "turnover_candidate", "measurement": "TOTAL_SHARE_TURNOVER", "local_available": False, "exact_path": "not available", "exact_field": "SharesTraded/TotalShares", "unit": "ratio", "stock_coverage": 0, "definition_fidelity": "closer to D05 shares-outstanding denominator", "A_share_interpretation": "all issued shares denominator", "denominator_quality": "direct dated total shares absent; cap/close inference not audited", "zero_rate": math.nan, "extreme_distribution": "not measurable", "denominator_discontinuities": "inferred series audited in history CSV but not accepted"},
        {"row_type": "turnover_candidate", "measurement": "FREE_FLOAT_TURNOVER", "local_available": False, "exact_path": "not available", "exact_field": "SharesTraded/FreeFloatShares", "unit": "ratio", "stock_coverage": 0, "definition_fidelity": "secondary A-share economic denominator; not exact D05 total shares", "A_share_interpretation": "tradable economic float denominator", "denominator_quality": "free-float series absent", "zero_rate": math.nan, "extreme_distribution": "not measurable", "denominator_discontinuities": "not measurable"},
        {"row_type": "public_probe", "measurement": "AKSHARE_STOCK_ZH_A_HIST_TURNOVER", "local_available": False, "exact_path": "network probe only; no cache", "exact_field": "成交量;换手率", "unit": "volume unit/turnover percent not source-certified in response", "stock_coverage": 0, "definition_fidelity": "probe unresolved", "denominator_quality": "all 25 fixed requests failed", "notes": "25/25 failed: 15 ProxyError, 10 SSLError; no retry, source switch or raw cache"},
        {"row_type": "public_contract", "measurement": "TUSHARE_DAILY_BASIC", "local_available": False, "exact_path": "https://tushare.pro/document/2?doc_id=32", "exact_field": "turnover_rate;turnover_rate_f;total_share;float_share;free_share", "unit": "turnover percent; shares in 10k", "stock_coverage": 0, "definition_fidelity": "fields explicitly define unrestricted-float and free-float turnover", "denominator_quality": "historically dated vendor series; vintage policy still needs audit", "notes": "tushare not installed; no token; official docs require >=2000 points"},
    ])
    valid_counts = {
        "daily_qfq_close_return": (stats["qfq_valid"], stats["qfq_rows"]),
        "daily_share_volume": (0, stats["rows"]),
        "daily_amount": (stats["amount_valid"], stats["rows"]),
        "historical_total_shares": (0, stats["rows"]),
        "historical_float_shares": (0, stats["rows"]),
        "historical_free_float_shares": (0, stats["rows"]),
        "vendor_turnover": (stats["turnover_valid"], stats["rows"]),
        "daily_total_market_cap_size": (stats["size_valid"], stats["rows"]),
        "daily_high_low_close": (min(stats["high_valid"], stats["low_valid"], stats["close_valid"]), stats["rows"]),
    }
    out["valid_observations"] = out.measurement.map(lambda x: valid_counts.get(x, (math.nan, math.nan))[0])
    out["reference_observations"] = out.measurement.map(lambda x: valid_counts.get(x, (math.nan, math.nan))[1])
    out["row_missing_rate"] = 1 - out.valid_observations / out.reference_observations
    return pd.concat([out, candidates], ignore_index=True, sort=False)


def microstructure_inventory() -> pd.DataFrame:
    rows = [
        ("ST_status", False, "Tushare ST lists / name history", "historical source exists but not locally tested", "permission/points likely", "needed for interpretation; execution also"),
        ("suspension_trading_status", False, "Tushare suspend_d", "daily historical fields documented", "API permission required", "helpful for mechanism; required for execution"),
        ("limit_up_down_prices", False, "Tushare stk_limit", "pre_close;up_limit;down_limit", ">=2000 points", "helpful for 1D mechanism; required for execution"),
        ("one_price_limit_status", False, "derive only with limit price + OHLC after source acquired", "not local", "supplement required", "helpful; required for execution"),
        ("previous_close", False, "can derive from consecutive local raw/QFQ dates; no explicit field", "bounded local history", "free", "mechanism sufficient with exact calendar rule"),
        ("daily_high_low_close", True, "data/cache/price/*.csv high;low;close", "2020/2021-2026", "local", "mechanism proxy only"),
        ("historical_bid1_ask1_spread_L1", False, "no local files/fields", "none", "exchange/vendor historical data likely licensed", "quoted spread unavailable"),
        ("Amihud_illiquidity_proxy", True, "QFQ return + amount", "bounded local history", "free", "proxy feasible; not quoted spread/information asymmetry"),
        ("high_low_spread_estimator", True, "raw high/low", "bounded local history", "free", "proxy feasible; not quoted spread/information asymmetry"),
        ("Roll_type_estimator", True, "QFQ close returns", "bounded local history", "free", "proxy feasible; assumptions may fail"),
        ("analyst_reports", False, "Tushare research_report / public alternatives", "Tushare documents history from 2017", "separate permission", "future ANALYST_COUNT_12M/BROKER_COUNT_12M/REPORT_COUNT_12M feasible only with report_date<=observation"),
    ]
    return pd.DataFrame(rows, columns=["item", "local_available", "public_source_or_local_path", "historical_depth_or_fields", "access_cost_or_permission", "reliability_and_research_need"])


def report(root: Path, history: pd.DataFrame, inventory: pd.DataFrame, micro: pd.DataFrame, stats: dict, threshold: pd.DataFrame, quartile: pd.DataFrame, rho: float, material: bool) -> str:
    q = inventory.loc[inventory.row_type.eq("local_inventory"), ["measurement", "local_available", "exact_path", "exact_field", "unit", "stock_coverage", "date_min", "date_max", "historical_point_in_time_status", "signal_time_legal", "new_download_required"]]
    turn = inventory.loc[inventory.row_type.ne("local_inventory")]
    endpoints = {h: history[f"potential_{h}d_rows_upper_bound"].sum() / history.number_of_valid_V_dates_upper_bound.sum() for h in (1, 2, 5)}
    threshold_text = threshold[["threshold", "exact_candidate_stock_count", "upper_bound_stock_count", "upper_bound_percentage", "median_history_length_upper_bound", "minimum_local_history_days", "maximum_local_history_days", "median_market_cap"]]
    return f"""# H7 — Dynamic Volume–Return Relation Data Readiness Audit

## Technical summary

**H7_NOT_READY.** Daily adjusted prices, amount, market cap, OHLC and calendar are locally available, but neither true `TOTAL_SHARE_TURNOVER` nor `FREE_FLOAT_TURNOVER` is locally reconstructible: canonical share volume and auditable historical share denominators are absent. The local vendor `turnover` is not accepted because its denominator is unresolved and its median stock has only 23 distinct values; {stats['zero_count']:,}/{stats['observations']:,} finite observations are zero. A fixed 25-stock AkShare probe failed 25/25 from SSL/proxy transport errors, and Tushare daily_basic could not be tested because no package/token is configured and the official contract requires points.

No C2, return-volume regression, sign distribution or relation with size was calculated. History and endpoint counts below are explicitly an **upper-bound infrastructure diagnostic using the unresolved local vendor field**, not candidate readiness and not a result.

## Local measurement inventory

{q.to_markdown(index=False)}

Database schema declarations alone were not counted as available data. Daily cap divided by raw close can algebraically imply dated shares, but no source-certified share/effective-date/vintage lineage exists; the per-stock discontinuity counts are retained only in `h7_history_sufficiency.csv`.

## Both exact turnover candidates require supplementation

{turn.to_markdown(index=False)}

`TOTAL_SHARE_TURNOVER` is the **Primary candidate for a future contract** because total shares is closer to the D05 shares-outstanding denominator. `FREE_FLOAT_TURNOVER` is the A-share economic secondary robustness because it focuses on actually tradable ownership, but it is not the same denominator. This is a definition/data recommendation only. Official Tushare daily_basic documentation explicitly defines `turnover_rate` from unrestricted circulating shares and `turnover_rate_f` from free-float shares and provides total/float/free share fields; it requires at least 2,000 points: https://tushare.pro/document/2?doc_id=32 .

## Log turnover and epsilon are not yet contractible

For the unresolved local vendor field only: zero={stats['zero_count']:,} ({stats['zero_rate']:.2%}), smallest positive={stats['smallest_positive']:.6g}, p1={stats['p1']:.6g}, p5={stats['p5']:.6g}, median={stats['median']:.6g}, p95={stats['p95']:.6g}, p99={stats['p99']:.6g}, max={stats['maximum']:.6g}. Its granularity and unknown zeros make `log(turnover+epsilon)` unsafe. Do not copy D05 epsilon. Future principle: first resolve source units/status semantics, retain true zero separately from missing/nontrading, then freeze one measurement-scale epsilon below the smallest reliable positive value without looking at C2.

## Exact 200-prior-day contract is computationally feasible, but the input is not ready

The audit verifies the availability algorithm: t is valid only when t and all exact prior 200 CSI300 dates are finite; t is excluded from its baseline; there is no fill or earlier-date substitution. Exact candidate valid days are zero until a reliable turnover source is obtained. The stock rows nevertheless report the maximum rows the existing calendar/QFQ infrastructure could support if the local vendor field's definition and precision were resolved.

{threshold_text.to_markdown(index=False)}

Thus `stocks_ge_500/750/1000/1250_valid_days` are all **0 for an accepted exact candidate**. The upper-bound counts are shown only for data planning. Listing dates and broader-A industry mapping are unavailable, so listing-age/year and industry distributions are UNKNOWN rather than inferred from the bounded raw-cache start date.

## History-size dependence must be reassessed after supplementation

Upper-bound `Spearman(potential_1d_rows, log latest market cap)={rho:.6f}`; the latest market cap is historical-dated but not vintage-audited. The mechanical upper-bound size-quartile table is:

{quartile.to_markdown(index=False)}

`history_selection_size_confounding={'material' if material else 'not_material_in_upper_bound'}` applies only to this upper bound. No valid conclusion about exact turnover eligibility is possible before source supplementation.

## Potential endpoint infrastructure

Conditional on the unresolved upper-bound V dates, exact QFQ endpoint availability is 1D={endpoints[1]:.6%}, 2D={endpoints[2]:.6%}, 5D={endpoints[5]:.6%}. This checks only the presence of P(t−1), P(t) and P(t+h), never computes returns or compares horizons. For an accepted candidate, all endpoint coverages are currently UNKNOWN.

## Microstructure, spread and analyst metadata

{micro.to_markdown(index=False)}

Tushare documents daily limit prices (including previous close) and daily suspension records, both permissioned supplements: https://tushare.pro/document/2?doc_id=183 and https://tushare.pro/document/2?doc_id=214 . Exact local historical quoted spread is false. Free daily proxies are feasible, but none is D05 quoted spread or information asymmetry. Tushare's research-report contract documents reports from 2017 and requires separate access; future dated counts are conceptually feasible only under `report_date<=observation_date`: https://tushare.pro/document/2?doc_id=415 . No report data were downloaded or linked to any relation.

## Recommendation and next data action

- `PRIMARY_TURNOVER_CANDIDATE=TOTAL_SHARE_TURNOVER`; acquire one documented historical daily source with share volume and dated total shares, or an explicitly equivalent direct rate.
- `SECONDARY_MEASUREMENT_ROBUSTNESS=FREE_FLOAT_TURNOVER`; acquire source-defined free-float turnover/free shares from the same vintage if possible.
- `recommended_min_valid_days=UNKNOWN`; the exact-candidate retained counts are zero, while upper bounds cannot justify a threshold. `threshold_selection_requires_human_judgment=true`, after a successful source probe and before C2.
- Do not implement Amihud/high-low/Roll as substitute Primary measures. Do not estimate C2 until turnover precision, zero semantics and denominator lineage are resolved.

## Audit identity and QA

Focused tests cover exact prior-200 exclusion of t, missing/no-fill, endpoint presence, threshold data-only rules and forbidden regression/C2 paths. The runner reads only current local historical paths and has no network client. The separately authorized 25-stock probe made 25 requests and saved no raw cache; all failed and no source switch/retry occurred.

```text
research_type=data_readiness_audit
sample_role=historical_seen
D05_inspired=true
D05_replication=false
network_download_performed=true_small_25_stock_probe_no_data_returned
C2_estimated=false
volume_return_regression_run=false
future_performance_used_for_design=false
H5_run=false
H6_run=false
MCTS_run=false
Phase_B_run=false
prospective_data_accessed=false
final_test_accessed=false
H7_data_readiness=H7_NOT_READY
```
"""


def run(root: Path) -> None:
    output = root / OUT
    output.mkdir(parents=True, exist_ok=True)
    history, stats, _ = scan_local(root)
    threshold, quartile, rho, material = threshold_rows(history)
    combined = pd.concat([history, threshold, quartile], ignore_index=True, sort=False)
    inventory = inventory_rows(stats)
    micro = microstructure_inventory()
    for frame in (combined, inventory, micro):
        for key, value in IDENTITY.items():
            frame[key] = value
    combined.to_csv(output / "h7_history_sufficiency.csv", index=False)
    inventory.to_csv(output / "h7_turnover_measurement_inventory.csv", index=False)
    micro.to_csv(output / "h7_microstructure_data_inventory.csv", index=False)
    (output / "h7_dynamic_volume_return_data_readiness.md").write_text(
        report(root, history, inventory, micro, stats, threshold, quartile, rho, material), encoding="utf-8"
    )
    print(threshold[["threshold", "exact_candidate_stock_count", "upper_bound_stock_count"]].to_string(index=False))
    print(f"history_length_size_spearman_upper_bound={rho:.8f}")
    print("H7_data_readiness=H7_NOT_READY; C2_estimated=false")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    run(parser.parse_args().project_root.resolve())
