from __future__ import annotations

import argparse
import inspect
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.data import safe_fetch  # noqa: E402
from aq_factor_lab.utils import first_existing_column, to_numeric  # noqa: E402

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None


UNIVERSE_PATH = ROOT / "data" / "processed" / "backtest_universe_research_v1_2.csv"
RAW_BASE_PATH = ROOT / "data" / "processed" / "raw_base_price_panel_v1_2.csv"
QFQ_CACHE_DIR = ROOT / "data" / "cache" / "qfq_enrichment_v1_2"
QFQ_PANEL_OUT = ROOT / "data" / "processed" / "qfq_enrichment_panel_v1_2.csv"
ADJUSTED_PANEL_OUT = ROOT / "data" / "processed" / "adjusted_price_panel_v1_2.csv"
MANIFEST_OUT = ROOT / "data" / "processed" / "qfq_fetch_manifest_v1_2.csv"
FAILURES_OUT = ROOT / "reports" / "qfq_enrichment_failures_v1_2.csv"
READINESS_OUT = ROOT / "reports" / "qfq_enrichment_readiness_v1_2.md"

QFQ_COLUMNS = ["stock_code", "trade_date", "qfq_open", "qfq_high", "qfq_low", "qfq_close", "source_qfq", "fetched_at"]
ADJUSTED_COLUMNS = [
    "stock_code",
    "trade_date",
    "close",
    "qfq_close",
    "adjusted_close",
    "qfq_open",
    "qfq_high",
    "qfq_low",
    "amount",
    "total_market_cap",
    "circulating_market_cap",
    "source_raw",
    "source_qfq",
    "adjusted_flag",
]
MANIFEST_COLUMNS = [
    "run_id",
    "fetched_at",
    "stock_code",
    "final_status",
    "row_count",
    "start_date",
    "end_date",
    "coverage_ratio",
    "cache_path",
    "source_endpoint",
    "attempts",
    "elapsed_seconds",
    "error_type",
    "error_message",
]
FAILURE_COLUMNS = ["run_id", "fetched_at", "stock_code", "source_endpoint", "attempts", "elapsed_seconds", "error_type", "error_message", "final_status"]


def code6(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return "".join(ch for ch in text if ch.isdigit()).zfill(6)[-6:]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_run_id() -> str:
    return datetime.now().strftime("qfq_v1_2_%Y%m%d_%H%M%S")


def yyyymmdd_text(value: str) -> str:
    return pd.to_datetime(value).strftime("%Y%m%d")


def sina_symbol(stock_code: str) -> str:
    code = code6(stock_code)
    if code.startswith(("000", "001", "002", "003", "300", "301")):
        return f"sz{code}"
    if code.startswith(("600", "601", "603", "605", "688")):
        return f"sh{code}"
    raise ValueError(f"Unsupported A-share code for Sina daily: {code}")


def parse_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [code6(item) for item in value.split(",") if item.strip()]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"code": str, "stock_code": str})


def load_universe_codes(path: Path = UNIVERSE_PATH) -> list[str]:
    df = read_csv(path)
    col = "stock_code" if "stock_code" in df.columns else "code"
    return sorted({code6(value) for value in df[col].dropna()})


def select_symbols(universe_codes: list[str], symbols: str | None, limit: int | None) -> list[str]:
    selected = parse_csv_list(symbols) if symbols else list(universe_codes)
    return selected[: max(0, limit)] if limit is not None else selected


def infer_date_range(raw_base: pd.DataFrame) -> tuple[str, str]:
    dates = pd.to_datetime(raw_base["trade_date"], errors="coerce").dropna()
    if dates.empty:
        raise ValueError("Cannot infer date range from raw_base_price_panel_v1_2.csv")
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def clip_raw_base(raw_base: pd.DataFrame, start_date: str, end_date: str) -> pd.DataFrame:
    dates = pd.to_datetime(raw_base["trade_date"], errors="coerce")
    mask = (dates >= pd.to_datetime(start_date)) & (dates <= pd.to_datetime(end_date))
    return raw_base.loc[mask].reset_index(drop=True)


