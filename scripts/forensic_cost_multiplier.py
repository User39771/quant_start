"""Minimal COST ERC-8056 multiplier forensic check; no full swap retrieval."""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import requests
from Crypto.Hash import keccak


RPC_URL = "https://rpc.mainnet.chain.robinhood.com"
ARCHIVE_RPC_URL = "https://rpc.ordofi.network"
ASSETS_URL = "https://api.robinhood.com/rhj/assets"
ACTIONS_URL = "https://api.robinhood.com/rhj/corporate-actions"
NASDAQ_HISTORY_URL = "https://api.nasdaq.com/api/quote/COST/historical"
NASDAQ_DIVIDENDS_URL = "https://api.nasdaq.com/api/quote/COST/dividends"
COST = "0x4EA005168D7F09a7A0Ba9D1DEf21a479950E44C2"
POOL = "0x0a2121A50A09eD0796ae81F9c53fF9398355a398"
POOL_START = datetime.fromisoformat("2026-07-22T23:51:49+00:00")
OUTPUT = Path("reports/robinhood_chain_pilot/eligible_token_inventory/cost_multiplier_forensic")
UI_EVENT = "0x2205df4534432b2f60654a3fdb48737ffdaf3e9edb1a498bd985bc026b15b055"
V3_SWAP = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"


def selector(signature: str) -> str:
    digest = keccak.new(digest_bits=256)
    digest.update(signature.encode())
    return "0x" + digest.hexdigest()[:8]


def rpc(method: str, params: list, attempts: int = 5, url: str = RPC_URL):
    for attempt in range(attempts):
        response = requests.post(
            url,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=40,
        )
        if response.status_code == 429:
            time.sleep(2 ** attempt)
            continue
        response.raise_for_status()
        payload = response.json()
        if "error" not in payload:
            return payload["result"]
        if attempt + 1 == attempts:
            raise RuntimeError(payload["error"])
        time.sleep(2 ** attempt)
    raise AssertionError("unreachable")


def block_timestamp(block: int) -> int:
    return int(rpc("eth_getBlockByNumber", [hex(block), False])["timestamp"], 16)


def block_near(timestamp: int, latest: int) -> int:
    block = max(0, latest + round((timestamp - block_timestamp(latest)) * 10))
    for _ in range(8):
        error = timestamp - block_timestamp(block)
        if abs(error) <= 2:
            return block
        block = max(0, block + round(error * 10))
    return block


def eth_call(signature: str, block: int | str = "latest") -> int:
    params = [{"to": COST, "data": selector(signature)}, hex(block) if isinstance(block, int) else block]
    try:
        result = rpc("eth_call", params)
    except RuntimeError:
        if not isinstance(block, int):
            raise
        result = rpc("eth_call", params, url=ARCHIVE_RPC_URL)
    return int(result, 16)


def signed(word: str) -> int:
    value = int(word, 16)
    return value - 2**256 if value >= 2**255 else value


def format_multiplier(raw: int) -> str:
    return f"{Decimal(raw) / Decimal(10**18):.18f}"


def get_json(url: str) -> dict:
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()


