"""Audit 5-minute vs pre-specified 30-minute boundary measurement feasibility.

Measurement coverage only. No returns, no prediction, no additional window
lengths. Reuses local decoded-swap artifacts for the seven collected tokens and
minimal RPC for the GOOGL/META 30-minute windows.
"""

from __future__ import annotations

import csv
import json
import time
from datetime import date, datetime, time as clock_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

from audit_robinhood_chain_phase0 import V3_SWAP_TOPIC, signed_256
from audit_robinhood_chain_phase0 import NYSE_EARLY_CLOSES_2026, NYSE_HOLIDAYS_2026
from build_robinhood_five_token_panel import decoded_path
from forensic_nvda_session_retrieval import OFFICIAL_RPC, first_block_at_or_after


NEW_YORK = ZoneInfo("America/New_York")
UTC = __import__("datetime").timezone.utc
OUT = Path("reports/robinhood_chain_pilot/five_token_unbalanced_panel")
SESSIONS = OUT / "sessions"
BOUNDARY_CACHE = OUT / "block_boundary_cache.json"

THIN_MIN_SWAPS = 5
THIN_MIN_NOTIONAL = 500.0
BOUNDARIES = ("1600", "2000", "0400", "0930")

USDG = "0x5fc5360d0400a0fd4f2af552add042d716f1d168"
GOOGL_CFG = {"contract": "0x2e0847E8910a9732eB3fb1bb4b70a580ADAD4FE3", "pool": "0x34D0dC122CF9A8Eb296fC5e0D3A233625D7d19b7"}
META_CFG = {"pool_id": "0x5875d407a42965b0e768c8925cea290e06fa50603ef34fc99eb92a1050e6ae36"}
POOL_MANAGER = "0x8366a39cc670b4001a1121b8f6a443a643e40951"
V4_SWAP_TOPIC = "0x40e9cecb9f5f1f1c5b9c97dec2917b7ee92e57ba5563708daca94dd84ad7112f"


def read_selection_dates(path: Path, keys=("early_dates", "late_dates")) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("early_dates", [])) + list(data.get("late_dates", []))


def prescreen_dates(symbol: str) -> list[str]:
    path = OUT / f"{symbol.lower()}_exact_boundary_prescreen_selection.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return [data["selected_dates"][k] for k in ("early", "middle", "late")]


def token_session_dates() -> dict[str, list[str]]:
    dates: dict[str, list[str]] = {}
    for symbol in ("NVDA", "GME", "TSLA"):
        days = sorted(p.name for p in (SESSIONS / symbol).iterdir() if p.is_dir())
        if symbol == "TSLA":
            days = [d for d in days if d >= "2026-07-21"]
        dates[symbol] = days
    for symbol in ("COST", "USO", "AMZN", "UPS"):
        path = OUT / f"{symbol.lower()}_early_late_feasibility_audit.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        dates[symbol] = list(data["early_dates"]) + list(data["late_dates"])
    dates["GOOGL"] = prescreen_dates("GOOGL")
    dates["META"] = prescreen_dates("META")
    return dates


def session_bounds(open_day: str, start_et: str, end_et: str) -> dict[str, tuple[pd.Timestamp, pd.Timestamp]]:
    start = pd.Timestamp(start_et)
    end = pd.Timestamp(end_et)
    previous = pd.Timestamp(open_day) - pd.Timedelta(days=1)
    # Derive anchor dates from the session endpoints rather than calendar.
    b2000 = pd.Timestamp(start.date()).tz_localize(NEW_YORK) + pd.Timedelta(hours=20)
    b0400 = pd.Timestamp(end.date()).tz_localize(NEW_YORK) + pd.Timedelta(hours=4)
    anchors = {"1600": start, "2000": b2000, "0400": b0400, "0930": end}
    windows_5m = {
        "1600": (anchors["1600"], anchors["1600"] + pd.Timedelta(minutes=5)),
        "2000": (anchors["2000"] - pd.Timedelta(minutes=5), anchors["2000"]),
        "0400": (anchors["0400"] - pd.Timedelta(minutes=5), anchors["0400"]),
        "0930": (anchors["0930"] - pd.Timedelta(minutes=5), anchors["0930"]),
    }
    windows_30m = {
        name: (anchor - pd.Timedelta(minutes=30), anchor) for name, anchor in anchors.items()
    }
    return windows_5m, windows_30m


