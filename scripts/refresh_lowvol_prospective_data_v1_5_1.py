"""Prepare and publish append-only prospective LOWVOL20 market data."""

from __future__ import annotations

import argparse
import csv
import hashlib
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
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


VERSION = "v1.5.1"
ATOL, RTOL = 1e-10, 1e-8
APPROVAL_COLUMNS = [
    "refresh_run_id", "parent_refresh_run_id", "cutoff", "price_panel_path",
    "benchmark_panel_path", "price_panel_sha256", "benchmark_panel_sha256",
    "qa_sha256", "approved_at", "publication_status", "decision_maker", "notes",
]
MANIFEST_COLUMNS = [
    "refresh_run_id", "parent_refresh_run_id", "asset_type", "code", "status",
    "primary_endpoint", "endpoint_used", "fallback_attempted", "requested_start",
    "requested_end", "response_min_date", "response_max_date", "normalized_min_date",
    "normalized_max_date", "overlap_row_count", "new_row_count", "slice_path",
    "slice_sha256", "error",
]
CONTINUITY_COLUMNS = [
    "stock_code", "continuity_segment_id", "frozen_anchor_date", "new_segment_start_date",
    "approved_overlap_start_date", "approved_overlap_end_date", "bridge_type", "bridge_parameter",
    "old_frozen_factor", "current_refreshed_factor", "factor_definition", "factor_direction",
    "factor_effective_date", "next_factor_effective_date", "guard_mode", "primary_qfq_source",
    "independent_raw_source", "cash_per_share", "record_date", "ex_date", "official_action_path",
    "official_action_sha256", "factor_raw_path", "factor_raw_sha256", "factor_normalized_path",
    "factor_version_sha256", "forensic_report_path", "forensic_report_sha256", "evidence_status",
    "approval_status", "approved_by", "approved_at", "qfq_display_decimals", "raw_display_decimals",
    "factor_decimal_places", "bridge_parameter_decimal_places", "notes",
]
BRIDGE_COLUMNS = [
    "refresh_run_id", "stock_code", "continuity_segment_id", "status", "bridge_type",
    "bridge_parameter", "registry_sha256", "endpoint_used", "overlap_count", "overlap_failure_count",
    "raw_identity_pass", "corporate_action_return_pass", "independent_raw_pass",
    "later_factor_event_absent", "later_corporate_action_absent", "transformed_new_row_count", "error",
    "retrieved_at", "runtime_factor_sha256", "runtime_action_sha256", "runtime_primary_raw_sha256",
    "runtime_independent_raw_sha256",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ_") + uuid.uuid4().hex[:8]


def report_root(root: Path) -> Path:
    return root / "reports/prospective/lowvol_v1_5_1"


def approval_path(root: Path) -> Path:
    return report_root(root) / "approved_refreshes.csv"


def read_approvals(root: Path) -> pd.DataFrame:
    path = approval_path(root)
    if not path.exists():
        return pd.DataFrame(columns=APPROVAL_COLUMNS)
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if frame.columns.tolist() != APPROVAL_COLUMNS or frame["refresh_run_id"].duplicated().any():
        raise ValueError("Invalid approved refresh ledger")
    return frame


def run_dir(root: Path, run_id: str) -> Path:
    if not run_id or any(char not in "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_" for char in run_id):
        raise ValueError("Invalid refresh_run_id")
    return report_root(root) / "refresh_runs" / run_id


def frozen_paths(root: Path) -> list[Path]:
    paths = [
        root / "data/processed/adjusted_price_panel_v1_5.csv",
        root / "data/processed/hybrid_benchmark_panel_v1_5.csv",
        root / "data/processed/research_universe_lowvol_freeze_20260711.csv",
        root / "reports/prospective/lowvol_v1_5_1/prospective_periods.csv",
        root / "scripts/run_lowvol_locked_grid_prototype_v1_5_1.py",
        root / "tests/test_lowvol_locked_grid_prototype_v1_5_1.py",
        root / "reports/lowvol_locked_grid_prototype_periods_v1_5_1.csv",
        root / "reports/lowvol_locked_grid_prototype_nav_v1_5_1.csv",
        root / "reports/lowvol_locked_grid_prototype_summary_v1_5_1.csv",
        root / "reports/lowvol_locked_grid_prototype_qa_v1_5_1.csv",
        root / "reports/lowvol_locked_grid_prototype_v1_5_1.md",
        root / "reports/lowvol_locked_grid_prototype_v1_5_1_freeze_audit.md",
        root / "reports/lowvol_locked_grid_prototype_v1_5_1_freeze_checks.csv",
        root / "reports/lowvol_locked_grid_prototype_v1_5_1_freeze_manifest.csv",
        root / "reports/lowvol_locked_grid_prototype_v1_5_1_reproduction_diff.csv",
        root / "reports/lowvol_locked_grid_prototype_v1_5_1_signoff.md",
    ]
    paths += sorted((root / "data/cache/qfq_refresh_v1_5").glob("*.csv"))
    paths += sorted((root / "data/cache/benchmark_refresh_v1_5").glob("*.csv"))
    paths += sorted((root / "reports/prospective/lowvol_v1_5_1/refresh_runs/20260713T134837418081Z_b0fd97ac").glob("**/*"))
    paths += sorted((root / "reports/prospective/lowvol_v1_5_1/qfq_forensics_20260713").glob("**/*"))
    return [path for path in paths if path.exists()]


def hash_snapshot(root: Path) -> dict[str, str]:
    return {str(path.relative_to(root)): sha256(path) for path in frozen_paths(root)}


def load_continuity_registry(root: Path, path: Path | None) -> tuple[pd.DataFrame, str]:
    if path is None:
        return pd.DataFrame(columns=CONTINUITY_COLUMNS), ""
    path = path if path.is_absolute() else root / path
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if frame.columns.tolist() != CONTINUITY_COLUMNS:
        raise ValueError("Continuity registry schema mismatch")
    frame["stock_code"] = frame["stock_code"].map(code6)
    if frame["continuity_segment_id"].eq("").any() or frame["continuity_segment_id"].duplicated().any():
        raise ValueError("Continuity segment IDs must be nonempty and unique")
    return frame, sha256(path)


def approved_segment(registry: pd.DataFrame, code: str, end_date: pd.Timestamp) -> pd.Series | None:
    rows = registry[
        registry["stock_code"].eq(code)
        & pd.to_datetime(registry["new_segment_start_date"], errors="raise").le(end_date)
    ]
    if rows.empty:
        return None
    if len(rows) != 1:
        raise ValueError(f"Expected one continuity segment for {code}")
    row = rows.iloc[0]
    if row["evidence_status"] != "confirmed" or row["approval_status"] != "approved":
        raise ValueError(f"Continuity segment is not approved for {code}")
    if not row["approved_by"].strip() or not row["approved_at"].strip():
        raise ValueError(f"Continuity approval identity is incomplete for {code}")
    return row


def verify_evidence_hashes(root: Path, row: pd.Series) -> None:
    for path_field, hash_field in (
        ("official_action_path", "official_action_sha256"),
        ("factor_raw_path", "factor_raw_sha256"),
        ("factor_normalized_path", "factor_version_sha256"),
        ("forensic_report_path", "forensic_report_sha256"),
    ):
        path = root / row[path_field]
        if not path.is_file() or sha256(path).lower() != row[hash_field].lower():
            raise ValueError(f"Continuity evidence hash mismatch: {path_field}")


def rounded_interval(value: float, decimals: int) -> tuple[float, float]:
    half = 0.5 * 10.0 ** (-decimals)
    return value - half, value + half


def intervals_overlap(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return max(left[0], right[0]) <= min(left[1], right[1]) + ATOL


def multiply_intervals(left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float]:
    values = [a * b for a in left for b in right]
    return min(values), max(values)


def return_interval(previous: tuple[float, float], current: tuple[float, float], cash: float = 0.0) -> tuple[float, float]:
    return (current[0] + cash) / previous[1] - 1.0, (current[1] + cash) / previous[0] - 1.0


def default_continuity_evidence_fetcher(code: str, start: str, end: str) -> dict[str, pd.DataFrame]:
    try:
        from scripts.forensics_qfq_overlap_v1_5_1 import (
            default_action_fetcher, default_price_fetcher, normalize_actions, normalize_factor, normalize_price,
        )
    except ImportError:
        from forensics_qfq_overlap_v1_5_1 import (
            default_action_fetcher, default_price_fetcher, normalize_actions, normalize_factor, normalize_price,
        )
    independent_response = default_price_fetcher(code, start, end, "tencent", "")
    factor_response = default_price_fetcher(code, start, end, "sina", "qfq-factor")
    action_response = default_action_fetcher(code)
    try:
        raw_response = default_price_fetcher(code, start, end, "sina", "")
        primary_raw = normalize_price(raw_response, "raw_close")
    except Exception:
        raw_response = pd.DataFrame()
        primary_raw = pd.DataFrame(columns=["trade_date", "raw_close"])
    return {
        "primary_raw_response": raw_response,
        "primary_raw": primary_raw,
        "independent_raw_response": independent_response,
        "independent_raw": normalize_price(independent_response, "raw_close"),
        "factor_response": factor_response,
        "factor": normalize_factor(factor_response, "qfq_factor"),
        "actions_response": action_response,
        "actions": normalize_actions(code, action_response),
    }


def save_continuity_evidence(target: Path, code: str, evidence: dict[str, pd.DataFrame]) -> dict[str, str]:
    output = target / "continuity_evidence" / code
    output.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for name, frame in evidence.items():
        path = output / f"{name}.csv"
        frame.to_csv(path, index=False)
        hashes[name] = sha256(path)
    return hashes


def apply_continuity_bridge(
    root: Path, target: Path, normalized: pd.DataFrame, parent: pd.DataFrame, row: pd.Series,
    endpoint_used: str, cutoff: pd.Timestamp, end_date: pd.Timestamp, evidence_fetcher: Callable,
) -> tuple[pd.DataFrame, dict[str, object]]:
    code = row["stock_code"]
    if endpoint_used != row["primary_qfq_source"]:
        raise ValueError("Continuity source mismatch")
    verify_evidence_hashes(root, row)
    start = row["approved_overlap_start_date"]
    evidence = evidence_fetcher(code, start, end_date.strftime("%Y-%m-%d"))
    evidence_hashes = save_continuity_evidence(target, code, evidence)

    factors = evidence["factor"].copy()
    factors["trade_date"] = pd.to_datetime(factors["trade_date"], errors="raise")
    next_factor = pd.Timestamp(row["next_factor_effective_date"])
    if len(factors[factors["trade_date"].eq(next_factor)]) != 1:
        raise ValueError("Registered factor-effective event is missing or ambiguous")
    later_factor_absent = not (
        factors["trade_date"].gt(next_factor) & factors["trade_date"].le(end_date)
    ).any()
    if not later_factor_absent:
        raise ValueError("Later factor-effective event requires a new continuity segment")
    current = factors[factors["trade_date"].le(pd.Timestamp(row["frozen_anchor_date"]))].sort_values("trade_date")
    if current.empty or current.iloc[-1]["trade_date"] != pd.Timestamp(row["factor_effective_date"]):
        raise ValueError("Current factor effective date mismatch")
    if not np.isclose(float(current.iloc[-1]["qfq_factor"]), float(row["current_refreshed_factor"]), atol=ATOL, rtol=RTOL):
        raise ValueError("Current refreshed factor mismatch")

    actions = evidence["actions"].copy()
    actions["ex_date"] = pd.to_datetime(actions["ex_date"], errors="coerce")
    event = actions[actions["ex_date"].eq(pd.Timestamp(row["ex_date"]))]
    if len(event) != 1:
        raise ValueError("Approved corporate action identity is missing or ambiguous")
    event = event.iloc[0]
    cash_per_share = float(event["cash_dividend_per_10"]) / 10.0
    if (str(event["record_date"]) != row["record_date"]
            or not np.isclose(cash_per_share, float(row["cash_per_share"]), atol=ATOL, rtol=RTOL)):
        raise ValueError("Approved corporate action identity changed")
    later_action_absent = not (
        actions["ex_date"].gt(pd.Timestamp(row["ex_date"])) & actions["ex_date"].le(end_date)
    ).any()
    if not later_action_absent:
        raise ValueError("Later corporate action requires a new continuity segment")

    qfq_decimals = int(row["qfq_display_decimals"])
    raw_decimals = int(row["raw_display_decimals"])
    factor_decimals = int(row["factor_decimal_places"])
    scale = float(row["bridge_parameter"])
    scale_interval = rounded_interval(scale, int(row["bridge_parameter_decimal_places"]))
    frame = normalized.copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
    frame["stock_code"] = frame["stock_code"].map(code6)
    old = parent[parent["stock_code"].eq(code)].copy()
    old["trade_date"] = pd.to_datetime(old["trade_date"], errors="raise")
    overlap = frame[
        frame["trade_date"].between(row["approved_overlap_start_date"], row["approved_overlap_end_date"])
    ].merge(old[["trade_date", "qfq_close"]], on="trade_date", how="inner", suffixes=("_refreshed", "_frozen"))
    expected_count = len(old[old["trade_date"].between(
        row["approved_overlap_start_date"], row["approved_overlap_end_date"]
    )])
    failures = 0
    for item in overlap.itertuples(index=False):
        mapped = multiply_intervals(rounded_interval(float(item.qfq_close_refreshed), qfq_decimals), scale_interval)
        if not intervals_overlap(mapped, rounded_interval(float(item.qfq_close_frozen), qfq_decimals)):
            failures += 1
    if len(overlap) < 5 or len(overlap) != expected_count or failures:
        raise ValueError("Approved overlap reconstruction failed")

    anchor = pd.Timestamp(row["frozen_anchor_date"])
    ex_date = pd.Timestamp(row["ex_date"])
    raw = evidence["primary_raw"].copy()
    independent = evidence["independent_raw"].copy()
    for raw_frame in (raw, independent):
        raw_frame["trade_date"] = pd.to_datetime(raw_frame["trade_date"], errors="raise")
    economic_raw = raw if row["bridge_type"] == "explicit_factor_bridge" else independent
    raw_anchor = economic_raw.loc[economic_raw["trade_date"].eq(anchor), "raw_close"]
    qfq_anchor = frame.loc[frame["trade_date"].eq(anchor), "qfq_close"]
    factor = float(row["current_refreshed_factor"])
    if len(raw_anchor) != 1 or len(qfq_anchor) != 1:
        raise ValueError("Anchor raw/QFQ evidence missing")
    implied_raw = multiply_intervals(
        rounded_interval(float(qfq_anchor.iloc[0]), qfq_decimals), rounded_interval(factor, factor_decimals)
    )
    raw_identity = intervals_overlap(implied_raw, rounded_interval(float(raw_anchor.iloc[0]), raw_decimals))
    if not raw_identity:
        raise ValueError("Raw/QFQ/factor identity failed")

    raw_post = economic_raw.loc[economic_raw["trade_date"].eq(ex_date), "raw_close"]
    independent_anchor = independent.loc[independent["trade_date"].eq(anchor), "raw_close"]
    independent_post = independent.loc[independent["trade_date"].eq(ex_date), "raw_close"]
    qfq_post = frame.loc[frame["trade_date"].eq(ex_date), "qfq_close"]
    if any(len(values) != 1 for values in (raw_post, independent_anchor, independent_post, qfq_post)):
        raise ValueError("Corporate-action boundary evidence missing")
    expected_return = return_interval(
        rounded_interval(float(raw_anchor.iloc[0]), raw_decimals),
        rounded_interval(float(raw_post.iloc[0]), raw_decimals), float(row["cash_per_share"]),
    )
    mapped_return = return_interval(
        rounded_interval(float(old.loc[old["trade_date"].eq(anchor), "qfq_close"].iloc[0]), qfq_decimals),
        multiply_intervals(rounded_interval(float(qfq_post.iloc[0]), qfq_decimals), scale_interval),
    )
    return_pass = intervals_overlap(expected_return, mapped_return)
    independent_return = return_interval(
        rounded_interval(float(independent_anchor.iloc[0]), raw_decimals),
        rounded_interval(float(independent_post.iloc[0]), raw_decimals), float(row["cash_per_share"]),
    )
    independent_pass = intervals_overlap(expected_return, independent_return)
    if not return_pass or not independent_pass:
        raise ValueError("Corporate-action total-return reconciliation failed")

    frame["qfq_close"] = pd.to_numeric(frame["qfq_close"], errors="raise") * scale
    if "adjusted_close" in frame:
        frame["adjusted_close"] = frame["qfq_close"]
    frame["source_qfq"] = frame["source_qfq"].astype(str) + "|" + row["continuity_segment_id"]
    new = frame[frame["trade_date"].gt(cutoff)].reset_index(drop=True)
    return new, {
        "stock_code": code, "continuity_segment_id": row["continuity_segment_id"], "status": "applied",
        "bridge_type": row["bridge_type"], "bridge_parameter": scale, "endpoint_used": endpoint_used,
        "overlap_count": len(overlap), "overlap_failure_count": failures, "raw_identity_pass": raw_identity,
        "corporate_action_return_pass": return_pass, "independent_raw_pass": independent_pass,
        "later_factor_event_absent": later_factor_absent, "later_corporate_action_absent": later_action_absent,
        "transformed_new_row_count": len(new), "error": "",
        "retrieved_at": now(), "runtime_factor_sha256": evidence_hashes["factor_response"],
        "runtime_action_sha256": evidence_hashes["actions_response"],
        "runtime_primary_raw_sha256": evidence_hashes["primary_raw_response"],
        "runtime_independent_raw_sha256": evidence_hashes["independent_raw_response"],
    }


def parent_panels(root: Path) -> tuple[str, Path, Path]:
    approvals = read_approvals(root)
    if approvals.empty:
        return (
            "",
            root / "data/processed/adjusted_price_panel_v1_5.csv",
            root / "data/processed/hybrid_benchmark_panel_v1_5.csv",
        )
    row = approvals.iloc[-1]
    price, benchmark = root / row["price_panel_path"], root / row["benchmark_panel_path"]
    if sha256(price) != row["price_panel_sha256"] or sha256(benchmark) != row["benchmark_panel_sha256"]:
        raise ValueError("Latest approved parent panel hash mismatch")
    return row["refresh_run_id"], price, benchmark


def load_parent(price_path: Path, benchmark_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    stocks = pd.read_csv(price_path, dtype={"stock_code": str})
    benchmarks = pd.read_csv(benchmark_path, dtype={"benchmark_code": str})
    expected_stock = ["stock_code", "trade_date", "qfq_close", "source_qfq", "adjusted_close", "adjusted_flag"]
    expected_benchmark = ["benchmark_code", "trade_date", "close", "instrument_type", "instrument_name", "source"]
    if stocks.columns.tolist() != expected_stock or benchmarks.columns.tolist() != expected_benchmark:
        raise ValueError("Parent panel schema mismatch")
    stocks["stock_code"] = stocks["stock_code"].map(code6)
    benchmarks["benchmark_code"] = benchmarks["benchmark_code"].map(code6)
    stocks["trade_date"] = pd.to_datetime(stocks["trade_date"], errors="raise")
    benchmarks["trade_date"] = pd.to_datetime(benchmarks["trade_date"], errors="raise")
    if stocks.duplicated(["stock_code", "trade_date"]).any() or benchmarks.duplicated(["benchmark_code", "trade_date"]).any():
        raise ValueError("Duplicate parent panel key")
    qfq = pd.to_numeric(stocks["qfq_close"], errors="raise")
    adjusted = pd.to_numeric(stocks["adjusted_close"], errors="raise")
    flag = stocks["adjusted_flag"].astype(str).str.lower().map({"true": True, "1": True, "false": False, "0": False})
    if flag.isna().any() or not flag.all() or (qfq <= 0).any() or not np.isclose(qfq, adjusted, atol=ATOL, rtol=RTOL).all():
        raise ValueError("Invalid parent adjusted/QFQ values")
    if (pd.to_numeric(benchmarks["close"], errors="raise") <= 0).any():
        raise ValueError("Invalid parent benchmark values")
    return stocks, benchmarks


def fetch_ordered(
    code: str, start: str, end: str, primary: Callable, fallback: Callable,
    normalizer: Callable[[str, pd.DataFrame, str], pd.DataFrame], primary_name: str, fallback_name: str,
) -> tuple[pd.DataFrame | None, str, bool, str, str, str]:
    errors = []
    for index, (fetch, name) in enumerate(((primary, primary_name), (fallback, fallback_name))):
        try:
            raw = fetch(code, start, end)
            raw_date = next((column for column in ("trade_date", "date", "日期") if column in raw), None)
            raw_dates = pd.to_datetime(raw[raw_date], errors="raise") if raw_date else pd.Series(dtype="datetime64[ns]")
            if raw_dates.duplicated().any():
                raise ValueError("Duplicate raw date")
            if {"qfq_close", "adjusted_close"}.issubset(raw.columns):
                qfq = pd.to_numeric(raw["qfq_close"], errors="raise")
                adjusted = pd.to_numeric(raw["adjusted_close"], errors="raise")
                if not np.isclose(qfq, adjusted, atol=ATOL, rtol=RTOL).all():
                    raise ValueError("Raw adjusted/QFQ conflict")
            normalized = normalizer(code, raw, name)
            dates = pd.to_datetime(normalized["trade_date"], errors="raise")
            if dates.duplicated().any():
                raise ValueError("Duplicate normalized date")
            return normalized, name, index == 1, " | ".join(errors), (
                raw_dates.min().strftime("%Y-%m-%d") if not raw_dates.empty else ""
            ), (raw_dates.max().strftime("%Y-%m-%d") if not raw_dates.empty else "")
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    return None, "", True, " | ".join(errors), "", ""


def compare_and_slice(
    normalized: pd.DataFrame, parent: pd.DataFrame, code_column: str, code: str,
    value_column: str, cutoff: pd.Timestamp,
) -> tuple[pd.DataFrame, int]:
    normalized = normalized.copy()
    normalized[code_column] = normalized[code_column].map(code6)
    normalized["trade_date"] = pd.to_datetime(normalized["trade_date"], errors="raise")
    values = pd.to_numeric(normalized[value_column], errors="raise")
    if (values <= 0).any() or normalized.duplicated([code_column, "trade_date"]).any():
        raise ValueError("Invalid or duplicate normalized rows")
    old = parent[parent[code_column].eq(code)].set_index("trade_date")
    overlap = normalized[normalized["trade_date"].le(cutoff)].set_index("trade_date")
    if overlap.empty or overlap.index.max() != old.index.max():
        raise ValueError("Missing latest accepted overlap")
    absent = overlap.index.difference(old.index)
    if len(absent):
        raise ValueError(f"New pre-cutoff rows: {list(absent.strftime('%Y-%m-%d'))[:3]}")
    expected = pd.to_numeric(old.loc[overlap.index, value_column], errors="raise").to_numpy()
    actual = pd.to_numeric(overlap[value_column], errors="raise").to_numpy()
    if not np.isclose(actual, expected, atol=ATOL, rtol=RTOL).all():
        raise ValueError("Historical overlap value changed")
    return normalized[normalized["trade_date"].gt(cutoff)].reset_index(drop=True), len(overlap)


def append_csv(parent_path: Path, output_path: Path, rows: pd.DataFrame, columns: list[str]) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(parent_path, output_path)
    prefix = output_path.read_bytes()
    if rows.empty:
        return
    with output_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        for row in rows[columns].itertuples(index=False, name=None):
            writer.writerow(row)
    if not output_path.read_bytes().startswith(prefix):
        raise ValueError("Candidate panel changed its parent byte prefix")


def write_report(path: Path, qa: dict[str, object]) -> None:
    lines = ["# LOWVOL20 Prospective Refresh QA v1.5.1", ""]
    lines += [f"- {key}: {value}" for key, value in qa.items()]
    lines += [
        "", "`observe_allowed=true` means technical data/QA readiness only; it is not human approval.",
        "`prepare --approve-refresh` authorizes this preparation run only; final approval requires `publish --approve`.",
        "No historical cache, panel, report, universe, or prospective ledger was modified.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prepare(
    root: Path, end_date: str, approve_refresh: bool,
    stock_primary: Callable = _default_stock_primary, stock_fallback: Callable = _default_stock_fallback,
    index_primary: Callable = _default_index_primary, index_fallback: Callable = _default_index_fallback,
    refresh_run_id: str | None = None,
    continuity_registry: Path | None = None,
    continuity_evidence_fetcher: Callable = default_continuity_evidence_fetcher,
) -> tuple[int, str]:
    if not approve_refresh:
        raise ValueError("Explicit --approve-refresh is required")
    end = pd.Timestamp(end_date)
    run_id = refresh_run_id or new_run_id()
    target = run_dir(root, run_id)
    if target.exists():
        raise ValueError("Refresh run directory already exists")
    before = hash_snapshot(root)
    registry, registry_hash = load_continuity_registry(root, continuity_registry)
    parent_id, price_path, benchmark_path = parent_panels(root)
    stocks, benchmarks = load_parent(price_path, benchmark_path)
    universe = pd.read_csv(root / "data/processed/research_universe_lowvol_freeze_20260711.csv", dtype=str)
    code_column = "code" if "code" in universe else "stock_code"
    codes = sorted(universe[code_column].map(code6).drop_duplicates())
    if len(codes) != 56:
        raise ValueError("Frozen universe must contain 56 unique codes")
    target.mkdir(parents=True)
    cutoff = benchmarks.loc[benchmarks["benchmark_code"].eq("000300"), "trade_date"].max()
    if end <= cutoff:
        qa = {"refresh_run_id": run_id, "critical_qa_pass": False, "observe_allowed": False, "status": "no_calendar_advancement", "parent_cutoff": cutoff.date(), "requested_end": end.date()}
        pd.DataFrame(columns=MANIFEST_COLUMNS).to_csv(target / "manifest.csv", index=False)
        pd.DataFrame(columns=["asset_type", "code", "status", "error"]).to_csv(target / "failures.csv", index=False)
        processed = target / "processed"
        append_csv(price_path, processed / "adjusted_price_panel_prospective_v1_5_1.csv", pd.DataFrame(), stocks.columns.tolist())
        append_csv(benchmark_path, processed / "hybrid_benchmark_panel_prospective_v1_5_1.csv", pd.DataFrame(), benchmarks.columns.tolist())
        pd.DataFrame([qa]).to_csv(target / "refresh_qa.csv", index=False)
        write_report(target / "refresh_qa.md", qa)
        return 1, run_id

    manifests, failures, stock_new, benchmark_new, bridges = [], [], [], [], []
    for code in codes:
        parent_code = stocks[stocks["stock_code"].eq(code)]
        start = parent_code["trade_date"].max().strftime("%Y-%m-%d")
        candidate_rows = registry[registry["stock_code"].eq(code)]
        if len(candidate_rows) == 1:
            start = min(start, candidate_rows.iloc[0]["approved_overlap_start_date"])
        frame, source, fallback_used, error, raw_min, raw_max = fetch_ordered(
            code, start, end.strftime("%Y-%m-%d"), stock_primary, stock_fallback,
            normalize_stock, "ak.stock_zh_a_daily", "ak.stock_zh_a_hist",
        )
        status, new, overlap = "failed", pd.DataFrame(), 0
        if frame is not None:
            try:
                new, overlap = compare_and_slice(frame, stocks, "stock_code", code, "qfq_close", cutoff)
                status = "primary_failed_fallback_succeeded" if fallback_used and not new.empty else (
                    "success_with_new_rows" if not new.empty else "success_no_new_rows"
                )
            except Exception as exc:
                try:
                    segment = approved_segment(registry, code, end)
                    if segment is None:
                        raise exc
                    new, bridge = apply_continuity_bridge(
                        root, target, frame, stocks, segment, source, cutoff, end, continuity_evidence_fetcher,
                    )
                    bridge["refresh_run_id"] = run_id
                    bridge["registry_sha256"] = registry_hash
                    bridges.append(bridge)
                    overlap = int(bridge["overlap_count"])
                    status = "primary_failed_fallback_succeeded" if fallback_used and not new.empty else (
                        "success_with_new_rows" if not new.empty else "success_no_new_rows"
                    )
                except Exception as bridge_exc:
                    if len(candidate_rows) == 1:
                        candidate = candidate_rows.iloc[0]
                        bridges.append({
                            "refresh_run_id": run_id, "stock_code": code,
                            "continuity_segment_id": candidate["continuity_segment_id"], "status": "failed",
                            "bridge_type": candidate["bridge_type"], "bridge_parameter": candidate["bridge_parameter"],
                            "registry_sha256": registry_hash, "endpoint_used": source, "error": str(bridge_exc),
                        })
                    status, error = "historical_restatement_detected", f"{error} | {bridge_exc}".strip(" |")
        slice_path = target / "slices/stocks" / f"{code}.csv"
        if frame is not None:
            slice_path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(slice_path, index=False)
        if status in ("failed", "historical_restatement_detected"):
            failures.append({"asset_type": "stock", "code": code, "status": status, "error": error})
        elif not new.empty:
            new = new.assign(adjusted_close=new["qfq_close"], adjusted_flag=True)
            stock_new.append(new[["stock_code", "trade_date", "qfq_close", "source_qfq", "adjusted_close", "adjusted_flag"]])
        dates = pd.to_datetime(frame["trade_date"]) if frame is not None else pd.Series(dtype="datetime64[ns]")
        manifests.append({
            "refresh_run_id": run_id, "parent_refresh_run_id": parent_id, "asset_type": "stock", "code": code,
            "status": status, "primary_endpoint": "ak.stock_zh_a_daily", "endpoint_used": source,
            "fallback_attempted": fallback_used, "requested_start": start, "requested_end": end.strftime("%Y-%m-%d"),
            "response_min_date": raw_min, "response_max_date": raw_max,
            "normalized_min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
            "normalized_max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
            "overlap_row_count": overlap, "new_row_count": len(new),
            "slice_path": str(slice_path.relative_to(root)), "slice_sha256": sha256(slice_path) if slice_path.exists() else "", "error": error,
        })

    for code in INDEX_IDENTITIES:
        parent_code = benchmarks[benchmarks["benchmark_code"].eq(code)]
        start = parent_code["trade_date"].max().strftime("%Y-%m-%d")
        frame, source, fallback_used, error, raw_min, raw_max = fetch_ordered(
            code, start, end.strftime("%Y-%m-%d"), index_primary, index_fallback,
            normalize_benchmark, "ak.stock_zh_index_daily_tx", "ak.index_zh_a_hist",
        )
        status, new, overlap = "failed", pd.DataFrame(), 0
        if frame is not None:
            try:
                new, overlap = compare_and_slice(frame, benchmarks, "benchmark_code", code, "close", cutoff)
                status = "primary_failed_fallback_succeeded" if fallback_used and not new.empty else (
                    "success_with_new_rows" if not new.empty else "success_no_new_rows"
                )
            except Exception as exc:
                status, error = "historical_restatement_detected", f"{error} | {exc}".strip(" |")
        slice_path = target / "slices/benchmarks" / f"{code}.csv"
        if frame is not None:
            slice_path.parent.mkdir(parents=True, exist_ok=True)
            frame.to_csv(slice_path, index=False)
        if status in ("failed", "historical_restatement_detected"):
            failures.append({"asset_type": "benchmark", "code": code, "status": status, "error": error})
        elif not new.empty:
            benchmark_new.append(new)
        dates = pd.to_datetime(frame["trade_date"]) if frame is not None else pd.Series(dtype="datetime64[ns]")
        manifests.append({
            "refresh_run_id": run_id, "parent_refresh_run_id": parent_id, "asset_type": "benchmark", "code": code,
            "status": status, "primary_endpoint": "ak.stock_zh_index_daily_tx", "endpoint_used": source,
            "fallback_attempted": fallback_used, "requested_start": start, "requested_end": end.strftime("%Y-%m-%d"),
            "response_min_date": raw_min, "response_max_date": raw_max,
            "normalized_min_date": dates.min().strftime("%Y-%m-%d") if not dates.empty else "",
            "normalized_max_date": dates.max().strftime("%Y-%m-%d") if not dates.empty else "",
            "overlap_row_count": overlap, "new_row_count": len(new),
            "slice_path": str(slice_path.relative_to(root)), "slice_sha256": sha256(slice_path) if slice_path.exists() else "", "error": error,
        })

    manifest = pd.DataFrame(manifests, columns=MANIFEST_COLUMNS)
    manifest.to_csv(target / "manifest.csv", index=False)
    pd.DataFrame(failures, columns=["asset_type", "code", "status", "error"]).to_csv(target / "failures.csv", index=False)
    pd.DataFrame(bridges, columns=BRIDGE_COLUMNS).to_csv(target / "continuity_bridges.csv", index=False)
    approved_applicable = registry[
        registry["approval_status"].eq("approved")
        & pd.to_datetime(registry["new_segment_start_date"], errors="raise").le(end)
    ]
    applied_bridges = [row for row in bridges if row.get("status") == "applied"]
    failed_bridges = [row for row in bridges if row.get("status") == "failed"]
    critical = not failures and len(manifest) == 59 and len(applied_bridges) == len(approved_applicable)
    stock_delta = pd.concat(stock_new, ignore_index=True) if stock_new else pd.DataFrame(columns=stocks.columns)
    benchmark_delta = pd.concat(benchmark_new, ignore_index=True) if benchmark_new else pd.DataFrame(columns=benchmarks.columns)
    processed = target / "processed"
    price_out = processed / "adjusted_price_panel_prospective_v1_5_1.csv"
    benchmark_out = processed / "hybrid_benchmark_panel_prospective_v1_5_1.csv"
    if critical:
        stock_delta["trade_date"] = pd.to_datetime(stock_delta["trade_date"]).dt.strftime("%Y-%m-%d")
        benchmark_delta["trade_date"] = pd.to_datetime(benchmark_delta["trade_date"]).dt.strftime("%Y-%m-%d")
        stock_delta = stock_delta.sort_values(["stock_code", "trade_date"])
        benchmark_delta = benchmark_delta.sort_values(["benchmark_code", "trade_date"])
        append_csv(price_path, price_out, stock_delta, stocks.columns.tolist())
        append_csv(benchmark_path, benchmark_out, benchmark_delta, benchmarks.columns.tolist())
        frozen_price = root / "data/processed/adjusted_price_panel_v1_5.csv"
        frozen_benchmark = root / "data/processed/hybrid_benchmark_panel_v1_5.csv"
        critical = price_out.read_bytes().startswith(frozen_price.read_bytes()) and benchmark_out.read_bytes().startswith(frozen_benchmark.read_bytes())
        combined_stocks, combined_benchmarks = load_parent(price_out, benchmark_out)
        latest = combined_benchmarks.groupby("benchmark_code")["trade_date"].max()
        critical = critical and set(latest.index) == set(INDEX_IDENTITIES) and latest.nunique() == 1 and latest["000300"] > cutoff
    qa = {
        "refresh_run_id": run_id, "parent_refresh_run_id": parent_id,
        "critical_qa_pass": critical, "observe_allowed": critical,
        "status": "prepared_qa_pass" if critical else "prepared_qa_fail",
        "parent_cutoff": cutoff.strftime("%Y-%m-%d"), "requested_end": end.strftime("%Y-%m-%d"),
        "stock_count": len(codes), "benchmark_count": 3, "failure_count": len(failures),
        "stock_new_row_count": len(stock_delta), "benchmark_new_row_count": len(benchmark_delta),
        "continuity_registry_sha256": registry_hash,
        "continuity_approved_count": len(approved_applicable), "continuity_applied_count": len(applied_bridges),
        "continuity_failure_count": len(failed_bridges),
        "price_panel_sha256": sha256(price_out) if price_out.exists() else "",
        "benchmark_panel_sha256": sha256(benchmark_out) if benchmark_out.exists() else "",
        "frozen_price_sha256": sha256(root / "data/processed/adjusted_price_panel_v1_5.csv"),
        "frozen_benchmark_sha256": sha256(root / "data/processed/hybrid_benchmark_panel_v1_5.csv"),
        "frozen_universe_sha256": sha256(root / "data/processed/research_universe_lowvol_freeze_20260711.csv"),
        "frozen_hashes_unchanged": before == hash_snapshot(root),
        "formal_performance_conclusion_allowed": False, "execution_sim_ready": False,
        "no_investment_conclusion": True,
    }
    if not qa["frozen_hashes_unchanged"]:
        qa["critical_qa_pass"] = qa["observe_allowed"] = False
        qa["status"] = "prepared_qa_fail"
    pd.DataFrame([qa]).to_csv(target / "refresh_qa.csv", index=False)
    write_report(target / "refresh_qa.md", qa)
    return (0 if qa["critical_qa_pass"] else 2), run_id


def append_cache(path: Path, rows: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    before = path.read_bytes() if path.exists() else b""
    rows.to_csv(path, mode="a", header=not path.exists(), index=False, lineterminator="\n")
    if before and not path.read_bytes().startswith(before):
        raise ValueError(f"Cache prefix changed: {path}")


def expected_cache_rows(root: Path, approvals: pd.DataFrame, asset_type: str, code: str) -> pd.DataFrame:
    frames = []
    for approval in approvals.itertuples(index=False):
        target = run_dir(root, approval.refresh_run_id)
        qa = pd.read_csv(target / "refresh_qa.csv", dtype=str, keep_default_na=False).iloc[0]
        manifest = pd.read_csv(target / "manifest.csv", dtype=str, keep_default_na=False)
        rows = manifest[(manifest["asset_type"] == asset_type) & (manifest["code"].map(code6) == code)]
        if len(rows) != 1:
            raise ValueError("Approved refresh manifest lineage is incomplete")
        slice_path = root / rows.iloc[0]["slice_path"]
        if sha256(slice_path) != rows.iloc[0]["slice_sha256"]:
            raise ValueError("Approved refresh slice hash mismatch")
        frame = pd.read_csv(slice_path, dtype=str, keep_default_na=False)
        frame = frame[pd.to_datetime(frame["trade_date"], errors="raise") > pd.Timestamp(qa["parent_cutoff"])]
        frames.append(frame)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def publish(root: Path, refresh_run_id: str, approve: bool, decision_maker: str, notes: str) -> int:
    if not approve:
        raise ValueError("Explicit --approve is required")
    if not decision_maker.strip() or not notes.strip():
        raise ValueError("Nonempty --decision-maker and --notes are required")
    target = run_dir(root, refresh_run_id)
    approvals = read_approvals(root)
    if refresh_run_id in set(approvals["refresh_run_id"]):
        raise ValueError("Refresh run already approved")
    qa_path = target / "refresh_qa.csv"
    qa = pd.read_csv(qa_path, dtype=str, keep_default_na=False).iloc[0]
    if qa["critical_qa_pass"].lower() != "true" or qa["observe_allowed"].lower() != "true":
        raise ValueError("Refresh run QA does not allow publication")
    current_parent, _, _ = parent_panels(root)
    if qa["parent_refresh_run_id"] != current_parent:
        raise ValueError("Refresh parent is no longer latest approved run")
    price = target / "processed/adjusted_price_panel_prospective_v1_5_1.csv"
    benchmark = target / "processed/hybrid_benchmark_panel_prospective_v1_5_1.csv"
    if sha256(price) != qa["price_panel_sha256"] or sha256(benchmark) != qa["benchmark_panel_sha256"]:
        raise ValueError("Prepared panel hash mismatch")
    frozen = {
        "frozen_price_sha256": root / "data/processed/adjusted_price_panel_v1_5.csv",
        "frozen_benchmark_sha256": root / "data/processed/hybrid_benchmark_panel_v1_5.csv",
        "frozen_universe_sha256": root / "data/processed/research_universe_lowvol_freeze_20260711.csv",
    }
    if any(sha256(path) != qa[key] for key, path in frozen.items()):
        raise ValueError("Frozen input changed after refresh preparation")
    manifest = pd.read_csv(target / "manifest.csv", dtype={"code": str}, keep_default_na=False)
    cutoff = pd.Timestamp(qa["parent_cutoff"])
    cache_writes = []
    for row in manifest.itertuples(index=False):
        if not row.slice_path:
            continue
        slice_path = root / row.slice_path
        if sha256(slice_path) != row.slice_sha256:
            raise ValueError("Prepared slice hash mismatch")
        frame = pd.read_csv(slice_path, dtype=str, keep_default_na=False)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
        new = frame[frame["trade_date"].gt(cutoff)].copy()
        new["trade_date"] = new["trade_date"].dt.strftime("%Y-%m-%d")
        cache = root / f"data/cache/prospective_lowvol_v1_5_1/{'stocks' if row.asset_type == 'stock' else 'benchmarks'}/{code6(row.code)}.csv"
        expected = expected_cache_rows(root, approvals, row.asset_type, code6(row.code))
        if cache.exists():
            old = pd.read_csv(cache, dtype=str, keep_default_na=False)
            if expected.empty or old.columns.tolist() != expected.columns.tolist() or not old.reset_index(drop=True).equals(expected.reset_index(drop=True)):
                raise ValueError("Prospective cache does not match approved lineage")
            if not new.empty and not old.empty and pd.to_datetime(new["trade_date"]).min() <= pd.to_datetime(old["trade_date"]).max():
                raise ValueError("Prospective cache append is not strictly newer")
        elif not expected.empty:
            raise ValueError("Approved prospective cache is missing")
        if not new.empty:
            cache_writes.append((cache, new))
    for cache, new in cache_writes:
        append_cache(cache, new)
    ledger = approval_path(root)
    ledger.parent.mkdir(parents=True, exist_ok=True)
    values = {
        "refresh_run_id": refresh_run_id, "parent_refresh_run_id": qa["parent_refresh_run_id"],
        "cutoff": pd.read_csv(benchmark, dtype=str)["trade_date"].max(),
        "price_panel_path": str(price.relative_to(root)), "benchmark_panel_path": str(benchmark.relative_to(root)),
        "price_panel_sha256": sha256(price), "benchmark_panel_sha256": sha256(benchmark),
        "qa_sha256": sha256(qa_path), "approved_at": now(), "publication_status": "approved",
        "decision_maker": decision_maker.strip(), "notes": notes.strip(),
    }
    pd.DataFrame([values], columns=APPROVAL_COLUMNS).to_csv(ledger, mode="a", header=not ledger.exists(), index=False)
    read_approvals(root)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "publish"))
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--end-date")
    parser.add_argument("--refresh-run-id")
    parser.add_argument("--approve-refresh", action="store_true", help="Authorize network preparation only; not final data approval")
    parser.add_argument("--approve", action="store_true", help="Record final human data approval during publish")
    parser.add_argument("--decision-maker")
    parser.add_argument("--notes")
    parser.add_argument("--continuity-registry")
    args = parser.parse_args(argv)
    root = Path(args.project_root).resolve()
    try:
        if args.command == "prepare":
            if not args.end_date:
                raise ValueError("--end-date is required")
            code, run_id = prepare(
                root, args.end_date, args.approve_refresh, refresh_run_id=args.refresh_run_id,
                continuity_registry=Path(args.continuity_registry) if args.continuity_registry else None,
            )
            print(f"refresh_run_id={run_id}")
            return code
        if not args.refresh_run_id:
            raise ValueError("--refresh-run-id is required")
        return publish(root, args.refresh_run_id, args.approve, args.decision_maker or "", args.notes or "")
    except Exception as exc:
        print(f"critical_error={exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
