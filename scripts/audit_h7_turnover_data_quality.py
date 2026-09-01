"""Offline, read-only H7 turnover cache quality and readiness audit."""

# ruff: noqa: E501 -- fixed data contracts and report prose are intentionally explicit.

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd

START_DATE = pd.Timestamp("2020-01-01")
DATA_CUTOFF = pd.Timestamp("2026-08-20")
OUT = Path("reports/hypothesis_7/data_quality")
BAO_CACHE = Path("data/cache/h7_turnover/baostock")
CN_CACHE = Path("data/cache/h7_turnover/cninfo")
QFQ_CACHE = Path("data/cache/h5a_broader_a_qfq_v1")
RAW_CACHE = Path("data/cache/price")
BAO_REQUIRED = {
    "stock_code", "trade_date", "volume_shares", "amount_cny",
    "baostock_circulating_turnover", "trading_status", "is_st", "close",
}
CN_REQUIRED = {
    "stock_code", "change_date", "announcement_date", "information_available_date",
    "total_shares", "circulating_shares", "event_date_incomplete",
}


def code6(value: object) -> str:
    digits = "".join(char for char in str(value) if char.isdigit())
    return digits[-6:].zfill(6)


def board(code: str) -> str:
    if code.startswith("688"):
        return "STAR"
    if code.startswith("300"):
        return "CHINEXT"
    if code.startswith(("600", "601", "603", "605")):
        return "SH_MAIN"
    return "SZ_MAIN"