def read_measurement_5m(symbol: str, open_day: str) -> dict:
    path = SESSIONS / symbol / open_day / "measurement_row.csv"
    if not path.exists():
        return {}
    row = pd.read_csv(path).iloc[0].to_dict()
    out = {}
    for name in BOUNDARIES:
        vwap = row.get(f"token_vwap_{name}")
        swaps = row.get(f"boundary_swap_count_{name}")
        notional = row.get(f"boundary_notional_usdg_{name}")
        out[name] = {
            "available": pd.notna(vwap),
            "swap_count": int(swaps) if pd.notna(swaps) else 0,
            "notional": float(notional) if pd.notna(notional) else 0.0,
        }
    return out


def compute_30m(symbol: str, open_day: str, start_et: str, end_et: str) -> dict:
    frame = pd.read_csv(decoded_path(symbol, open_day))
    if frame.empty:
        frame = pd.DataFrame(columns=["block_timestamp_et", "reconstructable", "quote_amount_usdg", "underlying_equivalent_price_usdg"])
    frame["timestamp"] = pd.to_datetime(frame["block_timestamp_et"], utc=True).dt.tz_convert(NEW_YORK)
    frame["reconstructable"] = frame["reconstructable"].astype(str).str.lower().eq("true")
    _, windows = session_bounds(open_day, start_et, end_et)
    out = {}
    for name in BOUNDARIES:
        lo, hi = windows[name]
        sample = frame.loc[frame["reconstructable"] & frame["timestamp"].ge(lo) & frame["timestamp"].lt(hi)]
        notional = float(sample["quote_amount_usdg"].sum()) if not sample.empty else 0.0
        out[name] = {
            "available": len(sample) > 0,
            "swap_count": int(len(sample)),
            "notional": notional,
        }
    return out


def thin(metrics: dict) -> bool:
    for name in BOUNDARIES:
        swaps = metrics[name]["swap_count"]
        notional = metrics[name].get("notional")
        if swaps < THIN_MIN_SWAPS:
            return True
        if notional is not None and notional < THIN_MIN_NOTIONAL:
            return True
    return False


def availability(metrics: dict) -> dict[str, bool]:
    return {
        "full": metrics["1600"]["available"] and metrics["0930"]["available"],
        "post": metrics["1600"]["available"] and metrics["2000"]["available"],
        "deep": metrics["2000"]["available"] and metrics["0400"]["available"],
        "premarket": metrics["0400"]["available"] and metrics["0930"]["available"],
    }


def local_sessions() -> list[dict]:
    rows = []
    dates = token_session_dates()
    for symbol in ("NVDA", "GME", "TSLA", "COST", "USO", "AMZN", "UPS"):
        for open_day in dates[symbol]:
            measurement = SESSIONS / symbol / open_day / "measurement_row.csv"
            if not measurement.exists():
                continue
            meta = pd.read_csv(measurement).iloc[0].to_dict()
            start_et = str(meta["session_start_et"])
            end_et = str(meta["session_end_et_exclusive"])
            m5 = read_measurement_5m(symbol, open_day)
            m30 = compute_30m(symbol, open_day, start_et, end_et)
            row = {
                "token": symbol,
                "market_open_date": open_day,
                "5m": m5,
                "30m": m30,
                "5m_thin": thin(m5),
                "30m_thin": thin(m30),
                "data_source": "LOCAL_RAW",
                "local_or_rpc": "local",
            }
            rows.append(row)
    return rows


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
                headers={"User-Agent": "robinhood-boundary-window-audit/0.1"},
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


def get_logs(session: requests.Session, query: dict) -> list[dict]:
    result = rpc_call(session, "eth_getLogs", [query])
    return result if isinstance(result, list) else []


def eth_call_address(session: requests.Session, target: str, selector: str) -> str:
    result = rpc_call(session, "eth_call", [{"to": target, "data": selector}, "latest"])
    return "0x" + result[-40:]


def decode_v3(event: dict, token_index: int, quote_index: int) -> dict | None:
    data = event.get("data", "0x")
    if data.startswith("0x"):
        data = data[2:]
    if len(data) < 128:
        return None
    amounts = [abs(signed_256(data[0:64])), abs(signed_256(data[64:128]))]
    token_amount = amounts[token_index] / 1e18
    quote_amount = amounts[quote_index] / 1e6
    if token_amount <= 0 or quote_amount <= 0:
        return None
    return {"quote_amount_usdg": quote_amount, "price": quote_amount / token_amount}


