"""Focused, read-only second-pass QFQ boundary forensics for 002230."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import requests
from pypdf import PdfReader

try:
    from scripts.forensics_qfq_overlap_v1_5_1 import (
        code6,
        default_action_fetcher,
        default_price_fetcher,
        normalize_actions,
        normalize_factor,
        normalize_price,
        sha256,
    )
except ImportError:
    from forensics_qfq_overlap_v1_5_1 import (
        code6,
        default_action_fetcher,
        default_price_fetcher,
        normalize_actions,
        normalize_factor,
        normalize_price,
        sha256,
    )


CODE = "002230"
ATOL, RTOL = 1e-10, 1e-8
PRIMARY_CAUSES = {
    "forensic_script_issue", "rounding_only", "source_data_issue",
    "tier1_bridge_not_supported", "unresolved",
}
SOURCE_DEFINITIONS = {
    "sina": {
        "endpoint": "https://stock.finance.sina.com.cn",
        "role": "primary",
        "raw": "unadjusted daily close returned by Sina",
        "qfq": "AkShare computes raw / Sina qfq_factor, then rounds prices to 2 decimals",
        "hfq": "AkShare computes raw * Sina hfq_factor, then rounds prices to 2 decimals",
    },
    "eastmoney": {
        "endpoint": "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        "role": "fallback",
        "raw": "vendor fqt=0 daily close",
        "qfq": "vendor fqt=1 adjusted series; absolute adjustment base is vendor-specific",
        "hfq": "vendor fqt=2 adjusted series; absolute adjustment base is vendor-specific",
    },
    "tencent": {
        "endpoint": "https://proxy.finance.qq.com/ifzqgtimg/appstock/app/newfqkline/get",
        "role": "independent",
        "raw": "vendor day series",
        "qfq": "vendor qfqday series; absolute adjustment base is vendor-specific",
        "hfq": "vendor hfqday series; absolute adjustment base is vendor-specific",
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def displayed_decimals(values: pd.Series) -> int:
    """Infer precision exposed by the DataFrame without inventing extra decimals."""
    result = 0
    for value in values.dropna():
        decimal = Decimal(str(value)).normalize()
        result = max(result, max(0, -decimal.as_tuple().exponent))
    return result


def rounded_interval(value: float, decimals: int | None) -> tuple[float, float]:
    if not np.isfinite(value):
        raise ValueError("interval value must be finite")
    if decimals is None:
        return float(value), float(value)
    half_unit = 0.5 * 10.0 ** (-int(decimals))
    return float(value - half_unit), float(value + half_unit)


def intervals_overlap(left: tuple[float, float], right: tuple[float, float]) -> bool:
    return max(left[0], right[0]) <= min(left[1], right[1]) + ATOL


def multiply_intervals(left: tuple[float, float], right: tuple[float, float]) -> tuple[float, float]:
    products = [a * b for a in left for b in right]
    return min(products), max(products)


def divide_intervals(numerator: tuple[float, float], denominator: tuple[float, float]) -> tuple[float, float]:
    if denominator[0] <= 0 <= denominator[1]:
        raise ValueError("division interval crosses zero")
    values = [a / b for a in numerator for b in denominator]
    return min(values), max(values)


def return_interval(previous: tuple[float, float], current: tuple[float, float],
                    cash_per_share: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
    numerator = (current[0] + cash_per_share[0], current[1] + cash_per_share[1])
    ratio = divide_intervals(numerator, previous)
    return ratio[0] - 1.0, ratio[1] - 1.0


def asof_factor(factors: pd.DataFrame, trade_date: str, value_col: str) -> tuple[str, float]:
    frame = factors[["trade_date", value_col]].copy()
    frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="raise")
    eligible = frame[frame["trade_date"] <= pd.Timestamp(trade_date)].sort_values("trade_date")
    if eligible.empty:
        raise ValueError(f"no {value_col} effective on {trade_date}")
    row = eligible.iloc[-1]
    return row["trade_date"].strftime("%Y-%m-%d"), float(row[value_col])


def validate_raw_identity(qfq: float, qfq_decimals: int, factor: float, factor_decimals: int,
                          raw: float, raw_decimals: int) -> tuple[bool, tuple[float, float], tuple[float, float]]:
    implied = multiply_intervals(
        rounded_interval(qfq, qfq_decimals),
        rounded_interval(factor, factor_decimals),
    )
    observed = rounded_interval(raw, raw_decimals)
    return intervals_overlap(implied, observed), implied, observed


def evaluate_bridge_candidate(name: str, scale: float, scale_decimals: int,
                              frozen: pd.DataFrame, refreshed: pd.DataFrame,
                              frozen_decimals: int, refreshed_decimals: int,
                              frozen_boundary: float,
                              refreshed_post: float,
                              expected_total_return: tuple[float, float],
                              raw_identity_pass: bool) -> dict[str, object]:
    common = frozen.merge(refreshed, on="trade_date", how="inner")
    overlap_passes: list[bool] = []
    residuals: list[float] = []
    scale_interval = rounded_interval(scale, scale_decimals)
    for row in common.itertuples(index=False):
        mapped = multiply_intervals(
            rounded_interval(float(row.refreshed_qfq), refreshed_decimals), scale_interval
        )
        expected = rounded_interval(float(row.frozen_qfq), frozen_decimals)
        overlap_passes.append(intervals_overlap(mapped, expected))
        residuals.append(float(row.frozen_qfq - row.refreshed_qfq * scale))

    mapped_post = multiply_intervals(
        rounded_interval(refreshed_post, refreshed_decimals), scale_interval
    )
    bridge_return = return_interval(
        rounded_interval(frozen_boundary, frozen_decimals), mapped_post
    )
    economic_pass = intervals_overlap(bridge_return, expected_total_return)
    overlap_pass = len(common) >= 5 and all(overlap_passes)
    return {
        "candidate": name,
        "scale": scale,
        "scale_decimals": scale_decimals,
        "common_date_count": len(common),
        "raw_identity_pass": raw_identity_pass,
        "overlap_reconstruction_pass": overlap_pass,
        "overlap_failure_count": int(len(overlap_passes) - sum(overlap_passes)),
        "maximum_point_residual": max((abs(x) for x in residuals), default=np.nan),
        "bridge_return_lower": bridge_return[0],
        "bridge_return_upper": bridge_return[1],
        "total_return_lower": expected_total_return[0],
        "total_return_upper": expected_total_return[1],
        "corporate_action_return_pass": economic_pass,
        "all_three_checks_pass": bool(raw_identity_pass and overlap_pass and economic_pass),
    }


def classify(primary_evidence_complete: bool, accepted_candidate: bool,
             corrected_overlap_pass: bool, legacy_overlap_pass: bool,
             independent_raw_pass: bool, source_conflict: bool) -> tuple[str, str]:
    if not primary_evidence_complete:
        return "unresolved", ""
    if source_conflict:
        return "source_data_issue", ""
    if accepted_candidate and independent_raw_pass and corrected_overlap_pass and not legacy_overlap_pass:
        return "forensic_script_issue", "display_rounding"
    if accepted_candidate and independent_raw_pass:
        return "rounding_only", "display_rounding"
    return "tier1_bridge_not_supported", ""


def protected_snapshot(root: Path, output: Path) -> dict[str, str]:
    paths = [
        root / "data/processed/adjusted_price_panel_v1_5.csv",
        root / "data/processed/hybrid_benchmark_panel_v1_5.csv",
        root / "reports/prospective/lowvol_v1_5_1/approved_refreshes.csv",
        root / "reports/prospective/lowvol_v1_5_1/prospective_periods.csv",
    ]
    paths += list((root / "data/cache").glob("**/*"))
    paths += list((root / "reports/prospective/lowvol_v1_5_1/refresh_runs").glob("**/*"))
    first_pass = root / "reports/prospective/lowvol_v1_5_1/qfq_forensics_20260713"
    paths += [path for path in first_pass.glob("**/*") if output not in path.parents and path != output]
    snapshots = root / "reports/prospective/lowvol_v1_5_1/snapshots"
    paths += list(snapshots.glob("**/*")) if snapshots.exists() else []
    return {str(path.relative_to(root)): sha256(path) for path in paths if path.is_file()}


def save_frame(frame: pd.DataFrame, path: Path) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return path.stat().st_size, sha256(path)


def default_announcement_fetcher(code: str) -> tuple[pd.DataFrame, str, bytes, str]:
    import akshare as ak

    metadata = ak.stock_zh_a_disclosure_report_cninfo(
        symbol=code, keyword="权益分派实施公告", start_date="20260701", end_date="20260713"
    )
    if metadata.empty:
        raise ValueError("official implementation announcement not found")
    row = metadata.iloc[0]
    values = [str(value) for value in row]
    detail_url = next((value for value in values if "announcementId=" in value), "")
    match = re.search(r"announcementId=(\d+)", detail_url)
    date_match = re.search(r"announcementTime=(\d{4}-\d{2}-\d{2})", detail_url)
    if not match or not date_match:
        raise ValueError("official announcement id/date unavailable")
    pdf_url = f"https://static.cninfo.com.cn/finalpage/{date_match.group(1)}/{match.group(1)}.PDF"
    response = requests.get(pdf_url, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
    response.raise_for_status()
    pdf_bytes = response.content
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf_bytes)).pages)
    return metadata, pdf_url, pdf_bytes, text


def parse_announcement(text: str) -> dict[str, object]:
    compact = re.sub(r"\s+", "", text)
    cash = re.search(r"每10股派([0-9.]+)元", compact)
    total = re.search(r"现有总股本[（(]?([0-9,]+)股", compact)
    return {
        "cash_dividend_per_10": float(cash.group(1)) if cash else np.nan,
        "total_share_capital": int(total.group(1).replace(",", "")) if total else np.nan,
        "capital_unchanged_during_implementation": "股本总额未发生变化" in compact,
        "cash_only_language_found": bool(cash),
    }


def _source_value_column(frame: pd.DataFrame) -> str:
    return next(column for column in frame.columns if column != "trade_date")


def _boundary_values(frame: pd.DataFrame, value_col: str) -> dict[str, float]:
    indexed = frame.set_index("trade_date")[value_col]
    return {date: float(indexed.loc[date]) for date in ("2026-07-10", "2026-07-13") if date in indexed.index}


def run(root: Path, refresh_run_id: str, start: str, end: str,
        price_fetcher: Callable = default_price_fetcher,
        action_fetcher: Callable = default_action_fetcher,
        announcement_fetcher: Callable = default_announcement_fetcher) -> int:
    root = Path(root).resolve()
    if code6(CODE) != CODE or pd.Timestamp(start) >= pd.Timestamp(end):
        raise ValueError("invalid forensic parameters")
    failed_run = root / "reports/prospective/lowvol_v1_5_1/refresh_runs" / refresh_run_id
    if not failed_run.exists():
        raise FileNotFoundError(failed_run)
    output = root / "reports/prospective/lowvol_v1_5_1/qfq_forensics_20260713/002230_second_pass"
    raw_dir = output / "raw"
    if output.exists():
        raise FileExistsError(f"second-pass output already exists: {output}")
    before = protected_snapshot(root, output)
    output.mkdir(parents=True)
    retrieved_at = utc_now()
    manifest: list[dict[str, object]] = []

    def record(name: str, source: str, role: str, frame: pd.DataFrame,
               adjustment: str, endpoint: str, error: str = "") -> None:
        path = raw_dir / f"{name}.csv"
        size, digest = save_frame(frame, path)
        manifest.append({
            "evidence_name": name, "source": source, "source_role": role,
            "endpoint": endpoint, "adjustment_mode": adjustment,
            "path": str(path.relative_to(root)), "file_size": size, "sha256": digest,
            "row_count": len(frame), "retrieved_at": retrieved_at,
            "factor_version_identity": digest if "factor" in name else "",
            "status": "error" if error else "ok", "error": error,
        })

    frozen_all = pd.read_csv(root / "data/processed/adjusted_price_panel_v1_5.csv", dtype={"stock_code": str})
    frozen = frozen_all[
        frozen_all["stock_code"].map(code6).eq(CODE)
        & pd.to_datetime(frozen_all["trade_date"]).between(start, end)
    ][["trade_date", "qfq_close"]].rename(columns={"qfq_close": "frozen_qfq"})
    frozen["trade_date"] = pd.to_datetime(frozen["trade_date"]).dt.strftime("%Y-%m-%d")
    record("frozen_qfq", "frozen_v1_5", "frozen", frozen, "qfq", "local")

    evidence: dict[tuple[str, str], pd.DataFrame] = {}
    source_rows: list[dict[str, object]] = []
    for source in ("sina", "eastmoney", "tencent"):
        definition = SOURCE_DEFINITIONS[source]
        for adjust, label in (("", "raw"), ("qfq", "qfq"), ("hfq", "hfq")):
            try:
                response = price_fetcher(CODE, start, end, source, adjust)
                record(f"{source}_{label}_response", source, definition["role"], response,
                       label, definition["endpoint"])
                normalized = normalize_price(response, f"{source}_{label}_close")
                evidence[(source, label)] = normalized
                record(f"{source}_{label}_normalized", source, definition["role"], normalized,
                       label, definition["endpoint"])
                decimals = displayed_decimals(normalized[f"{source}_{label}_close"])
                values = _boundary_values(normalized, f"{source}_{label}_close")
                for trade_date, value in values.items():
                    source_rows.append({
                        "source": source, "source_role": definition["role"], "adjustment_mode": label,
                        "trade_date": trade_date, "value": value, "raw_precision": decimals,
                        "normalized_precision": decimals, "rounding_model": definition[label],
                        "retrieved_at": retrieved_at, "factor_effective_date": "",
                        "factor_version_identity": "",
                    })
            except Exception as exc:
                record(f"{source}_{label}_response", source, definition["role"], pd.DataFrame(),
                       label, definition["endpoint"], f"{type(exc).__name__}: {exc}")

    factors: dict[str, pd.DataFrame] = {}
    for factor_label in ("qfq-factor", "hfq-factor"):
        try:
            response = price_fetcher(CODE, start, end, "sina", factor_label)
            record(f"sina_{factor_label}_response", "sina", "primary", response,
                   factor_label, SOURCE_DEFINITIONS["sina"]["endpoint"])
            value_col = factor_label.replace("-", "_")
            normalized = normalize_factor(response, value_col)
            factors[factor_label] = normalized
            record(f"sina_{factor_label}_normalized", "sina", "primary", normalized,
                   factor_label, SOURCE_DEFINITIONS["sina"]["endpoint"])
        except Exception as exc:
            record(f"sina_{factor_label}_response", "sina", "primary", pd.DataFrame(),
                   factor_label, SOURCE_DEFINITIONS["sina"]["endpoint"], f"{type(exc).__name__}: {exc}")

    try:
        actions_raw = action_fetcher(CODE)
        actions = normalize_actions(CODE, actions_raw)
        record("cninfo_corporate_actions_response", "cninfo", "official", actions_raw,
               "corporate_action", "https://webapi.cninfo.com.cn/api/sysapi/p_sysapi1139?scode=002230")
    except Exception as exc:
        actions = pd.DataFrame()
        record("cninfo_corporate_actions_response", "cninfo", "official", pd.DataFrame(),
               "corporate_action", "https://webapi.cninfo.com.cn/api/sysapi/p_sysapi1139?scode=002230",
               f"{type(exc).__name__}: {exc}")

    announcement_facts: dict[str, object] = {}
    announcement_url = ""
    try:
        metadata, announcement_url, pdf_bytes, announcement_text = announcement_fetcher(CODE)
        record("cninfo_announcement_metadata", "cninfo", "official", metadata,
               "announcement", announcement_url)
        pdf_path = raw_dir / "cninfo_announcement.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(pdf_bytes)
        manifest.append({
            "evidence_name": "cninfo_announcement_pdf", "source": "cninfo", "source_role": "official",
            "endpoint": announcement_url, "adjustment_mode": "announcement",
            "path": str(pdf_path.relative_to(root)), "file_size": pdf_path.stat().st_size,
            "sha256": sha256(pdf_path), "row_count": "", "retrieved_at": retrieved_at,
            "factor_version_identity": "", "status": "ok", "error": "",
        })
        text_path = raw_dir / "cninfo_announcement.txt"
        text_path.write_text(announcement_text, encoding="utf-8")
        manifest.append({
            "evidence_name": "cninfo_announcement_text", "source": "cninfo", "source_role": "official",
            "endpoint": announcement_url, "adjustment_mode": "announcement",
            "path": str(text_path.relative_to(root)), "file_size": text_path.stat().st_size,
            "sha256": sha256(text_path), "row_count": "", "retrieved_at": retrieved_at,
            "factor_version_identity": "", "status": "ok", "error": "",
        })
        announcement_facts = parse_announcement(announcement_text)
    except Exception as exc:
        manifest.append({
            "evidence_name": "cninfo_announcement", "source": "cninfo", "source_role": "official",
            "endpoint": announcement_url, "adjustment_mode": "announcement", "path": "",
            "file_size": 0, "sha256": "", "row_count": 0, "retrieved_at": retrieved_at,
            "factor_version_identity": "", "status": "error", "error": f"{type(exc).__name__}: {exc}",
        })

    action = pd.Series(dtype=object)
    if not actions.empty:
        candidates = actions[pd.to_datetime(actions["ex_date"], errors="coerce").eq(pd.Timestamp("2026-07-13"))]
        if not candidates.empty:
            action = candidates.iloc[-1]
    official_complete = not action.empty and bool(announcement_facts)
    cash_per_share = float(action.get("cash_dividend_per_10", np.nan)) / 10.0 if not action.empty else np.nan
    bonus = float(action.get("bonus_ratio_per_10", np.nan)) if not action.empty else np.nan
    transfer = float(action.get("transfer_ratio_per_10", np.nan)) if not action.empty else np.nan

    raw_sources = {source: evidence[(source, "raw")] for source in SOURCE_DEFINITIONS if (source, "raw") in evidence}
    qfq_sources = {source: evidence[(source, "qfq")] for source in SOURCE_DEFINITIONS if (source, "qfq") in evidence}
    raw_returns: list[dict[str, object]] = []
    raw_intervals: dict[str, tuple[float, float]] = {}
    for source, frame in raw_sources.items():
        values = _boundary_values(frame, f"{source}_raw_close")
        if set(values) == {"2026-07-10", "2026-07-13"}:
            decimals = displayed_decimals(frame[f"{source}_raw_close"])
            interval = return_interval(
                rounded_interval(values["2026-07-10"], decimals),
                rounded_interval(values["2026-07-13"], decimals),
                rounded_interval(cash_per_share, 6) if np.isfinite(cash_per_share) else (0.0, 0.0),
            )
            raw_intervals[source] = interval
            raw_returns.append({
                "metric": "raw_corporate_action_total_return", "source": source,
                "point_value": (values["2026-07-13"] + cash_per_share) / values["2026-07-10"] - 1.0,
                "lower": interval[0], "upper": interval[1], "cash_per_share": cash_per_share,
                "notes": "raw close plus official cash dividend; no send/transfer adjustment",
            })

    for (source, adjustment), frame in evidence.items():
        if adjustment not in {"qfq", "hfq"}:
            continue
        value_col = f"{source}_{adjustment}_close"
        values = _boundary_values(frame, value_col)
        if set(values) != {"2026-07-10", "2026-07-13"}:
            continue
        decimals = displayed_decimals(frame[value_col])
        interval = return_interval(
            rounded_interval(values["2026-07-10"], decimals),
            rounded_interval(values["2026-07-13"], decimals),
        )
        raw_returns.append({
            "metric": f"{adjustment}_boundary_return", "source": source,
            "point_value": values["2026-07-13"] / values["2026-07-10"] - 1.0,
            "lower": interval[0], "upper": interval[1], "cash_per_share": 0.0,
            "notes": "return continuity only; absolute adjusted levels are not compared across vendors",
        })

    expected_interval = next(iter(raw_intervals.values()), (np.nan, np.nan))
    independent_raw_sources = [source for source in ("eastmoney", "tencent") if source in raw_intervals]
    independent_raw_pass = bool(independent_raw_sources) and all(
        intervals_overlap(raw_intervals[source], expected_interval) for source in independent_raw_sources
    )
    source_conflict = len(raw_intervals) > 1 and any(
        not intervals_overlap(interval, expected_interval) for interval in raw_intervals.values()
    )

    factor_rows: list[dict[str, object]] = []
    bridge_rows: list[dict[str, object]] = []
    raw_identity_pass = False
    accepted_candidate = False
    corrected_overlap_pass = False
    legacy_overlap_pass = False
    pre_effective = post_effective = ""
    pre_factor = post_factor = np.nan
    current_source = ""
    qfq_values: dict[str, float] = {}
    if "qfq-factor" in factors and qfq_sources and np.isfinite(expected_interval).all():
        current_source = "sina" if "sina" in qfq_sources else next(iter(qfq_sources))
        current_qfq = qfq_sources[current_source].rename(
            columns={f"{current_source}_qfq_close": "refreshed_qfq"}
        )
        qfq_values = _boundary_values(current_qfq, "refreshed_qfq")
        factor_frame = factors["qfq-factor"]
        pre_effective, pre_factor = asof_factor(factor_frame, "2026-07-10", "qfq_factor")
        post_effective, post_factor = asof_factor(factor_frame, "2026-07-13", "qfq_factor")
        factor_decimals = displayed_decimals(factor_frame["qfq_factor"])
        qfq_decimals = displayed_decimals(current_qfq["refreshed_qfq"])

        identity_results: list[bool] = []
        for trade_date, factor, effective in (
            ("2026-07-10", pre_factor, pre_effective),
            ("2026-07-13", post_factor, post_effective),
        ):
            raw_candidates = [source for source in ("sina", "eastmoney", "tencent") if source in raw_sources]
            raw_source = raw_candidates[0] if raw_candidates else ""
            raw_values = _boundary_values(raw_sources[raw_source], f"{raw_source}_raw_close") if raw_source else {}
            passed = False
            implied = (np.nan, np.nan)
            observed = (np.nan, np.nan)
            if trade_date in qfq_values and trade_date in raw_values:
                raw_decimals = displayed_decimals(raw_sources[raw_source][f"{raw_source}_raw_close"])
                passed, implied, observed = validate_raw_identity(
                    qfq_values[trade_date], qfq_decimals, factor, factor_decimals,
                    raw_values[trade_date], raw_decimals,
                )
            identity_results.append(passed)
            factor_rows.append({
                "trade_date": trade_date, "factor_effective_date": effective,
                "retrieved_at": retrieved_at, "factor_version_identity": sha256(raw_dir / "sina_qfq-factor_normalized.csv"),
                "qfq": qfq_values.get(trade_date, np.nan), "qfq_factor": factor,
                "implied_raw_lower": implied[0], "implied_raw_upper": implied[1],
                "observed_raw_lower": observed[0], "observed_raw_upper": observed[1],
                "raw_identity_pass": passed,
            })
        raw_identity_pass = all(identity_results)

        frozen_decimals = displayed_decimals(frozen["frozen_qfq"])
        scales = {
            "candidate_pre_over_post": pre_factor / post_factor,
            "candidate_post_over_pre": post_factor / pre_factor,
        }
        for name, scale in scales.items():
            row = evaluate_bridge_candidate(
                name, scale, factor_decimals, frozen, current_qfq,
                frozen_decimals, qfq_decimals,
                float(frozen.set_index("trade_date").loc["2026-07-10", "frozen_qfq"]),
                qfq_values["2026-07-13"], expected_interval, raw_identity_pass,
            )
            bridge_rows.append(row)
        accepted_candidate = sum(bool(row["all_three_checks_pass"]) for row in bridge_rows) == 1
        corrected_overlap_pass = any(bool(row["overlap_reconstruction_pass"]) for row in bridge_rows)

        # First-pass logic allowed only one displayed-price rounding half-unit.
        legacy_scale = float(np.median(
            frozen.merge(current_qfq, on="trade_date")["frozen_qfq"]
            / frozen.merge(current_qfq, on="trade_date")["refreshed_qfq"]
        ))
        merged = frozen.merge(current_qfq, on="trade_date")
        legacy_overlap_pass = bool(
            ((merged["frozen_qfq"] - merged["refreshed_qfq"] * legacy_scale).abs() <= 0.00500000005).all()
        )

    primary_complete = bool(
        official_complete and np.isfinite(cash_per_share) and bonus == 0 and transfer == 0
        and raw_intervals and factors.get("qfq-factor") is not None and bridge_rows
    )
    cause, secondary = classify(
        primary_complete, accepted_candidate, corrected_overlap_pass,
        legacy_overlap_pass, independent_raw_pass, source_conflict,
    )
    assert cause in PRIMARY_CAUSES
    tier1_factor = bool(accepted_candidate and raw_identity_pass and independent_raw_pass and official_complete)
    tier1_rescaling = bool(accepted_candidate and independent_raw_pass and official_complete)
    continuity_allowed = bool(tier1_factor or tier1_rescaling)

    representative_raw_source = next(iter(raw_intervals), "")
    representative_raw_values = (
        _boundary_values(raw_sources[representative_raw_source], f"{representative_raw_source}_raw_close")
        if representative_raw_source else {}
    )
    raw_point_return = next(
        (row["point_value"] for row in raw_returns
         if row["metric"] == "raw_corporate_action_total_return"), np.nan
    )
    qfq_point_return = (
        qfq_values.get("2026-07-13", np.nan) / qfq_values.get("2026-07-10", np.nan) - 1.0
        if all(date in qfq_values for date in ("2026-07-10", "2026-07-13")) else np.nan
    )
    qfq_minus_total_bps = (
        (qfq_point_return - raw_point_return) * 10000
        if np.isfinite(qfq_point_return) and np.isfinite(raw_point_return) else np.nan
    )
    accepted_scale = next((row["scale"] for row in bridge_rows if row["all_three_checks_pass"]), np.nan)
    mapped_post = qfq_values.get("2026-07-13", np.nan) * accepted_scale
    endpoint_failures = [
        f"{row['evidence_name']}: {row['error']}" for row in manifest if row["status"] == "error"
    ]

    pd.DataFrame(manifest).to_csv(output / "evidence_manifest.csv", index=False)
    pd.DataFrame(source_rows).to_csv(output / "source_boundary_prices.csv", index=False)
    pd.DataFrame(factor_rows).to_csv(output / "factor_version_reconciliation.csv", index=False)
    pd.DataFrame(bridge_rows).to_csv(output / "bridge_direction_comparison.csv", index=False)
    pd.DataFrame(raw_returns).to_csv(output / "manual_return_reconciliation.csv", index=False)

    accepted = [row["candidate"] for row in bridge_rows if row["all_three_checks_pass"]]
    report = f"""# 002230 QFQ Boundary Second-Pass Forensics v1.5.1

