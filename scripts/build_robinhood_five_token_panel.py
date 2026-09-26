"""Build the fixed five-token Robinhood Chain overnight panel, resumably.

This is deliberately a bounded research-data constructor, not a pipeline or
strategy. Raw Swap logs come from the official Robinhood Chain RPC and every
successful terminal block chunk is persisted before the next request.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import time
from datetime import date, datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests

from audit_robinhood_chain_phase0 import NYSE_EARLY_CLOSES_2026, NYSE_HOLIDAYS_2026, V3_SWAP_TOPIC
from forensic_nvda_session_retrieval import OFFICIAL_RPC, first_block_at_or_after, signed_256
from robinhood_timestamp_cache import insert_exact_timestamps, lookup_timestamps


ROOT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")
SESSIONS = ROOT / "sessions"
SESSION_LEDGER = ROOT / "session_checkpoint.csv"
PANEL_CSV = ROOT / "five_token_unbalanced_session_panel.csv"
COVERAGE_CSV = ROOT / "per_token_coverage.csv"
QA_JSON = ROOT / "data_quality_summary.json"
QA_MD = ROOT / "data_quality_summary.md"
BOUNDARY_CACHE = ROOT / "block_boundary_cache.json"
GLOBAL_TIMESTAMP_CACHE = ROOT / "global_exact_block_timestamps.sqlite3"
INVENTORY = Path("reports/robinhood_chain_pilot/eligible_token_inventory/eligible_token_inventory.csv")
NVDA_SOURCE = Path("reports/robinhood_chain_phase0/nvda_20_session")
NVDA_MEASUREMENTS = Path("reports/robinhood_chain_pilot/nvda_20_session/nvda_overnight_session_measurements.csv")

NEW_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc
USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
CUTOFF = date(2026, 9, 4)
INITIAL_CHUNK_BLOCKS = 5_000
MINIMUM_CHUNK_BLOCKS = 250
THIN_MIN_SWAPS = 5
THIN_MIN_NOTIONAL = 500.0
SEGMENTS = ("post", "deep", "premarket", "full")
BOUNDARIES = ("1600", "2000", "0400", "0930")
TIMESTAMP_BATCH_SIZE = 100
RESEARCH_ELIGIBLE_STARTS = {"TSLA": "2026-07-21"}

TOKENS = {
    "NVDA": {
        "contract": "0xd0601CE157Db5bdC3162BbaC2a2C8aF5320D9EEC",
        "pool": "0xd4EB21209C4D6093f80B5b84f5C45cc093EA14a3",
        "pool_start": "2026-07-21T11:02:06Z",
        "assetclass": "stocks",
    },
    "GME": {
        "contract": "0x1b0E319c6A659F002271B69dB8A7df2F911c153E",
        "pool": "0xE2b46c905E12Ab8E2f864e4821a4325884C1B126",
        "pool_start": "2026-07-23T20:27:17Z",
        "assetclass": "stocks",
    },
    "TSLA": {
        "contract": "0x322F0929c4625eD5bAd873c95208D54E1c003b2d",
        "pool": "0xf4ACdAEEB7022862A763C9B1B885e11191c889E3",
        "pool_start": "2026-07-08T22:06:17Z",
        "assetclass": "stocks",
    },
    "COST": {
        "contract": "0x4EA005168D7F09a7A0Ba9D1DEf21a479950E44C2",
        "pool": "0x0a2121A50A09eD0796ae81F9c53fF9398355a398",
        "pool_start": "2026-07-22T23:51:49Z",
        "assetclass": "stocks",
    },
    "USO": {
        "contract": "0xa30FA36Db767ad9eD3f7a60fC79526fB4d56D344",
        "pool": "0x02175608F1b5E6b5ed221cCFdC7Be197D111D915",
        "pool_start": "2026-07-17T09:45:08Z",
        "assetclass": "etf",
    },
    "AMZN": {
        "contract": "0x12f190a9F9d7D37a250758b26824B97CE941bF54",
        "pool": "0x8AC92DA74AB5F3b1d024Dc1943Ad7e15Dc4179Ef",
        "pool_start": "2026-07-21T06:01:54Z",
        "assetclass": "stocks",
    },
    "UPS": {
        "contract": "0xf23250dac154D05Bb671CB0d0eBEf3c635c79CE2",
        "pool": "0x3Ab74C45DceCC6A62898204Dd42143a816B44CB1",
        "pool_start": "2026-06-25T16:29:33Z",
        "assetclass": "stocks",
    },
}
BASE_PANEL_TOKEN_ORDER = ("NVDA", "GME", "TSLA", "COST", "USO")
TOKEN_ORDER = tuple(TOKENS)


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    replace_with_retry(temporary, path)


def replace_with_retry(temporary: Path, path: Path) -> None:
    # Windows readers/antivirus may briefly hold the destination. Retrying the
    # same atomic replace preserves the old complete checkpoint until success.
    for retry in range(20):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if retry == 19:
                raise
            time.sleep(0.1 * (retry + 1))


def atomic_json(path: Path, value) -> None:
    atomic_text(path, json.dumps(value, indent=2, allow_nan=False, default=str))


def atomic_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    names = fieldnames or (list(rows[0]) if rows else [])
    with temporary.open("w", newline="", encoding="utf-8-sig") as handle:
        if names:
            writer = csv.DictWriter(handle, fieldnames=names, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
    replace_with_retry(temporary, path)


def append_csv(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def is_market_day(day: date) -> bool:
    return day.weekday() < 5 and day not in NYSE_HOLIDAYS_2026


def all_sessions() -> dict[str, list[dict]]:
    days: list[date] = []
    day = date(2026, 7, 1)
    while day <= CUTOFF:
        if is_market_day(day):
            days.append(day)
        day += timedelta(days=1)
    pairs = []
    for previous_day, open_day in zip(days, days[1:]):
        close = clock_time(13) if previous_day in NYSE_EARLY_CLOSES_2026 else clock_time(16)
        start = datetime.combine(previous_day, close, NEW_YORK)
        end = datetime.combine(open_day, clock_time(9, 30), NEW_YORK)
        pairs.append({"market_open_date": open_day.isoformat(), "start_et": start, "end_et": end})
    result = {}
    for symbol, config in TOKENS.items():
        pool_start = datetime.fromisoformat(config["pool_start"].replace("Z", "+00:00"))
        result[symbol] = [item for item in pairs if item["start_et"].astimezone(UTC) >= pool_start]
    return result


def research_eligible(symbol: str, item: dict) -> bool:
    return item["market_open_date"] >= RESEARCH_ELIGIBLE_STARTS.get(symbol, "0000-00-00")


def select_pending_sessions(pending: list[tuple[str, dict]], requested_dates: list[str] | None, limit: int):
    if requested_dates is None:
        return pending[:limit]
    by_date = {item["market_open_date"]: (symbol, item) for symbol, item in pending}
    return [by_date[open_date] for open_date in requested_dates if open_date in by_date][:limit]


def rpc_call(http: requests.Session, method: str, params: list, timeout: int = 60):
    for retry in range(8):
        try:
            response = http.post(
                OFFICIAL_RPC,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=timeout,
                headers={"User-Agent": "robinhood-five-token-panel/0.1"},
            )
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.RequestException(str(response.status_code))
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                raise RuntimeError(payload["error"])
            return payload["result"]
        except (requests.RequestException, RuntimeError, ValueError):
            if retry == 7:
                raise
            time.sleep(min(2 ** (retry + 1), 30))


def eth_address_call(http: requests.Session, target: str, selector: str) -> str:
    result = rpc_call(http, "eth_call", [{"to": target, "data": selector}, "latest"])
    return "0x" + result[-40:]


def verify_pool_order(symbol: str) -> dict:
    path = ROOT / "token_metadata" / f"{symbol}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    config = TOKENS[symbol]
    http = requests.Session()
    token0 = eth_address_call(http, config["pool"], "0x0dfe1681")
    token1 = eth_address_call(http, config["pool"], "0xd21220a7")
    expected = {config["contract"].lower(), USDG}
    if {token0.lower(), token1.lower()} != expected:
        raise RuntimeError(f"{symbol} pool ordering integrity failure: {token0}, {token1}")
    metadata = {
        "token_symbol": symbol,
        "canonical_contract": config["contract"],
        "pool": config["pool"],
        "venue": "Uniswap V3",
        "pool_start_utc": config["pool_start"],
        "pool_token0": token0,
        "pool_token1": token1,
        "token_index": 0 if token0.lower() == config["contract"].lower() else 1,
        "quote_index": 0 if token0.lower() == USDG else 1,
        "token_decimals": 18,
        "quote_decimals": 6,
        "verified_via": f"eth_call token0()/token1() on {OFFICIAL_RPC}",
    }
    atomic_json(path, metadata)
    return metadata


def block_boundary(target: datetime) -> int:
    cache = json.loads(BOUNDARY_CACHE.read_text(encoding="utf-8")) if BOUNDARY_CACHE.exists() else {}
    key = str(int(target.astimezone(UTC).timestamp()))
    if key not in cache:
        cache[key] = first_block_at_or_after(requests.Session(), OFFICIAL_RPC, int(key))
        atomic_json(BOUNDARY_CACHE, cache)
    return int(cache[key])


def log_query(pool: str, first: int, last: int) -> dict:
    return {"address": pool, "topics": [V3_SWAP_TOPIC], "fromBlock": hex(first), "toBlock": hex(last)}


def attempt_logs(http: requests.Session, pool: str, first: int, last: int, retry: int) -> tuple[list[dict] | None, dict]:
    started = time.perf_counter()
    status = "unknown_error"
    http_status = None
    events = None
    try:
        response = http.post(
            OFFICIAL_RPC,
            json={"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [log_query(pool, first, last)]},
            timeout=40,
            headers={"User-Agent": "robinhood-five-token-panel/0.1"},
        )
        http_status = response.status_code
        if http_status == 429:
            status = "rate_limit"
        else:
            response.raise_for_status()
            payload = response.json()
            if "result" in payload:
                events, status = payload["result"], "success"
            else:
                message = str(payload.get("error", "")).lower()
                status = "cap" if "limit" in message or "exceed" in message else "rpc_timeout" if "timeout" in message or "busy" in message else "rpc_error"
    except requests.Timeout:
        status = "timeout"
    except (requests.RequestException, ValueError):
        status = "http_error"
    return events, {
        "provider": OFFICIAL_RPC,
        "block_start": first,
        "block_end": last,
        "block_count": last - first + 1,
        "http_status": http_status,
        "request_status": status,
        "retry_number": retry,
        "event_count": len(events) if events is not None else 0,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def checkpoint_rows(symbol: str, open_date: str, state: dict) -> list[dict]:
    return [
        {
            "token_symbol": symbol,
            "session_id": f"{symbol}_{open_date}",
            "block_start": item["block_start"],
            "block_end": item["block_end"],
            "provider": OFFICIAL_RPC,
            "event_count": item["event_count"],
            "request_status": "success",
            "retry_count": item["retry_count"],
            "split_depth": item["split_depth"],
            "completion_flag": True,
            "elapsed_seconds": item["elapsed_seconds"],
        }
        for item in sorted(state["successful"], key=lambda row: row["block_start"])
    ]


def validate_successful(session_dir: Path, state: dict) -> None:
    ranges = sorted((row["block_start"], row["block_end"]) for row in state["successful"])
    for (first, last), next_bounds in zip(ranges, ranges[1:]):
        if last >= next_bounds[0]:
            raise RuntimeError(f"overlapping saved chunks: {(first, last)}, {next_bounds}")
    for row in state["successful"]:
        path = session_dir / "chunks" / f"{row['block_start']}_{row['block_end']}.json"
        if not path.exists():
            raise RuntimeError(f"checkpointed chunk missing: {path}")
        if len(json.loads(path.read_text(encoding="utf-8"))) != row["event_count"]:
            raise RuntimeError(f"checkpoint event-count mismatch: {path}")


def retrieve_chunks(symbol: str, item: dict, first_block: int, last_block: int) -> tuple[list[dict], int]:
    open_date = item["market_open_date"]
    session_dir = SESSIONS / symbol / open_date
    chunks_dir = session_dir / "chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    state_path = session_dir / "retrieval_state.json"
    checkpoint_path = session_dir / "chunk_checkpoint.csv"
    attempts_path = session_dir / "chunk_attempts.csv"
    if state_path.exists():
        state = json.loads(state_path.read_text(encoding="utf-8"))
        if state["exact_block_range"] != [first_block, last_block]:
            raise RuntimeError(f"saved block range changed for {symbol} {open_date}")
        validate_successful(session_dir, state)
    else:
        state = {
            "token_symbol": symbol,
            "market_open_date": open_date,
            "exact_block_range": [first_block, last_block],
            "initial_chunk_blocks": INITIAL_CHUNK_BLOCKS,
            "minimum_chunk_blocks": MINIMUM_CHUNK_BLOCKS,
            "pending": [
                {"block_start": start, "block_end": min(start + INITIAL_CHUNK_BLOCKS - 1, last_block), "split_depth": 0}
                for start in range(first_block, last_block + 1, INITIAL_CHUNK_BLOCKS)
            ],
            "successful": [],
            "status": "in_progress",
        }
        atomic_json(state_path, state)
    request_count = 0
    http = requests.Session()
    while state["pending"]:
        pending = state["pending"][0]
        first, last, depth = pending["block_start"], pending["block_end"], pending["split_depth"]
        orphan_path = chunks_dir / f"{first}_{last}.json"
        if orphan_path.exists():
            # A crash can occur after the atomic chunk write but before the state
            # write. Adopt the valid saved chunk instead of refetching it.
            orphan_events = json.loads(orphan_path.read_text(encoding="utf-8"))
            state["pending"].pop(0)
            state["successful"].append(
                {"block_start": first, "block_end": last, "event_count": len(orphan_events), "retry_count": 0, "split_depth": depth, "elapsed_seconds": 0.0}
            )
            atomic_json(state_path, state)
            atomic_csv(checkpoint_path, checkpoint_rows(symbol, open_date, state))
            continue
        retries = 0
        while True:
            events, attempt = attempt_logs(http, TOKENS[symbol]["pool"], first, last, retries)
            request_count += 1
            attempt.update({"token_symbol": symbol, "session_id": f"{symbol}_{open_date}", "split_depth": depth})
            append_csv(attempts_path, attempt)
            if events is not None:
                atomic_json(chunks_dir / f"{first}_{last}.json", events)
                state["pending"].pop(0)
                state["successful"].append(
                    {"block_start": first, "block_end": last, "event_count": len(events), "retry_count": retries, "split_depth": depth, "elapsed_seconds": attempt["elapsed_seconds"]}
                )
                atomic_json(state_path, state)
                atomic_csv(checkpoint_path, checkpoint_rows(symbol, open_date, state))
                break
            width = last - first + 1
            transient = attempt["request_status"] in {"rate_limit", "timeout", "http_error", "rpc_timeout"}
            retry_limit = 8 if width <= MINIMUM_CHUNK_BLOCKS else 4
            if transient and retries < retry_limit:
                retries += 1
                time.sleep(min(2**retries, 30))
                continue
            if width <= MINIMUM_CHUNK_BLOCKS:
                state["status"] = "incomplete_minimum_chunk_failed"
                state["error"] = f"terminal chunk failed: {first}-{last}"
                atomic_json(state_path, state)
                raise RuntimeError(state["error"])
            middle = (first + last) // 2
            state["pending"][:1] = [
                {"block_start": first, "block_end": middle, "split_depth": depth + 1},
                {"block_start": middle + 1, "block_end": last, "split_depth": depth + 1},
            ]
            atomic_json(state_path, state)
            break
    successful = sorted(state["successful"], key=lambda row: row["block_start"])
    cursor = first_block
    for row in successful:
        if row["block_start"] != cursor:
            raise RuntimeError(f"gap in completed chunks at block {cursor}")
        cursor = row["block_end"] + 1
    if cursor != last_block + 1:
        raise RuntimeError(f"incomplete terminal coverage ending at {cursor - 1}")
    state["status"] = "raw_complete"
    atomic_json(state_path, state)
    events: list[dict] = []
    for row in successful:
        events.extend(json.loads((chunks_dir / f"{row['block_start']}_{row['block_end']}.json").read_text(encoding="utf-8")))
    return events, request_count


def batch_timestamps(blocks: list[int], path: Path) -> tuple[dict[int, int], dict]:
    cache = {int(key): int(value) for key, value in json.loads(path.read_text(encoding="utf-8")).items()} if path.exists() else {}
    required = sorted(set(blocks))
    session_hits = len(required) - sum(block not in cache for block in required)
    global_hits = lookup_timestamps(GLOBAL_TIMESTAMP_CACHE, (block for block in required if block not in cache))
    cache.update(global_hits)
    if global_hits:
        atomic_json(path, {str(block): timestamp for block, timestamp in cache.items()})
    missing = [block for block in required if block not in cache]
    stats = {
        "timestamps_required": len(required),
        "timestamps_reused": len(required) - len(missing),
        "timestamps_reused_from_session_checkpoint": session_hits,
        "timestamps_reused_from_global_cache": len(global_hits),
        "timestamp_rpc_misses": len(missing),
        "global_cache_hit_rate_among_session_checkpoint_misses": (
            len(global_hits) / (len(global_hits) + len(missing))
            if global_hits or missing else None
        ),
        "newly_inserted_global_cache_rows": 0,
        "timestamp_block_lookups": 0,
        "timestamp_rpc_batch_requests": 0,
        "timestamp_retry_events": 0,
        "timestamp_rate_limit_events": 0,
        "timestamp_timeout_events": 0,
    }
    http = requests.Session()
    for offset in range(0, len(missing), TIMESTAMP_BATCH_SIZE):
        batch = missing[offset : offset + TIMESTAMP_BATCH_SIZE]
        payload = [{"jsonrpc": "2.0", "id": index, "method": "eth_getBlockByNumber", "params": [hex(block), False]} for index, block in enumerate(batch)]
        for retry in range(8):
            try:
                stats["timestamp_rpc_batch_requests"] += 1
                response = http.post(OFFICIAL_RPC, json=payload, timeout=60, headers={"User-Agent": "robinhood-five-token-panel/0.1"})
                if response.status_code == 429 or response.status_code >= 500:
                    if response.status_code == 429:
                        stats["timestamp_rate_limit_events"] += 1
                    raise requests.RequestException(str(response.status_code))
                response.raise_for_status()
                result = response.json()
                if not isinstance(result, list) or any("error" in row or not row.get("result") for row in result):
                    raise RuntimeError("invalid batch block response")
                by_id = {row["id"]: row for row in result}
                resolved = {block: int(by_id[index]["result"]["timestamp"], 16) for index, block in enumerate(batch)}
                inserted, _ = insert_exact_timestamps(GLOBAL_TIMESTAMP_CACHE, resolved)
                stats["newly_inserted_global_cache_rows"] += inserted
                cache.update(resolved)
                stats["timestamp_block_lookups"] += len(batch)
                atomic_json(path, {str(block): timestamp for block, timestamp in cache.items()})
                break
            except (requests.RequestException, RuntimeError, ValueError) as error:
                stats["timestamp_retry_events"] += 1
                if isinstance(error, requests.Timeout):
                    stats["timestamp_timeout_events"] += 1
                if retry == 7:
                    raise
                time.sleep(min(2 ** (retry + 1), 30))
    return cache, stats


def multiplier_at(symbol: str, timestamp: int) -> float:
    if symbol == "COST" and timestamp >= int(datetime(2026, 8, 10, 15, 10, 24, tzinfo=UTC).timestamp()):
        return 1.000612040296259656
    if symbol == "UPS" and timestamp >= int(datetime(2026, 9, 4, 15, 10, 26, tzinfo=UTC).timestamp()):
        return 1.002208724969205741
    return 1.0


def decode_events(symbol: str, metadata: dict, events: list[dict], timestamps: dict[int, int]) -> tuple[list[dict], int]:
    unique = {}
    for event in events:
        unique.setdefault((event["transactionHash"].lower(), int(event["logIndex"], 16)), event)
    decoded = []
    for event in sorted(unique.values(), key=lambda row: (int(row["blockNumber"], 16), int(row["logIndex"], 16))):
        words = [event["data"][2 + index * 64 : 2 + (index + 1) * 64] for index in range(2)]
        amounts = [abs(signed_256(word)) for word in words]
        token_amount = amounts[metadata["token_index"]] / 1e18
        quote_amount = amounts[metadata["quote_index"]] / 1e6
        raw_price = quote_amount / token_amount if quote_amount > 0 and token_amount > 0 else None
        block = int(event["blockNumber"], 16)
        timestamp = timestamps[block]
        multiplier = multiplier_at(symbol, timestamp)
        underlying_price = raw_price / multiplier if raw_price else None
        reconstructable = bool(underlying_price and math.isfinite(underlying_price) and 0 < underlying_price < 1_000_000)
        decoded.append(
            {
                "block_number": block,
                "block_timestamp_utc": timestamp,
                "block_timestamp_et": datetime.fromtimestamp(timestamp, UTC).astimezone(NEW_YORK).isoformat(),
                "transaction_hash": event["transactionHash"],
                "log_index": int(event["logIndex"], 16),
                "event_sender": "0x" + event["topics"][1][-40:],
                "recipient": "0x" + event["topics"][2][-40:],
                "quote_amount_usdg": quote_amount,
                "token_amount": token_amount,
                "execution_price_usdg_per_token": raw_price,
                "historical_multiplier": multiplier,
                "underlying_equivalent_price_usdg": underlying_price,
                "reconstructable": reconstructable,
            }
        )
    return decoded, len(events) - len(unique)


def write_decoded(path: Path, rows: list[dict]) -> None:
    fields = [
        "block_number", "block_timestamp_utc", "block_timestamp_et", "transaction_hash", "log_index",
        "event_sender", "recipient", "quote_amount_usdg", "token_amount", "execution_price_usdg_per_token",
        "historical_multiplier", "underlying_equivalent_price_usdg", "reconstructable",
    ]
    atomic_csv(path, rows, fields)


def complete_session(symbol: str, item: dict) -> dict:
    started = time.perf_counter()
    open_date = item["market_open_date"]
    session_dir = SESSIONS / symbol / open_date
    session_dir.mkdir(parents=True, exist_ok=True)
    metadata = verify_pool_order(symbol)
    first_block = block_boundary(item["start_et"])
    last_block = block_boundary(item["end_et"]) - 1
    raw_started = time.perf_counter()
    events, requests_this_run = retrieve_chunks(symbol, item, first_block, last_block)
    raw_runtime = time.perf_counter() - raw_started
    blocks = [int(event["blockNumber"], 16) for event in events]
    timestamp_started = time.perf_counter()
    timestamps, timestamp_stats = batch_timestamps(blocks, session_dir / "block_timestamps.json")
    timestamp_runtime = time.perf_counter() - timestamp_started
    decode_started = time.perf_counter()
    decoded, duplicates = decode_events(symbol, metadata, events, timestamps)
    start_ts = int(item["start_et"].astimezone(UTC).timestamp())
    end_ts = int(item["end_et"].astimezone(UTC).timestamp())
    if any(not start_ts <= row["block_timestamp_utc"] < end_ts for row in decoded):
        raise RuntimeError(f"timestamp outside frozen session for {symbol} {open_date}")
    if len({(row["transaction_hash"].lower(), row["log_index"]) for row in decoded}) != len(decoded):
        raise RuntimeError("exact duplicate event keys remain")
    decode_runtime = time.perf_counter() - decode_started
    checkpoint_started = time.perf_counter()
    write_decoded(session_dir / "decoded_swaps.csv", decoded)
    valid = [row for row in decoded if row["reconstructable"]]
    stamps = sorted(row["block_timestamp_utc"] for row in decoded)
    gaps = [right - left for left, right in zip([start_ts, *stamps], [*stamps, end_ts])]
    state = json.loads((session_dir / "retrieval_state.json").read_text(encoding="utf-8"))
    multipliers = sorted({row["historical_multiplier"] for row in decoded}) or sorted({multiplier_at(symbol, start_ts), multiplier_at(symbol, end_ts - 1)})
    summary = {
        "token_symbol": symbol,
        "market_open_date": open_date,
        "session_start_et": item["start_et"].isoformat(),
        "session_end_et_exclusive": item["end_et"].isoformat(),
        "session_start_utc": item["start_et"].astimezone(UTC).isoformat(),
        "session_end_utc_exclusive": item["end_et"].astimezone(UTC).isoformat(),
        "exact_block_start": first_block,
        "exact_block_end": last_block,
        "completion_status": "complete",
        "raw_event_count": len(events),
        "decoded_event_count": len(decoded),
        "exact_duplicates_removed": duplicates,
        "reconstructable_price_count": len(valid),
        "reconstruction_percentage": 100 * len(valid) / len(decoded) if decoded else None,
        "multiplier_states": multipliers,
        "source_provider": OFFICIAL_RPC,
        "terminal_chunk_count": len(state["successful"]),
        "retrieval_requests_this_run": requests_this_run,
        "session_runtime_seconds": round(time.perf_counter() - started, 3),
        "largest_execution_gap_minutes": max(gaps) / 60,
        "warning": "COST multiplier path is measurement-ready; economic formula remains incompletely documented." if symbol == "COST" else "",
        "error": "",
        "runtime_diagnostics": {
            "raw_swap_log_retrieval_seconds": round(raw_runtime, 3),
            "block_timestamp_resolution_seconds": round(timestamp_runtime, 3),
            "decode_price_reconstruction_seconds": round(decode_runtime, 3),
            "raw_log_rpc_requests": requests_this_run,
            "raw_log_retry_events": 0 if requests_this_run == 0 else None,
            **timestamp_stats,
        },
    }
    summary["runtime_diagnostics"]["session_checkpoint_writing_seconds"] = round(time.perf_counter() - checkpoint_started, 3)
    atomic_json(session_dir / "summary.json", summary)
    return summary


def completed_summaries(schedule: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for symbol, items in schedule.items():
        for item in items:
            path = SESSIONS / symbol / item["market_open_date"] / "summary.json"
            if path.exists():
                summary = json.loads(path.read_text(encoding="utf-8"))
                if summary.get("completion_status") in {"complete", "complete_reused"}:
                    rows.append(summary)
    return rows


def bootstrap_nvda(schedule: dict[str, list[dict]]) -> None:
    source_quality = {row["market_open_date"]: row for row in csv.DictReader((NVDA_SOURCE / "nvda_session_quality.csv").open(encoding="utf-8-sig"))}
    for item in schedule["NVDA"]:
        open_date = item["market_open_date"]
        if open_date not in source_quality:
            continue
        session_dir = SESSIONS / "NVDA" / open_date
        summary_path = session_dir / "summary.json"
        if summary_path.exists():
            continue
        source = source_quality[open_date]
        source_dir = (NVDA_SOURCE / "sessions" / open_date).resolve()
        manifest = {
            "reuse_reason": "validated NVDA Phase 0 session; no redownload",
            "source_session_directory": str(source_dir),
            "source_decoded_swaps": str(source_dir / "decoded_swaps.csv"),
            "source_chunks_directory": str(source_dir / "chunks"),
            "source_retrieval_state": str(source_dir / "retrieval_state.json"),
            "source_chunk_attempts": str(source_dir / "chunk_attempts.csv"),
        }
        atomic_json(session_dir / "reuse_manifest.json", manifest)
        summary = {
            "token_symbol": "NVDA",
            "market_open_date": open_date,
            "session_start_et": source["session_start_et"],
            "session_end_et_exclusive": source["session_end_et_exclusive"],
            "session_start_utc": datetime.fromisoformat(source["session_start_et"]).astimezone(UTC).isoformat(),
            "session_end_utc_exclusive": datetime.fromisoformat(source["session_end_et_exclusive"]).astimezone(UTC).isoformat(),
            "exact_block_start": int(source["exact_block_start"]),
            "exact_block_end": int(source["exact_block_end"]),
            "completion_status": "complete_reused",
            "raw_event_count": int(source["raw_unique_swap_count"]),
            "decoded_event_count": int(source["decoded_swap_count"]),
            "exact_duplicates_removed": int(source["exact_duplicates_removed"]),
            "reconstructable_price_count": int(source["reconstructable_price_count"]),
            "reconstruction_percentage": float(source["reconstructable_price_percentage"]),
            "multiplier_states": [1.0],
            "source_provider": source["raw_log_provider"],
            "terminal_chunk_count": int(source["terminal_chunk_count"]),
            "retrieval_requests_this_run": 0,
            "session_runtime_seconds": 0,
            "largest_execution_gap_minutes": float(source["largest_execution_gap_minutes"]),
            "warning": "reused validated NVDA artifact",
            "error": "",
        }
        atomic_json(summary_path, summary)


def decoded_path(symbol: str, open_date: str) -> Path:
    local = SESSIONS / symbol / open_date / "decoded_swaps.csv"
    if local.exists():
        return local
    manifest = SESSIONS / symbol / open_date / "reuse_manifest.json"
    if manifest.exists():
        return Path(json.loads(manifest.read_text(encoding="utf-8"))["source_decoded_swaps"])
    raise FileNotFoundError(local)


def money(value: str) -> float:
    return float(value.replace("$", "").replace(",", ""))


def ensure_underlying(symbol: str, schedule: dict[str, list[dict]]) -> dict:
    path = ROOT / "underlying" / f"{symbol}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    config = TOKENS[symbol]
    first_previous = schedule[symbol][0]["start_et"].date().isoformat()
    url = f"https://api.nasdaq.com/api/quote/{symbol}/historical"
    params = {"assetclass": config["assetclass"], "fromdate": first_previous, "todate": CUTOFF.isoformat(), "limit": 100}
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": f"https://www.nasdaq.com/market-activity/{config['assetclass']}/{symbol.lower()}/historical",
    }
    for retry in range(6):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            payload = response.json()
            rows = payload["data"]["tradesTable"]["rows"]
            values = {
                datetime.strptime(row["date"], "%m/%d/%Y").date().isoformat(): {"open": money(row["open"]), "close": money(row["close"])}
                for row in rows
            }
            required = {item["market_open_date"] for item in schedule[symbol]} | {item["start_et"].date().isoformat() for item in schedule[symbol]}
            if not required.issubset(values):
                raise RuntimeError(f"Nasdaq coverage missing {sorted(required - set(values))}")
            result = {
                "token_symbol": symbol,
                "source_url": response.url,
                "source_page": headers["Referer"],
                "assetclass": config["assetclass"],
                "adjustment_convention": "raw Nasdaq Open and Close/Last; adjusted close not used",
                "rows": values,
            }
            atomic_json(path, result)
            return result
        except (requests.RequestException, RuntimeError, ValueError, KeyError, TypeError):
            if retry == 5:
                raise
            time.sleep(min(2 ** (retry + 1), 15))


def boundary_metrics(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    sample = frame.loc[frame["reconstructable"] & frame["timestamp"].ge(start) & frame["timestamp"].lt(end)]
    notional = float(sample["quote_amount_usdg"].sum())
    return {
        "vwap": float((sample["underlying_equivalent_price_usdg"] * sample["quote_amount_usdg"]).sum() / notional) if notional > 0 else math.nan,
        "swap_count": int(len(sample)),
        "notional": notional,
    }


def segment_metrics(frame: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    sample = frame.loc[frame["timestamp"].ge(start) & frame["timestamp"].lt(end)]
    valid = sample.loc[sample["reconstructable"]]
    minutes = (end - start).total_seconds() / 60
    return {
        "swap_count": int(len(sample)),
        "notional": float(valid["quote_amount_usdg"].sum()),
        "active_min_share": float(sample["timestamp"].dt.floor("min").nunique() / minutes),
        "median_trade_size": float(valid["quote_amount_usdg"].median()) if not valid.empty else math.nan,
    }


def log_return(end: float, start: float) -> float:
    return math.log(end / start) if np.isfinite(start) and np.isfinite(end) and start > 0 and end > 0 else math.nan


def prior_1600_last(symbol: str, item: dict, metadata: dict) -> float:
    path = SESSIONS / symbol / item["market_open_date"] / "last_trade_1600.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["last_price"]
    start = item["start_et"]
    first, last = block_boundary(start - timedelta(minutes=5)), block_boundary(start) - 1
    http = requests.Session()
    events = None
    for retry in range(8):
        events, attempt = attempt_logs(http, TOKENS[symbol]["pool"], first, last, retry)
        if events is not None:
            break
        time.sleep(min(2 ** (retry + 1), 30))
    if events is None:
        raise RuntimeError(f"could not retrieve 16:00 sensitivity window: {symbol} {item['market_open_date']}")
    timestamp_started = time.perf_counter()
    timestamps, timestamp_stats = batch_timestamps([int(event["blockNumber"], 16) for event in events], path.with_name("last_trade_1600_timestamps.json"))
    timestamp_runtime = time.perf_counter() - timestamp_started
    decoded, duplicates = decode_events(symbol, metadata, events, timestamps)
    valid = [row for row in decoded if row["reconstructable"] and row["block_timestamp_utc"] < int(start.astimezone(UTC).timestamp())]
    result = {
        "window_start_et": (start - timedelta(minutes=5)).isoformat(),
        "window_end_et_exclusive": start.isoformat(),
        "exact_block_start": first,
        "exact_block_end": last,
        "event_count": len(events),
        "exact_duplicates_removed": duplicates,
        "last_price": valid[-1]["underlying_equivalent_price_usdg"] if valid else None,
        "provider": OFFICIAL_RPC,
        "raw_log_rpc_requests": retry + 1,
        "raw_log_retry_events": retry,
        "timestamp_stats": timestamp_stats,
        "timestamp_resolution_seconds": round(timestamp_runtime, 3),
    }
    atomic_json(path, result)
    return result["last_price"]


def measure_session(symbol: str, item: dict, underlying: dict) -> dict:
    open_date = item["market_open_date"]
    cache_path = SESSIONS / symbol / open_date / "measurement_row.csv"
    if cache_path.exists():
        return pd.read_csv(cache_path).iloc[0].to_dict()
    existing_nvda = pd.read_csv(NVDA_MEASUREMENTS)
    if symbol == "NVDA" and open_date in set(existing_nvda["market_open_date"]):
        old = existing_nvda.loc[existing_nvda["market_open_date"].eq(open_date)].iloc[0].to_dict()
        old.update(
            {
                "token_symbol": "NVDA", "underlying_symbol": "NVDA",
                "underlying_previous_close": old.pop("nvda_previous_close"),
                "underlying_next_open": old.pop("nvda_next_open"),
                "underlying_gap_return": old.pop("nvda_gap_return"),
            }
        )
        old.pop("nvda_previous_close_date", None)
        temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
        pd.DataFrame([old]).to_csv(temporary, index=False)
        replace_with_retry(temporary, cache_path)
        return old
    frame = pd.read_csv(decoded_path(symbol, open_date))
    if frame.empty:
        frame = pd.DataFrame(columns=["block_timestamp_et", "block_number", "log_index", "reconstructable", "quote_amount_usdg", "underlying_equivalent_price_usdg"])
    frame["timestamp"] = pd.to_datetime(frame["block_timestamp_et"], utc=True).dt.tz_convert(NEW_YORK)
    frame["reconstructable"] = frame["reconstructable"].astype(str).str.lower().eq("true")
    frame = frame.sort_values(["timestamp", "block_number", "log_index"]).reset_index(drop=True)
    start, end = pd.Timestamp(item["start_et"]), pd.Timestamp(item["end_et"])
    b2000, b0400 = start.normalize() + pd.Timedelta(hours=20), end.normalize() + pd.Timedelta(hours=4)
    boundaries = {"1600": start, "2000": b2000, "0400": b0400, "0930": end}
    windows = {
        "1600": (start, start + pd.Timedelta(minutes=5)),
        "2000": (b2000 - pd.Timedelta(minutes=5), b2000),
        "0400": (b0400 - pd.Timedelta(minutes=5), b0400),
        "0930": (end - pd.Timedelta(minutes=5), end),
    }
    metrics = {name: boundary_metrics(frame, *window) for name, window in windows.items()}
    vwaps = {name: value["vwap"] for name, value in metrics.items()}
    metadata = verify_pool_order(symbol)
    prior = prior_1600_last(symbol, item, metadata)
    lasts = {"1600": float(prior) if prior is not None else math.nan}
    for name in ("2000", "0400", "0930"):
        sample = frame.loc[frame["reconstructable"] & frame["timestamp"].lt(boundaries[name])]
        lasts[name] = float(sample.iloc[-1]["underlying_equivalent_price_usdg"]) if not sample.empty else math.nan
    segment_bounds = {"post": (start, b2000), "deep": (b2000, b0400), "premarket": (b0400, end), "full": (start, end)}
    activity = {name: segment_metrics(frame, *bounds) for name, bounds in segment_bounds.items()}
    missing = [name for name, value in vwaps.items() if not np.isfinite(value)]
    thin = [name for name, value in metrics.items() if value["swap_count"] < THIN_MIN_SWAPS or value["notional"] < THIN_MIN_NOTIONAL]
    row = {
        "session_id": f"{symbol}_{open_date}",
        "token_symbol": symbol,
        "underlying_symbol": symbol,
        "market_open_date": open_date,
        "session_start_et": start.isoformat(),
        "session_end_et_exclusive": end.isoformat(),
        **{f"token_vwap_{name}": value for name, value in vwaps.items()},
        **{f"boundary_swap_count_{name}": value["swap_count"] for name, value in metrics.items()},
        **{f"boundary_notional_usdg_{name}": value["notional"] for name, value in metrics.items()},
        **{f"token_last_{name}": value for name, value in lasts.items()},
        "token_ret_full": log_return(vwaps["0930"], vwaps["1600"]),
        "token_ret_post": log_return(vwaps["2000"], vwaps["1600"]),
        "token_ret_deep": log_return(vwaps["0400"], vwaps["2000"]),
        "token_ret_premarket": log_return(vwaps["0930"], vwaps["0400"]),
        "token_ret_full_last_trade": log_return(lasts["0930"], lasts["1600"]),
        "token_ret_post_last_trade": log_return(lasts["2000"], lasts["1600"]),
        "token_ret_deep_last_trade": log_return(lasts["0400"], lasts["2000"]),
        "token_ret_premarket_last_trade": log_return(lasts["0930"], lasts["0400"]),
    }
    row["return_decomposition_error"] = row["token_ret_full"] - sum(
        [row["token_ret_post"], row["token_ret_deep"], row["token_ret_premarket"]]
    ) if not missing else math.nan
    row["return_decomposition_valid"] = bool(np.isfinite(row["return_decomposition_error"]) and abs(row["return_decomposition_error"]) <= 1e-12)
    last_values = [row["token_ret_full_last_trade"], row["token_ret_post_last_trade"], row["token_ret_deep_last_trade"], row["token_ret_premarket_last_trade"]]
    row["return_decomposition_error_last_trade"] = last_values[0] - sum(last_values[1:]) if all(np.isfinite(value) for value in last_values) else math.nan
    row["return_decomposition_valid_last_trade"] = bool(np.isfinite(row["return_decomposition_error_last_trade"]) and abs(row["return_decomposition_error_last_trade"]) <= 1e-12)
    for segment in SEGMENTS:
        for metric, value in activity[segment].items():
            row[f"{metric}_{segment}"] = value
    previous_date = item["start_et"].date().isoformat()
    source = underlying["rows"]
    row.update(
        {
            "underlying_previous_close": source[previous_date]["close"],
            "underlying_next_open": source[open_date]["open"],
            "underlying_gap_return": log_return(source[open_date]["open"], source[previous_date]["close"]),
            "price_reconstruction_rate": float(frame["reconstructable"].mean()) if len(frame) else math.nan,
            "largest_execution_gap_minutes": json.loads((SESSIONS / symbol / open_date / "summary.json").read_text(encoding="utf-8"))["largest_execution_gap_minutes"],
            "thin_boundary_flag": bool(thin),
            "thin_boundary_detail": ",".join(thin),
            "missing_boundary_flag": bool(missing),
            "missing_boundary_detail": ",".join(missing),
            "multiplier_warning": "Exact timestamp-effective path applied; economic formula remains incompletely documented." if symbol == "COST" else "",
            "session_warning": "; ".join(filter(None, ["missing primary VWAP: " + ",".join(missing) if missing else "", "thin primary boundary (<5 swaps or <500 USDG): " + ",".join(thin) if thin else ""])),
        }
    )
    temporary = cache_path.with_suffix(cache_path.suffix + ".tmp")
    pd.DataFrame([row]).to_csv(temporary, index=False)
    replace_with_retry(temporary, cache_path)
    return row


def rebuild_outputs(schedule: dict[str, list[dict]], fetch_underlying: bool = True) -> None:
    # Replacement-screen sessions remain separate from the frozen five-token panel.
    panel_schedule = {symbol: schedule[symbol] for symbol in BASE_PANEL_TOKEN_ORDER}
    summaries = completed_summaries(panel_schedule)
    atomic_csv(SESSION_LEDGER, summaries)
    completed = {(row["token_symbol"], row["market_open_date"]) for row in summaries}
    panel_rows = []
    underlying_cache = {}
    if fetch_underlying:
        for symbol in BASE_PANEL_TOKEN_ORDER:
            if any(key[0] == symbol for key in completed):
                underlying_cache[symbol] = ensure_underlying(symbol, schedule)
        for symbol in BASE_PANEL_TOKEN_ORDER:
            for item in panel_schedule[symbol]:
                if research_eligible(symbol, item) and (symbol, item["market_open_date"]) in completed:
                    panel_rows.append(measure_session(symbol, item, underlying_cache[symbol]))
    if panel_rows:
        panel = pd.DataFrame(panel_rows).sort_values(["token_symbol", "market_open_date"])
        if panel.duplicated(["token_symbol", "market_open_date"]).any():
            raise RuntimeError("duplicate panel primary key")
        expected_keys = {(symbol, item["market_open_date"]) for symbol, items in panel_schedule.items() for item in items}
        if not set(zip(panel["token_symbol"], panel["market_open_date"])).issubset(expected_keys):
            raise RuntimeError("panel row is not a valid scheduled market open")
        if not (
            panel[["swap_count_post", "swap_count_deep", "swap_count_premarket"]].sum(axis=1)
            == panel["swap_count_full"]
        ).all():
            raise RuntimeError("segment swap counts do not reconcile")
        primary_complete = panel[[f"token_vwap_{name}" for name in BOUNDARIES]].notna().all(axis=1)
        if not panel.loc[primary_complete, "return_decomposition_valid"].astype(bool).all():
            raise RuntimeError("primary return decomposition failure")
        if not panel.loc[panel["return_decomposition_error_last_trade"].notna(), "return_decomposition_valid_last_trade"].astype(bool).all():
            raise RuntimeError("last-trade return decomposition failure")
        if not panel["underlying_previous_close"].notna().all() or not panel["underlying_next_open"].notna().all():
            raise RuntimeError("underlying Open/Close alignment failure")
        missing_consistent = panel[[f"token_vwap_{name}" for name in BOUNDARIES]].isna().any(axis=1) == panel["missing_boundary_flag"].astype(bool)
        if not missing_consistent.all():
            raise RuntimeError("missing boundary flag inconsistency")
        temporary = PANEL_CSV.with_suffix(PANEL_CSV.suffix + ".tmp")
        panel.to_csv(temporary, index=False)
        replace_with_retry(temporary, PANEL_CSV)
    coverage = []
    for symbol in BASE_PANEL_TOKEN_ORDER:
        eligible = [item for item in panel_schedule[symbol] if research_eligible(symbol, item)]
        done = [item for item in eligible if (symbol, item["market_open_date"]) in completed]
        coverage.append(
            {
                "token_symbol": symbol,
                "pool_start_utc": TOKENS[symbol]["pool_start"],
                "first_eligible_session": eligible[0]["market_open_date"],
                "last_eligible_session": eligible[-1]["market_open_date"],
                "total_eligible_sessions": len(eligible),
                "successfully_measured_sessions": len(done),
                "retained_but_research_ineligible_sessions": len(panel_schedule[symbol]) - len(eligible),
                "missing_unusable_sessions": len(eligible) - len(done),
                "missingness_reason": "retrieval not yet completed" if len(done) < len(eligible) else "",
            }
        )
    atomic_csv(COVERAGE_CSV, coverage)
    eligible_total = sum(research_eligible(symbol, item) for symbol, items in panel_schedule.items() for item in items)
    completed_eligible = sum(
        research_eligible(symbol, item) and (symbol, item["market_open_date"]) in completed
        for symbol, items in panel_schedule.items() for item in items
    )
    missing_prices = int(panel[[f"token_vwap_{name}" for name in BOUNDARIES]].isna().sum().sum()) if panel_rows else None
    thin_count = int(panel["thin_boundary_flag"].astype(bool).sum()) if panel_rows else None
    incomplete_ranges = sum(
        1
        for symbol in BASE_PANEL_TOKEN_ORDER
        for path in (SESSIONS / symbol).glob("*/retrieval_state.json")
        if json.loads(path.read_text(encoding="utf-8")).get("status") != "raw_complete"
    )
    all_complete = completed_eligible == eligible_total and incomplete_ranges == 0
    warnings = bool((missing_prices or 0) + (thin_count or 0)) or any(row["token_symbol"] == "COST" for row in summaries)
    classification = "DATASET_READY_WITH_WARNINGS" if all_complete and warnings else "DATASET_READY" if all_complete else "DATASET_NOT_READY"
    qa = {
        "classification": classification,
        "common_cutoff_date": CUTOFF.isoformat(),
        "eligible_sessions_by_token": {row["token_symbol"]: row["total_eligible_sessions"] for row in coverage},
        "measured_sessions_by_token": {row["token_symbol"]: row["successfully_measured_sessions"] for row in coverage},
        "final_or_current_token_session_sample_size": len(panel_rows),
        "eligible_token_session_total": eligible_total,
        "collected_token_session_total_including_retained_ineligible_history": len(completed),
        "research_roles": {
            "core_primary_candidates": ["NVDA", "GME", "COST", "USO"],
            "secondary_sensitivity": ["TSLA"],
        },
        "unbalanced_range": [min(len(items) for items in panel_schedule.values()), max(len(items) for items in panel_schedule.values())],
        "missing_primary_boundary_prices": missing_prices,
        "thin_boundary_warning_sessions": thin_count,
        "incomplete_retrieval_ranges": incomplete_ranges,
        "multiplier_issue": "COST exact timing/value path resolved and applied; economic formula remains incompletely documented.",
        "next_stage_suitability": all_complete,
        "interpretation_limit": "Data construction only; no prediction, price-discovery, causality, or profitability claim.",
    }
    atomic_json(QA_JSON, qa)
    less_liquid = "Pending complete panel measurement." if not all_complete else "See coverage and boundary/activity columns; thin flags are retained rather than excluded."
    markdown = f"""# Five-token panel data-quality status

