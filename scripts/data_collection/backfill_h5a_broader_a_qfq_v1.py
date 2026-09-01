"""Simple resumable Sina QFQ downloader for the broader-A historical cache."""

from __future__ import annotations

import argparse
import csv
import json
import math
import os
import random
import re
import socket
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

START_DATE = "2020-12-28"
END_DATE = "2026-05-18"
SOURCE = "ak.stock_zh_a_daily(adjust=qfq)"
FETCH_BATCH_ID = "sina_broader_a_historical_v1"
MAX_ATTEMPTS_PER_PASS = 3
MAX_RETRY_PASSES = 2
CANONICAL_COLUMNS = ["stock_code", "trade_date", "qfq_close", "source", "fetch_batch_id"]
STATUS_COLUMNS = [
    "stock_code",
    "status",
    "attempts",
    "pass_index",
    "attempts_in_pass",
    "rows",
    "date_min",
    "date_max",
    "last_error",
    "error_type",
    "board",
    "feasibility_group",
]
REQUEST_COLUMNS = [
    "timestamp_utc",
    "stock_code",
    "pass_index",
    "attempt",
    "status",
    "elapsed_seconds",
    "error_type",
    "error",
]
TRANSIENT_TYPES = {
    "SSLError",
    "RemoteDisconnected",
    "ConnectionResetError",
    "ConnectionError",
    "ReadTimeout",
    "ConnectTimeout",
    "Timeout",
}


class DataQualityError(ValueError):
    pass


class SystemicStop(RuntimeError):
    pass


def code6(value: object) -> str:
    digits = "".join(ch for ch in str(value).strip().split(".")[0] if ch.isdigit())
    if not digits:
        raise ValueError(f"invalid stock code: {value!r}")
    return digits[-6:].zfill(6)


