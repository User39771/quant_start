"""One-session NVDA/USDG raw-swap retrieval forensic."""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import requests

from audit_robinhood_chain_phase0 import (
    ASSETS_URL,
    CORPORATE_ACTIONS_URL,
    USDG,
    V3_SWAP_TOPIC,
    signed_256,
    url_json,
)


OFFICIAL_RPC = "https://rpc.mainnet.chain.robinhood.com"
FALLBACK_RPC = "https://rpc.ordofi.network"
NVDA_POOL = "0xd4eb21209c4d6093f80b5b84f5c45cc093ea14a3"
SESSION_START_UTC = datetime(2026, 8, 10, 20, 0, tzinfo=timezone.utc)
SESSION_END_UTC = datetime(2026, 8, 11, 13, 30, tzinfo=timezone.utc)
INITIAL_CHUNK_BLOCKS = 5_000
MINIMUM_CHUNK_BLOCKS = 250
OUTPUT_DIR = Path("reports/robinhood_chain_phase0/nvda_2026-08-11_forensic")
CHUNK_LOG_PATH = OUTPUT_DIR / "chunk_attempts.csv"
RAW_EVENTS_PATH = OUTPUT_DIR / "raw_swaps.csv"
SUMMARY_PATH = OUTPUT_DIR / "summary.json"
BLOCKSCOUT_LOG_PATH = OUTPUT_DIR / "blockscout_attempts.csv"


def rpc(session: requests.Session, url: str, method: str, params: list, timeout: int = 40):
    response = session.post(
        url,
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
        timeout=timeout,
        headers={"User-Agent": "nvda-one-session-forensic/0.1"},
    )
    response.raise_for_status()
    payload = response.json()
    if "error" in payload:
        raise RuntimeError(payload["error"])
    return payload["result"]


def block_timestamp(session: requests.Session, url: str, block: int) -> int:
    return int(rpc(session, url, "eth_getBlockByNumber", [hex(block), False])["timestamp"], 16)


def first_block_at_or_after(session: requests.Session, url: str, target: int) -> int:
    latest = int(rpc(session, url, "eth_blockNumber", []), 16)
    latest_timestamp = block_timestamp(session, url, latest)
    estimate = max(0, latest + round((target - latest_timestamp) * 10))
    low, high = max(0, estimate - 20_000), estimate + 20_000
    while block_timestamp(session, url, low) >= target:
        low = max(0, low - 20_000)
    while block_timestamp(session, url, high) < target:
        high += 20_000
    while low + 1 < high:
        middle = (low + high) // 2
        if block_timestamp(session, url, middle) < target:
            low = middle
        else:
            high = middle
    return high


def query(first: int, last: int) -> dict:
    return {
        "address": NVDA_POOL,
        "topics": [V3_SWAP_TOPIC],
        "fromBlock": hex(first),
        "toBlock": hex(last),
    }