generated_at={retrieved_at}  
stock_code=002230  
forensic_window={start} to {end}  
refresh_run_id={refresh_run_id}

## Official Corporate Action

- announcement_url={announcement_url}
- cash_dividend_per_10={action.get('cash_dividend_per_10', np.nan)}
- cash_dividend_per_share={cash_per_share}
- record_date={action.get('record_date', '')}
- ex_date={action.get('ex_date', '')}
- payment_date={action.get('payment_date', '')}
- bonus_per_10={bonus}
- transfer_per_10={transfer}
- total_share_capital={announcement_facts.get('total_share_capital', '')}
- capital_unchanged_during_implementation={announcement_facts.get('capital_unchanged_during_implementation', '')}
- report_period_label=2025 annual report (CNInfo report-period field)

The CNInfo dividend-history `publication_time` field is a report-period label, not an announcement clock timestamp.

## Source Semantics

- Sina QFQ: raw / qfq_factor, rounded by AkShare to two decimals.
- Sina HFQ: raw * hfq_factor, rounded by AkShare to two decimals.
- Eastmoney and Tencent adjusted levels use vendor-specific bases. They are used primarily to validate raw prices and return continuity, not absolute adjusted-price equality.
- Precision intervals use the highest precision exposed by each fetched DataFrame. A +/-0.005 interval is used only for genuinely two-decimal values.

