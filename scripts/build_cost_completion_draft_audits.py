"""Build local-only DRAFT audits after the frozen COST completion.

This intentionally reads checkpoints and decoded artifacts only.  It neither
fetches RPC data nor reads next-open/return fields from measurement rows.
"""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from audit_boundary_window_5m_vs_30m import (
    BOUNDARIES,
    THIN_MIN_NOTIONAL,
    THIN_MIN_SWAPS,
    availability,
    compute_30m,
    read_measurement_5m,
    thin,
)


OUT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")
SESSIONS = OUT / "sessions"
MANIFEST = OUT / "cost_full_history_completion_manifest.json"
SOURCE_30M = OUT / "boundary_window_feasibility_5m_vs_30m_sessions.csv"
PANEL_TOKENS = ("NVDA", "GME", "TSLA", "COST", "USO", "AMZN", "UPS", "GOOGL", "META")
SAMPLE_DESIGNS = {
    "NVDA": "FULL_HISTORY",
    "GME": "FULL_HISTORY",
    "TSLA": "FULL_HISTORY_WITH_ELIGIBILITY_CORRECTION",
    "COST": "FULL_HISTORY",
    "USO": "BOUNDED_EARLY_LATE_SCREEN",
    "AMZN": "BOUNDED_REPLACEMENT_SCREEN",
    "UPS": "BOUNDED_REPLACEMENT_SCREEN",
    "GOOGL": "THREE_DATE_PRESCREEN",
    "META": "THREE_DATE_PRESCREEN",
}
UTC = timezone.utc
COST_CONTRACT = "0x4EA005168D7F09a7A0Ba9D1DEf21a479950E44C2"
COST_POOL = "0x0a2121A50A09eD0796ae81F9c53fF9398355a398"
V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"

SESSION_COLUMNS = [
    "token", "market_open_date",
    "5m_1600_available", "5m_2000_available", "5m_0400_available", "5m_0930_available", "5m_deep_available",
    "30m_1600_available", "30m_2000_available", "30m_0400_available", "30m_0930_available", "30m_deep_available",
    "5m_2000_swap_count", "5m_0400_swap_count", "30m_2000_swap_count", "30m_0400_swap_count",
    "5m_2000_notional", "5m_0400_notional", "30m_2000_notional", "30m_0400_notional",
    "5m_thin_flag", "30m_thin_flag", "data_source", "local_or_rpc",
]


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False, default=str), encoding="utf-8")


def bool_value(value) -> bool:
    return str(value).lower() == "true" if isinstance(value, str) else bool(value)


def robust(row: pd.Series) -> bool:
    return bool_value(row["30m_deep_available"]) and all(
        float(row[f"30m_{boundary}_swap_count"]) >= THIN_MIN_SWAPS
        and float(row[f"30m_{boundary}_notional"]) >= THIN_MIN_NOTIONAL
        for boundary in ("2000", "0400")
    )


def boundary_non_thin(frame: pd.DataFrame, window: str, boundary: str) -> pd.Series:
    return (
        frame[f"{window}_{boundary}_available"].map(bool_value)
        & frame[f"{window}_{boundary}_swap_count"].ge(THIN_MIN_SWAPS)
        & frame[f"{window}_{boundary}_notional"].ge(THIN_MIN_NOTIONAL)
    )


def deep_robust(frame: pd.DataFrame, window: str) -> pd.Series:
    return boundary_non_thin(frame, window, "2000") & boundary_non_thin(frame, window, "0400")