def retrieve_provider(
    provider_name: str,
    provider_url: str,
    ranges: list[tuple[int, int]],
    adaptive: bool,
) -> tuple[list[dict], list[dict], list[tuple[int, int]], bool]:
    session = requests.Session()
    pending = deque(ranges)
    events = []
    attempts = []
    terminal_ranges = []
    complete = True
    request_number = 0
    while pending:
        first, last = pending.popleft()
        retries = 0
        while True:
            request_number += 1
            started = time.perf_counter()
            http_status = None
            rpc_status = "error"
            condition = None
            returned = 0
            try:
                response = session.post(
                    provider_url,
                    json={"jsonrpc": "2.0", "id": 1, "method": "eth_getLogs", "params": [query(first, last)]},
                    timeout=40,
                    headers={"User-Agent": "nvda-one-session-forensic/0.1"},
                )
                http_status = response.status_code
                if response.status_code == 429:
                    condition = "rate_limit"
                    raise requests.HTTPError("429", response=response)
                response.raise_for_status()
                payload = response.json()
                if "error" in payload:
                    message = str(payload["error"]).lower()
                    condition = "cap" if "limit" in message or "exceed" in message else "rpc_timeout" if "timeout" in message or "busy" in message else "rpc_error"
                    raise RuntimeError(payload["error"])
                batch = payload["result"]
                returned = len(batch)
                events.extend(batch)
                rpc_status = "success"
                terminal_ranges.append((first, last))
            except requests.Timeout:
                condition = "timeout"
            except requests.HTTPError as error:
                http_status = error.response.status_code if error.response is not None else http_status
                condition = condition or "http_error"
            except (requests.RequestException, RuntimeError, ValueError):
                condition = condition or "rpc_error"
            elapsed = time.perf_counter() - started
            attempts.append(
                {
                    "request_number": request_number,
                    "provider": provider_name,
                    "provider_url": provider_url,
                    "block_start": first,
                    "block_end": last,
                    "block_count": last - first + 1,
                    "http_status": http_status,
                    "rpc_status": rpc_status,
                    "retry_count": retries,
                    "response_event_count": returned,
                    "condition": condition,
                    "elapsed_seconds": round(elapsed, 3),
                }
            )
            if rpc_status == "success":
                break
            if condition == "rate_limit" and retries < 4:
                retries += 1
                time.sleep(2**retries)
                continue
            width = last - first + 1
            if adaptive and width > MINIMUM_CHUNK_BLOCKS:
                middle = (first + last) // 2
                pending.appendleft((middle + 1, last))
                pending.appendleft((first, middle))
            else:
                complete = False
                terminal_ranges.append((first, last))
            break
        if len(terminal_ranges) % 25 == 0 and terminal_ranges:
            print(f"{provider_name}: terminal chunks={len(terminal_ranges)} events={len(events)}", flush=True)
    return events, attempts, sorted(terminal_ranges), complete


def ranges_cover_exactly(ranges: list[tuple[int, int]], first: int, last: int) -> bool:
    if not ranges or ranges[0][0] != first or ranges[-1][1] != last:
        return False
    return all(left[1] + 1 == right[0] for left, right in zip(ranges, ranges[1:]))


def deduplicate(events: list[dict]) -> tuple[list[dict], int]:
    unique = {}
    for event in events:
        key = (event["transactionHash"].lower(), int(event["logIndex"], 16))
        unique.setdefault(key, event)
    ordered = sorted(unique.values(), key=lambda event: (int(event["blockNumber"], 16), int(event["logIndex"], 16)))
    return ordered, len(events) - len(ordered)


def decode(event: dict, multiplier: float) -> dict:
    amount0 = abs(signed_256(event["data"][2:66])) / 1e6  # USDG is token0.
    amount1 = abs(signed_256(event["data"][66:130])) / 1e18  # NVDA is token1.
    price = amount0 / amount1 if amount0 > 0 and amount1 > 0 else None
    return {
        "block_number": int(event["blockNumber"], 16),
        "transaction_hash": event["transactionHash"],
        "log_index": int(event["logIndex"], 16),
        "event_sender": "0x" + event["topics"][1][-40:],
        "recipient": "0x" + event["topics"][2][-40:],
        "quote_amount_usdg": amount0,
        "token_amount_nvda": amount1,
        "execution_price_usdg_per_token": price,
        "underlying_equivalent_price_usdg": price / multiplier if price else None,
        "reconstructable": bool(price and 0 < price < 1_000_000),
    }


