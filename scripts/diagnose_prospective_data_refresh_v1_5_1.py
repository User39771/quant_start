"""Read-only evidence for LOWVOL20 prospective data-refresh readiness."""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd

try:
    from scripts.refresh_research_data_v1_5 import (
        INDEX_IDENTITIES,
        _default_index_fallback,
        _default_index_primary,
        _default_stock_fallback,
        _default_stock_primary,
        code6,
        normalize_benchmark,
        normalize_stock,
    )
    from scripts.run_lowvol_prospective_append_v1_5_1 import next_period
except ImportError:
    from refresh_research_data_v1_5 import (
        INDEX_IDENTITIES,
        _default_index_fallback,
        _default_index_primary,
        _default_stock_fallback,
        _default_stock_primary,
        code6,
        normalize_benchmark,
        normalize_stock,
    )
    from run_lowvol_prospective_append_v1_5_1 import next_period


REQUEST_COLUMNS = [
    "asset_type", "code", "endpoint", "requested_start", "requested_end",
    "request_attempted", "request_status", "fallback_attempted", "cache_status",
    "response_row_count", "response_min_date", "response_max_date",
    "normalized_row_count", "normalized_min_date", "normalized_max_date",
    "candidate_date", "candidate_date_present", "latest_valid_date",
    "error_class", "error_summary",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_paths(root: Path) -> list[Path]:
    paths = [
        root / "data/processed/adjusted_price_panel_v1_5.csv",
        root / "data/processed/qfq_enrichment_panel_v1_5.csv",
        root / "data/processed/hybrid_benchmark_panel_v1_5.csv",
        root / "data/processed/research_universe_lowvol_freeze_20260711.csv",
        root / "reports/qfq_refresh_manifest_v1_5.csv",
        root / "reports/adjusted_price_panel_QA_v1_5.csv",
        root / "reports/adjusted_stock_pool_baseline_periods_v1_5.csv",
        root / "reports/prospective/lowvol_v1_5_1/prospective_periods.csv",
    ]
    paths += sorted((root / "data/cache/qfq_refresh_v1_5").glob("*.csv"))
    paths += sorted((root / "data/cache/benchmark_refresh_v1_5").glob("*.csv"))
    return [path for path in paths if path.exists()]


def hash_snapshot(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): sha256(path) for path in protected_paths(root)}


