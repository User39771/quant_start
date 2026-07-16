"""Read-only QFQ overlap forensics for blocked prospective refresh rows."""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd


ATOL, RTOL = 1e-10, 1e-8
MIN_COMMON_DATES = 5
ALLOWED_CODES = {"002044", "002230"}
STATUS_VALUES = {
    "tier1_factor_bridge_supported",
    "tier1_rescaling_supported",
    "tier2_only_supported",
    "confirmed_source_error",
    "unresolved",
}
MANIFEST_COLUMNS = [
    "stock_code", "evidence_type", "source", "source_url", "path", "bytes",
    "sha256", "row_count", "min_date", "max_date", "displayed_decimal_places",
    "normalization_decimal_places", "observed_price_tick", "rounding_model",
    "comparison_tolerance", "status", "error",
]
OVERLAP_COLUMNS = [
    "stock_code", "trade_date", "frozen_qfq", "refreshed_qfq",
    "multiplicative_scale", "scaled_refreshed_qfq", "multiplicative_residual",
    "additive_shift", "shifted_refreshed_qfq", "additive_residual",
    "source_tolerance", "multiplicative_normalized_error",
    "additive_normalized_error", "included_in_fit", "exclusion_reason",
]
ACTION_COLUMNS = [
    "stock_code", "source", "source_url", "implementation_announcement_date",
    "dividend_plan", "bonus_ratio_per_10", "transfer_ratio_per_10",
    "cash_dividend_per_10", "record_date", "ex_date", "payment_date",
    "share_arrival_date", "implementation_note", "publication_time",
    "official_evidence_available", "raw_columns", "notes",
]


def code6(value: object) -> str:
    return str(value).strip().split(".")[0].zfill(6)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_tolerance(displayed_decimals: int, normalized_decimals: int) -> float:
    """Worst-case independent rounding envelope for two displayed prices."""
    return 0.5 * 10 ** (-displayed_decimals) + 0.5 * 10 ** (-normalized_decimals)


def precision_profile(frame: pd.DataFrame, value_col: str, displayed_decimals: int = 2) -> dict[str, object]:
    values = pd.to_numeric(frame.get(value_col, pd.Series(dtype=float)), errors="coerce").dropna()
    unique = np.sort(values.unique())
    diffs = np.diff(unique)
    tick = float(diffs[diffs > ATOL].min()) if (diffs > ATOL).any() else np.nan
    normalized_decimals = max(displayed_decimals, 10)
    return {
        "displayed_decimal_places": displayed_decimals,
        "normalization_decimal_places": normalized_decimals,
        "observed_price_tick": tick,
        "rounding_model": "source values rounded to displayed precision; normalized as float64",
        "comparison_tolerance": source_tolerance(displayed_decimals, normalized_decimals),
    }


def normalize_price(raw: pd.DataFrame, value_name: str) -> pd.DataFrame:
    date_col = next((c for c in ("trade_date", "date", "日期") if c in raw.columns), None)
    close_col = next((c for c in (value_name, "qfq_close", "hfq_close", "close", "收盘") if c in raw.columns), None)
    if date_col is None or close_col is None:
        raise ValueError(f"missing date/close columns: {list(raw.columns)}")
    out = pd.DataFrame({
        "trade_date": pd.to_datetime(raw[date_col], errors="raise").dt.strftime("%Y-%m-%d"),
        value_name: pd.to_numeric(raw[close_col], errors="raise"),
    })
    if out.duplicated("trade_date").any() or (~np.isfinite(out[value_name])).any() or (out[value_name] <= 0).any():
        raise ValueError("duplicate, nonfinite, or nonpositive price evidence")
    return out.sort_values("trade_date").reset_index(drop=True)


