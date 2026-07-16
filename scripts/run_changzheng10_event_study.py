# ruff: noqa: E501  # Report prose and Markdown table rows are clearer unsplit.

from __future__ import annotations

import argparse
import hashlib
import math
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

EVENT_DATE = pd.Timestamp("2026-07-10")
FIRST_TRADING_DAY_AFTER_EVENT = pd.Timestamp("2026-07-13")
FETCH_START = "20260301"
FETCH_END = "20260717"
ATOL = 1e-12
EXPECTED_UNIVERSE_SHA256 = "A8C2803802F1927176FDF7940AA187B551FDC6D03037876C1C5D9D297780E626"
WINDOWS = {
    "pre_event": (-5, -1),
    "event_day": (0, 0),
    "event_to_1": (0, 1),
    "event_to_3": (0, 3),
    "event_to_5": (0, 5),
}
PRIMARY_RELATIVE_DAYS = (1, 3, 5)
BENCHMARKS = {"000300": "HS300", "000852": "CSI1000"}
PROTECTED = (
    "data/processed/research_universe_lowvol_freeze_20260711.csv",
    "data/processed/adjusted_price_panel_v1_5.csv",
    "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv",
    "reports/lowvol_locked_grid_prototype_periods_v1_5_1.csv",
    "reports/theme_breadth_hypothesis_v1_7.md",
)


class ReadinessBlocked(RuntimeError):
    pass


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest().upper()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def code6(value: object) -> str:
    return str(value).strip().split(".")[0].zfill(6)


def source_sha256(frame: pd.DataFrame) -> str:
    canonical = frame.sort_values(["instrument_code", "trade_date"]).to_csv(
        index=False, lineterminator="\n"
    )
    return sha256_bytes(canonical.encode("utf-8"))