def point_in_time_shares(events: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    calendar = pd.DataFrame({"trade_date": dates}).sort_values("trade_date")
    if events.empty:
        calendar["information_available_date"] = pd.NaT
        calendar["total_shares"] = np.nan
        calendar["circulating_shares"] = np.nan
        return calendar
    usable = events.loc[
        ~events.event_date_incomplete
        & events.total_shares.gt(0)
        & events.information_available_date.notna(),
        ["information_available_date", "total_shares", "circulating_shares"],
    ].sort_values("information_available_date")
    usable = usable.drop_duplicates("information_available_date", keep="last")
    if usable.empty:
        return point_in_time_shares(pd.DataFrame(), dates)
    return pd.merge_asof(
        calendar, usable, left_on="trade_date", right_on="information_available_date",
        direction="backward", allow_exact_matches=True,
    )


def exact_prior_200_ready(valid: pd.Series) -> pd.Series:
    """Current measurement plus exactly the preceding 200 market rows must be valid."""
    current = valid.eq(True)
    prior = current.shift(1).rolling(200, min_periods=200).sum().eq(200)
    return current & prior


def max_missing_run(mask: np.ndarray) -> int:
    best = current = 0
    for value in mask:
        current = current + 1 if value else 0
        best = max(best, current)
    return best


def load_status(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=["stock_code", "status"])
    frame = pd.read_csv(path, dtype={"stock_code": str})
    frame["stock_code"] = frame.stock_code.map(code6)
    return frame


def status_cache_mismatches(
    universe: list[str], status: pd.DataFrame, valid_cache: set[str], source: str
) -> list[dict]:
    states = status.drop_duplicates("stock_code", keep="last").set_index("stock_code")["status"].to_dict()
    success_states = (
        {"SUCCESS", "SKIP_ALREADY_COMPLETE", "PARTIAL"}
        if source == "BAOSTOCK"
        else {"SUCCESS_WITH_EVENTS", "SUCCESS_NO_EVENTS"}
    )
    rows = []
    for code in universe:
        state = str(states.get(code, ""))
        cached = code in valid_cache
        if state in success_states and not cached:
            kind = "STATUS_SUCCESS_CACHE_MISSING_OR_INVALID"
        elif state and state not in success_states and cached:
            kind = "STATUS_STALE_CACHE_VALID"
        elif not state and cached:
            kind = "CACHE_VALID_STATUS_MISSING"
        elif state and state not in success_states and not cached:
            kind = "STATUS_FAILURE_CACHE_MISSING_OR_INVALID"
        else:
            continue
        rows.append({"stock_code": code, "source": source, "exception_type": kind, "details": f"status={state};cache_valid={cached}"})
    return rows


def read_cninfo(path: Path, code: str) -> tuple[pd.DataFrame, list[str]]:
    errors: list[str] = []
    try:
        frame = pd.read_csv(path, dtype={"stock_code": str})
    except Exception as exc:
        return pd.DataFrame(), [f"CORRUPT_FILE:{type(exc).__name__}:{exc}"]
    if missing := CN_REQUIRED - set(frame):
        return frame, [f"SCHEMA_ERROR:missing={sorted(missing)}"]
    if len(frame):
        frame["stock_code"] = frame.stock_code.map(code6)
        if frame.stock_code.ne(code).any():
            errors.append("STOCK_CODE_MISMATCH")
    for column in ("change_date", "announcement_date", "information_available_date"):
        frame[column] = pd.to_datetime(frame[column], errors="coerce")
    frame["total_shares"] = pd.to_numeric(frame.total_shares, errors="coerce")
    frame["circulating_shares"] = pd.to_numeric(frame.circulating_shares, errors="coerce")
    frame["event_date_incomplete"] = frame.event_date_incomplete.astype(str).str.lower().eq("true")
    return frame, errors


def read_baostock(path: Path, code: str) -> tuple[pd.DataFrame, list[str]]:
    errors: list[str] = []
    try:
        frame = pd.read_csv(path, dtype={"stock_code": str})
    except Exception as exc:
        return pd.DataFrame(), [f"CORRUPT_FILE:{type(exc).__name__}:{exc}"]
    if missing := BAO_REQUIRED - set(frame):
        return frame, [f"SCHEMA_ERROR:missing={sorted(missing)}"]
    frame["stock_code"] = frame.stock_code.map(code6)
    frame["trade_date"] = pd.to_datetime(frame.trade_date, errors="coerce")
    if frame.stock_code.ne(code).any():
        errors.append("STOCK_CODE_MISMATCH")
    if frame.trade_date.isna().any():
        errors.append("UNPARSABLE_TRADE_DATE")
    if frame.trade_date.duplicated().any():
        errors.append("DUPLICATE_TRADE_DATE")
    if not frame.trade_date.is_monotonic_increasing:
        errors.append("DATES_NOT_ASCENDING")
    if frame.trade_date.gt(DATA_CUTOFF).any():
        errors.append("AFTER_CUTOFF_ROWS")
    for column in ("volume_shares", "amount_cny", "baostock_circulating_turnover", "trading_status", "is_st", "close"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if frame.volume_shares.dropna().lt(0).any() or np.isinf(frame.volume_shares.dropna()).any():
        errors.append("NEGATIVE_OR_INFINITE_VOLUME")
    if frame.amount_cny.dropna().lt(0).any() or np.isinf(frame.amount_cny.dropna()).any():
        errors.append("NEGATIVE_OR_INFINITE_AMOUNT")
    turn = frame.baostock_circulating_turnover.dropna()
    if turn.lt(0).any() or np.isinf(turn).any():
        errors.append("INVALID_TURNOVER")
    if not set(frame.trading_status.dropna().unique()).issubset({0, 1}):
        errors.append("INVALID_TRADING_STATUS")
    if not set(frame.is_st.dropna().unique()).issubset({0, 1}):
        errors.append("INVALID_IS_ST")
    return frame, errors


def qfq_dates(root: Path, code: str) -> set[pd.Timestamp]:
    path = root / QFQ_CACHE / f"{code}.csv"
    if not path.exists():
        return set()
    frame = pd.read_csv(path, usecols=["trade_date", "qfq_close"])
    valid = pd.to_numeric(frame.qfq_close, errors="coerce").gt(0)
    return set(pd.to_datetime(frame.loc[valid, "trade_date"], errors="coerce").dropna())


def local_share_validation(root: Path, code: str, lineage: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, pd.Timestamp]:
    path = root / RAW_CACHE / f"{code}.csv"
    if not path.exists():
        return np.array([]), np.array([]), pd.NaT
    raw = pd.read_csv(path, usecols=lambda x: x in {"date", "trade_date", "close", "total_market_cap", "circulating_market_cap"})
    date_col = "trade_date" if "trade_date" in raw else "date"
    raw["trade_date"] = pd.to_datetime(raw[date_col], errors="coerce")
    raw = raw.loc[raw.trade_date.le(DATA_CUTOFF)].drop_duplicates("trade_date", keep="last")
    joined = raw.merge(lineage, on="trade_date", how="left")
    close = pd.to_numeric(joined.close, errors="coerce")
    implied_total = pd.to_numeric(joined.get("total_market_cap"), errors="coerce") / close
    implied_circ = pd.to_numeric(joined.get("circulating_market_cap"), errors="coerce") / close
    total_error = ((implied_total - joined.total_shares).abs() / joined.total_shares).replace([np.inf, -np.inf], np.nan).dropna().to_numpy()
    circ_error = ((implied_circ - joined.circulating_shares).abs() / joined.circulating_shares).replace([np.inf, -np.inf], np.nan).dropna().to_numpy()
    return total_error, circ_error, raw.trade_date.max()


def _quantiles(values: np.ndarray, points: list[float]) -> dict[float, float]:
    clean = values[np.isfinite(values)]
    return {point: float(np.quantile(clean, point)) if len(clean) else math.nan for point in points}


def run(root: Path) -> None:
    root = root.resolve()
    output = root / OUT
    output.mkdir(parents=True, exist_ok=True)
    universe_frame = pd.read_csv(root / "data/processed/h5a_broader_a_universe_v1.csv", dtype={"stock_code": str})
    universe = sorted(universe_frame.loc[universe_frame.universe_status.eq("INCLUDED"), "stock_code"].map(code6).unique())
    if len(universe) != 5195:
        raise ValueError(f"expected_5195_stocks_got={len(universe)}")
    bao_status = load_status(root / "reports/hypothesis_7/data_acquisition/h7_baostock_download_status.csv")
    cn_status = load_status(root / "reports/hypothesis_7/data_acquisition/h7_cninfo_download_status.csv")
    bao_files = {path.stem: path for path in (root / BAO_CACHE).glob("*.csv") if path.stem.isdigit() and len(path.stem) == 6}
    cn_files = {path.stem: path for path in (root / CN_CACHE).glob("*.csv") if path.stem.isdigit() and len(path.stem) == 6}
    malformed = [path for directory in (root / BAO_CACHE, root / CN_CACHE) for path in directory.glob("*.csv") if not (path.stem.isdigit() and len(path.stem) == 6)]
    reference, ref_errors = read_baostock(bao_files.get("000001", Path("missing")), "000001")
    if ref_errors or reference.empty:
        raise ValueError(f"market_calendar_reference_invalid={ref_errors}")
    market_calendar = pd.DatetimeIndex(reference.trade_date.drop_duplicates().sort_values())
    calendar_position = {date: index for index, date in enumerate(market_calendar)}

    quality_rows: list[dict] = []
    history_rows: list[dict] = []
    exceptions: list[dict] = []
    micro_counts = {key: 0 for key in ("A_suspended_volume_zero", "B_trading_volume_zero", "C_volume_positive_turn_zero", "D_volume_zero_turn_positive", "E_turn_missing_suspended", "F_turn_missing_trading")}
    micro_stock_counts = {key: 0 for key in micro_counts}
    primary_chunks: list[np.ndarray] = []
    secondary_chunks: list[np.ndarray] = []
    implied_circ_chunks: list[np.ndarray] = []
    local_total_chunks: list[np.ndarray] = []
    local_circ_chunks: list[np.ndarray] = []
    valid_bao: set[str] = set()
    valid_cn: set[str] = set()
    endpoint_numerators = {1: 0, 2: 0, 5: 0}
    endpoint_denominator = 0
    overlap_rows = expected_order_rows = violation_rows = 0
    suspended_price_rows = unchanged_close_rows = comparable_close_rows = low_volume_rows = positive_volume_rows = 0
    is_st_valid_rows = st_days = secondary_zero_rows = secondary_observation_rows = 0
    suspected_truncated = 0

    for number, code in enumerate(universe, 1):
        bao_path, cn_path = bao_files.get(code), cn_files.get(code)
        bao, bao_errors = (read_baostock(bao_path, code) if bao_path else (pd.DataFrame(), ["CACHE_FILE_MISSING"]))
        events, cn_errors = (read_cninfo(cn_path, code) if cn_path else (pd.DataFrame(), ["CACHE_FILE_MISSING"]))
        if not bao_errors:
            valid_bao.add(code)
        if not cn_errors:
            valid_cn.add(code)
        for error in bao_errors:
            exceptions.append({"stock_code": code, "source": "BAOSTOCK", "exception_type": error.split(":", 1)[0], "details": error})
        for error in cn_errors:
            exceptions.append({"stock_code": code, "source": "CNINFO", "exception_type": error.split(":", 1)[0], "details": error})
        if bao_errors or bao.empty:
            quality_rows.append({"stock_code": code, "board": board(code), "bao_cache_valid": False, "cninfo_cache_valid": not cn_errors})
            history_rows.append({"stock_code": code, "board": board(code), "valid_200d_primary_days": 0, "valid_200d_secondary_days": 0})
            continue

        observed_dates = pd.DatetimeIndex(bao.trade_date)
        interval_calendar = market_calendar[(market_calendar >= observed_dates.min()) & (market_calendar <= observed_dates.max())]
        missing_dates = interval_calendar.difference(observed_dates)
        missing_mask = ~interval_calendar.isin(observed_dates)
        internal_gap = len(missing_dates)
        max_gap = max_missing_run(missing_mask)
        volume = bao.volume_shares
        secondary = bao.baostock_circulating_turnover
        status = bao.trading_status
        zero_patterns = {
            "A_suspended_volume_zero": status.eq(0) & volume.eq(0),
            "B_trading_volume_zero": status.eq(1) & volume.eq(0),
            "C_volume_positive_turn_zero": volume.gt(0) & secondary.eq(0),
            "D_volume_zero_turn_positive": volume.eq(0) & secondary.gt(0),
            "E_turn_missing_suspended": secondary.isna() & status.eq(0),
            "F_turn_missing_trading": secondary.isna() & status.eq(1),
        }
        for key, mask in zero_patterns.items():
            micro_counts[key] += int(mask.sum())
            micro_stock_counts[key] += int(mask.any())
        secondary_chunks.append(secondary.dropna().to_numpy(dtype=float))
        is_st_valid_rows += int(bao.is_st.notna().sum())
        st_days += int(bao.is_st.eq(1).sum())
        secondary_zero_rows += int(secondary.eq(0).sum())
        secondary_observation_rows += int(secondary.notna().sum())
        suspended_price_rows += int((status.eq(0) & bao.close.notna()).sum())
        positions = bao.trade_date.map(calendar_position)
        consecutive = positions.diff().eq(1)
        same_close = bao.close.eq(bao.close.shift(1)) & consecutive.fillna(False)
        unchanged_close_rows += int(same_close.sum())
        comparable_close_rows += int(consecutive.fillna(False).sum())
        positive = volume[volume.gt(0)]
        if len(positive):
            p1_volume = positive.quantile(.01)
            low_volume_rows += int(positive.le(p1_volume).sum())
            positive_volume_rows += len(positive)

        event_count = 0
        incomplete_events = duplicate_events = invalid_total_events = invalid_circ_events = extreme_jumps = date_contract_errors = after_cutoff_events = 0
        if not cn_errors and not events.empty:
            event_count = len(events)
            expected_information = events[["change_date", "announcement_date"]].max(axis=1)
            contract_ok = events.information_available_date.eq(expected_information) | (
                events.information_available_date.isna() & expected_information.isna()
            )
            date_contract_errors = int((~contract_ok).sum())
            incomplete_events = int(events.event_date_incomplete.sum())
            duplicate_events = int(
                events.loc[events.information_available_date.notna(), "information_available_date"]
                .duplicated()
                .sum()
            )
            invalid_total_events = int(events.total_shares.le(0).sum())
            invalid_circ_events = int((events.circulating_shares.lt(0) | events.circulating_shares.gt(events.total_shares)).sum())
            after_cutoff_events = int(events[["change_date", "announcement_date", "information_available_date"]].max(axis=1).gt(DATA_CUTOFF).sum())
            usable_total = events.loc[~events.event_date_incomplete & events.total_shares.gt(0)].sort_values("information_available_date").total_shares
            ratio = usable_total / usable_total.shift(1)
            extreme_jumps = int((ratio.lt(.25) | ratio.gt(4)).sum())
            for kind, count in (
                ("CNINFO_DATE_CONTRACT_MISMATCH", date_contract_errors), ("CNINFO_INCOMPLETE_EVENT_DATE", incomplete_events),
                ("CNINFO_DUPLICATE_INFORMATION_DATE", duplicate_events), ("CNINFO_INVALID_TOTAL_SHARES", invalid_total_events),
                ("CNINFO_INVALID_CIRCULATING_SHARES", invalid_circ_events), ("CNINFO_EVENT_AFTER_CUTOFF", after_cutoff_events),
                ("CNINFO_EXTREME_TOTAL_SHARE_JUMP", extreme_jumps),
            ):
                if count:
                    exceptions.append({"stock_code": code, "source": "CNINFO", "exception_type": kind, "details": f"count={count}"})

        lineage = point_in_time_shares(events if not cn_errors else pd.DataFrame(), observed_dates)
        daily = bao.merge(lineage, on="trade_date", how="left", validate="one_to_one")
        primary = daily.volume_shares / daily.total_shares.where(daily.total_shares.gt(0))
        primary = primary.where(daily.volume_shares.ge(0)).replace([np.inf, -np.inf], np.nan)
        primary_chunks.append(primary.dropna().to_numpy(dtype=float))
        primary_valid = primary.notna()
        secondary_valid = secondary.notna() & secondary.ge(0) & np.isfinite(secondary)
        first_valid_share = daily.loc[daily.total_shares.gt(0), "trade_date"].min()
        if pd.isna(first_valid_share):
            exceptions.append({"stock_code": code, "source": "CNINFO", "exception_type": "NO_OPENING_TOTAL_SHARES", "details": "no point-in-time total-share level in BaoStock interval"})
        elif first_valid_share > daily.trade_date.min():
            exceptions.append({"stock_code": code, "source": "CNINFO", "exception_type": "NO_OPENING_TOTAL_SHARES", "details": f"unknown_until={first_valid_share.date()}"})
        if events.empty and not cn_errors:
            exceptions.append({"stock_code": code, "source": "CNINFO", "exception_type": "SUCCESS_NO_EVENTS_NO_OPENING_LEVEL", "details": "empty history is valid cache but Primary cannot be constructed"})

        calendar_frame = pd.DataFrame({"trade_date": market_calendar}).merge(
            pd.DataFrame({"trade_date": daily.trade_date, "primary_valid": primary_valid, "secondary_valid": secondary_valid}),
            on="trade_date", how="left",
        )
        ready_primary = exact_prior_200_ready(calendar_frame.primary_valid)
        ready_secondary = exact_prior_200_ready(calendar_frame.secondary_valid)
        valid_200_dates = market_calendar[ready_primary.to_numpy()]
        qfq = qfq_dates(root, code)
        endpoint_denominator += len(valid_200_dates)
        for horizon in (1, 2, 5):
            count = 0
            for date in valid_200_dates:
                position = calendar_position[date]
                if position > 0 and position + horizon < len(market_calendar):
                    required = {market_calendar[position - 1], date, market_calendar[position + horizon]}
                    count += required.issubset(qfq)
            endpoint_numerators[horizon] += count

        overlap = primary.notna() & secondary.notna()
        relative_violation = primary > secondary * 1.01
        violation_relative = (primary / secondary.replace(0, np.nan) - 1).replace([np.inf, -np.inf], np.nan)
        overlap_rows += int(overlap.sum())
        expected_order_rows += int((overlap & (primary <= secondary * (1 + 1e-10))).sum())
        violation_rows += int((overlap & relative_violation).sum())
        implied_valid = daily.volume_shares.gt(0) & secondary.gt(0) & daily.circulating_shares.gt(0)
        implied = daily.loc[implied_valid, "volume_shares"] / secondary[implied_valid]
        implied_error = ((implied - daily.loc[implied_valid, "circulating_shares"]).abs() / daily.loc[implied_valid, "circulating_shares"]).replace([np.inf, -np.inf], np.nan)
        implied_circ_chunks.append(implied_error.dropna().to_numpy(dtype=float))
        total_local, circ_local, local_last = local_share_validation(root, code, lineage)
        local_total_chunks.append(total_local)
        local_circ_chunks.append(circ_local)
        implied_median, implied_p95 = implied_error.median(), implied_error.quantile(.95)
        local_total_median = float(np.median(total_local)) if len(total_local) else math.nan
        local_total_p95 = float(np.quantile(total_local, .95)) if len(total_local) else math.nan
        local_circ_median = float(np.median(circ_local)) if len(circ_local) else math.nan
        local_circ_p95 = float(np.quantile(circ_local, .95)) if len(circ_local) else math.nan
        if int((overlap & relative_violation).sum()):
            exceptions.append({
                "stock_code": code, "source": "CROSS_CHECK",
                "exception_type": "PRIMARY_SECONDARY_ORDER_VIOLATION_GT_1PCT",
                "details": f"rows={int((overlap & relative_violation).sum())};max_relative={violation_relative.max():.6g}",
            })
        if (pd.notna(implied_median) and implied_median > .10) or (pd.notna(implied_p95) and implied_p95 > .20):
            exceptions.append({
                "stock_code": code, "source": "CROSS_CHECK",
                "exception_type": "BAOSTOCK_CNINFO_CIRCULATING_DISCREPANCY",
                "details": f"median={implied_median:.6g};p95={implied_p95:.6g}",
            })
        if (np.isfinite(local_total_median) and local_total_median > .10) or (np.isfinite(local_total_p95) and local_total_p95 > .20):
            exceptions.append({
                "stock_code": code, "source": "LOCAL_VALIDATION",
                "exception_type": "LOCAL_TOTAL_SHARE_VALIDATION_DISCREPANCY",
                "details": f"median={local_total_median:.6g};p95={local_total_p95:.6g}",
            })
        if (np.isfinite(local_circ_median) and local_circ_median > .10) or (np.isfinite(local_circ_p95) and local_circ_p95 > .20):
            exceptions.append({
                "stock_code": code, "source": "LOCAL_VALIDATION",
                "exception_type": "LOCAL_CIRCULATING_SHARE_VALIDATION_DISCREPANCY",
                "details": f"median={local_circ_median:.6g};p95={local_circ_p95:.6g}",
            })
        qfq_last = max(qfq) if qfq else pd.NaT
        local_reference_last = max((x for x in (local_last, qfq_last) if pd.notna(x)), default=pd.NaT)
        truncated = False
        if pd.notna(local_reference_last) and local_reference_last > observed_dates.max():
            between = market_calendar[(market_calendar > observed_dates.max()) & (market_calendar <= local_reference_last)]
            truncated = len(between) >= 5
            if truncated:
                suspected_truncated += 1
                exceptions.append({"stock_code": code, "source": "BAOSTOCK", "exception_type": "SUSPECTED_TRUNCATED_DOWNLOAD", "details": f"bao_last={observed_dates.max().date()};local_last={local_reference_last.date()}"})

        primary_coverage = float(primary_valid.mean())
        secondary_coverage = float(secondary_valid.mean())
        quality_rows.append({
            "stock_code": code, "board": board(code), "bao_cache_valid": not bao_errors, "cninfo_cache_valid": not cn_errors,
            "first_trade_date": observed_dates.min(), "last_trade_date": observed_dates.max(), "row_count": len(bao),
            "trading_day_count": int(status.eq(1).sum()), "nontrading_status_count": int(status.eq(0).sum()),
            "valid_volume_days": int(volume.notna().sum()), "valid_turnover_days": int(secondary_valid.sum()),
            "amount_missing_days": int(bao.amount_cny.isna().sum()), "internal_missing_market_days": internal_gap,
            "maximum_internal_gap": max_gap, "history_shape": "INTERNAL_GAP_SUSPECTED" if internal_gap else ("LIKELY_SHORT_LISTING_HISTORY" if observed_dates.min() > START_DATE + pd.Timedelta(days=60) else "FULL_OR_EXPECTED_HISTORY"),
            "cninfo_event_count": event_count, "cninfo_incomplete_event_count": incomplete_events,
            "first_valid_total_share_date": first_valid_share, "last_valid_total_share_date": daily.loc[daily.total_shares.gt(0), "trade_date"].max(),
            "valid_total_share_days": int(daily.total_shares.gt(0).sum()), "share_lineage_coverage": float(daily.total_shares.gt(0).mean()),
            "primary_valid_rows": int(primary_valid.sum()), "primary_coverage": primary_coverage,
            "secondary_valid_rows": int(secondary_valid.sum()), "secondary_coverage": secondary_coverage,
            "primary_gt_one_rows": int(primary.gt(1).sum()), "primary_secondary_overlap_rows": int(overlap.sum()),
            "primary_gt_secondary_by_1pct_rows": int((overlap & relative_violation).sum()),
            "baostock_implied_circ_vs_cninfo_median_error": implied_median,
            "baostock_implied_circ_vs_cninfo_p95_error": implied_p95,
            "local_total_vs_cninfo_median_error": local_total_median,
            "local_total_vs_cninfo_p95_error": local_total_p95,
            "local_circulating_vs_cninfo_median_error": local_circ_median,
            "local_circulating_vs_cninfo_p95_error": local_circ_p95,
            "secondary_distinct_values": int(secondary.dropna().nunique()), "suspected_truncated_download": truncated,
        })
        history_rows.append({
            "stock_code": code, "board": board(code), "first_valid_200d_date": market_calendar[ready_primary.to_numpy()].min() if ready_primary.any() else pd.NaT,
            "valid_200d_primary_days": int(ready_primary.sum()), "valid_200d_secondary_days": int(ready_secondary.sum()),
            "endpoint_1d_ready_days": sum(1 for date in valid_200_dates if calendar_position[date] > 0 and calendar_position[date] + 1 < len(market_calendar) and {market_calendar[calendar_position[date] - 1], date, market_calendar[calendar_position[date] + 1]}.issubset(qfq)),
            "endpoint_2d_ready_days": sum(1 for date in valid_200_dates if calendar_position[date] > 0 and calendar_position[date] + 2 < len(market_calendar) and {market_calendar[calendar_position[date] - 1], date, market_calendar[calendar_position[date] + 2]}.issubset(qfq)),
            "endpoint_5d_ready_days": sum(1 for date in valid_200_dates if calendar_position[date] > 0 and calendar_position[date] + 5 < len(market_calendar) and {market_calendar[calendar_position[date] - 1], date, market_calendar[calendar_position[date] + 5]}.issubset(qfq)),
        })
        if number % 250 == 0:
            print(f"offline_quality_audit={number}/{len(universe)}", flush=True)

    exceptions.extend(status_cache_mismatches(universe, bao_status, valid_bao, "BAOSTOCK"))
    exceptions.extend(status_cache_mismatches(universe, cn_status, valid_cn, "CNINFO"))
    for path in malformed:
        exceptions.append({"stock_code": "", "source": path.parent.name.upper(), "exception_type": "MALFORMED_CACHE_FILENAME", "details": path.name})
    quality = pd.DataFrame(quality_rows)
    history = pd.DataFrame(history_rows)
    exception_frame = pd.DataFrame(exceptions)
    size = pd.read_csv(root / "reports/hypothesis_7/h7_history_sufficiency.csv", dtype={"stock_code": str})
    size = size.loc[size.row_type.eq("stock"), ["stock_code", "latest_total_market_cap"]]
    size["stock_code"] = size.stock_code.map(code6)
    history = history.merge(size, on="stock_code", how="left")
    history["log_size"] = np.log(pd.to_numeric(history.latest_total_market_cap, errors="coerce"))
    eligible_size = history.log_size.notna()
    history.loc[eligible_size, "size_quartile"] = pd.qcut(
        history.loc[eligible_size, "log_size"].rank(method="first"), 4,
        labels=["Q1_SMALL", "Q2", "Q3", "Q4_LARGE"],
    ).astype(str)
    threshold_rows = []
    for threshold in (500, 750, 1000, 1250):
        included = history.valid_200d_primary_days.ge(threshold)
        threshold_rows.append({"row_type": "threshold", "threshold": threshold, "stock_count": int(included.sum()), "percentage_of_universe": float(included.mean())})
        rates = history.assign(included=included).groupby("size_quartile", observed=True).included.mean()
        for quartile, rate in rates.items():
            threshold_rows.append({"row_type": "size_quartile", "threshold": threshold, "size_quartile": quartile, "inclusion_rate": rate})
    threshold_frame = pd.DataFrame(threshold_rows)
    primary_values = np.concatenate(primary_chunks) if primary_chunks else np.array([])
    secondary_values = np.concatenate(secondary_chunks) if secondary_chunks else np.array([])
    implied_errors = np.concatenate(implied_circ_chunks) if implied_circ_chunks else np.array([])
    local_total_errors = np.concatenate(local_total_chunks) if local_total_chunks else np.array([])
    local_circ_errors = np.concatenate(local_circ_chunks) if local_circ_chunks else np.array([])
    primary_q = _quantiles(primary_values, [0, .001, .01, .05, .5, .95, .99, .999, 1])
    secondary_q = _quantiles(secondary_values, [.01, .5, .99, 1])
    implied_q = _quantiles(implied_errors, [.5, .9, .95, .99])
    local_total_q = _quantiles(local_total_errors, [.5, .95])
    local_circ_q = _quantiles(local_circ_errors, [.5, .95])
    history_rho = history[["valid_200d_primary_days", "log_size"]].corr(method="spearman").iloc[0, 1]
    status_mismatch_count = int(exception_frame.exception_type.isin({"STATUS_SUCCESS_CACHE_MISSING_OR_INVALID", "STATUS_STALE_CACHE_VALID", "CACHE_VALID_STATUS_MISSING", "STATUS_FAILURE_CACHE_MISSING_OR_INVALID"}).sum())
    primary_stocks = int(quality.primary_valid_rows.gt(0).sum())
    exception_stock_count = int(exception_frame.loc[exception_frame.stock_code.ne(""), "stock_code"].nunique())
    readiness = "H7_DATA_NOT_READY" if primary_stocks / len(universe) < .90 or len(valid_bao) / len(universe) < .95 else (
        "H7_DATA_READY_WITH_EXCEPTIONS" if exception_stock_count else "H7_DATA_READY"
    )
    micro_rows = [
        {"metric": "tradestatus_coverage", "value": quality.trading_day_count.add(quality.nontrading_status_count).sum() / quality.row_count.sum()},
        {"metric": "isST_coverage", "value": is_st_valid_rows / quality.row_count.sum()},
        {"metric": "suspended_stock_days", "value": quality.nontrading_status_count.sum()},
        {"metric": "ST_stock_days", "value": st_days},
        {"metric": "secondary_zero_rate", "value": secondary_zero_rows / secondary_observation_rows if secondary_observation_rows else math.nan},
        {"metric": "suspended_days_with_price_observation", "value": suspended_price_rows},
        {"metric": "consecutive_unchanged_close_rate", "value": unchanged_close_rows / comparable_close_rows if comparable_close_rows else math.nan},
        {"metric": "within_stock_positive_volume_p1_day_rate", "value": low_volume_rows / positive_volume_rows if positive_volume_rows else math.nan},
        {"metric": "historical_limit_status_ready", "value": False},
    ]
    total_bao_rows = quality.row_count.sum()
    for key, count in micro_counts.items():
        micro_rows.append({"metric": f"zero_semantics_{key}_count", "value": count})
        micro_rows.append({"metric": f"zero_semantics_{key}_stock_count", "value": micro_stock_counts[key]})
        micro_rows.append({"metric": f"zero_semantics_{key}_stock_day_rate", "value": count / total_bao_rows})
    board_summary = quality.groupby("board", observed=True).agg(
        stock_count=("stock_code", "size"), bao_success=("bao_cache_valid", "sum"),
        cninfo_event_stocks=("cninfo_event_count", lambda x: int(x.gt(0).sum())),
        median_primary_coverage=("primary_coverage", "median"),
    ).reset_index()
    board_history = history.groupby("board", observed=True).valid_200d_primary_days.median().rename("median_valid_200d_primary_days").reset_index()
    board_summary = board_summary.merge(board_history, on="board", how="left")
    micro = pd.DataFrame(micro_rows)
    quality.to_csv(output / "h7_turnover_quality_by_stock.csv", index=False, encoding="utf-8-sig")
    exception_frame.to_csv(output / "h7_turnover_quality_exceptions.csv", index=False, encoding="utf-8-sig")
    pd.concat([history.assign(row_type="stock"), threshold_frame], ignore_index=True, sort=False).to_csv(output / "h7_history_sufficiency_real.csv", index=False, encoding="utf-8-sig")
    pd.concat([micro.assign(row_type="metric"), board_summary.assign(row_type="board")], ignore_index=True, sort=False).to_csv(output / "h7_microstructure_readiness.csv", index=False, encoding="utf-8-sig")
    report = build_report(
        universe, bao_files, cn_files, bao_status, cn_status, valid_bao, valid_cn, quality,
        exception_frame, threshold_frame, micro, board_summary, primary_q, secondary_q,
        implied_q, local_total_q, local_circ_q, overlap_rows, expected_order_rows,
        violation_rows, status_mismatch_count, suspected_truncated, endpoint_denominator,
        endpoint_numerators, history_rho, readiness,
    )
    (output / "h7_turnover_data_quality_report.md").write_text(report, encoding="utf-8")
    print(f"H7_data_readiness={readiness}")
    print(f"primary_stocks={primary_stocks};status_cache_mismatch_count={status_mismatch_count}")


def build_report(
    universe: list[str], bao_files: dict, cn_files: dict, bao_status: pd.DataFrame,
    cn_status: pd.DataFrame, valid_bao: set[str], valid_cn: set[str], quality: pd.DataFrame,
    exceptions: pd.DataFrame, thresholds: pd.DataFrame, micro: pd.DataFrame,
    board_summary: pd.DataFrame, primary_q: dict, secondary_q: dict, implied_q: dict,
    local_total_q: dict, local_circ_q: dict, overlap_rows: int, expected_order_rows: int,
    violation_rows: int, mismatch_count: int, suspected_truncated: int,
    endpoint_denominator: int, endpoint_numerators: dict, history_rho: float,
    readiness: str,
) -> str:
    bao_counts = bao_status.status.value_counts().to_dict()
    cn_counts = cn_status.status.value_counts().to_dict()
    primary = quality.loc[quality.primary_valid_rows.gt(0)]
    secondary = quality.loc[quality.secondary_valid_rows.gt(0)]
    top_exceptions = exceptions.exception_type.value_counts().head(12).to_dict() if len(exceptions) else {}
    exception_counts = exceptions.exception_type.value_counts().to_dict() if len(exceptions) else {}
    micro_map = micro.set_index("metric").value.to_dict()
    threshold_counts = thresholds.loc[thresholds.row_type.eq("threshold")].set_index("threshold").stock_count.to_dict()
    precision_concern = quality.secondary_distinct_values.median() < 100
    semantic_review = sum(micro_map.get(f"zero_semantics_{key}_count", 0) for key in ("B_trading_volume_zero", "C_volume_positive_turn_zero", "D_volume_zero_turn_positive", "F_turn_missing_trading")) / quality.row_count.sum() > .01
    return f"""# H7 Post-Download Data Quality & Readiness Audit

## Decision

**{readiness}.** Both source caches cover the 5,195-stock universe and were re-read independently of status. Primary turnover is broadly constructible, but data-availability and lineage exceptions remain explicit; none was repaired with future events, local cap/close, or BaoStock-implied shares. This is a data-layer decision only.

```text
data_cutoff=2026-08-20
broader_a_stock_count={len(universe)}
BAOSTOCK_cache_files={len(bao_files)}
BAOSTOCK_valid_files={len(valid_bao)}
BAOSTOCK_complete_or_usable_stocks={int(quality.bao_cache_valid.sum())}
BAOSTOCK_failed_or_corrupt_stocks={len(universe)-len(valid_bao)}
BAOSTOCK_suspected_truncated_downloads={suspected_truncated}
BAOSTOCK_status={json.dumps(bao_counts, ensure_ascii=False)}
CNINFO_cache_files={len(cn_files)}
CNINFO_valid_files={len(valid_cn)}
CNINFO_status={json.dumps(cn_counts, ensure_ascii=False)}
CNINFO_stocks_without_opening_total_shares={int(quality.first_valid_total_share_date.isna().sum() + (quality.first_valid_total_share_date > quality.first_trade_date).sum())}
status_cache_mismatch_count={mismatch_count}
PRIMARY_stock_count_with_any_valid_data={int(primary.stock_code.nunique())}
PRIMARY_median_coverage={primary.primary_coverage.median()}
PRIMARY_p10_coverage={primary.primary_coverage.quantile(.10)}
PRIMARY_stocks_ge_99pct_coverage={int(quality.primary_coverage.ge(.99).sum())}
PRIMARY_stocks_ge_95pct_coverage={int(quality.primary_coverage.ge(.95).sum())}
PRIMARY_stocks_ge_90pct_coverage={int(quality.primary_coverage.ge(.90).sum())}
PRIMARY_stocks_lt_80pct_coverage={int(quality.primary_coverage.lt(.80).sum())}
SECONDARY_stock_count={int(secondary.stock_code.nunique())}
SECONDARY_median_coverage={secondary.secondary_coverage.median()}
SECONDARY_median_distinct_values_per_stock={quality.secondary_distinct_values.median()}
primary_vs_secondary_expected_order_rate={expected_order_rows/overlap_rows if overlap_rows else math.nan}
primary_gt_secondary_by_more_than_1pct_rows={violation_rows}
baostock_implied_circ_vs_cninfo_median_error={implied_q[.5]}
baostock_implied_circ_vs_cninfo_p95_error={implied_q[.95]}
stocks_with_any_valid_200d={int(quality.merge(pd.read_csv(Path.cwd()/OUT/'h7_history_sufficiency_real.csv', dtype={'stock_code': str}), on='stock_code', how='left').valid_200d_primary_days.gt(0).sum()) if (Path.cwd()/OUT/'h7_history_sufficiency_real.csv').exists() else 'see_csv'}
stocks_ge_500_valid_days={int(threshold_counts.get(500, 0))}
stocks_ge_750_valid_days={int(threshold_counts.get(750, 0))}
stocks_ge_1000_valid_days={int(threshold_counts.get(1000, 0))}
stocks_ge_1250_valid_days={int(threshold_counts.get(1250, 0))}
history_length_size_spearman={history_rho}
endpoint_1D_coverage={endpoint_numerators[1]/endpoint_denominator if endpoint_denominator else math.nan}
endpoint_2D_coverage={endpoint_numerators[2]/endpoint_denominator if endpoint_denominator else math.nan}
endpoint_5D_coverage={endpoint_numerators[5]/endpoint_denominator if endpoint_denominator else math.nan}
tradestatus_coverage={micro_map['tradestatus_coverage']}
isST_coverage={micro_map['isST_coverage']}
suspended_stock_days={int(micro_map['suspended_stock_days'])}
ST_stock_days={int(micro_map['ST_stock_days'])}
historical_limit_status_ready=false
top_quality_exception_types={json.dumps(top_exceptions, ensure_ascii=False)}
C2_estimated=false
volume_return_regression_run=false
future_performance_accessed=false
network_download_performed=false
H5_run=false
H6_run=false
MCTS_run=false
Phase_B_run=false
H7_data_readiness={readiness}
```

## Cache and structural QA

Status and physical caches were checked independently. BaoStock valid files={len(valid_bao):,}/{len(universe):,}; CNINFO valid files={len(valid_cn):,}/{len(universe):,}. Empty CNINFO histories are valid `SUCCESS_NO_EVENTS` responses, not schema crashes. Malformed or stale status/cache combinations are listed in the exceptions CSV. Structural exception counts include schema, duplicate date, cutoff, sign/range, information-date, duplicate-event and extreme-jump checks.

```text
files_with_schema_error={exception_counts.get('SCHEMA_ERROR', 0)}
files_with_corrupt_content={exception_counts.get('CORRUPT_FILE', 0)}
files_with_duplicate_dates={exception_counts.get('DUPLICATE_TRADE_DATE', 0)}
files_with_after_cutoff_rows={exception_counts.get('AFTER_CUTOFF_ROWS', 0)}
files_with_negative_volume={exception_counts.get('NEGATIVE_OR_INFINITE_VOLUME', 0)}
files_with_invalid_turnover={exception_counts.get('INVALID_TURNOVER', 0)}
stocks_with_internal_market_day_gaps={int(quality.internal_missing_market_days.gt(0).sum())}
```

## Measurement and zero semantics

Primary decimal turnover quantiles are p0={primary_q[0]:.8g}, p0.1={primary_q[.001]:.8g}, p1={primary_q[.01]:.8g}, p5={primary_q[.05]:.8g}, median={primary_q[.5]:.8g}, p95={primary_q[.95]:.8g}, p99={primary_q[.99]:.8g}, p99.9={primary_q[.999]:.8g}, max={primary_q[1]:.8g}. `turnover>1` rows={int(quality.primary_gt_one_rows.sum())}; values were flagged, not winsorized.

Secondary turnover has zero rate={micro_map['secondary_zero_rate']:.8g}, missing rate={1-secondary.secondary_valid_rows.sum()/quality.row_count.sum():.8g}, p1={secondary_q[.01]:.8g}, median={secondary_q[.5]:.8g}, p99={secondary_q[.99]:.8g}, max={secondary_q[1]:.8g}. Median distinct values per stock={quality.secondary_distinct_values.median():.1f}, p10={quality.secondary_distinct_values.quantile(.10):.1f}; precision concern={precision_concern}.

Full-market zero/missing patterns are stored in `h7_microstructure_readiness.csv`. `ZERO_OR_MISSING_SEMANTICS_REVIEW_REQUIRED={semantic_review}` is based only on whether B/C/D/F exceed 1% in aggregate; it does not select epsilon.

## Share lineage and denominator cross-checks

Point-in-time total shares use only complete events on/after `max(change_date, announcement_date)`, then apply the known level forward. The interval before the first usable level remains unknown. `SUCCESS_NO_EVENTS` has no authoritative external opening level in the current project, so it stays `NO_OPENING_TOTAL_SHARES`.

Across overlap rows, `TOTAL_SHARE_TURNOVER <= BAOSTOCK_CIRCULATING_TURNOVER` within numerical tolerance on {expected_order_rows/overlap_rows if overlap_rows else math.nan:.6%}; rows exceeding the secondary by more than 1%={violation_rows:,}. These are validation flags, not automatic deletions, because the denominators differ. BaoStock-implied circulating-share relative error versus CNINFO has median={implied_q[.5]:.6%}, p90={implied_q[.9]:.6%}, p95={implied_q[.95]:.6%}, p99={implied_q[.99]:.6%}.

Local implied total-share error has pooled median={local_total_q[.5]:.6%}, p95={local_total_q[.95]:.6%}; local implied circulating-share error has median={local_circ_q[.5]:.6%}, p95={local_circ_q[.95]:.6%}. These remain **USEFUL_BUT_NOT_AUTHORITATIVE** and never fill Primary.

## Exact history and endpoint readiness

Every eligible t requires a valid current Primary measurement and all exact prior 200 BaoStock market dates; t is excluded from its own baseline and no missing date is replaced. These are measurement-availability counts only: the future log/epsilon contract remains undecided. QFQ endpoint coverage checks only the presence of t-1, t and t+1/t+2/t+5 closes; no return was calculated.

{thresholds.loc[thresholds.row_type.eq('threshold')].to_markdown(index=False)}

The size relation is Spearman(valid history days, log latest historical market cap)={history_rho:.6f}. Size-quartile inclusion rates are in `h7_history_sufficiency_real.csv`; no new industry or listing-year metadata was downloaded.

## Board and microstructure readiness

{board_summary.to_markdown(index=False)}

`tradestatus` and `isST` are available at the rates above. Suspended rows are retained. Historical limit-up/down or one-price-limit authoritative fields are absent, so `historical_limit_status_ready=false`; OHLC was not promoted to an authoritative substitute. Constant-close, suspended-price, stock-specific positive-volume p1-day, and ST-day diagnostics are descriptive only.

## Recommended next step

Review the explicit lineage/order/status exceptions and choose a minimum valid-history threshold using coverage and selection-bias evidence only. Then preregister H7 measurement, zero/log handling, eligible-sample and microstructure exclusions before any coefficient estimation. Do not select the threshold from H7 results.
"""


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    run(parser.parse_args().project_root)