def fit_overlap(frozen: pd.DataFrame, refreshed: pd.DataFrame, tolerance: float) -> tuple[pd.DataFrame, dict[str, object]]:
    common = frozen.merge(refreshed, on="trade_date", how="inner")
    valid = (
        np.isfinite(common["frozen_qfq"])
        & np.isfinite(common["refreshed_qfq"])
        & common["frozen_qfq"].gt(0)
        & common["refreshed_qfq"].gt(0)
    )
    common["included_in_fit"] = valid
    common["exclusion_reason"] = np.where(valid, "", "missing_nonfinite_or_nonpositive")
    fitted = common.loc[valid]
    scale = float(np.median(fitted["frozen_qfq"] / fitted["refreshed_qfq"])) if not fitted.empty else np.nan
    shift = float(np.median(fitted["frozen_qfq"] - fitted["refreshed_qfq"])) if not fitted.empty else np.nan
    common["multiplicative_scale"] = scale
    common["scaled_refreshed_qfq"] = common["refreshed_qfq"] * scale
    common["multiplicative_residual"] = common["frozen_qfq"] - common["scaled_refreshed_qfq"]
    common["additive_shift"] = shift
    common["shifted_refreshed_qfq"] = common["refreshed_qfq"] + shift
    common["additive_residual"] = common["frozen_qfq"] - common["shifted_refreshed_qfq"]
    common["source_tolerance"] = tolerance
    common["multiplicative_normalized_error"] = common["multiplicative_residual"].abs() / tolerance
    common["additive_normalized_error"] = common["additive_residual"].abs() / tolerance
    mult_errors = common.loc[valid, "multiplicative_normalized_error"]
    add_errors = common.loc[valid, "additive_normalized_error"]
    summary = {
        "common_date_count": int(valid.sum()),
        "all_common_dates_used": int(valid.sum()) == len(fitted),
        "minimum_common_dates_pass": int(valid.sum()) >= MIN_COMMON_DATES,
        "multiplicative_scale": scale,
        "additive_shift": shift,
        "multiplicative_max_normalized_error": float(mult_errors.max()) if not mult_errors.empty else np.nan,
        "multiplicative_error_dispersion": float(mult_errors.std(ddof=1)) if len(mult_errors) > 1 else np.nan,
        "multiplicative_fit_pass": bool(len(mult_errors) >= MIN_COMMON_DATES and mult_errors.max() <= 1.0),
        "additive_max_normalized_error": float(add_errors.max()) if not add_errors.empty else np.nan,
        "additive_error_dispersion": float(add_errors.std(ddof=1)) if len(add_errors) > 1 else np.nan,
        "additive_fit_pass": bool(len(add_errors) >= MIN_COMMON_DATES and add_errors.max() <= 1.0),
    }
    return common, summary


def raw_total_return(previous_raw: float, post_raw: float, cash_per_10: float = 0.0,
                     bonus_per_10: float = 0.0, transfer_per_10: float = 0.0) -> float:
    shares = 1.0 + (bonus_per_10 + transfer_per_10) / 10.0
    return (post_raw * shares + cash_per_10 / 10.0) / previous_raw - 1.0


def first_boundary_return(prices: pd.DataFrame, ex_date: str, value_col: str) -> float | None:
    dates = pd.to_datetime(prices["trade_date"])
    ex = pd.Timestamp(ex_date)
    before = prices.loc[dates < ex]
    after = prices.loc[dates >= ex]
    if before.empty or after.empty:
        return None
    return float(after.iloc[0][value_col] / before.iloc[-1][value_col] - 1.0)


def reconcile_return(actual: float | None, expected: float | None, tolerance: float) -> bool:
    return bool(actual is not None and expected is not None and np.isfinite(actual) and np.isfinite(expected)
                and abs(actual - expected) <= tolerance)


def reconcile_explicit_qfq_factor(raw: pd.DataFrame, qfq: pd.DataFrame, factors: pd.DataFrame,
                                  raw_col: str, qfq_col: str, factor_col: str,
                                  tolerance: float) -> dict[str, object]:
    prices = raw[["trade_date", raw_col]].merge(qfq[["trade_date", qfq_col]], on="trade_date")
    prices["trade_date"] = pd.to_datetime(prices["trade_date"])
    factor_values = factors[["trade_date", factor_col]].copy()
    factor_values["trade_date"] = pd.to_datetime(factor_values["trade_date"])
    merged = pd.merge_asof(
        prices.sort_values("trade_date"), factor_values.sort_values("trade_date"),
        on="trade_date", direction="backward",
    ).dropna()
    if merged.empty:
        return {"explicit_factor_observation_count": 0, "explicit_factor_max_error": np.nan,
                "explicit_factor_reconciles": False}
    implied = merged[raw_col] / merged[factor_col]
    errors = (implied - merged[qfq_col]).abs()
    return {
        "explicit_factor_observation_count": len(merged),
        "explicit_factor_max_error": float(errors.max()),
        "explicit_factor_reconciles": bool(len(merged) >= MIN_COMMON_DATES and errors.max() <= tolerance),
    }