def _col(raw: pd.DataFrame, candidates: list[str]) -> pd.Series:
    col = first_existing_column(raw, candidates)
    return raw[col] if col is not None else pd.Series([pd.NA] * len(raw), index=raw.index)


def _date_series(raw: pd.DataFrame) -> pd.Series:
    col = first_existing_column(raw, ["date", "日期"])
    if col is not None:
        return raw[col]
    if raw.index.name or not isinstance(raw.index, pd.RangeIndex):
        return pd.Series(raw.index, index=raw.index)
    return pd.Series([pd.NA] * len(raw), index=raw.index)


def normalize_qfq_frame(symbol: str, raw: pd.DataFrame, fetched_at: str, source: str = "ak.stock_zh_a_hist") -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=QFQ_COLUMNS)
    out = pd.DataFrame(
        {
            "stock_code": code6(symbol),
            "trade_date": pd.to_datetime(_date_series(raw), errors="coerce").dt.strftime("%Y-%m-%d"),
            "qfq_open": to_numeric(_col(raw, ["open", "开盘"])),
            "qfq_high": to_numeric(_col(raw, ["high", "最高"])),
            "qfq_low": to_numeric(_col(raw, ["low", "最低"])),
            "qfq_close": to_numeric(_col(raw, ["close", "收盘"])),
            "source_qfq": source,
            "fetched_at": fetched_at,
        }
    )
    out = out.dropna(subset=["trade_date"]).sort_values(["stock_code", "trade_date"]).drop_duplicates(["stock_code", "trade_date"], keep="last")
    return out.reindex(columns=QFQ_COLUMNS).reset_index(drop=True)


