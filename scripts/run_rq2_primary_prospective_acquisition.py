from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import statistics
import sys
import time
from collections import Counter
from datetime import date, datetime, time as dt_time, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import requests


ROOT = Path(__file__).resolve().parents[1]
DESIGN_DIR = ROOT / "reports" / "robinhood_chain_pilot" / "rq2_information_content_design"
CACHE_ROOT = ROOT / "data" / "cache" / "alpaca_rq2_primary"
MANIFEST_PATH = DESIGN_DIR / "rq2_underlying_stock_acquisition_manifest.json"
POLICY_PATH = DESIGN_DIR / "rq2_alpaca_trade_condition_policy_draft.csv"
BRIDGE_PATH = DESIGN_DIR / "rq2_price_free_row_level_eligibility.csv"
REPORT_JSON_PATH = DESIGN_DIR / "rq2_primary_prospective_acquisition_report.json"
NY = ZoneInfo("America/New_York")
API_ROOT = "https://data.alpaca.markets"
PRIMARY_CODES = {"NVDA": "Q", "GME": "N", "COST": "Q"}
PRIMARY_NAMES = {"NVDA": "NASDAQ OMX", "GME": "New York Stock Exchange", "COST": "NASDAQ OMX"}
EXPECTED_FIELDS = {"c", "i", "p", "s", "t", "x", "z"}
IDENTITY_TOLERANCE = 1e-12
PINNED_XNYS_SESSIONS = [
    "2026-07-21", "2026-07-22", "2026-07-23", "2026-07-24", "2026-07-27",
    "2026-07-28", "2026-07-29", "2026-07-30", "2026-07-31", "2026-08-03",
    "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07", "2026-08-10",
    "2026-08-11", "2026-08-12", "2026-08-13", "2026-08-14", "2026-08-17",
    "2026-08-18", "2026-08-19", "2026-08-20", "2026-08-21", "2026-08-24",
    "2026-08-25", "2026-08-26", "2026-08-27", "2026-08-28", "2026-08-31",
    "2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
]


def load_env_credentials() -> tuple[str, str]:
    values: dict[str, str] = {}
    env_path = ROOT / ".env"
    if not env_path.exists():
        raise RuntimeError("PROJECT_ROOT_ENV_MISSING")
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in {"APCA_API_KEY_ID", "APCA_API_SECRET_KEY"}:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        values[name] = value
    if not values.get("APCA_API_KEY_ID") or not values.get("APCA_API_SECRET_KEY"):
        raise RuntimeError("ALPACA_CREDENTIALS_ABSENT")
    return values["APCA_API_KEY_ID"], values["APCA_API_SECRET_KEY"]


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
    tmp.replace(path)


def parse_timestamp(value: str) -> datetime:
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    if "." in text:
        head, tail = text.split(".", 1)
        offset_pos = max(tail.find("+"), tail.find("-"))
        if offset_pos >= 0:
            fraction, offset = tail[:offset_pos], tail[offset_pos:]
            text = f"{head}.{fraction[:6]}{offset}"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def request_end_inclusive(end_exclusive: datetime) -> str:
    prior_second = end_exclusive.astimezone(timezone.utc) - timedelta(seconds=1)
    return prior_second.strftime("%Y-%m-%dT%H:%M:%S") + ".999999999Z"


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def count_cached_requests() -> int:
    count = 0
    exchange_path = CACHE_ROOT / "exchange_metadata.json"
    if exchange_path.exists():
        count += 1
    actions_path = CACHE_ROOT / "corporate_actions_all.json"
    if actions_path.exists():
        count += len(json.loads(actions_path.read_text(encoding="utf-8")).get("requests", []))
    for metadata_path in CACHE_ROOT.glob("*/*/*_metadata.json"):
        count += len(json.loads(metadata_path.read_text(encoding="utf-8")).get("requests", []))
    return count


