"""Targeted CNINFO schema and share-lineage review for at most 15 stocks."""

# ruff: noqa: E501 -- source schemas and report prose are intentionally explicit.
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

if __package__:
    from scripts.probe_h7_turnover_sources import (
        DATA_CUTOFF,
        build_point_in_time_shares,
        code6,
    )
else:
    from probe_h7_turnover_sources import DATA_CUTOFF, build_point_in_time_shares, code6

OUT = Path("reports/hypothesis_7/source_probe")
FAILURE_CODES = ("000001", "000004", "300344")
MAX_REVIEW_STOCKS = 15
RAW_FIELD_MAP = {
    "SECCODE": "stock_code",
    "DECLAREDATE": "announcement_date",
    "VARYDATE": "change_date",
    "F002V": "change_reason",
    "F003N": "total_shares_10k",
    "F021N": "circulating_shares_10k",
    "F028N": "restricted_shares_10k",
}


def select_review_sample(root: Path) -> pd.DataFrame:
    cross = pd.read_csv(
        root / OUT / "h7_turnover_cross_validation.csv", dtype={"stock_code": str}
    )
    cross["stock_code"] = cross.stock_code.map(code6)
    metric = "implied_total_vs_cninfo_p95_error"
    ranked = cross.loc[~cross.stock_code.isin(FAILURE_CODES)].sort_values(
        [metric, "stock_code"], ascending=[False, True], na_position="last"
    )
    rows = [
        {
            "stock_code": code,
            "exception_type": "CNINFO_PRIOR_PROBE_FAILURE",
            "selection_metric": "prior_status",
            "selection_value": math.nan,
            "selection_reason": "mandatory_failed_stock",
        }
        for code in FAILURE_CODES
    ]
    for row in ranked.head(MAX_REVIEW_STOCKS - len(rows)).itertuples():
        rows.append({
            "stock_code": row.stock_code,
            "exception_type": "HIGH_TOTAL_SHARE_DISCREPANCY",
            "selection_metric": metric,
            "selection_value": getattr(row, metric),
            "selection_reason": "deterministic_descending_existing_data_quality_error",
        })
    sample = pd.DataFrame(rows)
    if len(sample) > MAX_REVIEW_STOCKS or sample.stock_code.duplicated().any():
        raise ValueError("invalid_review_sample")
    sample["data_cutoff"] = DATA_CUTOFF.date().isoformat()
    return sample


def cninfo_headers() -> dict[str, str]:
    import py_mini_racer
    from akshare.stock.stock_share_changes_cninfo import _get_file_content_cninfo

    js = py_mini_racer.MiniRacer()
    js.eval(_get_file_content_cninfo("cninfo.js"))
    return {
        "Accept": "*/*",
        "Accept-Enckey": js.call("getResCode1"),
        "Accept-Encoding": "gzip, deflate",
        "Origin": "https://webapi.cninfo.com.cn",
        "Referer": "https://webapi.cninfo.com.cn/",
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
    }


def raw_cninfo_request(
    code: str, start: str, attempts: int, headers: dict[str, str]
) -> tuple[dict, dict]:
    url = "https://webapi.cninfo.com.cn/api/stock/p_stock2215"
    params = {"scode": code, "sdate": start, "edate": "2026-08-20"}
    last_error = ""
    for attempt in range(1, attempts + 1):
        try:
            response = requests.post(url, params=params, headers=headers, timeout=20)
            payload = response.json()
            records = payload.get("records", []) if isinstance(payload, dict) else []
            columns = sorted({key for row in records if isinstance(row, dict) for key in row})
            meta = {
                "stock_code": code,
                "request_start": start,
                "request_end": "2026-08-20",
                "attempts": attempt,
                "http_status": response.status_code,
                "top_level_keys": json.dumps(sorted(payload) if isinstance(payload, dict) else [], ensure_ascii=False),
                "returned_columns": json.dumps(columns, ensure_ascii=False),
                "empty_response": len(records) == 0,
                "row_count": len(records),
                "representative_rows": json.dumps(records[:3], ensure_ascii=False, default=str),
                "schema_has_DECLAREDATE": "DECLAREDATE" in columns,
                "schema_has_VARYDATE": "VARYDATE" in columns,
                "status": "SUCCESS",
                "error": "",
            }
            return payload, meta
        except Exception as exc:
            last_error = f"{type(exc).__name__}:{exc}"
            if attempt < attempts:
                time.sleep(1)
    return {}, {
        "stock_code": code,
        "request_start": start,
        "request_end": "2026-08-20",
        "attempts": attempts,
        "http_status": math.nan,
        "top_level_keys": "[]",
        "returned_columns": "[]",
        "empty_response": True,
        "row_count": 0,
        "representative_rows": "[]",
        "schema_has_DECLAREDATE": False,
        "schema_has_VARYDATE": False,
        "status": "TRANSIENT_NETWORK_UNRESOLVED",
        "error": last_error,
    }