def cost_technical_audit(dates: list[str]) -> dict:
    anomalies: list[dict] = []
    rows = []
    multiplier_transition = int(datetime(2026, 8, 10, 15, 10, 24, tzinfo=UTC).timestamp())
    for open_date in dates:
        directory = SESSIONS / "COST" / open_date
        summary_path = directory / "summary.json"
        measurement_path = directory / "measurement_row.csv"
        state_path = directory / "retrieval_state.json"
        required = {"summary": summary_path, "measurement": measurement_path, "state": state_path}
        missing = [name for name, path in required.items() if not path.exists()]
        if missing:
            anomalies.append({"date": open_date, "severity": "STOP_FOR_RESEARCH_REVIEW", "issue": "missing_required_artifact", "detail": missing})
            continue
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        state = json.loads(state_path.read_text(encoding="utf-8"))
        successful = sorted(state.get("successful", []), key=lambda item: item["block_start"])
        cursor = state.get("exact_block_range", [None])[0]
        chunk_errors = []
        raw_events = 0
        for item in successful:
            chunk = directory / "chunks" / f"{item['block_start']}_{item['block_end']}.json"
            if item["block_start"] != cursor or not chunk.exists():
                chunk_errors.append(f"gap_or_missing_chunk:{item['block_start']}-{item['block_end']}")
                break
            events = json.loads(chunk.read_text(encoding="utf-8"))
            event_count = len(events)
            if event_count != item["event_count"]:
                chunk_errors.append(f"event_count_mismatch:{item['block_start']}-{item['block_end']}")
            if any(event.get("address", "").lower() != COST_POOL.lower() for event in events):
                chunk_errors.append(f"unexpected_pool_address:{item['block_start']}-{item['block_end']}")
            if any(not event.get("topics") or event["topics"][0].lower() != V3_SWAP_TOPIC for event in events):
                chunk_errors.append(f"unexpected_event_topic:{item['block_start']}-{item['block_end']}")
            raw_events += event_count
            cursor = item["block_end"] + 1
        if cursor != state.get("exact_block_range", [None, None])[1] + 1:
            chunk_errors.append("terminal_block_coverage_incomplete")
        decoded = pd.read_csv(directory / "decoded_swaps.csv")
        stamps = {int(key): int(value) for key, value in json.loads((directory / "block_timestamps.json").read_text(encoding="utf-8")).items()}
        decoded_blocks = set(decoded["block_number"].astype(int))
        timestamp_errors = []
        if not decoded_blocks.issubset(stamps):
            timestamp_errors.append("decoded_block_missing_timestamp")
        start = int(datetime.fromisoformat(summary["session_start_utc"]).timestamp())
        end = int(datetime.fromisoformat(summary["session_end_utc_exclusive"]).timestamp())
        if not decoded["block_timestamp_utc"].between(start, end - 1).all():
            timestamp_errors.append("decoded_timestamp_outside_frozen_session")
        expected_multiplier = decoded["block_timestamp_utc"].map(lambda value: 1.000612040296259656 if int(value) >= multiplier_transition else 1.0)
        if not (decoded["historical_multiplier"].astype(float).sub(expected_multiplier).abs() < 1e-15).all():
            timestamp_errors.append("COST_multiplier_timestamp_mismatch")
        if decoded.duplicated(["transaction_hash", "log_index"]).any():
            timestamp_errors.append("decoded_exact_duplicate")
        if not decoded["reconstructable"].astype(str).str.lower().eq("true").all():
            timestamp_errors.append("unreconstructable_swap")
        for column in ("quote_amount_usdg", "token_amount", "execution_price_usdg_per_token", "underlying_equivalent_price_usdg"):
            values = pd.to_numeric(decoded[column], errors="coerce")
            if not values.map(lambda value: math.isfinite(value) and value > 0).all():
                timestamp_errors.append(f"nonpositive_or_nonfinite:{column}")
        mismatches = chunk_errors + timestamp_errors
        if state.get("status") != "raw_complete":
            mismatches.append(f"raw_state={state.get('status')}")
        if summary.get("completion_status") not in {"complete", "complete_reused"}:
            mismatches.append(f"summary_state={summary.get('completion_status')}")
        if raw_events != int(summary.get("raw_event_count", -1)):
            mismatches.append("summary_raw_event_count_mismatch")
        if len(decoded) != int(summary.get("decoded_event_count", -1)):
            mismatches.append("summary_decoded_event_count_mismatch")
        if raw_events - len(decoded) != int(summary.get("exact_duplicates_removed", -1)):
            mismatches.append("summary_duplicate_count_mismatch")
        if mismatches:
            anomalies.append({"date": open_date, "severity": "STOP_FOR_RESEARCH_REVIEW", "issue": "technical_integrity_failure", "detail": mismatches})
        measurement = pd.read_csv(
            measurement_path,
            usecols=lambda name: name.startswith("token_vwap_") or name.startswith("boundary_") or name in {"thin_boundary_flag", "missing_boundary_flag"},
        ).iloc[0]
        rows.append({
            "market_open_date": open_date,
            "raw_event_count": raw_events,
            "decoded_event_count": len(decoded),
            "reconstructable_count": int(decoded["reconstructable"].astype(str).str.lower().eq("true").sum()),
            "terminal_chunk_count": len(successful),
            "timestamp_checkpoint_entries": len(stamps),
            "missing_primary_boundary": bool_value(measurement["missing_boundary_flag"]),
            "thin_primary_boundary": bool_value(measurement["thin_boundary_flag"]),
            "technical_integrity_ok": not mismatches,
        })
    return {
        "artifact_status": "DRAFT_TECHNICAL_AUDIT_ONLY",
        "token": "COST",
        "canonical_contract": COST_CONTRACT,
        "canonical_pool": COST_POOL,
        "pool_ordering": "COST token / USDG, frozen and previously verified",
        "manifest_dates": dates,
        "completed_dates": [row["market_open_date"] for row in rows],
        "completed_count": len(rows),
        "expected_count": len(dates),
        "technical_integrity_pass": not anomalies and len(rows) == len(dates),
        "stop_for_research_review": bool(anomalies),
        "anomalies": anomalies,
        "session_technical_rows": rows,
        "no_next_open_fields_read": True,
        "no_predictive_analysis": True,
        "methodological_judgment": "NOT_MADE",
    }