def main() -> None:
    assets = url_json(ASSETS_URL)["assets"]
    nvda = next(asset for asset in assets if asset["tokenSymbol"] == "NVDA")
    canonical_contract = next(deployment["contractAddress"] for deployment in nvda["deployments"] if deployment["chainId"] == 4663)
    assert canonical_contract.lower() == "0xd0601ce157db5bdc3162bbac2a2c8af5320d9eec"
    actions = [
        action
        for action in url_json(CORPORATE_ACTIONS_URL).get("corpActions", [])
        if action.get("tokenSymbol") == "NVDA" and action.get("processDate")
        and (action["processDate"]["year"], action["processDate"]["month"], action["processDate"]["day"]) <= (2026, 8, 11)
    ]
    assert not actions
    multiplier = 1.0

    boundary_session = requests.Session()
    first_block = first_block_at_or_after(boundary_session, OFFICIAL_RPC, int(SESSION_START_UTC.timestamp()))
    first_excluded_block = first_block_at_or_after(boundary_session, OFFICIAL_RPC, int(SESSION_END_UTC.timestamp()))
    last_block = first_excluded_block - 1
    assert block_timestamp(boundary_session, OFFICIAL_RPC, first_block) >= int(SESSION_START_UTC.timestamp())
    assert block_timestamp(boundary_session, OFFICIAL_RPC, last_block) < int(SESSION_END_UTC.timestamp())
    assert block_timestamp(boundary_session, OFFICIAL_RPC, first_excluded_block) >= int(SESSION_END_UTC.timestamp())
    initial_ranges = [
        (start, min(start + INITIAL_CHUNK_BLOCKS - 1, last_block))
        for start in range(first_block, last_block + 1, INITIAL_CHUNK_BLOCKS)
    ]
    print(f"Exact range {first_block}-{last_block}; initial chunks={len(initial_ranges)}", flush=True)

    official_events, official_attempts, final_ranges, official_complete = retrieve_provider(
        "official_robinhood", OFFICIAL_RPC, initial_ranges, adaptive=True
    )
    assert ranges_cover_exactly(final_ranges, first_block, last_block)
    fallback_events, fallback_attempts, fallback_ranges, fallback_complete = retrieve_provider(
        "fallback_ordofi", FALLBACK_RPC, final_ranges, adaptive=False
    )
    assert fallback_ranges == final_ranges

    official_unique, official_duplicates = deduplicate(official_events)
    fallback_unique, fallback_duplicates = deduplicate(fallback_events)
    official_keys = {(event["transactionHash"].lower(), int(event["logIndex"], 16)) for event in official_unique}
    fallback_keys = {(event["transactionHash"].lower(), int(event["logIndex"], 16)) for event in fallback_unique}
    recovered = official_unique if official_complete else fallback_unique
    decoded = [decode(event, multiplier) for event in recovered]
    reconstructable = sum(row["reconstructable"] for row in decoded)
    providers_agree = official_complete and fallback_complete and official_keys == fallback_keys
    official_counts_by_range = {
        (row["block_start"], row["block_end"]): row["response_event_count"]
        for row in official_attempts
        if row["rpc_status"] == "success"
    }
    fallback_successful_ranges_match = all(
        official_counts_by_range[(row["block_start"], row["block_end"])] == row["response_event_count"]
        for row in fallback_attempts
        if row["rpc_status"] == "success"
    )
    demonstrably_complete = official_complete and ranges_cover_exactly(final_ranges, first_block, last_block)
    if demonstrably_complete:
        classification = "RETRIEVAL_IMPLEMENTATION_ISSUE"
    elif official_events or fallback_events:
        classification = "MIXED"
    else:
        classification = "PUBLIC_ACCESS_LIMITATION"

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    attempts = official_attempts + fallback_attempts
    with CHUNK_LOG_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(attempts[0]))
        writer.writeheader()
        writer.writerows(attempts)
    with RAW_EVENTS_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(decoded[0]) if decoded else ["block_number"])
        writer.writeheader()
        writer.writerows(decoded)
    summary = {
        "session_market_open": "2026-08-11T09:30:00-04:00",
        "session_start": "2026-08-10T16:00:00-04:00",
        "session_end_exclusive": "2026-08-11T09:30:00-04:00",
        "canonical_nvda_contract": canonical_contract,
        "pool": NVDA_POOL,
        "venue": "Uniswap V3",
        "quote": "USDG",
        "quote_contract": USDG,
        "exact_block_range_inclusive": [first_block, last_block],
        "minimum_chunk_blocks": MINIMUM_CHUNK_BLOCKS,
        "chunk_requests_attempted": len(attempts),
        "official_successful_requests": sum(row["rpc_status"] == "success" for row in official_attempts),
        "official_failed_requests": sum(row["rpc_status"] != "success" for row in official_attempts),
        "fallback_successful_requests": sum(row["rpc_status"] == "success" for row in fallback_attempts),
        "fallback_failed_requests": sum(row["rpc_status"] != "success" for row in fallback_attempts),
        "official_raw_event_count": len(official_unique),
        "fallback_raw_event_count": len(fallback_unique),
        "official_exact_duplicates_removed": official_duplicates,
        "fallback_exact_duplicates_removed": fallback_duplicates,
        "provider_event_key_symmetric_difference": len(official_keys ^ fallback_keys),
        "blockscout_count": None,
        "blockscout_status": "250-block probe returned 3 events; full-session reconciliation not completed after larger chunks timed out",
        "blockscout_probe": {"block_range": [33069045, 33069294], "event_count": 3},
        "hourly_indexed_evidence": {"full_hours_with_volume": 17, "full_hour_volume_usd": 730644.26},
        "historical_multiplier": multiplier,
        "multiplier_basis": "no NVDA corporate action effective by session date",
        "reconstructable_event_count": reconstructable,
        "reconstructable_event_percentage": round(100 * reconstructable / len(decoded), 6) if decoded else None,
        "official_complete": official_complete,
        "fallback_complete": fallback_complete,
        "providers_agree_exactly": providers_agree,
        "fallback_successful_ranges_match_official": fallback_successful_ranges_match,
        "demonstrably_complete": demonstrably_complete,
        "classification": classification,
    }
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