def valid_qfq(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.reindex(columns=QFQ_COLUMNS)
    out = frame.copy()
    out["stock_code"] = out["stock_code"].map(code6)
    out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    out["qfq_close"] = pd.to_numeric(out["qfq_close"], errors="coerce")
    return out.dropna(subset=["trade_date"]).loc[out["qfq_close"] > 0].reindex(columns=QFQ_COLUMNS)


def symbol_coverage(raw_symbol: pd.DataFrame, qfq: pd.DataFrame) -> float:
    if raw_symbol.empty:
        return 0.0
    raw_dates = set(raw_symbol["trade_date"].astype(str))
    qfq_dates = set(valid_qfq(qfq)["trade_date"].astype(str))
    return len(raw_dates & qfq_dates) / len(raw_dates)


def cache_is_complete(symbol: str, raw_symbol: pd.DataFrame, cache_dir: Path = QFQ_CACHE_DIR) -> bool:
    path = cache_dir / f"{code6(symbol)}.csv"
    if not path.exists():
        return False
    cached = pd.read_csv(path, dtype={"stock_code": str})
    return symbol_coverage(raw_symbol, cached) >= 1.0


def safe_fetch_compatible() -> bool:
    params = inspect.signature(safe_fetch).parameters
    return {"label", "fetcher", "max_attempts"}.issubset(params)


def fetch_with_safe_fetch(label: str, fetcher: Callable[[], pd.DataFrame], max_attempts: int) -> pd.DataFrame:
    if safe_fetch_compatible():
        return safe_fetch(
            label,
            fetcher,
            max_attempts=max_attempts,
            base_sleep=0.5,
            random_sleep_range=(0.0, 0.5),
            timeout_seconds=20,
        )
    last_error: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return fetcher()
        except Exception as exc:  # pragma: no cover - fallback only
            last_error = exc
            if attempt < max_attempts:
                time.sleep(0.5 * attempt)
    raise RuntimeError(f"{label} failed: {last_error}") from last_error


def fetch_sina_qfq_raw(symbol: str, start_date: str, end_date: str, max_attempts: int) -> pd.DataFrame:
    if ak is None:
        raise RuntimeError("AkShare is not installed")
    return fetch_with_safe_fetch(
        f"sina qfq price {code6(symbol)}",
        lambda: ak.stock_zh_a_daily(
            symbol=sina_symbol(symbol),
            start_date=yyyymmdd_text(start_date),
            end_date=yyyymmdd_text(end_date),
            adjust="qfq",
        ),
        max_attempts,
    )


def fetch_eastmoney_qfq_raw(symbol: str, start_date: str, end_date: str, max_attempts: int) -> pd.DataFrame:
    if ak is None:
        raise RuntimeError("AkShare is not installed")
    return fetch_with_safe_fetch(
        f"eastmoney qfq price {code6(symbol)}",
        lambda: ak.stock_zh_a_hist(
            symbol=code6(symbol),
            period="daily",
            start_date=yyyymmdd_text(start_date),
            end_date=yyyymmdd_text(end_date),
            adjust="qfq",
            timeout=20,
        ),
        max_attempts,
    )


def _usable_qfq(symbol: str, raw_symbol: pd.DataFrame, raw: pd.DataFrame, fetched_at: str, source: str) -> pd.DataFrame:
    qfq = normalize_qfq_frame(symbol, raw, fetched_at, source=source)
    if valid_qfq(qfq).empty:
        raise ValueError(f"{source} returned no legal qfq_close")
    if symbol_coverage(raw_symbol, qfq) <= 0:
        raise ValueError(f"{source} qfq coverage against raw_base is 0")
    return qfq


def fetch_qfq_with_fallback(
    symbol: str,
    raw_symbol: pd.DataFrame,
    start_date: str,
    end_date: str,
    max_attempts: int,
    *,
    sina_fetch: Callable[[str, str, str], pd.DataFrame] | None = None,
    eastmoney_fetch: Callable[[str, str, str], pd.DataFrame] | None = None,
    fetched_at: str = "",
) -> tuple[pd.DataFrame, str]:
    fetched_at = fetched_at or now_utc()
    errors: list[str] = []
    try:
        raw = sina_fetch(symbol, start_date, end_date) if sina_fetch else fetch_sina_qfq_raw(symbol, start_date, end_date, max_attempts)
        return _usable_qfq(symbol, raw_symbol, raw, fetched_at, "ak.stock_zh_a_daily"), "ak.stock_zh_a_daily"
    except Exception as exc:
        errors.append(f"ak.stock_zh_a_daily: {type(exc).__name__}: {exc}")
    try:
        raw = eastmoney_fetch(symbol, start_date, end_date) if eastmoney_fetch else fetch_eastmoney_qfq_raw(symbol, start_date, end_date, max_attempts)
        return _usable_qfq(symbol, raw_symbol, raw, fetched_at, "ak.stock_zh_a_hist"), "ak.stock_zh_a_hist"
    except Exception as exc:
        errors.append(f"ak.stock_zh_a_hist: {type(exc).__name__}: {exc}")
    raise RuntimeError("; ".join(errors))


def default_fetch_qfq(symbol: str, raw_symbol: pd.DataFrame, start_date: str, end_date: str, max_attempts: int) -> tuple[pd.DataFrame, str]:
    return fetch_qfq_with_fallback(symbol, raw_symbol, start_date, end_date, max_attempts)


def manifest_row(
    run_id: str,
    fetched_at: str,
    symbol: str,
    final_status: str,
    row_count: int,
    start_date: str,
    end_date: str,
    coverage_ratio: float,
    cache_path: Path,
    attempts: int,
    elapsed_seconds: float,
    error: Exception | None = None,
    source_endpoint: str = "ak.stock_zh_a_hist",
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "fetched_at": fetched_at,
        "stock_code": code6(symbol),
        "final_status": final_status,
        "row_count": row_count,
        "start_date": start_date,
        "end_date": end_date,
        "coverage_ratio": round(float(coverage_ratio), 6),
        "cache_path": str(cache_path),
        "source_endpoint": source_endpoint,
        "attempts": attempts,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "error_type": type(error).__name__ if error else "",
        "error_message": str(error) if error else "",
    }


def failure_row(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": row["run_id"],
        "fetched_at": row["fetched_at"],
        "stock_code": row["stock_code"],
        "source_endpoint": row["source_endpoint"],
        "attempts": row["attempts"],
        "elapsed_seconds": row["elapsed_seconds"],
        "error_type": row["error_type"],
        "error_message": row["error_message"],
        "final_status": row["final_status"],
    }


def fetch_or_cache_symbol(
    symbol: str,
    raw_symbol: pd.DataFrame,
    cache_dir: Path,
    run_id: str,
    fetched_at: str,
    start_date: str,
    end_date: str,
    max_attempts: int,
    *,
    fetcher: Callable[[str, pd.DataFrame, str, str, int], tuple[pd.DataFrame, str]] = default_fetch_qfq,
    resume: bool = False,
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any] | None]:
    started = time.perf_counter()
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{code6(symbol)}.csv"
    if cache_is_complete(symbol, raw_symbol, cache_dir):
        cached = pd.read_csv(cache_path, dtype={"stock_code": str})
        coverage = symbol_coverage(raw_symbol, cached)
        return cached.reindex(columns=QFQ_COLUMNS), manifest_row(run_id, fetched_at, symbol, "cached_ok", len(cached), start_date, end_date, coverage, cache_path, 0, time.perf_counter() - started, source_endpoint="cached:qfq_enrichment_v1_2"), None
    try:
        qfq, source_endpoint = fetcher(symbol, raw_symbol, start_date, end_date, max_attempts)
        qfq.to_csv(cache_path, index=False, encoding="utf-8-sig")
        coverage = symbol_coverage(raw_symbol, qfq)
        status = "ok" if coverage >= 1.0 else "partial_ok"
        row = manifest_row(run_id, fetched_at, symbol, status, len(qfq), start_date, end_date, coverage, cache_path, max_attempts, time.perf_counter() - started, source_endpoint=source_endpoint)
        return qfq, row, None
    except Exception as exc:
        row = manifest_row(run_id, fetched_at, symbol, "error", 0, start_date, end_date, 0.0, cache_path, max_attempts, time.perf_counter() - started, exc, source_endpoint="ak.stock_zh_a_daily,ak.stock_zh_a_hist")
        return pd.DataFrame(columns=QFQ_COLUMNS), row, failure_row(row)


