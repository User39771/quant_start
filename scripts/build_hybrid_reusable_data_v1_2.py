from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

try:
    import akshare as ak
except Exception:  # pragma: no cover
    ak = None


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_UNIVERSE = ROOT / "data" / "processed" / "backtest_universe_research_v1_2.csv"
EXPANDED_UNIVERSE = ROOT / "data" / "processed" / "backtest_universe_expanded_only_v1_2.csv"
LEGACY_PRICE_CACHE = ROOT / "data" / "cache" / "price"
RAW_BASE_OUT = ROOT / "data" / "processed" / "raw_base_price_panel_v1_2.csv"
BENCHMARK_OUT = ROOT / "data" / "processed" / "hybrid_benchmark_panel_v1_2.csv"
MANIFEST_OUT = ROOT / "data" / "processed" / "hybrid_data_manifest_v1_2.csv"
GAPS_OUT = ROOT / "reports" / "hybrid_data_gaps_v1_2.csv"
REPORT_OUT = ROOT / "reports" / "hybrid_reusable_data_readiness_v1_2.md"

RAW_BASE_COLUMNS = [
    "stock_code",
    "trade_date",
    "close",
    "high",
    "low",
    "amount",
    "total_market_cap",
    "circulating_market_cap",
    "source",
    "data_layer",
    "adjusted_flag",
]
BENCHMARK_COLUMNS = [
    "benchmark_code",
    "trade_date",
    "open",
    "high",
    "low",
    "close",
    "amount",
    "pre_close",
    "source",
    "data_layer",
]
MANIFEST_COLUMNS = [
    "symbol",
    "asset_type",
    "source",
    "data_layer",
    "status",
    "row_count",
    "start_date",
    "end_date",
    "adjusted_flag",
    "elapsed_seconds",
    "error_type",
    "error_message",
]
GAP_COLUMNS = ["symbol", "asset_type", "gap_type", "details"]
REQUIRED_BENCHMARKS = ["000300", "000852"]
OPTIONAL_BENCHMARKS = ["399006"]


def code6(value: Any) -> str:
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return "".join(ch for ch in text if ch.isdigit()).zfill(6)[-6:]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def tx_symbol(symbol: str) -> str:
    return f"sz{symbol}" if code6(symbol).startswith("399") else f"sh{code6(symbol)}"


def read_universe(path: Path) -> list[str]:
    df = pd.read_csv(path, dtype={"code": str, "stock_code": str})
    col = "stock_code" if "stock_code" in df.columns else "code"
    return sorted({code6(value) for value in df[col].dropna()})


def numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce")


def clip_date_window(frame: pd.DataFrame, date_col: str, start_date: str, end_date: str) -> pd.DataFrame:
    if frame.empty or not start_date or not end_date:
        return frame.copy()
    dates = pd.to_datetime(frame[date_col], errors="coerce")
    mask = (dates >= pd.to_datetime(start_date)) & (dates <= pd.to_datetime(end_date))
    return frame.loc[mask].reset_index(drop=True)


def normalize_legacy_price_cache(symbol: str, raw: pd.DataFrame, path: Path) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "stock_code": code6(symbol),
            "trade_date": pd.to_datetime(raw.get("date"), errors="coerce").dt.strftime("%Y-%m-%d"),
            "close": numeric(raw.get("close", pd.Series(dtype=float))),
            "high": numeric(raw.get("high", pd.Series(dtype=float))),
            "low": numeric(raw.get("low", pd.Series(dtype=float))),
            "amount": numeric(raw.get("amount", pd.Series(dtype=float))),
            "total_market_cap": numeric(raw.get("total_market_cap", pd.Series(dtype=float))),
            "circulating_market_cap": numeric(raw.get("circulating_market_cap", pd.Series(dtype=float))),
            "source": str(path),
            "data_layer": "legacy_db_price_cache",
            "adjusted_flag": "false",
        }
    )
    return out.reindex(columns=RAW_BASE_COLUMNS).dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)


