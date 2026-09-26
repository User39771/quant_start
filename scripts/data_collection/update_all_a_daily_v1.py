from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC = PROJECT_ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.data_layer.akshare_client import AkSharePublicClient  # noqa: E402
from aq_factor_lab.data_layer.normalize import (  # noqa: E402
    normalize_daily_price,
    normalize_universe,
)

VERSION = "all_a_daily_v1"
DEFAULT_REQUESTED_AS_OF = "2026-07-25"
PROVISIONAL_START = "2021-01-01"
RAW_COLUMNS = [
    "stock_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "turnover_rate",
    "source",
    "fetched_at",
    "request_start",
    "request_end",
]
QFQ_COLUMNS = [
    "stock_code",
    "trade_date",
    "qfq_open",
    "qfq_high",
    "qfq_low",
    "qfq_close",
    "qfq_volume",
    "qfq_amount",
    "qfq_turnover_rate",
    "qfq_factor",
    "factor_source",
    "source",
    "fetched_at",
    "request_start",
    "request_end",
]
INVENTORY_COLUMNS = [
    "path",
    "stock_code",
    "exchange",
    "adjustment_type",
    "min_date",
    "max_date",
    "row_count",
    "schema",
    "source",
    "sha256",
    "duplicate_key_count",
    "invalid_date_count",
    "nonfinite_price_count",
    "status",
]
STOCK_MANIFEST_COLUMNS = [
    "stock_code",
    "name",
    "exchange",
    "board",
    "mode",
    "sample_reason",
    "start_policy",
    "request_start",
    "request_end",
    "raw_status",
    "qfq_status",
    "raw_rows",
    "qfq_rows",
    "raw_min_date",
    "raw_max_date",
    "qfq_min_date",
    "qfq_max_date",
    "raw_sha256",
    "qfq_sha256",
    "error_type",
    "error_message",
]
REQUEST_COLUMNS = [
    "timestamp",
    "stock_code",
    "endpoint",
    "adjustment_type",
    "attempt",
    "request_start",
    "request_end",
    "status",
    "row_count",
    "elapsed_seconds",
    "error_type",
    "error_message",
]
FAILURE_COLUMNS = [
    "timestamp",
    "stock_code",
    "stage",
    "error_type",
    "error_message",
    "recoverable",
]
OVERLAP_COLUMNS = [
    "stock_code",
    "trade_date",
    "field",
    "old_value",
    "new_value",
    "absolute_difference",
    "status",
]
PROTECTED_PATTERNS = [
    "data/processed/research_universe_lowvol_freeze_*.csv",
    "data/processed/adjusted_price_panel_v1_5.csv",
    "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv",
    "data/processed/mom60_factor_panel_v1_3.csv",
    "reports/*mom60*v1_3*",
    "reports/lowvol*v1_5*",
    "reports/liquidity_filter*v1_6*",
    "reports/theme_breadth*v1_7*",
]
REQUIRED_PROTECTED_PATHS = [
    "reports/liquidity_filter_amount_readiness_v1_6.csv",
]
PROTECTED_INVENTORY_COLUMNS = [
    "relative_path",
    "exists",
    "is_file",
    "readable",
    "size_bytes",
    "sha256",
    "status",
    "error_type",
    "error_message",
]
BENCHMARK_PROBE_COLUMNS = [
    "run_id",
    "requested_as_of",
    "benchmark_code",
    "endpoint_name",
    "source_identity",
    "akshare_version",
    "attempt_number",
    "started_at_utc",
    "finished_at_utc",
    "elapsed_seconds",
    "outcome",
    "reason_code",
    "exception_type",
    "error_message",
    "http_status_if_available",
    "row_count",
    "min_date",
    "max_date",
    "latest_date",
    "schema",
    "response_sha256_if_available",
]
BENCHMARK_IDENTITIES = {
    "000300": {"name": "CSI 300", "tx_symbol": "sh000300"},
}


class ProtectedFileUnreadable(RuntimeError):
    reason_code = "PROTECTED_FILE_UNREADABLE"

    def __init__(self, row: dict[str, Any]) -> None:
        self.row = row
        message = (
            f"{self.reason_code}: {row['relative_path']}; "
            f"{row['error_type']}; errno={row.get('errno', '')}; "
            f"{row['error_message']}. Close Excel, previewers, or any process "
            "holding the file, then retry."
        )
        super().__init__(message)


class BenchmarkProbeError(RuntimeError):
    def __init__(self, reason_code: str, message: str) -> None:
        self.reason_code = reason_code
        super().__init__(message)


def now_text() -> str:
    return datetime.now(UTC).isoformat()


def sha256(
    path: Path,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
    open_fn: Callable[[Path], Any] | None = None,
) -> str:
    opener = open_fn or (lambda value: value.open("rb"))
    retry_delays = (1, 2, 4)
    for attempt in range(len(retry_delays) + 1):
        try:
            digest = hashlib.sha256()
            with opener(path) as handle:
                for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                    digest.update(chunk)
            return digest.hexdigest()
        except OSError:
            if attempt == len(retry_delays):
                raise
            sleep_fn(retry_delays[attempt])
    raise RuntimeError("unreachable")


def frame_sha256(frame: pd.DataFrame) -> str:
    text = frame.to_csv(index=False, lineterminator="\n", na_rep="")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(tmp, index=False, encoding="utf-8-sig", lineterminator="\n")
    tmp.replace(path)


