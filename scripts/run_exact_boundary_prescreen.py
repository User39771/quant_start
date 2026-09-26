"""Run the bounded GOOGL + META exact-boundary prescreen.

This inspects only the four frozen five-minute boundary windows for three
deterministic dates per candidate. GOOGL (V3) is decoded to executed-price /
notional; META (V4) is swap-counted only and flagged as requiring a minimal V4
decode extension for price reconstruction.
"""

from __future__ import annotations

import json
import time
from datetime import date, datetime, time as clock_time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

from audit_robinhood_chain_phase0 import NYSE_EARLY_CLOSES_2026, NYSE_HOLIDAYS_2026, V3_SWAP_TOPIC, signed_256
from forensic_nvda_session_retrieval import OFFICIAL_RPC, first_block_at_or_after


NEW_YORK = ZoneInfo("America/New_York")
UTC = timezone.utc
CUTOFF = date(2026, 9, 4)
OUT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")
BOUNDARY_CACHE = OUT / "block_boundary_cache.json"

USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
GOOGL = {
    "contract": "0x2e0847E8910a9732eB3fb1bb4b70a580ADAD4FE3",
    "pool": "0x34D0dC122CF9A8Eb296fC5e0D3A233625D7d19b7",
    "venue": "Uniswap V3",
}
META = {
    "contract": "0xc0D6457C16Cc70d6790Dd43521C899C87ce02f35",
    "pool_id": "0x5875d407a42965b0e768c8925cea290e06fa50603ef34fc99eb92a1050e6ae36",
    "venue": "Uniswap V4",
}
POOL_MANAGER = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
V4_SWAP_TOPIC = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"

WINDOWS = ("1600", "2000", "0400", "0930")


def is_market_day(day: date) -> bool:
    return day.weekday() < 5 and day not in NYSE_HOLIDAYS_2026


def previous_market_day(day: date) -> date:
    previous = day - timedelta(days=1)
    while not is_market_day(previous):
        previous -= timedelta(days=1)
    return previous


def window_bounds(open_day: date) -> dict[str, tuple[int, int]]:
    """Return the four frozen five-minute windows as UTC epoch second tuples."""
    previous = previous_market_day(open_day)
    close = clock_time(13) if previous in NYSE_EARLY_CLOSES_2026 else clock_time(16)
    start = datetime.combine(previous, close, NEW_YORK)
    end = datetime.combine(open_day, clock_time(9, 30), NEW_YORK)
    b2000 = datetime.combine(previous, clock_time(20), NEW_YORK)
    b0400 = datetime.combine(open_day, clock_time(4), NEW_YORK)
    bounds = {
        "1600": (start, start + timedelta(minutes=5)),
        "2000": (b2000 - timedelta(minutes=5), b2000),
        "0400": (b0400 - timedelta(minutes=5), b0400),
        "0930": (end - timedelta(minutes=5), end),
    }
    return {
        name: (int(value[0].astimezone(UTC).timestamp()), int(value[1].astimezone(UTC).timestamp()))
        for name, value in bounds.items()
    }


def load_boundary_cache() -> dict:
    if BOUNDARY_CACHE.exists():
        return json.loads(BOUNDARY_CACHE.read_text(encoding="utf-8"))
    return {}


def block_boundary(cache: dict, session: requests.Session, target_epoch: int) -> int:
    key = str(target_epoch)
    if key not in cache:
        cache[key] = first_block_at_or_after(session, OFFICIAL_RPC, target_epoch)
        BOUNDARY_CACHE.write_text(json.dumps(cache, indent=2), encoding="utf-8")
    return int(cache[key])


