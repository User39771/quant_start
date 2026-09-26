"""Resumable 20-session NVDA/USDG Phase 0 data-quality audit."""

from __future__ import annotations

import argparse
import csv
import json
import math
import shutil
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from audit_robinhood_chain_phase0 import ASSETS_URL, CORPORATE_ACTIONS_URL, UTC, market_schedule, url_json
from forensic_nvda_session_retrieval import (
    CHUNK_LOG_PATH as FORENSIC_CHUNK_LOG,
    FALLBACK_RPC,
    INITIAL_CHUNK_BLOCKS,
    MINIMUM_CHUNK_BLOCKS,
    NVDA_POOL,
    OFFICIAL_RPC,
    RAW_EVENTS_PATH as FORENSIC_RAW_EVENTS,
    decode,
    first_block_at_or_after,
    query,
    ranges_cover_exactly,
)


OUTPUT_DIR = Path("reports/robinhood_chain_phase0/nvda_20_session")
SESSIONS_DIR = OUTPUT_DIR / "sessions"
QUALITY_TABLE = OUTPUT_DIR / "nvda_session_quality.csv"
AUDIT_SUMMARY = OUTPUT_DIR / "summary.json"
FORENSIC_OPEN_DATE = "2026-08-11"
LARGE_GAP_MINUTES = 60