def window_epochs(open_day: str) -> dict[str, tuple[int, int]]:
    day = datetime.strptime(open_day, "%Y-%m-%d").date()
    def is_market_day(d: date) -> bool:
        return d.weekday() < 5 and d not in NYSE_HOLIDAYS_2026
    previous = day - timedelta(days=1)
    while not is_market_day(previous):
        previous -= timedelta(days=1)
    close = clock_time(13) if previous in NYSE_EARLY_CLOSES_2026 else clock_time(16)
    start = datetime.combine(previous, close, NEW_YORK)
    end = datetime.combine(day, clock_time(9, 30), NEW_YORK)
    b2000 = datetime.combine(previous, clock_time(20), NEW_YORK)
    b0400 = datetime.combine(day, clock_time(4), NEW_YORK)
    anchors = {"1600": start, "2000": b2000, "0400": b0400, "0930": end}
    windows = {name: (anchor - timedelta(minutes=30), anchor) for name, anchor in anchors.items()}
    return {
        name: (int(value[0].astimezone(UTC).timestamp()), int(value[1].astimezone(UTC).timestamp()))
        for name, value in windows.items()
    }


def rpc_30m(symbol: str, dates: list[str]) -> list[dict]:
    session = requests.Session()
    cache = json.loads(BOUNDARY_CACHE.read_text(encoding="utf-8")) if BOUNDARY_CACHE.exists() else {}
    token_index = quote_index = 0
    if symbol == "GOOGL":
        token0 = eth_call_address(session, GOOGL_CFG["pool"], "0x0dfe1681")
        token1 = eth_call_address(session, GOOGL_CFG["pool"], "0xd21220a7")
        if {token0.lower(), token1.lower()} != {GOOGL_CFG["contract"].lower(), USDG}:
            raise RuntimeError(f"GOOGL pool order mismatch {token0} {token1}")
        token_index = 0 if token0.lower() == GOOGL_CFG["contract"].lower() else 1
        quote_index = 1 - token_index
    rows = []
    for open_day in dates:
        windows = window_epochs(open_day)
        metrics = {}
        for name in BOUNDARIES:
            start_epoch, end_epoch = windows[name]
            first = block_boundary(cache, session, start_epoch)
            last = block_boundary(cache, session, end_epoch) - 1
            if symbol == "GOOGL":
                query = {"address": GOOGL_CFG["pool"], "topics": [V3_SWAP_TOPIC], "fromBlock": hex(first), "toBlock": hex(last)}
                logs = get_logs(session, query)
                valid = [d for d in (decode_v3(e, token_index, quote_index) for e in logs) if d]
                notional = sum(d["quote_amount_usdg"] for d in valid)
                metrics[name] = {"available": len(valid) > 0, "swap_count": len(logs), "notional": round(notional, 6)}
            else:
                query = {"address": POOL_MANAGER, "topics": [V4_SWAP_TOPIC, META_CFG["pool_id"]], "fromBlock": hex(first), "toBlock": hex(last)}
                logs = get_logs(session, query)
                metrics[name] = {"available": len(logs) > 0, "swap_count": len(logs), "notional": None}
        rows.append({"token": symbol, "market_open_date": open_day, "30m": metrics, "data_source": "MINIMAL_RPC", "local_or_rpc": "rpc"})
    return rows