def raw_implied_by_qfq_factor(qfq: pd.DataFrame, factors: pd.DataFrame,
                              qfq_col: str, factor_col: str) -> pd.DataFrame:
    prices = qfq[["trade_date", qfq_col]].copy()
    prices["trade_date"] = pd.to_datetime(prices["trade_date"])
    factor_values = factors[["trade_date", factor_col]].copy()
    factor_values["trade_date"] = pd.to_datetime(factor_values["trade_date"])
    merged = pd.merge_asof(
        prices.sort_values("trade_date"), factor_values.sort_values("trade_date"),
        on="trade_date", direction="backward",
    ).dropna()
    merged["factor_implied_raw_close"] = merged[qfq_col] * merged[factor_col]
    merged["trade_date"] = merged["trade_date"].dt.strftime("%Y-%m-%d")
    return merged[["trade_date", "factor_implied_raw_close"]]


def classify_evidence(fit: dict[str, object], explicit_factor_reconciles: bool,
                      post_event_reconciles: bool, independent_reconciles: bool,
                      official_action_available: bool, source_error_confirmed: bool = False) -> tuple[str, bool]:
    if source_error_confirmed:
        return "confirmed_source_error", False
    if explicit_factor_reconciles and official_action_available and independent_reconciles:
        return "tier1_factor_bridge_supported", True
    if (fit.get("multiplicative_fit_pass") and post_event_reconciles
            and independent_reconciles and official_action_available):
        return "tier1_rescaling_supported", True
    if official_action_available and post_event_reconciles:
        return "tier2_only_supported", False
    return "unresolved", False


def protected_snapshot(root: Path, failed_run: Path, output: Path) -> dict[str, str]:
    paths = [
        root / "data/processed/adjusted_price_panel_v1_5.csv",
        root / "data/processed/hybrid_benchmark_panel_v1_5.csv",
        root / "reports/prospective/lowvol_v1_5_1/approved_refreshes.csv",
        root / "reports/prospective/lowvol_v1_5_1/prospective_periods.csv",
    ]
    paths += list((root / "data/cache").glob("**/*.csv"))
    paths += list(failed_run.glob("**/*"))
    snapshots = root / "reports/prospective/lowvol_v1_5_1/snapshots"
    paths += list(snapshots.glob("**/*")) if snapshots.exists() else []
    return {
        str(path.relative_to(root)): sha256(path)
        for path in paths if path.is_file() and output not in path.parents
    }


def _ak_price_worker(queue: mp.Queue, code: str, start: str, end: str, source: str, adjust: str) -> None:
    import akshare as ak
    try:
        if source == "sina":
            frame = ak.stock_zh_a_daily(
                symbol="sz" + code, start_date=start.replace("-", ""),
                end_date=end.replace("-", ""), adjust=adjust,
            )
        elif source == "eastmoney":
            frame = ak.stock_zh_a_hist(
                symbol=code, start_date=start.replace("-", ""),
                end_date=end.replace("-", ""), adjust=adjust, timeout=15,
            )
        elif source == "tencent":
            frame = ak.stock_zh_a_hist_tx(
                symbol="sz" + code, start_date=start.replace("-", ""),
                end_date=end.replace("-", ""), adjust=adjust, timeout=15,
            )
        else:
            raise ValueError(source)
        queue.put((True, frame))
    except Exception as exc:
        queue.put((False, f"{type(exc).__name__}: {exc}"))


def _ak_action_worker(queue: mp.Queue, code: str) -> None:
    import akshare as ak
    try:
        queue.put((True, ak.stock_dividend_cninfo(symbol=code)))
    except Exception as exc:
        queue.put((False, f"{type(exc).__name__}: {exc}"))