def build_raw_base_panel(symbols: list[str], cache_dir: Path = LEGACY_PRICE_CACHE) -> tuple[pd.DataFrame, list[dict[str, str]], list[dict[str, Any]]]:
    frames: list[pd.DataFrame] = []
    gaps: list[dict[str, str]] = []
    manifest: list[dict[str, Any]] = []
    for symbol in symbols:
        started = time.perf_counter()
        path = cache_dir / f"{code6(symbol)}.csv"
        if not path.exists():
            gaps.append({"symbol": code6(symbol), "asset_type": "stock", "gap_type": "missing_legacy_price_cache", "details": str(path)})
            manifest.append(manifest_row(symbol, "stock", "legacy_db_price_cache", "legacy_db_price_cache", "missing", 0, "", "", "false", time.perf_counter() - started))
            continue
        try:
            raw = pd.read_csv(path, dtype=str)
            frame = normalize_legacy_price_cache(symbol, raw, path)
            before = len(frame)
            frame = frame.dropna(subset=["close"])
            if len(frame) < before:
                gaps.append({"symbol": code6(symbol), "asset_type": "stock", "gap_type": "dropped_missing_close", "details": f"{before - len(frame)} rows"})
            for col in ["high", "low", "amount"]:
                missing = int(frame[col].isna().sum()) if col in frame else len(frame)
                if missing:
                    gaps.append({"symbol": code6(symbol), "asset_type": "stock", "gap_type": f"missing_{col}", "details": f"{missing} rows"})
            frames.append(frame)
            dates = pd.to_datetime(frame["trade_date"], errors="coerce")
            manifest.append(manifest_row(symbol, "stock", str(path), "legacy_db_price_cache", "ok", len(frame), str(dates.min().date()), str(dates.max().date()), "false", time.perf_counter() - started))
        except Exception as exc:
            gaps.append({"symbol": code6(symbol), "asset_type": "stock", "gap_type": "legacy_cache_read_error", "details": f"{type(exc).__name__}: {exc}"})
            manifest.append(manifest_row(symbol, "stock", str(path), "legacy_db_price_cache", "error", 0, "", "", "false", time.perf_counter() - started, exc))
    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=RAW_BASE_COLUMNS)
    return panel.reindex(columns=RAW_BASE_COLUMNS), gaps, manifest


def manifest_row(
    symbol: str,
    asset_type: str,
    source: str,
    data_layer: str,
    status: str,
    row_count: int,
    start_date: str,
    end_date: str,
    adjusted_flag: str,
    elapsed_seconds: float,
    error: Exception | None = None,
) -> dict[str, Any]:
    return {
        "symbol": code6(symbol),
        "asset_type": asset_type,
        "source": source,
        "data_layer": data_layer,
        "status": status,
        "row_count": row_count,
        "start_date": start_date,
        "end_date": end_date,
        "adjusted_flag": adjusted_flag,
        "elapsed_seconds": round(elapsed_seconds, 3),
        "error_type": type(error).__name__ if error else "",
        "error_message": str(error) if error else "",
    }


