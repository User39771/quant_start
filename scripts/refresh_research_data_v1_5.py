from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd


INDEX_IDENTITIES = {
    "000300": {"name": "CSI 300", "tx_symbol": "sh000300"},
    "000852": {"name": "CSI 1000", "tx_symbol": "sh000852"},
    "399006": {"name": "ChiNext Index", "tx_symbol": "sz399006"},
}


def code6(value: object) -> str:
    return str(value).strip().split(".")[0].zfill(6)


def _date_close(raw: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    date_col = next((c for c in ("trade_date", "date", "日期") if c in raw), None)
    close_col = next((c for c in ("qfq_close", "close", "收盘") if c in raw), None)
    if not date_col or not close_col:
        raise ValueError("missing date/close columns")
    dates = pd.to_datetime(raw[date_col], errors="raise")
    closes = pd.to_numeric(raw[close_col], errors="raise")
    if raw.empty or closes.le(0).any():
        raise ValueError("empty or nonpositive close data")
    return dates, closes


def normalize_stock(code: str, raw: pd.DataFrame, source: str) -> pd.DataFrame:
    dates, closes = _date_close(raw)
    out = pd.DataFrame({
        "stock_code": code6(code),
        "trade_date": dates.dt.strftime("%Y-%m-%d"),
        "qfq_close": closes,
        "source_qfq": source,
    }).drop_duplicates(["stock_code", "trade_date"], keep="last")
    if out.empty:
        raise ValueError("empty normalized stock data")
    return out.sort_values("trade_date").reset_index(drop=True)


def normalize_benchmark(code: str, raw: pd.DataFrame, source: str) -> pd.DataFrame:
    code = code6(code)
    if code not in INDEX_IDENTITIES:
        raise ValueError(f"unsupported benchmark {code}")
    dates, closes = _date_close(raw)
    return pd.DataFrame({
        "benchmark_code": code,
        "trade_date": dates.dt.strftime("%Y-%m-%d"),
        "close": closes,
        "instrument_type": "index",
        "instrument_name": INDEX_IDENTITIES[code]["name"],
        "source": source,
    }).drop_duplicates(["benchmark_code", "trade_date"], keep="last").sort_values("trade_date").reset_index(drop=True)


def refresh_stock(
    code: str,
    start_date: str,
    end_date: str,
    primary: Callable,
    fallback: Callable,
    seed_path: Path | None,
) -> tuple[pd.DataFrame, str, bool, list[str]]:
    errors: list[str] = []
    for fetch, source in (
        (primary, "ak.stock_zh_a_daily"),
        (fallback, "ak.stock_zh_a_hist"),
    ):
        try:
            return normalize_stock(code, fetch(code, start_date, end_date), source), source, False, errors
        except Exception as exc:
            errors.append(f"{source}: {exc}")
    if seed_path and seed_path.exists():
        seed = pd.read_csv(seed_path, dtype={"stock_code": str})
        return normalize_stock(code, seed, "seeded_from_v1_2"), "seeded_from_v1_2", True, errors
    raise RuntimeError("; ".join(errors))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _default_stock_primary(code: str, start: str, end: str) -> pd.DataFrame:
    import akshare as ak
    prefix = "sh" if code6(code).startswith(("600", "601", "603", "605", "688")) else "sz"
    return ak.stock_zh_a_daily(symbol=prefix + code6(code), start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="qfq")


def _default_stock_fallback(code: str, start: str, end: str) -> pd.DataFrame:
    import akshare as ak
    return ak.stock_zh_a_hist(symbol=code6(code), start_date=start.replace("-", ""), end_date=end.replace("-", ""), adjust="qfq")


def _default_index_primary(code: str, *_: str) -> pd.DataFrame:
    import akshare as ak
    return ak.stock_zh_index_daily_tx(symbol=INDEX_IDENTITIES[code6(code)]["tx_symbol"])


def _default_index_fallback(code: str, start: str, end: str) -> pd.DataFrame:
    import akshare as ak
    return ak.index_zh_a_hist(symbol=code6(code), start_date=start.replace("-", ""), end_date=end.replace("-", ""))


def run(
    root: Path,
    start_date: str,
    end_date: str,
    stock_primary: Callable = _default_stock_primary,
    stock_fallback: Callable = _default_stock_fallback,
    index_primary: Callable = _default_index_primary,
    index_fallback: Callable = _default_index_fallback,
    sleep_seconds: float = 0,
) -> dict:
    del sleep_seconds  # Source throttling belongs in the caller when live fetching.
    root = Path(root)
    processed, reports = root / "data" / "processed", root / "reports"
    stock_cache = root / "data" / "cache" / "qfq_refresh_v1_5"
    index_cache = root / "data" / "cache" / "benchmark_refresh_v1_5"
    universe = pd.read_csv(processed / "research_universe_lowvol_freeze_20260711.csv", dtype=str)
    code_col = "stock_code" if "stock_code" in universe else "code"
    codes = universe[code_col].map(code6).drop_duplicates().tolist()
    stock_frames, manifests, failures = [], [], []
    fetched_at = datetime.now(timezone.utc).isoformat()
    for code in codes:
        try:
            frame, source, seeded, errors = refresh_stock(
                code, start_date, end_date, stock_primary, stock_fallback,
                root / "data" / "cache" / "qfq_enrichment_v1_2" / f"{code}.csv",
            )
            path = stock_cache / f"{code}.csv"
            _write(frame, path)
            stock_frames.append(frame)
            manifests.append({"stock_code": code, "status": "seeded" if seeded else "ok", "source": source, "fetched_at": fetched_at, "cache_path": str(path), "sha256": _sha256(path), "errors": " | ".join(errors)})
        except Exception as exc:
            failures.append({"stock_code": code, "error": str(exc)})
            manifests.append({"stock_code": code, "status": "error", "source": "", "fetched_at": fetched_at, "cache_path": "", "sha256": "", "errors": str(exc)})
    qfq = pd.concat(stock_frames, ignore_index=True) if stock_frames else pd.DataFrame(columns=["stock_code", "trade_date", "qfq_close", "source_qfq"])
    adjusted = qfq.assign(adjusted_close=qfq.get("qfq_close"), adjusted_flag=True)

    index_frames = []
    for code in INDEX_IDENTITIES:
        errors = []
        frame = None
        used_source = ""
        for fetch, source in ((index_primary, "ak.stock_zh_index_daily_tx"), (index_fallback, "ak.index_zh_a_hist")):
            try:
                frame = normalize_benchmark(code, fetch(code, start_date, end_date), source)
                used_source = source
                break
            except Exception as exc:
                errors.append(f"{source}: {exc}")
        if frame is None:
            old = processed / "hybrid_benchmark_panel_v1_2.csv"
            if old.exists():
                seed = pd.read_csv(old, dtype={"benchmark_code": str})
                seed = seed[seed["benchmark_code"].map(code6).eq(code)]
                if not seed.empty:
                    frame = normalize_benchmark(code, seed, "seeded_from_v1_2")
        if frame is not None:
            path = index_cache / f"{code}.csv"
            _write(frame, path)
            index_frames.append(frame)
            manifests.append({"stock_code": code, "status": "ok", "source": used_source or "seeded_from_v1_2", "fetched_at": fetched_at, "cache_path": str(path), "sha256": _sha256(path), "errors": " | ".join(errors), "instrument_type": "index"})
        else:
            failures.append({"stock_code": code, "error": " | ".join(errors)})
            manifests.append({"stock_code": code, "status": "error", "source": "", "fetched_at": fetched_at, "cache_path": "", "sha256": "", "errors": " | ".join(errors), "instrument_type": "index"})
    benchmarks = pd.concat(index_frames, ignore_index=True) if index_frames else pd.DataFrame()

    _write(qfq, processed / "qfq_enrichment_panel_v1_5.csv")
    _write(adjusted, processed / "adjusted_price_panel_v1_5.csv")
    _write(benchmarks, processed / "hybrid_benchmark_panel_v1_5.csv")
    _write(pd.DataFrame(manifests), reports / "qfq_refresh_manifest_v1_5.csv")
    _write(pd.DataFrame(failures, columns=["stock_code", "error"]), reports / "qfq_refresh_failures_v1_5.csv")
    coverage = qfq["stock_code"].nunique() / len(codes) if codes else 0.0
    benchmark_codes = set(benchmarks.get("benchmark_code", pd.Series(dtype=str)))
    critical = bool(
        coverage == 1.0
        and not qfq.duplicated(["stock_code", "trade_date"]).any()
        and (qfq["qfq_close"] > 0).all()
        and not benchmarks.duplicated(["benchmark_code", "trade_date"]).any()
        and benchmark_codes == set(INDEX_IDENTITIES)
        and benchmarks["instrument_type"].eq("index").all()
        and (benchmarks["close"] > 0).all()
    )
    qa = {
        "critical_qa_pass": critical,
        "stock_coverage_ratio": coverage,
        "stock_count": qfq["stock_code"].nunique(),
        "row_count": len(qfq),
        "min_date": qfq["trade_date"].min(),
        "max_date": qfq["trade_date"].max(),
        "duplicate_stock_date_count": int(qfq.duplicated(["stock_code", "trade_date"]).sum()),
        "benchmark_count": len(benchmark_codes),
        "benchmark_max_date": benchmarks["trade_date"].max() if not benchmarks.empty else "",
        "failed_instrument_count": len(failures),
    }
    _write(pd.DataFrame([qa]), reports / "adjusted_price_panel_QA_v1_5.csv")
    (reports / "adjusted_price_panel_QA_v1_5.md").write_text(
        f"# Adjusted Price Panel QA v1.5\n\n- critical_qa_pass: {str(critical).lower()}\n- stock_coverage_ratio: {coverage:.6f}\n- formal_performance_conclusion_allowed: false\n",
        encoding="utf-8",
    )
    _write(pd.DataFrame(), reports / "qfq_refresh_diff_v1_5.csv")
    return {"qa": qa}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=Path(__file__).resolve().parents[1])
    parser.add_argument("--start-date", default="2020-01-01")
    parser.add_argument("--end-date", default=datetime.now().date().isoformat())
    args = parser.parse_args(argv)
    result = run(Path(args.project_root), args.start_date, args.end_date)
    return 0 if result["qa"]["critical_qa_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