def reconcile_blockscout() -> None:
    chunk_rows = list(csv.DictReader(CHUNK_LOG_PATH.open(encoding="utf-8-sig")))
    ranges = sorted(
        {
            (int(row["block_start"]), int(row["block_end"]))
            for row in chunk_rows
            if row["provider"] == "official_robinhood" and row["rpc_status"] == "success"
        }
    )
    summary = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
    expected_first, expected_last = summary["exact_block_range_inclusive"]
    assert ranges_cover_exactly(ranges, expected_first, expected_last)
    attempts = []
    events = []
    complete = True
    session = requests.Session()
    for request_number, (first, last) in enumerate(ranges, start=1):
        started = time.perf_counter()
        status = None
        condition = None
        result = []
        retries = 0
        while True:
            try:
                response = session.get(
                    "https://robinhoodchain.blockscout.com/api",
                    params={
                        "module": "logs",
                        "action": "getLogs",
                        "address": NVDA_POOL,
                        "fromBlock": first,
                        "toBlock": last,
                        "topic0": V3_SWAP_TOPIC,
                    },
                    timeout=30,
                    headers={"User-Agent": "nvda-one-session-forensic/0.1"},
                )
                status = response.status_code
                response.raise_for_status()
                payload = response.json()
                if payload.get("status") == "1":
                    result = payload.get("result", [])
                    condition = "success"
                    break
                if payload.get("message") == "No logs found":
                    condition = "success_empty"
                    break
                condition = "indexer_error"
            except requests.Timeout:
                condition = "timeout"
            except requests.RequestException:
                condition = "http_error"
            if retries >= 3:
                complete = False
                break
            retries += 1
            time.sleep(2**retries)
        events.extend(result)
        attempts.append(
            {
                "request_number": request_number,
                "provider": "blockscout",
                "block_start": first,
                "block_end": last,
                "block_count": last - first + 1,
                "http_status": status,
                "status": condition,
                "retry_count": retries,
                "response_event_count": len(result),
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            }
        )
        if request_number % 25 == 0:
            print(f"Blockscout: chunks={request_number}/{len(ranges)} events={len(events)}", flush=True)
        time.sleep(0.1)
    with BLOCKSCOUT_LOG_PATH.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(attempts[0]))
        writer.writeheader()
        writer.writerows(attempts)

    raw_rows = list(csv.DictReader(RAW_EVENTS_PATH.open(encoding="utf-8-sig")))
    official_keys = {(row["transaction_hash"].lower(), int(row["log_index"])) for row in raw_rows}
    blockscout_keys = {(event["transactionHash"].lower(), int(event["logIndex"], 16)) for event in events}
    agrees = complete and blockscout_keys == official_keys
    summary.update(
        {
            "blockscout_count": len(blockscout_keys),
            "blockscout_status": "complete_exact_match" if agrees else "incomplete_or_disagrees",
            "blockscout_successful_chunks": sum(row["status"].startswith("success") for row in attempts),
            "blockscout_failed_chunks": sum(not row["status"].startswith("success") for row in attempts),
            "blockscout_official_event_key_symmetric_difference": len(blockscout_keys ^ official_keys),
            "demonstrably_complete": bool(summary["official_complete"]),
            "classification": "RETRIEVAL_IMPLEMENTATION_ISSUE" if summary["official_complete"] else "MIXED",
        }
    )
    SUMMARY_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    reconcile_blockscout() if "--blockscout" in sys.argv else main()
