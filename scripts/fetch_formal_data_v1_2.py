from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.data_layer.config import DataLayerConfig  # noqa: E402
from aq_factor_lab.data_layer.service import DataLayerService  # noqa: E402


UNIVERSE_PATH = ROOT / "data" / "processed" / "backtest_universe_research_v1_2.csv"
SMOKE_PRICE_PANEL = ROOT / "data" / "processed" / "backtest_price_panel_v1_2.csv"
REVIEWED_POOL = ROOT / "data" / "stockPool" / "pool_decision_suggestions_v1_2.csv"

FORMAL_PRICE_PANEL = ROOT / "data" / "processed" / "formal_price_panel_v1_2.csv"
FORMAL_BENCHMARK_PANEL = ROOT / "data" / "processed" / "formal_benchmark_panel_v1_2.csv"
FORMAL_TRADE_CALENDAR = ROOT / "data" / "processed" / "formal_trade_calendar_v1_2.csv"
FORMAL_MANIFEST = ROOT / "data" / "processed" / "formal_price_fetch_manifest_v1_2.csv"
FAILURE_REPORT = ROOT / "reports" / "minimal_data_fetch_failures_v1_2.csv"
READINESS_REPORT = ROOT / "reports" / "formal_data_readiness_report_v1_2.md"

PRICE_COLUMNS = [
    "stock_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "qfq_open",
    "qfq_high",
    "qfq_low",
    "qfq_close",
    "adjusted_close",
    "volume",
    "amount",
    "pre_close",
    "source_endpoint",
    "fetched_at",
    "adjust_type",
]
BENCHMARK_COLUMNS = [
    "benchmark_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "amount",
    "pre_close",
    "source_endpoint",
    "fetched_at",
    "adjust_type",
]
MANIFEST_COLUMNS = [
    "symbol",
    "asset_type",
    "endpoint",
    "adjust_type",
    "start_date",
    "end_date",
    "row_count",
    "fetched_at",
    "elapsed_seconds",
    "status",
    "error_type",
    "error_message",
]
FAILURE_COLUMNS = [
    "symbol",
    "asset_type",
    "endpoint",
    "adjust_type",
    "attempts",
    "critical",
    "elapsed_seconds",
    "error_type",
    "error_message",
]


def code6(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits.zfill(6)[-6:]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_csv_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [code6(item) for item in value.split(",") if item.strip()]


def read_csv(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype={"code": str, "stock_code": str, "symbol": str})


def infer_date_range(price_panel: pd.DataFrame) -> tuple[str, str]:
    date_col = "trade_date" if "trade_date" in price_panel.columns else "date"
    dates = pd.to_datetime(price_panel[date_col], errors="coerce").dropna()
    if dates.empty:
        raise ValueError("Cannot infer date range from empty price panel dates")
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def load_universe_codes(path: Path, include_reviewed_universe: bool = False) -> list[str]:
    df = read_csv(path)
    code_col = "stock_code" if "stock_code" in df.columns else "code"
    codes = {code6(value) for value in df[code_col].dropna()}
    if include_reviewed_universe and REVIEWED_POOL.exists():
        reviewed = read_csv(REVIEWED_POOL)
        reviewed_col = "stock_code" if "stock_code" in reviewed.columns else "code"
        codes.update(code6(value) for value in reviewed[reviewed_col].dropna())
    return sorted(codes)


def select_symbols(universe_codes: list[str], symbols: str | None, limit: int | None) -> list[str]:
    selected = parse_csv_list(symbols) if symbols else list(universe_codes)
    if limit is not None:
        selected = selected[: max(0, limit)]
    return selected


def completed_manifest_pairs(manifest: pd.DataFrame) -> set[tuple[str, str, str]]:
    if manifest.empty:
        return set()
    required = {"symbol", "asset_type", "adjust_type", "status"}
    if not required.issubset(manifest.columns):
        return set()
    ok = manifest.loc[manifest["status"].astype(str).str.lower().eq("ok")]
    return {
        (code6(row["symbol"]), str(row["asset_type"]), str(row["adjust_type"]))
        for _, row in ok.iterrows()
    }


def load_existing_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=columns)
    return pd.read_csv(path, dtype={"symbol": str, "stock_code": str, "benchmark_code": str}).reindex(columns=columns)


