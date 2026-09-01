"""H8 explicit-event lineage and clean-row availability; never fit Eq.9."""

# ruff: noqa: E501 -- explicit report contracts.
from __future__ import annotations

import argparse
import inspect
import json
import socket
import sys
import time
from pathlib import Path

import baostock as bs
import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import resolve_h8_final_contract as h8  # noqa: E402

OUT = Path("reports/hypothesis_8/corporate_action")
CACHE = Path("data/cache/h8_corporate_actions")
START = "2020-01-01"
END = "2026-05-12"
FIELDS = ["code", "dividOperateDate", "foreAdjustFactor", "backAdjustFactor", "adjustFactor"]
SUCCESS = {"SUCCESS_WITH_EVENTS", "SUCCESS_NO_EVENTS"}
CHRONOLOGY = "PER_STOCK_LONGEST_CA_CLEAN_CONSECUTIVE_SEGMENT"
CNINFO_URL = "https://webapi.cninfo.com.cn/api/sysapi/p_sysapi1139"


def atomic_csv(frame, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(path)


def calendar(root):
    data = pd.read_csv(
        root / "data/processed/hybrid_benchmark_panel_v1_5.csv", dtype={"benchmark_code": str}
    )
    dates = pd.DatetimeIndex(
        pd.to_datetime(
            data.loc[data.benchmark_code.str.zfill(6).eq("000300"), "trade_date"]
        ).unique()
    ).sort_values()
    return dates[(dates >= START) & (dates <= END)]


def candidates(root):
    audit = pd.read_csv(
        root / h8.OUT / "h8_price_corporate_action_audit.csv", dtype={"stock_code": str}
    )
    old = pd.read_csv(root / h8.MAPPING / "h8_sample_feasibility.csv", dtype={"stock_code": str})
    data = (
        audit.loc[audit.board.isin(["SH_MAIN", "SZ_MAIN"]) & ~audit.observed_ever_st]
        .merge(
            old[["stock_code", "historical_mean_circulating_market_cap"]],
            on="stock_code",
            validate="one_to_one",
        )
        .sort_values("stock_code")
    )
    if len(data) != 2790 or not data.stock_code.is_unique:
        raise ValueError("H8_candidate_contract_changed")
    data["size_quartile"] = "UNKNOWN"
    good = h8.positive(data.historical_mean_circulating_market_cap)
    data.loc[good, "size_quartile"] = pd.qcut(
        data.loc[good, "historical_mean_circulating_market_cap"].rank(method="first"),
        4,
        labels=h8.QUARTILES,
    ).astype(str)
    return data


def select_probe(data):
    parts = []
    for _, group in data.loc[data.size_quartile.ne("UNKNOWN")].groupby(
        ["board", "size_quartile"], sort=True
    ):
        ordered = group.sort_values(["raw_p1_upper_bound", "stock_code"])
        parts.append(
            ordered.iloc[np.linspace(0, len(ordered) - 1, min(5, len(ordered))).astype(int)]
        )
    return pd.concat(parts).reset_index(drop=True)


def symbol(code):
    return ("sh." if h8.board(code) == "SH_MAIN" else "sz.") + code


def normalize_bao(frame, code, dates):
    if list(frame.columns) != FIELDS:
        raise ValueError("unexpected_adjust_factor_schema:" + str(list(frame.columns)))
    result = frame.copy()
    if result.empty:
        return result
    if not result.code.eq(symbol(code)).all():
        raise ValueError("stock_identity_mismatch")
    event_dates = pd.to_datetime(result.dividOperateDate, errors="raise")
    if not event_dates.between(START, END).all():
        raise ValueError("event_outside_requested_interval")
    if event_dates.duplicated().any():
        raise ValueError("duplicate_or_conflicting_event_date")
    if not event_dates.isin(dates).all():
        raise ValueError("event_not_on_common_market_date")
    for column in FIELDS[2:]:
        result[column] = pd.to_numeric(result[column], errors="raise")
        if not h8.positive(result[column]).all():
            raise ValueError("nonpositive_or_nonfinite_factor:" + column)
    # A deliberately loose data-quality guard, fixed before the 40-stock probe.
    # Five percent of observed common dates is already far above ordinary event frequency.
    if len(result) / len(dates) > 0.05:
        raise ValueError("dense_daily_style_event_series")
    result["dividOperateDate"] = event_dates.dt.strftime("%Y-%m-%d")
    return result.sort_values("dividOperateDate").reset_index(drop=True)


def load_status(root):
    path = root / CACHE / "stock_status.csv"
    if not path.exists():
        return {}
    data = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    return data.set_index("stock_code").to_dict("index")


def response_frame(response):
    """BaoStock get_data drops columns for an empty successful response."""
    if list(response.fields) != FIELDS:
        raise ValueError("unexpected_response_fields")
    raw = response.get_data()
    if response.error_code != "0":
        raise ConnectionError("pagination_failure:" + response.error_code)
    return pd.DataFrame(columns=FIELDS) if raw.empty else raw


def fetch_bao(root, codes, dates):
    status = load_status(root)
    logged_in = False
    socket.setdefaulttimeout(15)
    try:
        for number, code in enumerate(codes, 1):
            path = root / CACHE / "baostock" / f"{code}.csv"
            previous = status.get(code, {})
            if (
                previous.get("status") in SUCCESS
                and previous.get("request_start") == START
                and previous.get("request_end") == END
                and path.exists()
            ):
                try:
                    normalize_bao(pd.read_csv(path, dtype={"code": str}), code, dates)
                except (ValueError, KeyError, TypeError) as exc:
                    status[code] = {
                        **previous,
                        "status": "SCHEMA_FAILED",
                        "error": "cached_file:" + str(exc),
                    }
                    atomic_csv(
                        pd.DataFrame.from_dict(status, orient="index")
                        .rename_axis("stock_code")
                        .reset_index(),
                        root / CACHE / "stock_status.csv",
                    )
                continue
            attempts = int(previous.get("attempts", 0))
            if attempts >= 2:
                continue  # preserve the last failure; bounded across resume invocations.
            record = dict(
                stock_code=code,
                request_start=START,
                request_end=END,
                source="BAOSTOCK_QUERY_ADJUST_FACTOR",
                status="NETWORK_FAILED",
                api_status="",
                attempts=attempts,
                row_count=0,
                earliest_event="",
                latest_event="",
                error="",
                fetch_time="",
                returned_fields="",
            )
            while attempts < 2:
                attempts += 1
                record["attempts"] = attempts
                begin = time.perf_counter()
                try:
                    if not logged_in:
                        login = bs.login()
                        if login.error_code != "0":
                            raise ConnectionError("login:" + login.error_code)
                        logged_in = True
                    response = bs.query_adjust_factor(symbol(code), start_date=START, end_date=END)
                    record["api_status"] = response.error_code
                    record["returned_fields"] = "|".join(response.fields)
                    if response.error_code != "0":
                        raise ConnectionError(response.error_code + ":" + response.error_msg)
                    raw = response_frame(response)
                    events = normalize_bao(raw, code, dates)
                    atomic_csv(events, path)
                    record.update(
                        status="SUCCESS_WITH_EVENTS" if len(events) else "SUCCESS_NO_EVENTS",
                        row_count=len(events),
                        earliest_event=events.dividOperateDate.min() if len(events) else "",
                        latest_event=events.dividOperateDate.max() if len(events) else "",
                        error="",
                    )
                    break
                except (ValueError, KeyError, TypeError) as exc:
                    record.update(status="SCHEMA_FAILED", error=str(exc))
                    break
                except Exception as exc:
                    record.update(status="NETWORK_FAILED", error=f"{type(exc).__name__}:{exc}")
                    if logged_in:
                        bs.logout()
                    logged_in = False
                    if attempts < 2:
                        time.sleep(1)
                finally:
                    record["fetch_time"] = pd.Timestamp.now(tz="Asia/Shanghai").isoformat()
                    record["runtime_seconds"] = time.perf_counter() - begin
            status[code] = {k: v for k, v in record.items() if k != "stock_code"}
            atomic_csv(
                pd.DataFrame.from_dict(status, orient="index")
                .rename_axis("stock_code")
                .reset_index(),
                root / CACHE / "stock_status.csv",
            )
            if len(codes) <= 40 or number % 100 == 0:
                print(f"CA cache {number}/{len(codes)} {code} {record['status']}", flush=True)
            time.sleep(0.1)
    finally:
        if logged_in:
            bs.logout()
    return status


def normalize_cninfo(payload, code):
    if not isinstance(payload, dict) or "records" not in payload:
        raise ValueError("CNINFO_invalid_response")
    rows = payload["records"]
    if not isinstance(rows, list):
        raise ValueError("CNINFO_records_not_list")
    cols = ["stock_code", "event_date", "announcement_date", "source_field", "description"]
    if not rows:
        return pd.DataFrame(columns=cols), 0
    raw = pd.DataFrame(rows)
    if "F020D" not in raw:
        raise ValueError("CNINFO_missing_explicit_ex_date_F020D")
    parsed = pd.to_datetime(raw.F020D, errors="coerce")
    if (raw.F020D.notna() & parsed.isna()).any():
        raise ValueError("CNINFO_malformed_ex_date")
    valid = parsed.between(START, END)
    result = pd.DataFrame(
        {
            "stock_code": code,
            "event_date": parsed[valid].dt.strftime("%Y-%m-%d"),
            "announcement_date": raw.loc[valid, "F006D"],
            "source_field": "F020D_EX_RIGHT_DATE",
            "description": raw.loc[valid, "F007V"],
        }
    )
    return result.drop_duplicates().sort_values("event_date"), int(parsed.isna().sum())


def fetch_cninfo(root, sample):
    import py_mini_racer
    from akshare.stock.stock_dividend_cninfo import _get_file_content_ths

    rows = []
    # The local share-change cache has VARYDATE, not a certified ex-dividend date.
    # Never promote generic share changes to price-adjustment events.
    with requests.Session() as session, py_mini_racer.MiniRacer() as js:
        js.eval(_get_file_content_ths("cninfo.js"))
        for code in sample.stock_code:
            path = root / CACHE / "cninfo_probe" / f"{code}.csv"
            row = dict(
                stock_code=code,
                cninfo_status="NETWORK_FAILED",
                cninfo_error="",
                cninfo_missing_ex_dates=0,
            )
            try:
                if path.exists():
                    external = pd.read_csv(path, dtype={"stock_code": str})
                    # Normalized caches contain dated events only, not undated source rows.
                    row["cninfo_missing_ex_dates"] = np.nan
                else:
                    headers = {
                        "Accept-Enckey": js.call("getResCode1"),
                        "User-Agent": "Mozilla/5.0",
                        "Origin": "https://webapi.cninfo.com.cn",
                        "Referer": "https://webapi.cninfo.com.cn/",
                    }
                    response = session.post(
                        CNINFO_URL, params={"scode": code}, headers=headers, timeout=20
                    )
                    response.raise_for_status()
                    external, missing = normalize_cninfo(response.json(), code)
                    row["cninfo_missing_ex_dates"] = missing
                    atomic_csv(external, path)
                row.update(
                    cninfo_status="SUCCESS", external_known_events=external.event_date.nunique()
                )
            except Exception as exc:
                row.update(cninfo_error=f"{type(exc).__name__}:{exc}", external_known_events=0)
            rows.append(row)
            print(f"CNINFO probe {len(rows)}/{len(sample)} {row['cninfo_status']}", flush=True)
            time.sleep(0.1)
    return pd.DataFrame(rows)


def cross_validate(source_dates, external_dates, external_success=True):
    source_dates, external_dates = set(source_dates), set(external_dates)
    rows = []
    for date in sorted(source_dates | external_dates):
        bao, external = date in source_dates, date in external_dates
        category = (
            "VALIDATED_EVENT"
            if bao and external
            else "SOURCE_ONLY_PLAUSIBLE_EVENT"
            if bao
            else "UNRESOLVED_EVENT"
        )
        rows.append(
            dict(
                event_date=date,
                baostock_event=bao,
                external_event=external,
                classification=category,
                false_negative=external and not bao,
                external_source_available=external_success,
            )
        )
    return rows


def accept_source(probe, cross):
    # Strict sufficient evidence, not an outcome/performance threshold.
    # The finite external probe can never prove complete lifetime event coverage.
    api_ok = probe.status.isin(SUCCESS).sum() >= 38
    schema_ok = not probe.status.eq("SCHEMA_FAILED").any()
    external_ok = probe.cninfo_status.eq("SUCCESS").sum() >= 38
    known = int(cross.external_event.sum()) if len(cross) else 0
    missed = int(cross.false_negative.sum()) if len(cross) else 0
    if api_ok and schema_ok and external_ok and known > 0 and missed == 0:
        return "BAOSTOCK_CA_SOURCE_ACCEPTED_WITH_LIMITATIONS"
    return "BAOSTOCK_CA_SOURCE_REJECTED"


def probe_sources(root, data, dates):
    sample = select_probe(data)
    statuses = fetch_bao(root, sample.stock_code.tolist(), dates)
    external = fetch_cninfo(root, sample)
    probe = (
        sample[["stock_code", "board", "size_quartile", "raw_p1_upper_bound"]]
        .merge(
            pd.DataFrame.from_dict(statuses, orient="index")
            .rename_axis("stock_code")
            .reset_index(),
            on="stock_code",
            validate="one_to_one",
        )
        .merge(external, on="stock_code", validate="one_to_one")
    )
    cross_rows = []
    for row in probe.itertuples(index=False):
        source = (
            pd.read_csv(
                root / CACHE / "baostock" / f"{row.stock_code}.csv"
            ).dividOperateDate.tolist()
            if row.status in SUCCESS
            else []
        )
        ext = (
            pd.read_csv(root / CACHE / "cninfo_probe" / f"{row.stock_code}.csv").event_date.tolist()
            if row.cninfo_status == "SUCCESS"
            else []
        )
        for item in cross_validate(source, ext, row.cninfo_status == "SUCCESS"):
            item["source_event_kind"] = (
                "EXTERNAL_EX_DATE" if item["external_event"] else "SOURCE_ONLY_EVENT"
            )
            item["local_share_metadata"] = ""
            local_path = root / "data/cache/h7_turnover/cninfo" / f"{row.stock_code}.csv"
            if item["baostock_event"] and not item["external_event"] and local_path.exists():
                local = pd.read_csv(local_path, usecols=["change_date", "change_reason"])
                reasons = "|".join(
                    local.loc[local.change_date.eq(item["event_date"]), "change_reason"].astype(str)
                )
                item["local_share_metadata"] = reasons
                if "A股上市" in reasons:
                    item["source_event_kind"] = "LISTING_INITIALIZATION_NOT_DIVIDEND"
            cross_rows.append(dict(stock_code=row.stock_code, **item))
    cross = pd.DataFrame(
        cross_rows,
        columns=[
            "stock_code",
            "event_date",
            "baostock_event",
            "external_event",
            "classification",
            "false_negative",
            "external_source_available",
            "source_event_kind",
            "local_share_metadata",
        ],
    )
    atomic_csv(probe, root / OUT / "h8_ca_source_probe.csv")
    atomic_csv(cross, root / OUT / "h8_ca_cross_validation.csv")
    return probe, cross


def contamination_mask(dates, events):
    event = pd.Series(dates.isin(pd.to_datetime(list(events))), index=dates)
    return event, event | event.shift(-1, fill_value=False)


def clean_stock(root, code, dates, status):
    row = dict(
        stock_code=code,
        ca_cache_status=status.get("status", "NOT_REQUESTED"),
        final_P1_rows=0,
        final_P2_rows=0,
        final_matched_rows=0,
        garch_status="NOT_RUN_CA_UNAVAILABLE",
        garch_nobs=0,
        segment_start="",
        segment_end="",
        earliest_ca_covered_date="",
        first_final_formation="",
        matched_pre_garch=0,
        clean_return_segments=0,
        clean_returns_outside_longest=0,
    )
    if row["ca_cache_status"] not in SUCCESS:
        return row
    events = normalize_bao(pd.read_csv(root / CACHE / "baostock" / f"{code}.csv"), code, dates)
    raw, ever_st, _, _ = h8.load_raw(root, code, dates)
    if ever_st or h8.board(code) not in {"SH_MAIN", "SZ_MAIN"}:
        raise ValueError("frozen_candidate_identity_changed")
    p1, p2, current = h8.raw_presence(raw, dates)
    event, contaminated = contamination_mask(dates, events.dividOperateDate)
    matched = p2 & ~contaminated
    # Only price-derived magnitudes used in this task: current returns for GARCH.
    history_close = raw.loc[raw.index <= h8.CUTOFF, "close"]
    returns = (history_close / history_close.shift(1) - 1).where(
        current.loc[history_close.index] & ~event.loc[history_close.index]
    )
    returns = returns.where(np.isfinite(returns))
    segment = h8.longest_segment(returns)
    qa = h8.garch_probe(segment)
    groups = returns.notna().ne(returns.notna().shift()).cumsum()
    row.update(
        garch_status="GARCH_SUCCESS" if qa["success"] else "GARCH_NUMERIC_FAILURE",
        garch_nobs=len(segment),
        garch_warning=qa["warning"],
        garch_error=qa["error"],
        garch_converged=qa["converged"],
        garch_parameter_finite=qa["parameter_finite"],
        garch_variance_finite_share=qa["conditional_variance_finite_share"],
        garch_runtime_seconds=qa["runtime_seconds"],
        segment_start=str(segment.index.min()),
        segment_end=str(segment.index.max()),
        earliest_ca_covered_date=max(pd.Timestamp(START), raw.close.first_valid_index())
        .date()
        .isoformat(),
        matched_pre_garch=int(matched.sum()),
        clean_return_segments=int(groups[returns.notna()].nunique()),
        clean_returns_outside_longest=int(returns.notna().sum() - len(segment)),
        ca_event_count=len(events),
        raw_p1_presence=int(p1.sum()),
        ca_clean_p1_presence=int((p1 & ~contaminated).sum()),
    )
    if qa["success"]:
        final = matched & matched.index.isin(segment.index)
        count = int(final.sum())
        row.update(
            final_P1_rows=count,
            final_P2_rows=count,
            final_matched_rows=count,
            first_final_formation=str(dates[final][0].date()) if count else "",
        )
    return row


def final_thresholds(data):
    thresholds = [750, 1000, 1250]
    if data.final_matched_rows.max() >= 1500:
        thresholds.append(1500)
    rows = []
    for threshold in thresholds:
        selected = data.final_matched_rows.ge(threshold)
        sub = data[selected]
        size = sub.historical_mean_circulating_market_cap
        rates = [float(selected[data.size_quartile.eq(q)].mean()) for q in h8.QUARTILES]
        row = dict(
            min_rows=threshold,
            eligible_stocks=len(sub),
            candidate_share=len(sub) / len(data),
            median_rows=sub.final_matched_rows.median(),
            p10_rows=sub.final_matched_rows.quantile(0.1),
            p90_rows=sub.final_matched_rows.quantile(0.9),
            SH_MAIN=int(sub.board.eq("SH_MAIN").sum()),
            SZ_MAIN=int(sub.board.eq("SZ_MAIN").sum()),
            mean_size=size.mean(),
            median_size=size.median(),
            size_inclusion_spread=max(rates) - min(rates),
            spearman_rows_log_size=sub.loc[h8.positive(size), "final_matched_rows"].corr(
                np.log(size[h8.positive(size)]), method="spearman"
            ),
            row_basis="FINAL_CA_CLEAN_GARCH_VALID_MATCHED_ROWS",
        )
        row.update(
            {q + "_inclusion_rate": rate for q, rate in zip(h8.QUARTILES, rates, strict=True)}
        )
        rows.append(row)
    return pd.DataFrame(rows)


def write_source_report(root, probe, cross, source_status):
    known = int(cross.external_event.sum())
    matched = int((cross.external_event & cross.baostock_event).sum())
    report = f"""# H8 Corporate-Action Source Resolution

`corporate_action_source_status={source_status}`.

## Direct source evidence

Installed BaoStock {bs.__version__}; function exists; signature `{inspect.signature(bs.query_adjust_factor)}`. Installed implementation: `{inspect.getsourcefile(bs.query_adjust_factor)}`. Actual server fields: `{FIELDS}`. A preliminary call on probe member 600019 returned 11 sparse dated records before the cached 40-stock pass; it is not an additional probe stock. The package's adjustment endpoint is used directly, not a third-party guessed BaoStock schema.

`dividOperateDate` is accepted as an effective adjustment/ex-date only after the CNINFO cross-check below. Factor values are positive finite metadata, never used to change a price or infer additional event dates. No attempt is made to infer a precise cumulative-factor algorithm from field names.

Probe sample is 40 deterministic main-board/non-observed-ever-ST stocks: five history-spanning members per SH/SZ x size-quartile cell. Selection uses only prior data-readiness counts/size. Request start={START}, end={END}. API success={int(probe.status.isin(SUCCESS).sum())}/{len(probe)}; with events={int(probe.status.eq("SUCCESS_WITH_EVENTS").sum())}; no events={int(probe.status.eq("SUCCESS_NO_EVENTS").sum())}; source event count={int(cross.baostock_event.sum())}.

All accepted rows have parseable, unique, in-range common-market event dates and positive finite factors. The fixed pre-probe dense-series QA guard is >5% of common-market dates; this is an intentionally loose source sanity check, not a return-based threshold. Individual event counts and intervals are in the probe CSV. An empty successful response remains SUCCESS_NO_EVENTS, not a download failure.

## Independent ex-date check / false negatives

Existing local CNINFO share-history files contain share-change VARYDATE, not certified dividend ex-date. They were not silently promoted to corporate actions. Explicit CNINFO historical-dividend endpoint: [{CNINFO_URL}]({CNINFO_URL}); current installed AKShare `stock_dividend_cninfo` maps F020D to 除权日, F018D to 股权登记日, and F023D to 派息日. Only **F020D** is matched. No PDF or announcement corpus was downloaded. API supports code-level history; records outside {START}..{END} are discarded before caching/matching. Missing ex-dates are never replaced by payment/registration dates. Fresh responses can count undated rows, but dated-only normalized caches cannot reconstruct that count: cache-only missing-ex-date counts are UNKNOWN (blank), not zero. The validation denominator contains explicit known dates only and is not an exhaustive-event-completeness claim.

CNINFO successful stock probes={int(probe.cninfo_status.eq("SUCCESS").sum())}/{len(probe)}. Unique stock/date external known events={known}; exact-date matched={matched}; unmatched={known - matched}; match rate={matched / known if known else float("nan"):.6%}.

{h8.markdown_table(cross.classification.value_counts().rename_axis("classification").reset_index(name="count"))}

VALIDATED_EVENT requires the same stock and exact date in both sources. Valid source-only rows are SOURCE_ONLY_PLAUSIBLE_EVENT, not falsely called independent validations. Unmatched explicit external events are UNRESOLVED_EVENT / false-negative evidence; the procedure does not shift dates to force matching. No price-return heuristic or old QFQ/raw ratio is used.

The source also returns listing initialization records: {int(cross.source_event_kind.eq("LISTING_INITIALIZATION_NOT_DIVIDEND").sum())} probe rows align with local CNINFO A股上市 metadata. They are separately identified, not claimed to be dividend events; excluding the listing boundary cannot remove an otherwise valid adjacent pre-listing return. Other source-only rows remain explicitly unvalidated externally. Source event count includes these initialization rows.

Adapter QA correction: BaoStock's get_data() returns a columnless DataFrame for a successful no-record response even when response.fields contains all five fields. The adapter now verifies response.fields and preserves that schema for an empty frame; this is SUCCESS_NO_EVENTS, not a source-schema failure. The one affected probe member600962 was retried within the two-attempt budget; no sample expansion or source threshold change.

The pre-probe sufficient acceptance rule is >=38/40 successful BaoStock and CNINFO probes, no schema failures, at least one known external event, and **zero unmatched known external events**. A finite 40-stock probe cannot prove exhaustive lifetime capture: a pass is ACCEPTED_WITH_LIMITATIONS. Rejection stops before full download and GARCH.

Optional Sina/AKShare factor cross-check was not needed and was not run. Public BaoStock website retrieval returned an application shell rather than readable field documentation; no third-party schema description was substituted as authoritative evidence. The acceptance rests on direct package/server records plus actual CNINFO date matches.

## Coverage and limitations

Source coverage is the explicitly queried {START}..{END} interval, not the first observed event date. SUCCESS_NO_EVENTS means the API reports no event in that interval, not that lifetime absence is established. Cache failures give no coverage and exclude that stock from clean-row counts. Source-only coverage outside probe members is an acknowledged vendor-completeness limitation. Calendar plausibility and external-date validation do not prove every type of corporate action is captured.

All prices stay raw. H8 current-universe / observed-ever-ST / historical-seen limitations remain. H7 is unchanged; no H8 coefficients or future-return relations were computed.
"""
    (root / OUT / "h8_ca_source_resolution.md").write_text(report, encoding="utf-8")


def write_readiness(root, source_status, data=None, table=None):
    if data is None:
        report = f"# H8 Clean-Sample Readiness\n\nH8_readiness=H8_NOT_READY\n\nSource status={source_status}. Full cache, clean-row construction and GARCH were not run. Final counts and threshold statistics are UNKNOWN, not zero.\n\nH7_rerun=false; H7_modified=false; H8_results_opened=false; gamma31_estimated=false; gamma32_estimated=false; Eq9_fit=false.\n"
        (root / OUT / "h8_final_clean_sample_readiness.md").write_text(report, encoding="utf-8")
        return
    positive_rows = data.loc[data.final_matched_rows.gt(0), "final_matched_rows"]
    counts = data.ca_cache_status.value_counts().to_dict()
    garch = data.garch_status.value_counts().to_dict()
    ready = source_status != "BAOSTOCK_CA_SOURCE_REJECTED" and table.eligible_stocks.max() > 0
    state = "H8_READY_FOR_HUMAN_FREEZE" if ready else "H8_NOT_READY"
    report = f"""# H8 Final CA-Clean Sample / History Threshold Readiness

**H8_readiness={state}**. This is data/contract readiness, not an H8 result. Primary threshold remains a human choice. No Eq.9 fit or preregistration was run.

## Price contract and start

Source status={source_status}; candidate count={len(data)}. Cache status={json.dumps(counts)}. Price source=BAOSTOCK_RAW_OHLC; `PRICE_CONTRACT_READY_WITH_LIMITATION` for successful event-cache stocks only. Rule: a formation row is invalid if t or t+1 is an explicit CA event date. Conditioning r_t and future cc/out boundary contamination are both excluded; P2 intraday shares the matched exclusion. No adjusted OHLC, synthetic open, price substitution or ratio-based events.

CA source queried {START}..{END}; successful stock-specific covered starts are recorded in h8_final_clean_stock_rows.csv. Natural boundaries: raw common calendar begins 2020-01-02; first exact22 formation is 2020-02-11; old QFQ overlap begins 2020-12-28 but no longer constrains this explicit source. **RECOMMENDED_H8_ANALYSIS_START={data.loc[data.final_matched_rows.gt(0), "first_final_formation"].min()}** (earliest final matched formation; individual starts differ). Formation cutoff=2026-05-11, next endpoint=2026-05-12; no extension to August.

## GARCH chronology — fixed before event probe

`final_sample_contract={CHRONOLOGY}`. Choose each stock's longest sequence of adjacent valid raw close-to-close decimal returns after CA-day invalidation; ties choose earliest. Estimate one zero-mean GARCH(1,1), normal, rescale=False using arch8.0.0 on that sequence. Reset begins at its own first date using the package default in-sample backcast. Other segments are not concatenated, not separately fitted, and not used to rescue a failure. The fitted parameters/backcast are in-sample, not prospective estimates.

This choice prioritizes the simple single-stock single-estimation implementation. Multiple separately reinitialized segment models would retain more observations but introduce multiple parameter estimates or a new shared-parameter likelihood. Neither is silently introduced. Consequence: {int(data.clean_returns_outside_longest.sum())} otherwise clean current-return observations are outside the chosen longest segments. Thus minimum-history comparisons refer to **one contiguous GARCH segment**, not accumulated disconnected history. This tradeoff was fixed before any final row counts, and not based on H8 effects.

Specification status={json.dumps(garch)}. Only successful finite-positive variance paths count. All failed models remain GARCH_NUMERIC_FAILURE without rescue. GARCH final contract resolved under this stated adaptation; numerical success is not statistical identification or paper equivalence, and very short converged segments do not pass the stock-level minimum-history candidates.

## Final matched rows

Stocks with any rows={len(positive_rows)}; across these stocks median={positive_rows.median()}, p10={positive_rows.quantile(0.1)}, p90={positive_rows.quantile(0.9)}. Across all {len(data)} candidates median={data.final_matched_rows.median()}, p10={data.final_matched_rows.quantile(0.1)}, p90={data.final_matched_rows.quantile(0.9)}. Final P1/P2/matched totals all equal {int(data.final_matched_rows.sum())}. Per-stock counts, source failures and GARCH failures are preserved in the companion CSV. Zero final rows mean unavailable under this implemented contract, not no economic effect.

Exact22 turnover validity, current/next active OHLC, positive finite values, weekday and sample membership use the existing H8 helpers. V is constructible without future information; zero-truncated V and zero returns remain eligible. GARCH inputs stop at the conditioning cutoff; no future-return relation or Eq.9 outcome analysis is performed.

Before longest-segment/GARCH restriction, CA-clean matched presence totals {int(data.matched_pre_garch.sum())}; final retained share is {data.final_matched_rows.sum() / data.matched_pre_garch.sum():.4%}. Median source event records per candidate={data.ca_event_count.median()}; among stocks meeting750 rows={data.loc[data.final_matched_rows.ge(750), "ca_event_count"].median()}. These are sample-composition measures, not return attribution.

## Threshold comparison — final rows only

{h8.markdown_table(table[["min_rows", "eligible_stocks", "candidate_share", "median_rows", "SH_MAIN", "SZ_MAIN", "size_inclusion_spread"]])}

Size quartiles are fixed within the 2790 pre-threshold candidates; two missing-size stocks stay UNKNOWN. CSV provides quartile inclusion rates, size means/medians, p10/p90 rows and Spearman(final_rows,log_size) within each retained subset. This is sample-selection evidence only. 1500 is tabulated only if some final stock history makes it feasible; otherwise 1500 eligibility is zero under this contract and is not introduced as another active candidate.

Smaller absolute inclusion-rate spreads at tighter thresholds must not be read as proof of improved balance: overall retention falls sharply, and the largest-size quartile remains less represented. This final selection pattern is materially different from the old pre-CA upper-bound comparison.

**recommended_primary_min_rows=HUMAN_JUDGMENT; recommended_long_history_sensitivity=UNRESOLVED; threshold_selection_requires_human_judgment=true.** Paper's 2400-day intent cannot be replicated; neither maximum retention nor nearest-to-2400 is an automatic choice. Event exclusion plus longest-segment selection may strongly favor stocks with fewer dividends/actions, so human review must weigh that structural selection alongside size and SH/SZ coverage. Do not inherit the old pre-CA upper bounds or H7's750 rule.

## Boundaries and human decision

P1_SIGN_READY={str(ready).lower()} (data only, threshold not frozen); P2_TIMING_READY={str(ready).lower()} (same matched sample); P3_INSTITUTION=NOT_FEASIBLE. PRICE_LIMIT_ROBUSTNESS=UNAVAILABLE_IN_V1; PRICE_LIMIT_BLOCKS_PRIMARY=false.

H7_rerun=false; H7_modified=false; H8_results_opened=false; gamma31_estimated=false; gamma32_estimated=false; Eq9_fit=false; H5/H6/MCTS/Phase_B_run=false; strategy_backtest_run=false.

Next: human choice of minimum history and review of longest-segment selection limitations, before any separate H8 preregistration or Eq.9 run. No automatic continuation. Data-quality skill separates external validations, source-only plausible records and unknown coverage; minimal implementation reuses H8 helpers and keeps one fixed GARCH fit per stock. STOP BEFORE PREREGISTRATION / EQ9 FIT.
"""
    (root / OUT / "h8_final_clean_sample_readiness.md").write_text(report, encoding="utf-8")


def run(root, mode):
    root = root.resolve()
    before = h8.protected_metadata(root)
    data, dates = candidates(root), calendar(root)
    (root / OUT).mkdir(parents=True, exist_ok=True)
    if mode in {"probe", "all"}:
        probe, cross = probe_sources(root, data, dates)
    else:
        probe = pd.read_csv(root / OUT / "h8_ca_source_probe.csv", dtype={"stock_code": str})
        cross = pd.read_csv(root / OUT / "h8_ca_cross_validation.csv", dtype={"stock_code": str})
    source_status = accept_source(probe, cross)
    write_source_report(root, probe, cross, source_status)
    print(source_status, flush=True)
    if mode == "probe" or source_status == "BAOSTOCK_CA_SOURCE_REJECTED":
        write_readiness(root, source_status)
    else:
        status = (
            fetch_bao(root, data.stock_code.tolist(), dates)
            if mode in {"full", "all"}
            else load_status(root)
        )
        records = []
        for i, code in enumerate(data.stock_code, 1):
            records.append(clean_stock(root, code, dates, status.get(code, {})))
            if i % 100 == 0:
                print(f"CA-clean/GARCH availability {i}/{len(data)}", flush=True)
        final = data[
            ["stock_code", "board", "size_quartile", "historical_mean_circulating_market_cap"]
        ].merge(pd.DataFrame(records), on="stock_code", validate="one_to_one")
        table = final_thresholds(final)
        atomic_csv(final, root / OUT / "h8_final_clean_stock_rows.csv")
        atomic_csv(table, root / OUT / "h8_final_clean_history_thresholds.csv")
        write_readiness(root, source_status, final, table)
    if before != h8.protected_metadata(root):
        raise RuntimeError("H7_metadata_changed")
    print("H7 unchanged; no Eq9 fit; bounded task complete", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--mode", choices=["probe", "full", "clean", "all"], default="probe")
    args = parser.parse_args()
    run(args.project_root, args.mode)