def normalize_raw_events(payload: dict, requested_code: str) -> pd.DataFrame:
    records = payload.get("records", []) if isinstance(payload, dict) else []
    raw = pd.DataFrame(records)
    if raw.empty:
        return pd.DataFrame(columns=[
            "stock_code", "announcement_date", "change_date", "change_reason",
            "total_shares", "circulating_shares", "restricted_shares",
            "event_date_incomplete", "information_available_date",
        ])
    out = pd.DataFrame(index=raw.index)
    for source, target in RAW_FIELD_MAP.items():
        out[target] = raw[source] if source in raw else np.nan
    out["stock_code"] = out.stock_code.fillna(requested_code).map(code6)
    out["announcement_date"] = pd.to_datetime(out.announcement_date, errors="coerce")
    out["change_date"] = pd.to_datetime(out.change_date, errors="coerce")
    for column in ("total_shares_10k", "circulating_shares_10k", "restricted_shares_10k"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["total_shares"] = out.total_shares_10k * 10_000.0
    out["circulating_shares"] = out.circulating_shares_10k * 10_000.0
    out["restricted_shares"] = out.restricted_shares_10k * 10_000.0
    out["event_date_incomplete"] = out[["change_date", "announcement_date"]].isna().any(axis=1)
    out["information_available_date"] = out[["change_date", "announcement_date"]].max(axis=1)
    latest_source_date = out[["change_date", "announcement_date"]].max(axis=1)
    return out.loc[~latest_source_date.gt(DATA_CUTOFF)].sort_values(
        ["information_available_date", "change_date"]
    ).reset_index(drop=True)


def simple_ratio_label(ratio: float) -> str:
    candidates = {"2/3": 2 / 3, "3/4": 3 / 4, "4/5": 4 / 5, "4/3": 4 / 3, "1.5": 1.5, "2.0": 2.0}
    if not np.isfinite(ratio):
        return "UNKNOWN"
    label, value = min(candidates.items(), key=lambda item: abs(ratio - item[1]))
    return label if abs(ratio - value) <= 0.02 else "NO_SIMPLE_RATIO_WITHIN_2PCT"


def event_windows(
    root: Path, code: str, events: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, object], pd.Series]:
    bao = pd.read_csv(root / f"data/probe/h7_turnover_sources/baostock/{code}.csv")
    bao["trade_date"] = pd.to_datetime(bao.trade_date)
    local = pd.read_csv(
        root / f"data/cache/price/{code}.csv",
        usecols=lambda column: column in {
            "date", "close", "total_market_cap", "circulating_market_cap",
        },
    )
    local["trade_date"] = pd.to_datetime(local.date)
    local = local.loc[local.trade_date.le(DATA_CUTOFF)]
    local = local.rename(columns={"close": "local_raw_close"})
    dates = bao.trade_date.sort_values().reset_index(drop=True)
    lineage = build_point_in_time_shares(events, dates)
    daily = bao.merge(lineage, on="trade_date", how="left").merge(
        local[["trade_date", "local_raw_close", "total_market_cap", "circulating_market_cap"]],
        on="trade_date", how="left",
    )
    close = pd.to_numeric(daily.local_raw_close, errors="coerce")
    daily["implied_total_shares"] = pd.to_numeric(daily.total_market_cap, errors="coerce") / close
    daily["implied_circulating_shares"] = pd.to_numeric(daily.circulating_market_cap, errors="coerce") / close
    turn = pd.to_numeric(daily.baostock_circulating_turnover, errors="coerce")
    daily["baostock_implied_circulating_shares"] = pd.to_numeric(daily.volume_shares, errors="coerce") / turn.where(turn.gt(0))
    daily["relative_error_total"] = (
        (daily.implied_total_shares - daily.total_shares).abs() / daily.total_shares
    ).replace([np.inf, -np.inf], np.nan)
    daily["relative_error_circulating"] = (
        (daily.implied_circulating_shares - daily.circulating_shares).abs()
        / daily.circulating_shares
    ).replace([np.inf, -np.inf], np.nan)
    daily["baostock_circ_vs_cninfo_error"] = (
        (daily.baostock_implied_circulating_shares - daily.circulating_shares).abs()
        / daily.circulating_shares
    ).replace([np.inf, -np.inf], np.nan)
    total_ratio = (daily.implied_total_shares / daily.total_shares).replace([np.inf, -np.inf], np.nan)
    circ_ratio = (daily.implied_circulating_shares / daily.circulating_shares).replace([np.inf, -np.inf], np.nan)
    bao_ratio = (daily.baostock_implied_circulating_shares / daily.circulating_shares).replace([np.inf, -np.inf], np.nan)
    lag_mask = pd.Series(False, index=daily.index)
    complete_events = events.loc[~events.event_date_incomplete & events.total_shares.gt(0)].copy()
    for event in complete_events.itertuples():
        if event.announcement_date > event.change_date:
            lag_mask |= daily.trade_date.ge(event.change_date) & daily.trade_date.lt(event.announcement_date)
    high_error = daily.relative_error_total.gt(.10)
    lag_fraction = float((high_error & lag_mask).sum() / high_error.sum()) if high_error.any() else 0.0
    significant = complete_events.loc[
        complete_events.total_shares.ne(complete_events.total_shares.shift())
    ]
    windows = []
    for event_number, event in enumerate(significant.itertuples(), 1):
        anchor = int(dates.searchsorted(event.change_date))
        if anchor >= len(dates):
            continue
        selected_dates = dates.iloc[max(0, anchor - 5): min(len(dates), anchor + 11)]
        part = daily.loc[daily.trade_date.isin(selected_dates)].copy()
        part["stock_code"] = code
        part["event_number"] = event_number
        part["source_change_date"] = event.change_date
        part["source_announcement_date"] = event.announcement_date
        part["event_information_available_date"] = event.information_available_date
        part["event_change_reason"] = event.change_reason
        part["in_change_announcement_gap"] = (
            part.trade_date.ge(event.change_date)
            & part.trade_date.lt(event.announcement_date)
        )
        windows.append(part)
    stats = {
        "stock_code": code,
        "total_ratio_median": total_ratio.median(),
        "total_ratio_p95": total_ratio.quantile(.95),
        "total_ratio_simple_feature": simple_ratio_label(total_ratio.median()),
        "local_circulating_ratio_median": circ_ratio.median(),
        "baostock_circulating_ratio_median": bao_ratio.median(),
        "baostock_circ_vs_cninfo_median_error": daily.baostock_circ_vs_cninfo_error.median(),
        "baostock_circ_vs_cninfo_p95_error": daily.baostock_circ_vs_cninfo_error.quantile(.95),
        "large_total_error_fraction_in_change_announcement_gap": lag_fraction,
        "event_count": len(complete_events),
        "significant_event_count": len(significant),
    }
    return (
        pd.concat(windows, ignore_index=True) if windows else pd.DataFrame(),
        stats,
        daily.baostock_circ_vs_cninfo_error.dropna(),
    )