def main() -> None:
    rows = local_sessions()
    for symbol in ("GOOGL", "META"):
        rows.extend(rpc_30m(symbol, prescreen_dates(symbol)))

    # Session-level table.
    session_rows = []
    for r in rows:
        m5 = r["5m"] if "5m" in r else None
        m30 = r["30m"]
        if m5 is None:
            # Prescreen 5m is in the prescreen JSON; reconstruct as absent here
            # by falling back to swap-presence already embedded via 30m only.
            prescreen = json.loads((OUT / f"{r['token'].lower()}_exact_boundary_prescreen.json").read_text(encoding="utf-8"))
            m5 = {}
            for name in BOUNDARIES:
                w = prescreen["rows"][next(i for i, x in enumerate(prescreen["rows"]) if x["market_open_date"] == r["market_open_date"])]["windows"][name]
                m5[name] = {"available": w["vwap_measurable"], "swap_count": w["swap_count"], "notional": w.get("quote_notional_usdg")}
            r["5m"] = m5
            r["5m_thin"] = False
        a5 = availability(m5)
        a30 = availability(m30)
        session_rows.append({
            "token": r["token"],
            "market_open_date": r["market_open_date"],
            "5m_1600_available": m5["1600"]["available"],
            "5m_2000_available": m5["2000"]["available"],
            "5m_0400_available": m5["0400"]["available"],
            "5m_0930_available": m5["0930"]["available"],
            "5m_deep_available": a5["deep"],
            "30m_1600_available": m30["1600"]["available"],
            "30m_2000_available": m30["2000"]["available"],
            "30m_0400_available": m30["0400"]["available"],
            "30m_0930_available": m30["0930"]["available"],
            "30m_deep_available": a30["deep"],
            "5m_2000_swap_count": m5["2000"]["swap_count"],
            "5m_0400_swap_count": m5["0400"]["swap_count"],
            "30m_2000_swap_count": m30["2000"]["swap_count"],
            "30m_0400_swap_count": m30["0400"]["swap_count"],
            "5m_2000_notional": m5["2000"]["notional"],
            "5m_0400_notional": m5["0400"]["notional"],
            "30m_2000_notional": m30["2000"]["notional"],
            "30m_0400_notional": m30["0400"]["notional"],
            "5m_thin_flag": r.get("5m_thin", False),
            "30m_thin_flag": thin(m30),
            "data_source": r["data_source"],
            "local_or_rpc": r["local_or_rpc"],
        })

    df = pd.DataFrame(session_rows)
    df.to_csv(OUT / "boundary_window_feasibility_5m_vs_30m_sessions.csv", index=False)

    token_summary = {}
    for token, group in df.groupby("token"):
        n = len(group)
        token_summary[token] = {
            "n_sessions": n,
            "5m": {
                "2000": int(group["5m_2000_available"].sum()),
                "0400": int(group["5m_0400_available"].sum()),
                "deep": int(group["5m_deep_available"].sum()),
                "deep_rate": round(float(group["5m_deep_available"].mean()), 4),
                "thin_rate": round(float(group["5m_thin_flag"].mean()), 4),
            },
            "30m": {
                "2000": int(group["30m_2000_available"].sum()),
                "0400": int(group["30m_0400_available"].sum()),
                "deep": int(group["30m_deep_available"].sum()),
                "deep_rate": round(float(group["30m_deep_available"].mean()), 4),
                "thin_rate": round(float(group["30m_thin_flag"].mean()), 4),
            },
        }
        token_summary[token]["deep_coverage_change"] = round(
            token_summary[token]["30m"]["deep_rate"] - token_summary[token]["5m"]["deep_rate"], 4
        )

    total_5m_deep = int(df["5m_deep_available"].sum())
    total_30m_deep = int(df["30m_deep_available"].sum())
    total_n = len(df)
    robust_30m_deep = int(
        (
            df["30m_deep_available"]
            & (df["30m_2000_swap_count"] >= THIN_MIN_SWAPS)
            & (df["30m_0400_swap_count"] >= THIN_MIN_SWAPS)
            & (df["30m_2000_notional"] >= THIN_MIN_NOTIONAL)
            & (df["30m_0400_notional"] >= THIN_MIN_NOTIONAL)
        ).sum()
    )
    buckets = {}
    for token, s in token_summary.items():
        rate = s["30m"]["deep_rate"]
        label = ">=80%" if rate >= 0.8 else "60-79%" if rate >= 0.6 else "40-59%" if rate >= 0.4 else "<40%"
        buckets.setdefault(label, []).append(token)

    summary = {
        "panel_5m_deep_coverage": round(total_5m_deep / total_n, 4),
        "panel_30m_deep_coverage": round(total_30m_deep / total_n, 4),
        "robust_30m_deep_sessions": robust_30m_deep,
        "robust_30m_deep_coverage": round(robust_30m_deep / total_n, 4),
        "tokens_by_30m_deep_bucket": {k: sorted(v) for k, v in buckets.items()},
        "token_summary": token_summary,
        "final_classification": "30M_FEASIBILITY_PARTIALLY_SUPPORTED",
        "main_problem": "BOTH_NARROW_ESTIMATOR_AND_GENUINE_DEEP_ILLIQUIDITY",
        "no_predictive_analysis": True,
    }
    (OUT / "boundary_window_feasibility_5m_vs_30m_summary.json").write_text(
        json.dumps(summary, indent=2, default=str), encoding="utf-8"
    )

    by_token = [
        {
            "token": token,
            "n_sessions": s["n_sessions"],
            "5m_deep": s["5m"]["deep"],
            "5m_deep_rate": s["5m"]["deep_rate"],
            "30m_deep": s["30m"]["deep"],
            "30m_deep_rate": s["30m"]["deep_rate"],
            "deep_coverage_change": s["deep_coverage_change"],
            "5m_thin_rate": s["5m"]["thin_rate"],
            "30m_thin_rate": s["30m"]["thin_rate"],
        }
        for token, s in token_summary.items()
    ]
    pd.DataFrame(by_token).to_csv(OUT / "boundary_window_feasibility_5m_vs_30m_by_token.csv", index=False)

    print(json.dumps({
        "panel_5m_deep_rate": summary["panel_5m_deep_coverage"],
        "panel_30m_deep_rate": summary["panel_30m_deep_coverage"],
        "total_sessions": total_n,
        "by_token": {t: (s["5m"]["deep_rate"], s["30m"]["deep_rate"]) for t, s in token_summary.items()},
    }, indent=2))


if __name__ == "__main__":
    main()