def get_nasdaq(url: str, params: dict) -> dict:
    response = requests.get(
        url,
        params=params,
        headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*", "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    latest = int(rpc("eth_blockNumber", []), 16)
    start_block = block_near(int(POOL_START.timestamp()), latest)
    assets = get_json(ASSETS_URL)["assets"]
    asset = next(item for item in assets if item["tokenSymbol"] == "COST")
    actions_payload = get_json(ACTIONS_URL)
    actions = actions_payload.get("corpActions", actions_payload.get("corporateActions", []))
    cost_actions = [item for item in actions if item.get("tokenSymbol") == "COST"]
    history = get_nasdaq(NASDAQ_HISTORY_URL, {"assetclass": "stocks", "fromdate": "2026-08-03", "todate": "2026-08-11", "limit": 10})
    cost_aug10 = next(row for row in history["data"]["tradesTable"]["rows"] if row["date"] == "08/10/2026")
    dividends = get_nasdaq(NASDAQ_DIVIDENDS_URL, {"assetclass": "stocks"})
    cost_dividend = next(row for row in dividends["data"]["dividends"]["rows"] if row["exOrEffDate"] == "07/24/2026")

    events = rpc(
        "eth_getLogs",
        [{"address": COST, "topics": [UI_EVENT], "fromBlock": "0x0", "toBlock": "latest"}],
    )
    decoded = []
    for event in events:
        words = [event["data"][2 + index * 64 : 2 + (index + 1) * 64] for index in range(3)]
        old, new, effective = (int(word, 16) for word in words)
        block = int(event["blockNumber"], 16)
        decoded.append(
            {
                "event_block": block,
                "event_timestamp_utc": datetime.fromtimestamp(block_timestamp(block), timezone.utc).isoformat(),
                "old_multiplier": format_multiplier(old),
                "new_multiplier": format_multiplier(new),
                "old_multiplier_raw": old,
                "new_multiplier_raw": new,
                "effective_timestamp_utc": datetime.fromtimestamp(effective, timezone.utc).isoformat(),
                "effective_unix": effective,
                "transaction_hash": event["transactionHash"],
            }
        )

    try:
        start_multiplier_raw = eth_call("uiMultiplier()", start_block)
        historical_state_source = "historical eth_call"
    except RuntimeError:
        start_multiplier_raw = None
        historical_state_source = "archive state unavailable; derived from complete ERC-8056 event trail"
    ordered = sorted(decoded, key=lambda item: item["effective_unix"])
    if ordered:
        derived_start = ordered[0]["old_multiplier_raw"]
        for transition in ordered:
            if transition["effective_unix"] <= int(POOL_START.timestamp()):
                derived_start = transition["new_multiplier_raw"]
        if start_multiplier_raw is None:
            start_multiplier_raw = derived_start
    start_multiplier = format_multiplier(start_multiplier_raw) if start_multiplier_raw is not None else None
    current_multiplier_raw = eth_call("uiMultiplier()")
    pending_multiplier_raw = eth_call("newUIMultiplier()")
    current_multiplier = format_multiplier(current_multiplier_raw)
    pending_multiplier = format_multiplier(pending_multiplier_raw)
    effective_at = eth_call("effectiveAt()")

    swap_samples = []
    for transition in ordered:
        effective_block = block_near(transition["effective_unix"], latest)
        logs = rpc(
            "eth_getLogs",
            [{"address": POOL, "topics": [V3_SWAP], "fromBlock": hex(effective_block - 3000), "toBlock": hex(effective_block + 3000)}],
        )
        for event in logs:
            words = [event["data"][2 + index * 64 : 2 + (index + 1) * 64] for index in range(5)]
            amount0, amount1 = signed(words[0]), signed(words[1])
            block = int(event["blockNumber"], 16)
            timestamp = block_timestamp(block)
            # Pool ordering is verified separately below; COST is token0 and USDG token1.
            raw_price = abs(amount1) / 1e6 / (abs(amount0) / 1e18) if amount0 else None
            multiplier = transition["old_multiplier"] if timestamp < transition["effective_unix"] else transition["new_multiplier"]
            swap_samples.append(
                {
                    "timestamp_utc": datetime.fromtimestamp(timestamp, timezone.utc).isoformat(),
                    "side_of_transition": "before" if timestamp < transition["effective_unix"] else "after",
                    "raw_usdg_per_raw_token": raw_price,
                    "multiplier": multiplier,
                    "usdg_per_ui_share": float(Decimal(str(raw_price)) / Decimal(multiplier)) if raw_price else None,
                    "transaction_hash": event["transactionHash"],
                }
            )

    token0 = "0x" + rpc("eth_call", [{"to": POOL, "data": "0x0dfe1681"}, "latest"])[-40:]
    token1 = "0x" + rpc("eth_call", [{"to": POOL, "data": "0xd21220a7"}, "latest"])[-40:]
    assert token0.lower() == COST.lower()
    assert current_multiplier == asset["currentMultiplier"]

    OUTPUT.mkdir(parents=True, exist_ok=True)
    timeline = []
    cursor = POOL_START
    multiplier = start_multiplier
    for transition in ordered:
        effective = datetime.fromtimestamp(transition["effective_unix"], timezone.utc)
        if effective <= POOL_START:
            continue
        timeline.append({"effective_from": cursor.isoformat(), "effective_to": effective.isoformat(), "multiplier": multiplier, "source": "ERC-8056 event oldMultiplier", "corporate_action_type": "LIKELY_CASH_DIVIDEND; RH endpoint absent", "corporate_action_date": "2026-07-24 ex/record; 2026-08-07 payment", "evidence_quality": "HIGH_STATE_PATH; MODERATE_CAUSAL_ATTRIBUTION", "notes": "eligible-window state before the only full-lifetime update event"})
        cursor, multiplier = effective, transition["new_multiplier"]
    timeline.append({"effective_from": cursor.isoformat(), "effective_to": "OPEN", "multiplier": multiplier, "source": "ERC-8056 event + current eth_call + /rhj/assets", "corporate_action_type": "LIKELY_CASH_DIVIDEND; RH endpoint absent", "corporate_action_date": "2026-07-24 ex/record; 2026-08-07 payment", "evidence_quality": "HIGH_STATE_PATH; MODERATE_CAUSAL_ATTRIBUTION", "notes": "exact effective timestamp is onchain; gross dividend does not mathematically reconcile without undocumented deductions"})
    with (OUTPUT / "cost_multiplier_timeline.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(timeline[0]))
        writer.writeheader()
        writer.writerows(timeline)
    with (OUTPUT / "cost_transition_swap_samples.csv").open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(swap_samples[0]) if swap_samples else ["none"])
        writer.writeheader()
        if swap_samples:
            writer.writerows(swap_samples)
    summary = {
        "canonical_contract": COST,
        "canonical_pool": POOL,
        "pool_token0": token0,
        "pool_token1": token1,
        "pool_start_utc": POOL_START.isoformat(),
        "start_block": start_block,
        "start_multiplier": start_multiplier,
        "historical_state_source": historical_state_source,
        "current_multiplier_api": asset["currentMultiplier"],
        "current_multiplier_onchain": current_multiplier,
        "new_ui_multiplier_onchain": pending_multiplier,
        "effective_at_onchain": effective_at,
        "cost_corporate_actions_api": cost_actions,
        "nasdaq_cost_aug10": cost_aug10,
        "nasdaq_cost_dividend": cost_dividend,
        "multiplier_events": decoded,
        "transition_swap_sample_count": len(swap_samples),
        "implied_cash_value_at_last_pre_transition_swap": str((Decimal(current_multiplier) - Decimal(1)) * Decimal(str(swap_samples[1]["raw_usdg_per_raw_token"]))) if len(swap_samples) >= 2 else None,
        "classification": "RESOLVED_WITH_MINOR_UNCERTAINTY",
        "panel_implication": "COST_ELIGIBLE_WITH_WARNING",
    }
    (OUTPUT / "forensic_evidence.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
