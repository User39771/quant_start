"""Extend accepted H8 CA lineage and recompute eligibility only; never fit Eq.9."""

# ruff: noqa: E501 -- explicit audit fields and report contract.
from __future__ import annotations

import argparse
import socket
import sys
import time
from pathlib import Path

import baostock as bs
import numpy as np
import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import resolve_h8_corporate_action_lineage as ca
from scripts import resolve_h8_final_contract as h8

OUT = Path("reports/hypothesis_8/cutoff_extension")
STATUS_NAME = "h8_ca_incremental_20260513_20260820_status.csv"
INCREMENTAL_START = "2026-05-13"
DATA_CUTOFF = pd.Timestamp("2026-08-20")
ANALYSIS_START = pd.Timestamp("2020-02-11")
OLD_FORMATION_CUTOFF = pd.Timestamp("2026-05-11")
SUCCESS = {"SUCCESS_WITH_NEW_EVENTS", "SUCCESS_NO_NEW_EVENTS"}
THRESHOLDS = (750, 1000, 1250, 1500)


def market_calendar(root: Path) -> pd.DatetimeIndex:
    """Use a long-listed BaoStock main-board file as the frozen common-market calendar."""
    frame = pd.read_csv(root / h8.BAO / "600000.csv", usecols=["trade_date"])
    dates = pd.DatetimeIndex(pd.to_datetime(frame.trade_date)).sort_values().unique()
    dates = dates[(dates >= ca.START) & (dates <= DATA_CUTOFF)]
    if dates.empty or dates[-1] != DATA_CUTOFF:
        raise ValueError("final_market_endpoint_unavailable")
    return dates


def formation_cutoff(dates: pd.DatetimeIndex) -> tuple[pd.Timestamp, pd.Timestamp]:
    endpoint = dates[dates <= DATA_CUTOFF][-1]
    prior = dates[dates < endpoint]
    if prior.empty:
        raise ValueError("no_prior_market_date")
    return endpoint, prior[-1]


def normalize_increment(frame: pd.DataFrame, code: str, dates: pd.DatetimeIndex) -> pd.DataFrame:
    if list(frame.columns) != ca.FIELDS:
        raise ValueError("unexpected_adjust_factor_schema:" + str(list(frame.columns)))
    out = frame.copy()
    if out.empty:
        return out
    if not out.code.eq(ca.symbol(code)).all():
        raise ValueError("stock_identity_mismatch")
    event_dates = pd.to_datetime(out.dividOperateDate, errors="raise")
    if not event_dates.between(INCREMENTAL_START, DATA_CUTOFF).all():
        raise ValueError("event_outside_incremental_interval")
    if event_dates.duplicated().any() or not event_dates.isin(dates).all():
        raise ValueError("duplicate_or_nonmarket_event_date")
    for column in ca.FIELDS[2:]:
        out[column] = pd.to_numeric(out[column], errors="raise")
        if not h8.positive(out[column]).all():
            raise ValueError("nonpositive_or_nonfinite_factor:" + column)
    out["dividOperateDate"] = event_dates.dt.strftime("%Y-%m-%d")
    return out.sort_values("dividOperateDate").reset_index(drop=True)


def merge_events(old: pd.DataFrame, new: pd.DataFrame) -> tuple[pd.DataFrame, list[str]]:
    """Merge by event date; never choose between conflicting factor metadata."""
    combined = old[ca.FIELDS].copy() if new.empty else pd.concat(
        [old[ca.FIELDS], new[ca.FIELDS]], ignore_index=True
    )
    conflicts: list[str] = []
    for date, group in combined.groupby("dividOperateDate", sort=True):
        metadata = group[ca.FIELDS[2:]].drop_duplicates()
        if len(metadata) > 1:
            conflicts.append(str(date))
    if conflicts:
        return combined.iloc[:0], conflicts
    merged = combined.drop_duplicates("dividOperateDate", keep="first")
    return merged.sort_values("dividOperateDate").reset_index(drop=True), conflicts