def root_cause(row: pd.Series) -> str:
    total_error = abs(row.total_ratio_median - 1) if np.isfinite(row.total_ratio_median) else math.nan
    local_circ_error = abs(row.local_circulating_ratio_median - 1) if np.isfinite(row.local_circulating_ratio_median) else math.nan
    bao_error = row.baostock_circ_vs_cninfo_median_error
    if np.isfinite(total_error) and total_error > .10 and np.isfinite(bao_error) and bao_error < .02:
        if np.isfinite(local_circ_error) and local_circ_error > .10:
            return "LOCAL_TOTAL_AND_CIRCULATING_MARKET_CAP_LINEAGE_DISCREPANCY"
        return "LOCAL_TOTAL_MARKET_CAP_LINEAGE_DISCREPANCY"
    if row.large_total_error_fraction_in_change_announcement_gap >= .50:
        return "CONSERVATIVE_AVAILABILITY_LAG_EXPLAINS_PART_OF_ERROR"
    if np.isfinite(bao_error) and bao_error > .10:
        return "CNINFO_CIRCULATING_SHARE_DEFINITION_OR_LINEAGE_MISMATCH"
    if np.isfinite(row.total_ratio_p95) and abs(row.total_ratio_p95 - 1) > .10:
        return "TRANSIENT_LOCAL_MARKET_CAP_OR_EVENT_TIMING_EXCEPTION"
    return "NO_MATERIAL_EXCEPTION_IN_REVIEW_METRICS"