def board_of(code: str) -> str:
    code = code6(code)
    if code.startswith("688"):
        return "STAR"
    if code.startswith(("300", "301")):
        return "CHINEXT"
    if code.startswith("6"):
        return "SH_MAIN"
    return "SZ_MAIN"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def json_default(value: object) -> object:
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    item = getattr(value, "item", None)
    if callable(item):
        return item()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def paths(project_root: Path) -> tuple[Path, Path]:
    cache = project_root / "data" / "cache" / "h5a_broader_a_qfq_v1"
    return cache, cache / "_download"


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    """Publish only a fully closed, flushed and re-readable CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        with tmp.open("w", newline="", encoding="utf-8-sig") as handle:
            frame.to_csv(handle, index=False)
            handle.flush()
            os.fsync(handle.fileno())
        pd.read_csv(tmp)
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def load_universe(project_root: Path) -> list[str]:
    path = project_root / "data" / "processed" / "h5a_broader_a_universe_v1.csv"
    frame = pd.read_csv(path, dtype=str)
    if "universe_status" in frame:
        frame = frame.loc[frame["universe_status"].eq("INCLUDED")]
    codes = frame["stock_code"].map(code6).tolist()
    if len(codes) != 5195 or len(codes) != len(set(codes)):
        raise DataQualityError("expected 5,195 unique broader-A stock codes")
    return codes


def normalize_qfq(raw: pd.DataFrame, code: str) -> pd.DataFrame:
    if raw is None or raw.empty:
        raise DataQualityError("empty response")
    date_col = next((c for c in ("trade_date", "date", "日期") if c in raw), None)
    close_col = next((c for c in ("qfq_close", "close", "收盘") if c in raw), None)
    if date_col is None or close_col is None:
        raise DataQualityError("Sina response schema changed: missing date or qfq close")
    dates = pd.to_datetime(raw[date_col], errors="coerce")
    closes = pd.to_numeric(raw[close_col], errors="coerce")
    if dates.isna().any() or dates.duplicated().any():
        raise DataQualityError("trade_date must be parseable and unique")
    if closes.isna().any() or (~closes.map(math.isfinite)).any() or (closes <= 0).any():
        raise DataQualityError("qfq_close must be finite and positive")
    frame = pd.DataFrame({"trade_date": dates.dt.strftime("%Y-%m-%d"), "qfq_close": closes})
    frame = frame.loc[frame["trade_date"].between(START_DATE, END_DATE)].sort_values("trade_date")
    if frame.empty:
        raise DataQualityError("no rows inside required date range")
    frame.insert(0, "stock_code", code6(code))
    frame["source"] = SOURCE
    frame["fetch_batch_id"] = FETCH_BATCH_ID
    frame = frame[CANONICAL_COLUMNS].reset_index(drop=True)
    validate_file(frame, code)
    return frame


def validate_file(frame: pd.DataFrame, code: str) -> None:
    if list(frame.columns) != CANONICAL_COLUMNS or frame.empty:
        raise DataQualityError("canonical schema mismatch or empty file")
    if set(frame["stock_code"].astype(str).map(code6)) != {code6(code)}:
        raise DataQualityError("stock code mismatch")
    dates = pd.to_datetime(frame["trade_date"], errors="coerce")
    values = pd.to_numeric(frame["qfq_close"], errors="coerce")
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise DataQualityError("trade_date must be parseable, unique and increasing")
    if dates.max() > pd.Timestamp(END_DATE):
        raise DataQualityError("file contains data after required_end_date")
    if values.isna().any() or (~values.map(math.isfinite)).any() or (values <= 0).any():
        raise DataQualityError("qfq_close must be finite and positive")
    if set(frame["source"].astype(str)) != {SOURCE}:
        raise DataQualityError("RAW close or unexpected source cannot be used as QFQ")


def valid_cached_file(path: Path, code: str) -> bool:
    if not path.exists():
        return False
    try:
        validate_file(pd.read_csv(path, dtype={"stock_code": str}), code)
    except (OSError, ValueError, DataQualityError):
        return False
    return True


def fetch_sina(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    import akshare as ak

    prefix = "sh" if code6(code).startswith("6") else "sz"
    # AkShare 1.18.64 exposes no Session hook here; each retry invokes it afresh.
    return ak.stock_zh_a_daily(
        symbol=prefix + code6(code),
        start_date=start_date.replace("-", ""),
        end_date=end_date.replace("-", ""),
        adjust="qfq",
    )


def classify_error(exc: BaseException) -> str:
    """Do not mistake stock codes such as 000403/000429 for HTTP statuses."""
    name = type(exc).__name__
    text = f"{name}: {exc}".lower()
    if "ssl" in text or "unexpected_eof" in text or "unexpected eof" in text:
        return "SSLError"
    if "remotedisconnected" in text:
        return "RemoteDisconnected"
    if "connection reset" in text or "connectionreseterror" in text:
        return "ConnectionResetError"
    if "readtimeout" in text:
        return "ReadTimeout"
    if "connecttimeout" in text:
        return "ConnectTimeout"
    if isinstance(exc, (TimeoutError, socket.timeout)) or "timed out" in text:
        return "Timeout"
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    if status_code == 429 or re.search(r"\bhttp(?: status)?[ :=]+429\b", text):
        return "HTTP429"
    if status_code == 403 or re.search(r"\bhttp(?: status)?[ :=]+403\b", text):
        return "HTTP403"
    if "connectionerror" in text or "connection aborted" in text:
        return "ConnectionError"
    return name


def retry_after(exc: BaseException) -> float | None:
    response = getattr(exc, "response", None)
    value = getattr(response, "headers", {}).get("Retry-After") if response is not None else None
    try:
        return max(0.0, float(value)) if value is not None else None
    except (TypeError, ValueError):
        return None


def initial_status(codes: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "stock_code": codes,
            "status": "pending",
            "attempts": 0,
            "pass_index": 0,
            "attempts_in_pass": 0,
            "rows": 0,
            "date_min": "",
            "date_max": "",
            "last_error": "",
            "error_type": "",
            "board": [board_of(c) for c in codes],
            "feasibility_group": 0,
        }
    )[STATUS_COLUMNS]


def load_status(path: Path, codes: list[str], cache_dir: Path) -> pd.DataFrame:
    if path.exists():
        frame = pd.read_csv(path, dtype={"stock_code": str}).reindex(columns=STATUS_COLUMNS)
        frame["stock_code"] = frame["stock_code"].map(code6)
        if set(frame["stock_code"]) != set(codes) or len(frame) != len(codes):
            raise DataQualityError("download_status.csv does not match the 5,195-stock universe")
        frame = frame.set_index("stock_code").loc[codes].reset_index()
    else:
        frame = initial_status(codes)
    for column in ("status", "date_min", "date_max", "last_error", "error_type", "board"):
        frame[column] = frame[column].fillna("").astype(str)
    for column in ("attempts", "pass_index", "attempts_in_pass", "rows", "feasibility_group"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
    frame["status"] = frame["status"].replace({"failed": "failed_for_now"})
    for index, row in frame.iterrows():
        code = row["stock_code"]
        cached_path = cache_dir / f"{code}.csv"
        if valid_cached_file(cached_path, code):
            cached = pd.read_csv(cached_path, dtype={"stock_code": str})
            frame.loc[
                index, ["status", "rows", "date_min", "date_max", "last_error", "error_type"]
            ] = [
                "success",
                len(cached),
                cached["trade_date"].min(),
                cached["trade_date"].max(),
                "",
                "",
            ]
        elif row["status"] == "success":
            frame.loc[index, ["status", "attempts_in_pass", "last_error", "error_type"]] = [
                "pending",
                0,
                "cached success file failed basic QA",
                "DataQualityError",
            ]
        elif row["status"] == "in_progress":
            frame.loc[index, ["status", "last_error", "error_type"]] = [
                "failed_for_now",
                "previous run interrupted during request",
                "Interrupted",
            ]
    allowed = {"success", "failed_for_now", "pending", "final_failed"}
    if not set(frame["status"]).issubset(allowed):
        raise DataQualityError(f"unknown checkpoint status: {set(frame['status']) - allowed}")
    return frame[STATUS_COLUMNS]


def append_request(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig" if new_file else "utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUEST_COLUMNS)
        if new_file:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in REQUEST_COLUMNS})
        handle.flush()


def log_pause(meta_dir: Path, code: str, pass_index: int, kind: str, seconds: float) -> None:
    append_request(
        meta_dir / "request_log.csv",
        {
            "timestamp_utc": utc_now(),
            "stock_code": code,
            "pass_index": pass_index,
            "status": kind,
            "elapsed_seconds": round(seconds, 3),
        },
    )


def inspect_existing(cache_dir: Path, status: pd.DataFrame) -> dict:
    files = [p for p in cache_dir.glob("*.csv") if re.fullmatch(r"\d{6}\.csv", p.name)]
    partial = list(cache_dir.glob("*.tmp")) + list(cache_dir.glob("*partial*"))
    valid = sum(valid_cached_file(p, p.stem) for p in files)
    return {
        "existing_files_checked": len(files),
        "existing_valid_success": valid,
        "existing_partial": len(partial),
        "existing_invalid": len(files) - valid,
        "checkpoint_success": int(status["status"].eq("success").sum()),
    }


def summarize(
    status: pd.DataFrame, started: float, state: str, existing: dict | None = None
) -> dict:
    counts = status["status"].value_counts().to_dict()
    errors = status.loc[status["error_type"].ne(""), "error_type"].value_counts()
    result = {
        "state": state,
        "universe_count": len(status),
        "success_count": int(counts.get("success", 0)),
        "failed_for_now_count": int(counts.get("failed_for_now", 0)),
        "final_failed_count": int(counts.get("final_failed", 0)),
        "pending_count": int(counts.get("pending", 0)),
        "coverage": float(counts.get("success", 0) / len(status)),
        "elapsed_this_run_seconds": round(time.monotonic() - started, 1),
        "error_types": errors.to_dict(),
    }
    if existing:
        result.update(existing)
    return result


def longest_streak(values: list[bool]) -> int:
    longest = current = 0
    for value in values:
        current = current + 1 if value else 0
        longest = max(longest, current)
    return longest


def feasibility_metrics(status: pd.DataFrame, meta_dir: Path, group: int, started: float) -> dict:
    sample = status.loc[status["feasibility_group"].eq(group)]
    path = meta_dir / "request_log.csv"
    logs = (
        pd.read_csv(path, dtype={"stock_code": str})
        if path.exists()
        else pd.DataFrame(columns=REQUEST_COLUMNS)
    )
    logs = logs.loc[logs["stock_code"].astype(str).map(code6).isin(set(sample["stock_code"]))]
    attempts = logs.loc[logs["status"].isin(["success", "failed"])]
    latency = pd.to_numeric(
        logs.loc[logs["status"].eq("success"), "elapsed_seconds"], errors="coerce"
    )
    pauses = pd.to_numeric(
        logs.loc[logs["status"].eq("normal_pause"), "elapsed_seconds"], errors="coerce"
    )
    final_fail = sample["status"].isin(["failed_for_now", "final_failed"])
    return {
        "group": group,
        "tested": len(sample),
        "success": int(sample["status"].eq("success").sum()),
        "failed": int(final_fail.sum()),
        "attempts": len(attempts),
        "retry_count": max(0, len(attempts) - len(sample)),
        "ssl_eof_count": int(attempts["error_type"].eq("SSLError").sum()),
        "median_request_latency": float(latency.median()) if not latency.empty else None,
        "median_normal_pause": float(pauses.median()) if not pauses.empty else None,
        "elapsed_seconds": round(time.monotonic() - started, 1),
        "longest_failure_streak": longest_streak(final_fail.tolist()),
        "rate_limit_failures": int(attempts["error_type"].isin(["HTTP429", "HTTP403"]).sum()),
    }


def save_outputs(
    status: pd.DataFrame,
    meta_dir: Path,
    started: float,
    state: str,
    existing: dict | None = None,
    feasibility: dict | None = None,
) -> dict:
    atomic_write_csv(status[STATUS_COLUMNS], meta_dir / "download_status.csv")
    failed = status.loc[
        status["status"].isin(["failed_for_now", "final_failed"]),
        ["stock_code", "status", "attempts", "pass_index", "error_type", "last_error"],
    ]
    atomic_write_csv(failed, meta_dir / "failed_codes.csv")
    summary = summarize(status, started, state, existing)
    if feasibility:
        summary["vpn_long_run_feasibility"] = feasibility
    lines = ["# Broader-A Sina QFQ Download Summary", ""]
    lines += [
        f"- {k}: `"
        f"{json.dumps(v, ensure_ascii=False, default=json_default) if isinstance(v, dict) else v}`"
        for k, v in summary.items()
    ]
    lines += [
        "- TLS certificate verification remains enabled; `verify=False` is not used.",
        "- HTTP 429/403 is not bypassed; downloads are serial and use no proxy pool.",
        "- amount data and H5A/MCTS/Phase B/prospective/final-test logic "
        "were not read or modified.",
    ]
    (meta_dir / "download_summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return summary


def download_one(
    code: str,
    status: pd.DataFrame,
    index: int,
    cache_dir: Path,
    meta_dir: Path,
    fetcher: Callable[[str, str, str], pd.DataFrame],
    sleep_fn: Callable[[float], None],
    uniform_fn: Callable[[float, float], float] = random.uniform,
) -> str:
    status.at[index, "attempts_in_pass"] = 0
    last_kind = "failed_for_now"
    for attempt in range(1, MAX_ATTEMPTS_PER_PASS + 1):
        status.at[index, "attempts"] = int(status.at[index, "attempts"]) + 1
        status.at[index, "attempts_in_pass"] = attempt
        started = time.monotonic()
        try:
            frame = normalize_qfq(fetcher(code, START_DATE, END_DATE), code)
            atomic_write_csv(frame, cache_dir / f"{code}.csv")
            if not valid_cached_file(cache_dir / f"{code}.csv", code):
                raise DataQualityError("published file failed canonical QA")
        except Exception as exc:
            error_type = (
                "DataQualityError" if isinstance(exc, DataQualityError) else classify_error(exc)
            )
            error = str(exc)[:500]
            append_request(
                meta_dir / "request_log.csv",
                {
                    "timestamp_utc": utc_now(),
                    "stock_code": code,
                    "pass_index": int(status.at[index, "pass_index"]),
                    "attempt": attempt,
                    "status": "failed",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "error_type": error_type,
                    "error": error,
                },
            )
            status.loc[index, ["last_error", "error_type"]] = [error, error_type]
            if error_type in {"HTTP429", "HTTP403"}:
                seconds = retry_after(exc) or uniform_fn(600.0, 1800.0)
                last_kind = "rate_limited"
            elif error_type in TRANSIENT_TYPES:
                seconds = uniform_fn(15.0, 30.0) if attempt == 1 else uniform_fn(45.0, 90.0)
                last_kind = "transient_failed"
                log_pause(
                    meta_dir, code, int(status.at[index, "pass_index"]), "connection_recovery", 0.0
                )
            else:
                seconds = uniform_fn(15.0, 30.0) if attempt == 1 else uniform_fn(45.0, 90.0)
                last_kind = "data_failed"
            if attempt < MAX_ATTEMPTS_PER_PASS:
                log_pause(
                    meta_dir, code, int(status.at[index, "pass_index"]), "error_backoff", seconds
                )
                sleep_fn(seconds)
            continue
        append_request(
            meta_dir / "request_log.csv",
            {
                "timestamp_utc": utc_now(),
                "stock_code": code,
                "pass_index": int(status.at[index, "pass_index"]),
                "attempt": attempt,
                "status": "success",
                "elapsed_seconds": round(time.monotonic() - started, 3),
            },
        )
        status.loc[
            index, ["status", "rows", "date_min", "date_max", "last_error", "error_type"]
        ] = ["success", len(frame), frame["trade_date"].min(), frame["trade_date"].max(), "", ""]
        atomic_write_csv(status[STATUS_COLUMNS], meta_dir / "download_status.csv")
        return "success"
    status.at[index, "status"] = "failed_for_now"
    atomic_write_csv(status[STATUS_COLUMNS], meta_dir / "download_status.csv")
    return last_kind


def select_feasibility(status: pd.DataFrame, group: int) -> list[int]:
    """Take a deterministic board-balanced 50-stock sample from pending rows."""
    quotas = {"SZ_MAIN": 13, "SH_MAIN": 13, "CHINEXT": 12, "STAR": 12}
    chosen: list[int] = []
    for board, quota in quotas.items():
        eligible = status.index[
            status["status"].eq("pending")
            & status["board"].eq(board)
            & status["feasibility_group"].eq(0)
        ].tolist()
        chosen.extend(eligible[:quota])
    if len(chosen) != 50:
        raise DataQualityError("cannot form deterministic 50-stock four-board feasibility sample")
    status.loc[chosen, "feasibility_group"] = group
    return chosen


def process_indices(
    indices: list[int],
    status: pd.DataFrame,
    cache_dir: Path,
    meta_dir: Path,
    started: float,
    existing: dict,
    sleep_fn: Callable[[float], None],
    uniform_fn: Callable[[float, float], float],
) -> None:
    network_streak = transient_streak = rate_streak = processed = 0
    for index in indices:
        code = status.at[index, "stock_code"]
        outcome = download_one(
            code, status, index, cache_dir, meta_dir, fetch_sina, sleep_fn, uniform_fn
        )
        processed += 1
        if outcome == "success":
            network_streak = transient_streak = rate_streak = 0
        else:
            network_streak = (
                network_streak + 1 if outcome in {"transient_failed", "rate_limited"} else 0
            )
            transient_streak = transient_streak + 1 if outcome == "transient_failed" else 0
            rate_streak = rate_streak + 1 if outcome == "rate_limited" else 0
        if transient_streak and transient_streak % 3 == 0:
            seconds = uniform_fn(180.0, 360.0)
            log_pause(
                meta_dir, code, int(status.at[index, "pass_index"]), "global_cooldown", seconds
            )
            sleep_fn(seconds)
        if rate_streak >= 3:
            raise SystemicStop("SERVER_RATE_LIMIT_ACTIVE")
        if network_streak >= 50:
            raise SystemicStop("NETWORK_ENVIRONMENT_UNUSABLE")
        seconds = uniform_fn(2.5, 6.0)
        log_pause(meta_dir, code, int(status.at[index, "pass_index"]), "normal_pause", seconds)
        sleep_fn(seconds)
        if processed % 50 == 0:
            print(
                json.dumps(
                    save_outputs(status, meta_dir, started, "DOWNLOAD_IN_PROGRESS", existing),
                    ensure_ascii=False,
                    default=json_default,
                ),
                flush=True,
            )


def run_download(
    project_root: Path,
    sleep_fn: Callable[[float], None] = time.sleep,
    uniform_fn: Callable[[float, float], float] = random.uniform,
) -> tuple[int, dict]:
    started = time.monotonic()
    cache_dir, meta_dir = paths(project_root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    codes = load_universe(project_root)
    status_path = meta_dir / "download_status.csv"
    status = load_status(status_path, codes, cache_dir)
    existing = inspect_existing(cache_dir, status)
    atomic_write_csv(status, status_path)
    feasibility: dict | None = None
    try:
        groups = [g for g in sorted(status["feasibility_group"].unique()) if g > 0]
        if not groups:
            selected = select_feasibility(status, 1)
            atomic_write_csv(status, status_path)
            groups = [1]
        else:
            selected = status.index[
                status["feasibility_group"].eq(groups[-1]) & status["status"].eq("pending")
            ].tolist()
        if selected:
            process_indices(
                selected, status, cache_dir, meta_dir, started, existing, sleep_fn, uniform_fn
            )
        feasibility = feasibility_metrics(status, meta_dir, groups[-1], started)
        if feasibility["tested"] != 50 or feasibility["success"] + feasibility["failed"] != 50:
            return 130, save_outputs(
                status, meta_dir, started, "VPN_FEASIBILITY_IN_PROGRESS", existing, feasibility
            )
        if feasibility["success"] >= 45 and feasibility["rate_limit_failures"] < 3:
            feasible_state = True
        elif feasibility["success"] < 35 or feasibility["rate_limit_failures"] >= 3:
            feasible_state = False
        elif groups[-1] == 1:
            selected = select_feasibility(status, 2)
            atomic_write_csv(status, status_path)
            process_indices(
                selected, status, cache_dir, meta_dir, started, existing, sleep_fn, uniform_fn
            )
            feasibility = feasibility_metrics(status, meta_dir, 2, started)
            feasible_state = feasibility["success"] >= 45 and feasibility["rate_limit_failures"] < 3
            if 35 <= feasibility["success"] < 45:
                feasibility["result"] = "unstable"
                return 2, save_outputs(
                    status, meta_dir, started, "VPN_FEASIBILITY_UNSTABLE", existing, feasibility
                )
        else:
            feasibility["result"] = "unstable"
            return 2, save_outputs(
                status, meta_dir, started, "VPN_FEASIBILITY_UNSTABLE", existing, feasibility
            )
        feasibility["result"] = str(feasible_state).lower()
        if not feasible_state:
            return 2, save_outputs(
                status, meta_dir, started, "VPN_FEASIBILITY_FAILED", existing, feasibility
            )
        for pass_index in range(MAX_RETRY_PASSES + 1):
            if pass_index > 0:
                retry = status.index[
                    status["status"].eq("failed_for_now") & status["pass_index"].eq(pass_index - 1)
                ]
                status.loc[retry, ["status", "pass_index", "attempts_in_pass"]] = [
                    "pending",
                    pass_index,
                    0,
                ]
            pending = status.index[
                status["status"].eq("pending") & status["pass_index"].eq(pass_index)
            ].tolist()
            process_indices(
                pending, status, cache_dir, meta_dir, started, existing, sleep_fn, uniform_fn
            )
        status.loc[status["status"].eq("failed_for_now"), "status"] = "final_failed"
    except KeyboardInterrupt:
        return 130, save_outputs(
            status, meta_dir, started, "DOWNLOAD_IN_PROGRESS", existing, feasibility
        )
    except SystemicStop as exc:
        return 2, save_outputs(status, meta_dir, started, str(exc), existing, feasibility)
    return 0, save_outputs(status, meta_dir, started, "DOWNLOAD_COMPLETE", existing, feasibility)


def show_status(project_root: Path) -> dict:
    cache_dir, meta_dir = paths(project_root)
    status_path = meta_dir / "download_status.csv"
    started = time.monotonic()
    if not status_path.exists():
        return summarize(initial_status(load_universe(project_root)), started, "NOT_STARTED")
    status = pd.read_csv(status_path, dtype={"stock_code": str}).reindex(columns=STATUS_COLUMNS)
    return summarize(status, started, "DOWNLOAD_STATUS", inspect_existing(cache_dir, status))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--project-root", default=".")
    status = sub.add_parser("status")
    status.add_argument("--project-root", default=".")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.project_root).resolve()
    if args.command == "status":
        print(json.dumps(show_status(root), ensure_ascii=False, indent=2, default=json_default))
        return 0
    code, summary = run_download(root)
    print(json.dumps(summary, ensure_ascii=False, indent=2, default=json_default))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