def cost_measurement_rows(dates: list[str]) -> list[dict]:
    rows = []
    for open_date in dates:
        meta = pd.read_csv(SESSIONS / "COST" / open_date / "measurement_row.csv", usecols=["session_start_et", "session_end_et_exclusive"]).iloc[0]
        metrics_5m = read_measurement_5m("COST", open_date)
        metrics_30m = compute_30m("COST", open_date, str(meta["session_start_et"]), str(meta["session_end_et_exclusive"]))
        available_5m, available_30m = availability(metrics_5m), availability(metrics_30m)
        rows.append({
            "token": "COST", "market_open_date": open_date,
            **{f"5m_{name}_available": metrics_5m[name]["available"] for name in BOUNDARIES},
            "5m_deep_available": available_5m["deep"],
            **{f"30m_{name}_available": metrics_30m[name]["available"] for name in BOUNDARIES},
            "30m_deep_available": available_30m["deep"],
            **{f"5m_{name}_swap_count": metrics_5m[name]["swap_count"] for name in ("2000", "0400")},
            **{f"30m_{name}_swap_count": metrics_30m[name]["swap_count"] for name in ("2000", "0400")},
            **{f"5m_{name}_notional": metrics_5m[name]["notional"] for name in ("2000", "0400")},
            **{f"30m_{name}_notional": metrics_30m[name]["notional"] for name in ("2000", "0400")},
            "5m_thin_flag": thin(metrics_5m), "30m_thin_flag": thin(metrics_30m),
            "data_source": "LOCAL_RAW", "local_or_rpc": "local",
        })
    return rows