def load_increment_status(root: Path) -> dict[str, dict]:
    path = root / OUT / STATUS_NAME
    if not path.exists():
        return {}
    frame = pd.read_csv(path, dtype={"stock_code": str}).fillna("")
    return frame.set_index("stock_code").to_dict("index")


def write_status(root: Path, status: dict[str, dict]) -> None:
    frame = pd.DataFrame.from_dict(status, orient="index").rename_axis("stock_code").reset_index()
    for attempt in range(5):
        try:
            ca.atomic_csv(frame.sort_values("stock_code"), root / OUT / STATUS_NAME)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.2 * (attempt + 1))


def _valid_merged_cache(path: Path, code: str, dates: pd.DatetimeIndex) -> bool:
    try:
        frame = pd.read_csv(path, dtype={"code": str})
        if list(frame.columns) != ca.FIELDS or frame.dividOperateDate.duplicated().any():
            return False
        event_dates = pd.to_datetime(frame.dividOperateDate, errors="raise")
        if (event_dates > DATA_CUTOFF).any() or not event_dates.isin(dates).all():
            return False
        if len(frame) and not frame.code.eq(ca.symbol(code)).all():
            return False
        return all(h8.positive(pd.to_numeric(frame[c], errors="coerce")).all() for c in ca.FIELDS[2:])
    except (OSError, ValueError, KeyError, TypeError):
        return False


def fetch_increment(root: Path, codes: list[str], dates: pd.DatetimeIndex) -> dict[str, dict]:
    status = load_increment_status(root)
    logged_in = False
    socket.setdefaulttimeout(15)
    try:
        for number, code in enumerate(codes, 1):
            path = root / ca.CACHE / "baostock" / f"{code}.csv"
            previous = status.get(code, {})
            if previous.get("status") in SUCCESS and _valid_merged_cache(path, code, dates):
                continue
            attempts = int(previous.get("attempts", 0) or 0)
            if attempts >= 2:
                continue
            record = dict(
                request_start=INCREMENTAL_START,
                request_end=str(DATA_CUTOFF.date()),
                source="BAOSTOCK_QUERY_ADJUST_FACTOR",
                status="NETWORK_FAILED",
                api_status="",
                attempts=attempts,
                new_event_count=0,
                merged_event_count=0,
                metadata_conflicts=0,
                conflict_dates="",
                error="",
                fetch_time="",
                runtime_seconds=np.nan,
            )
            old = pd.read_csv(path, dtype={"code": str}) if path.exists() else None
            if old is None or not _valid_merged_cache(path, code, dates):
                record.update(status="SCHEMA_FAILED", error="old_cache_missing_or_invalid")
                status[code] = record
                write_status(root, status)
                continue
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
                    response = bs.query_adjust_factor(
                        ca.symbol(code),
                        start_date=INCREMENTAL_START,
                        end_date=str(DATA_CUTOFF.date()),
                    )
                    record["api_status"] = response.error_code
                    if response.error_code != "0":
                        raise ConnectionError(response.error_code + ":" + response.error_msg)
                    new = normalize_increment(ca.response_frame(response), code, dates)
                    merged, conflicts = merge_events(old, new)
                    if conflicts:
                        record.update(
                            status="CA_METADATA_CONFLICT",
                            metadata_conflicts=len(conflicts),
                            conflict_dates="|".join(conflicts),
                            error="date_factor_metadata_conflict",
                        )
                        break
                    ca.atomic_csv(merged, path)
                    record.update(
                        status="SUCCESS_WITH_NEW_EVENTS" if len(new) else "SUCCESS_NO_NEW_EVENTS",
                        new_event_count=len(new),
                        merged_event_count=len(merged),
                        error="",
                    )
                    break
                except (ValueError, KeyError, TypeError) as exc:
                    record.update(status="SCHEMA_FAILED", error=f"{type(exc).__name__}:{exc}")
                    break
                except Exception as exc:  # network errors are bounded and stock-local
                    record.update(status="NETWORK_FAILED", error=f"{type(exc).__name__}:{exc}")
                    if logged_in:
                        bs.logout()
                    logged_in = False
                    if attempts < 2:
                        time.sleep(1)
                finally:
                    record["fetch_time"] = pd.Timestamp.now(tz="Asia/Shanghai").isoformat()
                    record["runtime_seconds"] = time.perf_counter() - begin
            status[code] = record
            write_status(root, status)
            if number % 100 == 0 or len(codes) <= 40:
                print(f"H8 CA increment {number}/{len(codes)} {code} {record['status']}", flush=True)
            time.sleep(0.1)
    finally:
        if logged_in:
            bs.logout()
    return status