def atomic_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def append_csv(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def official_log_attempt(session: requests.Session, first: int, last: int, retry_count: int) -> tuple[list[dict] | None, dict]:
    started = time.perf_counter()
    http_status = None
    condition = None
    events = None
    try:
        response = session.post(
            OFFICIAL_RPC,
            json={"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [query(first, last)]},
            timeout=40,
            headers={"User-Agent": "nvda-phase0-resumable/0.1"},
        )
        http_status = response.status_code
        if response.status_code == 429:
            condition = "rate_limit"
        else:
            response.raise_for_status()
            payload = response.json()
            if "result" in payload:
                events = payload["result"]
                condition = "success"
            else:
                message = str(payload.get("error", "")).lower()
                condition = "cap" if "limit" in message or "exceed" in message else "rpc_timeout" if "timeout" in message or "busy" in message else "rpc_error"
    except requests.Timeout:
        condition = "timeout"
    except requests.RequestException:
        condition = "http_error"
    return events, {
        "provider": "official_robinhood",
        "block_start": first,
        "block_end": last,
        "block_count": last - first + 1,
        "http_status": http_status,
        "status": condition,
        "retry_count": retry_count,
        "response_event_count": len(events) if events is not None else 0,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def retrieve_session_chunks(session_dir: Path, first_block: int, last_block: int) -> tuple[list[dict], int]:
    state_path = session_dir / "retrieval_state.json"
    attempts_path = session_dir / "chunk_attempts.csv"
    chunks_dir = session_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        assert state["exact_block_range"] == [first_block, last_block]
        if state["pending"]:
            state["status"] = "in_progress"
            atomic_json(state_path, state)
    else:
        state = {
            "exact_block_range": [first_block, last_block],
            "minimum_chunk_blocks": MINIMUM_CHUNK_BLOCKS,
            "pending": [
                [start, min(start + INITIAL_CHUNK_BLOCKS - 1, last_block)]
                for start in range(first_block, last_block + 1, INITIAL_CHUNK_BLOCKS)
            ],
            "successful": [],
            "status": "in_progress",
        }
        atomic_json(state_path, state)
    request_count = 0
    http_session = requests.Session()
    while state["pending"]:
        first, last = state["pending"][0]
        chunk_path = chunks_dir / f"{first}_{last}.json"
        if chunk_path.exists():
            state["pending"].pop(0)
            if [first, last] not in state["successful"]:
                state["successful"].append([first, last])
            atomic_json(state_path, state)
            continue
        retries = 0
        while True:
            events, attempt = official_log_attempt(http_session, first, last, retries)
            request_count += 1
            append_csv(attempts_path, attempt)
            if events is not None:
                atomic_json(chunk_path, events)
                state["pending"].pop(0)
                state["successful"].append([first, last])
                atomic_json(state_path, state)
                break
            at_minimum = last - first + 1 <= MINIMUM_CHUNK_BLOCKS
            transient = attempt["status"] in {"rate_limit", "timeout", "http_error", "rpc_timeout"}
            retry_limit = 8 if at_minimum else 4
            if transient and retries < retry_limit:
                retries += 1
                time.sleep(min(2**retries, 30))
                continue
            width = last - first + 1
            if width <= MINIMUM_CHUNK_BLOCKS:
                state["status"] = "incomplete_minimum_chunk_failed"
                atomic_json(state_path, state)
                raise RuntimeError(f"Terminal chunk failed at minimum size: {first}-{last}")
            middle = (first + last) // 2
            state["pending"][:1] = [[first, middle], [middle + 1, last]]
            atomic_json(state_path, state)
            break
    successful = sorted(tuple(bounds) for bounds in state["successful"])
    assert ranges_cover_exactly(successful, first_block, last_block)
    state["status"] = "raw_complete"
    atomic_json(state_path, state)
    events = []
    for first, last in successful:
        events.extend(json.loads((chunks_dir / f"{first}_{last}.json").read_text(encoding="utf-8")))
    return events, request_count


def batch_block_timestamps(blocks: list[int], cache_path: Path) -> dict[int, int]:
    cache = {int(block): timestamp for block, timestamp in json.loads(cache_path.read_text(encoding="utf-8")).items()} if cache_path.exists() else {}
    missing = [block for block in sorted(set(blocks)) if block not in cache]
    session = requests.Session()
    for offset in range(0, len(missing), 100):
        batch = missing[offset : offset + 100]
        payload = [
            {"jsonrpc": "2.0", "id": index, "method": "eth_getBlockByNumber", "params": [hex(block), False]}
            for index, block in enumerate(batch)
        ]
        for retry in range(10):
            try:
                response = session.post(
                    FALLBACK_RPC,
                    json=payload,
                    timeout=60,
                    headers={"User-Agent": "nvda-phase0-resumable/0.1"},
                )
            except requests.RequestException:
                time.sleep(min(2 ** (retry + 1), 30))
                continue
            if response.status_code == 429 or response.status_code >= 500:
                time.sleep(min(2 ** (retry + 1), 30))
                continue
            response.raise_for_status()
            result = response.json()
            if not isinstance(result, list) or any("error" in item for item in result):
                time.sleep(2 ** (retry + 1))
                continue
            by_id = {item["id"]: item for item in result}
            cache.update({block: int(by_id[index]["result"]["timestamp"], 16) for index, block in enumerate(batch)})
            atomic_json(cache_path, {str(block): timestamp for block, timestamp in cache.items()})
            print(f"Timestamp blocks checkpointed: {len(cache)}", flush=True)
            time.sleep(0.2)
            break
        else:
            raise RuntimeError(f"Could not retrieve block timestamps for batch starting {batch[0]}")
    return cache


def unique_events(events: list[dict]) -> tuple[list[dict], int]:
    by_key = {}
    for event in events:
        key = (event["transactionHash"].lower(), int(event["logIndex"], 16))
        by_key.setdefault(key, event)
    ordered = sorted(by_key.values(), key=lambda event: (int(event["blockNumber"], 16), int(event["logIndex"], 16)))
    return ordered, len(events) - len(ordered)


def summarize_decoded(
    open_date: str,
    start_et: datetime,
    end_et: datetime,
    first_block: int,
    last_block: int,
    decoded: list[dict],
    duplicates_removed: int,
    terminal_chunks: int,
    retrieval_requests: int,
    runtime_seconds: float | None,
    reused_forensic: bool,
) -> dict:
    timestamps = sorted(row["block_timestamp_utc"] for row in decoded)
    start_timestamp = int(start_et.astimezone(UTC).timestamp())
    end_timestamp = int(end_et.astimezone(UTC).timestamp())
    gaps = [right - left for left, right in zip([start_timestamp, *timestamps], [*timestamps, end_timestamp])]
    reconstructable = sum(row["reconstructable"] for row in decoded)
    quote_sizes = [row["quote_amount_usdg"] for row in decoded if row["reconstructable"]]
    return {
        "market_open_date": open_date,
        "session_start_et": start_et.isoformat(),
        "session_end_et_exclusive": end_et.isoformat(),
        "exact_block_start": first_block,
        "exact_block_end": last_block,
        "terminal_chunk_count": terminal_chunks,
        "retrieval_request_count_this_completion": retrieval_requests,
        "raw_unique_swap_count": len(decoded),
        "exact_duplicates_removed": duplicates_removed,
        "decoded_swap_count": len(decoded),
        "swap_fill_count": len(decoded),
        "active_trading_minutes": len({timestamp // 60 for timestamp in timestamps}),
        "usdg_notional": sum(quote_sizes),
        "median_trade_size_usdg": statistics.median(quote_sizes) if quote_sizes else None,
        "first_execution_timestamp_et": datetime.fromtimestamp(timestamps[0], UTC).astimezone(start_et.tzinfo).isoformat() if timestamps else None,
        "last_execution_timestamp_et": datetime.fromtimestamp(timestamps[-1], UTC).astimezone(start_et.tzinfo).isoformat() if timestamps else None,
        "largest_execution_gap_minutes": max(gaps) / 60,
        "large_gap_ge_60m": max(gaps) >= LARGE_GAP_MINUTES * 60,
        "reconstructable_price_count": reconstructable,
        "reconstructable_price_percentage": 100 * reconstructable / len(decoded) if decoded else None,
        "zero_trade_session": not decoded,
        "unique_economic_traders": None,
        "unique_trader_note": "unavailable: Uniswap sender/recipient may be router or hook",
        "historical_multiplier": 1.0,
        "multiplier_basis": "current multiplier 1.0 and no NVDA corporate action effective in sample",
        "raw_log_provider": OFFICIAL_RPC,
        "block_timestamp_provider": FALLBACK_RPC,
        "terminal_block_coverage_complete": True,
        "completion_status": "complete",
        "reused_forensic_artifact": reused_forensic,
        "session_runtime_seconds": runtime_seconds,
        "session_runtime_note": "reused prior forensic artifact" if reused_forensic else "exact wall time unavailable after interrupted resume" if runtime_seconds is None else "uninterrupted wall time",
    }


def write_decoded(path: Path, decoded: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(decoded[0]) if decoded else ["block_number"])
        writer.writeheader()
        writer.writerows(decoded)


def finish_events(
    session_dir: Path,
    open_date: str,
    start_et: datetime,
    end_et: datetime,
    first_block: int,
    last_block: int,
    events: list[dict],
    retrieval_requests: int,
    runtime_seconds: float,
    reused_forensic: bool,
) -> dict:
    events, duplicates_removed = unique_events(events)
    blocks = [int(event["blockNumber"], 16) for event in events]
    timestamps = batch_block_timestamps(blocks, session_dir / "block_timestamps.json")
    decoded = []
    for event in events:
        row = decode(event, 1.0)
        row["block_timestamp_utc"] = timestamps[row["block_number"]]
        row["block_timestamp_et"] = datetime.fromtimestamp(row["block_timestamp_utc"], UTC).astimezone(start_et.tzinfo).isoformat()
        decoded.append(row)
    assert all(
        not row["reconstructable"] or math.isfinite(row["execution_price_usdg_per_token"])
        for row in decoded
    )
    write_decoded(session_dir / "decoded_swaps.csv", decoded)
    state_path = session_dir / "retrieval_state.json"
    terminal_chunks = len(json.loads(state_path.read_text(encoding="utf-8"))["successful"]) if state_path.exists() else 128
    summary = summarize_decoded(
        open_date,
        start_et,
        end_et,
        first_block,
        last_block,
        decoded,
        duplicates_removed,
        terminal_chunks,
        retrieval_requests,
        runtime_seconds,
        reused_forensic,
    )
    atomic_json(session_dir / "summary.json", summary)
    return summary


def bootstrap_forensic(schedule: list[dict]) -> None:
    session_dir = SESSIONS_DIR / FORENSIC_OPEN_DATE
    if (session_dir / "summary.json").exists():
        return
    session = next(item for item in schedule if item["market_open_date"].isoformat() == FORENSIC_OPEN_DATE)
    session_dir.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(FORENSIC_CHUNK_LOG, session_dir / "chunk_attempts.csv")
    raw_rows = list(csv.DictReader(FORENSIC_RAW_EVENTS.open(encoding="utf-8-sig")))
    blocks = [int(row["block_number"]) for row in raw_rows]
    timestamps = batch_block_timestamps(blocks, session_dir / "block_timestamps.json")
    decoded = []
    for row in raw_rows:
        block = int(row["block_number"])
        decoded.append(
            {
                "block_number": block,
                "transaction_hash": row["transaction_hash"],
                "log_index": int(row["log_index"]),
                "event_sender": row["event_sender"],
                "recipient": row["recipient"],
                "quote_amount_usdg": float(row["quote_amount_usdg"]),
                "token_amount_nvda": float(row["token_amount_nvda"]),
                "execution_price_usdg_per_token": float(row["execution_price_usdg_per_token"]),
                "underlying_equivalent_price_usdg": float(row["underlying_equivalent_price_usdg"]),
                "reconstructable": row["reconstructable"].lower() == "true",
                "block_timestamp_utc": timestamps[block],
                "block_timestamp_et": datetime.fromtimestamp(timestamps[block], UTC).astimezone(session["window_start_et"].tzinfo).isoformat(),
            }
        )
    write_decoded(session_dir / "decoded_swaps.csv", decoded)
    summary = summarize_decoded(
        FORENSIC_OPEN_DATE,
        session["window_start_et"],
        session["window_end_et"],
        33_069_045,
        33_698_598,
        decoded,
        duplicates_removed=0,
        terminal_chunks=128,
        retrieval_requests=0,
        runtime_seconds=0.0,
        reused_forensic=True,
    )
    atomic_json(session_dir / "summary.json", summary)
    assert summary["raw_unique_swap_count"] == 3159
    print("Reused validated 2026-08-11 forensic session without re-fetching logs.", flush=True)


def completed_summaries(schedule: list[dict]) -> list[dict]:
    rows = []
    for item in schedule:
        path = SESSIONS_DIR / item["market_open_date"].isoformat() / "summary.json"
        if path.exists():
            summary = json.loads(path.read_text(encoding="utf-8"))
            if summary.get("completion_status") == "complete":
                rows.append(summary)
    return rows


def write_aggregate(schedule: list[dict]) -> list[dict]:
    rows = completed_summaries(schedule)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if rows:
        with QUALITY_TABLE.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    summary = {
        "sessions_completed": len(rows),
        "sessions_total": 20,
        "remaining_sessions": 20 - len(rows),
        "completed_market_opens": [row["market_open_date"] for row in rows],
    }
    if len(rows) == 20:
        total_swaps = sum(row["swap_fill_count"] for row in rows)
        total_notional = sum(row["usdg_notional"] for row in rows)
        reconstructable = sum(row["reconstructable_price_count"] for row in rows)
        session_minutes = [
            (datetime.fromisoformat(row["session_end_et_exclusive"]) - datetime.fromisoformat(row["session_start_et"])).total_seconds() / 60
            for row in rows
        ]
        active_ratios = [row["active_trading_minutes"] / minutes for row, minutes in zip(rows, session_minutes)]
        all_trade_sizes = []
        for row in rows:
            path = SESSIONS_DIR / row["market_open_date"] / "decoded_swaps.csv"
            all_trade_sizes.extend(float(item["quote_amount_usdg"]) for item in csv.DictReader(path.open(encoding="utf-8-sig")))
        summary.update(
            {
                "nonempty_sessions": sum(not row["zero_trade_session"] for row in rows),
                "total_swaps": total_swaps,
                "median_swaps_per_session": statistics.median(row["swap_fill_count"] for row in rows),
                "total_overnight_notional_usdg": total_notional,
                "median_session_notional_usdg": statistics.median(row["usdg_notional"] for row in rows),
                "median_trade_size_usdg": statistics.median(all_trade_sizes),
                "total_active_trading_minutes": sum(row["active_trading_minutes"] for row in rows),
                "median_active_minutes_per_session": statistics.median(row["active_trading_minutes"] for row in rows),
                "total_session_minutes": sum(session_minutes),
                "aggregate_active_minute_coverage": sum(row["active_trading_minutes"] for row in rows) / sum(session_minutes),
                "median_session_active_minute_coverage": statistics.median(active_ratios),
                "price_reconstruction_success_rate": reconstructable / total_swaps if total_swaps else None,
                "sessions_with_large_execution_gaps": sum(row["large_gap_ge_60m"] for row in rows),
                "retrieval_failures_or_incomplete_sessions": 0,
            }
        )
        active_ratio = summary["median_session_active_minute_coverage"]
        summary["assessment"] = "PASS" if summary["nonempty_sessions"] >= 18 and summary["price_reconstruction_success_rate"] >= 0.99 and active_ratio >= 0.25 else "CONDITIONAL PASS" if summary["nonempty_sessions"] >= 10 and summary["price_reconstruction_success_rate"] >= 0.95 else "FAIL"
    atomic_json(AUDIT_SUMMARY, summary)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-sessions-this-run", type=int, default=3)
    args = parser.parse_args()
    if args.max_sessions_this_run < 1:
        parser.error("--max-sessions-this-run must be positive")

    assets = url_json(ASSETS_URL)["assets"]
    nvda = next(asset for asset in assets if asset["tokenSymbol"] == "NVDA")
    contract = next(item["contractAddress"] for item in nvda["deployments"] if item["chainId"] == 4663)
    assert contract.lower() == "0xd0601ce157db5bdc3162bbac2a2c8af5320d9eec" and nvda["currentMultiplier"] == "1.000000000000000000"
    effective_actions = [
        action
        for action in url_json(CORPORATE_ACTIONS_URL).get("corpActions", [])
        if action.get("tokenSymbol") == "NVDA" and action.get("processDate")
        and (action["processDate"]["year"], action["processDate"]["month"], action["processDate"]["day"]) <= (2026, 9, 4)
    ]
    assert not effective_actions
    schedule = market_schedule()
    bootstrap_forensic(schedule)
    completed = {row["market_open_date"] for row in completed_summaries(schedule)}
    pending = [item for item in schedule if item["market_open_date"].isoformat() not in completed]
    selected = pending[: args.max_sessions_this_run]
    cumulative_started = time.perf_counter()
    for item in selected:
        open_date = item["market_open_date"].isoformat()
        session_dir = SESSIONS_DIR / open_date
        session_dir.mkdir(parents=True, exist_ok=True)
        session_started = time.perf_counter()
        state_path = session_dir / "retrieval_state.json"
        resumed_session = state_path.exists()
        if resumed_session:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            first_block, last_block = state["exact_block_range"]
        else:
            boundary_session = requests.Session()
            first_block = first_block_at_or_after(boundary_session, OFFICIAL_RPC, int(item["window_start_et"].astimezone(UTC).timestamp()))
            last_block = first_block_at_or_after(boundary_session, OFFICIAL_RPC, int(item["window_end_et"].astimezone(UTC).timestamp())) - 1
        events, retrieval_requests = retrieve_session_chunks(session_dir, first_block, last_block)
        summary = finish_events(
            session_dir,
            open_date,
            item["window_start_et"],
            item["window_end_et"],
            first_block,
            last_block,
            events,
            retrieval_requests,
            None if resumed_session else time.perf_counter() - session_started,
            reused_forensic=False,
        )
        rows = write_aggregate(schedule)
        print(f"Completed {len(rows)} / 20", flush=True)
        runtime = summary["session_runtime_seconds"]
        print(f"Session runtime: {runtime:.1f}s" if runtime is not None else "Session runtime: unavailable after interrupted resume", flush=True)
        print(f"Cumulative runtime: {time.perf_counter() - cumulative_started:.1f}s", flush=True)
        print(f"Remaining sessions: {20 - len(rows)}", flush=True)
    if not selected:
        rows = write_aggregate(schedule)
        print(f"No incomplete sessions selected. Completed {len(rows)} / 20.", flush=True)


if __name__ == "__main__":
    main()
