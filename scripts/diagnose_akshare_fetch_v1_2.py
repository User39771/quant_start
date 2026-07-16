from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover - diagnostic records unavailable dependency at runtime
    ak = None


ROOT = Path(__file__).resolve().parents[1]
CSV_OUT = ROOT / "reports" / "akshare_fetch_diagnostics_v1_2.csv"
MD_OUT = ROOT / "reports" / "akshare_fetch_diagnostics_v1_2.md"

STOCKS = ["000063", "300857", "000681", "000901", "000938", "000977"]
BENCHMARKS = ["000300", "000852", "399006"]
FULL_START = "20200101"
SHORT_START = "20250101"
END_DATE = "20260616"
COLUMNS = [
    "symbol",
    "asset_type",
    "endpoint",
    "adjust_type",
    "date_window",
    "status",
    "row_count",
    "columns",
    "elapsed_seconds",
    "error_type",
    "error_message",
]


def tx_symbol(symbol: str) -> str:
    return f"sz{symbol}" if symbol.startswith("399") else f"sh{symbol}"


def call_endpoint(
    call: Callable[[], Any],
    *,
    symbol: str,
    asset_type: str,
    endpoint: str,
    adjust_type: str,
    date_window: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = call()
        elapsed = time.perf_counter() - started
        frame = result if isinstance(result, pd.DataFrame) else pd.DataFrame(result)
        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "endpoint": endpoint,
            "adjust_type": adjust_type,
            "date_window": date_window,
            "status": "ok",
            "row_count": len(frame),
            "columns": ",".join(map(str, frame.columns)),
            "elapsed_seconds": round(elapsed, 3),
            "error_type": "",
            "error_message": "",
        }
    except Exception as exc:
        elapsed = time.perf_counter() - started
        return {
            "symbol": symbol,
            "asset_type": asset_type,
            "endpoint": endpoint,
            "adjust_type": adjust_type,
            "date_window": date_window,
            "status": "error",
            "row_count": 0,
            "columns": "",
            "elapsed_seconds": round(elapsed, 3),
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        }


def missing_function_row(symbol: str, endpoint: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "asset_type": "benchmark",
        "endpoint": endpoint,
        "adjust_type": "raw",
        "date_window": "fallback_tx",
        "status": "function_missing",
        "row_count": 0,
        "columns": "",
        "elapsed_seconds": 0.0,
        "error_type": "AttributeError",
        "error_message": "akshare has no stock_zh_index_daily_tx",
    }


def fallback_index_call(ak_module: Any, symbol: str) -> dict[str, Any]:
    endpoint = "ak.stock_zh_index_daily_tx"
    if not hasattr(ak_module, "stock_zh_index_daily_tx"):
        return missing_function_row(symbol, endpoint)
    mapped = tx_symbol(symbol)
    print(f"[benchmark fallback] {symbol} -> {mapped}", flush=True)
    return call_endpoint(
        lambda: ak_module.stock_zh_index_daily_tx(symbol=mapped),
        symbol=symbol,
        asset_type="benchmark",
        endpoint=endpoint,
        adjust_type="raw",
        date_window="fallback_tx",
    )