def select_cninfo_sanity(root: Path, status: dict[str, dict]) -> pd.DataFrame:
    rows = []
    for code, record in status.items():
        if record.get("status") != "SUCCESS_WITH_NEW_EVENTS":
            continue
        events = pd.read_csv(root / ca.CACHE / "baostock" / f"{code}.csv")
        events = events[pd.to_datetime(events.dividOperateDate).between(INCREMENTAL_START, DATA_CUTOFF)]
        for event in events.itertuples(index=False):
            rows.append(
                dict(
                    stock_code=code,
                    board=h8.board(code),
                    event_date=event.dividOperateDate,
                    event_month=str(event.dividOperateDate)[:7],
                    factor_signature=f"{event.foreAdjustFactor}|{event.backAdjustFactor}|{event.adjustFactor}",
                )
            )
    data = pd.DataFrame(rows)
    if data.empty:
        return data
    data = data.sort_values(["event_month", "board", "factor_signature", "stock_code", "event_date"])
    chosen = data.groupby(["event_month", "board"], sort=True).head(1)
    remaining = data.loc[~data.index.isin(chosen.index)]
    return pd.concat([chosen, remaining]).head(20).reset_index(drop=True)


def cninfo_sanity(root: Path, status: dict[str, dict]) -> pd.DataFrame:
    """Small optional exact-date check; network failure never revises old source acceptance."""
    sample = select_cninfo_sanity(root, status)
    if sample.empty:
        ca.atomic_csv(sample, root / OUT / "h8_incremental_cninfo_sanity.csv")
        return sample
    import py_mini_racer
    from akshare.stock.stock_dividend_cninfo import _get_file_content_ths

    rows = []
    with requests.Session() as session, py_mini_racer.MiniRacer() as js:
        js.eval(_get_file_content_ths("cninfo.js"))
        for item in sample.itertuples(index=False):
            row = item._asdict()
            try:
                response = session.post(
                    ca.CNINFO_URL,
                    params={"scode": item.stock_code},
                    headers={
                        "Accept-Enckey": js.call("getResCode1"),
                        "User-Agent": "Mozilla/5.0",
                        "Origin": "https://webapi.cninfo.com.cn",
                        "Referer": "https://webapi.cninfo.com.cn/",
                    },
                    timeout=20,
                )
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get("records"), list):
                    raise ValueError("CNINFO_invalid_response")
                raw = pd.DataFrame(payload["records"])
                if "F020D" not in raw:
                    raise ValueError("CNINFO_missing_explicit_ex_date_F020D")
                dates = set(pd.to_datetime(raw.F020D, errors="coerce").dropna().dt.strftime("%Y-%m-%d"))
                row.update(
                    cninfo_status="SUCCESS",
                    exact_date_match=item.event_date in dates,
                    explicit_date_contradiction=False,
                    error="",
                )
            except Exception as exc:
                row.update(
                    cninfo_status="UNAVAILABLE",
                    exact_date_match=False,
                    explicit_date_contradiction=False,
                    error=f"{type(exc).__name__}:{exc}",
                )
            rows.append(row)
            time.sleep(0.1)
    result = pd.DataFrame(rows)
    ca.atomic_csv(result, root / OUT / "h8_incremental_cninfo_sanity.csv")
    return result