def _date_close(raw: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    date_column = next((column for column in ("trade_date", "date", "日期") if column in raw), None)
    close_column = next(
        (column for column in ("adjusted_close", "qfq_close", "close", "收盘") if column in raw),
        None,
    )
    if date_column is None or close_column is None or raw.empty:
        raise ValueError("Price response lacks date/close columns or rows")
    dates = pd.to_datetime(raw[date_column], errors="raise")
    closes = pd.to_numeric(raw[close_column], errors="coerce")
    if not np.isfinite(closes).all() or closes.le(0).any():
        raise ValueError("Price response contains missing, nonfinite, or nonpositive closes")
    return dates, closes


def normalize_prices(
    code: str,
    raw: pd.DataFrame,
    instrument_type: str,
    instrument_name: str,
    endpoint: str,
    fetched_at: str,
) -> pd.DataFrame:
    dates, closes = _date_close(raw)
    result = pd.DataFrame(
        {
            "instrument_type": instrument_type,
            "instrument_code": code6(code),
            "instrument_name": instrument_name,
            "trade_date": dates,
            "adjusted_close": closes,
            "adjustment": "qfq" if instrument_type == "stock" else "none",
            "source_endpoint": endpoint,
            "fetched_at_utc": fetched_at,
        }
    )
    result = result.loc[
        result["trade_date"].between(
            pd.Timestamp(FETCH_START), pd.Timestamp(FETCH_END), inclusive="both"
        )
    ].sort_values("trade_date")
    if result.empty:
        raise ValueError(f"No {code} prices in the requested date range")
    if result.duplicated(["instrument_code", "trade_date"]).any():
        raise ValueError(f"Duplicate price date for {code}")
    return result.reset_index(drop=True)


def retry_fetch(fetch: Callable[[], pd.DataFrame], attempts: int = 3) -> pd.DataFrame:
    errors = []
    for attempt in range(attempts):
        try:
            return fetch()
        except Exception as exc:  # source errors vary by AkShare version
            errors.append(str(exc))
            if attempt + 1 < attempts:
                time.sleep(2**attempt)
    raise RuntimeError(" | ".join(errors))


def default_stock_fetch(code: str) -> pd.DataFrame:
    import akshare as ak

    return ak.stock_zh_a_hist(
        symbol=code6(code),
        period="daily",
        start_date=FETCH_START,
        end_date=FETCH_END,
        adjust="qfq",
        timeout=20,
    )


def default_index_fetch(code: str) -> pd.DataFrame:
    import akshare as ak

    symbol = "sh" + code6(code)
    return ak.stock_zh_index_daily_tx(symbol=symbol)


def manifest_row(
    code: str,
    instrument_type: str,
    instrument_name: str,
    endpoint: str,
    fetched_at: str,
    akshare_version: str,
    status: str,
    frame: pd.DataFrame | None = None,
    error: str = "",
) -> dict[str, object]:
    return {
        "instrument_type": instrument_type,
        "instrument_code": code6(code),
        "instrument_name": instrument_name,
        "source_endpoint": endpoint,
        "akshare_version": akshare_version,
        "data_fetch_time_utc": fetched_at,
        "requested_start_date": FETCH_START,
        "requested_end_date": FETCH_END,
        "price_date_min": frame["trade_date"].min().date().isoformat() if frame is not None else "",
        "price_date_max": frame["trade_date"].max().date().isoformat() if frame is not None else "",
        "row_count": len(frame) if frame is not None else 0,
        "status": status,
        "source_sha256": source_sha256(frame) if frame is not None else "",
        "error": error,
    }


def event_calendar(
    hs300: pd.DataFrame, csi1000: pd.DataFrame
) -> tuple[list[pd.Timestamp], dict[int, pd.Timestamp]]:
    hs_dates = sorted(pd.to_datetime(hs300["trade_date"]).unique())
    csi_dates = set(pd.to_datetime(csi1000["trade_date"]).unique())
    if EVENT_DATE not in hs_dates:
        raise ValueError("T0 is absent from the HS300 index calendar")
    event_position = hs_dates.index(EVENT_DATE)
    if event_position < 6 or event_position + 5 >= len(hs_dates):
        latest = hs_dates[-1].date().isoformat() if hs_dates else "none"
        raise ReadinessBlocked(f"T+5 is not observable; HS300 latest date={latest}")
    relative_dates = {relative: hs_dates[event_position + relative] for relative in range(-6, 6)}
    missing_csi = sorted(date for date in relative_dates.values() if date not in csi_dates)
    if missing_csi:
        raise ReadinessBlocked(f"CSI1000 misses required dates: {missing_csi}")
    if relative_dates[1] != FIRST_TRADING_DAY_AFTER_EVENT:
        raise ValueError("First full trading day after event differs from 2026-07-13")
    return hs_dates, relative_dates


def theme_codes(universe: pd.DataFrame) -> tuple[list[str], list[str]]:
    normalized = universe.copy()
    normalized["code"] = normalized["code"].map(code6)
    if len(normalized) != 56 or normalized["code"].nunique() != 56:
        raise ValueError("Frozen universe is not 56 unique stocks")
    space = sorted(normalized.loc[normalized["theme"].astype(str).str.contains("商业航天"), "code"])
    ai = sorted(normalized.loc[normalized["theme"].astype(str).str.contains("AI"), "code"])
    if len(space) != 12 or len(ai) != 45 or len(set(space)) != 12 or len(set(ai)) != 45:
        raise ValueError(f"Frozen theme counts differ: space={len(space)}, AI={len(ai)}")
    if set(space) & set(ai) != {"002049"}:
        raise ValueError("Expected multi-theme overlap is not exactly 002049")
    return space, ai


def complete_price_matrix(
    snapshot: pd.DataFrame, codes: list[str], dates: list[pd.Timestamp]
) -> pd.DataFrame:
    stock = snapshot.loc[
        snapshot["instrument_type"].eq("stock") & snapshot["instrument_code"].isin(codes)
    ]
    matrix = stock.pivot(
        index="trade_date", columns="instrument_code", values="adjusted_close"
    ).reindex(index=dates, columns=codes)
    if matrix.shape != (len(dates), len(codes)) or not np.isfinite(matrix.to_numpy()).all():
        missing = matrix.isna().stack()[lambda values: values].index.tolist()
        raise ReadinessBlocked(f"Stock prices missing; no fill permitted: {missing[:20]}")
    if (matrix.to_numpy() <= 0).any():
        raise ValueError("Nonpositive stock price in required matrix")
    return matrix


def daily_returns(matrix: pd.DataFrame) -> pd.DataFrame:
    returns = matrix.pct_change(fill_method=None).iloc[1:]
    if not np.isfinite(returns.to_numpy()).all():
        raise ValueError("Daily return calculation produced invalid values")
    return returns


def compounded(values: pd.Series) -> float:
    numeric = pd.to_numeric(values, errors="coerce")
    if numeric.empty or not np.isfinite(numeric).all():
        return math.nan
    return float(np.prod(1 + numeric) - 1)


def approximate_equal_weight_contribution(stock_window_return: float, member_count: int) -> float:
    if member_count <= 0:
        raise ValueError("member_count must be positive")
    return float(stock_window_return / member_count)


def window_slice(values: pd.Series, relative_days: pd.Series, window: str) -> pd.Series:
    start, end = WINDOWS[window]
    return values.loc[relative_days.between(start, end).to_numpy()]


def classify_interpretation(
    cars: dict[tuple[str, int], float], positive_stock_count: int
) -> tuple[str, str]:
    positive_windows = sum(
        all(cars[(benchmark, relative)] > 0 for benchmark in BENCHMARKS)
        for relative in PRIMARY_RELATIVE_DAYS
    )
    t5_positive = all(cars[(benchmark, 5)] > 0 for benchmark in BENCHMARKS)
    reversal = all(
        cars[(benchmark, 3)] > 0 and cars[(benchmark, 5)] < 0 for benchmark in BENCHMARKS
    )
    if positive_windows >= 2 and t5_positive and positive_stock_count >= 7 and not reversal:
        return (
            "positive response observed",
            "positive CAR is persistent across both benchmarks and broad across stocks",
        )
    coherent = []
    for relative in PRIMARY_RELATIVE_DAYS:
        values = [cars[(benchmark, relative)] for benchmark in BENCHMARKS]
        coherent.append(all(value > 0 for value in values) or all(value < 0 for value in values))
    all_near_zero = all(abs(value) <= ATOL for value in cars.values())
    if all_near_zero or (not any(coherent) and 5 <= positive_stock_count <= 7):
        return (
            "no clear response observed",
            "benchmark-adjusted directions are unstable and the stock cross-section is dispersed",
        )
    negative_t5 = all(cars[(benchmark, 5)] < 0 for benchmark in BENCHMARKS)
    detail = (
        "consistent negative T+5 abnormal performance"
        if negative_t5
        else "window, benchmark, or cross-sectional evidence is mixed"
    )
    return "mixed response", detail


def breadth60(
    snapshot: pd.DataFrame,
    universe: pd.DataFrame,
    calendar: list[pd.Timestamp],
    as_of: pd.Timestamp,
) -> dict[str, object]:
    position = calendar.index(as_of)
    dates = calendar[position - 59 : position + 1]
    if len(dates) != 60:
        return {
            "as_of_date": as_of.date().isoformat(),
            "eligible_weight": 0.0,
            "above_weight": 0.0,
            "coverage": 0.0,
            "breadth60": math.nan,
            "valid": False,
        }
    themes = universe.set_index(universe["code"].map(code6))["theme"].astype(str)
    weights = {
        code: (0.5 if "|" in theme else 1.0)
        for code, theme in themes.items()
        if "商业航天" in theme
    }
    matrix = (
        snapshot.loc[snapshot["instrument_type"].eq("stock")]
        .pivot(index="trade_date", columns="instrument_code", values="adjusted_close")
        .reindex(index=dates, columns=sorted(weights))
    )
    eligible = np.isfinite(matrix.to_numpy()).all(axis=0) & (matrix.to_numpy() > 0).all(axis=0)
    eligible_codes = [code for code, flag in zip(matrix.columns, eligible, strict=True) if flag]
    above_codes = [code for code in eligible_codes if matrix.iloc[-1][code] > matrix[code].mean()]
    total = sum(weights.values())
    denominator = sum(weights[code] for code in eligible_codes)
    numerator = sum(weights[code] for code in above_codes)
    coverage = denominator / total
    return {
        "as_of_date": as_of.date().isoformat(),
        "eligible_weight": denominator,
        "above_weight": numerator,
        "coverage": coverage,
        "breadth60": numerator / denominator if denominator else math.nan,
        "valid": coverage >= 0.90,
    }


def build_analysis(
    snapshot: pd.DataFrame,
    universe: pd.DataFrame,
    calendar: list[pd.Timestamp],
    relative_dates: dict[int, pd.Timestamp],
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    space, ai = theme_codes(universe)
    dates = [relative_dates[relative] for relative in range(-6, 6)]
    stock_codes = sorted(set(space) | set(ai))
    stock_returns = daily_returns(complete_price_matrix(snapshot, stock_codes, dates))
    relative = pd.Series(range(-5, 6), index=stock_returns.index)
    index_snapshot = snapshot.loc[snapshot["instrument_type"].eq("index")]
    index_matrix = index_snapshot.pivot(
        index="trade_date", columns="instrument_code", values="adjusted_close"
    ).reindex(index=dates, columns=list(BENCHMARKS))
    if not np.isfinite(index_matrix.to_numpy()).all():
        raise ReadinessBlocked("Benchmark prices are incomplete in the event window")
    index_returns = daily_returns(index_matrix)
    raw_series = {
        "Space": stock_returns[space].mean(axis=1),
        "AI": stock_returns[ai].mean(axis=1),
        "HS300": index_returns["000300"],
        "CSI1000": index_returns["000852"],
    }
    rows = []
    for name, values in raw_series.items():
        for date, value in values.items():
            relative_day = int(relative.loc[date])
            phase = "pre_event" if relative_day < 0 else "event"
            phase_values = (
                values.loc[(relative < 0).to_numpy()]
                if phase == "pre_event"
                else values.loc[(relative >= 0).to_numpy()]
            )
            through = phase_values.loc[:date]
            rows.append(
                {
                    "trade_date": date.date().isoformat(),
                    "relative_day": relative_day,
                    "series": name,
                    "daily_return": float(value),
                    "cumulative_return": compounded(through),
                    "abnormal_return": math.nan,
                    "car": math.nan,
                    "cumulative_excess_return": math.nan,
                    "valid_member_count": len(space)
                    if name == "Space"
                    else len(ai)
                    if name == "AI"
                    else 1,
                    "primary_interpretation_day": relative_day in PRIMARY_RELATIVE_DAYS,
                }
            )
    cars: dict[tuple[str, int], float] = {}
    for code, benchmark_name in BENCHMARKS.items():
        abnormal = raw_series["Space"] - index_returns[code]
        for date, value in abnormal.items():
            relative_day = int(relative.loc[date])
            if relative_day >= 0:
                through = abnormal.loc[(relative >= 0).to_numpy()].loc[:date]
                space_through = raw_series["Space"].loc[(relative >= 0).to_numpy()].loc[:date]
                benchmark_through = index_returns[code].loc[(relative >= 0).to_numpy()].loc[:date]
                car = float(through.sum())
                excess = compounded(space_through) - compounded(benchmark_through)
                cars[(code, relative_day)] = car
            else:
                car = math.nan
                excess = math.nan
            rows.append(
                {
                    "trade_date": date.date().isoformat(),
                    "relative_day": relative_day,
                    "series": f"Space_vs_{benchmark_name}",
                    "daily_return": math.nan,
                    "cumulative_return": math.nan,
                    "abnormal_return": float(value),
                    "car": car,
                    "cumulative_excess_return": excess,
                    "valid_member_count": len(space),
                    "primary_interpretation_day": relative_day in PRIMARY_RELATIVE_DAYS,
                }
            )
    contribution_rows = []
    for window, (start, end) in WINDOWS.items():
        mask = relative.between(start, end).to_numpy()
        for code in space:
            stock_window = stock_returns.loc[mask, code]
            stock_return = compounded(stock_window)
            row = {
                "window": window,
                "stock_code": code,
                "stock_name": universe.set_index(universe["code"].map(code6)).loc[code, "name"],
                "stock_cumulative_return": stock_return,
                "approximate_equal_weight_contribution": approximate_equal_weight_contribution(
                    stock_return, len(space)
                ),
            }
            for benchmark in BENCHMARKS:
                row[f"car_vs_{benchmark}"] = float(
                    (stock_window - index_returns.loc[mask, benchmark]).sum()
                )
            contribution_rows.append(row)
    contributions = pd.DataFrame(contribution_rows)
    t5 = contributions.loc[contributions["window"].eq("event_to_5")].copy()
    t5["rank"] = t5["stock_cumulative_return"].rank(method="first", ascending=False).astype(int)
    contributions = contributions.merge(t5[["stock_code", "rank"]], on="stock_code", how="left")
    positive_stock_count = int((t5["car_vs_000852"] > 0).sum())
    category, category_detail = classify_interpretation(cars, positive_stock_count)
    breadth_before = breadth60(snapshot, universe, calendar, relative_dates[-1])
    breadth_after = breadth60(snapshot, universe, calendar, relative_dates[5])
    metrics = {
        "category": category,
        "category_detail": category_detail,
        "positive_stock_count_csi1000_t5": positive_stock_count,
        "cars": cars,
        "raw_series": raw_series,
        "relative": relative,
        "breadth_before": breadth_before,
        "breadth_after": breadth_after,
    }
    return pd.DataFrame(rows), contributions, metrics


def window_metrics(metrics: dict[str, object]) -> pd.DataFrame:
    raw_series = metrics["raw_series"]
    relative = metrics["relative"]
    rows = []
    for window in WINDOWS:
        row: dict[str, object] = {"window": window}
        for name, values in raw_series.items():
            row[name] = compounded(window_slice(values, relative, window))
        row["Space_minus_AI"] = row["Space"] - row["AI"]
        end = WINDOWS[window][1]
        if end >= 0:
            for code, name in BENCHMARKS.items():
                row[f"CAR_vs_{name}"] = metrics["cars"][(code, end)]
        rows.append(row)
    return pd.DataFrame(rows)


def event_definition_markdown(
    universe_hash: str, snapshot_hash: str, akshare_version: str, fetched_at: str
) -> str:
    return f"""# Long March 10B recovery event definition

- event: 长征十号乙一级火箭海上网系回收成功
- event_date: 2026-07-10
- launch_time: 12:15 Asia/Shanghai
- recovery_time: approximately 12:21 Asia/Shanghai
- earliest_located_official_web_timestamp: 2026-07-10 14:43 Asia/Shanghai
- T0: 2026-07-10
- first_trading_day_after_event: 2026-07-13
- frozen_universe_sha256: {universe_hash}
- point_in_time_universe: false
- data_fetch_time_utc: {fetched_at}
- source: AkShare stock_zh_a_hist(qfq); stock_zh_index_daily_tx
- akshare_version: {akshare_version}
- event_price_snapshot_sha256: {snapshot_hash}

Because the event occurred during lunch break, T0 return contains pre-event morning trading and post-event afternoon reaction. Therefore T+1/T+3/T+5 are primary interpretation windows.

The v1.5 universe was frozen after the event. It is used only as a fixed descriptive research set and is not claimed to be a point-in-time event-date universe.
"""


def summary_markdown(
    windows: pd.DataFrame,
    contributions: pd.DataFrame,
    metrics: dict[str, object],
    manifest: pd.DataFrame,
) -> str:
    lines = [
        "# 长征十号乙海上回收事件响应诊断",
        "",
        "## Descriptive interpretation category",
        "",
        f"### {metrics['category']}",
        "",
        str(metrics["category_detail"]),
        "",
        "该类别仅概括描述性证据，不代表统计显著性、投资价值、策略或 Alpha 有效性。",
        "",
        "## Timing limitation",
        "",
        "Because the event occurred during lunch break, T0 return contains pre-event morning trading and post-event afternoon reaction. Therefore T+1/T+3/T+5 are primary interpretation windows.",
        "",
        "## Theme and benchmark returns",
        "",
        "| Window | Space | AI (background only) | HS300 | CSI1000 | Space-AI | CAR HS300 | CAR CSI1000 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in windows.itertuples(index=False):
        lines.append(
            f"| {row.window} | {row.Space:.4%} | {row.AI:.4%} | {row.HS300:.4%} | {row.CSI1000:.4%} | {row.Space_minus_AI:.4%} | "
            f"{getattr(row, 'CAR_vs_HS300', math.nan):.4%} | {getattr(row, 'CAR_vs_CSI1000', math.nan):.4%} |"
        )
    lines += [
        "",
        "AI 和 Space-AI 只作背景比较，不进入 interpretation category。T0 只作 timing sensitivity。",
        "",
        "## Individual stock response",
        "",
        f"CSI1000-adjusted positive stocks at T+5: {metrics['positive_stock_count_csi1000_t5']}/12.",
        "",
        "| Rank | Code | Name | T+5 return | Approximate EW contribution |",
        "|---:|---|---|---:|---:|",
    ]
    t5 = contributions.loc[contributions["window"].eq("event_to_5")].sort_values("rank")
    for row in t5.itertuples(index=False):
        lines.append(
            f"| {row.rank} | {row.stock_code} | {row.stock_name} | {row.stock_cumulative_return:.4%} | {row.approximate_equal_weight_contribution:.4%} |"
        )
    lines += [
        "",
        "Approximate contribution equals each stock's window return divided by 12. It sums to the arithmetic mean of stock window returns and need not exactly reconstruct the compounded daily equal-weight portfolio NAV.",
        "",
        "## Breadth60 supplement",
        "",
        f"- before: {metrics['breadth_before']}",
        f"- after: {metrics['breadth_after']}",
        "- Breadth is supplementary and does not enter the category.",
        "",
        "## Data lineage and limitations",
        "",
        f"- instruments fetched successfully: {(manifest['status'] == 'ok').sum()}/{len(manifest)}",
        "- no missing prices were filled",
        "- the universe is fixed but not claimed point-in-time",
        "- this single daily event study does not establish causality",
        "",
    ]
    return "\n".join(lines)


def write_manifest(directory: Path, manifest: pd.DataFrame) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    manifest.to_csv(directory / "event_data_manifest.csv", index=False, encoding="utf-8-sig")


def run(
    root: Path,
    stock_fetch: Callable[[str], pd.DataFrame] = default_stock_fetch,
    index_fetch: Callable[[str], pd.DataFrame] = default_index_fetch,
) -> int:
    root = Path(root)
    output = root / "reports/event_study/changzheng10_recovery"
    protected_before = {relative: sha256_file(root / relative) for relative in PROTECTED}
    universe_path = root / PROTECTED[0]
    universe_hash = sha256_file(universe_path)
    if universe_hash != EXPECTED_UNIVERSE_SHA256:
        raise ValueError(f"Frozen universe hash differs: {universe_hash}")
    universe = pd.read_csv(universe_path, dtype={"code": str})
    theme_codes(universe)
    try:
        import akshare as ak

        akshare_version = str(ak.__version__)
    except Exception:
        akshare_version = "unavailable"
    fetched_at = datetime.now(UTC).isoformat()
    frames: list[pd.DataFrame] = []
    manifest_rows: list[dict[str, object]] = []
    for code, name in BENCHMARKS.items():
        endpoint = "akshare.stock_zh_index_daily_tx"
        try:
            frame = normalize_prices(
                code,
                retry_fetch(lambda code=code: index_fetch(code)),
                "index",
                name,
                endpoint,
                fetched_at,
            )
            frames.append(frame)
            manifest_rows.append(
                manifest_row(
                    code, "index", name, endpoint, fetched_at, akshare_version, "ok", frame
                )
            )
        except Exception as exc:
            manifest_rows.append(
                manifest_row(
                    code,
                    "index",
                    name,
                    endpoint,
                    fetched_at,
                    akshare_version,
                    "error",
                    error=str(exc),
                )
            )
    manifest = pd.DataFrame(manifest_rows)
    if (manifest["status"] != "ok").any():
        write_manifest(output, manifest)
        return 2
    try:
        calendar, relative_dates = event_calendar(frames[0], frames[1])
    except ReadinessBlocked as exc:
        manifest.loc[:, "status"] = "blocked_waiting_for_t_plus_5"
        manifest.loc[:, "error"] = str(exc)
        write_manifest(output, manifest)
        return 2
    names = universe.set_index(universe["code"].map(code6))["name"].to_dict()
    themes = universe.set_index(universe["code"].map(code6))["theme"].astype(str).to_dict()
    for code in sorted(names):
        endpoint = "akshare.stock_zh_a_hist_qfq"
        try:
            frame = normalize_prices(
                code,
                retry_fetch(lambda code=code: stock_fetch(code)),
                "stock",
                names[code],
                endpoint,
                fetched_at,
            )
            frame["theme"] = themes[code]
            frames.append(frame)
            manifest_rows.append(
                manifest_row(
                    code, "stock", names[code], endpoint, fetched_at, akshare_version, "ok", frame
                )
            )
        except Exception as exc:
            manifest_rows.append(
                manifest_row(
                    code,
                    "stock",
                    names[code],
                    endpoint,
                    fetched_at,
                    akshare_version,
                    "error",
                    error=str(exc),
                )
            )
    manifest = pd.DataFrame(manifest_rows)
    if (manifest["status"] != "ok").any():
        write_manifest(output, manifest)
        return 2
    snapshot = pd.concat(frames, ignore_index=True, sort=False).sort_values(
        ["instrument_type", "instrument_code", "trade_date"]
    )
    event_returns, contributions, metrics = build_analysis(
        snapshot, universe, calendar, relative_dates
    )
    windows = window_metrics(metrics)
    protected_after = {relative: sha256_file(root / relative) for relative in PROTECTED}
    if protected_before != protected_after:
        raise ValueError("Protected artifacts changed during event study")
    output.mkdir(parents=True, exist_ok=True)
    snapshot_path = output / "event_price_snapshot.csv"
    snapshot.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
    write_manifest(output, manifest)
    (output / "event_definition.md").write_text(
        event_definition_markdown(
            universe_hash, sha256_file(snapshot_path), akshare_version, fetched_at
        ),
        encoding="utf-8",
    )
    event_returns.to_csv(output / "event_returns.csv", index=False, encoding="utf-8-sig")
    contributions.to_csv(output / "stock_contribution.csv", index=False, encoding="utf-8-sig")
    (output / "event_study_summary.md").write_text(
        summary_markdown(windows, contributions, metrics, manifest), encoding="utf-8"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Long March 10B recovery event diagnostic")
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    return run(args.project_root.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
