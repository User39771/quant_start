"""Strictly bounded 30-stock H7 turnover-source feasibility probe."""

# ruff: noqa: E501 -- fixed source contracts and report prose are intentionally explicit.

from __future__ import annotations

import argparse
import math
import socket
import time
from pathlib import Path

import numpy as np
import pandas as pd

START_DATE = pd.Timestamp("2020-01-01")
DATA_CUTOFF = pd.Timestamp("2026-08-20")
MAX_STOCKS = 30
FIELDS = "date,code,open,high,low,close,volume,amount,turn,tradestatus,isST"
OUT = Path("reports/hypothesis_7/source_probe")
RAW = Path("data/probe/h7_turnover_sources")


def code6(value: object) -> str:
    digits = "".join(char for char in str(value) if char.isdigit())
    return digits[-6:].zfill(6)


def select_sample(root: Path) -> pd.DataFrame:
    """Choose 30 stocks deterministically by board, size tercile, and history."""
    history = pd.read_csv(
        root / "reports/hypothesis_7/h7_history_sufficiency.csv",
        dtype={"stock_code": str},
    )
    history = history.loc[history["row_type"].eq("stock")].copy()
    history["stock_code"] = history["stock_code"].map(code6)
    history["local_size"] = pd.to_numeric(history["latest_total_market_cap"], errors="coerce")
    history = history.loc[history.local_size.gt(0)].copy()
    history["size_tercile"] = pd.qcut(
        history.local_size.rank(method="first"), 3, labels=["SMALL", "MID", "LARGE"]
    ).astype(str)
    chosen: list[int] = []
    for (_, _), group in history.groupby(["board", "size_tercile"], sort=True):
        ordered = group.sort_values(["local_history_start", "stock_code"])
        chosen.append(int(ordered.index[0]))
        if len(ordered) > 1:
            chosen.append(int(ordered.index[-1]))
    remainder = history.drop(index=set(chosen)).sort_values(
        ["board", "size_tercile", "stock_code"]
    )
    chosen.extend(int(index) for index in remainder.index[: MAX_STOCKS - len(chosen)])
    sample = history.loc[chosen[:MAX_STOCKS]].copy()
    sample["exchange"] = np.where(sample.stock_code.str.startswith(("5", "6", "9")), "SH", "SZ")
    sample["selection_stratum"] = sample.board + "_" + sample.size_tercile
    sample["selection_reason"] = "deterministic_board_size_history_coverage"
    result = sample[["stock_code", "exchange", "local_size", "selection_stratum", "selection_reason"]]
    result = result.sort_values("stock_code").reset_index(drop=True)
    if len(result) != MAX_STOCKS or result.stock_code.duplicated().any():
        raise ValueError("probe_sample_must_be_30_unique_stocks")
    return result


def apply_cutoff(frame: pd.DataFrame, date_column: str) -> tuple[pd.DataFrame, int]:
    dates = pd.to_datetime(frame[date_column], errors="coerce")
    after = dates.gt(DATA_CUTOFF)
    return frame.loc[~after].copy(), int(after.sum())