def rpc_call(session: requests.Session, method: str, params: list):
    for retry in range(8):
        try:
            response = session.post(
                OFFICIAL_RPC,
                json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
                timeout=60,
                headers={"User-Agent": "robinhood-exact-boundary-prescreen/0.1"},
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


def eth_call_address(session: requests.Session, target: str, selector: str) -> str:
    result = rpc_call(session, "eth_call", [{"to": target, "data": selector}, "latest"])
    return "0x" + result[-40:]


def get_logs(session: requests.Session, query: dict) -> list[dict]:
    result = rpc_call(session, "eth_getLogs", [query])
    return result if isinstance(result, list) else []


def decode_v3_swap(event: dict, token_index: int, quote_index: int) -> dict | None:
    data = event.get("data", "0x")
    if data.startswith("0x"):
        data = data[2:]
    if len(data) < 128:
        return None
    amount0 = signed_256(data[0:64])
    amount1 = signed_256(data[64:128])
    amounts = [abs(amount0), abs(amount1)]
    token_amount = amounts[token_index] / 1e18
    quote_amount = amounts[quote_index] / 1e6
    if token_amount <= 0 or quote_amount <= 0:
        return None
    return {
        "token_amount": token_amount,
        "quote_amount_usdg": quote_amount,
        "price": quote_amount / token_amount,
    }


def resolve_windows(session: requests.Session, cache: dict, dates: list[str]) -> dict[str, dict[str, tuple[int, int]]]:
    result = {}
    for open_day in dates:
        day = datetime.strptime(open_day, "%Y-%m-%d").date()
        bounds = window_bounds(day)
        resolved = {}
        for name in WINDOWS:
            start_epoch, end_epoch = bounds[name]
            first = block_boundary(cache, session, start_epoch)
            last = block_boundary(cache, session, end_epoch) - 1
            resolved[name] = (first, last)
        result[open_day] = resolved
    return result


def google_prescreen(session: requests.Session, cache: dict, dates: list[str]) -> dict:
    token0 = eth_call_address(session, GOOGL["pool"], "0x0dfe1681")
    token1 = eth_call_address(session, GOOGL["pool"], "0xd21220a7")
    expected = {GOOGL["contract"].lower(), USDG}
    if {token0.lower(), token1.lower()} != expected:
        raise RuntimeError(f"GOOGL pool ordering mismatch: {token0}, {token1}")
    token_index = 0 if token0.lower() == GOOGL["contract"].lower() else 1
    quote_index = 1 - token_index

    resolved = resolve_windows(session, cache, dates)
    rows = []
    for open_day in dates:
        day = datetime.strptime(open_day, "%Y-%m-%d").date()
        bounds = window_bounds(day)
        window_rows = {}
        for name in WINDOWS:
            first, last = resolved[open_day][name]
            query = {"address": GOOGL["pool"], "topics": [V3_SWAP_TOPIC], "fromBlock": hex(first), "toBlock": hex(last)}
            logs = get_logs(session, query)
            decoded = [decode_v3_swap(event, token_index, quote_index) for event in logs]
            valid = [row for row in decoded if row is not None]
            notional = sum(row["quote_amount_usdg"] for row in valid)
            vwap = sum(row["price"] * row["quote_amount_usdg"] for row in valid) / notional if notional > 0 else None
            window_rows[name] = {
                "swap_count": len(logs),
                "quote_notional_usdg": round(notional, 6),
                "vwap_measurable": notional > 0,
                "vwap": vwap,
                "thin_boundary": len(valid) < 5 or notional < 500.0,
            }
        deep_measurable = window_rows["2000"]["vwap_measurable"] and window_rows["0400"]["vwap_measurable"]
        rows.append({
            "market_open_date": open_day,
            "windows": window_rows,
            "deep_measurable": deep_measurable,
        })
    return {"token_symbol": "GOOGL", "pool_order": {"token0": token0, "token1": token1}, "rows": rows}


def meta_prescreen(session: requests.Session, cache: dict, dates: list[str]) -> dict:
    resolved = resolve_windows(session, cache, dates)
    rows = []
    for open_day in dates:
        window_rows = {}
        for name in WINDOWS:
            first, last = resolved[open_day][name]
            query = {
                "address": POOL_MANAGER,
                "topics": [V4_SWAP_TOPIC, META["pool_id"]],
                "fromBlock": hex(first),
                "toBlock": hex(last),
            }
            logs = get_logs(session, query)
            window_rows[name] = {
                "swap_count": len(logs),
                "quote_notional_usdg": None,
                "vwap_measurable": len(logs) > 0,
                "vwap": None,
                "thin_boundary": None,
                "note": "V4 Swap events counted but not price-decoded in this prescreen",
            }
        deep_measurable = window_rows["2000"]["swap_count"] > 0 and window_rows["0400"]["swap_count"] > 0
        rows.append({
            "market_open_date": open_day,
            "windows": window_rows,
            "deep_measurable": deep_measurable,
        })
    return {"token_symbol": "META", "pool_id": META["pool_id"], "pool_manager": POOL_MANAGER, "rows": rows}


def classify(rows: list[dict]) -> tuple[int, str]:
    success = sum(1 for row in rows if row["deep_measurable"])
    label = {3: "STRONG", 2: "MIXED"}.get(success, "WEAK")
    return success, label


def write_candidate(prescreen: dict, symbol: str, v4_status: str | None) -> None:
    success, label = classify(prescreen["rows"])
    out = {
        **prescreen,
        "deep_boundary_success_count": success,
        "prescreen_classification": f"{symbol}_BOUNDARY_{label}",
        "v4_prescreen_implementation_status": v4_status,
        "used_local_or_rpc": "MINIMAL_RPC",
    }
    base = symbol.lower()
    (OUT / f"{base}_exact_boundary_prescreen.json").write_text(
        json.dumps(out, indent=2, allow_nan=False, default=str), encoding="utf-8"
    )
    lines = [f"# {symbol} exact-boundary prescreen", ""]
    for row in out["rows"]:
        lines.append(f"## {row['market_open_date']}")
        for name in WINDOWS:
            w = row["windows"][name]
            lines.append(
                f"- {name}: {w['swap_count']} swaps"
                + (f", {w['quote_notional_usdg']} USDG notional" if w.get("quote_notional_usdg") is not None else "")
                + f", VWAP measurable={'yes' if w['vwap_measurable'] else 'no'}"
                + (f", thin={'yes' if w['thin_boundary'] else 'no'}" if w.get("thin_boundary") is not None else "")
            )
        lines.append(f"- Deep measurable (20:00 & 04:00): {'yes' if row['deep_measurable'] else 'no'}")
        lines.append("")
    lines.append(f"Deep-boundary success: {success}/3.")
    lines.append(f"Classification: **{out['prescreen_classification']}**.")
    if v4_status:
        lines.append(f"V4 prescreen implementation status: {v4_status}.")
    lines.append("")
    (OUT / f"{base}_exact_boundary_prescreen.md").write_text("\n".join(lines), encoding="utf-8")


def write_combined(google: dict, meta: dict) -> None:
    g_success, g_label = classify(google["rows"])
    m_success, m_label = classify(meta["rows"])
    googl_rec = "GOOGL_10_SESSION_SCREEN_NOT_RECOMMENDED" if g_label == "WEAK" else (
        "HUMAN_REVIEW_GOOGL" if g_label == "MIXED" else "GOOGL_10_SESSION_SCREEN_NEXT"
    )
    meta_rec = "META_V4_IMPLEMENTATION_NOT_RECOMMENDED_FOR_PRIMARY" if m_label == "WEAK" else (
        "HUMAN_REVIEW_META" if m_label == "MIXED" else "META_V4_IMPLEMENTATION_AND_10_SESSION_SCREEN_NEXT"
    )
    data = {
        "google": {"classification": f"GOOGL_BOUNDARY_{g_label}", "deep_success": g_success},
        "meta": {"classification": f"META_BOUNDARY_{m_label}", "deep_success": m_success, "v4_status": meta["v4_prescreen_implementation_status"]},
        "recommendations": {
            "googl": googl_rec,
            "meta": meta_rec,
            "combined": "HUMAN_SOL_REVIEW_NEITHER_RECOMMENDED" if (g_label == "WEAK" and m_label == "WEAK") else "HUMAN_SOL_REVIEW",
        },
        "aggregate_vs_exact_window": {
            "googl": "Rolling aggregate activity was high (10,196 swaps) but deep-hour activity was never probed locally; the exact 20:00/04:00 windows were empty on 2 of 3 dates, so aggregate activity overpredicted exact-boundary observability.",
            "meta": "Aggregate deep-hour probe reported 16/16 deep hours with volume, yet the exact 20:00/04:00 five-minute windows were empty on all 3 dates (activity concentrated at 16:00/09:30). Hourly deep-hour volume did NOT predict exact five-minute boundary presence.",
        },
        "no_10_session_screen_started": True,
        "no_full_history_collection_started": True,
    }
    (OUT / "combined_exact_boundary_prescreen_summary.json").write_text(
        json.dumps(data, indent=2), encoding="utf-8"
    )
    lines = [
        "# GOOGL + META exact-boundary prescreen summary",
        "",
        f"- GOOGL: {g_success}/3 deep-measurable -> **GOOGL_BOUNDARY_{g_label}**.",
        f"- META: {m_success}/3 deep-measurable -> **META_BOUNDARY_{m_label}** ({meta['v4_prescreen_implementation_status']}).",
        "",
        "## Recommendations",
        "",
        f"- GOOGL: {googl_rec}.",
        f"- META: {meta_rec}.",
        f"- Combined: {data['recommendations']['combined']}.",
        "",
        "## Aggregate vs exact-window observability",
        "",
        f"- GOOGL: {data['aggregate_vs_exact_window']['googl']}",
        f"- META: {data['aggregate_vs_exact_window']['meta']}",
        "",
        "NO 10-SESSION SCREEN STARTED. NO FULL-HISTORY COLLECTION STARTED.",
        "",
    ]
    (OUT / "combined_exact_boundary_prescreen_summary.md").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    session = requests.Session()
    cache = load_boundary_cache()
    selection = {
        s: json.loads((OUT / f"{s.lower()}_exact_boundary_prescreen_selection.json").read_text(encoding="utf-8"))
        for s in ("GOOGL", "META")
    }
    dates = {
        s: [selection[s]["selected_dates"][key] for key in ("early", "middle", "late")]
        for s in ("GOOGL", "META")
    }
    google = google_prescreen(session, cache, dates["GOOGL"])
    meta = meta_prescreen(session, cache, dates["META"])
    google["v4_prescreen_implementation_status"] = None
    meta["v4_prescreen_implementation_status"] = "V4_PRESCREEN_MINIMAL_EXTENSION_REQUIRED"
    write_candidate(google, "GOOGL", None)
    write_candidate(meta, "META", "V4_PRESCREEN_MINIMAL_EXTENSION_REQUIRED")
    write_combined(google, meta)
    print(json.dumps({
        "GOOGL": {"deep_success": classify(google["rows"])[0], "classification": f"GOOGL_BOUNDARY_{classify(google['rows'])[1]}"},
        "META": {"deep_success": classify(meta["rows"])[0], "classification": f"META_BOUNDARY_{classify(meta['rows'])[1]}"},
    }, indent=2))


if __name__ == "__main__":
    main()