def normalize_tx_benchmark(symbol: str, raw: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(
        {
            "benchmark_code": code6(symbol),
            "trade_date": pd.to_datetime(raw.get("date"), errors="coerce").dt.strftime("%Y-%m-%d"),
            "open": numeric(raw.get("open", pd.Series(dtype=float))),
            "high": numeric(raw.get("high", pd.Series(dtype=float))),
            "low": numeric(raw.get("low", pd.Series(dtype=float))),
            "close": numeric(raw.get("close", pd.Series(dtype=float))),
            "amount": numeric(raw.get("amount", pd.Series(dtype=float))),
            "source": "ak.stock_zh_index_daily_tx",
            "data_layer": "akshare_tx_index_fallback",
        }
    )
    out = out.dropna(subset=["trade_date", "close"]).sort_values("trade_date").reset_index(drop=True)
    out["pre_close"] = out.groupby("benchmark_code")["close"].shift(1)
    return out.reindex(columns=BENCHMARK_COLUMNS)


def fetch_benchmarks(symbols: list[str], start_date: str = "", end_date: str = "") -> tuple[pd.DataFrame, list[dict[str, str]], list[dict[str, Any]]]:
    frames: list[pd.DataFrame] = []
    gaps: list[dict[str, str]] = []
    manifest: list[dict[str, Any]] = []
    for symbol in symbols:
        started = time.perf_counter()
        if ak is None or not hasattr(ak, "stock_zh_index_daily_tx"):
            exc = RuntimeError("akshare stock_zh_index_daily_tx unavailable")
            gaps.append({"symbol": code6(symbol), "asset_type": "benchmark", "gap_type": "benchmark_fetch_unavailable", "details": str(exc)})
            manifest.append(manifest_row(symbol, "benchmark", "ak.stock_zh_index_daily_tx", "akshare_tx_index_fallback", "error", 0, "", "", "false", time.perf_counter() - started, exc))
            continue
        try:
            raw = ak.stock_zh_index_daily_tx(symbol=tx_symbol(symbol))
            frame = clip_date_window(normalize_tx_benchmark(symbol, raw), "trade_date", start_date, end_date)
            frames.append(frame)
            dates = pd.to_datetime(frame["trade_date"], errors="coerce")
            if frame.empty or not dates.notna().any():
                gaps.append({"symbol": code6(symbol), "asset_type": "benchmark", "gap_type": "benchmark_empty_window", "details": f"{start_date}..{end_date}"})
                manifest.append(manifest_row(symbol, "benchmark", "ak.stock_zh_index_daily_tx", "akshare_tx_index_fallback", "error", 0, "", "", "false", time.perf_counter() - started, RuntimeError("empty benchmark date window")))
            else:
                manifest.append(manifest_row(symbol, "benchmark", "ak.stock_zh_index_daily_tx", "akshare_tx_index_fallback", "ok", len(frame), str(dates.min().date()), str(dates.max().date()), "false", time.perf_counter() - started))
        except Exception as exc:
            gaps.append({"symbol": code6(symbol), "asset_type": "benchmark", "gap_type": "benchmark_fetch_error", "details": f"{type(exc).__name__}: {exc}"})
            manifest.append(manifest_row(symbol, "benchmark", "ak.stock_zh_index_daily_tx", "akshare_tx_index_fallback", "error", 0, "", "", "false", time.perf_counter() - started, exc))
    panel = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=BENCHMARK_COLUMNS)
    return panel.reindex(columns=BENCHMARK_COLUMNS), gaps, manifest


def evaluate_readiness(raw_panel: pd.DataFrame, benchmark_panel: pd.DataFrame, universe_codes: list[str], gaps: list[dict[str, str]]) -> dict[str, Any]:
    covered = set(raw_panel["stock_code"].dropna().map(code6)) if "stock_code" in raw_panel else set()
    coverage = len(covered) / len(set(universe_codes)) if universe_codes else 0.0
    required_bench = set(REQUIRED_BENCHMARKS)
    found_bench = set(benchmark_panel["benchmark_code"].dropna().map(code6)) if "benchmark_code" in benchmark_panel else set()
    has_qfq = "qfq_close" in raw_panel.columns and raw_panel["qfq_close"].notna().any()
    has_execution_fields = all(col in raw_panel.columns and raw_panel[col].notna().any() for col in ["open", "volume", "pre_close"])
    raw_base_ready = coverage >= 0.95 and "close" in raw_panel and raw_panel["close"].notna().any()
    benchmark_ready = required_bench.issubset(found_bench)
    adjusted_return_ready = bool(raw_base_ready and has_qfq)
    execution_sim_ready = bool(raw_base_ready and benchmark_ready and adjusted_return_ready and has_execution_fields)
    return {
        "raw_base_ready": bool(raw_base_ready),
        "benchmark_ready": bool(benchmark_ready),
        "adjusted_return_ready": bool(adjusted_return_ready),
        "execution_sim_ready": bool(execution_sim_ready),
        "formal_performance_conclusion_allowed": bool(adjusted_return_ready and execution_sim_ready),
        "universe_count": len(set(universe_codes)),
        "covered_stock_count": len(covered),
        "stock_coverage_ratio": coverage,
        "missing_required_benchmarks": ",".join(sorted(required_bench - found_bench)),
        "gap_count": len(gaps),
    }