def diagnose_stocks(ak_module: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    windows = [("full", FULL_START), ("short", SHORT_START)]
    for symbol in STOCKS:
        for window_name, start in windows:
            for adjust in ["", "qfq"]:
                adjust_type = "raw" if adjust == "" else "qfq"
                print(f"[stock] {symbol} {window_name} {adjust_type} start", flush=True)
                row = call_endpoint(
                    lambda symbol=symbol, start=start, adjust=adjust: ak_module.stock_zh_a_hist(
                        symbol=symbol,
                        period="daily",
                        start_date=start,
                        end_date=END_DATE,
                        adjust=adjust,
                    ),
                    symbol=symbol,
                    asset_type="stock",
                    endpoint="ak.stock_zh_a_hist",
                    adjust_type=adjust_type,
                    date_window=f"{window_name}:{start}-{END_DATE}",
                )
                print(f"[stock] {symbol} {window_name} {adjust_type} {row['status']} rows={row['row_count']} elapsed={row['elapsed_seconds']}s", flush=True)
                rows.append(row)
    return rows


def diagnose_benchmarks(ak_module: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for symbol in BENCHMARKS:
        print(f"[benchmark] {symbol} index_zh_a_hist start", flush=True)
        row = call_endpoint(
            lambda symbol=symbol: ak_module.index_zh_a_hist(
                symbol=symbol,
                period="daily",
                start_date=FULL_START,
                end_date=END_DATE,
            ),
            symbol=symbol,
            asset_type="benchmark",
            endpoint="ak.index_zh_a_hist",
            adjust_type="raw",
            date_window=f"full:{FULL_START}-{END_DATE}",
        )
        print(f"[benchmark] {symbol} index_zh_a_hist {row['status']} rows={row['row_count']} elapsed={row['elapsed_seconds']}s", flush=True)
        rows.append(row)
        if row["status"] != "ok":
            fallback = fallback_index_call(ak_module, symbol)
            print(f"[benchmark] {symbol} tx_fallback {fallback['status']} rows={fallback['row_count']} elapsed={fallback['elapsed_seconds']}s", flush=True)
            rows.append(fallback)
    return rows


def status_counts(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return ["- none"]
    counts = df.groupby(["asset_type", "endpoint", "status"], dropna=False).size().reset_index(name="count")
    return [
        f"- {row.asset_type} | {row.endpoint} | {row.status}: {row['count']}"
        for _, row in counts.iterrows()
    ]


def full_vs_short_lines(df: pd.DataFrame) -> list[str]:
    stock = df[df["asset_type"].eq("stock")]
    if stock.empty:
        return ["- none"]
    lines = []
    for symbol, group in stock.groupby("symbol"):
        full_ok = group[group["date_window"].str.startswith("full")]["status"].eq("ok").any()
        short_ok = group[group["date_window"].str.startswith("short")]["status"].eq("ok").any()
        if not full_ok and short_ok:
            lines.append(f"- {symbol}: short window works, full window fails")
        elif not full_ok and not short_ok:
            lines.append(f"- {symbol}: both full and short windows fail")
    return lines or ["- no date-window-specific failure pattern detected"]


def raw_qfq_lines(df: pd.DataFrame) -> list[str]:
    stock = df[df["asset_type"].eq("stock")]
    lines = []
    for (symbol, window), group in stock.groupby(["symbol", "date_window"]):
        raw_ok = group[group["adjust_type"].eq("raw")]["status"].eq("ok").any()
        qfq_ok = group[group["adjust_type"].eq("qfq")]["status"].eq("ok").any()
        if raw_ok and not qfq_ok:
            lines.append(f"- {symbol} {window}: raw works, qfq fails")
        elif qfq_ok and not raw_ok:
            lines.append(f"- {symbol} {window}: qfq works, raw fails")
    return lines or ["- no raw/qfq split failure pattern detected"]


def benchmark_lines(df: pd.DataFrame) -> list[str]:
    bench = df[df["asset_type"].eq("benchmark")]
    lines = []
    for symbol, group in bench.groupby("symbol"):
        index_ok = group[group["endpoint"].eq("ak.index_zh_a_hist")]["status"].eq("ok").any()
        tx = group[group["endpoint"].eq("ak.stock_zh_index_daily_tx")]
        tx_status = "not_attempted" if tx.empty else ",".join(sorted(set(tx["status"])))
        lines.append(f"- {symbol}: index_zh_a_hist_ok={str(index_ok).lower()}, tx_fallback_status={tx_status}")
    return lines or ["- none"]


def render_report(rows: list[dict[str, Any]], version: str) -> str:
    df = pd.DataFrame(rows, columns=COLUMNS)
    return "\n".join(
        [
            "# AkShare Fetch Diagnostics v1.2",
            "",
            f"- AkShare version: {version}",
            f"- total_calls: {len(df)}",
            "",
            "## Status Counts",
            *status_counts(df),
            "",
            "## Stock Date Window Patterns",
            *full_vs_short_lines(df),
            "",
            "## Stock Raw vs QFQ Patterns",
            *raw_qfq_lines(df),
            "",
            "## Benchmark Endpoint Patterns",
            *benchmark_lines(df),
            "",
            "## Interpretation",
            "- Treat this report as endpoint diagnostics only; it does not validate formal data readiness.",
            "- Prefer conclusions directly supported by the CSV rows above.",
            "",
        ]
    )


def write_outputs(rows: list[dict[str, Any]], version: str) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=COLUMNS).to_csv(CSV_OUT, index=False, encoding="utf-8-sig")
    MD_OUT.write_text(render_report(rows, version), encoding="utf-8")


def main() -> None:
    if ak is None:
        rows = [
            {
                "symbol": "",
                "asset_type": "environment",
                "endpoint": "import akshare",
                "adjust_type": "",
                "date_window": "",
                "status": "error",
                "row_count": 0,
                "columns": "",
                "elapsed_seconds": 0.0,
                "error_type": "ImportError",
                "error_message": "akshare is not importable",
            }
        ]
        write_outputs(rows, "unavailable")
        print("akshare version: unavailable", flush=True)
        return

    version = str(getattr(ak, "__version__", "unknown"))
    print(f"akshare version: {version}", flush=True)
    rows = diagnose_stocks(ak)
    rows.extend(diagnose_benchmarks(ak))
    write_outputs(rows, version)
    print(f"wrote {CSV_OUT}", flush=True)
    print(f"wrote {MD_OUT}", flush=True)


if __name__ == "__main__":
    main()