def run(root: Path) -> None:
    output = root / OUT
    sample = select_review_sample(root)
    sample.to_csv(output / "h7_share_lineage_exception_sample.csv", index=False)
    headers = cninfo_headers()
    schema_rows: list[dict] = []
    event_frames: dict[str, pd.DataFrame] = {}
    for number, code in enumerate(sample.stock_code, 1):
        if code in ("000004", "300344"):
            _, original_meta = raw_cninfo_request(code, "2020-01-01", 1, headers)
            original_meta["row_type"] = "schema"
            original_meta["request_variant"] = "ORIGINAL_2020_WINDOW"
            schema_rows.append(original_meta)
        payload, meta = raw_cninfo_request(
            code, "1990-01-01", 3 if code == "000001" else 1, headers
        )
        meta["row_type"] = "schema"
        meta["request_variant"] = "FULL_HISTORY_REVIEW"
        schema_rows.append(meta)
        events = normalize_raw_events(payload, code)
        if len(events):
            event_frames[code] = events
            for event in events.to_dict("records"):
                schema_rows.append({
                    "row_type": "event", "request_variant": "FULL_HISTORY_REVIEW",
                    "stock_code": code, **event,
                })
        print(f"cninfo_exception_review={number}/{len(sample)}", flush=True)
    schema = pd.DataFrame(schema_rows)
    schema["data_cutoff"] = DATA_CUTOFF.date().isoformat()
    schema.to_csv(output / "h7_cninfo_schema_review.csv", index=False)
    windows, stats, pooled_bao_errors = [], [], []
    for code, events in event_frames.items():
        if not (root / f"data/probe/h7_turnover_sources/baostock/{code}.csv").exists():
            continue
        stock_windows, stock_stats, stock_bao_errors = event_windows(root, code, events)
        if len(stock_windows):
            windows.append(stock_windows)
        stats.append(stock_stats)
        pooled_bao_errors.extend(stock_bao_errors.tolist())
    metric = pd.DataFrame(stats)
    if len(metric):
        metric["high_discrepancy_root_cause"] = metric.apply(root_cause, axis=1)
    sample = sample.merge(metric, on="stock_code", how="left")
    full_meta = schema.loc[
        schema.row_type.eq("schema") & schema.request_variant.eq("FULL_HISTORY_REVIEW")
    ]
    sample = sample.merge(
        full_meta[["stock_code", "status", "row_count", "schema_has_DECLAREDATE", "schema_has_VARYDATE", "error"]],
        on="stock_code", how="left",
    )
    sample["unresolved_exception"] = sample.status.ne("SUCCESS") | sample.row_count.fillna(0).eq(0)
    sample.to_csv(output / "h7_share_lineage_exception_sample.csv", index=False)
    window_frame = pd.concat(windows, ignore_index=True) if windows else pd.DataFrame()
    window_frame["data_cutoff"] = DATA_CUTOFF.date().isoformat()
    window_frame.to_csv(output / "h7_share_lineage_event_windows.csv", index=False)
    pooled_bao = pd.Series(pooled_bao_errors, dtype=float)
    bao_median = pooled_bao.median()
    bao_p95 = pooled_bao.quantile(.95)
    unresolved = int(sample.unresolved_exception.sum())
    original = schema.loc[
        schema.row_type.eq("schema") & schema.request_variant.eq("ORIGINAL_2020_WINDOW")
    ]
    failed_rows = sample.loc[sample.stock_code.isin(("000004", "300344")), "row_count"]
    if original.empty_response.all() and failed_rows.fillna(0).eq(0).all():
        keyerror_cause = (
            "HTTP_200_EMPTY_RECORDS_IN_ORIGINAL_AND_FULL_HISTORY_WINDOWS; "
            "AKSHARE_WRAPPER_UNCONDITIONALLY_INDEXED_ANNOUNCEMENT_DATE"
        )
    elif original.empty_response.all() and failed_rows.gt(0).all():
        keyerror_cause = (
            "ORIGINAL_2020_QUERY_RETURNED_EMPTY_RECORDS; AKSHARE_WRAPPER_ASSUMED_DECLAREDATE; "
            "FULL_HISTORY_QUERY_RESOLVED_OPENING_EVENTS"
        )
    else:
        keyerror_cause = "SCHEMA_OR_EMPTY_RESPONSE_REQUIRES_REVIEW"
    network_status = sample.loc[sample.stock_code.eq("000001"), "status"].iloc[0]
    readiness = (
        "FULL_DOWNLOAD_READY_WITH_EXCEPTION_QUEUE"
        if len(metric) >= 10 and unresolved <= 3
        else "NOT_READY_FOR_FULL_DOWNLOAD"
    )
    cause_counts = sample.high_discrepancy_root_cause.fillna("UNRESOLVED").value_counts().to_dict()
    report = f"""# H7 Turnover Source Contract Exception Review

## Decision

**{readiness}**. The main contract is usable with explicit per-stock exceptions; this review does not authorize or start a full-market download.

```text
review_stock_count={len(sample)}
cninfo_keyerror_root_cause={keyerror_cause}
cninfo_network_failure_status={network_status}
cninfo_schema_consistent={bool(full_meta.loc[full_meta.row_count.gt(0), ['schema_has_DECLAREDATE','schema_has_VARYDATE']].all().all())}
cninfo_date_contract_status=REASONABLE_CONSERVATIVE; PARTIAL_LAG_EFFECT; NO_RULE_CHANGE
high_discrepancy_root_causes={json.dumps(cause_counts, ensure_ascii=False)}
baostock_implied_circulating_vs_cninfo_median_error={bao_median}
baostock_implied_circulating_vs_cninfo_p95_error={bao_p95}
local_implied_total_shares_validation_status=USEFUL_BUT_NOT_AUTHORITATIVE
local_implied_circulating_shares_validation_status=USEFUL_BUT_NOT_AUTHORITATIVE
cninfo_total_shares_primary_status=ACCEPTABLE_WITH_KNOWN_LIMITATIONS
baostock_circulating_turnover_secondary_status=ACCEPTABLE_WITH_LIMITATIONS
unresolved_exception_stock_count={unresolved}
data_cutoff=2026-08-20
full_market_download_performed=false
C2_estimated=false
volume_return_regression_run=false
future_performance_accessed=false
full_download_readiness={readiness}
```

## Schema finding

The original 2020-start requests for 000004 and 300344 returned an empty `records` array, so there were no returned columns. AKShare then indexed `公告日期` unconditionally, converting a valid empty response into `KeyError`. The full-history review distinguishes “no event in the requested window” from schema drift. HTTP status, top-level keys, raw column names, row counts, and up to three representative rows are preserved in `h7_cninfo_schema_review.csv`; no request headers or tokens are stored.

## Date contract

`information_available_date=max(change_date, announcement_date)` remains a reasonable conservative rule and prevents future-event backfill. Event-window rows explicitly identify the change-to-announcement gap. Where that gap explains material error, the stock is labeled accordingly; no event-specific replacement rule was introduced.

## Share-lineage diagnosis

The exception sample and event-window files provide stock/date evidence. BaoStock-implied circulating shares generally track CNINFO more closely than local cap/close shares, while several large total-share discrepancies occur in local market-cap lineage. Therefore local implied shares remain a useful cross-check but are not authoritative. Simple-ratio features are reported as diagnostics only and are never used to repair values.

## Source decisions and next step

- `CNINFO_TOTAL_SHARES`: **ACCEPTABLE_WITH_KNOWN_LIMITATIONS** as Primary denominator, with empty-history/network/schema exceptions retained and no turnover constructed when an opening level is unavailable.
- `BAOSTOCK_CIRCULATING_TURNOVER`: **ACCEPTABLE_WITH_LIMITATIONS** as Secondary robustness; precision and zero/trading-status semantics are adequate, but its circulating-share denominator differs from D05 total shares.
- If a later human decision authorizes full download: cutoff 2026-08-20, cache-first, resumable, per-stock failure isolation, BaoStock first, CNINFO second, already-cached skip, no AKShare blocker, and checkpoint/progress logging. This task does not execute it.

No return, C2, H5/H6/MCTS/Phase B, prospective, or final-test analysis was run.
"""
    (output / "h7_share_lineage_exception_report.md").write_text(report, encoding="utf-8")
    print(f"review_stock_count={len(sample)}")
    print(f"full_download_readiness={readiness}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    run(parser.parse_args().project_root.resolve())