class AlpacaClient:
    def __init__(self, key: str, secret: str, pause_seconds: float) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
            "User-Agent": "rq2-primary-prospective-acquisition/1.0",
        })
        self.pause_seconds = pause_seconds
        self.request_count = 0

    def get(self, route: str, params: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        safe_params = {key: value for key, value in params.items() if value is not None}
        last_error: Exception | None = None
        for attempt in range(1, 6):
            try:
                response = self.session.get(API_ROOT + route, params=safe_params, timeout=(10, 45))
                self.request_count += 1
                if response.status_code == 429 or 500 <= response.status_code < 600:
                    if attempt == 5:
                        response.raise_for_status()
                    retry_after = float(response.headers.get("Retry-After", 0) or 0)
                    time.sleep(max(retry_after, min(2 ** attempt, 20)))
                    continue
                response.raise_for_status()
                payload = response.json()
                metadata = {
                    "route": route,
                    "params": safe_params,
                    "http_status": response.status_code,
                    "request_id": response.headers.get("X-Request-ID") or response.headers.get("Apca-Request-Id") or "",
                }
                time.sleep(self.pause_seconds)
                return payload, metadata
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == 5:
                    raise
                time.sleep(min(2 ** attempt, 20))
        raise RuntimeError(str(last_error))


def load_authorized_manifest() -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    rows = [
        row for row in manifest["rows"]
        if row["candidate_for_stock_acquisition"] is True
        and row["sample_role"] == "PROSPECTIVE_EXTENSION"
        and row["primary_inferential_row"] is True
    ]
    keys = [(row["token"], row["market_open_date"]) for row in rows]
    if len(rows) != 60 or len(set(keys)) != len(rows):
        raise RuntimeError("MANIFEST_MEMBERSHIP_INTEGRITY_FAILURE")
    if Counter(row["token"] for row in rows) != Counter({"NVDA": 13, "GME": 29, "COST": 18}):
        raise RuntimeError("MANIFEST_ASSET_COUNT_FAILURE")
    return manifest, rows


def validate_calendar(row: dict[str, Any]) -> None:
    current = row["market_open_date"]
    if current not in PINNED_XNYS_SESSIONS:
        raise RuntimeError("CALENDAR_MAPPING_FAILURE")
    index = PINNED_XNYS_SESSIONS.index(current)
    if index == 0 or PINNED_XNYS_SESSIONS[index - 1] != row["previous_trading_date"]:
        raise RuntimeError("CALENDAR_MAPPING_FAILURE")
    market_date = date.fromisoformat(current)
    p20_date = market_date - timedelta(days=1)
    expected_start = datetime.combine(p20_date, dt_time(19, 30), NY)
    expected_end = datetime.combine(p20_date, dt_time(20, 0), NY)
    if parse_timestamp(row["p20_start_utc"]) != expected_start.astimezone(timezone.utc):
        raise RuntimeError("CALENDAR_MAPPING_FAILURE")
    if parse_timestamp(row["p20_end_utc"]) != expected_end.astimezone(timezone.utc):
        raise RuntimeError("CALENDAR_MAPPING_FAILURE")


def load_condition_policy() -> tuple[dict[str, str], str]:
    mapping: dict[str, str] = {}
    with POLICY_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw_codes = row["condition_code"].strip()
            category = row["include_exclude_special"].strip()
            if raw_codes == "UNKNOWN" or raw_codes == "NOT_IN_HISTORICAL_SCHEMA":
                continue
            normalized_category = (
                "INCLUDE" if category == "INCLUDE"
                else "SPECIAL_HANDLING" if category == "SPECIAL_HANDLING"
                else "EXCLUDE" if category.startswith("EXCLUDE")
                else "REVIEW_REQUIRED"
            )
            for code in (part.strip() for part in raw_codes.split("/")):
                mapping[code] = normalized_category
    return mapping, sha256_file(POLICY_PATH)


def flatten_exchange_records(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        if value and all(isinstance(key, str) and isinstance(name, str) for key, name in value.items()):
            return [{"code": code, "name": name} for code, name in value.items()]
        direct = [value] if "code" in value and "name" in value else []
        nested: list[dict[str, Any]] = []
        for child in value.values():
            nested.extend(flatten_exchange_records(child))
        return direct + nested
    return []


def flatten_corporate_actions(payload: dict[str, Any]) -> list[dict[str, Any]]:
    root = payload.get("corporate_actions", payload)
    records: list[dict[str, Any]] = []
    if isinstance(root, list):
        return [dict(item) for item in root if isinstance(item, dict)]
    if isinstance(root, dict):
        for action_type, items in root.items():
            if not isinstance(items, list):
                continue
            for item in items:
                if isinstance(item, dict):
                    record = dict(item)
                    record.setdefault("type", action_type)
                    records.append(record)
    return records


def symbol_of_action(record: dict[str, Any]) -> str:
    for key in ("symbol", "old_symbol", "initiating_symbol"):
        if record.get(key):
            return str(record[key]).upper()
    return ""


def effective_date_of_action(record: dict[str, Any]) -> str:
    for key in ("effective_date", "ex_date", "execution_date"):
        if record.get(key):
            return str(record[key])[:10]
    return ""


def fetch_paged_trades(
    client: AlpacaClient,
    ticker: str,
    start: datetime,
    end_exclusive: datetime,
    cache_dir: Path,
    label: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    page = 0
    token: str | None = None
    records: list[dict[str, Any]] = []
    requests_meta: list[dict[str, Any]] = []
    while True:
        page += 1
        params = {
            "symbols": ticker,
            "start": iso_z(start),
            "end": request_end_inclusive(end_exclusive),
            "limit": 10000,
            "feed": "sip",
            "sort": "asc",
            "page_token": token,
        }
        payload, metadata = client.get("/v2/stocks/trades", params)
        atomic_json(cache_dir / f"{label}_page_{page:03d}.json", payload)
        requests_meta.append(metadata)
        page_records = payload.get("trades", {}).get(ticker, [])
        if not isinstance(page_records, list):
            raise RuntimeError("ALPACA_TRADE_SCHEMA_MISMATCH")
        records.extend(page_records)
        token = payload.get("next_page_token")
        if not token:
            break
        if page >= 500:
            raise RuntimeError("PAGINATION_SAFETY_LIMIT")
    metadata = {
        "label": label,
        "start_utc": iso_z(start),
        "end_exclusive_utc": iso_z(end_exclusive),
        "request_end_inclusive": request_end_inclusive(end_exclusive),
        "pages": page,
        "pagination_complete": token is None or token == "",
        "returned_rows": len(records),
        "requests": requests_meta,
    }
    return records, metadata


def normalize_trade(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "conditions": list(record.get("c") or []),
        "trade_id": str(record.get("i", "")),
        "price": record.get("p"),
        "size": record.get("s"),
        "timestamp": record.get("t"),
        "exchange": record.get("x"),
        "tape": record.get("z"),
    }


def normalize_condition_codes(conditions: list[Any]) -> list[str]:
    if not conditions:
        return ["SPACE"]
    return ["SPACE" if not str(code).strip() else str(code).strip() for code in conditions]


def classify_trade(record: dict[str, Any], condition_policy: dict[str, str]) -> tuple[str, list[str]]:
    codes = normalize_condition_codes(list(record.get("c") or []))
    unknown = [code for code in codes if code not in condition_policy]
    if unknown:
        return "REVIEW_REQUIRED", unknown
    categories = {condition_policy[code] for code in codes}
    if "EXCLUDE" in categories:
        return "EXCLUDE", []
    if "REVIEW_REQUIRED" in categories:
        return "REVIEW_REQUIRED", []
    if "SPECIAL_HANDLING" in categories:
        return "SPECIAL_HANDLING", []
    return "INCLUDE", []


def analyze_trade_window(
    raw_records: list[dict[str, Any]],
    start: datetime,
    end_exclusive: datetime,
    condition_policy: dict[str, str],
) -> dict[str, Any]:
    normalized = [normalize_trade(record) for record in raw_records]
    missing_fields = sum(1 for record in raw_records if not EXPECTED_FIELDS.issubset(record))
    aware = True
    inside = True
    nonpositive = 0
    unknown_codes: set[str] = set()
    condition_counts: Counter[str] = Counter()
    exchange_counts: Counter[str] = Counter()
    included: list[tuple[dict[str, Any], datetime, float, float, float]] = []
    ids: list[str] = []
    for raw, record in zip(raw_records, normalized):
        try:
            timestamp = parse_timestamp(str(record["timestamp"]))
        except Exception:
            aware = False
            continue
        if not (start <= timestamp < end_exclusive):
            inside = False
        try:
            price = float(record["price"])
            size = float(record["size"])
        except (TypeError, ValueError):
            nonpositive += 1
            continue
        if not math.isfinite(price) or not math.isfinite(size) or price <= 0 or size <= 0:
            nonpositive += 1
            continue
        classification, unknown = classify_trade(raw, condition_policy)
        unknown_codes.update(unknown)
        for code in normalize_condition_codes(list(raw.get("c") or [])):
            condition_counts[code] += 1
        exchange_counts[str(raw.get("x", ""))] += 1
        ids.append(str(raw.get("i", "")))
        if classification in {"INCLUDE", "SPECIAL_HANDLING"} and not unknown:
            included.append((raw, timestamp, price, size, price * size))
    duplicate_ids = len(ids) - len(set(ids))
    trade_count = len(included)
    share_volume = sum(item[3] for item in included)
    notional = sum(item[4] for item in included)
    vwap = notional / share_volume if share_volume > 0 else None
    timestamps = [item[1] for item in included]
    prices = [item[2] for item in included]
    notionals = [item[4] for item in included]
    median_price = statistics.median(prices) if prices else None
    max_abs = max((abs(price - median_price) for price in prices), default=None) if median_price is not None else None
    max_pct = max_abs / median_price if median_price and max_abs is not None else None
    last_age = (end_exclusive - max(timestamps)).total_seconds() if timestamps else None
    max_notional = max(notionals, default=None)
    hard_gates = {
        "exact_interval_requested": True,
        "pagination_complete": True,
        "all_rows_inside_interval": inside,
        "timestamps_timezone_aware": aware,
        "all_conditions_classified": not unknown_codes,
        "minimum_5_executions": trade_count >= 5,
        "minimum_100_shares": share_volume >= 100,
        "minimum_10000_notional": notional >= 10000,
        "finite_positive_vwap": vwap is not None and math.isfinite(vwap) and vwap > 0,
    }
    return {
        "normalized": normalized,
        "raw_trade_count": len(raw_records),
        "eligible_trade_count": trade_count,
        "eligible_share_volume": share_volume,
        "eligible_notional": notional,
        "vwap": vwap,
        "first_trade_time": iso_z(min(timestamps)) if timestamps else "",
        "last_trade_time": iso_z(max(timestamps)) if timestamps else "",
        "last_trade_age_seconds": last_age,
        "max_single_trade_notional": max_notional,
        "max_single_trade_notional_share": max_notional / notional if max_notional is not None and notional > 0 else None,
        "median_trade_price": median_price,
        "max_abs_price_deviation_from_median": max_abs,
        "max_abs_pct_price_deviation_from_median": max_pct,
        "condition_code_counts": dict(sorted(condition_counts.items())),
        "exchange_counts": dict(sorted(exchange_counts.items())),
        "duplicate_trade_id_count": duplicate_ids,
        "missing_required_trade_field_count": missing_fields,
        "nonpositive_price_or_size_count": nonpositive,
        "unknown_condition_codes": sorted(unknown_codes),
        "hard_gates": hard_gates,
        "p20_quality_ok": all(hard_gates.values()),
        "staleness_warning": last_age is not None and last_age > 60,
        "anomaly_review_required": duplicate_ids > 0 or missing_fields > 0 or nonpositive > 0,
    }


def official_record(
    records: list[dict[str, Any]],
    condition: str,
    primary_code: str,
    start: datetime,
    end_exclusive: datetime,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    normalized = [normalize_trade(record) for record in records]
    qualifying: list[dict[str, Any]] = []
    for raw, norm in zip(records, normalized):
        try:
            timestamp = parse_timestamp(str(norm["timestamp"]))
            price = float(norm["price"])
            size = float(norm["size"])
        except (TypeError, ValueError):
            continue
        if start <= timestamp < end_exclusive and raw.get("x") == primary_code and condition in (raw.get("c") or []) and price > 0 and size > 0:
            qualifying.append(norm)
    return normalized, qualifying


def action_for_row(actions: list[dict[str, Any]], ticker: str, previous_date: str, market_date: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for record in actions:
        if symbol_of_action(record) != ticker:
            continue
        effective = effective_date_of_action(record)
        if effective and previous_date < effective <= market_date:
            matches.append(record)
    return matches


def reason_list(result: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    if not result.get("calendar_ok", False): reasons.append("CALENDAR_MAPPING_FAILURE")
    if result.get("corporate_action_exclusion", False): reasons.append("CORPORATE_ACTION_CROSSES_OVERNIGHT_INTERVAL")
    p20 = result.get("p20", {})
    gates = p20.get("hard_gates", {})
    if not gates.get("minimum_5_executions", False): reasons.append("P20_INSUFFICIENT_ELIGIBLE_TRADES")
    if not gates.get("minimum_100_shares", False): reasons.append("P20_INSUFFICIENT_SHARES")
    if not gates.get("minimum_10000_notional", False): reasons.append("P20_INSUFFICIENT_NOTIONAL")
    if p20.get("unknown_condition_codes"): reasons.append("UNKNOWN_TRADE_CONDITION")
    if result.get("open_record_count") == 0: reasons.append("MISSING_OFFICIAL_OPEN")
    elif result.get("open_record_count") != 1: reasons.append("AMBIGUOUS_OFFICIAL_OPEN")
    if result.get("close_record_count") == 0: reasons.append("MISSING_OFFICIAL_CLOSE")
    elif result.get("close_record_count") != 1: reasons.append("AMBIGUOUS_OFFICIAL_CLOSE")
    if not result.get("price_basis_consistent", False): reasons.append("PRICE_BASIS_INCONSISTENT")
    if result.get("return_identity_ok") is False: reasons.append("RETURN_IDENTITY_FAILURE")
    if p20.get("anomaly_review_required", False): reasons.append("ANOMALY_REQUIRES_REVIEW")
    if result.get("retrieval_error"): reasons.append("SOURCE_RETRIEVAL_FAILURE")
    return list(dict.fromkeys(reasons))


def process_row(
    client: AlpacaClient,
    row: dict[str, Any],
    condition_policy: dict[str, str],
    condition_policy_sha: str,
    actions: list[dict[str, Any]],
    exchange_names: dict[str, str],
    reprocess_cache: bool = False,
) -> dict[str, Any]:
    ticker = row["token"]
    market_date = date.fromisoformat(row["market_open_date"])
    previous_date = date.fromisoformat(row["previous_trading_date"])
    row_dir = CACHE_ROOT / ticker / row["market_open_date"]
    checkpoint = row_dir / "row_result.json"
    if checkpoint.exists():
        existing = json.loads(checkpoint.read_text(encoding="utf-8"))
        if existing.get("checkpoint_status") == "COMPLETE" and not reprocess_cache:
            return existing
        if existing.get("checkpoint_status") == "COMPLETE" and reprocess_cache:
            normalized_path = row_dir / "p20_trades_normalized.jsonl"
            metadata_path = row_dir / "p20_metadata.json"
            normalized = [json.loads(line) for line in normalized_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            raw_records = [
                {"c": item["conditions"], "i": item["trade_id"], "p": item["price"], "s": item["size"], "t": item["timestamp"], "x": item["exchange"], "z": item["tape"]}
                for item in normalized
            ]
            p20_start = parse_timestamp(row["p20_start_utc"])
            p20_end = parse_timestamp(row["p20_end_utc"])
            p20 = analyze_trade_window(raw_records, p20_start, p20_end, condition_policy)
            p20.pop("normalized")
            p20_meta = json.loads(metadata_path.read_text(encoding="utf-8"))
            p20["hard_gates"]["pagination_complete"] = p20_meta["pagination_complete"]
            p20["p20_quality_ok"] = all(p20["hard_gates"].values())
            existing["p20"] = p20
            existing["stock_p20"] = p20["vwap"] if p20["p20_quality_ok"] else None
            prices = (existing.get("stock_prev_close"), existing.get("stock_p20"), existing.get("stock_open"))
            if all(value is not None and math.isfinite(value) and value > 0 for value in prices):
                previous_close, p20_value, stock_open = prices
                existing["stock_post_return"] = math.log(p20_value / previous_close)
                existing["stock_20_to_open_return"] = math.log(stock_open / p20_value)
                existing["stock_total_open_gap"] = math.log(stock_open / previous_close)
                existing["return_identity_error"] = abs(existing["stock_total_open_gap"] - existing["stock_post_return"] - existing["stock_20_to_open_return"])
                existing["return_identity_ok"] = existing["return_identity_error"] <= IDENTITY_TOLERANCE
            else:
                existing.update({"stock_post_return": None, "stock_20_to_open_return": None, "stock_total_open_gap": None, "return_identity_error": None, "return_identity_ok": None})
            existing["trade_condition_ok"] = not p20["unknown_condition_codes"]
            existing["review_required"] = bool(
                p20["unknown_condition_codes"]
                or p20["anomaly_review_required"]
                or p20["staleness_warning"]
                or existing.get("open_quality_ok") is not True
                or existing.get("close_quality_ok") is not True
                or existing.get("calendar_ok") is not True
                or existing.get("return_identity_ok") is False
                or existing.get("retrieval_error")
            )
            existing["exclusion_reasons"] = reason_list(existing)
            existing["primary_stock_row_ok"] = (
                existing.get("calendar_ok") is True
                and not existing.get("corporate_action_exclusion", False)
                and p20["p20_quality_ok"]
                and existing.get("open_quality_ok") is True
                and existing.get("close_quality_ok") is True
                and existing.get("price_basis_consistent") is True
                and existing.get("return_identity_ok") is True
                and existing["trade_condition_ok"]
                and not p20["anomaly_review_required"]
            )
            atomic_json(checkpoint, existing)
            return existing
    row_dir.mkdir(parents=True, exist_ok=True)
    base = {
        "checkpoint_status": "STARTED",
        "token": ticker,
        "stock_ticker": ticker,
        "market_open_date": row["market_open_date"],
        "previous_trading_date": row["previous_trading_date"],
        "token_deep_robust": row["token_deep_robust"],
        "prior_outcome_exposure": row["prior_outcome_exposure"],
        "sample_role": row["sample_role"],
        "primary_inferential_row": row["primary_inferential_row"],
        "candidate_for_stock_acquisition": row["candidate_for_stock_acquisition"],
        "acquisition_mode": "PRIMARY_PROSPECTIVE_ACQUISITION",
        "source": "Alpaca Historical Market Data API",
        "feed": "sip",
        "price_basis": "RAW_CONTEMPORANEOUS_MARKET_PRICES",
        "condition_mapping_sha256": condition_policy_sha,
        "calendar_ok": False,
        "primary_exchange_code": PRIMARY_CODES[ticker],
        "primary_exchange_name": exchange_names[PRIMARY_CODES[ticker]],
    }
    atomic_json(checkpoint, base)
    try:
        validate_calendar(row)
        base["calendar_ok"] = True
        row_actions = action_for_row(actions, ticker, row["previous_trading_date"], row["market_open_date"])
        atomic_json(row_dir / "corporate_actions.json", {"source": "/v1/corporate-actions", "records": row_actions})
        base.update({
            "corporate_action_flag": bool(row_actions),
            "corporate_action_type": "|".join(sorted({str(item.get("type", "")) for item in row_actions if item.get("type")})),
            "corporate_action_effective_date": "|".join(sorted({effective_date_of_action(item) for item in row_actions if effective_date_of_action(item)})),
            "corporate_action_source": "Alpaca /v1/corporate-actions plus frozen pre-acquisition source review",
            "corporate_action_exclusion": bool(row_actions),
        })

        p20_start = parse_timestamp(row["p20_start_utc"])
        p20_end = parse_timestamp(row["p20_end_utc"])
        p20_raw, p20_meta = fetch_paged_trades(client, ticker, p20_start, p20_end, row_dir, "p20")
        p20 = analyze_trade_window(p20_raw, p20_start, p20_end, condition_policy)
        p20["hard_gates"]["pagination_complete"] = p20_meta["pagination_complete"]
        p20["p20_quality_ok"] = all(p20["hard_gates"].values())
        jsonl(row_dir / "p20_trades_normalized.jsonl", p20.pop("normalized"))
        atomic_json(row_dir / "p20_metadata.json", p20_meta)
        base["p20"] = p20

        open_start = datetime.combine(market_date, dt_time(9, 29), NY).astimezone(timezone.utc)
        open_end = datetime.combine(market_date, dt_time(9, 31), NY).astimezone(timezone.utc)
        open_raw, open_meta = fetch_paged_trades(client, ticker, open_start, open_end, row_dir, "open")
        open_normalized, open_qualifying = official_record(open_raw, "Q", PRIMARY_CODES[ticker], open_start, open_end)
        jsonl(row_dir / "open_trades_normalized.jsonl", open_normalized)
        atomic_json(row_dir / "open_metadata.json", open_meta)
        atomic_json(row_dir / "open_official_records.json", open_qualifying)

        close_start = datetime.combine(previous_date, dt_time(15, 59), NY).astimezone(timezone.utc)
        close_end = datetime.combine(previous_date, dt_time(16, 1), NY).astimezone(timezone.utc)
        close_raw, close_meta = fetch_paged_trades(client, ticker, close_start, close_end, row_dir, "close")
        close_normalized, close_qualifying = official_record(close_raw, "M", PRIMARY_CODES[ticker], close_start, close_end)
        jsonl(row_dir / "close_trades_normalized.jsonl", close_normalized)
        atomic_json(row_dir / "close_metadata.json", close_meta)
        atomic_json(row_dir / "close_official_records.json", close_qualifying)

        base.update({
            "open_record_count": len(open_qualifying),
            "open_quality_ok": len(open_qualifying) == 1,
            "open_timestamp": open_qualifying[0]["timestamp"] if len(open_qualifying) == 1 else "",
            "open_exchange": open_qualifying[0]["exchange"] if len(open_qualifying) == 1 else "",
            "open_conditions": open_qualifying[0]["conditions"] if len(open_qualifying) == 1 else [],
            "stock_open": float(open_qualifying[0]["price"]) if len(open_qualifying) == 1 else None,
            "close_record_count": len(close_qualifying),
            "close_quality_ok": len(close_qualifying) == 1,
            "close_timestamp": close_qualifying[0]["timestamp"] if len(close_qualifying) == 1 else "",
            "close_exchange": close_qualifying[0]["exchange"] if len(close_qualifying) == 1 else "",
            "close_conditions": close_qualifying[0]["conditions"] if len(close_qualifying) == 1 else [],
            "stock_prev_close": float(close_qualifying[0]["price"]) if len(close_qualifying) == 1 else None,
            "stock_p20": p20["vwap"] if p20["p20_quality_ok"] else None,
            "price_basis_consistent": True,
        })
        prices = (base["stock_prev_close"], base["stock_p20"], base["stock_open"])
        if all(value is not None and math.isfinite(value) and value > 0 for value in prices):
            previous_close, p20_value, stock_open = prices
            base["stock_post_return"] = math.log(p20_value / previous_close)
            base["stock_20_to_open_return"] = math.log(stock_open / p20_value)
            base["stock_total_open_gap"] = math.log(stock_open / previous_close)
            base["return_identity_error"] = abs(base["stock_total_open_gap"] - base["stock_post_return"] - base["stock_20_to_open_return"])
            base["return_identity_ok"] = base["return_identity_error"] <= IDENTITY_TOLERANCE
        else:
            base.update({
                "stock_post_return": None,
                "stock_20_to_open_return": None,
                "stock_total_open_gap": None,
                "return_identity_error": None,
                "return_identity_ok": None,
            })
        base["trade_condition_ok"] = not p20["unknown_condition_codes"]
        base["review_required"] = bool(
            p20["unknown_condition_codes"]
            or p20["anomaly_review_required"]
            or p20["staleness_warning"]
            or base.get("open_quality_ok") is not True
            or base.get("close_quality_ok") is not True
            or base.get("calendar_ok") is not True
            or base.get("return_identity_ok") is False
            or base.get("retrieval_error")
        )
        base["exclusion_reasons"] = reason_list(base)
        base["primary_stock_row_ok"] = (
            base["calendar_ok"]
            and not base["corporate_action_exclusion"]
            and p20["p20_quality_ok"]
            and base["open_quality_ok"]
            and base["close_quality_ok"]
            and base["price_basis_consistent"]
            and base["return_identity_ok"] is True
            and base["trade_condition_ok"]
            and not p20["anomaly_review_required"]
        )
        base["checkpoint_status"] = "COMPLETE"
    except Exception as exc:
        base["retrieval_error"] = f"{type(exc).__name__}: {exc}"
        base.setdefault("corporate_action_flag", False)
        base.setdefault("corporate_action_type", "")
        base.setdefault("corporate_action_effective_date", "")
        base.setdefault("corporate_action_source", "Alpaca /v1/corporate-actions plus frozen pre-acquisition source review")
        base.setdefault("corporate_action_exclusion", False)
        base.setdefault("open_record_count", None)
        base.setdefault("open_quality_ok", False)
        base.setdefault("close_record_count", None)
        base.setdefault("close_quality_ok", False)
        base.setdefault("price_basis_consistent", False)
        base.setdefault("return_identity_ok", None)
        base["review_required"] = True
        base["exclusion_reasons"] = reason_list(base)
        base["primary_stock_row_ok"] = False
        base["checkpoint_status"] = "COMPLETE"
    atomic_json(checkpoint, base)
    return base


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pause-seconds", type=float, default=0.35)
    parser.add_argument("--max-rows", type=int, default=None)
    parser.add_argument("--reprocess-cache", action="store_true")
    args = parser.parse_args()
    key, secret = load_env_credentials()
    manifest, authorized_rows = load_authorized_manifest()
    if args.max_rows is not None:
        authorized_rows = authorized_rows[: args.max_rows]
    condition_policy, condition_sha = load_condition_policy()
    CACHE_ROOT.mkdir(parents=True, exist_ok=True)
    client = AlpacaClient(key, secret, args.pause_seconds)

    if args.reprocess_cache:
        cached_exchange = json.loads((CACHE_ROOT / "exchange_metadata.json").read_text(encoding="utf-8"))
        exchange_payload = cached_exchange["response"]
    else:
        exchange_payload, exchange_meta = client.get("/v2/stocks/meta/exchanges", {})
        atomic_json(CACHE_ROOT / "exchange_metadata.json", {"response": exchange_payload, "request": exchange_meta})
    exchange_records = flatten_exchange_records(exchange_payload)
    exchange_names = {str(record.get("code", "")): str(record.get("name", "")) for record in exchange_records}
    for ticker, code in PRIMARY_CODES.items():
        if code not in exchange_names:
            raise RuntimeError(f"PRIMARY_VENUE_UNRESOLVED_{ticker}")
        expected = PRIMARY_NAMES[ticker].lower()
        observed = exchange_names[code].lower()
        if ticker in {"NVDA", "COST"} and "nasdaq" not in observed:
            raise RuntimeError(f"PRIMARY_VENUE_CONFLICT_{ticker}")
        if ticker == "GME" and "new york" not in observed and observed != "nyse":
            raise RuntimeError("PRIMARY_VENUE_CONFLICT_GME")

    action_params = {
        "symbols": "NVDA,GME,COST",
        "start": "2026-07-14",
        "end": "2026-09-11",
        "region": "us",
        "data_quality": "complete",
        "limit": 1000,
        "sort": "asc",
    }
    if args.reprocess_cache:
        all_actions = json.loads((CACHE_ROOT / "corporate_actions_all.json").read_text(encoding="utf-8"))["records"]
    else:
        action_pages: list[dict[str, Any]] = []
        action_requests: list[dict[str, Any]] = []
        page_token: str | None = None
        while True:
            params = dict(action_params)
            if page_token:
                params["page_token"] = page_token
            payload, metadata = client.get("/v1/corporate-actions", params)
            action_pages.append(payload)
            action_requests.append(metadata)
            page_token = payload.get("next_page_token")
            if not page_token:
                break
        all_actions = []
        for payload in action_pages:
            all_actions.extend(flatten_corporate_actions(payload))
        atomic_json(CACHE_ROOT / "corporate_actions_all.json", {
            "requests": action_requests,
            "records": all_actions,
            "pagination_complete": not page_token,
        })

    results: list[dict[str, Any]] = []
    total = len(authorized_rows)
    for index, row in enumerate(authorized_rows, start=1):
        result = process_row(client, row, condition_policy, condition_sha, all_actions, exchange_names, args.reprocess_cache)
        results.append(result)
        complete = sum(item.get("checkpoint_status") == "COMPLETE" for item in results)
        passed = sum(item.get("primary_stock_row_ok") is True for item in results)
        review = sum(item.get("review_required") is True for item in results)
        print(f"progress={index}/{total} completed={complete} qa_pass={passed} review_required={review}", flush=True)

    expected_keys = {(row["token"], row["market_open_date"]) for row in authorized_rows}
    result_keys = {(row["token"], row["market_open_date"]) for row in results}
    if expected_keys != result_keys or len(results) != len(result_keys):
        raise RuntimeError("MANIFEST_COVERAGE_FAILURE")
    qa_pass = sum(row.get("primary_stock_row_ok") is True for row in results)
    qa_fail = total - qa_pass
    successful = sum(not row.get("retrieval_error") for row in results)
    p20_retrieved = sum("p20" in row and not row.get("retrieval_error") for row in results)
    p20_constructed = sum(row.get("p20", {}).get("vwap") is not None for row in results)
    p20_pass = sum(row.get("p20", {}).get("p20_quality_ok") is True for row in results)
    open_unique = sum(row.get("open_quality_ok") is True for row in results)
    close_unique = sum(row.get("close_quality_ok") is True for row in results)
    corporate_exclusions = sum(row.get("corporate_action_exclusion") is True for row in results)
    stale = sum(row.get("p20", {}).get("staleness_warning") is True for row in results)
    anomaly = sum(row.get("p20", {}).get("anomaly_review_required") is True for row in results)
    review = sum(row.get("review_required") is True for row in results)
    new_conditions = sorted({code for row in results for code in row.get("p20", {}).get("unknown_condition_codes", [])})
    reasons = Counter(reason for row in results for reason in row.get("exclusion_reasons", []))
    valid_identity = [row for row in results if row.get("return_identity_ok") is not None]
    prior_request_count = 0
    if args.reprocess_cache and REPORT_JSON_PATH.exists():
        prior_request_count = int(json.loads(REPORT_JSON_PATH.read_text(encoding="utf-8")).get("request_count", 0))
    report = {
        "artifact": "RQ2_PRIMARY_PROSPECTIVE_ACQUISITION_REPORT",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "acquisition_mode": "PRIMARY_PROSPECTIVE_ACQUISITION",
        "status": "COMPLETE" if qa_fail == 0 else "COMPLETE_WITH_QA_EXCLUSIONS",
        "counts": {
            "expected_manifest_rows": total,
            "attempted_rows": len(results),
            "successfully_acquired_rows": successful,
            "stock_p20_windows_retrieved_successfully": p20_retrieved,
            "stock_p20_anchors_constructed": p20_constructed,
            "p20_qa_pass_rows": p20_pass,
            "unique_official_open_rows": open_unique,
            "unique_official_close_rows": close_unique,
            "corporate_action_exclusions": corporate_exclusions,
            "staleness_warnings": stale,
            "anomaly_review_rows": anomaly,
            "primary_stock_row_ok": qa_pass,
            "qa_fail_rows": qa_fail,
            "review_required_rows": review,
        },
        "exclusion_reason_counts": dict(sorted(reasons.items())),
        "new_trade_condition_codes": new_conditions,
        "all_valid_rows_pass_return_identity": bool(valid_identity) and all(row["return_identity_ok"] for row in valid_identity),
        "valid_identity_row_count": len(valid_identity),
        "manifest_coverage_complete": expected_keys == result_keys,
        "discovery_rows_fetched": 0,
        "tsla_rows_fetched": 0,
        "request_count": client.request_count or prior_request_count or count_cached_requests(),
        "source_behavior_consistent_with_smoke_test": successful > 0 and p20_retrieved > 0,
        "correlation_calculated": False,
        "regression_run": False,
        "hypothesis_interpretation_performed": False,
        "cache_root": "data/cache/alpaca_rq2_primary",
        "output_artifacts": [
            "rq2_underlying_stock_price_qa.csv",
            "rq2_primary_prospective_aligned_panel.csv",
            "rq2_primary_prospective_acquisition_report.md",
            "rq2_primary_prospective_acquisition_report.json",
        ],
        "manifest_sha256": sha256_file(MANIFEST_PATH),
        "bridge_sha256": sha256_file(BRIDGE_PATH),
    }
    atomic_json(CACHE_ROOT / "acquisition_rows.json", {"rows": results})
    atomic_json(REPORT_JSON_PATH, report)
    print("acquisition_complete=" + report["status"], flush=True)
    print("summary_counts=" + json.dumps(report["counts"], sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"fatal_status={type(exc).__name__}:{exc}", file=sys.stderr, flush=True)
        raise