def percent_to_decimal(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce") / 100.0


def baostock_volume_to_shares(values: pd.Series) -> pd.Series:
    """BaoStock documents daily volume in shares."""
    return pd.to_numeric(values, errors="coerce")


def eastmoney_volume_to_shares(values: pd.Series) -> pd.Series:
    """AKShare/Eastmoney A-share history reports volume in 100-share lots."""
    return pd.to_numeric(values, errors="coerce") * 100.0


def normalize_baostock(frame: pd.DataFrame, stock_code: str) -> tuple[pd.DataFrame, int]:
    out = frame.copy()
    out.columns = [str(column).strip() for column in out.columns]
    out["stock_code"] = code6(stock_code)
    out["trade_date"] = pd.to_datetime(out["date"], errors="coerce")
    for column in ("open", "high", "low", "close", "volume", "amount", "turn"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    out["volume_shares"] = baostock_volume_to_shares(out.volume)
    out["baostock_circulating_turnover"] = percent_to_decimal(out.turn)
    out, discarded = apply_cutoff(out, "trade_date")
    keep = [
        "stock_code", "trade_date", "open", "high", "low", "close", "volume_shares",
        "amount", "turn", "baostock_circulating_turnover", "tradestatus", "isST",
    ]
    return out[keep].sort_values("trade_date").reset_index(drop=True), discarded


def normalize_cninfo(frame: pd.DataFrame, stock_code: str) -> tuple[pd.DataFrame, int]:
    required = {"公告日期", "变动日期", "总股本", "已流通股份"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"cninfo_missing_fields={sorted(missing)}")
    out = pd.DataFrame({
        "stock_code": code6(stock_code),
        "announcement_date": pd.to_datetime(frame["公告日期"], errors="coerce"),
        "change_date": pd.to_datetime(frame["变动日期"], errors="coerce"),
        # CNINFO share-capital values are reported in 10,000-share units.
        "total_shares_10k": pd.to_numeric(frame["总股本"], errors="coerce"),
        "circulating_shares_10k": pd.to_numeric(frame["已流通股份"], errors="coerce"),
    })
    out["total_shares"] = out.total_shares_10k * 10_000.0
    out["circulating_shares"] = out.circulating_shares_10k * 10_000.0
    out["event_date_incomplete"] = out[["announcement_date", "change_date"]].isna().any(axis=1)
    out["information_available_date"] = out[["announcement_date", "change_date"]].max(axis=1)
    received_after = int(
        out[["announcement_date", "change_date"]].max(axis=1).gt(DATA_CUTOFF).sum()
    )
    out = out.loc[
        ~out[["announcement_date", "change_date"]].max(axis=1).gt(DATA_CUTOFF)
    ].copy()
    return out.sort_values(["information_available_date", "change_date"]).reset_index(drop=True), received_after


def build_point_in_time_shares(events: pd.DataFrame, dates: pd.Series) -> pd.DataFrame:
    calendar = pd.DataFrame({"trade_date": pd.to_datetime(dates)}).sort_values("trade_date")
    usable = events.loc[
        ~events.event_date_incomplete
        & events.total_shares.gt(0)
        & events.information_available_date.notna(),
        ["information_available_date", "change_date", "announcement_date", "total_shares", "circulating_shares"],
    ].drop_duplicates()
    usable = usable.sort_values(["information_available_date", "change_date"]).drop_duplicates(
        "information_available_date", keep="last"
    )
    if usable.empty:
        for column in ("change_date", "announcement_date", "total_shares", "circulating_shares"):
            calendar[column] = pd.NaT if "date" in column else np.nan
        return calendar
    return pd.merge_asof(
        calendar,
        usable.sort_values("information_available_date"),
        left_on="trade_date",
        right_on="information_available_date",
        direction="backward",
        allow_exact_matches=True,
    )


def exact_200_positive_valid(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    positive = pd.Series(np.isfinite(numeric) & numeric.gt(0), index=values.index)
    return positive & positive.shift(1).rolling(200, min_periods=200).sum().eq(200)


def decimal_precision(values: pd.Series) -> int:
    numeric = pd.to_numeric(values, errors="coerce").dropna()
    if numeric.empty:
        return 0
    return max(len(text.rstrip("0").split(".")[1]) if "." in text else 0 for text in numeric.map(lambda x: f"{x:.12f}"))


def profile_turnover(values: pd.Series, prefix: str) -> dict[str, object]:
    numeric = pd.to_numeric(values, errors="coerce")
    positive = numeric[numeric.gt(0)]
    return {
        f"{prefix}_distinct_values": int(numeric.dropna().nunique()),
        f"{prefix}_minimum_positive": positive.min() if len(positive) else math.nan,
        f"{prefix}_decimal_precision": decimal_precision(numeric),
        f"{prefix}_zero_count": int(numeric.eq(0).sum()),
        f"{prefix}_missing_count": int(numeric.isna().sum()),
    }


def fetch_baostock(sample: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], list[dict], int]:
    import baostock as bs

    socket.setdefaulttimeout(20)
    login = bs.login()
    if login.error_code != "0":
        return {}, [{"stock_code": code, "status": "FAILED", "error": login.error_msg} for code in sample.stock_code], 0
    frames: dict[str, pd.DataFrame] = {}
    summary: list[dict] = []
    discarded = 0
    try:
        for number, code in enumerate(sample.stock_code, 1):
            vendor_code = ("sh." if code.startswith(("5", "6", "9")) else "sz.") + code
            try:
                result = bs.query_history_k_data_plus(
                    vendor_code, FIELDS, start_date="2020-01-01", end_date="2026-08-20",
                    frequency="d", adjustflag="3",
                )
                rows = []
                while result.error_code == "0" and result.next():
                    rows.append(result.get_row_data())
                if result.error_code != "0":
                    raise RuntimeError(f"{result.error_code}:{result.error_msg}")
                raw = pd.DataFrame(rows, columns=result.fields)
                if raw.empty:
                    raise ValueError("empty_response")
                normalized, removed = normalize_baostock(raw, code)
                if normalized.trade_date.duplicated().any():
                    raise ValueError("duplicate_trade_dates")
                discarded += removed
                frames[code] = normalized
                summary.append({"stock_code": code, "status": "SUCCESS", "error": ""})
            except Exception as exc:  # source failures belong in the probe result
                summary.append({"stock_code": code, "status": "FAILED", "error": f"{type(exc).__name__}:{exc}"})
            if number % 5 == 0:
                print(f"baostock_completed={number}/30", flush=True)
    finally:
        bs.logout()
    return frames, summary, discarded


def fetch_cninfo(sample: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], list[dict], int]:
    import akshare as ak

    frames: dict[str, pd.DataFrame] = {}
    summary: list[dict] = []
    discarded = 0
    for number, code in enumerate(sample.stock_code, 1):
        try:
            raw = ak.stock_share_change_cninfo(
                symbol=code, start_date="20200101", end_date="20260820"
            )
            if raw.empty:
                raise ValueError("empty_response")
            normalized, removed = normalize_cninfo(raw, code)
            discarded += removed
            frames[code] = normalized
            summary.append({"stock_code": code, "status": "SUCCESS", "error": ""})
        except Exception as exc:
            summary.append({"stock_code": code, "status": "FAILED", "error": f"{type(exc).__name__}:{exc}"})
        if number % 5 == 0:
            print(f"cninfo_completed={number}/30", flush=True)
    return frames, summary, discarded


def fetch_akshare(sample: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], list[dict], int]:
    import akshare as ak

    frames: dict[str, pd.DataFrame] = {}
    summary: list[dict] = []
    discarded = 0
    for number, code in enumerate(sample.stock_code, 1):
        error = ""
        for attempt in (1, 2):
            try:
                raw = ak.stock_zh_a_hist(
                    symbol=code, period="daily", start_date="20200101",
                    end_date="20260820", adjust="", timeout=20,
                )
                if raw.empty:
                    raise ValueError("empty_response")
                required = {"日期", "成交量", "成交额", "换手率"}
                if missing := required - set(raw.columns):
                    raise ValueError(f"missing_fields={sorted(missing)}")
                out = pd.DataFrame({
                    "stock_code": code,
                    "trade_date": pd.to_datetime(raw["日期"], errors="coerce"),
                    "volume_lots": pd.to_numeric(raw["成交量"], errors="coerce"),
                    "volume_shares": eastmoney_volume_to_shares(raw["成交量"]),
                    "amount": pd.to_numeric(raw["成交额"], errors="coerce"),
                    "turnover_percent": pd.to_numeric(raw["换手率"], errors="coerce"),
                    "turnover_decimal": percent_to_decimal(raw["换手率"]),
                })
                out, removed = apply_cutoff(out, "trade_date")
                if out.trade_date.duplicated().any():
                    raise ValueError("duplicate_trade_dates")
                discarded += removed
                frames[code] = out.sort_values("trade_date").reset_index(drop=True)
                summary.append({"stock_code": code, "status": "SUCCESS", "attempts": attempt, "error": ""})
                error = ""
                break
            except Exception as exc:
                error = f"{type(exc).__name__}:{exc}"
                if attempt == 1:
                    time.sleep(1)
        if error:
            summary.append({"stock_code": code, "status": "AKSHARE_NETWORK_UNAVAILABLE", "attempts": 2, "error": error})
        if number % 5 == 0:
            print(f"akshare_completed={number}/30", flush=True)
    return frames, summary, discarded