def _timed_process(target: Callable, args: tuple, timeout: float = 20.0) -> pd.DataFrame:
    context = mp.get_context("spawn")
    queue = context.Queue()
    process = context.Process(target=target, args=(queue, *args))
    process.start()
    process.join(timeout)
    if process.is_alive():
        process.terminate()
        process.join()
        raise TimeoutError(f"endpoint exceeded {timeout:.0f}s forensic timeout")
    if queue.empty():
        raise RuntimeError(f"endpoint worker exited {process.exitcode} without evidence")
    ok, value = queue.get()
    if not ok:
        raise RuntimeError(value)
    return value


def default_price_fetcher(code: str, start: str, end: str, source: str, adjust: str) -> pd.DataFrame:
    return _timed_process(_ak_price_worker, (code, start, end, source, adjust))


def default_action_fetcher(code: str) -> pd.DataFrame:
    return _timed_process(_ak_action_worker, (code,))


def normalize_factor(raw: pd.DataFrame, value_name: str) -> pd.DataFrame:
    date_col = next((c for c in ("trade_date", "date", "日期") if c in raw.columns), None)
    factor_col = next((c for c in raw.columns if "factor" in str(c).lower() or "因子" in str(c)), None)
    if date_col is None or factor_col is None:
        raise ValueError(f"missing date/factor columns: {list(raw.columns)}")
    out = pd.DataFrame({
        "trade_date": pd.to_datetime(raw[date_col], errors="raise").dt.strftime("%Y-%m-%d"),
        value_name: pd.to_numeric(raw[factor_col], errors="raise"),
    })
    if out.duplicated("trade_date").any() or (~np.isfinite(out[value_name])).any() or (out[value_name] <= 0).any():
        raise ValueError("duplicate, nonfinite, or nonpositive factor evidence")
    return out.sort_values("trade_date").reset_index(drop=True)