def render_report(readiness: dict[str, Any], manifest: pd.DataFrame, gaps: pd.DataFrame) -> str:
    status_counts = manifest["status"].value_counts().to_dict() if not manifest.empty else {}
    gap_counts = gaps["gap_type"].value_counts().to_dict() if not gaps.empty else {}
    return "\n".join(
        [
            "# Hybrid Reusable Data Readiness v1.2",
            "",
            f"- raw_base_ready: {str(readiness['raw_base_ready']).lower()}",
            f"- benchmark_ready: {str(readiness['benchmark_ready']).lower()}",
            f"- adjusted_return_ready: {str(readiness['adjusted_return_ready']).lower()}",
            f"- execution_sim_ready: {str(readiness['execution_sim_ready']).lower()}",
            f"- formal_performance_conclusion_allowed: {str(readiness['formal_performance_conclusion_allowed']).lower()}",
            f"- stock_coverage: {readiness['covered_stock_count']}/{readiness['universe_count']} ({readiness['stock_coverage_ratio']:.2%})",
            f"- missing_required_benchmarks: {readiness['missing_required_benchmarks'] or 'none'}",
            f"- manifest_status_counts: {status_counts}",
            f"- gap_counts: {gap_counts}",
            "",
            "## Price Adjustment Judgement",
            "- Existing `data/cache/price` files are treated as raw/unverified prices.",
            "- Evidence: `akshare_code_inventory_v1_2` traces the cache primarily to PostgreSQL `public.stock_prices`; sampled files do not include `qfq_close`, `adj_factor`, or adjustment metadata.",
            "- Therefore `adjusted_flag=false` for raw base panel rows.",
            "",
            "## Caveats",
            "- Raw base data can support cache-coverage checks and smoke close baselines only.",
            "- Missing qfq/open/volume/pre_close keeps adjusted return and execution simulation readiness false.",
            "- No silent forward fill is applied to missing stock prices.",
            "",
        ]
    )


def write_csv(path: Path, frame: pd.DataFrame, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.reindex(columns=columns).to_csv(path, index=False, encoding="utf-8-sig")


def run(fetch_benchmark: bool = True, include_optional_benchmark: bool = True) -> dict[str, Any]:
    universe_codes = read_universe(RESEARCH_UNIVERSE)
    raw_panel, stock_gaps, stock_manifest = build_raw_base_panel(universe_codes, LEGACY_PRICE_CACHE)
    raw_dates = pd.to_datetime(raw_panel["trade_date"], errors="coerce") if not raw_panel.empty else pd.Series(dtype="datetime64[ns]")
    start_date = str(raw_dates.min().date()) if raw_dates.notna().any() else ""
    end_date = str(raw_dates.max().date()) if raw_dates.notna().any() else ""
    benchmark_symbols = REQUIRED_BENCHMARKS + (OPTIONAL_BENCHMARKS if include_optional_benchmark else [])
    if fetch_benchmark:
        benchmark_panel, benchmark_gaps, benchmark_manifest = fetch_benchmarks(benchmark_symbols, start_date, end_date)
    else:
        benchmark_panel, benchmark_gaps, benchmark_manifest = pd.DataFrame(columns=BENCHMARK_COLUMNS), [], []
    gaps = stock_gaps + benchmark_gaps
    manifest = pd.DataFrame(stock_manifest + benchmark_manifest, columns=MANIFEST_COLUMNS)
    gap_frame = pd.DataFrame(gaps, columns=GAP_COLUMNS)
    readiness = evaluate_readiness(raw_panel, benchmark_panel, universe_codes, gaps)
    write_csv(RAW_BASE_OUT, raw_panel, RAW_BASE_COLUMNS)
    write_csv(BENCHMARK_OUT, benchmark_panel, BENCHMARK_COLUMNS)
    write_csv(MANIFEST_OUT, manifest, MANIFEST_COLUMNS)
    write_csv(GAPS_OUT, gap_frame, GAP_COLUMNS)
    REPORT_OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT_OUT.write_text(render_report(readiness, manifest, gap_frame), encoding="utf-8")
    return readiness


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Build hybrid reusable v1.2 data panels from stable local cache paths.")
    p.add_argument("--skip-benchmark-fetch", action="store_true")
    p.add_argument("--required-benchmarks-only", action="store_true")
    return p


def main() -> None:
    args = parser().parse_args()
    readiness = run(fetch_benchmark=not args.skip_benchmark_fetch, include_optional_benchmark=not args.required_benchmarks_only)
    for key in ["raw_base_ready", "benchmark_ready", "adjusted_return_ready", "execution_sim_ready", "formal_performance_conclusion_allowed"]:
        print(f"{key}={str(readiness[key]).lower()}")
    print(f"stock_coverage={readiness['covered_stock_count']}/{readiness['universe_count']} ({readiness['stock_coverage_ratio']:.2%})")


if __name__ == "__main__":
    main()