def measurement_summary(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    rows = []
    for token, group in frame.groupby("token", sort=False):
        robust_count = int(group.apply(robust, axis=1).sum())
        rows.append({
            "token": token,
            "sessions": len(group),
            "5m_deep_available": int(group["5m_deep_available"].map(bool_value).sum()),
            "5m_deep_rate": round(float(group["5m_deep_available"].map(bool_value).mean()), 4),
            "30m_deep_available": int(group["30m_deep_available"].map(bool_value).sum()),
            "30m_deep_rate": round(float(group["30m_deep_available"].map(bool_value).mean()), 4),
            "30m_deep_robust": robust_count,
            "30m_deep_robust_rate": round(robust_count / len(group), 4),
            "5m_thin_sessions": int(group["5m_thin_flag"].map(bool_value).sum()),
            "30m_thin_sessions": int(group["30m_thin_flag"].map(bool_value).sum()),
        })
    result = pd.DataFrame(rows)
    payload = {
        "artifact_status": "DRAFT_MEASUREMENT_COVERAGE_ONLY",
        "panel_tokens": list(PANEL_TOKENS),
        "sample_designs": SAMPLE_DESIGNS,
        "total_sessions": len(frame),
        "per_token": {row["token"]: row for row in rows},
        "threshold": {"minimum_swaps_per_boundary": THIN_MIN_SWAPS, "minimum_notional_usdg_per_boundary": THIN_MIN_NOTIONAL},
        "non_cost_30m_source": str(SOURCE_30M),
        "cost_30m_source": "local decoded COST artifacts; no RPC",
        "no_next_open_fields_read": True,
        "no_predictive_analysis": True,
        "methodological_judgment": "NOT_MADE",
    }
    return result, payload


def main() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    dates = manifest["eligible_dates"]
    if manifest.get("token_symbol") != "COST" or len(dates) != 31 or len(set(dates)) != 31:
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: frozen COST manifest invalid")
    audit = cost_technical_audit(dates)
    if audit["stop_for_research_review"]:
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: COST technical audit failed; progress was persisted")

    collection_totals = {key: 0 for key in (
        "raw_event_count", "terminal_chunk_count", "raw_log_rpc_requests",
        "total_timestamp_checkpoint_hits", "total_global_timestamp_cache_hits",
        "total_timestamp_rpc_misses", "total_newly_inserted_global_cache_rows",
        "total_timestamp_rpc_batch_requests", "total_timestamp_retry_events",
        "total_timestamp_rate_limit_events", "total_timestamp_timeout_events",
        "total_timestamp_resolution_seconds", "session_runtime_seconds",
    )}
    for open_date in manifest["missing_dates_to_collect"]:
        summary = json.loads((SESSIONS / "COST" / open_date / "summary.json").read_text(encoding="utf-8"))
        diagnostics = summary.get("runtime_diagnostics", {})
        collection_totals["raw_event_count"] += int(summary["raw_event_count"])
        collection_totals["terminal_chunk_count"] += int(summary["terminal_chunk_count"])
        collection_totals["session_runtime_seconds"] += float(summary["session_runtime_seconds"])
        for key in collection_totals:
            if key not in {"raw_event_count", "terminal_chunk_count", "session_runtime_seconds"}:
                collection_totals[key] += diagnostics.get(key) or 0
    non_checkpoint = collection_totals["total_global_timestamp_cache_hits"] + collection_totals["total_timestamp_rpc_misses"]
    collection_totals["global_cache_hit_rate_among_non_checkpoint_timestamps"] = (
        collection_totals["total_global_timestamp_cache_hits"] / non_checkpoint if non_checkpoint else 0.0
    )
    audit.update({
        "artifact_status": "FINAL_TECHNICAL_AUDIT",
        "approval": "HUMAN_SOL_APPROVED",
        "previously_collected_count": len(manifest["existing_collected_dates"]),
        "newly_collected_count": len(manifest["missing_dates_to_collect"]),
        "newly_collected_dates": manifest["missing_dates_to_collect"],
        "collection_totals_for_new_sessions": collection_totals,
        "technical_qa_decision": "PASS",
        "methodological_judgment": "PARENT_REVIEWED",
    })
    write_json(OUT / "cost_full_history_completion_audit.json", audit)
    audit_md = ["# COST full-history completion audit", "", "Parent-reviewed technical audit; no next-open outcomes or predictive analysis were used.", "", f"- Frozen manifest: {len(manifest['existing_collected_dates'])} existing + {len(manifest['missing_dates_to_collect'])} newly collected = {audit['completed_count']}/{audit['expected_count']}.", f"- Technical QA: **{audit['technical_qa_decision']}**; no incomplete ranges, unresolved timestamps, duplicates, wrong-pool events, parse failures, or non-finite reconstructed values.", f"- Canonical contract: `{COST_CONTRACT}`.", f"- Canonical V3 pool: `{COST_POOL}`.", "- Frozen multiplier: 1.0 before 2026-08-10 15:10:24 UTC; 1.000612040296259656 from that instant onward.", f"- New-session raw swaps: {collection_totals['raw_event_count']:,}; terminal chunks: {collection_totals['terminal_chunk_count']:,}.", f"- Timestamp checkpoint hits: {collection_totals['total_timestamp_checkpoint_hits']:,}; global-cache hits: {collection_totals['total_global_timestamp_cache_hits']:,}; RPC misses: {collection_totals['total_timestamp_rpc_misses']:,}.", f"- Aggregate global-cache hit rate after per-session checkpoints: {collection_totals['global_cache_hit_rate_among_non_checkpoint_timestamps']:.1%}.", "", "No other token was collected.", ""]
    (OUT / "cost_full_history_completion_audit.md").write_text("\n".join(audit_md), encoding="utf-8")

    persisted = pd.read_csv(SOURCE_30M, usecols=lambda name: name in SESSION_COLUMNS)
    non_cost = persisted.loc[persisted["token"].isin([token for token in PANEL_TOKENS if token != "COST"]), SESSION_COLUMNS]
    cost = pd.DataFrame(cost_measurement_rows(dates))[SESSION_COLUMNS]
    frame = pd.concat([non_cost, cost], ignore_index=True)
    if frame.duplicated(["token", "market_open_date"]).any() or set(cost["market_open_date"]) != set(dates):
        raise RuntimeError("STOP_FOR_RESEARCH_REVIEW: merged measurement key integrity failure")
    summary_csv, measurement_json = measurement_summary(frame)
    cost["5m_deep_robust"] = deep_robust(cost, "5m")
    cost["30m_deep_robust"] = deep_robust(cost, "30m")
    cost.to_csv(OUT / "cost_full_history_measurement_summary.csv", index=False)
    five_deep = cost["5m_deep_available"].map(bool_value)
    thirty_deep = cost["30m_deep_available"].map(bool_value)
    five_robust = cost["5m_deep_robust"]
    thirty_robust = cost["30m_deep_robust"]
    cost_classification = (
        "COST_FULL_HISTORY_ROBUST_HIGH" if thirty_robust.mean() >= 0.8 else
        "COST_FULL_HISTORY_ROBUST_MODERATE" if thirty_robust.mean() >= 0.6 else
        "COST_FULL_HISTORY_ROBUST_LOW" if thirty_robust.mean() >= 0.4 else
        "COST_FULL_HISTORY_ROBUST_POOR"
    )
    early = cost["market_open_date"].le("2026-08-12")
    late = ~early
    measurement_json.update({
        "artifact_status": "FINAL_MEASUREMENT_COVERAGE",
        "cost_full_history": {
            "sessions": len(cost),
            "5m": {
                "2000_available_count": int(cost["5m_2000_available"].map(bool_value).sum()),
                "0400_available_count": int(cost["5m_0400_available"].map(bool_value).sum()),
                "deep_available_count": int(five_deep.sum()),
                "deep_available_rate": round(float(five_deep.mean()), 4),
                "all_four_boundary_thin_count": int(cost["5m_thin_flag"].map(bool_value).sum()),
                "all_four_boundary_thin_rate": round(float(cost["5m_thin_flag"].map(bool_value).mean()), 4),
                "deep_available_but_thin_count": int((five_deep & ~five_robust).sum()),
            },
            "30m": {
                "2000_available_count": int(cost["30m_2000_available"].map(bool_value).sum()),
                "0400_available_count": int(cost["30m_0400_available"].map(bool_value).sum()),
                "deep_available_count": int(thirty_deep.sum()),
                "deep_available_rate": round(float(thirty_deep.mean()), 4),
                "robust_deep_count": int(thirty_robust.sum()),
                "robust_deep_rate": round(float(thirty_robust.mean()), 4),
                "available_but_thin_count": int((thirty_deep & ~thirty_robust).sum()),
                "unavailable_count": int((~thirty_deep).sum()),
                "robust_share_among_available": round(float(thirty_robust.sum() / thirty_deep.sum()), 4),
                "2000_non_thin_count": int(boundary_non_thin(cost, "30m", "2000").sum()),
                "2000_non_thin_rate": round(float(boundary_non_thin(cost, "30m", "2000").mean()), 4),
                "0400_non_thin_count": int(boundary_non_thin(cost, "30m", "0400").sum()),
                "0400_non_thin_rate": round(float(boundary_non_thin(cost, "30m", "0400").mean()), 4),
                "median_2000_swap_count": float(cost["30m_2000_swap_count"].median()),
                "median_0400_swap_count": float(cost["30m_0400_swap_count"].median()),
                "median_2000_notional_usdg": float(cost["30m_2000_notional"].median()),
                "median_0400_notional_usdg": float(cost["30m_0400_notional"].median()),
            },
            "temporal_maturation": {
                "early_period_through_2026_08_12": {"sessions": int(early.sum()), "robust": int(thirty_robust[early].sum())},
                "later_period_from_2026_08_13": {"sessions": int(late.sum()), "robust": int(thirty_robust[late].sum())},
                "description": "Matured sharply around mid-August: 2/14 robust through Aug 12 versus 16/17 from Aug 13 onward; the sole later exception was Aug 25.",
                "eligibility_unchanged": True,
            },
            "classification": cost_classification,
        },
        "methodological_judgment": "PARENT_REVIEWED_MEASUREMENT_ONLY",
    })
    write_json(OUT / "cost_full_history_measurement_summary.json", measurement_json)
    c5 = measurement_json["cost_full_history"]["5m"]
    c30 = measurement_json["cost_full_history"]["30m"]
    lines = ["# COST full-history measurement summary", "", "Measurement coverage only; no next-open outcomes or predictive analysis.", "", f"- Sessions: {len(cost)}/31.", f"- 5m: 20:00 available {c5['2000_available_count']}/31; 04:00 available {c5['0400_available_count']}/31; deep available {c5['deep_available_count']}/31 ({c5['deep_available_rate']:.1%}); all-four-boundary thin {c5['all_four_boundary_thin_count']}/31 ({c5['all_four_boundary_thin_rate']:.1%}).", f"- 30m: 20:00 available {c30['2000_available_count']}/31; 04:00 available {c30['0400_available_count']}/31; deep available {c30['deep_available_count']}/31 ({c30['deep_available_rate']:.1%}).", f"- 30m robust deep: {c30['robust_deep_count']}/31 ({c30['robust_deep_rate']:.1%}); available-but-thin {c30['available_but_thin_count']}; unavailable {c30['unavailable_count']}; robust among available {c30['robust_share_among_available']:.1%}.", f"- 30m boundary non-thin: 20:00 {c30['2000_non_thin_count']}/31 ({c30['2000_non_thin_rate']:.1%}); 04:00 {c30['0400_non_thin_count']}/31 ({c30['0400_non_thin_rate']:.1%}).", f"- 30m medians: 20:00 {c30['median_2000_swap_count']:.0f} swaps / {c30['median_2000_notional_usdg']:.2f} USDG; 04:00 {c30['median_0400_swap_count']:.0f} swaps / {c30['median_0400_notional_usdg']:.2f} USDG.", "- Chronology: 2/14 robust through Aug 12 versus 16/17 from Aug 13 onward; liquidity matured sharply, with Aug 25 the sole later non-robust session. Eligibility remains unchanged.", f"- Classification: **{cost_classification}**.", ""]
    (OUT / "cost_full_history_measurement_summary.md").write_text("\n".join(lines), encoding="utf-8")

    frame["robust"] = frame.apply(robust, axis=1)
    robust_counts = frame.loc[frame["robust"]].groupby("token").size().reindex(PANEL_TOKENS, fill_value=0)
    total = int(robust_counts.sum())
    shares = {token: round(int(count) / total, 4) for token, count in robust_counts.items()} if total else {}
    nvda_gme_share = (int(robust_counts["NVDA"]) + int(robust_counts["GME"])) / total if total else 0.0
    core_three_share = (int(robust_counts["NVDA"]) + int(robust_counts["GME"]) + int(robust_counts["COST"])) / total if total else 0.0
    classification = "ROBUST_PANEL_HIGHLY_CONCENTRATED" if nvda_gme_share >= 0.7 else "ROBUST_PANEL_MODERATELY_CONCENTRATED" if nvda_gme_share >= 0.5 else "ROBUST_PANEL_BROAD"
    robust_json = {
        "artifact_status": "FINAL_ROBUST_COVERAGE_ONLY",
        "panel_tokens": list(PANEL_TOKENS),
        "sample_designs": SAMPLE_DESIGNS,
        "total_sessions": len(frame),
        "total_30m_deep_available": int(frame["30m_deep_available"].map(bool_value).sum()),
        "total_30m_deep_robust": total,
        "robust_observations_by_token": {token: int(count) for token, count in robust_counts.items()},
        "robust_share_by_token": shares,
        "nvda_gme_robust_share": round(nvda_gme_share, 4),
        "nvda_gme_cost_robust_share": round(core_three_share, 4),
        "robust_panel_concentration_classification": classification,
        "threshold": {"minimum_swaps_per_boundary": THIN_MIN_SWAPS, "minimum_notional_usdg_per_boundary": THIN_MIN_NOTIONAL},
        "no_next_open_fields_read": True,
        "no_predictive_analysis": True,
        "previous_provisional_nvda_gme_share": 0.775,
        "previous_provisional_total_robust": 80,
        "previous_panel_was_unequal_completeness": True,
        "panel_remains_unbalanced": True,
        "methodological_judgment": "PARENT_REVIEWED_MEASUREMENT_ONLY",
    }
    write_json(OUT / "post_cost_robust_panel_summary.json", robust_json)
    robust_md = ["# Post-COST robust panel summary", "", "30-minute deep-boundary coverage only; robust requires both 20:00 and 04:00 windows to have at least 5 swaps and 500 USDG notional.", "", f"- Sessions: {len(frame)}; robust observations: {total}.", f"- Robust counts: NVDA {robust_counts['NVDA']}; GME {robust_counts['GME']}; COST {robust_counts['COST']}; TSLA {robust_counts['TSLA']}.", f"- Shares: NVDA {shares['NVDA']:.1%}; GME {shares['GME']:.1%}; COST {shares['COST']:.1%}; NVDA + GME {nvda_gme_share:.1%}; NVDA + GME + COST {core_three_share:.1%}.", "- Previous provisional NVDA + GME share was 77.5% of 80 robust observations, from an unequal-completeness panel.", "- COST materially broadened the measured base by contributing 18 robust observations, reducing NVDA + GME concentration to 66.7%.", "", "The panel remains unbalanced because secondary tokens retain bounded/prescreen designs. No next-open outcome fields were read.", ""]
    (OUT / "post_cost_robust_panel_summary.md").write_text("\n".join(robust_md), encoding="utf-8")
    print(json.dumps({"cost_completed": audit["completed_count"], "measurement_sessions": len(frame), "robust_sessions": total, "classification": classification}, indent=2))


if __name__ == "__main__":
    main()