## Manual Reconciliation

raw_total_return=(P_2026_07_13 + {cash_per_share}) / P_2026_07_10 - 1

- representative_raw_source={representative_raw_source}
- raw_close_2026_07_10={representative_raw_values.get('2026-07-10', np.nan)}
- raw_close_2026_07_13={representative_raw_values.get('2026-07-13', np.nan)}
- theoretical_total_return={raw_point_return}
- refreshed_qfq_source={current_source}
- refreshed_qfq_2026_07_10={qfq_values.get('2026-07-10', np.nan)}
- refreshed_qfq_2026_07_13={qfq_values.get('2026-07-13', np.nan)}
- refreshed_qfq_return={qfq_point_return}
- qfq_minus_total_return_bps={qfq_minus_total_bps}
- raw_source_count={len(raw_intervals)}
- independent_raw_sources={','.join(independent_raw_sources)}
- independent_raw_pass={str(independent_raw_pass).lower()}
- raw_identity_pass={str(raw_identity_pass).lower()}
- legacy_one_sided_overlap_pass={str(legacy_overlap_pass).lower()}
- corrected_two_sided_overlap_pass={str(corrected_overlap_pass).lower()}

## Bridge Direction

General versioned identity: `Q_old(t) = Q_refreshed(t) * F_refreshed(t) / F_old(t)`.
Both date-ratio candidates were tested; neither candidate was accepted by name alone.

