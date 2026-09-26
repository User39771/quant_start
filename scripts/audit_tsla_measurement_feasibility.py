"""Audit TSLA measurement availability from completed local artifacts only."""

from __future__ import annotations

import bisect
import json
from pathlib import Path

import pandas as pd


ROOT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")
SESSIONS = ROOT / "sessions" / "TSLA"
BOUNDARIES = ("1600", "2000", "0400", "0930")
POOL_CREATED_UTC = "2026-07-08T22:06:17Z"


def atomic_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    directories = sorted(path for path in SESSIONS.iterdir() if (path / "summary.json").exists())
    if len(directories) != 41:
        raise RuntimeError(f"expected 41 completed TSLA sessions, found {len(directories)}")

    chronology = []
    measurements = []
    all_executions: list[pd.Timestamp] = []
    summaries = []
    unresolved = 0
    for directory in directories:
        summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
        measurement = pd.read_csv(directory / "measurement_row.csv").iloc[0]
        decoded = pd.read_csv(directory / "decoded_swaps.csv")
        timestamps = pd.to_datetime(decoded["block_timestamp_et"], utc=True) if not decoded.empty else pd.Series(dtype="datetime64[ns, UTC]")
        all_executions.extend(timestamps.tolist())
        required_blocks = set(decoded["block_number"].astype(int)) if not decoded.empty else set()
        timestamp_map = json.loads((directory / "block_timestamps.json").read_text(encoding="utf-8")) if (directory / "block_timestamps.json").exists() else {}
        unresolved += len(required_blocks - {int(block) for block in timestamp_map})
        available = {name: pd.notna(measurement[f"token_vwap_{name}"]) for name in BOUNDARIES}
        chronology.append(
            {
                "market_open_date": directory.name,
                "raw_swap_count": int(summary["raw_event_count"]),
                "any_swaps": bool(summary["raw_event_count"]),
                "first_execution_timestamp_utc": timestamps.min().isoformat() if len(timestamps) else "",
                "last_execution_timestamp_utc": timestamps.max().isoformat() if len(timestamps) else "",
                **{f"vwap_{name}_available": available[name] for name in BOUNDARIES},
                "thin_boundary_flag": bool(measurement["thin_boundary_flag"]),
            }
        )
        measurements.append((directory, measurement, available))
        summaries.append(summary)

    chronology_frame = pd.DataFrame(chronology)
    chronology_frame.to_csv(ROOT / "tsla_measurement_feasibility_chronology.csv", index=False)
    active_index = next(
        index
        for index in range(len(chronology))
        if all(row["any_swaps"] for row in chronology[index:])
    )
    active_start = chronology[active_index]["market_open_date"]

    definitions = {
        "full": ("1600", "0930"),
        "post": ("1600", "2000"),
        "deep_overnight": ("2000", "0400"),
        "premarket": ("0400", "0930"),
        "all_four": BOUNDARIES,
    }

    def availability(rows: list[dict]) -> dict:
        result = {}
        for name, needed in definitions.items():
            count = sum(all(row[f"vwap_{boundary}_available"] for boundary in needed) for row in rows)
            result[name] = {"count": count, "denominator": len(rows), "percentage": 100 * count / len(rows)}
        return result

    all_executions.sort()
    execution_values = [timestamp.value for timestamp in all_executions]
    missing_rows = []
    missing_summary = {}
    for name in BOUNDARIES:
        boundary_missing = []
        for directory, measurement, available in measurements:
            if available[name]:
                continue
            start = pd.Timestamp(measurement["session_start_et"])
            end = pd.Timestamp(measurement["session_end_et_exclusive"])
            targets = {
                "1600": start,
                "2000": start.normalize() + pd.Timedelta(hours=20),
                "0400": end.normalize() + pd.Timedelta(hours=4),
                "0930": end,
            }
            target = targets[name].tz_convert("UTC")
            position = bisect.bisect_left(execution_values, target.value)
            preceding = all_executions[position - 1].isoformat() if position else ""
            following = all_executions[position].isoformat() if position < len(all_executions) else ""
            row = {
                "boundary": name,
                "market_open_date": directory.name,
                "boundary_timestamp_utc": target.isoformat(),
                "nearest_preceding_execution_utc": preceding,
                "nearest_following_execution_utc": following,
            }
            missing_rows.append(row)
            boundary_missing.append(directory.name)
        missing_summary[name] = {
            "missing_session_count": len(boundary_missing),
            "missing_dates": boundary_missing,
            "initial_zero_period_missing": sum(date < active_start for date in boundary_missing),
            "active_history_missing": sum(date >= active_start for date in boundary_missing),
        }
    pd.DataFrame(missing_rows).to_csv(ROOT / "tsla_missing_boundary_audit.csv", index=False)

    raw = sum(int(summary["raw_event_count"]) for summary in summaries)
    reconstructable = sum(int(summary["reconstructable_price_count"]) for summary in summaries)
    runtime = [summary.get("runtime_diagnostics", {}) for summary in summaries]
    result = {
        "nominal_sessions": 41,
        "pool_creation_utc": POOL_CREATED_UTC,
        "nominal_first_market_open_date": chronology[0]["market_open_date"],
        "first_session_with_swaps": next(row["market_open_date"] for row in chronology if row["any_swaps"]),
        "continuous_activity_start": active_start,
        "initial_zero_swap_sessions": active_index,
        "availability_nominal": availability(chronology),
        "availability_after_initial_zero_period": availability(chronology[active_index:]),
        "missing_boundaries": missing_summary,
        "quality": {
            "raw_swaps": raw,
            "reconstructable_swaps": reconstructable,
            "reconstruction_rate": reconstructable / raw if raw else None,
            "exact_duplicates": sum(int(summary["exact_duplicates_removed"]) for summary in summaries),
            "incomplete_raw_ranges": sum(summary["completion_status"] != "complete" for summary in summaries),
            "unresolved_execution_timestamps": unresolved,
            "source_providers": sorted({summary["source_provider"] for summary in summaries}),
            "multiplier_states": sorted({value for summary in summaries for value in summary["multiplier_states"]}),
        },
        "persisted_completion_run_cache_diagnostics": {
            "session_checkpoint_hits": sum(item.get("total_timestamp_checkpoint_hits", 0) for item in runtime),
            "global_cache_hits": sum(item.get("total_global_timestamp_cache_hits", 0) for item in runtime),
            "rpc_timestamp_misses": sum(item.get("total_timestamp_rpc_misses", 0) for item in runtime),
            "new_global_cache_rows": sum(item.get("total_newly_inserted_global_cache_rows", 0) for item in runtime),
        },
        "eligibility_start_classification": "ELIGIBILITY_START_TOO_EARLY" if active_index else "ELIGIBILITY_START_OK",
        "candidate_corrected_start": active_start if active_index else None,
        "panel_suitability_classification": "TSLA_PANEL_NOT_USEFUL_FOR_PRIMARY_DEEP_ANALYSIS",
        "recommendation_for_human_review": (
            "If approved, move TSLA's eligibility start to the first continuously active session and retain TSLA "
            "as a secondary/sensitivity asset; do not treat it as a core primary deep-overnight asset under the "
            "unchanged five-minute boundaries."
        ),
    }
    cache = result["persisted_completion_run_cache_diagnostics"]
    cache["aggregate_global_cache_hit_rate_non_checkpoint"] = (
        cache["global_cache_hits"] / (cache["global_cache_hits"] + cache["rpc_timestamp_misses"])
        if cache["global_cache_hits"] or cache["rpc_timestamp_misses"] else None
    )
    atomic_json(ROOT / "tsla_measurement_feasibility_audit.json", result)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
