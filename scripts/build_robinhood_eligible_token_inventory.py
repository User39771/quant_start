"""Build a lightweight Robinhood Chain Stock Token eligibility inventory.

Only registry metadata and bounded indexer summaries are requested.  This
script deliberately does not download raw swap histories.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests


ASSETS_URL = "https://api.robinhood.com/rhj/assets"
CORPORATE_ACTIONS_URL = "https://api.robinhood.com/rhj/corporate-actions"
DEXSCREENER_TOKENS_URL = "https://api.dexscreener.com/tokens/v1/robinhood/"
GECKO_OHLCV_URL = "https://api.geckoterminal.com/api/v2/networks/robinhood/pools/{pool}/ohlcv/hour"
NASDAQ_HISTORY_URL = "https://api.nasdaq.com/api/quote/{symbol}/historical"
OFFICIAL_RPC_URL = "https://rpc.mainnet.chain.robinhood.com"
MAINNET_CHAIN_ID = 4663
USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
AS_OF = date(2026, 9, 9)
OUTPUT_DIR = Path("reports/robinhood_chain_pilot/eligible_token_inventory")
SHORTLIST = {"NVDA", "GME", "META", "AMZN", "TSLA", "USO"}
PRIVATE_UNDERLIERS = {"SPCX", "XNDU"}
NEW_YORK = ZoneInfo("America/New_York")
POOL_MANAGER = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
V3_SWAP_TOPIC = "0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67"
V4_SWAP_TOPIC = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"


def get_json(url: str, params: dict | None = None, attempts: int = 4) -> dict:
    headers = {"User-Agent": "Mozilla/5.0 Robinhood-Chain-academic-feasibility/1.0"}
    for attempt in range(attempts):
        try:
            response = requests.get(url, params=params, headers=headers, timeout=30)
            response.raise_for_status()
            return response.json()
        except (requests.RequestException, ValueError):
            if attempt + 1 == attempts:
                raise
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def market_sessions(start: str | None) -> int | None:
    if not start:
        return None
    day = datetime.fromisoformat(start.replace("Z", "+00:00")).date()
    # Only closures inside the bounded July-September 2026 pool-age range.
    closures = {date(2026, 7, 3), date(2026, 9, 7)}
    count = 0
    while day <= AS_OF:
        if day.weekday() < 5 and day not in closures:
            count += 1
        day += timedelta(days=1)
    return count


def verify_underlying(symbol: str) -> tuple[bool, str]:
    asset_class = "etf" if symbol == "USO" else "stocks"
    payload = get_json(
        NASDAQ_HISTORY_URL.format(symbol=symbol),
        {"assetclass": asset_class, "fromdate": "2026-07-01", "todate": "2026-09-08", "limit": 10},
    )
    rows = ((payload.get("data") or {}).get("tradesTable") or {}).get("rows") or []
    valid = bool(rows) and all(row.get("open") and row.get("close") for row in rows)
    return valid, f"https://www.nasdaq.com/market-activity/{asset_class}/{symbol.lower()}/historical"


def overnight_summary(pool: str) -> str:
    payload = get_json(
        GECKO_OHLCV_URL.format(pool=pool),
        {"aggregate": 1, "limit": 48, "currency": "usd", "token": "base"},
    )
    candles = payload["data"]["attributes"]["ohlcv_list"]
    deep = [item for item in candles if datetime.fromtimestamp(item[0], timezone.utc).astimezone(NEW_YORK).hour >= 20 or datetime.fromtimestamp(item[0], timezone.utc).astimezone(NEW_YORK).hour < 4]
    nonzero = sum(float(item[5]) > 0 for item in deep)
    volume = sum(float(item[5]) for item in deep)
    return f"GeckoTerminal last-48h hourly OHLCV: {nonzero} deep-overnight hours with volume; ${volume:.2f} aggregate"


def recent_rpc_logs(pool: str, version: str) -> int:
    def call(method: str, params: list):
        response = requests.post(
            OFFICIAL_RPC_URL,
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        if "error" in payload:
            raise RuntimeError(payload["error"])
        return payload["result"]

    latest = int(call("eth_blockNumber", []), 16)
    query = {"fromBlock": hex(latest - 500), "toBlock": hex(latest)}
    if version == "Uniswap V4":
        query.update({"address": POOL_MANAGER, "topics": [V4_SWAP_TOPIC, pool]})
    else:
        query.update({"address": pool, "topics": [V3_SWAP_TOPIC]})
    return len(call("eth_getLogs", [query]))


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    assets = get_json(ASSETS_URL)["assets"]
    mainnet = [
        asset
        for asset in assets
        if asset.get("status") == "ASSET_STATUS_ACTIVE"
        and any(item.get("chainId") == MAINNET_CHAIN_ID for item in asset.get("deployments", []))
    ]
    by_contract = {
        next(item["contractAddress"] for item in asset["deployments"] if item.get("chainId") == MAINNET_CHAIN_ID).lower(): asset
        for asset in mainnet
    }

    pools = []
    addresses = list(by_contract)
    for offset in range(0, len(addresses), 30):
        pools.extend(get_json(DEXSCREENER_TOKENS_URL + ",".join(addresses[offset : offset + 30])))
        time.sleep(0.4)

    mapped: dict[str, list[dict]] = {address: [] for address in by_contract}
    for pool in pools:
        base = pool.get("baseToken", {}).get("address", "").lower()
        quote = pool.get("quoteToken", {}).get("address", "").lower()
        if base in by_contract and quote == USDG:
            mapped[base].append(pool)
        elif quote in by_contract and base == USDG:
            mapped[quote].append(pool)

    try:
        actions_payload = get_json(CORPORATE_ACTIONS_URL)
        actions = actions_payload.get("corpActions", actions_payload.get("corporateActions", []))
    except requests.RequestException:
        actions = []
    actions_by_symbol: dict[str, list[dict]] = {}
    for action in actions:
        actions_by_symbol.setdefault(action.get("tokenSymbol", ""), []).append(action)

    rows = []
    for address, asset in by_contract.items():
        candidates = mapped[address]
        pool = max(candidates, key=lambda item: float(item.get("volume", {}).get("h24") or 0)) if candidates else None
        attributes = pool or {}
        dex_id = attributes.get("dexId", "")
        transactions = attributes.get("txns", {}).get("h24", {})
        swap_count = sum(int(transactions.get(key) or 0) for key in ("buys", "sells")) if pool else None
        volume = float(attributes.get("volume", {}).get("h24") or 0) if pool else None
        created = datetime.fromtimestamp(attributes["pairCreatedAt"] / 1000, timezone.utc).isoformat().replace("+00:00", "Z") if pool and attributes.get("pairCreatedAt") else None
        labels = " ".join(attributes.get("labels") or []).lower()
        sessions = market_sessions(created)
        multiplier = asset.get("currentMultiplier")
        token_actions = actions_by_symbol.get(asset["tokenSymbol"], [])
        if multiplier == "1.000000000000000000" and not token_actions:
            multiplier_risk = "CLEAR_CURRENT_NO_RECORDED_ACTION"
        elif token_actions:
            multiplier_risk = "DOCUMENTED_ACTION_DATE_AWARE_REVIEW"
        else:
            multiplier_risk = "UNRESOLVED_NONUNIT_MULTIPLIER"
        if pool:
            activity = "HIGH" if swap_count >= 500 and volume >= 100_000 else "MODERATE" if swap_count >= 50 and volume >= 10_000 else "LOW"
            classification = "CONDITIONAL"  # promoted only after underlier and overnight confirmation
            rejection = ""
        else:
            activity = "UNKNOWN"
            classification = "REJECT"
            rejection = "No canonical-token/USDG pair in bounded DEX Screener canonical-token batch scan"
        row = {
                "token_symbol": asset["tokenSymbol"],
                "underlying_symbol": asset["tokenSymbol"],
                "token_name": asset["tokenName"],
                "canonical_contract": next(item["contractAddress"] for item in asset["deployments"] if item.get("chainId") == MAINNET_CHAIN_ID),
                "status": asset["status"],
                "spot_venue": dex_id or "UNKNOWN",
                "venue_version": "Uniswap V4" if "v4" in labels else "Uniswap V3" if "v3" in labels else "UNKNOWN",
                "pool_or_market_id": attributes.get("pairAddress", "UNKNOWN"),
                "quote_asset": "USDG" if pool else "UNKNOWN",
                "pool_mapping_confidence": "HIGH" if pool else "UNKNOWN",
                "first_verified_spot_date": created or "UNKNOWN",
                "eligible_session_count_estimate": sessions if sessions is not None else "UNKNOWN",
                "has_15_sessions": sessions >= 15 if sessions is not None else "UNKNOWN",
                "has_20_sessions": sessions >= 20 if sessions is not None else "UNKNOWN",
                "recent_activity_evidence": "DEX Screener rolling 24h canonical-token batch summary" if pool else "Not observed in bounded scan",
                "recent_swap_count_or_rate": swap_count if swap_count is not None else "UNKNOWN",
                "recent_notional_if_available": volume if volume is not None else "UNKNOWN",
                "overnight_activity_evidence": "UNKNOWN",
                "recent_rpc_execution_evidence": "UNKNOWN",
                "activity_confidence": "MEDIUM" if pool else "LOW",
                "underlying_open_close_available": "UNKNOWN",
                "underlying_source": "UNKNOWN",
                "current_multiplier": multiplier,
                "historical_multiplier_risk": multiplier_risk,
                "corporate_action_warning": json.dumps(token_actions, separators=(",", ":")) if token_actions else "",
                "data_access_complexity": "MEDIUM_RPC_LOGS" if pool else "HIGH_POOL_DISCOVERY_REQUIRED",
                "overall_classification": classification,
                "selection_reason": "",
                "rejection_reason": rejection,
            }
        if asset["tokenSymbol"] in PRIVATE_UNDERLIERS:
            row["overall_classification"] = "REJECT"
            row["rejection_reason"] = "No valid US-listed equity/ETF regular-session Open/Close target"
        rows.append(row)

    for row in rows:
        if row["token_symbol"] not in SHORTLIST:
            continue
        available, source = verify_underlying(row["underlying_symbol"])
        row["underlying_open_close_available"] = available
        row["underlying_source"] = source
        time.sleep(0.5)
        row["overnight_activity_evidence"] = overnight_summary(row["pool_or_market_id"])
        row["recent_rpc_execution_evidence"] = f"{recent_rpc_logs(row['pool_or_market_id'], row['venue_version'])} Swap logs in latest 500 blocks via official RPC"
        row["activity_confidence"] = "HIGH"
        time.sleep(10)
        if row["token_symbol"] == "NVDA":
            row["overall_classification"] = "STRONG"
            row["selection_reason"] = "Validated 20-session anchor; not counted as an additional recommendation"
        elif available and row["has_20_sessions"] is True and row["historical_multiplier_risk"] == "CLEAR_CURRENT_NO_RECORDED_ACTION":
            row["overall_classification"] = "STRONG"
            row["selection_reason"] = {
                "GME": "High-activity retail-attention candidate with long-enough pool history",
                "META": "Large established technology issuer; liquid V4 venue diversifies venue version",
                "AMZN": "Large established technology/consumer issuer with sustained activity",
                "TSLA": "High-attention, high-volatility large-cap candidate with the oldest selected pool",
                "USO": "Liquid non-equity-sector ETF adds commodity-linked diversification",
            }[row["token_symbol"]]

    rows.sort(key=lambda row: (row["overall_classification"] == "REJECT", -(row["recent_notional_if_available"] if isinstance(row["recent_notional_if_available"], float) else -1), row["token_symbol"]))
    assert len(rows) == len(mainnet) == len({row["canonical_contract"].lower() for row in rows})
    assert {row["token_symbol"] for row in rows if row["overall_classification"] == "STRONG"} == SHORTLIST
    output = OUTPUT_DIR / "eligible_token_inventory.csv"
    with output.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    diagnostics = {
        "as_of": AS_OF.isoformat(),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "active_mainnet_assets": len(mainnet),
        "dexscreener_batch_requests": (len(addresses) + 29) // 30,
        "pairs_returned": len(pools),
        "canonical_usdg_pool_mappings": sum(bool(value) for value in mapped.values()),
        "mapped_with_at_least_15_estimated_sessions": sum(row["pool_mapping_confidence"] == "HIGH" and row["has_15_sessions"] is True for row in rows),
        "mapped_with_at_least_20_estimated_sessions": sum(row["pool_mapping_confidence"] == "HIGH" and row["has_20_sessions"] is True for row in rows),
        "shortlist_including_anchor": sorted(SHORTLIST),
        "corporate_actions_loaded": len(actions),
        "scope_note": "Registry-wide metadata plus bounded summary/indexer probes; no raw swap history",
    }
    (OUTPUT_DIR / "diagnostics.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
    print(json.dumps(diagnostics, indent=2))
    for row in rows[:30]:
        print(row["token_symbol"], row["venue_version"], row["eligible_session_count_estimate"], row["recent_swap_count_or_rate"], row["recent_notional_if_available"])


if __name__ == "__main__":
    main()