def atomic_write_json(payload: dict[str, Any], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    json.loads(tmp.read_text(encoding="utf-8"))
    tmp.replace(path)


def append_csv(path: Path, row: dict[str, Any], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists() and path.stat().st_size > 0
    with path.open("a", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow({column: row.get(column, "") for column in columns})


def empty_csv(path: Path, columns: list[str]) -> None:
    if not path.exists():
        atomic_write_csv(pd.DataFrame(columns=columns), path)


def code6(value: Any) -> str:
    match = re.search(r"(\d{6})", str(value))
    return match.group(1) if match else ""


def classify_code(code: str) -> tuple[str, str]:
    code = code6(code)
    if code.startswith(("4", "8", "92")):
        return "BJ", "Beijing"
    if code.startswith(("688", "689")):
        return "SH", "STAR"
    if code.startswith(("600", "601", "603", "605")):
        return "SH", "Main"
    if code.startswith(("300", "301")):
        return "SZ", "ChiNext"
    if code.startswith(("000", "001", "002", "003")):
        return "SZ", "Main"
    return "", ""


def is_current_a_share(code: str) -> bool:
    exchange, _ = classify_code(code)
    return bool(exchange)


def canonical_universe(
    raw: pd.DataFrame,
    requested_as_of: str,
    source: str = "akshare.stock_zh_a_spot_em",
) -> pd.DataFrame:
    normalized, _ = normalize_universe(raw)
    normalized["stock_code"] = normalized["symbol"].map(code6)
    normalized = normalized[normalized["stock_code"].map(is_current_a_share)].copy()
    normalized[["exchange", "board"]] = normalized["stock_code"].apply(
        lambda value: pd.Series(classify_code(value))
    )
    normalized["listing_date"] = pd.to_datetime(
        normalized["list_date"], errors="coerce"
    ).dt.strftime("%Y-%m-%d")
    normalized["listing_date_source"] = np.where(
        normalized["listing_date"].notna(), normalized["source"], "unavailable_in_spot_endpoint"
    )
    normalized["current_listed_status"] = "current_snapshot_member"
    normalized["universe_as_of"] = requested_as_of
    normalized["point_in_time_universe"] = False
    normalized["survivorship_bias_warning"] = (
        "Current snapshot only; not a historical point-in-time universe."
    )
    normalized["source"] = source
    columns = [
        "stock_code",
        "name",
        "exchange",
        "board",
        "listing_date",
        "listing_date_source",
        "current_listed_status",
        "universe_as_of",
        "point_in_time_universe",
        "survivorship_bias_warning",
        "source",
    ]
    out = normalized[columns].drop_duplicates("stock_code").sort_values("stock_code")
    universe_hash = frame_sha256(out)
    out["source_sha256"] = universe_hash
    return out.reset_index(drop=True)


def protected_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    for pattern in PROTECTED_PATTERNS:
        if "*" in pattern or "?" in pattern:
            files.update(root.glob(pattern))
        else:
            files.add(root / pattern)
    files.update(root / relative for relative in REQUIRED_PROTECTED_PATHS)
    return sorted(files)


def collect_protected_hashes(
    root: Path,
    inventory_path: Path,
    *,
    paths: list[Path] | None = None,
    hash_fn: Callable[[Path], str] | None = None,
) -> dict[str, str]:
    hash_fn = hash_fn or sha256
    rows = []
    hashes = {}
    first_error: dict[str, Any] | None = None
    for path in paths or protected_files(root):
        relative = path.relative_to(root).as_posix()
        row: dict[str, Any] = {
            "relative_path": relative,
            "exists": path.exists(),
            "is_file": path.is_file(),
            "readable": False,
            "size_bytes": path.stat().st_size if path.exists() and path.is_file() else "",
            "sha256": "",
            "status": "unreadable",
            "error_type": "",
            "error_message": "",
        }
        try:
            if not path.exists():
                raise FileNotFoundError(2, "Protected file does not exist", str(path))
            if not path.is_file():
                raise OSError(f"Protected path is not a regular file: {path}")
            digest = hash_fn(path)
            row.update(readable=True, sha256=digest, status="ok")
            hashes[relative] = digest
        except Exception as exc:
            row.update(
                error_type=type(exc).__name__,
                error_message=str(exc),
                errno=getattr(exc, "errno", ""),
            )
            if first_error is None:
                first_error = row.copy()
        rows.append(row)
    atomic_write_csv(pd.DataFrame(rows, columns=PROTECTED_INVENTORY_COLUMNS), inventory_path)
    if first_error is not None:
        raise ProtectedFileUnreadable(first_error)
    return hashes


def hash_snapshot_path(root: Path) -> Path:
    return root / f"data/sandbox/{VERSION}/metadata/frozen_hash_snapshot.json"


def save_hash_snapshot(root: Path, run_dir: Path) -> dict[str, Any]:
    hashes = collect_protected_hashes(
        root, run_dir / "protected_file_inventory.csv"
    )
    payload = {
        "created_at": now_text(),
        "snapshot_complete": True,
        "protected_file_count": len(hashes),
        "hashes": hashes,
    }
    atomic_write_json(payload, hash_snapshot_path(root))
    return payload


def run_snapshot(root: Path) -> tuple[int, Path]:
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S_snapshot")
    run_dir = root / f"reports/data_refresh/{VERSION}/{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    formal = hash_snapshot_path(root)
    formal.unlink(missing_ok=True)
    try:
        payload = save_hash_snapshot(root, run_dir)
        manifest = {
            "run_id": run_id,
            "mode": "snapshot",
            "status": "completed",
            "reason_code": "",
            "snapshot_complete": True,
            "all_protected_files_readable": True,
            "protected_file_count": payload["protected_file_count"],
            "exit_code": 0,
        }
        atomic_write_json(manifest, run_dir / "run_manifest.json")
        return 0, run_dir
    except ProtectedFileUnreadable as exc:
        manifest = {
            "run_id": run_id,
            "mode": "snapshot",
            "status": "failed",
            "reason_code": exc.reason_code,
            "snapshot_complete": False,
            "all_protected_files_readable": False,
            "error_message": str(exc),
            "exit_code": 1,
        }
        atomic_write_json(manifest, run_dir / "run_manifest.json")
        return 1, run_dir


def load_recent_hash_snapshot(root: Path, max_age_seconds: int = 3600) -> dict[str, str]:
    path = hash_snapshot_path(root)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("snapshot_complete") is not True:
        raise RuntimeError("Frozen hash snapshot is incomplete")
    created = datetime.fromisoformat(payload["created_at"])
    if (datetime.now(UTC) - created).total_seconds() > max_age_seconds:
        raise RuntimeError("Frozen hash snapshot is stale")
    return dict(payload["hashes"])


def write_hash_audit(before: dict[str, str], after: dict[str, str], path: Path) -> bool:
    rows = []
    for key in sorted(set(before) | set(after)):
        status = "unchanged" if before.get(key) == after.get(key) else "changed"
        if key not in before:
            status = "added"
        elif key not in after:
            status = "missing"
        rows.append(
            {
                "path": key,
                "sha256_before": before.get(key, ""),
                "sha256_after": after.get(key, ""),
                "status": status,
            }
        )
    atomic_write_csv(pd.DataFrame(rows), path)
    return bool(rows) and all(row["status"] == "unchanged" for row in rows)


def finalize_protected_failure(
    root: Path, run_dir: Path, manifest: dict[str, Any]
) -> int:
    snapshot_path = hash_snapshot_path(root)
    snapshot = (
        json.loads(snapshot_path.read_text(encoding="utf-8"))
        if snapshot_path.exists()
        else {"snapshot_complete": False, "hashes": {}}
    )
    before = dict(snapshot.get("hashes", {}))
    inventory_path = run_dir / "protected_file_inventory.csv"
    inventory = (
        pd.read_csv(inventory_path, dtype=str).fillna("")
        if inventory_path.exists()
        else pd.DataFrame(columns=PROTECTED_INVENTORY_COLUMNS)
    )
    by_path = inventory.set_index("relative_path").to_dict("index")
    audit_rows = []
    for relative in sorted(set(before) | set(by_path)):
        current = by_path.get(relative, {})
        current_hash = current.get("sha256", "")
        if current.get("status") == "unreadable":
            status = "unreadable"
        elif relative not in before:
            status = "added"
        elif not current:
            status = "missing"
        elif current_hash == before[relative]:
            status = "unchanged"
        else:
            status = "changed"
        audit_rows.append(
            {
                "path": relative,
                "sha256_before": before.get(relative, ""),
                "sha256_after": current_hash,
                "status": status,
            }
        )
    atomic_write_csv(pd.DataFrame(audit_rows), run_dir / "frozen_hash_audit.csv")
    unreadable = sum(row["status"] == "unreadable" for row in audit_rows)
    changes = sum(row["status"] in {"changed", "added", "missing"} for row in audit_rows)
    failure_path = run_dir / "failure_log.csv"
    existing_failures = pd.read_csv(failure_path)
    if existing_failures.empty:
        append_csv(
            run_dir / "failure_log.csv",
            {
                "timestamp": now_text(),
                "stock_code": "",
                "stage": "protected_preflight",
                "error_type": manifest.get("error_type", ""),
                "error_message": manifest.get("error_message", ""),
                "recoverable": True,
            },
            FAILURE_COLUMNS,
        )
    failures = pd.read_csv(failure_path)
    atomic_write_csv(
        failures.groupby(["stage", "error_type"], dropna=False)
        .size()
        .reset_index(name="count"),
        run_dir / "failure_counts.csv",
    )
    raw_count = len(list((root / f"data/sandbox/{VERSION}/raw").glob("*.csv")))
    qfq_count = len(list((root / f"data/sandbox/{VERSION}/qfq").glob("*.csv")))
    manifest.update(
        {
            "snapshot_complete": bool(snapshot.get("snapshot_complete")),
            "all_protected_files_readable": False,
            "protected_file_count": len(audit_rows),
            "protected_file_unreadable_count": unreadable,
            "frozen_hash_changes": changes,
            "benchmark_preflight_pass": False,
            "benchmark_preflight_attempted": False,
            "stock_sample_started": False,
            "stock_sample_qa_pass": False,
            "sandbox_raw_count": raw_count,
            "sandbox_qfq_count": qfq_count,
            "partial_outputs": raw_count + qfq_count,
            "qfq_rebase_unapproved": 0,
            "full_refresh_technically_ready": False,
            "exit_code": 1,
        }
    )
    atomic_write_json(manifest, run_dir / "run_manifest.json")
    if manifest.get("mode") == "smoke":
        atomic_write_json(manifest, run_dir / "smoke_manifest.json")
    report = f"""# A股全市场日频更新 Smoke

- run_id: `{manifest.get('run_id', run_dir.name)}`
- status: `{manifest.get('status', '')}`
- reason_code: `{manifest.get('reason_code', '')}`
- snapshot_complete: `{str(manifest['snapshot_complete']).lower()}`
- all_protected_files_readable: `false`
- protected_file_unreadable_count: `{unreadable}`
- frozen_hash_changes: `{changes}`
- benchmark_preflight_attempted: `false`
- stock_sample_started: `false`
- sandbox_raw_count: `{raw_count}`
- sandbox_qfq_count: `{qfq_count}`
- full_refresh_technically_ready: `false`

Smoke stopped before the benchmark and stock phases. Unreadable files were retained
in the protected set and were not classified as unchanged. Close Excel, previewers,
or any process holding the listed files before requesting another smoke.
"""
    (run_dir / "data_refresh_report.md").write_text(report, encoding="utf-8")
    return 1


def candidate_inventory_files(root: Path) -> list[Path]:
    candidates = [
        root / "data/cache/price",
        root / "data/cache/qfq_enrichment_v1_2",
        root / "data/cache/qfq_refresh_v1_5",
        root / "data/cache/public/clean/akshare/daily_price",
        root / "data/processed",
        root / f"data/sandbox/{VERSION}/raw",
        root / f"data/sandbox/{VERSION}/qfq",
    ]
    files: set[Path] = set()
    for directory in candidates:
        if directory.exists():
            files.update(directory.rglob("*.csv"))
    return sorted(files)


def infer_inventory_code(path: Path, frame: pd.DataFrame) -> str:
    for column in ["stock_code", "code", "symbol", "股票代码"]:
        if column in frame.columns:
            values = frame[column].dropna().map(code6)
            values = values[values != ""].drop_duplicates()
            if len(values) == 1:
                return values.iloc[0]
            if len(values) > 1:
                return f"MULTI:{len(values)}"
    return code6(path.stem)


def infer_inventory_type(path: Path, columns: list[str]) -> str:
    text = path.as_posix().lower()
    if "qfq" in text or any(column.startswith("qfq_") for column in columns):
        return "qfq"
    if "adjusted_close" in columns:
        return "adjusted_mixed"
    return "raw_or_unadjusted"


def inventory_file(root: Path, path: Path) -> dict[str, Any]:
    base = {
        "path": path.relative_to(root).as_posix(),
        "stock_code": code6(path.stem),
        "exchange": classify_code(code6(path.stem))[0],
        "adjustment_type": "",
        "min_date": "",
        "max_date": "",
        "row_count": 0,
        "schema": "",
        "source": "local_file",
        "sha256": "",
        "duplicate_key_count": "",
        "invalid_date_count": "",
        "nonfinite_price_count": "",
        "status": "unreadable",
    }
    try:
        frame = pd.read_csv(path, dtype=str, low_memory=False)
        base["sha256"] = sha256(path)
        base["stock_code"] = infer_inventory_code(path, frame)
        base["exchange"] = classify_code(base["stock_code"])[0]
        base["adjustment_type"] = infer_inventory_type(path, list(frame.columns))
        base["row_count"] = len(frame)
        base["schema"] = "|".join(frame.columns.astype(str))
        date_column = next(
            (column for column in ["trade_date", "date", "日期"] if column in frame.columns),
            None,
        )
        price_column = next(
            (
                column
                for column in ["qfq_close", "adjusted_close", "close", "收盘"]
                if column in frame.columns
            ),
            None,
        )
        if date_column:
            dates = pd.to_datetime(frame[date_column], errors="coerce")
            base["invalid_date_count"] = int(dates.isna().sum())
            base["min_date"] = dates.min().strftime("%Y-%m-%d") if dates.notna().any() else ""
            base["max_date"] = dates.max().strftime("%Y-%m-%d") if dates.notna().any() else ""
            keys = [date_column]
            for column in ["stock_code", "code", "symbol", "股票代码"]:
                if column in frame.columns:
                    keys.insert(0, column)
                    break
            base["duplicate_key_count"] = int(frame.duplicated(keys).sum())
        if price_column:
            values = pd.to_numeric(frame[price_column], errors="coerce")
            base["nonfinite_price_count"] = int((~np.isfinite(values)).sum())
        base["status"] = "ok"
    except Exception as exc:
        base["status"] = f"unreadable:{type(exc).__name__}"
    return base


def build_inventory(root: Path, output: Path) -> pd.DataFrame:
    files = candidate_inventory_files(root)
    prior_paths = sorted(
        (
            path
            for path in (root / f"reports/data_refresh/{VERSION}").glob(
                "*/local_data_inventory.csv"
            )
            if path.resolve() != output.resolve()
        ),
        reverse=True,
    )
    for prior in prior_paths:
        try:
            cached = pd.read_csv(prior, dtype=str, low_memory=False)
            newest_source = max((path.stat().st_mtime_ns for path in files), default=0)
            if len(cached) == len(files) and newest_source <= prior.stat().st_mtime_ns:
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(prior, output)
                return cached
        except Exception:
            continue
    rows = [inventory_file(root, path) for path in files]
    frame = pd.DataFrame(rows, columns=INVENTORY_COLUMNS)
    atomic_write_csv(frame, output)
    return frame


def mark_orphaned_runs(root: Path) -> None:
    base = root / f"reports/data_refresh/{VERSION}"
    if not base.exists():
        return
    cutoff = time.time() - 600
    for run_dir in base.iterdir():
        if (
            not run_dir.is_dir()
            or (run_dir / "run_manifest.json").exists()
            or run_dir.stat().st_mtime > cutoff
        ):
            continue
        atomic_write_json(
            {
                "version": VERSION,
                "run_id": run_dir.name,
                "mode": run_dir.name.rsplit("_", 1)[-1],
                "status": "interrupted_before_checkpoint",
                "finished_at": now_text(),
                "exit_code": 2,
            },
            run_dir / "run_manifest.json",
        )


def fetch_with_retry(
    action: Callable[[], pd.DataFrame],
    *,
    request_path: Path,
    stock_code: str,
    endpoint: str,
    adjustment_type: str,
    request_start: str,
    request_end: str,
    attempts: int,
    sleep_seconds: float,
) -> pd.DataFrame:
    for attempt in range(1, attempts + 1):
        started = time.monotonic()
        try:
            frame = action()
            append_csv(
                request_path,
                {
                    "timestamp": now_text(),
                    "stock_code": stock_code,
                    "endpoint": endpoint,
                    "adjustment_type": adjustment_type,
                    "attempt": attempt,
                    "request_start": request_start,
                    "request_end": request_end,
                    "status": "success",
                    "row_count": len(frame),
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                },
                REQUEST_COLUMNS,
            )
            return frame
        except Exception as exc:
            append_csv(
                request_path,
                {
                    "timestamp": now_text(),
                    "stock_code": stock_code,
                    "endpoint": endpoint,
                    "adjustment_type": adjustment_type,
                    "attempt": attempt,
                    "request_start": request_start,
                    "request_end": request_end,
                    "status": "failed",
                    "elapsed_seconds": round(time.monotonic() - started, 3),
                    "error_type": type(exc).__name__,
                    "error_message": str(exc)[:500],
                },
                REQUEST_COLUMNS,
            )
            if attempt == attempts:
                raise
            time.sleep(sleep_seconds * (2 ** (attempt - 1)))
    raise RuntimeError("unreachable")


def eastmoney_stock_kline(
    code: str,
    start: str,
    end: str,
    *,
    adjusted: bool,
    timeout: float = 20,
) -> pd.DataFrame:
    exchange, _ = classify_code(code)
    market = "1" if exchange == "SH" else "0"
    session = requests.Session()
    session.trust_env = False
    response = session.get(
        "http://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={
            "secid": f"{market}.{code}",
            "klt": "101",
            "fqt": "1" if adjusted else "0",
            "beg": start.replace("-", ""),
            "end": end.replace("-", ""),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
        },
        headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    klines = (payload.get("data") or {}).get("klines") or []
    if not klines:
        raise RuntimeError(f"Eastmoney kline returned no rows for {code}")
    columns = [
        "日期",
        "开盘",
        "收盘",
        "最高",
        "最低",
        "成交量",
        "成交额",
        "振幅",
        "涨跌幅",
        "涨跌额",
        "换手率",
    ]
    return pd.DataFrame([row.split(",") for row in klines], columns=columns)


def classify_probe_error(exc: Exception) -> str:
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status == 403:
        return "HTTP_403"
    if status == 429:
        return "HTTP_429"
    name = type(exc).__name__
    text = str(exc)
    if name == "RemoteDisconnected" or "RemoteDisconnected" in text:
        return "REMOTE_DISCONNECTED"
    if isinstance(exc, (TimeoutError, requests.Timeout)) or "timed out" in text.lower():
        return "TIMEOUT"
    if isinstance(exc, BenchmarkProbeError):
        return exc.reason_code
    return "UNKNOWN_ENDPOINT_ERROR"


def normalize_benchmark_response(
    raw: pd.DataFrame,
    *,
    benchmark_code: str,
    endpoint_name: str,
    requested_as_of: str,
) -> pd.DataFrame:
    if benchmark_code not in BENCHMARK_IDENTITIES:
        raise BenchmarkProbeError(
            "INDEX_IDENTITY_MISMATCH", f"Unsupported benchmark {benchmark_code}"
        )
    if raw.empty:
        raise BenchmarkProbeError("EMPTY_RESPONSE", "Benchmark response is empty")
    date_col = next(
        (column for column in ["date", "trade_date", "日期"] if column in raw), None
    )
    close_col = next(
        (column for column in ["close", "收盘"] if column in raw), None
    )
    if date_col is None or close_col is None:
        raise BenchmarkProbeError(
            "SCHEMA_MISMATCH", f"Missing date/close columns: {list(raw.columns)}"
        )
    for code_col in ["benchmark_code", "index_code", "symbol", "代码"]:
        if code_col in raw:
            codes = {code6(value) for value in raw[code_col].dropna()}
            if codes and codes != {benchmark_code}:
                raise BenchmarkProbeError(
                    "INDEX_IDENTITY_MISMATCH",
                    f"Response codes {sorted(codes)} do not match {benchmark_code}",
                )
    dates = pd.to_datetime(raw[date_col], errors="coerce")
    closes = pd.to_numeric(raw[close_col], errors="coerce")
    out = pd.DataFrame(
        {
            "benchmark_code": benchmark_code,
            "trade_date": dates,
            "close": closes,
            "instrument_type": "index",
            "instrument_name": BENCHMARK_IDENTITIES[benchmark_code]["name"],
            "source": endpoint_name,
        }
    ).dropna(subset=["trade_date", "close"])
    out = out[out["trade_date"] <= pd.Timestamp(requested_as_of)].copy()
    if out.empty:
        raise BenchmarkProbeError("EMPTY_RESPONSE", "No rows on or before requested_as_of")
    if out["trade_date"].duplicated().any() or not out["trade_date"].is_monotonic_increasing:
        raise BenchmarkProbeError(
            "SCHEMA_MISMATCH", "Benchmark dates are duplicated or not increasing"
        )
    if (~np.isfinite(out["close"]) | (out["close"] <= 0)).any():
        raise BenchmarkProbeError("SCHEMA_MISMATCH", "Benchmark close is invalid")
    out["trade_date"] = out["trade_date"].dt.strftime("%Y-%m-%d")
    return out.reset_index(drop=True)


def validate_benchmark_overlap(
    root: Path, benchmark: pd.DataFrame, benchmark_code: str
) -> None:
    cache_path = root / f"data/cache/benchmark_refresh_v1_5/{benchmark_code}.csv"
    if not cache_path.exists():
        raise BenchmarkProbeError(
            "INDEX_IDENTITY_MISMATCH", f"Missing local identity cache: {cache_path}"
        )
    local = pd.read_csv(cache_path, dtype={"benchmark_code": str})
    if (
        set(local["benchmark_code"].map(code6)) != {benchmark_code}
        or not local["instrument_type"].eq("index").all()
        or set(local["instrument_name"]) != {BENCHMARK_IDENTITIES[benchmark_code]["name"]}
    ):
        raise BenchmarkProbeError(
            "INDEX_IDENTITY_MISMATCH", "Local benchmark identity contract failed"
        )
    overlap = local[["trade_date", "close"]].merge(
        benchmark[["trade_date", "close"]],
        on="trade_date",
        suffixes=("_local", "_remote"),
    )
    if overlap.empty:
        raise BenchmarkProbeError(
            "INDEX_IDENTITY_MISMATCH", "No local/remote benchmark overlap"
        )
    left = pd.to_numeric(overlap["close_local"], errors="coerce")
    right = pd.to_numeric(overlap["close_remote"], errors="coerce")
    if not np.isclose(left, right, atol=1e-8, rtol=1e-8, equal_nan=False).all():
        raise BenchmarkProbeError(
            "INDEX_IDENTITY_MISMATCH", "Local/remote benchmark overlap conflicts"
        )


def _default_benchmark_primary(
    client: AkSharePublicClient, code: str, start: str, end: str
) -> pd.DataFrame:
    return client.index_daily(
        code, start.replace("-", ""), end.replace("-", ""), timeout=20
    )


def _default_benchmark_fallback(
    client: AkSharePublicClient, code: str, _start: str, _end: str
) -> pd.DataFrame:
    module = client._require_akshare()  # noqa: SLF001
    return module.stock_zh_index_daily_tx(
        symbol=BENCHMARK_IDENTITIES[code]["tx_symbol"]
    )


def benchmark_preflight(
    root: Path,
    run_dir: Path,
    run_id: str,
    requested_as_of: str,
    benchmark_code: str,
    *,
    client: AkSharePublicClient | None = None,
    primary_fetch: Callable[[str, str, str], pd.DataFrame] | None = None,
    fallback_fetch: Callable[[str, str, str], pd.DataFrame] | None = None,
    allow_fallback: bool = True,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> tuple[pd.DatetimeIndex, str, pd.DataFrame, str]:
    client = client or AkSharePublicClient()
    start = (pd.Timestamp(requested_as_of) - pd.Timedelta(days=550)).strftime("%Y-%m-%d")
    primary = primary_fetch or (
        lambda code, first, last: _default_benchmark_primary(
            client, code, first, last
        )
    )
    fallback = fallback_fetch or (
        lambda code, first, last: _default_benchmark_fallback(
            client, code, first, last
        )
    )
    endpoints = [
        ("ak.index_zh_a_hist", "akshare_index_primary", primary, 3),
    ]
    if allow_fallback:
        endpoints.append(
            (
                "ak.stock_zh_index_daily_tx",
                "akshare_tx_index_fallback",
                fallback,
                1,
            )
        )
    rows: list[dict[str, Any]] = []
    result: pd.DataFrame | None = None
    used_source = ""
    for endpoint_name, source_identity, fetch, max_attempts in endpoints:
        for attempt in range(1, max_attempts + 1):
            started_at = now_text()
            started = time.monotonic()
            row = dict.fromkeys(BENCHMARK_PROBE_COLUMNS, "")
            row.update(
                {
                    "run_id": run_id,
                    "requested_as_of": requested_as_of,
                    "benchmark_code": benchmark_code,
                    "endpoint_name": endpoint_name,
                    "source_identity": source_identity,
                    "akshare_version": client.version,
                    "attempt_number": attempt,
                    "started_at_utc": started_at,
                }
            )
            try:
                raw = fetch(benchmark_code, start, requested_as_of)
                normalized = normalize_benchmark_response(
                    raw,
                    benchmark_code=benchmark_code,
                    endpoint_name=endpoint_name,
                    requested_as_of=requested_as_of,
                )
                validate_benchmark_overlap(root, normalized, benchmark_code)
                row.update(
                    {
                        "finished_at_utc": now_text(),
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "outcome": "success",
                        "row_count": len(normalized),
                        "min_date": normalized["trade_date"].min(),
                        "max_date": normalized["trade_date"].max(),
                        "latest_date": normalized["trade_date"].max(),
                        "schema": "|".join(normalized.columns),
                        "response_sha256_if_available": frame_sha256(normalized),
                    }
                )
                rows.append(row)
                result = normalized
                used_source = endpoint_name
                break
            except Exception as exc:
                row.update(
                    {
                        "finished_at_utc": now_text(),
                        "elapsed_seconds": round(time.monotonic() - started, 3),
                        "outcome": "failed",
                        "reason_code": classify_probe_error(exc),
                        "exception_type": type(exc).__name__,
                        "error_message": str(exc)[:1000],
                        "http_status_if_available": getattr(
                            getattr(exc, "response", None), "status_code", ""
                        ),
                    }
                )
                rows.append(row)
                if attempt < max_attempts:
                    sleep_fn((5, 15)[attempt - 1])
        if result is not None:
            break
    manifest = pd.DataFrame(rows, columns=BENCHMARK_PROBE_COLUMNS)
    atomic_write_csv(manifest, run_dir / "benchmark_probe_manifest.csv")
    atomic_write_csv(
        manifest[manifest["outcome"].eq("failed")],
        run_dir / "benchmark_probe_failures.csv",
    )
    if result is None:
        reason = rows[-1]["reason_code"] if rows else "UNKNOWN_ENDPOINT_ERROR"
        raise BenchmarkProbeError(reason, f"Benchmark preflight failed: {reason}")
    resolved = result["trade_date"].max()
    calendar = pd.DatetimeIndex(pd.to_datetime(result["trade_date"]))
    return calendar, resolved, result, used_source


def write_benchmark_probe_report(
    run_dir: Path,
    *,
    run_id: str,
    requested_as_of: str,
    benchmark_code: str,
    success: bool,
    resolved_end: str = "",
    used_source: str = "",
    reason_code: str = "",
) -> None:
    fallback_used = used_source == "ak.stock_zh_index_daily_tx"
    report = f"""# Benchmark endpoint probe

- run_id: `{run_id}`
- requested_as_of: `{requested_as_of}`
- benchmark_code: `{benchmark_code}`
- benchmark_preflight_pass: `{str(success).lower()}`
- primary_endpoint: `ak.index_zh_a_hist`
- fallback_used: `{str(fallback_used).lower()}`
- fallback_endpoint: `{'ak.stock_zh_index_daily_tx' if fallback_used else ''}`
- resolved_end_date: `{resolved_end}`
- reason_code: `{reason_code}`
- sandbox_price_files_written: `false`

The fallback is the existing project index contract and is never mixed with the
primary response. Local benchmark data is used only for identity and overlap QA.
"""
    (run_dir / "benchmark_probe_report.md").write_text(report, encoding="utf-8")


def run_benchmark_probe(
    root: Path, requested_as_of: str, benchmark_code: str
) -> tuple[int, Path]:
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S_benchmark_probe")
    run_dir = root / f"reports/data_refresh/{VERSION}/{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    try:
        _, resolved, _, used_source = benchmark_preflight(
            root,
            run_dir,
            run_id,
            requested_as_of,
            benchmark_code,
        )
        write_benchmark_probe_report(
            run_dir,
            run_id=run_id,
            requested_as_of=requested_as_of,
            benchmark_code=benchmark_code,
            success=True,
            resolved_end=resolved,
            used_source=used_source,
        )
        return 0, run_dir
    except BenchmarkProbeError as exc:
        write_benchmark_probe_report(
            run_dir,
            run_id=run_id,
            requested_as_of=requested_as_of,
            benchmark_code=benchmark_code,
            success=False,
            reason_code=exc.reason_code,
        )
        return 2, run_dir


def read_standard(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path, dtype={"stock_code": str})
    frame["stock_code"] = frame["stock_code"].map(code6)
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise").dt.strftime(
        "%Y-%m-%d"
    )
    return frame[columns].sort_values("trade_date").reset_index(drop=True)


def compatible_seed(root: Path, code: str, kind: str) -> pd.DataFrame:
    if kind == "raw":
        candidates = list(
            (root / "data/cache/public/clean/akshare/daily_price").glob(f"**/*{code}*.csv")
        )
        target_columns = RAW_COLUMNS
    else:
        candidates = [
            root / f"data/cache/qfq_enrichment_v1_2/{code}.csv",
            root / f"data/cache/qfq_refresh_v1_5/{code}.csv",
        ]
        target_columns = QFQ_COLUMNS
    for path in candidates:
        if not path.exists():
            continue
        frame = pd.read_csv(path, dtype=str)
        if kind == "raw" and {"date", "open", "high", "low", "close"}.issubset(frame.columns):
            out = pd.DataFrame(
                {
                    "stock_code": code,
                    "trade_date": pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d"),
                    "open": frame["open"],
                    "high": frame["high"],
                    "low": frame["low"],
                    "close": frame["close"],
                    "volume": frame.get("volume"),
                    "amount": frame.get("amount"),
                    "turnover_rate": frame.get("turnover"),
                    "source": f"seed:{path.relative_to(root).as_posix()}",
                    "fetched_at": "",
                    "request_start": "",
                    "request_end": "",
                }
            )
            return out[target_columns]
        required = {"trade_date", "qfq_open", "qfq_high", "qfq_low", "qfq_close"}
        if kind == "qfq" and required.issubset(frame.columns):
            out = pd.DataFrame(
                {
                    "stock_code": code,
                    "trade_date": pd.to_datetime(frame["trade_date"]).dt.strftime("%Y-%m-%d"),
                    "qfq_open": frame["qfq_open"],
                    "qfq_high": frame["qfq_high"],
                    "qfq_low": frame["qfq_low"],
                    "qfq_close": frame["qfq_close"],
                    "qfq_volume": frame.get("qfq_volume"),
                    "qfq_amount": frame.get("qfq_amount"),
                    "qfq_turnover_rate": frame.get("qfq_turnover_rate"),
                    "qfq_factor": frame.get("qfq_factor"),
                    "factor_source": frame.get("factor_source", "not_provided_by_source"),
                    "source": f"seed:{path.relative_to(root).as_posix()}",
                    "fetched_at": frame.get("fetched_at", ""),
                    "request_start": "",
                    "request_end": "",
                }
            )
            return out[target_columns]
    return pd.DataFrame(columns=target_columns)


def normalize_download(
    raw: pd.DataFrame,
    code: str,
    request_start: str,
    request_end: str,
    adjusted: bool,
    fetched_at: str,
    source: str = "akshare.stock_zh_a_hist",
) -> pd.DataFrame:
    base = normalize_daily_price(
        raw,
        symbol=code,
        start=request_start,
        end=request_end,
        adjusted=adjusted,
    )
    prefix = "qfq_" if adjusted else ""
    base["source"] = source
    out = pd.DataFrame(
        {
            "stock_code": code,
            "trade_date": base["date"].dt.strftime("%Y-%m-%d"),
            f"{prefix}open": base["open"],
            f"{prefix}high": base["high"],
            f"{prefix}low": base["low"],
            f"{prefix}close": base["close"],
            f"{prefix}volume": base["volume"],
            f"{prefix}amount": base["amount"],
            f"{prefix}turnover_rate": base["turnover"],
            "source": base["source"],
            "fetched_at": fetched_at,
            "request_start": request_start,
            "request_end": request_end,
        }
    )
    if adjusted:
        out["qfq_factor"] = np.nan
        out["factor_source"] = "not_provided_by_endpoint"
        return out[QFQ_COLUMNS]
    return out[RAW_COLUMNS]


def validate_standard(frame: pd.DataFrame, kind: str, end: str) -> None:
    if frame.empty:
        raise ValueError(f"{kind} download is empty")
    price_columns = (
        ["qfq_open", "qfq_high", "qfq_low", "qfq_close"]
        if kind == "qfq"
        else ["open", "high", "low", "close"]
    )
    dates = pd.to_datetime(frame["trade_date"], errors="coerce")
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError(f"{kind} dates invalid, duplicated, or unsorted")
    if dates.max() > pd.Timestamp(end):
        raise ValueError(f"{kind} contains future dates")
    values = frame[price_columns].apply(pd.to_numeric, errors="coerce")
    if (~np.isfinite(values)).any().any() or (values <= 0).any().any():
        raise ValueError(f"{kind} contains nonpositive or nonfinite OHLC")


def overlap_differences(
    old: pd.DataFrame,
    new: pd.DataFrame,
    kind: str,
    atol: float = 1e-8,
    rtol: float = 1e-10,
) -> pd.DataFrame:
    if old.empty:
        return pd.DataFrame(columns=OVERLAP_COLUMNS)
    fields = (
        ["qfq_open", "qfq_high", "qfq_low", "qfq_close", "qfq_volume", "qfq_amount"]
        if kind == "qfq"
        else ["open", "high", "low", "close", "volume", "amount"]
    )
    common = old.merge(new, on=["stock_code", "trade_date"], suffixes=("_old", "_new"))
    rows = []
    for field in fields:
        if f"{field}_old" not in common or f"{field}_new" not in common:
            continue
        left = pd.to_numeric(common[f"{field}_old"], errors="coerce")
        right = pd.to_numeric(common[f"{field}_new"], errors="coerce")
        comparable = left.notna() & right.notna()
        changed = comparable & ~np.isclose(left, right, atol=atol, rtol=rtol)
        for index in common.index[changed]:
            old_value = left.loc[index]
            new_value = right.loc[index]
            rows.append(
                {
                    "stock_code": common.loc[index, "stock_code"],
                    "trade_date": common.loc[index, "trade_date"],
                    "field": field,
                    "old_value": old_value,
                    "new_value": new_value,
                    "absolute_difference": abs(old_value - new_value),
                    "status": "changed",
                }
            )
    return pd.DataFrame(rows, columns=OVERLAP_COLUMNS)


def merge_history(old: pd.DataFrame, new: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    combined = pd.concat([old, new], ignore_index=True)
    return (
        combined.drop_duplicates(["stock_code", "trade_date"], keep="last")
        .sort_values("trade_date")
        .reset_index(drop=True)[columns]
    )


def request_start(old: pd.DataFrame, listing_date: str) -> tuple[str, str]:
    if old.empty:
        if listing_date:
            return max(listing_date, PROVISIONAL_START), "listing_date_or_provisional_start"
        return PROVISIONAL_START, "provisional_start_no_listing_date"
    last = pd.to_datetime(old["trade_date"]).max()
    return (last - timedelta(days=30)).strftime("%Y-%m-%d"), "incremental_with_30_day_overlap"


def choose_smoke(universe: pd.DataFrame, root: Path) -> pd.DataFrame:
    selected: list[str] = []
    preferred = [
        "600519",
        "000001",
        "300750",
        "688981",
        "601318",
        "002594",
        "603259",
        "300059",
    ]
    selected.extend(code for code in preferred if code in set(universe["stock_code"]))
    quotas = {"SH": 6, "SZ": 6, "BJ": 4, "STAR": 3, "ChiNext": 3}
    for key, count in quotas.items():
        column = "exchange" if key in {"SH", "SZ", "BJ"} else "board"
        pool = universe.loc[universe[column] == key, "stock_code"].tolist()
        pool_set = set(pool)
        for code in pool:
            if len([item for item in selected if item in pool_set]) >= count:
                break
            if code not in selected:
                selected.append(code)
    selected = list(dict.fromkeys(selected))
    if len(selected) < 20:
        selected.extend(
            code for code in universe["stock_code"] if code not in selected
        )
    out = universe[universe["stock_code"].isin(selected)].copy()
    cached = {
        path.stem for path in (root / "data/cache/price").glob("*.csv")
    }
    out["sample_reason"] = out["stock_code"].map(
        lambda code: "existing_cache" if code in cached else "missing_local_cache"
    )
    out.loc[
        out["stock_code"].isin(preferred), "sample_reason"
    ] += "|known_corporate_action_candidate"
    return out.sort_values(["exchange", "board", "stock_code"]).reset_index(drop=True)


def write_run_skeleton(run_dir: Path) -> None:
    empty_csv(run_dir / "stock_refresh_manifest.csv", STOCK_MANIFEST_COLUMNS)
    empty_csv(run_dir / "request_log.csv", REQUEST_COLUMNS)
    empty_csv(run_dir / "failure_log.csv", FAILURE_COLUMNS)
    empty_csv(run_dir / "raw_overlap_differences.csv", OVERLAP_COLUMNS)
    empty_csv(run_dir / "qfq_overlap_differences.csv", OVERLAP_COLUMNS)
    empty_csv(
        run_dir / "qfq_rebase_candidates.csv",
        ["stock_code", "candidate_path", "changed_cells", "candidate_sha256", "status"],
    )
    empty_csv(
        run_dir / "coverage_summary.csv",
        [
            "stock_code",
            "exchange",
            "board",
            "layer",
            "expected_market_days",
            "observed_rows",
            "missing_market_days",
            "coverage_ratio",
            "min_date",
            "max_date",
            "through_resolved_end",
        ],
    )
    empty_csv(
        run_dir / "date_gap_summary.csv",
        ["stock_code", "layer", "classification", "missing_date_count", "status"],
    )
    empty_csv(run_dir / "failure_counts.csv", ["stage", "error_type", "count"])


def prepare_run(
    root: Path,
    mode: str,
    requested_as_of: str,
    attempts: int,
    sleep_seconds: float,
) -> tuple[Path, dict[str, Any], pd.DataFrame, pd.DatetimeIndex]:
    run_id = datetime.now().strftime("%Y%m%dT%H%M%S") + f"_{mode}"
    run_dir = root / f"reports/data_refresh/{VERSION}/{run_id}"
    run_dir.mkdir(parents=True, exist_ok=False)
    write_run_skeleton(run_dir)
    try:
        before = collect_protected_hashes(
            root, run_dir / "protected_file_inventory.csv"
        )
        snapshot = load_recent_hash_snapshot(root)
        if before != snapshot:
            raise RuntimeError("Current protected hashes do not match the complete snapshot")
    except Exception as exc:
        reason = (
            exc.reason_code
            if isinstance(exc, ProtectedFileUnreadable)
            else "PROTECTED_SNAPSHOT_REQUIRED"
        )
        failed = {
            "version": VERSION,
            "run_id": run_id,
            "mode": mode,
            "status": "failed_protected_preflight",
            "phase": "protected_snapshot",
            "stock_sample_started": False,
            "reason_code": reason,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "exit_code": 1,
        }
        atomic_write_json(failed, run_dir / "run_manifest.json")
        if mode == "smoke":
            atomic_write_json(failed, run_dir / "smoke_manifest.json")
        finalize_protected_failure(root, run_dir, failed)
        raise
    atomic_write_json(before, run_dir / "frozen_hashes_before.json")
    client = AkSharePublicClient()
    try:
        calendar, resolved_end, hs300, calendar_source = benchmark_preflight(
            root,
            run_dir,
            run_id,
            requested_as_of,
            "000300",
            client=client,
        )
        write_benchmark_probe_report(
            run_dir,
            run_id=run_id,
            requested_as_of=requested_as_of,
            benchmark_code="000300",
            success=True,
            resolved_end=resolved_end,
            used_source=calendar_source,
        )
        inventory = build_inventory(root, run_dir / "local_data_inventory.csv")
        universe_source = "akshare.stock_zh_a_spot_em"
        try:
            universe_raw = fetch_with_retry(
                client.stock_universe,
                request_path=run_dir / "request_log.csv",
                stock_code="ALL_A",
                endpoint="stock_zh_a_spot_em",
                adjustment_type="universe",
                request_start="",
                request_end=requested_as_of,
                attempts=attempts,
                sleep_seconds=sleep_seconds,
            )
        except Exception:
            universe_source = "eastmoney.clist.current_a_share"
            universe_raw = fetch_with_retry(
                lambda: client._eastmoney_clist(  # noqa: SLF001
                    fs="b:MK0010,m:1+t:1,m:0+t:5,m:1+s:3,m:0+t:5,m:2",
                    fields="f12,f14,f13",
                ).rename(columns={"f12": "code", "f14": "name", "f13": "market_id"}),
                request_path=run_dir / "request_log.csv",
                stock_code="ALL_A",
                endpoint="eastmoney_clist_current_a_share",
                adjustment_type="universe",
                request_start="",
                request_end=requested_as_of,
                attempts=attempts,
                sleep_seconds=sleep_seconds,
            )
    except BenchmarkProbeError as exc:
        write_benchmark_probe_report(
            run_dir,
            run_id=run_id,
            requested_as_of=requested_as_of,
            benchmark_code="000300",
            success=False,
            reason_code=exc.reason_code,
        )
        append_csv(
            run_dir / "failure_log.csv",
            {
                "timestamp": now_text(),
                "stock_code": "",
                "stage": "benchmark_preflight",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1000],
                "recoverable": True,
            },
            FAILURE_COLUMNS,
        )
        atomic_write_json(
            {
                "version": VERSION,
                "run_id": run_id,
                "mode": mode,
                "status": "failed_preflight",
                "phase": "benchmark_calendar",
                "stock_sample_started": False,
                "reason_code": exc.reason_code,
                "started_at": now_text(),
                "requested_as_of": requested_as_of,
                "inventory_file_count": 0,
                "protected_file_count": len(before),
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "exit_code": 2,
            },
            run_dir / "run_manifest.json",
        )
        if mode == "smoke":
            shutil.copy2(
                run_dir / "run_manifest.json", run_dir / "smoke_manifest.json"
            )
        atomic_write_json(
            {
                "run_id": run_id,
                "mode": mode,
                "status": "failed_preflight",
                "completed": {},
                "updated_at": now_text(),
            },
            run_dir / "resume_checkpoint.json",
        )
        after = collect_protected_hashes(
            root, run_dir / "protected_file_inventory_after.csv"
        )
        write_hash_audit(before, after, run_dir / "frozen_hash_audit.csv")
        raise RuntimeError(f"{run_id}: preflight failed: {exc}") from exc
    universe = canonical_universe(universe_raw, requested_as_of, universe_source)
    if universe.empty or set(universe["exchange"]) != {"SH", "SZ", "BJ"}:
        raise RuntimeError("Current universe does not cover SH, SZ, and BJ")
    atomic_write_csv(universe, run_dir / "current_a_share_universe.csv")
    sandbox = root / f"data/sandbox/{VERSION}"
    atomic_write_csv(universe, sandbox / "universe/current_a_share_universe.csv")
    calendar_frame = hs300[["trade_date"]].rename(columns={"trade_date": "date"})
    calendar_path = sandbox / "metadata/hs300_market_calendar.csv"
    atomic_write_csv(calendar_frame, calendar_path)
    manifest = {
        "version": VERSION,
        "run_id": run_id,
        "mode": mode,
        "status": "prepared",
        "started_at": now_text(),
        "requested_as_of": requested_as_of,
        "resolved_end": resolved_end,
        "calendar_source": calendar_source,
        "calendar_sha256": sha256(calendar_path),
        "universe_source": universe_source,
        "universe_sha256": frame_sha256(universe.drop(columns=["source_sha256"])),
        "universe_count": len(universe),
        "akshare_version": client.version,
        "provisional_start": PROVISIONAL_START,
        "point_in_time_universe": False,
        "survivorship_bias_warning": (
            "Current snapshot only; not a historical point-in-time universe."
        ),
        "inventory_file_count": len(inventory),
        "protected_file_count": len(before),
        "protected_hash_deferred": False,
        "benchmark_preflight_pass": True,
        "stock_sample_started": mode != "prepare",
    }
    atomic_write_json(manifest, run_dir / "run_manifest.json")
    if mode == "smoke":
        atomic_write_json(manifest, run_dir / "smoke_manifest.json")
    checkpoint = {
        "run_id": run_id,
        "mode": mode,
        "status": "prepared",
        "resolved_end": resolved_end,
        "completed": {},
        "updated_at": now_text(),
    }
    atomic_write_json(checkpoint, run_dir / "resume_checkpoint.json")
    sandbox_checkpoint = sandbox / "checkpoints/resume_checkpoint.json"
    sandbox_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run_dir / "resume_checkpoint.json", sandbox_checkpoint)
    return run_dir, manifest, universe, calendar


def load_checkpoint(run_dir: Path) -> dict[str, Any]:
    return json.loads((run_dir / "resume_checkpoint.json").read_text(encoding="utf-8"))


def save_checkpoint(root: Path, run_dir: Path, checkpoint: dict[str, Any]) -> None:
    checkpoint["updated_at"] = now_text()
    atomic_write_json(checkpoint, run_dir / "resume_checkpoint.json")
    sandbox_checkpoint = (
        root / f"data/sandbox/{VERSION}/checkpoints/resume_checkpoint.json"
    )
    sandbox_checkpoint.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(run_dir / "resume_checkpoint.json", sandbox_checkpoint)


def stable_completed(root: Path, code: str, record: dict[str, Any]) -> bool:
    if not record.get("status", "").startswith("completed"):
        return False
    for kind in ["raw", "qfq"]:
        expected = record.get(f"{kind}_sha256", "")
        path = root / f"data/sandbox/{VERSION}/{kind}/{code}.csv"
        if expected and (not path.exists() or sha256(path) != expected):
            return False
    return True


def process_stock(
    root: Path,
    run_dir: Path,
    row: pd.Series,
    manifest: dict[str, Any],
    client: AkSharePublicClient,
    attempts: int,
    sleep_seconds: float,
) -> dict[str, Any]:
    code = row["stock_code"]
    end = manifest["resolved_end"]
    fetched_at = now_text()
    paths = {
        "raw": root / f"data/sandbox/{VERSION}/raw/{code}.csv",
        "qfq": root / f"data/sandbox/{VERSION}/qfq/{code}.csv",
    }
    old: dict[str, pd.DataFrame] = {}
    for kind, columns in [("raw", RAW_COLUMNS), ("qfq", QFQ_COLUMNS)]:
        old[kind] = read_standard(paths[kind], columns)
        if old[kind].empty:
            old[kind] = compatible_seed(root, code, kind)
    starts = [
        request_start(old["raw"], str(row.get("listing_date") or "")),
        request_start(old["qfq"], str(row.get("listing_date") or "")),
    ]
    start = min(starts[0][0], starts[1][0])
    start_policy = "|".join(sorted({starts[0][1], starts[1][1]}))
    downloads = {}
    for kind, adjusted in [("raw", False), ("qfq", True)]:
        fetched = fetch_with_retry(
            lambda adjusted=adjusted: eastmoney_stock_kline(
                code,
                start,
                end,
                adjusted=adjusted,
            ),
            request_path=run_dir / "request_log.csv",
            stock_code=code,
            endpoint="eastmoney_kline_stock",
            adjustment_type=kind,
            request_start=start,
            request_end=end,
            attempts=attempts,
            sleep_seconds=sleep_seconds,
        )
        downloads[kind] = normalize_download(
            fetched,
            code,
            start,
            end,
            adjusted,
            fetched_at,
            source="eastmoney.stock.kline",
        )
        validate_standard(downloads[kind], kind, end)
        time.sleep(sleep_seconds)
    raw_diff = overlap_differences(old["raw"], downloads["raw"], "raw")
    qfq_diff = overlap_differences(old["qfq"], downloads["qfq"], "qfq")
    for diff, filename in [
        (raw_diff, "raw_overlap_differences.csv"),
        (qfq_diff, "qfq_overlap_differences.csv"),
    ]:
        for diff_row in diff.to_dict("records"):
            append_csv(run_dir / filename, diff_row, OVERLAP_COLUMNS)
    result: dict[str, Any] = {
        "stock_code": code,
        "name": row["name"],
        "exchange": row["exchange"],
        "board": row["board"],
        "mode": manifest["mode"],
        "sample_reason": row.get("sample_reason", ""),
        "start_policy": start_policy,
        "request_start": start,
        "request_end": end,
        "raw_status": "updated",
        "qfq_status": "updated",
        "error_type": "",
        "error_message": "",
    }
    if raw_diff.empty:
        raw_final = merge_history(old["raw"], downloads["raw"], RAW_COLUMNS)
        validate_standard(raw_final, "raw", end)
        atomic_write_csv(raw_final, paths["raw"])
    else:
        raw_final = old["raw"]
        result["raw_status"] = "historical_restatement_blocked"
    if qfq_diff.empty:
        qfq_final = merge_history(old["qfq"], downloads["qfq"], QFQ_COLUMNS)
        validate_standard(qfq_final, "qfq", end)
        atomic_write_csv(qfq_final, paths["qfq"])
    else:
        qfq_final = old["qfq"]
        candidate = (
            root
            / f"data/sandbox/{VERSION}/candidate_rebases/{manifest['run_id']}/{code}.csv"
        )
        atomic_write_csv(downloads["qfq"], candidate)
        append_csv(
            run_dir / "qfq_rebase_candidates.csv",
            {
                "stock_code": code,
                "candidate_path": candidate.relative_to(root).as_posix(),
                "changed_cells": len(qfq_diff),
                "candidate_sha256": sha256(candidate),
                "status": "awaiting_review",
            },
            [
                "stock_code",
                "candidate_path",
                "changed_cells",
                "candidate_sha256",
                "status",
            ],
        )
        result["qfq_status"] = "rebase_candidate_blocked"
    for kind, frame in [("raw", raw_final), ("qfq", qfq_final)]:
        result[f"{kind}_rows"] = len(frame)
        result[f"{kind}_min_date"] = frame["trade_date"].min() if not frame.empty else ""
        result[f"{kind}_max_date"] = frame["trade_date"].max() if not frame.empty else ""
        result[f"{kind}_sha256"] = sha256(paths[kind]) if paths[kind].exists() else ""
    result["status"] = (
        "completed"
        if raw_diff.empty and qfq_diff.empty
        else "completed_with_review_block"
    )
    return result


def build_gap_and_coverage(
    root: Path,
    run_dir: Path,
    universe: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    end: str,
) -> None:
    coverage_rows = []
    gap_rows = []
    calendar = calendar[
        (calendar >= pd.Timestamp(PROVISIONAL_START)) & (calendar <= pd.Timestamp(end))
    ]
    for row in universe.itertuples(index=False):
        code = row.stock_code
        layer_dates: dict[str, set[pd.Timestamp]] = {}
        for kind, columns in [("raw", RAW_COLUMNS), ("qfq", QFQ_COLUMNS)]:
            frame = read_standard(
                root / f"data/sandbox/{VERSION}/{kind}/{code}.csv", columns
            )
            dates = set(pd.to_datetime(frame["trade_date"])) if not frame.empty else set()
            layer_dates[kind] = dates
            expected = set(calendar)
            missing = sorted(expected - dates)
            max_date = max(dates).strftime("%Y-%m-%d") if dates else ""
            coverage_rows.append(
                {
                    "stock_code": code,
                    "exchange": row.exchange,
                    "board": row.board,
                    "layer": kind,
                    "expected_market_days": len(expected),
                    "observed_rows": len(dates),
                    "missing_market_days": len(missing),
                    "coverage_ratio": len(dates & expected) / len(expected) if expected else np.nan,
                    "min_date": min(dates).strftime("%Y-%m-%d") if dates else "",
                    "max_date": max_date,
                    "through_resolved_end": max_date == end,
                }
            )
        all_missing = set(calendar) - (layer_dates["raw"] | layer_dates["qfq"])
        for kind in ["raw", "qfq"]:
            missing = sorted(set(calendar) - layer_dates[kind])
            if not missing:
                continue
            first = min(layer_dates[kind]) if layer_dates[kind] else pd.Timestamp(end)
            counts: dict[str, int] = {}
            for date in missing:
                if date < first:
                    classification = "pre_listing_or_provisional_history"
                elif date in all_missing:
                    classification = "possible_suspension_or_no_trade"
                else:
                    classification = "retrieval_or_layer_gap"
                counts[classification] = counts.get(classification, 0) + 1
            for classification, count in counts.items():
                gap_rows.append(
                    {
                        "stock_code": code,
                        "layer": kind,
                        "classification": classification,
                        "missing_date_count": count,
                        "status": "unresolved" if "retrieval" in classification else "descriptive",
                    }
                )
    atomic_write_csv(pd.DataFrame(coverage_rows), run_dir / "coverage_summary.csv")
    atomic_write_csv(
        pd.DataFrame(
            gap_rows,
            columns=[
                "stock_code",
                "layer",
                "classification",
                "missing_date_count",
                "status",
            ],
        ),
        run_dir / "date_gap_summary.csv",
    )


def finalize_report(
    root: Path,
    run_dir: Path,
    manifest: dict[str, Any],
    universe: pd.DataFrame,
    calendar: pd.DatetimeIndex,
) -> int:
    stock_path = run_dir / "stock_refresh_manifest.csv"
    stocks = (
        pd.read_csv(stock_path, dtype={"stock_code": str})
        if stock_path.exists()
        else pd.DataFrame()
    )
    failure_path = run_dir / "failure_log.csv"
    failures = (
        pd.read_csv(failure_path)
        if failure_path.exists() and failure_path.stat().st_size
        else pd.DataFrame()
    )
    if failures.empty:
        failure_counts = pd.DataFrame(columns=["stage", "error_type", "count"])
    else:
        failure_counts = (
            failures.groupby(["stage", "error_type"], dropna=False)
            .size()
            .reset_index(name="count")
        )
    atomic_write_csv(failure_counts, run_dir / "failure_counts.csv")
    build_gap_and_coverage(
        root, run_dir, universe, calendar, manifest["resolved_end"]
    )
    before = json.loads((run_dir / "frozen_hashes_before.json").read_text(encoding="utf-8"))
    try:
        after = collect_protected_hashes(
            root, run_dir / "protected_file_inventory_after.csv"
        )
        frozen_ok = write_hash_audit(
            before, after, run_dir / "frozen_hash_audit.csv"
        )
    except ProtectedFileUnreadable as exc:
        manifest.update(
            {
                "status": "failed_protected_postflight",
                "reason_code": exc.reason_code,
                "frozen_hash_audit_passed": False,
                "stock_sample_qa_pass": False,
                "full_refresh_technically_ready": False,
                "exit_code": 1,
            }
        )
        atomic_write_json(manifest, run_dir / "run_manifest.json")
        if manifest.get("mode") == "smoke":
            atomic_write_json(manifest, run_dir / "smoke_manifest.json")
        return 1
    completed = int(stocks["raw_status"].notna().sum()) if not stocks.empty else 0
    blocked = (
        int(
            (
                stocks["raw_status"].astype(str).str.contains("blocked")
                | stocks["qfq_status"].astype(str).str.contains("blocked")
            ).sum()
        )
        if not stocks.empty
        else 0
    )
    failed = len(failures)
    status = "completed"
    exit_code = 0
    if frozen_ok is False:
        status, exit_code = "failed_frozen_hash_change", 1
    elif failed:
        status, exit_code = "recoverable_partial", 2
    elif blocked:
        status, exit_code = "completed_with_review_blocks", 2
    stock_sample_qa_pass = exit_code == 0 and completed >= 20
    technically_ready = (
        manifest.get("mode") == "smoke"
        and frozen_ok
        and stock_sample_qa_pass
        and failed == 0
        and blocked == 0
    )
    manifest.update(
        {
            "status": status,
            "finished_at": now_text(),
            "completed_stock_records": completed,
            "failure_count": failed,
            "review_block_count": blocked,
            "frozen_hash_audit_passed": frozen_ok,
            "stock_sample_qa_pass": stock_sample_qa_pass,
            "partial_outputs": failed,
            "qfq_rebase_unapproved": blocked,
            "full_refresh_technically_ready": technically_ready,
            "exit_code": exit_code,
        }
    )
    atomic_write_json(manifest, run_dir / "run_manifest.json")
    if manifest.get("mode") == "smoke":
        atomic_write_json(manifest, run_dir / "smoke_manifest.json")
    checkpoint = load_checkpoint(run_dir)
    checkpoint["status"] = status
    save_checkpoint(root, run_dir, checkpoint)
    coverage = pd.read_csv(run_dir / "coverage_summary.csv")
    coverage_note = (
        coverage.groupby("layer")["coverage_ratio"].mean().round(6).to_dict()
        if not coverage.empty
        else {}
    )
    report = f"""# A股全市场日频数据补全与增量刷新

- Run ID: `{manifest['run_id']}`
- Mode: `{manifest['mode']}`
- Status: `{status}`
- Requested as-of: `{manifest['requested_as_of']}`
- Resolved completed trading day: `{manifest['resolved_end']}`
- Current A-share universe: {manifest['universe_count']} stocks
- Completed stock records: {completed}
- Failures: {failed}
- Review blocks: {blocked}
- Mean sandbox coverage by layer: `{coverage_note}`
- Frozen hash audit: `{'PASS' if frozen_ok else 'FAIL'}`
- Full refresh technically ready: `{str(technically_ready).lower()}`

## Boundaries

This run writes only under `data/sandbox/{VERSION}` and this run report directory.
The universe is a current snapshot and is not point-in-time; survivorship bias is explicit.
Missing prices are not filled. QFQ overlap changes are held as review candidates rather than
silently replacing history. This task does not calculate factors, portfolios, or backtests.

## Recovery

Resume with:

`python scripts/data_collection/update_all_a_daily_v1.py resume --project-root .`
` --run-id {manifest['run_id']}`
"""
    (run_dir / "data_refresh_report.md").write_text(report, encoding="utf-8")
    return exit_code


def execute_refresh(
    root: Path,
    run_dir: Path,
    manifest: dict[str, Any],
    universe: pd.DataFrame,
    calendar: pd.DatetimeIndex,
    attempts: int,
    sleep_seconds: float,
    max_consecutive_failures: int,
    failure_rate: float,
) -> int:
    checkpoint = load_checkpoint(run_dir)
    client = AkSharePublicClient()
    consecutive = 0
    attempts_count = 0
    failures_count = 0
    for _, row in universe.iterrows():
        code = row["stock_code"]
        record = checkpoint["completed"].get(code, {})
        if stable_completed(root, code, record):
            continue
        attempts_count += 1
        try:
            result = process_stock(
                root,
                run_dir,
                row,
                manifest,
                client,
                attempts,
                sleep_seconds,
            )
            append_csv(run_dir / "stock_refresh_manifest.csv", result, STOCK_MANIFEST_COLUMNS)
            checkpoint["completed"][code] = result
            consecutive = 0
        except Exception as exc:
            failures_count += 1
            consecutive += 1
            failure = {
                "timestamp": now_text(),
                "stock_code": code,
                "stage": "stock_refresh",
                "error_type": type(exc).__name__,
                "error_message": str(exc)[:1000],
                "recoverable": True,
            }
            append_csv(run_dir / "failure_log.csv", failure, FAILURE_COLUMNS)
            checkpoint["completed"][code] = {"status": "failed", **failure}
        save_checkpoint(root, run_dir, checkpoint)
        if consecutive >= max_consecutive_failures:
            manifest["stop_reason"] = "max_consecutive_failures"
            break
        if attempts_count >= 20 and failures_count / attempts_count > failure_rate:
            manifest["stop_reason"] = "failure_rate_threshold"
            break
    return finalize_report(root, run_dir, manifest, universe, calendar)


def latest_successful_smoke(root: Path) -> Path | None:
    base = root / f"reports/data_refresh/{VERSION}"
    candidates = []
    for path in base.glob("*_smoke/run_manifest.json"):
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            if manifest.get("status", "").startswith("completed") and int(
                manifest.get("completed_stock_records", 0)
            ) >= 20:
                candidates.append(path.parent)
        except Exception:
            continue
    return sorted(candidates)[-1] if candidates else None


def audit_failed_run(root: Path, run_id: str) -> int:
    run_dir = root / f"reports/data_refresh/{VERSION}/{run_id}"
    manifest_path = run_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") == "failed_protected_preflight":
        return finalize_protected_failure(root, run_dir, manifest)
    before = json.loads((run_dir / "frozen_hashes_before.json").read_text(encoding="utf-8"))
    after = collect_protected_hashes(
        root, run_dir / "protected_file_inventory_after.csv"
    )
    frozen_ok = write_hash_audit(
        before, after, run_dir / "frozen_hash_audit.csv"
    )
    manifest["frozen_hash_audit_passed"] = frozen_ok
    if not frozen_ok:
        manifest["status"] = "failed_frozen_hash_change"
        manifest["exit_code"] = 1
    atomic_write_json(manifest, manifest_path)
    empty_csv(
        run_dir / "current_a_share_universe.csv",
        [
            "stock_code",
            "name",
            "exchange",
            "board",
            "listing_date",
            "listing_date_source",
            "current_listed_status",
            "universe_as_of",
            "point_in_time_universe",
            "survivorship_bias_warning",
            "source",
            "source_sha256",
        ],
    )
    failures = pd.read_csv(run_dir / "failure_log.csv")
    failure_counts = (
        failures.groupby(["stage", "error_type"], dropna=False)
        .size()
        .reset_index(name="count")
    )
    atomic_write_csv(failure_counts, run_dir / "failure_counts.csv")
    checkpoint_path = run_dir / "resume_checkpoint.json"
    if checkpoint_path.exists():
        sandbox_checkpoint = (
            root / f"data/sandbox/{VERSION}/checkpoints/resume_checkpoint.json"
        )
        sandbox_checkpoint.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(checkpoint_path, sandbox_checkpoint)
    report = f"""# A股全市场日频数据补全与增量刷新

- Run ID: `{run_id}`
- Mode: `{manifest.get('mode', '')}`
- Status: `{manifest.get('status', '')}`
- Requested as-of: `{manifest.get('requested_as_of', '')}`
- Exit code: `{manifest.get('exit_code', 2)}`
- Frozen hash audit: `{'PASS' if frozen_ok else 'FAIL'}`

## Stop reason

The authoritative market-calendar endpoint remained unavailable after three retries.
No stock raw/QFQ file was written, and a full refresh was not authorized because the
required 20+ stock smoke gate did not pass.

## Exact recovery command

`python scripts/data_collection/update_all_a_daily_v1.py snapshot --project-root .`

Then:

`python scripts/data_collection/update_all_a_daily_v1.py smoke --project-root .`
` --requested-as-of {manifest.get('requested_as_of', DEFAULT_REQUESTED_AS_OF)}`

This task did not calculate factors, portfolios, or backtests.
"""
    (run_dir / "data_refresh_report.md").write_text(report, encoding="utf-8")
    return int(manifest.get("exit_code", 2))


def load_run(
    root: Path, run_id: str
) -> tuple[Path, dict[str, Any], pd.DataFrame, pd.DatetimeIndex]:
    run_dir = root / f"reports/data_refresh/{VERSION}/{run_id}"
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    universe = pd.read_csv(
        run_dir / "current_a_share_universe.csv", dtype={"stock_code": str}
    )
    calendar_frame = pd.read_csv(
        root / f"data/sandbox/{VERSION}/metadata/hs300_market_calendar.csv"
    )
    calendar = pd.DatetimeIndex(pd.to_datetime(calendar_frame["date"]))
    return run_dir, manifest, universe, calendar


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        choices=[
            "inventory",
            "snapshot",
            "probe-benchmark",
            "audit",
            "prepare",
            "smoke",
            "run",
            "resume",
            "report",
        ],
    )
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT)
    parser.add_argument("--requested-as-of", default=DEFAULT_REQUESTED_AS_OF)
    parser.add_argument("--benchmark-code", default="000300")
    parser.add_argument("--run-id")
    parser.add_argument("--approve-full-refresh", action="store_true")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--sleep-seconds", type=float, default=0.2)
    parser.add_argument("--max-consecutive-failures", type=int, default=10)
    parser.add_argument("--failure-rate", type=float, default=0.20)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.project_root.resolve()
    mark_orphaned_runs(root)
    if args.command == "snapshot":
        exit_code, run_dir = run_snapshot(root)
        print(run_dir.name)
        return exit_code
    if args.command == "probe-benchmark":
        exit_code, run_dir = run_benchmark_probe(
            root, args.requested_as_of, code6(args.benchmark_code)
        )
        print(run_dir.name)
        return exit_code
    if args.command == "audit":
        if not args.run_id:
            print("--run-id is required", file=sys.stderr)
            return 2
        return audit_failed_run(root, args.run_id)
    if args.command == "inventory":
        run_id = datetime.now().strftime("%Y%m%dT%H%M%S_inventory")
        run_dir = root / f"reports/data_refresh/{VERSION}/{run_id}"
        run_dir.mkdir(parents=True)
        inventory = build_inventory(root, run_dir / "local_data_inventory.csv")
        atomic_write_json(
            {
                "run_id": run_id,
                "mode": "inventory",
                "status": "completed",
                "inventory_file_count": len(inventory),
                "finished_at": now_text(),
                "exit_code": 0,
            },
            run_dir / "run_manifest.json",
        )
        print(run_id)
        return 0
    if args.command in {"prepare", "smoke", "run"}:
        if args.command == "run" and not args.approve_full_refresh:
            print("Full refresh requires --approve-full-refresh", file=sys.stderr)
            return 2
        if args.command == "run" and latest_successful_smoke(root) is None:
            print("Full refresh requires a successful >=20-stock smoke run", file=sys.stderr)
            return 2
        try:
            run_dir, manifest, universe, calendar = prepare_run(
                root,
                args.command,
                args.requested_as_of,
                args.attempts,
                args.sleep_seconds,
            )
        except ProtectedFileUnreadable as exc:
            print(str(exc), file=sys.stderr)
            return 1
        except Exception as exc:
            print(str(exc), file=sys.stderr)
            return 2
        print(manifest["run_id"], flush=True)
        if args.command == "prepare":
            return 0
        if args.command == "smoke":
            universe = choose_smoke(universe, root)
        return execute_refresh(
            root,
            run_dir,
            manifest,
            universe,
            calendar,
            args.attempts,
            args.sleep_seconds,
            args.max_consecutive_failures,
            args.failure_rate,
        )
    if not args.run_id:
        print("--run-id is required", file=sys.stderr)
        return 2
    run_dir, manifest, universe, calendar = load_run(root, args.run_id)
    if args.command == "report":
        return finalize_report(root, run_dir, manifest, universe, calendar)
    return execute_refresh(
        root,
        run_dir,
        manifest,
        universe,
        calendar,
        args.attempts,
        args.sleep_seconds,
        args.max_consecutive_failures,
        args.failure_rate,
    )


if __name__ == "__main__":
    raise SystemExit(main())