def append_csv_rows(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows, columns=columns)
    if frame.empty:
        if not path.exists():
            frame.to_csv(path, index=False, encoding="utf-8-sig")
        return
    frame.to_csv(path, mode="a", header=not path.exists(), index=False, encoding="utf-8-sig")


def reset_outputs(paths: list[Path]) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def dry_run_plan(
    symbols: list[str],
    benchmarks: list[str],
    optional_benchmarks: list[str],
    start_date: str,
    end_date: str,
) -> str:
    return "\n".join(
        [
            "dry_run=true",
            f"date_range={start_date}..{end_date}",
            f"stock_count={len(symbols)}",
            f"symbols={','.join(symbols)}",
            f"benchmarks={','.join(benchmarks)}",
            f"optional_benchmarks={','.join(optional_benchmarks) if optional_benchmarks else 'none'}",
        ]
    )


def _empty_price_panel() -> pd.DataFrame:
    return pd.DataFrame(columns=PRICE_COLUMNS)


def _empty_benchmark_panel() -> pd.DataFrame:
    return pd.DataFrame(columns=BENCHMARK_COLUMNS)


def _date_text(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%d")


def merge_stock_frames(symbol: str, raw: pd.DataFrame, qfq: pd.DataFrame, fetched_at: str) -> pd.DataFrame:
    if raw.empty and qfq.empty:
        return _empty_price_panel()

    stock_code = code6(symbol)
    raw_cols = ["date", "open", "high", "low", "close", "volume", "amount"]
    qfq_cols = ["date", "open", "high", "low", "close"]
    raw_part = raw.loc[:, [col for col in raw_cols if col in raw.columns]].copy()
    qfq_part = qfq.loc[:, [col for col in qfq_cols if col in qfq.columns]].copy()
    if raw_part.empty:
        raw_part = pd.DataFrame(columns=raw_cols)
    if qfq_part.empty:
        qfq_part = pd.DataFrame(columns=qfq_cols)

    raw_part["trade_date"] = _date_text(raw_part["date"]) if "date" in raw_part else pd.Series(dtype=str)
    qfq_part["trade_date"] = _date_text(qfq_part["date"]) if "date" in qfq_part else pd.Series(dtype=str)
    raw_part = raw_part.drop(columns=["date"], errors="ignore")
    qfq_part = qfq_part.drop(columns=["date"], errors="ignore").rename(
        columns={
            "open": "qfq_open",
            "high": "qfq_high",
            "low": "qfq_low",
            "close": "qfq_close",
        }
    )

    merged = raw_part.merge(qfq_part, on="trade_date", how="outer")
    merged.insert(0, "stock_code", stock_code)
    merged["adjusted_close"] = merged["qfq_close"]
    merged = merged.sort_values(["stock_code", "trade_date"]).reset_index(drop=True)
    merged["pre_close"] = merged.groupby("stock_code")["qfq_close"].shift(1)
    merged["source_endpoint"] = "akshare.stock_zh_a_hist"
    merged["fetched_at"] = fetched_at
    merged["adjust_type"] = "raw+qfq"
    return merged.reindex(columns=PRICE_COLUMNS)


def format_benchmark_frame(index_code: str, raw: pd.DataFrame, fetched_at: str) -> pd.DataFrame:
    if raw.empty:
        return _empty_benchmark_panel()
    out = raw.copy()
    out["benchmark_code"] = code6(index_code)
    out["trade_date"] = _date_text(out["date"])
    out = out.sort_values(["benchmark_code", "trade_date"]).reset_index(drop=True)
    out["pre_close"] = out.groupby("benchmark_code")["close"].shift(1)
    out["source_endpoint"] = "akshare.index_zh_a_hist"
    out["fetched_at"] = fetched_at
    out["adjust_type"] = "raw"
    return out.reindex(columns=BENCHMARK_COLUMNS)


def manifest_row(
    symbol: str,
    asset_type: str,
    endpoint: str,
    adjust_type: str,
    start_date: str,
    end_date: str,
    row_count: int,
    fetched_at: str,
    status: str,
    elapsed_seconds: float = 0.0,
    error: Exception | None = None,
) -> dict[str, Any]:
    return {
        "symbol": code6(symbol),
        "asset_type": asset_type,
        "endpoint": endpoint,
        "adjust_type": adjust_type,
        "start_date": start_date,
        "end_date": end_date,
        "row_count": row_count,
        "fetched_at": fetched_at,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "status": status,
        "error_type": type(error).__name__ if error else "",
        "error_message": str(error) if error else "",
    }


def failure_row(
    symbol: str,
    asset_type: str,
    endpoint: str,
    adjust_type: str,
    attempts: int,
    critical: bool,
    elapsed_seconds: float,
    error: Exception,
) -> dict[str, Any]:
    return {
        "symbol": code6(symbol),
        "asset_type": asset_type,
        "endpoint": endpoint,
        "adjust_type": adjust_type,
        "attempts": attempts,
        "critical": str(critical).lower(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "error_type": type(error).__name__,
        "error_message": str(error),
    }


def fetch_daily(service: DataLayerService, symbol: str, start: str, end: str, adjusted: bool) -> tuple[pd.DataFrame, Exception | None]:
    try:
        return service.get_daily_price(symbol, start, end, adjusted=adjusted), None
    except Exception as exc:  # per-symbol isolation is the point here
        return pd.DataFrame(), exc


def fetch_index(service: DataLayerService, index_code: str, start: str, end: str) -> tuple[pd.DataFrame, Exception | None]:
    try:
        return service.get_index_price(index_code, start, end), None
    except Exception as exc:
        return pd.DataFrame(), exc


def fetch_stock_symbol(
    service: DataLayerService,
    symbol: str,
    start: str,
    end: str,
    fetched_at: str,
    attempts: int,
    completed_adjusts: set[str] | None = None,
) -> tuple[pd.DataFrame, list[dict[str, Any]], list[dict[str, Any]]]:
    completed_adjusts = completed_adjusts or set()
    started = time.perf_counter()
    raw, raw_error = fetch_daily(service, symbol, start, end, adjusted=False)
    qfq, qfq_error = fetch_daily(service, symbol, start, end, adjusted=True)
    elapsed = time.perf_counter() - started
    manifests = []
    if "raw" not in completed_adjusts:
        manifests.append(manifest_row(symbol, "stock", "akshare.stock_zh_a_hist", "raw", start, end, len(raw), fetched_at, "error" if raw_error else "ok", elapsed, raw_error))
    if "qfq" not in completed_adjusts:
        manifests.append(manifest_row(symbol, "stock", "akshare.stock_zh_a_hist", "qfq", start, end, len(qfq), fetched_at, "error" if qfq_error else "ok", elapsed, qfq_error))
    failures = []
    if raw_error and "raw" not in completed_adjusts:
        failures.append(failure_row(symbol, "stock", "akshare.stock_zh_a_hist", "raw", attempts, True, elapsed, raw_error))
    if qfq_error and "qfq" not in completed_adjusts:
        failures.append(failure_row(symbol, "stock", "akshare.stock_zh_a_hist", "qfq", attempts, True, elapsed, qfq_error))
    return merge_stock_frames(symbol, raw, qfq, fetched_at), manifests, failures


def fetch_benchmark(
    service: DataLayerService,
    index_code: str,
    start: str,
    end: str,
    fetched_at: str,
    attempts: int,
    critical: bool,
) -> tuple[pd.DataFrame, dict[str, Any], list[dict[str, Any]]]:
    started = time.perf_counter()
    raw, error = fetch_index(service, index_code, start, end)
    elapsed = time.perf_counter() - started
    manifest = manifest_row(index_code, "benchmark", "akshare.index_zh_a_hist", "raw", start, end, len(raw), fetched_at, "error" if error else "ok", elapsed, error)
    failures = [failure_row(index_code, "benchmark", "akshare.index_zh_a_hist", "raw", attempts, critical, elapsed, error)] if error else []
    return format_benchmark_frame(index_code, raw, fetched_at), manifest, failures


def evaluate_readiness(
    price_panel: pd.DataFrame,
    benchmark_panel: pd.DataFrame,
    universe_codes: list[str],
    failures: pd.DataFrame,
    *,
    required_benchmarks: list[str],
    target_end_date: str,
) -> dict[str, Any]:
    stock_codes = set(price_panel["stock_code"].dropna().map(code6)) if "stock_code" in price_panel else set()
    duplicate_rows = int(price_panel.duplicated(["stock_code", "trade_date"], keep=False).sum()) if not price_panel.empty else 0
    required_price_cols = ["open", "high", "low", "close", "volume", "amount"]
    missing_required = int(price_panel[required_price_cols].isna().sum().sum()) if not price_panel.empty else len(universe_codes)
    missing_qfq = int(price_panel["qfq_close"].isna().sum()) if "qfq_close" in price_panel else len(universe_codes)
    price_cols = ["open", "high", "low", "close", "qfq_close"]
    invalid_prices = int((price_panel[price_cols].apply(pd.to_numeric, errors="coerce") <= 0).sum().sum()) if not price_panel.empty else 0

    pre_close_failures = 0
    if not price_panel.empty:
        sorted_panel = price_panel.sort_values(["stock_code", "trade_date"])
        non_first = sorted_panel.groupby("stock_code").cumcount() > 0
        pre_close_failures = int(sorted_panel.loc[non_first, "pre_close"].isna().sum())

    benchmark_codes = set(benchmark_panel["benchmark_code"].dropna().map(code6)) if "benchmark_code" in benchmark_panel else set()
    missing_benchmarks = [code for code in required_benchmarks if code6(code) not in benchmark_codes]
    critical_failures = 0
    if not failures.empty and "critical" in failures.columns:
        critical_failures = int(failures["critical"].astype(str).str.lower().eq("true").sum())

    target_end = pd.to_datetime(target_end_date)
    code_300378 = price_panel.loc[price_panel.get("stock_code", pd.Series(dtype=str)).map(code6).eq("300378")] if not price_panel.empty else pd.DataFrame()
    fixed_300378 = True
    if "300378" in set(universe_codes):
        fixed_300378 = (
            not code_300378.empty
            and not code_300378[["high", "low"]].isna().any().any()
            and pd.to_datetime(code_300378["trade_date"], errors="coerce").max() >= target_end
        )

    coverage_ratio = len(stock_codes) / len(universe_codes) if universe_codes else 0.0
    formal_ready = (
        coverage_ratio >= 0.95
        and missing_qfq == 0
        and missing_required == 0
        and pre_close_failures == 0
        and duplicate_rows == 0
        and invalid_prices == 0
        and not missing_benchmarks
        and critical_failures == 0
        and fixed_300378
    )
    return {
        "formal_ready": formal_ready,
        "universe_count": len(universe_codes),
        "covered_stock_count": len(stock_codes),
        "stock_coverage_ratio": coverage_ratio,
        "duplicate_stock_date_rows": duplicate_rows,
        "missing_required_price_values": missing_required,
        "missing_qfq_close_count": missing_qfq,
        "invalid_price_count": invalid_prices,
        "pre_close_failure_count": pre_close_failures,
        "missing_required_benchmarks": ",".join(missing_benchmarks),
        "critical_failure_count": critical_failures,
        "fixed_300378": fixed_300378,
    }


def summarize_missing_dates(price_panel: pd.DataFrame, benchmark_panel: pd.DataFrame, limit: int = 20) -> list[dict[str, Any]]:
    if price_panel.empty or benchmark_panel.empty or "000300" not in set(benchmark_panel["benchmark_code"].map(code6)):
        return []
    calendar = set(benchmark_panel.loc[benchmark_panel["benchmark_code"].map(code6).eq("000300"), "trade_date"])
    rows = []
    for code, group in price_panel.groupby("stock_code"):
        missing = sorted(calendar - set(group["trade_date"]))
        if missing:
            rows.append({"stock_code": code6(code), "missing_date_count": len(missing), "first_missing_date": missing[0]})
        if len(rows) >= limit:
            break
    return rows


def build_trade_calendar(benchmark_panel: pd.DataFrame) -> pd.DataFrame:
    if benchmark_panel.empty or "benchmark_code" not in benchmark_panel:
        return pd.DataFrame(columns=["trade_date", "is_trading_day", "source"])
    source = benchmark_panel.loc[benchmark_panel["benchmark_code"].map(code6).eq("000300")]
    if source.empty:
        return pd.DataFrame(columns=["trade_date", "is_trading_day", "source"])
    out = pd.DataFrame({"trade_date": sorted(source["trade_date"].dropna().unique())})
    out["is_trading_day"] = "true"
    out["source"] = "benchmark_000300"
    return out


def render_report(qa: dict[str, Any], missing_dates: list[dict[str, Any]], manifest_rows: list[dict[str, Any]]) -> str:
    missing_lines = ["- none"] if not missing_dates else [
        f"- {row['stock_code']}: {row['missing_date_count']} missing dates, first={row['first_missing_date']}"
        for row in missing_dates
    ]
    manifest_df = pd.DataFrame(manifest_rows)
    status_counts = manifest_df["status"].value_counts().to_dict() if not manifest_df.empty else {}
    return "\n".join(
        [
            "# Formal Data Readiness Report v1.2",
            "",
            "- baseline_mode: formal_data_readiness",
            "- no investment conclusion",
            "- not a point-in-time strategy backtest",
            f"- formal_ready: {str(bool(qa.get('formal_ready'))).lower()}",
            f"- research_universe_coverage: {qa.get('covered_stock_count', 0)}/{qa.get('universe_count', 0)} ({qa.get('stock_coverage_ratio', 0):.2%})",
            f"- duplicate_stock_date_rows: {qa.get('duplicate_stock_date_rows', 0)}",
            f"- missing_qfq_close_count: {qa.get('missing_qfq_close_count', 0)}",
            f"- missing_required_price_values: {qa.get('missing_required_price_values', 0)}",
            f"- invalid_price_count: {qa.get('invalid_price_count', 0)}",
            f"- pre_close_failure_count: {qa.get('pre_close_failure_count', 0)}",
            f"- missing_required_benchmarks: {qa.get('missing_required_benchmarks', '') or 'none'}",
            f"- critical_failure_count: {qa.get('critical_failure_count', 0)}",
            f"- fixed_300378: {str(bool(qa.get('fixed_300378'))).lower()}",
            f"- manifest_status_counts: {status_counts}",
            "",
            "## Missing Date Sample",
            *missing_lines,
            "",
            "## Caveats",
            "- AkShare qfq prices are vendor-adjusted and not independently audited.",
            "- Historical ST, suspension, and limit-up/down fields remain incomplete unless a separate trading-status source is added.",
            "- pre_close is computed from qfq_close for stocks and close for benchmarks.",
            "- This report checks data readiness only; it does not run a strategy backtest.",
            "",
        ]
    )


def write_csv(path: Path, df: pd.DataFrame, columns: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.reindex(columns=columns) if columns else df
    out.to_csv(path, index=False, encoding="utf-8-sig")


def run(args: argparse.Namespace) -> dict[str, Any]:
    date_source = read_csv(args.price_panel)
    start_date, end_date = infer_date_range(date_source)
    start_date = args.start_date or start_date
    end_date = args.end_date or end_date
    universe_codes = load_universe_codes(args.universe, args.include_reviewed_universe)
    selected_codes = select_symbols(universe_codes, args.symbols, args.limit)
    required_benchmarks = parse_csv_list(args.benchmarks)
    optional_benchmarks = parse_csv_list(args.optional_benchmarks)

    if args.dry_run:
        print(dry_run_plan(selected_codes, required_benchmarks, optional_benchmarks, start_date, end_date))
        return {
            "formal_ready": False,
            "universe_count": len(selected_codes),
            "covered_stock_count": 0,
            "stock_coverage_ratio": 0.0,
            "critical_failure_count": 0,
        }

    output_paths = [
        FORMAL_PRICE_PANEL,
        FORMAL_BENCHMARK_PANEL,
        FORMAL_TRADE_CALENDAR,
        FORMAL_MANIFEST,
        FAILURE_REPORT,
        READINESS_REPORT,
    ]
    if not args.resume and not args.no_write:
        reset_outputs(output_paths)

    existing_manifest = load_existing_csv(FORMAL_MANIFEST, MANIFEST_COLUMNS) if args.resume else pd.DataFrame(columns=MANIFEST_COLUMNS)
    completed = completed_manifest_pairs(existing_manifest)

    fetched_at = now_utc()

    config = DataLayerConfig(
        root_dir=ROOT,
        sleep_seconds=args.sleep,
        max_attempts=args.max_attempts,
        max_requests_per_run=args.max_requests,
        dry_run=args.dry_run,
    )
    service = DataLayerService(config)

    if not args.no_write:
        append_csv_rows(FORMAL_MANIFEST, [], MANIFEST_COLUMNS)
        append_csv_rows(FAILURE_REPORT, [], FAILURE_COLUMNS)
        append_csv_rows(FORMAL_PRICE_PANEL, [], PRICE_COLUMNS)
        append_csv_rows(FORMAL_BENCHMARK_PANEL, [], BENCHMARK_COLUMNS)

    manifest_rows: list[dict[str, Any]] = existing_manifest.to_dict("records") if args.resume and not existing_manifest.empty else []

    for index, symbol in enumerate(selected_codes, start=1):
        raw_done = (symbol, "stock", "raw") in completed
        qfq_done = (symbol, "stock", "qfq") in completed
        if args.resume and raw_done and qfq_done:
            print(f"[stock {index}/{len(selected_codes)}] skip {symbol} resume=complete", flush=True)
            continue
        print(f"[stock {index}/{len(selected_codes)}] start {symbol}", flush=True)
        completed_adjusts = {"raw" if raw_done else "", "qfq" if qfq_done else ""} - {""}
        panel, manifests, failures = fetch_stock_symbol(
            service,
            symbol,
            start_date,
            end_date,
            fetched_at,
            args.max_attempts,
            completed_adjusts=completed_adjusts,
        )
        ok_count = sum(1 for row in manifests if row["status"] == "ok")
        elapsed = max([float(row["elapsed_seconds"]) for row in manifests], default=0.0)
        complete_panel = not panel.empty and not panel[["open", "high", "low", "close", "qfq_close"]].isna().any().any()
        print(
            f"[stock {index}/{len(selected_codes)}] end {symbol} ok={ok_count}/{len(manifests)} rows={len(panel) if complete_panel else 0} elapsed={elapsed:.1f}s",
            flush=True,
        )
        manifest_rows.extend(manifests)
        if not args.no_write:
            if complete_panel:
                append_csv_rows(FORMAL_PRICE_PANEL, panel.to_dict("records"), PRICE_COLUMNS)
            append_csv_rows(FORMAL_MANIFEST, manifests, MANIFEST_COLUMNS)
            append_csv_rows(FAILURE_REPORT, failures, FAILURE_COLUMNS)

    benchmarks = required_benchmarks + optional_benchmarks
    for index, code in enumerate(benchmarks, start=1):
        if args.resume and (code, "benchmark", "raw") in completed:
            print(f"[benchmark {index}/{len(benchmarks)}] skip {code} resume=complete", flush=True)
            continue
        print(f"[benchmark {index}/{len(benchmarks)}] start {code}", flush=True)
        panel, manifest, failures = fetch_benchmark(
            service,
            code,
            start_date,
            end_date,
            fetched_at,
            args.max_attempts,
            critical=code in required_benchmarks,
        )
        print(f"[benchmark {index}/{len(benchmarks)}] end {code} status={manifest['status']} rows={len(panel)} elapsed={manifest['elapsed_seconds']:.1f}s", flush=True)
        manifest_rows.append(manifest)
        if not args.no_write:
            append_csv_rows(FORMAL_BENCHMARK_PANEL, panel.to_dict("records"), BENCHMARK_COLUMNS)
            append_csv_rows(FORMAL_MANIFEST, [manifest], MANIFEST_COLUMNS)
            append_csv_rows(FAILURE_REPORT, failures, FAILURE_COLUMNS)

    price_panel = load_existing_csv(FORMAL_PRICE_PANEL, PRICE_COLUMNS) if not args.no_write else _empty_price_panel()
    benchmark_panel = load_existing_csv(FORMAL_BENCHMARK_PANEL, BENCHMARK_COLUMNS) if not args.no_write else _empty_benchmark_panel()
    failures = load_existing_csv(FAILURE_REPORT, FAILURE_COLUMNS) if not args.no_write else pd.DataFrame(columns=FAILURE_COLUMNS)
    manifest = pd.DataFrame(manifest_rows, columns=MANIFEST_COLUMNS)
    trade_calendar = build_trade_calendar(benchmark_panel)
    missing_dates = summarize_missing_dates(price_panel, benchmark_panel)
    qa = evaluate_readiness(
        price_panel,
        benchmark_panel,
        selected_codes,
        failures,
        required_benchmarks=required_benchmarks,
        target_end_date=end_date,
    )

    if not args.no_write:
        write_csv(FORMAL_TRADE_CALENDAR, trade_calendar)
        READINESS_REPORT.parent.mkdir(parents=True, exist_ok=True)
        READINESS_REPORT.write_text(render_report(qa, missing_dates, manifest_rows), encoding="utf-8")

    return qa


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Fetch minimal formal v1.2 stock-pool price data.")
    p.add_argument("--universe", type=Path, default=UNIVERSE_PATH)
    p.add_argument("--price-panel", type=Path, default=SMOKE_PRICE_PANEL)
    p.add_argument("--start-date")
    p.add_argument("--end-date")
    p.add_argument("--benchmarks", default="000300,000852")
    p.add_argument("--optional-benchmarks", default="")
    p.add_argument("--symbols", help="Comma-separated 6-digit stock codes to fetch instead of the full universe")
    p.add_argument("--limit", type=int, help="Fetch only the first N selected universe stocks")
    p.add_argument("--resume", action="store_true", help="Skip symbol/adjust_type pairs already marked ok in the formal manifest")
    p.add_argument("--include-reviewed-universe", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--no-write", action="store_true")
    p.add_argument("--sleep", type=float, default=3.0)
    p.add_argument("--max-attempts", type=int, default=3)
    p.add_argument("--max-requests", type=int, default=500)
    return p


def main() -> None:
    qa = run(parser().parse_args())
    print(f"formal_ready={str(bool(qa['formal_ready'])).lower()}")
    print(f"coverage={qa['covered_stock_count']}/{qa['universe_count']} ({qa['stock_coverage_ratio']:.2%})")
    print(f"critical_failures={qa['critical_failure_count']}")


if __name__ == "__main__":
    main()