def raw_presence(raw: pd.DataFrame, dates: pd.DatetimeIndex, cutoff: pd.Timestamp):
    active = raw.trading_status.eq(1)
    close = active & h8.positive(raw.close)
    prior22 = (
        (active & h8.positive(raw.baostock_circulating_turnover))
        .shift(1, fill_value=False)
        .rolling(22, min_periods=22)
        .sum()
        .eq(22)
    )
    current = close & close.shift(1, fill_value=False)
    p1 = current & prior22 & h8.positive(raw.baostock_circulating_turnover)
    p1 &= close.shift(-1, fill_value=False) & pd.Series(dates <= cutoff, index=dates)
    p2 = p1 & (active & h8.positive(raw.open)).shift(-1, fill_value=False)
    return p1, p2, current


def clean_stock(root: Path, code: str, dates: pd.DatetimeIndex, cutoff: pd.Timestamp, status: dict):
    row = dict(
        stock_code=code,
        ca_increment_status=status.get("status", "NOT_REQUESTED"),
        new_CA_event_count=int(status.get("new_event_count", 0) or 0),
        final_P1_rows=0,
        final_P2_rows=0,
        final_matched_rows=0,
        garch_status="NOT_RUN_CA_UNAVAILABLE",
        garch_nobs=0,
        segment_start="",
        segment_end="",
        ca_event_count=0,
    )
    if row["ca_increment_status"] not in SUCCESS:
        return row
    events = pd.read_csv(root / ca.CACHE / "baostock" / f"{code}.csv", dtype={"code": str})
    if not _valid_merged_cache(root / ca.CACHE / "baostock" / f"{code}.csv", code, dates):
        row["ca_increment_status"] = "SCHEMA_FAILED"
        return row
    raw, ever_st, _, _ = h8.load_raw(root, code, dates)
    if ever_st or h8.board(code) not in {"SH_MAIN", "SZ_MAIN"}:
        raise ValueError("frozen_candidate_identity_changed")
    p1, p2, current = raw_presence(raw, dates, cutoff)
    event, contaminated = ca.contamination_mask(dates, events.dividOperateDate)
    matched = p2 & ~contaminated & pd.Series(dates >= ANALYSIS_START, index=dates)
    close = raw.loc[(raw.index >= ANALYSIS_START) & (raw.index <= cutoff), "close"]
    returns = (close / close.shift(1) - 1).where(current.loc[close.index] & ~event.loc[close.index])
    returns = returns.where(np.isfinite(returns))
    segment = h8.longest_segment(returns)
    qa = h8.garch_probe(segment)
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
        matched_pre_garch=int(matched.sum()),
        ca_event_count=len(events),
    )
    if qa["success"]:
        final = matched & matched.index.isin(segment.index)
        count = int(final.sum())
        row.update(final_P1_rows=count, final_P2_rows=count, final_matched_rows=count)
    return row


def segment_kind(old_start, old_end, new_start, new_end) -> str:
    values = [pd.to_datetime(x, errors="coerce") for x in (old_start, old_end, new_start, new_end)]
    os, oe, ns, ne = values
    if pd.isna(os) and pd.isna(ns):
        return "UNCHANGED"
    if os == ns and oe == ne:
        return "UNCHANGED"
    if os == ns and pd.notna(ne) and pd.notna(oe) and ne > oe:
        return "EXTENDED"
    if pd.notna(os) and pd.notna(ns) and os != ns:
        return "SWITCHED"
    return "SHORTENED_OR_OTHER"


def membership_reason(row) -> str:
    if row.GARCH_old_status != row.GARCH_new_status:
        return "GARCH_STATUS_CHANGE"
    if row.new_CA_event_count > 0 and (row.segment_changed or row.delta_rows != 0):
        return "NEW_CA_EVENT"
    if row.segment_transition == "SWITCHED":
        return "SEGMENT_SWITCH"
    if row.segment_transition == "EXTENDED":
        return "SEGMENT_EXTENSION"
    if row.delta_rows != 0:
        return "TAIL_EXTENSION" if row.delta_rows > 0 else "OTHER_DATA_AVAILABILITY"
    return "UNCHANGED"