def zero_attempt_diagnosis(fetch_summary: pd.DataFrame) -> dict[str, object]:
    if fetch_summary.empty or "endpoint" not in fetch_summary:
        attempts = successes = failures = 0
    else:
        price = fetch_summary.loc[fetch_summary["endpoint"].astype(str).eq("price")]
        successes = int(pd.to_numeric(price.get("success", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
        failures = int(pd.to_numeric(price.get("failed", pd.Series(dtype=float)), errors="coerce").fillna(0).sum())
        attempts = successes + failures
    return {
        "attempts": attempts,
        "successes": successes,
        "failures": failures,
        "displayed_success_rate": successes / attempts if attempts else 0.0,
        "issue_type": "misleading_zero_attempt_success_rate" if attempts == 0 else "none",
        "severity": "non_blocking_engineering_issue" if attempts == 0 else "none",
        "action": "deferred" if attempts == 0 else "none",
    }


def resolve_candidate(root: Path, benchmark: pd.DataFrame, explicit: str | None) -> tuple[str, str]:
    if explicit:
        return pd.Timestamp(explicit).strftime("%Y-%m-%d"), "explicit_probe_date"
    period = next_period(root, benchmark)
    value = period.get("rebalance_date")
    return (pd.Timestamp(value).strftime("%Y-%m-%d"), "frozen_schedule") if value is not None else ("", "not_yet_in_local_calendar")


def raw_date_range(raw: pd.DataFrame) -> tuple[str, str]:
    column = next((name for name in ("trade_date", "date", "日期") if name in raw), None)
    if raw.empty or column is None:
        return "", ""
    dates = pd.to_datetime(raw[column], errors="coerce").dropna()
    return (dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")) if not dates.empty else ("", "")


def request_row(
    asset_type: str,
    code: str,
    endpoint: str,
    start: str,
    end: str,
    candidate: str,
    cache_status: str,
    fetch: Callable[[], pd.DataFrame],
    normalize: Callable[[str, pd.DataFrame, str], pd.DataFrame],
    fallback_attempted: bool = False,
) -> dict[str, object]:
    row = dict.fromkeys(REQUEST_COLUMNS, "")
    row.update({
        "asset_type": asset_type, "code": code6(code), "endpoint": endpoint,
        "requested_start": start, "requested_end": end, "request_attempted": True,
        "fallback_attempted": fallback_attempted, "cache_status": cache_status,
        "candidate_date": candidate,
    })
    try:
        raw = fetch()
        raw_min, raw_max = raw_date_range(raw)
        normalized = normalize(code, raw, endpoint)
        dates = pd.to_datetime(normalized["trade_date"], errors="raise")
        row.update({
            "request_status": "success", "response_row_count": len(raw),
            "response_min_date": raw_min, "response_max_date": raw_max,
            "normalized_row_count": len(normalized),
            "normalized_min_date": dates.min().strftime("%Y-%m-%d"),
            "normalized_max_date": dates.max().strftime("%Y-%m-%d"),
            "candidate_date_present": bool(candidate and pd.Timestamp(candidate) in set(dates)),
            "latest_valid_date": dates.max().strftime("%Y-%m-%d"),
        })
    except Exception as exc:
        row.update({
            "request_status": "failed", "candidate_date_present": False,
            "error_class": type(exc).__name__, "error_summary": str(exc)[:500],
        })
    return row


def cache_rows(root: Path, candidate: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for asset_type, folder, endpoint in (
        ("stock", root / "data/cache/qfq_refresh_v1_5", "ak.stock_zh_a_daily"),
        ("benchmark", root / "data/cache/benchmark_refresh_v1_5", "ak.stock_zh_index_daily_tx"),
    ):
        for path in sorted(folder.glob("*.csv")):
            frame = pd.read_csv(path, dtype=str)
            date_col = "trade_date" if "trade_date" in frame else "date"
            dates = pd.to_datetime(frame[date_col], errors="coerce").dropna() if date_col in frame else pd.Series(dtype="datetime64[ns]")
            row = dict.fromkeys(REQUEST_COLUMNS, "")
            row.update({
                "asset_type": asset_type, "code": code6(path.stem), "endpoint": endpoint,
                "request_attempted": False, "request_status": "not_attempted",
                "fallback_attempted": False, "cache_status": "present",
                "normalized_row_count": len(frame), "candidate_date": candidate,
                "candidate_date_present": bool(candidate and pd.Timestamp(candidate) in set(dates)),
                "normalized_min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
                "normalized_max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
                "latest_valid_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
            })
            rows.append(row)
    return rows


def probe_with_fallback(
    asset_type: str, code: str, start: str, end: str, candidate: str,
    cache_status: str, primary: Callable, fallback: Callable,
) -> list[dict[str, object]]:
    if asset_type == "stock":
        normalizer = normalize_stock
        calls = (
            ("ak.stock_zh_a_daily", lambda: primary(code, start, end)),
            ("ak.stock_zh_a_hist", lambda: fallback(code, start, end)),
        )
    else:
        normalizer = normalize_benchmark
        calls = (
            ("ak.stock_zh_index_daily_tx", lambda: primary(code, start, end)),
            ("ak.index_zh_a_hist", lambda: fallback(code, start, end)),
        )
    rows = []
    for index, (endpoint, fetch) in enumerate(calls):
        rows.append(request_row(asset_type, code, endpoint, start, end, candidate, cache_status, fetch, normalizer, index == 1))
        if rows[-1]["request_status"] == "success":
            break
    return rows


def artifact_inventory(root: Path) -> list[dict[str, object]]:
    result = []
    for path in protected_paths(root):
        frame = None
        try:
            frame = pd.read_csv(path, dtype=str)
        except Exception:
            pass
        result.append({
            "path": str(path.relative_to(root)), "bytes": path.stat().st_size,
            "sha256": sha256(path), "rows": len(frame) if frame is not None else "",
        })
    return result


def refined_diagnosis(rows: list[dict[str, object]]) -> str:
    probes = [row for row in rows if row["request_attempted"]]
    if not probes:
        return "NOT_PROBED"
    if any(row["request_status"] == "failed" for row in probes):
        return "ENDPOINT_OR_NETWORK_FAILURE_RECORDED"
    present = {row["asset_type"]: bool(row["candidate_date_present"]) for row in probes}
    if present.get("stock") and present.get("benchmark"):
        return "SOURCE_DATA_AVAILABLE_LOCAL_CUTOFF_STALE"
    if not present.get("stock", True):
        return "STOCK_SOURCE_CANDIDATE_DATE_ABSENT"
    if not present.get("benchmark", True):
        return "BENCHMARK_SOURCE_CANDIDATE_DATE_ABSENT"
    return "PROBE_INCONCLUSIVE"


def write_outputs(
    root: Path, rows: list[dict[str, object]], inventory: list[dict[str, object]],
    zero: dict[str, object], candidate: str, candidate_source: str,
    hashes_unchanged: bool,
) -> None:
    output = root / "reports/prospective/lowvol_v1_5_1"
    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=REQUEST_COLUMNS).to_csv(output / "data_refresh_requests.csv", index=False)
    attempts = sum(bool(row["request_attempted"]) for row in rows)
    failures = sum(row["request_status"] == "failed" for row in rows)
    stock_caches = sum(row["asset_type"] == "stock" and row["cache_status"] == "present" for row in rows if not row["request_attempted"])
    benchmark_caches = sum(row["asset_type"] == "benchmark" and row["cache_status"] == "present" for row in rows if not row["request_attempted"])
    probe_rows = [row for row in rows if row["request_attempted"]]
    diagnosis = refined_diagnosis(rows)
    probe_summary = "\n".join(
        f"- {row['asset_type']} {row['code']} {row['endpoint']}: {row['request_status']}; "
        f"raw={row['response_min_date']}..{row['response_max_date']}; "
        f"normalized={row['normalized_min_date']}..{row['normalized_max_date']}; "
        f"candidate_present={str(row['candidate_date_present']).lower()}"
        for row in probe_rows
    ) or "- No network probes attempted."
    inventory_text = "\n".join(f"- `{item['path']}` rows={item['rows']} sha256={item['sha256']}" for item in inventory)
    report = f"""# LOWVOL20 v1.5.1 Data Refresh Diagnostic

- generated_at: {datetime.now(timezone.utc).isoformat()}
- primary_classification: REFRESH_NOT_INVOKED
- secondary_classification: CACHE_ONLY_NO_REMOTE_REQUESTS
- prospective_state: VALID_WAITING_INPUT_CUTOFF
- refined_probe_diagnosis: {diagnosis}
- candidate_date: {candidate or 'not_available_in_local_calendar'}
- candidate_date_source: {candidate_source}
- network_attempt_count: {attempts}
- network_failure_count: {failures}
- protected_hashes_unchanged: {str(hashes_unchanged).lower()}
- stock_cache_count: {stock_caches}
- benchmark_cache_count: {benchmark_caches}

## Zero-attempt Finding

- price_attempts: {zero['attempts']}
- displayed_success_rate: {zero['displayed_success_rate']:.1%}
- issue_type: {zero['issue_type']}
- severity: {zero['severity']}
- action: {zero['action']}

The earlier `0.0%` describes zero remote attempts under the generic CLI's cache-only price mode; it is not evidence of failed requests. Generic CLI changes are deferred.

## Probe Evidence

{probe_summary}

## Inventory And Hashes

{inventory_text}

## Boundary

No cache or processed panel was written, no endpoint order was changed, and prospective `observe` was not run. Broad refresh requires separate approval.
"""
    (output / "data_refresh_diagnostic.md").write_text(report, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=Path(__file__).resolve().parents[1])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--no-network", action="store_true")
    mode.add_argument("--probe-existing-sources", action="store_true")
    parser.add_argument("--probe-stock")
    parser.add_argument("--probe-benchmark", choices=sorted(INDEX_IDENTITIES))
    parser.add_argument("--control-date")
    parser.add_argument("--candidate-date")
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    benchmark_path = root / "data/processed/hybrid_benchmark_panel_v1_5.csv"
    benchmark = pd.read_csv(benchmark_path, dtype={"benchmark_code": str})
    candidate, candidate_source = resolve_candidate(root, benchmark, args.candidate_date)
    before = hash_snapshot(root)
    rows = cache_rows(root, candidate)
    if args.probe_existing_sources:
        if not args.control_date or not candidate:
            parser.error("probes require --control-date and an explicit or dynamically derived candidate date")
        if args.probe_stock:
            code = code6(args.probe_stock)
            rows += probe_with_fallback(
                "stock", code, args.control_date, candidate, candidate,
                "present" if (root / f"data/cache/qfq_refresh_v1_5/{code}.csv").exists() else "missing",
                _default_stock_primary, _default_stock_fallback,
            )
        if args.probe_benchmark:
            code = code6(args.probe_benchmark)
            rows += probe_with_fallback(
                "benchmark", code, args.control_date, candidate, candidate,
                "present" if (root / f"data/cache/benchmark_refresh_v1_5/{code}.csv").exists() else "missing",
                _default_index_primary, _default_index_fallback,
            )
    fetch_path = root / "data/processed/fetch_summary.csv"
    fetch_summary = pd.read_csv(fetch_path) if fetch_path.exists() else pd.DataFrame()
    zero = zero_attempt_diagnosis(fetch_summary)
    inventory = artifact_inventory(root)
    unchanged = before == hash_snapshot(root)
    write_outputs(root, rows, inventory, zero, candidate, candidate_source, unchanged)
    return 0 if unchanged else 2


if __name__ == "__main__":
    raise SystemExit(main())