**{classification}**

- A. Eligible sessions: {qa['eligible_sessions_by_token']}.
- B. Successfully measured: {qa['measured_sessions_by_token']}.
- C. Current/final sample: {len(panel_rows)} of {eligible_total} eligible token-sessions.
- D. Unbalanced panel: token histories range from {qa['unbalanced_range'][0]} to {qa['unbalanced_range'][1]} sessions; no padding or equal-length truncation.
- E. Missing primary boundary prices: {missing_prices if missing_prices is not None else 'not yet computed'}.
- F. Thin-boundary warning sessions: {thin_count if thin_count is not None else 'not yet computed'}.
- G. Liquidity/measurability versus NVDA: {less_liquid}
- H. Multiplier/corporate action: COST's exact transition timestamp and values are applied; its economic formula remains incompletely documented. No other in-sample multiplier transition is recorded.
- I. Incomplete retrieval ranges: {incomplete_ranges}. Unstarted sessions are reported separately in the coverage CSV.
- J. Technically suitable for next research-design stage: {'yes' if all_complete else 'no; collection remains incomplete'}.

This status concerns data construction only. It does not establish prediction, price discovery, attention effects, causality, or profitability.
"""
    atomic_text(QA_MD, markdown)


def integrity_inventory_check() -> None:
    rows = {row["token_symbol"]: row for row in csv.DictReader(INVENTORY.open(encoding="utf-8-sig"))}
    for symbol, config in TOKENS.items():
        row = rows[symbol]
        if row["canonical_contract"].lower() != config["contract"].lower() or row["pool_or_market_id"].lower() != config["pool"].lower():
            raise RuntimeError(f"inventory mapping changed for {symbol}")


def self_check(schedule: dict[str, list[dict]]) -> None:
    assert {symbol: len(items) for symbol, items in schedule.items()} == {"NVDA": 33, "GME": 30, "TSLA": 41, "COST": 31, "USO": 35, "AMZN": 33, "UPS": 46}
    assert multiplier_at("COST", int(datetime(2026, 8, 10, 15, 10, 23, tzinfo=UTC).timestamp())) == 1.0
    assert multiplier_at("COST", int(datetime(2026, 8, 10, 15, 10, 24, tzinfo=UTC).timestamp())) == 1.000612040296259656
    assert multiplier_at("UPS", int(datetime(2026, 9, 4, 15, 10, 25, tzinfo=UTC).timestamp())) == 1.0
    assert multiplier_at("UPS", int(datetime(2026, 9, 4, 15, 10, 26, tzinfo=UTC).timestamp())) == 1.002208724969205741
    for symbol, items in schedule.items():
        assert all(item["start_et"].astimezone(UTC) >= datetime.fromisoformat(TOKENS[symbol]["pool_start"].replace("Z", "+00:00")) for item in items)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-sessions-this-run", type=int, default=3)
    parser.add_argument("--token", choices=TOKEN_ORDER)
    parser.add_argument("--max-runtime-minutes", type=float)
    parser.add_argument("--market-open-dates", help="Comma-separated frozen session dates; requires --token")
    parser.add_argument("--plan-only", action="store_true")
    parser.add_argument("--finalize-only", action="store_true")
    args = parser.parse_args()
    if args.max_sessions_this_run < 1:
        parser.error("--max-sessions-this-run must be positive")
    if args.max_runtime_minutes is not None and args.max_runtime_minutes <= 0:
        parser.error("--max-runtime-minutes must be positive")
    requested_dates = args.market_open_dates.split(",") if args.market_open_dates else None
    if requested_dates and not args.token:
        parser.error("--market-open-dates requires --token")
    if requested_dates and len(requested_dates) != len(set(requested_dates)):
        parser.error("--market-open-dates contains duplicates")
    schedule = all_sessions()
    self_check(schedule)
    integrity_inventory_check()
    if args.plan_only:
        print(json.dumps({symbol: [items[0]["market_open_date"], items[-1]["market_open_date"], len(items)] for symbol, items in schedule.items()}, indent=2))
        return
    ROOT.mkdir(parents=True, exist_ok=True)
    bootstrap_nvda(schedule)
    if args.finalize_only:
        rebuild_outputs(schedule)
        return
    completed = {(row["token_symbol"], row["market_open_date"]) for row in completed_summaries(schedule)}
    symbols = (args.token,) if args.token else BASE_PANEL_TOKEN_ORDER
    if requested_dates:
        valid_dates = {item["market_open_date"] for item in schedule[args.token]}
        invalid_dates = [open_date for open_date in requested_dates if open_date not in valid_dates]
        if invalid_dates:
            parser.error(f"dates are not eligible for {args.token}: {invalid_dates}")
    pending = [(symbol, item) for symbol in symbols for item in schedule[symbol] if (symbol, item["market_open_date"]) not in completed]
    selected = select_pending_sessions(pending, requested_dates, args.max_sessions_this_run)
    invocation_started = time.perf_counter()
    processed = 0
    for symbol, item in selected:
        session_wall_started = time.perf_counter()
        summary = complete_session(symbol, item)
        processed += 1
        measurement_started = time.perf_counter()
        measurement = measure_session(symbol, item, ensure_underlying(symbol, schedule))
        measurement_runtime = time.perf_counter() - measurement_started
        output_started = time.perf_counter()
        rebuild_outputs(schedule)
        output_runtime = time.perf_counter() - output_started
        total_session_runtime = time.perf_counter() - session_wall_started
        summary_path = SESSIONS / symbol / item["market_open_date"] / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        boundary_path = summary_path.with_name("last_trade_1600.json")
        boundary = json.loads(boundary_path.read_text(encoding="utf-8")) if boundary_path.exists() else {}
        boundary_timestamp_stats = boundary.get("timestamp_stats", {})
        diagnostics = summary.setdefault("runtime_diagnostics", {})
        checkpoint_hits = diagnostics.get("timestamps_reused_from_session_checkpoint", 0) + boundary_timestamp_stats.get("timestamps_reused_from_session_checkpoint", 0)
        global_hits = diagnostics.get("timestamps_reused_from_global_cache", 0) + boundary_timestamp_stats.get("timestamps_reused_from_global_cache", 0)
        rpc_misses = diagnostics.get("timestamp_rpc_misses", 0) + boundary_timestamp_stats.get("timestamp_rpc_misses", 0)
        diagnostics.update(
            {
                "session_measurement_vwap_seconds": round(measurement_runtime, 3),
                "aggregate_checkpoint_output_writing_seconds": round(output_runtime, 3),
                "total_session_runtime_seconds": round(total_session_runtime, 3),
                "measurement_boundary_raw_log_rpc_requests": boundary.get("raw_log_rpc_requests", 0),
                "measurement_boundary_raw_log_retry_events": boundary.get("raw_log_retry_events", 0),
                "measurement_boundary_timestamp_block_lookups": boundary_timestamp_stats.get("timestamp_block_lookups", 0),
                "measurement_boundary_timestamp_rpc_batch_requests": boundary_timestamp_stats.get("timestamp_rpc_batch_requests", 0),
                "measurement_boundary_timestamp_retry_events": boundary_timestamp_stats.get("timestamp_retry_events", 0),
                "total_timestamp_checkpoint_hits": checkpoint_hits,
                "total_global_timestamp_cache_hits": global_hits,
                "total_timestamp_rpc_misses": rpc_misses,
                "global_cache_hit_rate_among_non_checkpoint_timestamps": global_hits / (global_hits + rpc_misses) if global_hits or rpc_misses else None,
                "total_newly_inserted_global_cache_rows": diagnostics.get("newly_inserted_global_cache_rows", 0) + boundary_timestamp_stats.get("newly_inserted_global_cache_rows", 0),
                "total_timestamp_rpc_batch_requests": diagnostics.get("timestamp_rpc_batch_requests", 0) + boundary_timestamp_stats.get("timestamp_rpc_batch_requests", 0),
                "total_timestamp_retry_events": diagnostics.get("timestamp_retry_events", 0) + boundary_timestamp_stats.get("timestamp_retry_events", 0),
                "total_timestamp_rate_limit_events": diagnostics.get("timestamp_rate_limit_events", 0) + boundary_timestamp_stats.get("timestamp_rate_limit_events", 0),
                "total_timestamp_timeout_events": diagnostics.get("timestamp_timeout_events", 0) + boundary_timestamp_stats.get("timestamp_timeout_events", 0),
                "total_timestamp_resolution_seconds": round(diagnostics.get("block_timestamp_resolution_seconds", 0) + boundary.get("timestamp_resolution_seconds", 0), 3),
            }
        )
        summary["session_runtime_seconds"] = round(total_session_runtime, 3)
        atomic_json(summary_path, summary)
        atomic_csv(SESSION_LEDGER, completed_summaries({symbol: schedule[symbol] for symbol in BASE_PANEL_TOKEN_ORDER}))
        completed_now = completed_summaries(schedule)
        token_done = sum(row["token_symbol"] == symbol for row in completed_now)
        remaining = sum(len(items) for items in schedule.values()) - len(completed_now)
        elapsed = time.perf_counter() - invocation_started
        print(f"Completed {symbol} {item['market_open_date']}", flush=True)
        print(f"{symbol} completed sessions: {token_done}", flush=True)
        print(f"Total completed token-sessions: {len(completed_now)}", flush=True)
        print(f"Session runtime: {summary['session_runtime_seconds']:.1f}s", flush=True)
        print(f"Runtime diagnostics: {json.dumps(diagnostics, sort_keys=True)}", flush=True)
        print(
            "Session QA: "
            + json.dumps(
                {
                    "raw_swaps": summary["raw_event_count"],
                    "reconstruction_rate": summary["reconstruction_percentage"],
                    "exact_duplicates": summary["exact_duplicates_removed"],
                    "primary_vwap_available": {name: pd.notna(measurement.get(f"token_vwap_{name}")) for name in BOUNDARIES},
                    "thin_boundary_warning": bool(measurement.get("thin_boundary_flag")),
                    "incomplete_raw_ranges": 0,
                },
                sort_keys=True,
            ),
            flush=True,
        )
        print(f"Cumulative invocation runtime: {elapsed:.1f}s", flush=True)
        print(f"Remaining eligible sessions: {remaining}", flush=True)
        if args.max_runtime_minutes is not None and elapsed >= args.max_runtime_minutes * 60:
            print("Runtime limit reached at a completed-session checkpoint.", flush=True)
            break
    if not processed:
        rebuild_outputs(schedule)
        print("No incomplete sessions selected; outputs rebuilt from checkpoints.", flush=True)


if __name__ == "__main__":
    main()