def threshold_table(data: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold in THRESHOLDS:
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
            spearman_rows_log_size=data.loc[selected & h8.positive(data.historical_mean_circulating_market_cap), "final_matched_rows"].corr(
                np.log(data.loc[selected & h8.positive(data.historical_mean_circulating_market_cap), "historical_mean_circulating_market_cap"]),
                method="spearman",
            ),
        )
        row.update({q + "_count": int(sub.size_quartile.eq(q).sum()) for q in h8.QUARTILES})
        row.update({q + "_inclusion_rate": rate for q, rate in zip(h8.QUARTILES, rates, strict=True)})
        rows.append(row)
    return pd.DataFrame(rows)


def boundary_diagnostics(transitions: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for threshold, low, high in ((750, 700, 800), (1000, 950, 1050), (1250, 1200, 1300), (1500, 1450, 1550)):
        sample = transitions.old_rows.between(low, high)
        old, new = transitions.old_rows.ge(threshold), transitions.new_rows.ge(threshold)
        rows.append(
            dict(
                threshold=threshold,
                old_boundary_low=low,
                old_boundary_high=high,
                stocks=int(sample.sum()),
                crossed_upward=int((sample & ~old & new).sum()),
                crossed_downward=int((sample & old & ~new).sum()),
                unchanged_side=int((sample & old.eq(new)).sum()),
            )
        )
    return pd.DataFrame(rows)


def build_transitions(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    cols = ["stock_code", "segment_start", "segment_end", "garch_status", "final_matched_rows"]
    x = old[cols].merge(new, on="stock_code", suffixes=("_old", "_new"), validate="one_to_one")
    x["segment_transition"] = [
        segment_kind(*v)
        for v in x[["segment_start_old", "segment_end_old", "segment_start_new", "segment_end_new"]].itertuples(index=False, name=None)
    ]
    x["segment_changed"] = x.segment_transition.ne("UNCHANGED")
    x = x.rename(
        columns={
            "final_matched_rows_old": "old_rows",
            "final_matched_rows_new": "new_rows",
            "garch_status_old": "GARCH_old_status",
            "garch_status_new": "GARCH_new_status",
        }
    )
    x["delta_rows"] = x.new_rows - x.old_rows
    for threshold in THRESHOLDS:
        x[f"old_{threshold}"] = x.old_rows.ge(threshold)
        x[f"new_{threshold}"] = x.new_rows.ge(threshold)
    x["membership_change_reason"] = [membership_reason(r) for r in x.itertuples(index=False)]
    return x


def write_report(root: Path, dates, cutoff, status, transitions, final, table, sanity):
    endpoint = dates[-1]
    old = pd.read_csv(root / ca.OUT / "h8_final_clean_stock_rows.csv", dtype={"stock_code": str})
    api = pd.DataFrame.from_dict(status, orient="index")
    successful = api.status.isin(SUCCESS)
    segment_counts = transitions.segment_transition.value_counts()
    threshold_lines = []
    for threshold in THRESHOLDS:
        old_member = transitions[f"old_{threshold}"]
        new_member = transitions[f"new_{threshold}"]
        row = table.loc[table.min_rows.eq(threshold)].iloc[0]
        threshold_lines.append(
            f"| {threshold} | {int(old_member.sum())} | {int(new_member.sum())} | {int(new_member.sum()-old_member.sum())} | {int((~old_member & new_member).sum())} | {int((old_member & ~new_member).sum())} | {row.candidate_share:.4%} | {row.size_inclusion_spread:.4%} |"
        )
    ca_all = final.ca_event_count
    c750 = final.loc[final.final_matched_rows.ge(750), "ca_event_count"]
    c1000 = final.loc[final.final_matched_rows.ge(1000), "ca_event_count"]
    sanity_success = sanity.cninfo_status.eq("SUCCESS") if len(sanity) else pd.Series(dtype=bool)
    sanity_matches = sanity.exact_date_match.eq(True) if len(sanity) else pd.Series(dtype=bool)
    sanity_status = (
        "INCREMENTAL_CNINFO_CHECK_UNAVAILABLE"
        if not sanity_success.any()
        else "INCREMENTAL_CNINFO_DATE_SEMANTICS_CONFIRMED"
        if sanity_matches[sanity_success].all()
        else "INCREMENTAL_CNINFO_DATE_CONTRADICTION"
    )
    report = f"""# H8 CA-Lineage Cutoff Extension Comparison

Status: **{'H8_EXTENDED_SAMPLE_READY_FOR_HUMAN_FREEZE' if successful.all() and api.metadata_conflicts.eq(0).all() else 'H8_EXTENDED_SAMPLE_NOT_READY'}**.

This is a sample-availability recalculation only. H8 results, Eq.9, gamma coefficients and outcome summaries were not opened or computed. The accepted BaoStock CA source, main-board/non-observed-ever-ST candidate set, exact-prior-22 rule, matched P1/P2 exclusion, zero-mean GARCH(1,1)-normal specification and longest-clean-segment chronology remain unchanged.

## Time and incremental source

- data cutoff: {DATA_CUTOFF.date()}
- analysis start: {ANALYSIS_START.date()}
- final market endpoint: {endpoint.date()}
- new formation cutoff: {cutoff.date()}
- old formation cutoff: {OLD_FORMATION_CUTOFF.date()}
- added formation market days: {int(((dates > OLD_FORMATION_CUTOFF) & (dates <= cutoff)).sum())}
- candidate stocks: {len(final)}
- API success: {int(successful.sum())}; with new events: {int(api.status.eq('SUCCESS_WITH_NEW_EVENTS').sum())}; no new events: {int(api.status.eq('SUCCESS_NO_NEW_EVENTS').sum())}
- network failed: {int(api.status.eq('NETWORK_FAILED').sum())}; schema failed: {int(api.status.eq('SCHEMA_FAILED').sum())}; metadata conflicts: {int(api.metadata_conflicts.sum())}
- new event rows: {int(api.new_event_count.sum())}
- optional CNINFO sanity: checked={int(sanity_success.sum())}, exact matches={int((sanity_success & sanity_matches).sum())}, conflicts={int((sanity_success & ~sanity_matches).sum())}, status={sanity_status}

No 2020-01-01..2026-05-12 full-history request was made for a valid old cache. Successful empty incremental responses are valid `SUCCESS_NO_NEW_EVENTS` records.

## Segment and GARCH availability

- unchanged: {int(segment_counts.get('UNCHANGED', 0))}
- extended: {int(segment_counts.get('EXTENDED', 0))}
- switched: {int(segment_counts.get('SWITCHED', 0))}
- shortened/other: {int(segment_counts.get('SHORTENED_OR_OTHER', 0))}
- GARCH success: {int(final.garch_status.eq('GARCH_SUCCESS').sum())}
- GARCH numeric failure: {int(final.garch_status.eq('GARCH_NUMERIC_FAILURE').sum())}
- old success to new failure: {int((transitions.GARCH_old_status.eq('GARCH_SUCCESS') & transitions.GARCH_new_status.eq('GARCH_NUMERIC_FAILURE')).sum())}
- old failure to new success: {int((transitions.GARCH_old_status.eq('GARCH_NUMERIC_FAILURE') & transitions.GARCH_new_status.eq('GARCH_SUCCESS')).sum())}

The selected longest clean segment was recomputed over the complete fixed analysis interval and ties choose the earliest segment. All GARCH diagnostics use only that new selected segment with the frozen package/model specification; failures are not rescued.

## Rows

- stocks with any final rows: {int(final.final_matched_rows.gt(0).sum())}
- old total matched rows: {int(old.final_matched_rows.sum())}
- new total matched rows: {int(final.final_matched_rows.sum())}
- delta: {int(final.final_matched_rows.sum()-old.final_matched_rows.sum())}
- median old/new rows: {old.final_matched_rows.median()} / {final.final_matched_rows.median()}

| threshold | old | new | delta | entered | dropped | candidate share | size inclusion spread |
|---:|---:|---:|---:|---:|---:|---:|---:|
{chr(10).join(threshold_lines)}

## Corporate-action frequency selection

- all candidates CA count median/p25/p75: {ca_all.median()} / {ca_all.quantile(.25)} / {ca_all.quantile(.75)}
- 750 sample median/p25/p75: {c750.median()} / {c750.quantile(.25)} / {c750.quantile(.75)}
- 1000 sample median/p25/p75: {c1000.median()} / {c1000.quantile(.25)} / {c1000.quantile(.75)}
- Spearman(CA event count, final rows): {final.ca_event_count.corr(final.final_matched_rows, method='spearman')}

These are sample-selection diagnostics, not return attribution. `recommended_primary_min_rows=HUMAN_JUDGMENT`; `recommended_long_history_sensitivity=HUMAN_JUDGMENT`.

H8_results_opened=false; Eq9_fit=false; gamma31_estimated=false; gamma32_estimated=false; outcome_statistics_computed=false; H7_rerun=false; H7_modified=false.

Recommended next step: **HUMAN_FREEZE_PRIMARY_AND_LONG_HISTORY_THRESHOLDS**. STOP.
"""
    (root / OUT / "h8_cutoff_extension_comparison.md").write_text(report, encoding="utf-8")


def run(root: Path, mode: str):
    root = root.resolve()
    before = h8.protected_metadata(root)
    (root / OUT).mkdir(parents=True, exist_ok=True)
    data = ca.candidates(root)
    dates = market_calendar(root)
    endpoint, cutoff = formation_cutoff(dates)
    if endpoint > DATA_CUTOFF or cutoff >= endpoint:
        raise ValueError("invalid_endpoint_contract")
    status = fetch_increment(root, data.stock_code.tolist(), dates) if mode in {"fetch", "all"} else load_increment_status(root)
    records = []
    for i, code in enumerate(data.stock_code, 1):
        records.append(clean_stock(root, code, dates, cutoff, status.get(code, {})))
        if i % 100 == 0:
            print(f"H8 extended clean/GARCH {i}/{len(data)}", flush=True)
    final = data[["stock_code", "board", "size_quartile", "historical_mean_circulating_market_cap"]].merge(
        pd.DataFrame(records), on="stock_code", validate="one_to_one"
    )
    old = pd.read_csv(root / ca.OUT / "h8_final_clean_stock_rows.csv", dtype={"stock_code": str})
    transitions = build_transitions(old, final)
    table = threshold_table(final)
    segment = transitions[
        [
            "stock_code",
            "segment_start_old",
            "segment_end_old",
            "segment_start_new",
            "segment_end_new",
            "segment_transition",
            "segment_changed",
            "new_CA_event_count",
        ]
    ]
    ca.atomic_csv(segment, root / OUT / "h8_segment_transition.csv")
    ca.atomic_csv(transitions, root / OUT / "h8_threshold_membership_transition.csv")
    ca.atomic_csv(final, root / OUT / "h8_extended_final_clean_stock_rows.csv")
    ca.atomic_csv(table, root / OUT / "h8_extended_history_thresholds.csv")
    ca.atomic_csv(boundary_diagnostics(transitions), root / OUT / "h8_threshold_boundary_diagnostics.csv")
    sanity_path = root / OUT / "h8_incremental_cninfo_sanity.csv"
    if mode in {"fetch", "all"}:
        sanity = cninfo_sanity(root, status)
    elif sanity_path.exists():
        sanity = pd.read_csv(sanity_path, dtype={"stock_code": str})
    else:
        sanity = pd.DataFrame()
    write_report(root, dates, cutoff, status, transitions, final, table, sanity)
    if before != h8.protected_metadata(root):
        raise RuntimeError("H7_metadata_changed")
    print("H8 extension eligibility complete; H7 unchanged; no Eq9/outcome statistics", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--mode", choices=["fetch", "recompute", "all"], default="all")
    args = parser.parse_args()
    run(args.project_root, args.mode)
