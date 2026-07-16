from __future__ import annotations

import argparse
import time
from datetime import timedelta
from pathlib import Path
from typing import Any, Callable

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None


ROOT = Path(__file__).resolve().parents[1]
RAW_BASE_PATH = ROOT / "data" / "processed" / "raw_base_price_panel_v1_2.csv"
CSV_OUT = ROOT / "reports" / "qfq_source_diagnostics_v1_2.csv"
MD_OUT = ROOT / "reports" / "qfq_source_diagnostics_v1_2.md"
DEFAULT_SYMBOLS = ["000063", "300857", "300378"]
COLUMNS = [
    "stock_code",
    "source_name",
    "symbol_used",
    "adjust_type",
    "window_type",
    "start_date",
    "end_date",
    "status",
    "row_count",
    "columns",
    "first_date",
    "last_date",
    "latest_close",
    "elapsed_seconds",
    "error_type",
    "error_message",
]


def code6(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return "".join(ch for ch in text if ch.isdigit()).zfill(6)[-6:]


def yyyymmdd(value: str) -> str:
    return pd.to_datetime(value).strftime("%Y%m%d")


def parse_symbols(value: str | None) -> list[str]:
    return [code6(item) for item in value.split(",") if item.strip()] if value else list(DEFAULT_SYMBOLS)


def sina_symbol(symbol: str) -> str:
    code = code6(symbol)
    return f"sh{code}" if code.startswith(("600", "601", "603", "605", "688")) else f"sz{code}"


def infer_date_range(path: Path = RAW_BASE_PATH) -> tuple[str, str]:
    df = pd.read_csv(path, dtype={"stock_code": str})
    dates = pd.to_datetime(df["trade_date"], errors="coerce").dropna()
    if dates.empty:
        raise ValueError("Cannot infer date range from raw_base_price_panel_v1_2.csv")
    return dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d")


def short_start_date(end_date: str, short_window_days: int) -> str:
    return (pd.to_datetime(end_date) - timedelta(days=short_window_days)).strftime("%Y-%m-%d")


def pick_date_series(frame: pd.DataFrame) -> pd.Series | None:
    for col in ["date", "日期"]:
        if col in frame.columns:
            return pd.to_datetime(frame[col], errors="coerce")
    if frame.index.name or not isinstance(frame.index, pd.RangeIndex):
        return pd.to_datetime(frame.index, errors="coerce")
    return None


def pick_close_series(frame: pd.DataFrame) -> pd.Series | None:
    for col in ["close", "收盘"]:
        if col in frame.columns:
            return pd.to_numeric(frame[col], errors="coerce")
    return None


def call_endpoint(
    call: Callable[[], Any],
    *,
    stock_code: str,
    source_name: str,
    symbol_used: str,
    window_type: str,
    start_date: str,
    end_date: str,
) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        result = call()
        elapsed = time.perf_counter() - started
        frame = result if isinstance(result, pd.DataFrame) else pd.DataFrame(result)
        row_count = len(frame)
        dates = pick_date_series(frame)
        closes = pick_close_series(frame)
        if row_count == 0 or dates is None or closes is None:
            return result_row(stock_code, source_name, symbol_used, window_type, start_date, end_date, "invalid_schema", row_count, frame, elapsed)
        valid = pd.DataFrame({"date": dates, "close": closes}).dropna(subset=["date", "close"]).sort_values("date")
        if valid.empty or float(valid.iloc[-1]["close"]) <= 0:
            return result_row(stock_code, source_name, symbol_used, window_type, start_date, end_date, "invalid_schema", row_count, frame, elapsed)
        return result_row(
            stock_code,
            source_name,
            symbol_used,
            window_type,
            start_date,
            end_date,
            "ok",
            row_count,
            frame,
            elapsed,
            first_date=valid.iloc[0]["date"].strftime("%Y-%m-%d"),
            last_date=valid.iloc[-1]["date"].strftime("%Y-%m-%d"),
            latest_close=float(valid.iloc[-1]["close"]),
        )
    except Exception as exc:
        elapsed = time.perf_counter() - started
        return result_row(stock_code, source_name, symbol_used, window_type, start_date, end_date, "error", 0, pd.DataFrame(), elapsed, error=exc)


def result_row(
    stock_code: str,
    source_name: str,
    symbol_used: str,
    window_type: str,
    start_date: str,
    end_date: str,
    status: str,
    row_count: int,
    frame: pd.DataFrame,
    elapsed: float,
    *,
    first_date: str = "",
    last_date: str = "",
    latest_close: float | str = "",
    error: Exception | None = None,
) -> dict[str, Any]:
    return {
        "stock_code": code6(stock_code),
        "source_name": source_name,
        "symbol_used": symbol_used,
        "adjust_type": "qfq",
        "window_type": window_type,
        "start_date": start_date,
        "end_date": end_date,
        "status": status,
        "row_count": row_count,
        "columns": ",".join(map(str, frame.columns)),
        "first_date": first_date,
        "last_date": last_date,
        "latest_close": latest_close,
        "elapsed_seconds": round(elapsed, 3),
        "error_type": type(error).__name__ if error else "",
        "error_message": str(error) if error else "",
    }


def build_call_plan(symbols: list[str], start_date: str, end_date: str, short_window_days: int) -> list[dict[str, str]]:
    short_start = short_start_date(end_date, short_window_days)
    plan: list[dict[str, str]] = []
    for symbol in symbols:
        code = code6(symbol)
        plan.extend(
            [
                {"stock_code": code, "source_name": "sina_daily", "symbol_used": sina_symbol(code), "window_type": "short", "start_date": short_start, "end_date": end_date},
                {"stock_code": code, "source_name": "eastmoney_hist", "symbol_used": code, "window_type": "short", "start_date": short_start, "end_date": end_date},
                {"stock_code": code, "source_name": "sina_daily", "symbol_used": sina_symbol(code), "window_type": "full", "start_date": start_date, "end_date": end_date},
                {"stock_code": code, "source_name": "eastmoney_hist", "symbol_used": code, "window_type": "full", "start_date": start_date, "end_date": end_date},
            ]
        )
    return plan


def execute_plan(ak_module: Any, plan: list[dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if ak_module is None:
        return [
            result_row(row["stock_code"], row["source_name"], row["symbol_used"], row["window_type"], row["start_date"], row["end_date"], "error", 0, pd.DataFrame(), 0.0, error=ImportError("akshare is not importable"))
            for row in plan
        ]
    for index, item in enumerate(plan, start=1):
        print(f"[{index}/{len(plan)}] {item['stock_code']} {item['source_name']} {item['window_type']} start", flush=True)
        if item["source_name"] == "sina_daily":
            call = lambda item=item: ak_module.stock_zh_a_daily(
                symbol=item["symbol_used"],
                start_date=yyyymmdd(item["start_date"]),
                end_date=yyyymmdd(item["end_date"]),
                adjust="qfq",
            )
        else:
            call = lambda item=item: ak_module.stock_zh_a_hist(
                symbol=item["symbol_used"],
                period="daily",
                start_date=yyyymmdd(item["start_date"]),
                end_date=yyyymmdd(item["end_date"]),
                adjust="qfq",
            )
        row = call_endpoint(call, **item)
        print(f"[{index}/{len(plan)}] {item['stock_code']} {item['source_name']} {item['window_type']} {row['status']} rows={row['row_count']} elapsed={row['elapsed_seconds']}s", flush=True)
        rows.append(row)
    return rows


def status_lines(df: pd.DataFrame) -> list[str]:
    if df.empty:
        return ["- none"]
    counts = df.groupby(["stock_code", "source_name", "window_type", "status"], dropna=False).size().reset_index(name="count")
    return [f"- {r.stock_code} | {r.source_name} | {r.window_type} | {r.status}: {r['count']}" for _, r in counts.iterrows()]


def render_report(rows: list[dict[str, Any]]) -> str:
    df = pd.DataFrame(rows, columns=COLUMNS)
    push2his_errors = df["error_message"].astype(str).str.contains("push2his.eastmoney.com", case=False, na=False) if not df.empty else pd.Series(dtype=bool)
    sina_ok = bool((df["source_name"].eq("sina_daily") & df["status"].eq("ok")).any()) if not df.empty else False
    eastmoney_ok = bool((df["source_name"].eq("eastmoney_hist") & df["status"].eq("ok")).any()) if not df.empty else False
    return "\n".join(
        [
            "# QFQ Source Diagnostics v1.2",
            "",
            f"- total_calls: {len(df)}",
            f"- Eastmoney push2his failure concentration: {int(push2his_errors.sum())} rows mention push2his.eastmoney.com",
            f"- Sina daily fallback candidate: {'yes' if sina_ok else 'no'}",
            f"- Eastmoney qfq available in diagnostics: {'yes' if eastmoney_ok else 'no'}",
            "",
            "## Status Summary",
            *status_lines(df),
            "",
            "## Interpretation",
            "- Diagnostic only; no qfq enrichment cache was written.",
            "- If Sina daily succeeds with usable qfq rows, next step is to add source_order=[\"cache\",\"sina_daily\",\"eastmoney_hist\"] to enrich_qfq_slow_v1_2.py.",
            "",
        ]
    )


def write_outputs(rows: list[dict[str, Any]]) -> None:
    CSV_OUT.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=COLUMNS).to_csv(CSV_OUT, index=False, encoding="utf-8-sig")
    MD_OUT.write_text(render_report(rows), encoding="utf-8")


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Diagnose alternative qfq sources for stock pool v1.2.")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS))
    p.add_argument("--start-date")
    p.add_argument("--end-date")
    p.add_argument("--short-window-days", type=int, default=180)
    return p


def main() -> None:
    args = parser().parse_args()
    default_start, default_end = infer_date_range()
    start_date = args.start_date or default_start
    end_date = args.end_date or default_end
    plan = build_call_plan(parse_symbols(args.symbols), start_date, end_date, args.short_window_days)
    rows = execute_plan(ak, plan)
    write_outputs(rows)
    print(f"wrote {CSV_OUT}", flush=True)
    print(f"wrote {MD_OUT}", flush=True)


if __name__ == "__main__":
    main()
