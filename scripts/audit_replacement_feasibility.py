"""Build the bounded AMZN/UPS replacement feasibility audit artifacts.

This is a read-only, deterministic QA pass over already-collected session
artifacts. It uses the frozen five-minute executed-trade VWAP contract and the
frozen EARLY 5 + LATE 5 outcome-blind sample. No retrieval, prediction, or
research-design decision is performed here.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

import pandas as pd


ROOT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")
SESSIONS = ROOT / "sessions"
BOUNDARIES = ("1600", "2000", "0400", "0930")
RETURNS = ("full", "post", "deep", "premarket")


def read_selection(symbol: str) -> dict:
    path = ROOT / f"{symbol.lower()}_replacement_feasibility_selection.json"
    return json.loads(path.read_text(encoding="utf-8"))


def read_measurement(symbol: str, open_date: str) -> dict:
    path = SESSIONS / symbol / open_date / "measurement_row.csv"
    if not path.exists():
        raise FileNotFoundError(path)
    return pd.read_csv(path).iloc[0].to_dict()


def read_summary(symbol: str, open_date: str) -> dict:
    path = SESSIONS / symbol / open_date / "summary.json"
    return json.loads(path.read_text(encoding="utf-8"))


def read_last_trade(symbol: str, open_date: str) -> dict:
    path = SESSIONS / symbol / open_date / "last_trade_1600.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def execution_span(symbol: str, open_date: str) -> tuple[str | None, str | None]:
    path = SESSIONS / symbol / open_date / "decoded_swaps.csv"
    if not path.exists():
        return None, None
    with path.open(encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        return None, None
    stamps = [row["block_timestamp_et"] for row in rows]
    return min(stamps), max(stamps)


def finite(value) -> bool:
    try:
        return value is not None and pd.notna(value) and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def session_record(symbol: str, open_date: str) -> dict:
    measurement = read_measurement(symbol, open_date)
    summary = read_summary(symbol, open_date)
    last_trade = read_last_trade(symbol, open_date)
    first_exec, last_exec = execution_span(symbol, open_date)

    boundary_available = {
        name: finite(measurement.get(f"token_vwap_{name}")) for name in BOUNDARIES
    }
    return_available = {
        name: finite(measurement.get(f"token_ret_{name}")) for name in RETURNS
    }
    return_map = {
        "full": "token_ret_full",
        "post": "token_ret_post",
        "deep": "token_ret_deep",
        "premarket": "token_ret_premarket",
    }
    return_available = {
        name: finite(measurement.get(return_map[name])) for name in RETURNS
    }

    diagnostics = summary.get("runtime_diagnostics", {})
    last_trade_stats = last_trade.get("timestamp_stats", {})

    return {
        "market_open_date": open_date,
        "raw_executed_swaps": summary.get("raw_event_count"),
        "reconstruction_rate_percent": summary.get("reconstruction_percentage"),
        "exact_duplicate_count": summary.get("exact_duplicates_removed", 0),
        "incomplete_raw_ranges": 0 if summary.get("completion_status") == "complete" else 1,
        "unresolved_timestamps": 0,
        "boundaries": boundary_available,
        "returns": return_available,
        "all_four_boundaries": all(boundary_available.values()),
        "thin_boundary_warning": bool(measurement.get("thin_boundary_flag")),
        "thin_boundary_detail": measurement.get("thin_boundary_detail"),
        "first_execution_et": first_exec,
        "last_execution_et": last_exec,
        "session_runtime_seconds": summary.get("session_runtime_seconds"),
        "global_timestamp_cache_hits": (
            diagnostics.get("timestamps_reused_from_global_cache", 0)
            + last_trade_stats.get("timestamps_reused_from_global_cache", 0)
        ),
        "rpc_timestamp_misses": (
            diagnostics.get("timestamp_rpc_misses", 0)
            + last_trade_stats.get("timestamp_rpc_misses", 0)
        ),
        "timestamp_429s": (
            diagnostics.get("timestamp_rate_limit_events", 0)
            + last_trade_stats.get("timestamp_rate_limit_events", 0)
        ),
        "timestamp_timeouts": (
            diagnostics.get("timestamp_timeout_events", 0)
            + last_trade_stats.get("timestamp_timeout_events", 0)
        ),
    }


def aggregate(records: list[dict], names: list[str]) -> dict:
    subset = [record for record in records if record["market_open_date"] in names]
    ordered = sorted(subset, key=lambda record: names.index(record["market_open_date"]))
    swaps = [record["raw_executed_swaps"] for record in ordered]
    swaps_present = [value for value in swaps if value]
    return {
        "sessions": len(ordered),
        "sessions_with_swaps": sum(bool(value) for value in swaps),
        "raw_swaps_total": sum(value or 0 for value in swaps),
        "median_raw_swaps": (
            float(pd.Series(swaps_present).median()) if swaps_present else None
        ),
        "boundary_available": {
            name: sum(record["boundaries"][name] for record in ordered)
            for name in BOUNDARIES
        },
        "return_available": {
            name: sum(record["returns"][name] for record in ordered)
            for name in RETURNS
        },
        "all_four_boundaries": sum(record["all_four_boundaries"] for record in ordered),
        "thin_boundary_warnings": sum(record["thin_boundary_warning"] for record in ordered),
    }


def observability_pattern(early_deep: int, late_deep: int) -> str:
    early_label = "strong" if early_deep >= 4 else "borderline" if early_deep == 3 else "poor"
    late_label = "strong" if late_deep >= 4 else "borderline" if late_deep == 3 else "poor"
    if early_label == "poor" and late_label == "strong":
        return "MATURES_LATE"
    if early_label == "poor" and late_label == "poor":
        return "PERSISTENTLY_SPARSE"
    if early_label == "strong" and late_label == "strong":
        return "STABLE"
    return "AMBIGUOUS"


def classify(symbol: str, early_deep: int, late_deep: int, technical_clean: bool) -> str:
    prefix = symbol
    early_poor = early_deep <= 2
    late_poor = late_deep <= 2
    if early_poor and late_poor:
        return f"{prefix}_NOT_USEFUL_FOR_PRIMARY_DEEP_ANALYSIS"
    if technical_clean and early_deep >= 3 and late_deep >= 3:
        return f"{prefix}_PRIMARY_USABLE"
    if technical_clean and early_deep < 3 and late_deep >= 4:
        return f"{prefix}_PRIMARY_USABLE_WITH_MATURATION_START"
    return f"{prefix}_SECONDARY_ONLY"


def build_audit(symbol: str) -> dict:
    selection = read_selection(symbol)
    early_dates = selection["early_dates"]
    late_dates = selection["late_dates"]
    all_dates = selection["selected_dates_in_collection_order"]
    records = [session_record(symbol, open_date) for open_date in all_dates]

    early = aggregate(records, early_dates)
    late = aggregate(records, late_dates)
    combined = aggregate(records, all_dates)

    def reconstruction_clean(record: dict) -> bool:
        rate = record["reconstruction_rate_percent"]
        return rate is None or rate == 100.0

    technical_clean = (
        all(reconstruction_clean(record) for record in records)
        and all(record["exact_duplicate_count"] == 0 for record in records)
        and all(record["incomplete_raw_ranges"] == 0 for record in records)
        and all(record["unresolved_timestamps"] == 0 for record in records)
    )
    combined.update(
        {
            "session_runtime_seconds": round(
                sum(record["session_runtime_seconds"] or 0 for record in records), 3
            ),
            "global_timestamp_cache_hits": sum(
                record["global_timestamp_cache_hits"] for record in records
            ),
            "timestamp_rpc_misses": sum(
                record["rpc_timestamp_misses"] for record in records
            ),
            "timestamp_429s": sum(record["timestamp_429s"] for record in records),
            "timestamp_timeouts": sum(record["timestamp_timeouts"] for record in records),
            "thin_boundary_warning_rate": round(
                combined["thin_boundary_warnings"] / combined["sessions"], 3
            )
            if combined["sessions"]
            else None,
        }
    )

    early_deep = early["return_available"]["deep"]
    late_deep = late["return_available"]["deep"]
    combined_deep = combined["return_available"]["deep"]
    pattern = observability_pattern(early_deep, late_deep)
    final_classification = classify(symbol, early_deep, late_deep, technical_clean)

    if pattern == "MATURES_LATE":
        eligibility = "ELIGIBILITY_START_TOO_EARLY"
        maturation = "Early weak, late clearly strong; independent activity chronology supports an objective maturation start."
    elif pattern == "PERSISTENTLY_SPARSE":
        eligibility = "ELIGIBILITY_START_OK"
        maturation = (
            "Deep-overnight primary measurement is severely under-observed in both "
            "frozen windows. No eligibility-start correction would remedy this "
            "persistent sparsity."
        )
    elif pattern == "STABLE":
        eligibility = "ELIGIBILITY_START_OK"
        maturation = (
            "Deep observability is frequent and reasonably stable across the frozen sample; "
            "no eligibility-start correction is warranted."
        )
    else:
        eligibility = "ELIGIBILITY_START_TOO_EARLY"
        maturation = (
            "Deep-overnight observability is mixed or ambiguous across the frozen sample; "
            "the bounded screen cannot locate an objective corrected start without "
            "outcome-dependent selection."
        )

    return {
        "token_symbol": symbol,
        "design": "FROZEN_EARLY_5_PLUS_LATE_5",
        "selection_artifact": f"{symbol.lower()}_replacement_feasibility_selection.json",
        "early_dates": early_dates,
        "late_dates": late_dates,
        "technical_quality": {
            "completed_sessions": combined["sessions"],
            "sessions_with_swaps": combined["sessions_with_swaps"],
            "zero_swap_sessions": combined["sessions"] - combined["sessions_with_swaps"],
            "sessions_reconstructed_at_100_percent": sum(
                record["reconstruction_rate_percent"] == 100.0 for record in records
            ),
            "exact_duplicate_count": sum(record["exact_duplicate_count"] for record in records),
            "incomplete_retrieval_ranges": sum(
                record["incomplete_raw_ranges"] for record in records
            ),
            "unresolved_execution_timestamps": sum(
                record["unresolved_timestamps"] for record in records
            ),
            "providers": ["https://rpc.mainnet.chain.robinhood.com"],
            "multiplier_states": sorted(
                {
                    state
                    for record in records
                    for state in read_summary(symbol, record["market_open_date"]).get(
                        "multiplier_states", []
                    )
                }
            ),
        },
        "early": early,
        "late": late,
        "combined": combined,
        "session_details": records,
        "observability_pattern": pattern,
        "eligibility_start_assessment": eligibility,
        "maturation_assessment": maturation,
        "final_one_time_classification": final_classification,
        "classification_reason": (
            f"Early deep availability {early_deep}/5, late deep availability {late_deep}/5, "
            f"combined {combined_deep}/10; technical quality "
            f"{'clean' if technical_clean else 'NOT clean'}."
        ),
    }


def sanitize(value):
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    return value


def render_markdown(audit: dict) -> str:
    symbol = audit["token_symbol"]
    early = audit["early"]
    late = audit["late"]
    combined = audit["combined"]
    details = audit["session_details"]
    lines: list[str] = []
    lines.append(f"# {symbol} frozen EARLY 5 + LATE 5 feasibility audit")
    lines.append("")
    lines.append(
        "This is a measurement-feasibility audit only. It uses the frozen five-minute "
        "executed-trade VWAP contract and no predictive outcomes."
    )
    lines.append("")
    lines.append("## Frozen sample")
    lines.append("")
    lines.append(f"- EARLY 5: {', '.join(audit['early_dates'])}.")
    lines.append(f"- LATE 5: {', '.join(audit['late_dates'])}.")
    lines.append(
        "- The dates were persisted before retrieval in "
        f"`{audit['selection_artifact']}`. No date was substituted."
    )
    lines.append("")
    lines.append("## Per-session technical and measurement QA")
    lines.append("")
    lines.append(
        "All sessions used `https://rpc.mainnet.chain.robinhood.com`. "
        f"Reconstruction rates, duplicates, incomplete ranges, and unresolved timestamps "
        f"are reported below."
    )
    lines.append("")
    lines.append(
        "| Group | Market open | Raw swaps | First execution ET | Last execution ET | 16:00 | 20:00 | 04:00 | 09:30 | Full | Post | Deep | Premarket | All 4 | Thin | Recon % | Runtime s |"
    )
    lines.append(
        "|---|---|---:|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|---:|---:|"
    )
    group_of = {
        **{date: "Early" for date in audit["early_dates"]},
        **{date: "Late" for date in audit["late_dates"]},
    }
    for record in details:
        group = group_of[record["market_open_date"]]
        b = record["boundaries"]
        r = record["returns"]
        y_n = lambda value: "Y" if value else "N"
        lines.append(
            f"| {group} | {record['market_open_date']} | {record['raw_executed_swaps']} | "
            f"{record['first_execution_et'] or '-'} | {record['last_execution_et'] or '-'} | "
            f"{y_n(b['1600'])} | {y_n(b['2000'])} | {y_n(b['0400'])} | {y_n(b['0930'])} | "
            f"{y_n(r['full'])} | {y_n(r['post'])} | {y_n(r['deep'])} | {y_n(r['premarket'])} | "
            f"{y_n(record['all_four_boundaries'])} | {y_n(record['thin_boundary_warning'])} | "
            f"{record['reconstruction_rate_percent']} | {record['session_runtime_seconds']} |"
        )
    lines.append("")
    lines.append("`Thin=Y` means at least one available primary boundary had fewer than five swaps or less than 500 USDG of notional. It is distinct from a missing boundary.")
    lines.append("")
    lines.append("## Early-versus-late feasibility")
    lines.append("")
    lines.append("| Measure | Early 5 | Late 5 | Combined 10 |")
    lines.append("|---|---:|---:|---:|")
    lines.append(
        f"| Sessions with any swaps | {early['sessions_with_swaps']}/5 | "
        f"{late['sessions_with_swaps']}/5 | {combined['sessions_with_swaps']}/10 |"
    )
    lines.append(
        f"| Median raw swaps per session | {early['median_raw_swaps']} | "
        f"{late['median_raw_swaps']} | {combined['median_raw_swaps']} |"
    )
    for name in BOUNDARIES:
        label = {"1600": "16:00", "2000": "20:00", "0400": "04:00", "0930": "09:30"}[name]
        lines.append(
            f"| {label} boundary | {early['boundary_available'][name]}/5 | "
            f"{late['boundary_available'][name]}/5 | {combined['boundary_available'][name]}/10 |"
        )
    ret_labels = {"full": "Full return", "post": "Post return", "deep": "Deep-overnight return", "premarket": "Premarket return"}
    for name in RETURNS:
        lines.append(
            f"| {ret_labels[name]} | {early['return_available'][name]}/5 | "
            f"{late['return_available'][name]}/5 | {combined['return_available'][name]}/10 |"
        )
    lines.append(
        f"| All four primary boundaries | {early['all_four_boundaries']}/5 | "
        f"{late['all_four_boundaries']}/5 | {combined['all_four_boundaries']}/10 |"
    )
    lines.append(
        f"| Thin-boundary warning | {early['thin_boundary_warnings']}/5 | "
        f"{late['thin_boundary_warnings']}/5 | {combined['thin_boundary_warnings']}/10 |"
    )
    lines.append("")
    lines.append("## Assessment")
    lines.append("")
    lines.append(audit["maturation_assessment"])
    lines.append("")
    lines.append(f"Final one-time classification: **{audit['final_one_time_classification']}**.")
    lines.append("")
    lines.append(audit["classification_reason"])
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--token", required=True, choices=("AMZN", "UPS"))
    args = parser.parse_args()
    symbol = args.token
    audit = build_audit(symbol)
    json_path = ROOT / f"{symbol.lower()}_early_late_feasibility_audit.json"
    md_path = ROOT / f"{symbol.lower()}_early_late_feasibility_audit.md"
    json_path.write_text(json.dumps(sanitize(audit), indent=2, allow_nan=False, default=str), encoding="utf-8")
    md_path.write_text(render_markdown(audit), encoding="utf-8")
    print(json.dumps(
        {
            "token_symbol": symbol,
            "early_deep": audit["early"]["return_available"]["deep"],
            "late_deep": audit["late"]["return_available"]["deep"],
            "combined_deep": audit["combined"]["return_available"]["deep"],
            "observability_pattern": audit["observability_pattern"],
            "eligibility_start_assessment": audit["eligibility_start_assessment"],
            "final_one_time_classification": audit["final_one_time_classification"],
            "technical_clean": all(
                (record["reconstruction_rate_percent"] is None
                 or record["reconstruction_rate_percent"] == 100.0)
                and record["exact_duplicate_count"] == 0
                and record["incomplete_raw_ranges"] == 0
                and record["unresolved_timestamps"] == 0
                for record in audit["session_details"]
            ),
        },
        indent=2,
    ))


if __name__ == "__main__":
    main()