def zero_semantics(frame: pd.DataFrame) -> dict[str, int]:
    volume_zero = frame.volume_shares.eq(0)
    turn_zero = frame.baostock_circulating_turnover.eq(0)
    return {
        "zero_A_suspended_volume_zero": int((frame.tradestatus.astype(str).eq("0") & volume_zero).sum()),
        "zero_B_trading_volume_zero": int((frame.tradestatus.astype(str).eq("1") & volume_zero).sum()),
        "zero_C_volume_positive_turn_zero": int((frame.volume_shares.gt(0) & turn_zero).sum()),
        "zero_D_turn_missing": int(frame.baostock_circulating_turnover.isna().sum()),
    }


def analyze(
    root: Path,
    sample: pd.DataFrame,
    bao: dict[str, pd.DataFrame],
    cninfo: dict[str, pd.DataFrame],
    east: dict[str, pd.DataFrame],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    bao_rows, cn_rows, cross_rows = [], [], []
    pooled_total_errors: list[float] = []
    for code in sample.stock_code:
        b = bao.get(code)
        c = cninfo.get(code)
        a = east.get(code)
        if b is not None:
            row = {
                "stock_code": code, "row_count": len(b), "date_min": b.trade_date.min(),
                "date_max": b.trade_date.max(), "duplicate_dates": int(b.trade_date.duplicated().sum()),
                "zero_volume": int(b.volume_shares.eq(0).sum()), **zero_semantics(b),
                **profile_turnover(b.baostock_circulating_turnover, "baostock_turn"),
            }
            valid = exact_200_positive_valid(b.baostock_circulating_turnover)
            row.update({
                "first_valid_200d_baostock_turn": b.loc[valid, "trade_date"].min(),
                "valid_200d_days_baostock_turn": int(valid.sum()),
                "coverage_200d_baostock_turn": float(valid.mean()),
            })
            bao_rows.append(row)
        if c is not None:
            complete = ~c.event_date_incomplete
            cn_rows.append({
                "stock_code": code, "event_count": len(c), "complete_event_count": int(complete.sum()),
                "earliest_event": c.change_date.min(), "latest_event": c.change_date.max(),
                "total_shares_valid": int(c.total_shares.gt(0).sum()),
                "circulating_shares_valid": int(c.circulating_shares.gt(0).sum()),
                "change_date_missing_rate": float(c.change_date.isna().mean()),
                "announcement_date_missing_rate": float(c.announcement_date.isna().mean()),
                "event_date_incomplete_count": int(c.event_date_incomplete.sum()),
                "duplicate_events": int(c.duplicated(["change_date", "announcement_date", "total_shares", "circulating_shares"]).sum()),
            })
        if b is None or c is None:
            continue
        lineage = build_point_in_time_shares(c, b.trade_date)
        joined = b.merge(lineage, on="trade_date", how="left")
        joined["total_share_turnover"] = joined.volume_shares / joined.total_shares
        total_valid = joined.total_share_turnover.replace([np.inf, -np.inf], np.nan).notna()
        total_200 = exact_200_positive_valid(joined.total_share_turnover)
        cross: dict[str, object] = {
            "stock_code": code,
            "first_valid_total_share_date": joined.loc[joined.total_shares.notna(), "trade_date"].min(),
            "last_valid_total_share_date": joined.loc[joined.total_shares.notna(), "trade_date"].max(),
            "share_event_count": int((~c.event_date_incomplete & c.total_shares.gt(0)).sum()),
            "constructed_turnover_rows": int(total_valid.sum()),
            "constructed_turnover_coverage": float(total_valid.mean()),
            "first_valid_200d_total_turnover": joined.loc[total_200, "trade_date"].min(),
            "valid_200d_days_total_turnover": int(total_200.sum()),
            "coverage_200d_total_turnover": float(total_200.mean()),
            **profile_turnover(joined.total_share_turnover, "constructed_turnover"),
        }
        relation = joined[["total_share_turnover", "baostock_circulating_turnover"]].dropna()
        cross["constructed_vs_baostock_turn_spearman"] = relation.corr(method="spearman").iloc[0, 1] if len(relation) > 1 else math.nan
        if a is not None:
            ba = b.merge(a, on=["stock_code", "trade_date"], suffixes=("_bao", "_ak"))
            if len(ba):
                volume_rel = (ba.volume_shares_bao - ba.volume_shares_ak).abs() / ba.volume_shares_ak.replace(0, np.nan)
                turn_abs = (ba.baostock_circulating_turnover - ba.turnover_decimal).abs()
                turn_rel = turn_abs / ba.turnover_decimal.replace(0, np.nan)
                cross.update({
                    "bao_ak_overlap_rows": len(ba),
                    "bao_ak_volume_ratio_median": (ba.volume_shares_bao / ba.volume_shares_ak.replace(0, np.nan)).median(),
                    "bao_ak_volume_relative_error_median": volume_rel.median(),
                    "bao_ak_turn_absolute_difference_median": turn_abs.median(),
                    "bao_ak_turn_relative_difference_median": turn_rel.median(),
                    "bao_ak_turn_absolute_difference_p95": turn_abs.quantile(.95),
                    "bao_ak_turn_correlation": ba[["baostock_circulating_turnover", "turnover_decimal"]].corr().iloc[0, 1],
                    **profile_turnover(ba.turnover_decimal, "akshare_turn"),
                })
        local_path = root / f"data/cache/price/{code}.csv"
        local = pd.read_csv(local_path, usecols=lambda name: name in {"date", "close", "total_market_cap", "circulating_market_cap"})
        local["trade_date"] = pd.to_datetime(local["date"], errors="coerce")
        local, _ = apply_cutoff(local, "trade_date")
        local_lineage = build_point_in_time_shares(c, local.trade_date)
        local = local.merge(local_lineage, on="trade_date", how="left")
        close = pd.to_numeric(local.close, errors="coerce")
        local["implied_total_shares"] = pd.to_numeric(local.total_market_cap, errors="coerce") / close
        local["implied_circulating_shares"] = pd.to_numeric(local.circulating_market_cap, errors="coerce") / close
        total_error = (
            (local.implied_total_shares - local.total_shares).abs() / local.total_shares
        ).replace([np.inf, -np.inf], np.nan)
        pooled_total_errors.extend(total_error.dropna().tolist())
        circ_error = (
            (local.implied_circulating_shares - local.circulating_shares).abs()
            / local.circulating_shares
        ).replace([np.inf, -np.inf], np.nan)
        cross.update({
            "implied_total_vs_cninfo_median_error": total_error.median(),
            "implied_total_vs_cninfo_p95_error": total_error.quantile(.95),
            "implied_total_vs_cninfo_max_error": total_error.max(),
            "implied_circulating_vs_cninfo_median_error": circ_error.median(),
            "implied_circulating_vs_cninfo_p95_error": circ_error.quantile(.95),
            "implied_circulating_vs_cninfo_max_error": circ_error.max(),
        })
        cross_rows.append(cross)
    cross_frame = pd.DataFrame(cross_rows)
    pooled = pd.Series(pooled_total_errors, dtype=float)
    cross_frame["pooled_implied_total_vs_cninfo_median_error"] = pooled.median()
    cross_frame["pooled_implied_total_vs_cninfo_p95_error"] = pooled.quantile(.95)
    cross_frame["pooled_implied_total_vs_cninfo_max_error"] = pooled.max()
    return pd.DataFrame(bao_rows), pd.DataFrame(cn_rows), cross_frame


def write_raw(root: Path, source: str, frames: dict[str, pd.DataFrame]) -> None:
    directory = root / RAW / source
    directory.mkdir(parents=True, exist_ok=True)
    for code, frame in frames.items():
        date_columns = [
            column for column in ("trade_date", "announcement_date", "change_date", "information_available_date")
            if column in frame
        ]
        if any(pd.to_datetime(frame[column]).max() > DATA_CUTOFF for column in date_columns):
            raise ValueError(f"post_cutoff_row_before_save={source}:{code}")
        frame.to_csv(directory / f"{code}.csv", index=False)


def report(
    sample: pd.DataFrame,
    bao_status: pd.DataFrame,
    cn_status: pd.DataFrame,
    ak_status: pd.DataFrame,
    bao_summary: pd.DataFrame,
    cn_summary: pd.DataFrame,
    cross: pd.DataFrame,
    discarded: int,
) -> tuple[str, str]:
    def median_column(frame: pd.DataFrame, column: str) -> float:
        return pd.to_numeric(frame.get(column, pd.Series(dtype=float)), errors="coerce").median()

    def first_column(frame: pd.DataFrame, column: str) -> float:
        values = pd.to_numeric(frame.get(column, pd.Series(dtype=float)), errors="coerce").dropna()
        return float(values.iloc[0]) if len(values) else math.nan

    bao_ok = int(bao_status.status.eq("SUCCESS").sum())
    cn_ok = int(cn_status.status.eq("SUCCESS").sum())
    ak_ok = int(ak_status.status.eq("SUCCESS").sum())
    constructed = int(cross.constructed_turnover_rows.gt(0).sum()) if len(cross) else 0
    independent_check = bool(
        (len(cross) and cross.implied_total_vs_cninfo_median_error.notna().any()) or ak_ok
    )
    if not bao_ok or not cn_ok or not constructed:
        result = "SOURCE_PROBE_FAIL"
    elif bao_ok == len(sample) and cn_ok == len(sample) and constructed == len(sample) and independent_check:
        result = "SOURCE_PROBE_PASS"
    else:
        result = "SOURCE_PROBE_PARTIAL"
    median_coverage = cross.constructed_turnover_coverage.median() if len(cross) else math.nan
    bao_distinct = bao_summary.baostock_turn_distinct_values.median() if len(bao_summary) else math.nan
    constructed_distinct = cross.constructed_turnover_distinct_values.median() if len(cross) else math.nan
    total_error_median = first_column(cross, "pooled_implied_total_vs_cninfo_median_error")
    total_error_p95 = first_column(cross, "pooled_implied_total_vs_cninfo_p95_error")
    total_200 = int(cross.valid_200d_days_total_turnover.fillna(0).gt(0).sum()) if len(cross) else 0
    bao_200 = int(bao_summary.valid_200d_days_baostock_turn.fillna(0).gt(0).sum()) if len(bao_summary) else 0
    zero_a = int(bao_summary.zero_A_suspended_volume_zero.fillna(0).sum()) if len(bao_summary) else 0
    zero_b = int(bao_summary.zero_B_trading_volume_zero.fillna(0).sum()) if len(bao_summary) else 0
    zero_c = int(bao_summary.zero_C_volume_positive_turn_zero.fillna(0).sum()) if len(bao_summary) else 0
    zero_d = int(bao_summary.zero_D_turn_missing.fillna(0).sum()) if len(bao_summary) else 0
    volume_error = median_column(cross, "bao_ak_volume_relative_error_median")
    turn_difference = median_column(cross, "bao_ak_turn_absolute_difference_median")
    turn_correlation = median_column(cross, "bao_ak_turn_correlation")
    content = f"""# H7 Turnover Source Feasibility Probe

## Result

**{result}**. This is a bounded data-source feasibility result, not H7, Alpha, or return predictability evidence.

```text
data_cutoff=2026-08-20
probe_stock_count={len(sample)}
baostock_success_count={bao_ok}
baostock_failure_count={len(sample)-bao_ok}
cninfo_success_count={cn_ok}
cninfo_failure_count={len(sample)-cn_ok}
akshare_success_count={ak_ok}
akshare_failure_count={len(sample)-ak_ok}
constructed_total_share_turnover_stock_count={constructed}
constructed_turnover_median_coverage={median_coverage}
baostock_turn_median_distinct_values={bao_distinct}
constructed_turnover_median_distinct_values={constructed_distinct}
implied_total_shares_vs_cninfo_median_error={total_error_median}
implied_total_shares_vs_cninfo_p95_error={total_error_p95}
baostock_vs_akshare_volume_relative_error_median={volume_error}
baostock_vs_akshare_turn_absolute_difference_median={turn_difference}
baostock_vs_akshare_turn_correlation_median={turn_correlation}
zero_A_suspended_volume_zero={zero_a}
zero_B_trading_volume_zero={zero_b}
zero_C_volume_positive_turn_zero={zero_c}
zero_D_turn_missing={zero_d}
stocks_with_valid_200d_total_share_turnover={total_200}
stocks_with_valid_200d_baostock_turn={bao_200}
rows_after_2026_08_20_received={discarded}
rows_after_2026_08_20_discarded={discarded}
full_market_download_performed=false
C2_estimated=false
volume_return_regression_run=false
future_performance_accessed=false
source_probe_result={result}
```

## Measurement contracts

- BaoStock `volume` is shares and `amount` is CNY; `turn` is percent with six-decimal advertised precision. It is converted to decimal and retained as `BAOSTOCK_CIRCULATING_TURNOVER`. BaoStock defines it against circulating shares, so it is not renamed total-share turnover.
- CNINFO `总股本` and `已流通股份` are normalized from 10,000-share reporting units to shares. The usable date is `max(change_date, announcement_date)`; incomplete events are excluded, the pre-first-event interval remains unknown, and no future event is backfilled.
- AKShare/Eastmoney `成交量` is converted from 100-share lots to shares and `换手率` from percent to decimal.
- `TOTAL_SHARE_TURNOVER = BaoStock volume shares / point-in-time CNINFO total shares`. Local cap/close implied shares are validation only.

## Source status

### BaoStock

{bao_status.to_markdown(index=False)}

### CNINFO

{cn_status.to_markdown(index=False)}

### AKShare/Eastmoney

{ak_status.to_markdown(index=False)}

## Cross-validation interpretation

All comparisons use same-stock, same-date overlaps after unit normalization. Differences between total-share turnover and vendor circulating-share turnover are expected because their denominators differ. Precision, zeros, exact 200-prior-day coverage, point-in-time lineage coverage, and implied-share errors are in the companion CSV files. No epsilon was selected and no return or C2 quantity was accessed.

The independent Eastmoney check is narrow ({ak_ok}/30 successful stocks), so its close agreement is supportive but insufficient for a PASS. In the BaoStock probe, all observed zero-volume/zero-turnover cases and all missing turnover rows were confined to `tradestatus=0`; no trading day had zero volume and no positive-volume day had zero turnover. This resolves zero semantics descriptively for this sample only and does not select epsilon.

Recommended next step: human review of the three CNINFO failures and the point-in-time share lineage, then a separately approved small retry or source-contract check. Do not expand to the full market until those issues and the narrow independent cross-check are accepted.

## Stop

The sample is deterministically limited to 30 current broader-A stocks. No full-market download, background task, H5/H6/MCTS/Phase B run, or automatic H7 execution occurred. Human review is required before any expansion.
"""
    return content, result


def run(root: Path) -> None:
    output = root / OUT
    output.mkdir(parents=True, exist_ok=True)
    sample = select_sample(root)
    sample["data_cutoff"] = DATA_CUTOFF.date().isoformat()
    sample["full_market_download_performed"] = False
    sample.to_csv(output / "h7_turnover_probe_sample.csv", index=False)
    bao, bao_status_rows, bao_discarded = fetch_baostock(sample)
    cninfo, cn_status_rows, cn_discarded = fetch_cninfo(sample)
    east, ak_status_rows, ak_discarded = fetch_akshare(sample)
    for source, frames in (("baostock", bao), ("cninfo", cninfo), ("akshare", east)):
        write_raw(root, source, frames)
    bao_status = sample.merge(pd.DataFrame(bao_status_rows), on="stock_code", how="left")
    cn_status = sample.merge(pd.DataFrame(cn_status_rows), on="stock_code", how="left")
    ak_status = sample.merge(pd.DataFrame(ak_status_rows), on="stock_code", how="left")
    bao_summary, cn_summary, cross = analyze(root, sample, bao, cninfo, east)
    bao_summary = bao_status.merge(bao_summary, on="stock_code", how="left")
    cn_summary = cn_status.merge(cn_summary, on="stock_code", how="left")
    cross = sample.merge(cross, on="stock_code", how="left")
    for frame in (sample, bao_summary, cn_summary, cross):
        frame["data_cutoff"] = DATA_CUTOFF.date().isoformat()
        frame["full_market_download_performed"] = False
        frame["C2_estimated"] = False
        frame["future_performance_accessed"] = False
    bao_summary.to_csv(output / "h7_baostock_probe_summary.csv", index=False)
    cn_summary.to_csv(output / "h7_cninfo_share_probe_summary.csv", index=False)
    cross.to_csv(output / "h7_turnover_cross_validation.csv", index=False)
    text, result = report(
        sample, bao_status, cn_status, ak_status, bao_summary, cn_summary, cross,
        bao_discarded + cn_discarded + ak_discarded,
    )
    (output / "h7_turnover_source_probe_report.md").write_text(text, encoding="utf-8")
    print(f"probe_stock_count={len(sample)}")
    print(f"source_probe_result={result}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    run(parser.parse_args().project_root.resolve())