def normalize_actions(code: str, raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame(columns=ACTION_COLUMNS)
    # CNInfo API p_sysapi1139 has a stable positional schema; retain original labels for audit.
    fields = [
        "implementation_announcement_date", "dividend_plan", "bonus_ratio_per_10",
        "transfer_ratio_per_10", "cash_dividend_per_10", "record_date", "ex_date",
        "payment_date", "share_arrival_date", "implementation_note", "publication_time",
    ]
    if len(raw.columns) < len(fields):
        raise ValueError(f"unexpected CNInfo dividend schema: {list(raw.columns)}")
    out = raw.iloc[:, :len(fields)].copy()
    out.columns = fields
    for field in ("implementation_announcement_date", "record_date", "ex_date", "payment_date"):
        out[field] = pd.to_datetime(out[field], errors="coerce").dt.strftime("%Y-%m-%d")
    for field in ("bonus_ratio_per_10", "transfer_ratio_per_10", "cash_dividend_per_10"):
        out[field] = pd.to_numeric(out[field], errors="coerce").fillna(0.0)
    out.insert(0, "source_url", "https://webapi.cninfo.com.cn/api/sysapi/p_sysapi1139?scode=" + code)
    out.insert(0, "source", "CNInfo p_sysapi1139")
    out.insert(0, "stock_code", code)
    out["official_evidence_available"] = out["ex_date"].ne("")
    out["raw_columns"] = json.dumps([str(c) for c in raw.columns], ensure_ascii=False)
    out["notes"] = "Official CNInfo dividend-history API; positional fields retained with raw labels."
    return out.reindex(columns=ACTION_COLUMNS)


def save_frame(frame: pd.DataFrame, path: Path) -> dict[str, object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")
    return {"path": path, "bytes": path.stat().st_size, "sha256": sha256(path), "row_count": len(frame)}


def date_range(frame: pd.DataFrame) -> tuple[str, str]:
    date_col = next((c for c in ("trade_date", "date", "日期") if c in frame.columns), None)
    if date_col is None or frame.empty:
        return "", ""
    dates = pd.to_datetime(frame[date_col], errors="coerce").dropna()
    return ((dates.min().strftime("%Y-%m-%d"), dates.max().strftime("%Y-%m-%d"))
            if not dates.empty else ("", ""))


def run(root: Path, refresh_run_id: str, codes: list[str], start: str, end: str,
        price_fetcher: Callable = default_price_fetcher,
        action_fetcher: Callable = default_action_fetcher) -> int:
    root = Path(root).resolve()
    codes = [code6(code) for code in codes]
    if not codes or not set(codes).issubset(ALLOWED_CODES) or len(codes) != len(set(codes)):
        raise ValueError("codes must be unique members of 002044,002230")
    if pd.Timestamp(start) >= pd.Timestamp(end):
        raise ValueError("invalid forensic window")
    failed_run = root / "reports/prospective/lowvol_v1_5_1/refresh_runs" / refresh_run_id
    if not failed_run.exists():
        raise FileNotFoundError(failed_run)
    output = root / "reports/prospective/lowvol_v1_5_1/qfq_forensics_20260713"
    raw_dir = output / "raw"
    before = protected_snapshot(root, failed_run, output)
    frozen_all = pd.read_csv(root / "data/processed/adjusted_price_panel_v1_5.csv", dtype={"stock_code": str})
    manifest_rows: list[dict[str, object]] = []
    overlap_frames: list[pd.DataFrame] = []
    action_frames: list[pd.DataFrame] = []
    conclusions: list[dict[str, object]] = []

    def record(code: str, evidence_type: str, source: str, url: str, frame: pd.DataFrame,
               path: Path, value_col: str = "", status: str = "ok", error: str = "",
               displayed_decimals: int = 2) -> None:
        saved = save_frame(frame, path)
        profile = precision_profile(frame, value_col, displayed_decimals) if value_col and not frame.empty else {
            "displayed_decimal_places": "", "normalization_decimal_places": "",
            "observed_price_tick": "", "rounding_model": "", "comparison_tolerance": "",
        }
        minimum, maximum = date_range(frame)
        manifest_rows.append({
            "stock_code": code, "evidence_type": evidence_type, "source": source,
            "source_url": url, "path": str(path.relative_to(root)), "bytes": saved["bytes"],
            "sha256": saved["sha256"], "row_count": len(frame), "min_date": minimum,
            "max_date": maximum, **profile, "status": status, "error": error,
        })

    for code in codes:
        frozen = frozen_all[
            frozen_all["stock_code"].map(code6).eq(code)
            & pd.to_datetime(frozen_all["trade_date"]).between(start, end)
        ][["trade_date", "qfq_close"]].rename(columns={"qfq_close": "frozen_qfq"})
        frozen["trade_date"] = pd.to_datetime(frozen["trade_date"]).dt.strftime("%Y-%m-%d")
        record(code, "frozen_qfq", "frozen v1.5 panel", "", frozen,
               raw_dir / code / "frozen_qfq.csv", "frozen_qfq")

        failed_path = failed_run / "slices/stocks" / f"{code}.csv"
        failed_raw = pd.read_csv(failed_path) if failed_path.exists() else pd.DataFrame()
        failed = normalize_price(failed_raw, "refreshed_qfq") if not failed_raw.empty else pd.DataFrame(columns=["trade_date", "refreshed_qfq"])
        record(code, "failed_refresh_qfq", "failed refresh Sina QFQ", "", failed,
               raw_dir / code / "failed_refresh_qfq.csv", "refreshed_qfq")

        evidence: dict[tuple[str, str], pd.DataFrame] = {}
        source_errors: list[str] = []
        for source in ("sina", "eastmoney", "tencent"):
            for adjust, name in (("", "raw"), ("qfq", "qfq"), ("hfq", "hfq")):
                endpoint = (
                    "https://stock.finance.sina.com.cn" if source == "sina"
                    else "https://push2his.eastmoney.com/api/qt/stock/kline/get" if source == "eastmoney"
                    else "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
                )
                try:
                    response = price_fetcher(code, start, end, source, adjust)
                    value_col = f"{source}_{name}_close"
                    normalized = normalize_price(response, value_col)
                    evidence[(source, name)] = normalized
                    record(code, f"{source}_{name}", source, endpoint, response,
                           raw_dir / code / f"{source}_{name}_response.csv")
                    record(code, f"{source}_{name}_normalized", source, endpoint, normalized,
                           raw_dir / code / f"{source}_{name}_normalized.csv", value_col)
                except Exception as exc:
                    source_errors.append(f"{source}_{name}: {type(exc).__name__}: {exc}")
                    record(code, f"{source}_{name}", source, endpoint, pd.DataFrame(),
                           raw_dir / code / f"{source}_{name}_response.csv", status="error", error=str(exc))

        for factor_name in ("qfq-factor", "hfq-factor"):
            endpoint = "https://finance.sina.com.cn/realstock/company/"
            try:
                response = price_fetcher(code, start, end, "sina", factor_name)
                value_col = factor_name.replace("-", "_")
                normalized = normalize_factor(response, value_col)
                evidence[("sina", factor_name)] = normalized
                record(code, f"sina_{factor_name}", "sina", endpoint, response,
                       raw_dir / code / f"sina_{factor_name}_response.csv")
                record(code, f"sina_{factor_name}_normalized", "sina", endpoint, normalized,
                       raw_dir / code / f"sina_{factor_name}_normalized.csv", value_col,
                       displayed_decimals=13)
            except Exception as exc:
                source_errors.append(f"sina_{factor_name}: {type(exc).__name__}: {exc}")
                record(code, f"sina_{factor_name}", "sina", endpoint, pd.DataFrame(),
                       raw_dir / code / f"sina_{factor_name}_response.csv", status="error", error=str(exc))

        current_qfq = evidence.get(("sina", "qfq"), failed)
        if len(current_qfq) < MIN_COMMON_DATES:
            fallback_source = next(
                (source for source in ("eastmoney", "tencent") if (source, "qfq") in evidence), None
            )
            if fallback_source:
                current_qfq = evidence[(fallback_source, "qfq")].rename(
                    columns={f"{fallback_source}_qfq_close": "refreshed_qfq"}
                )
        elif "sina_qfq_close" in current_qfq:
            current_qfq = current_qfq.rename(columns={"sina_qfq_close": "refreshed_qfq"})
        tolerance = source_tolerance(2, 10)
        overlap, fit = fit_overlap(frozen, current_qfq, tolerance)
        overlap.insert(0, "stock_code", code)
        overlap_frames.append(overlap.reindex(columns=OVERLAP_COLUMNS))

        try:
            raw_actions = action_fetcher(code)
            record(code, "official_corporate_actions_raw", "CNInfo p_sysapi1139",
                   "https://webapi.cninfo.com.cn/api/sysapi/p_sysapi1139?scode=" + code,
                   raw_actions, raw_dir / code / "cninfo_corporate_actions_response.csv")
            actions = normalize_actions(code, raw_actions)
        except Exception as exc:
            source_errors.append(f"cninfo_actions: {type(exc).__name__}: {exc}")
            actions = pd.DataFrame(columns=ACTION_COLUMNS)
            record(code, "official_corporate_actions_raw", "CNInfo p_sysapi1139",
                   "https://webapi.cninfo.com.cn/api/sysapi/p_sysapi1139?scode=" + code,
                   pd.DataFrame(), raw_dir / code / "cninfo_corporate_actions_response.csv",
                   status="error", error=str(exc))
        window_actions = actions[
            pd.to_datetime(actions.get("ex_date", pd.Series(dtype=str)), errors="coerce").between(start, end)
        ] if not actions.empty else actions
        action_frames.append(window_actions)

        action = window_actions.iloc[-1] if not window_actions.empty else None
        official = action is not None
        ex_date = str(action["ex_date"]) if official else ""
        refreshed_return = first_boundary_return(current_qfq, ex_date, "refreshed_qfq") if official else None
        independent = evidence.get(("eastmoney", "qfq"), evidence.get(("eastmoney", "hfq")))
        if independent is None:
            independent = evidence.get(("tencent", "qfq"), evidence.get(("tencent", "hfq")))
        independent_return = (
            first_boundary_return(independent, ex_date, "eastmoney_qfq_close")
            if official and independent is not None and "eastmoney_qfq_close" in independent
            else first_boundary_return(independent, ex_date, "eastmoney_hfq_close")
            if official and independent is not None and "eastmoney_hfq_close" in independent
            else first_boundary_return(independent, ex_date, "tencent_qfq_close")
            if official and independent is not None and "tencent_qfq_close" in independent
            else first_boundary_return(independent, ex_date, "tencent_hfq_close")
            if official and independent is not None and "tencent_hfq_close" in independent
            else None
        )
        raw_prices = evidence.get(("eastmoney", "raw"), evidence.get(("tencent", "raw"), evidence.get(("sina", "raw"))))
        raw_price_observed = raw_prices is not None
        factor_implied_raw_used = False
        if (raw_prices is None and ("sina", "qfq-factor") in evidence
                and not current_qfq.empty):
            raw_prices = raw_implied_by_qfq_factor(
                current_qfq, evidence[("sina", "qfq-factor")],
                "refreshed_qfq", "qfq_factor",
            )
            factor_implied_raw_used = True
        total_return = None
        if official and raw_prices is not None:
            value_col = next(c for c in raw_prices.columns if c.endswith("_raw_close"))
            dates = pd.to_datetime(raw_prices["trade_date"])
            before_raw = raw_prices.loc[dates < pd.Timestamp(ex_date)]
            after_raw = raw_prices.loc[dates >= pd.Timestamp(ex_date)]
            if not before_raw.empty and not after_raw.empty:
                total_return = raw_total_return(
                    float(before_raw.iloc[-1][value_col]), float(after_raw.iloc[0][value_col]),
                    float(action["cash_dividend_per_10"]), float(action["bonus_ratio_per_10"]),
                    float(action["transfer_ratio_per_10"]),
                )
        return_tolerance = max(2 * tolerance / max(float(frozen["frozen_qfq"].median()), 1.0), 1e-4)
        post_reconciles = reconcile_return(refreshed_return, total_return, return_tolerance)
        independent_reconciles = reconcile_return(independent_return, total_return, return_tolerance)

        explicit_factor = False
        for frame in evidence.values():
            explicit_factor = explicit_factor or any("factor" in str(c).lower() or "因子" in str(c) for c in frame.columns)
        factor_result = {
            "explicit_factor_observation_count": 0, "explicit_factor_max_error": np.nan,
            "explicit_factor_reconciles": False,
        }
        if all(key in evidence for key in (("sina", "raw"), ("sina", "qfq"), ("sina", "qfq-factor"))):
            factor_result = reconcile_explicit_qfq_factor(
                evidence[("sina", "raw")], evidence[("sina", "qfq")],
                evidence[("sina", "qfq-factor")], "sina_raw_close", "sina_qfq_close",
                "qfq_factor", tolerance,
            )
        explicit_factor_reconciles = bool(
            factor_result["explicit_factor_reconciles"] and post_reconciles and independent_reconciles
        )
        status, allowed = classify_evidence(
            fit, explicit_factor_reconciles,
            post_reconciles if raw_price_observed else False,
            independent_reconciles, official,
        )
        assert status in STATUS_VALUES
        conclusions.append({
            "stock_code": code, **fit, "official_action_available": official,
            "ex_date": ex_date, "refreshed_first_post_event_return": refreshed_return,
            "raw_corporate_action_total_return": total_return,
            "raw_price_observed": raw_price_observed,
            "factor_implied_raw_used": factor_implied_raw_used,
            "independent_adjusted_return": independent_return,
            "return_tolerance": return_tolerance, "post_event_return_reconciles": post_reconciles,
            "independent_source_reconciles": independent_reconciles,
            "explicit_adjustment_factor_found": explicit_factor,
            "explicit_factor_reconciles": explicit_factor_reconciles,
            **factor_result,
            "status": status, "v1_5_1_continuity_fix_allowed": allowed,
            "source_errors": " | ".join(source_errors),
        })

    output.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(manifest_rows, columns=MANIFEST_COLUMNS).to_csv(output / "evidence_manifest.csv", index=False)
    nonempty_actions = [frame for frame in action_frames if not frame.empty]
    (pd.concat(nonempty_actions, ignore_index=True) if nonempty_actions else pd.DataFrame(columns=ACTION_COLUMNS)).reindex(
        columns=ACTION_COLUMNS
    ).to_csv(output / "corporate_actions.csv", index=False)
    pd.concat(overlap_frames, ignore_index=True).reindex(columns=OVERLAP_COLUMNS).to_csv(output / "overlap_comparison.csv", index=False)
    after = protected_snapshot(root, failed_run, output)
    protected_ok = before == after
    all_allowed = all(bool(row["v1_5_1_continuity_fix_allowed"]) for row in conclusions)
    generated = datetime.now(timezone.utc).isoformat()
    rows_text = "\n".join(
        f"- {r['stock_code']}: status={r['status']}; common_dates={r['common_date_count']}; "
        f"scale={r['multiplicative_scale']}; fit_pass={str(r['multiplicative_fit_pass']).lower()}; "
        f"scale_max_normalized_error={r['multiplicative_max_normalized_error']}; "
        f"additive_shift={r['additive_shift']}; additive_fit_pass={str(r['additive_fit_pass']).lower()}; "
        f"official_action={str(r['official_action_available']).lower()}; "
        f"ex_date={r['ex_date'] or 'unavailable'}; "
        f"refreshed_boundary_return={r['refreshed_first_post_event_return']}; "
        f"corporate_action_total_return={r['raw_corporate_action_total_return']}; "
        f"independent_adjusted_return={r['independent_adjusted_return']}; "
        f"raw_price_observed={str(r['raw_price_observed']).lower()}; "
        f"factor_implied_raw_used={str(r['factor_implied_raw_used']).lower()}; "
        f"explicit_factor_found={str(r['explicit_adjustment_factor_found']).lower()}; "
        f"post_event_reconciles={str(r['post_event_return_reconciles']).lower()}; "
        f"independent_reconciles={str(r['independent_source_reconciles']).lower()}; "
        f"continuity_fix_allowed={str(r['v1_5_1_continuity_fix_allowed']).lower()}"
        for r in conclusions
    )
    errors_text = "\n".join(f"- {r['stock_code']}: {r['source_errors'] or 'none'}" for r in conclusions)
    report = f"""# 002044 / 002230 QFQ Overlap Forensics v1.5.1

- generated_at: {generated}
- refresh_run_id: {refresh_run_id}
- forensic_window: {start}..{end}
- affected_codes: {','.join(codes)}
- protected_artifacts_unchanged: {str(protected_ok).lower()}
- publish_allowed: false
- observe_allowed: false
- all_stock_v1_5_1_continuity_fix_allowed: {str(all_allowed).lower()}

## Conclusions

{rows_text}

## Source Errors

{errors_text}

## Interpretation

All common valid dates in the fixed window are used. Five dates are only the minimum sufficiency threshold. A stable scale alone is not enough: Tier 1 also requires official corporate-action evidence and independent post-event economic-return reconciliation.

No bridge, refresh acceptance change, production panel, cache, approval, or prospective observation was created.
"""
    (output / "qfq_overlap_forensics_v1_5_1.md").write_text(report, encoding="utf-8")
    policy = f"""# Prospective QFQ Continuity Policy v1.5.1 (Draft)

## Decision Boundary

- Tier 1 preserves frozen QFQ return semantics and may be proposed for v1.5.1 only after per-stock approval.
- Tier 1A: explicit, auditable adjustment-factor bridge with source, definition, effective date, and historical version.
- Tier 1B: one stable multiplicative rescaling over all common dates plus official-action and independent-source return reconciliation.
- Tier 2 changes or abstracts the return source: raw price plus corporate-action total return, or a synthetic continuous-return bridge.
- Tier 2 is not a normal v1.5.1 repair and requires a new methodology version, protocol, and signoff.

## Current Gate

- all_stock_v1_5_1_continuity_fix_allowed: {str(all_allowed).lower()}
- publish_allowed: false
- observe_allowed: false
- bridge_implementation_allowed: false
- new_methodology_version_required: {str(not all_allowed and any(r['status'] == 'tier2_only_supported' for r in conclusions)).lower()}

Each stock is assessed independently. One passing stock cannot authorize the all-or-nothing refresh run. Frozen history must remain byte-for-byte unchanged; no fill, backfill, next-date substitution, or silent vendor revision is allowed.
"""
    (output / "prospective_qfq_continuity_policy_v1_5_1.md").write_text(policy, encoding="utf-8")
    return 0 if protected_ok else 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", default=str(Path(__file__).resolve().parents[1]))
    parser.add_argument("--refresh-run-id", required=True)
    parser.add_argument("--codes", required=True)
    parser.add_argument("--start-date", required=True)
    parser.add_argument("--end-date", required=True)
    args = parser.parse_args(argv)
    try:
        return run(Path(args.project_root), args.refresh_run_id, args.codes.split(","), args.start_date, args.end_date)
    except Exception as exc:
        print(f"critical_error={type(exc).__name__}: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