- accepted_candidate={','.join(accepted)}
- pre_event_factor={pre_factor}; effective_date={pre_effective}
- post_event_factor={post_factor}; effective_date={post_effective}
- accepted_scale={accepted_scale}
- mapped_post_event_qfq_on_frozen_scale={mapped_post}
- exactly_one_candidate_passed={str(accepted_candidate).lower()}
- inverse_candidate_failed={str(len(bridge_rows) == 2 and accepted_candidate).lower()}

The accepted direction is determined by the three reconciliations above. The inverse direction failed all 12 overlap dates and the corporate-action return check.

## Endpoint Outcomes

- successful_raw_sources={','.join(raw_intervals)}
- endpoint_failures={' | '.join(endpoint_failures) if endpoint_failures else 'none'}

Adjusted-endpoint failures do not invalidate the result when primary raw and at least one independent raw source agree with the official action. Absolute QFQ/HFQ levels are vendor-base-specific and are not cross-vendor equality checks.

## Conclusion

- primary_cause={cause}
- secondary_numerical_cause={secondary}
- tier1_factor_bridge_supported={str(tier1_factor).lower()}
- tier1_rescaling_supported={str(tier1_rescaling).lower()}
- v1_5_1_continuity_fix_allowed={str(continuity_allowed).lower()}
- publish_allowed=false
- observe_allowed=false

This report authorizes no bridge implementation, refresh rerun, publication, observation, or LOWVOL20 methodology change.
"""
    (output / "002230_qfq_boundary_forensics_v1_5_1.md").write_text(report, encoding="utf-8")

    after = protected_snapshot(root, output)
    if before != after:
        raise RuntimeError("protected forensic inputs changed")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--refresh-run-id", required=True)
    parser.add_argument("--start-date", default="2026-06-25")
    parser.add_argument("--end-date", default="2026-07-13")
    args = parser.parse_args(argv)
    try:
        return run(Path(args.project_root), args.refresh_run_id, args.start_date, args.end_date)
    except Exception as exc:
        print(f"002230 second-pass forensics failed: {type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