def build_adjusted_panel(raw_base: pd.DataFrame, qfq_panel: pd.DataFrame) -> pd.DataFrame:
    raw = raw_base.copy()
    raw["stock_code"] = raw["stock_code"].map(code6)
    raw["trade_date"] = pd.to_datetime(raw["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    raw = raw.rename(columns={"source": "source_raw"})
    qfq = qfq_panel.copy()
    if qfq.empty:
        qfq = pd.DataFrame(columns=QFQ_COLUMNS)
    qfq["stock_code"] = qfq["stock_code"].map(code6) if "stock_code" in qfq else pd.Series(dtype=str)
    qfq["trade_date"] = pd.to_datetime(qfq["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d") if "trade_date" in qfq else pd.Series(dtype=str)
    qfq["qfq_close"] = pd.to_numeric(qfq.get("qfq_close"), errors="coerce")
    merged = raw.merge(qfq.reindex(columns=QFQ_COLUMNS), on=["stock_code", "trade_date"], how="left")
    legal = merged["qfq_close"] > 0
    merged["adjusted_close"] = merged["qfq_close"].where(legal)
    merged["adjusted_flag"] = legal.map(lambda value: "true" if value else "false")
    return merged.reindex(columns=ADJUSTED_COLUMNS).sort_values(["stock_code", "trade_date"]).reset_index(drop=True)


def latest_manifest_status(manifest: pd.DataFrame) -> pd.DataFrame:
    if manifest.empty:
        return pd.DataFrame(columns=MANIFEST_COLUMNS).set_index(pd.Index([], name="stock_code"))
    frame = manifest.copy()
    if "run_id" not in frame:
        frame["run_id"] = ""
    frame["stock_code"] = frame["stock_code"].map(code6)
    frame["fetched_at"] = pd.to_datetime(frame["fetched_at"], errors="coerce")
    return frame.sort_values(["stock_code", "fetched_at", "run_id"]).groupby("stock_code").tail(1).set_index("stock_code")


def alignment_warnings(raw_base: pd.DataFrame, adjusted_panel: pd.DataFrame) -> list[dict[str, Any]]:
    if raw_base.empty or adjusted_panel.empty:
        return []
    raw = raw_base[["stock_code", "trade_date", "close"]].copy()
    raw["stock_code"] = raw["stock_code"].map(code6)
    raw["trade_date"] = pd.to_datetime(raw["trade_date"], errors="coerce").dt.strftime("%Y-%m-%d")
    adj = adjusted_panel[["stock_code", "trade_date", "qfq_close", "adjusted_flag"]].copy()
    adj = adj.loc[adj["adjusted_flag"].astype(str).str.lower().eq("true")]
    joined = raw.merge(adj, on=["stock_code", "trade_date"], how="inner")
    if joined.empty:
        return []
    joined["close"] = pd.to_numeric(joined["close"], errors="coerce")
    joined["qfq_close"] = pd.to_numeric(joined["qfq_close"], errors="coerce")
    warnings: list[dict[str, Any]] = []
    for code, group in joined.dropna(subset=["close", "qfq_close"]).sort_values("trade_date").groupby("stock_code"):
        latest = group.iloc[-1]
        ratio = latest["qfq_close"] / latest["close"] if latest["close"] else float("nan")
        if pd.notna(ratio) and not (0.95 <= ratio <= 1.05):
            warnings.append({"stock_code": code6(code), "warning_type": "qfq_raw_alignment_warning", "trade_date": latest["trade_date"], "ratio": round(float(ratio), 6)})
    return warnings


def evaluate_readiness(raw_base: pd.DataFrame, adjusted_panel: pd.DataFrame, universe_codes: list[str], manifest: pd.DataFrame) -> dict[str, Any]:
    legal = adjusted_panel["adjusted_flag"].astype(str).str.lower().eq("true") if "adjusted_flag" in adjusted_panel else pd.Series(dtype=bool)
    stock_covered = set(adjusted_panel.loc[legal, "stock_code"].map(code6)) if not adjusted_panel.empty else set()
    universe = set(map(code6, universe_codes))
    raw_keys = raw_base[["stock_code", "trade_date"]].copy()
    raw_keys["stock_code"] = raw_keys["stock_code"].map(code6)
    raw_key_set = set(map(tuple, raw_keys.astype(str).to_numpy()))
    adjusted_keys = adjusted_panel.loc[legal, ["stock_code", "trade_date"]].copy() if not adjusted_panel.empty else pd.DataFrame(columns=["stock_code", "trade_date"])
    adjusted_keys["stock_code"] = adjusted_keys["stock_code"].map(code6) if not adjusted_keys.empty else pd.Series(dtype=str)
    adjusted_key_set = set(map(tuple, adjusted_keys.astype(str).to_numpy()))
    stock_coverage_ratio = len(stock_covered & universe) / len(universe) if universe else 0.0
    row_coverage_ratio = len(raw_key_set & adjusted_key_set) / len(raw_key_set) if raw_key_set else 0.0
    duplicate_rows = int(adjusted_panel.duplicated(["stock_code", "trade_date"], keep=False).sum()) if not adjusted_panel.empty else 0
    warnings = alignment_warnings(raw_base, adjusted_panel)
    latest = latest_manifest_status(manifest) if not manifest.empty else pd.DataFrame()
    current_failures = int(latest["final_status"].astype(str).eq("error").sum()) if not latest.empty else 0
    adjusted_ready = stock_coverage_ratio >= 0.95 and row_coverage_ratio >= 0.95 and duplicate_rows == 0
    return {
        "stock_coverage_ratio": stock_coverage_ratio,
        "row_coverage_ratio": row_coverage_ratio,
        "adjusted_return_ready": bool(adjusted_ready),
        "execution_sim_ready": False,
        "formal_performance_conclusion_allowed": False,
        "duplicate_stock_date_rows": duplicate_rows,
        "qfq_raw_alignment_warning_count": len(warnings),
        "qfq_raw_alignment_warnings": warnings,
        "current_failure_count": current_failures,
    }


def load_qfq_cache_for_universe(universe_codes: list[str], raw_base: pd.DataFrame, cache_dir: Path = QFQ_CACHE_DIR) -> tuple[pd.DataFrame, list[str]]:
    frames: list[pd.DataFrame] = []
    invalid: list[str] = []
    for symbol in sorted({code6(code) for code in universe_codes}):
        path = cache_dir / f"{symbol}.csv"
        raw_symbol = raw_base.loc[raw_base["stock_code"].map(code6).eq(symbol)]
        if not path.exists():
            continue
        try:
            cached = pd.read_csv(path, dtype={"stock_code": str}).reindex(columns=QFQ_COLUMNS)
            valid = valid_qfq(cached)
            if valid.empty or symbol_coverage(raw_symbol, valid) <= 0:
                invalid.append(symbol)
                continue
            frames.append(valid)
        except Exception:
            invalid.append(symbol)
    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=QFQ_COLUMNS)
    return panel.reindex(columns=QFQ_COLUMNS).drop_duplicates(["stock_code", "trade_date"], keep="last").reset_index(drop=True), invalid


def append_csv_rows(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        if not path.exists():
            frame.to_csv(path, index=False, encoding="utf-8-sig")
        return
    frame.to_csv(path, mode="a", header=not path.exists(), index=False, encoding="utf-8-sig")


def write_csv(path: Path, frame: pd.DataFrame, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = frame.reindex(columns=columns).copy()
    if "stock_code" in out:
        out["stock_code"] = out["stock_code"].map(code6).astype(str)
    if "trade_date" in out:
        out["trade_date"] = out["trade_date"].map(lambda value: pd.to_datetime(value, errors="coerce")).dt.strftime("%Y-%m-%d")
    if "adjusted_flag" in out:
        flags = out["adjusted_flag"].astype(str).str.strip().str.lower().isin({"true", "1", "yes", "y"})
        out["adjusted_flag"] = flags.map(lambda value: "true" if value else "false")
    out.to_csv(path, index=False, encoding="utf-8-sig")


def render_report(qa: dict[str, Any], manifest: pd.DataFrame) -> str:
    latest = latest_manifest_status(manifest) if not manifest.empty else pd.DataFrame()
    final_counts = latest["final_status"].value_counts().to_dict() if not latest.empty else {}
    warning_lines = ["- none"] if not qa["qfq_raw_alignment_warnings"] else [
        f"- {row['stock_code']}: {row['trade_date']} ratio={row['ratio']}" for row in qa["qfq_raw_alignment_warnings"]
    ]
    invalid_cache_symbols = qa.get("invalid_cache_symbols", [])
    invalid_lines = ["- none"] if not invalid_cache_symbols else [f"- {symbol}" for symbol in invalid_cache_symbols]
    return "\n".join(
        [
            "# QFQ Enrichment Readiness v1.2",
            "",
            f"- stock_coverage_ratio: {qa['stock_coverage_ratio']:.2%}",
            f"- row_coverage_ratio: {qa['row_coverage_ratio']:.2%}",
            f"- adjusted_return_ready: {str(qa['adjusted_return_ready']).lower()}",
            f"- execution_sim_ready: {str(qa['execution_sim_ready']).lower()}",
            f"- formal_performance_conclusion_allowed: {str(qa['formal_performance_conclusion_allowed']).lower()}",
            f"- duplicate_stock_date_rows: {qa['duplicate_stock_date_rows']}",
            f"- current_failure_count: {qa['current_failure_count']}",
            f"- latest_final_status_counts: {final_counts}",
            "",
            "## qfq_raw_alignment_warning",
            *warning_lines,
            "",
            "## invalid_cache_symbols",
            *invalid_lines,
            "",
            "## Caveats",
            "- Coverage denominator is existing raw_base stock_code/trade_date rows, not natural days or a full benchmark calendar.",
            "- qfq enrichment does not add historical ST, suspension, or limit-up/down state.",
            "- This script never enables formal performance conclusions by itself.",
            "",
        ]
    )


def rebuild_outputs_from_cache(
    raw_base: pd.DataFrame,
    universe_codes: list[str],
    manifest: pd.DataFrame,
    *,
    cache_dir: Path = QFQ_CACHE_DIR,
    output_dir: Path | None = None,
    report_path: Path = READINESS_OUT,
) -> dict[str, Any]:
    qfq_panel, invalid_cache_symbols = load_qfq_cache_for_universe(universe_codes, raw_base, cache_dir)
    adjusted = build_adjusted_panel(raw_base, qfq_panel)
    qa = evaluate_readiness(raw_base, adjusted, universe_codes, manifest)
    qa["invalid_cache_symbols"] = invalid_cache_symbols
    if output_dir is None:
        qfq_out = QFQ_PANEL_OUT
        adjusted_out = ADJUSTED_PANEL_OUT
    else:
        qfq_out = output_dir / QFQ_PANEL_OUT.name
        adjusted_out = output_dir / ADJUSTED_PANEL_OUT.name
    write_csv(qfq_out, qfq_panel, QFQ_COLUMNS)
    write_csv(adjusted_out, adjusted, ADJUSTED_COLUMNS)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(render_report(qa, manifest), encoding="utf-8")
    return qa


def dry_run_text(symbols: list[str], start_date: str, end_date: str) -> str:
    return "\n".join(["dry_run=true", f"date_range={start_date}..{end_date}", f"stock_count={len(symbols)}", f"symbols={','.join(symbols)}"])


def run(args: argparse.Namespace) -> dict[str, Any]:
    raw_base = read_csv(RAW_BASE_PATH)
    start_date, end_date = infer_date_range(raw_base)
    start_date = args.start_date or start_date
    end_date = args.end_date or end_date
    raw_base = clip_raw_base(raw_base, start_date, end_date)
    universe_codes = load_universe_codes(UNIVERSE_PATH)
    selected = select_symbols(universe_codes, args.symbols, args.limit)
    if args.dry_run:
        print(dry_run_text(selected, start_date, end_date))
        return {"adjusted_return_ready": False}

    run_id = make_run_id()
    fetched_at = now_utc()
    manifest_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    if not args.rebuild_from_cache_only:
        for index, symbol in enumerate(selected, start=1):
            raw_symbol = raw_base.loc[raw_base["stock_code"].map(code6).eq(code6(symbol))]
            print(f"[qfq {index}/{len(selected)}] start {symbol}", flush=True)
            qfq, manifest, failure = fetch_or_cache_symbol(
                symbol,
                raw_symbol,
                QFQ_CACHE_DIR,
                run_id,
                fetched_at,
                start_date,
                end_date,
                args.max_attempts,
                resume=args.resume,
            )
            print(f"[qfq {index}/{len(selected)}] end {symbol} status={manifest['final_status']} rows={len(qfq)} coverage={manifest['coverage_ratio']}", flush=True)
            manifest_rows.append(manifest)
            append_csv_rows(MANIFEST_OUT, [manifest], MANIFEST_COLUMNS)
            if failure:
                failure_rows.append(failure)
                append_csv_rows(FAILURES_OUT, [failure], FAILURE_COLUMNS)
            if index < len(selected):
                time.sleep(random.uniform(args.sleep_min, args.sleep_max))

    existing_manifest = pd.read_csv(MANIFEST_OUT, dtype={"stock_code": str}) if MANIFEST_OUT.exists() else pd.DataFrame(columns=MANIFEST_COLUMNS)
    manifest = pd.concat([existing_manifest, pd.DataFrame(manifest_rows)], ignore_index=True).drop_duplicates()
    append_csv_rows(FAILURES_OUT, [], FAILURE_COLUMNS)
    return rebuild_outputs_from_cache(raw_base, universe_codes, manifest, cache_dir=QFQ_CACHE_DIR, report_path=READINESS_OUT)


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Slow qfq enrichment for stock pool v1.2 research universe.")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--symbols")
    p.add_argument("--limit", type=int)
    p.add_argument("--resume", action="store_true")
    p.add_argument("--start-date")
    p.add_argument("--end-date")
    p.add_argument("--sleep-min", type=float, default=8.0)
    p.add_argument("--sleep-max", type=float, default=20.0)
    p.add_argument("--max-attempts", type=int, default=5)
    p.add_argument("--rebuild-from-cache-only", action="store_true")
    return p


def main() -> None:
    qa = run(parser().parse_args())
    print(f"adjusted_return_ready={str(bool(qa['adjusted_return_ready'])).lower()}")


if __name__ == "__main__":
    main()
