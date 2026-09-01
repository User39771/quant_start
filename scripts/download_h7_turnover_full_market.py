"""Cache-first H7 turnover data acquisition; no return or H7 performance analysis."""

# ruff: noqa: E501 -- source contracts and report prose are intentionally explicit.

from __future__ import annotations

import argparse
import json
import math
import socket
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests

START_DATE = pd.Timestamp("2020-01-01")
DATA_CUTOFF = pd.Timestamp("2026-08-20")
FIELDS = "date,code,open,high,low,close,volume,amount,turn,tradestatus,isST"
CACHE = Path("data/cache/h7_turnover")
REPORTS = Path("reports/hypothesis_7/data_acquisition")
PANEL = Path("data/processed/h7_turnover_daily_panel_v1.csv")
CHECKPOINT_EVERY = 50
MAX_ATTEMPTS = 3


def code6(value: object) -> str:
    digits = "".join(char for char in str(value) if char.isdigit())
    return digits[-6:].zfill(6)


def load_universe(root: Path) -> pd.DataFrame:
    path = root / "data/processed/h5a_broader_a_universe_v1.csv"
    frame = pd.read_csv(path, dtype={"stock_code": str})
    frame["stock_code"] = frame["stock_code"].map(code6)
    frame = frame.loc[frame["universe_status"].eq("INCLUDED")].copy()
    if len(frame) != 5195 or frame.stock_code.duplicated().any():
        raise ValueError(f"expected_5195_unique_included_stocks_got={len(frame)}")
    return frame.sort_values("stock_code").reset_index(drop=True)


def _atomic_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    frame.to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(path)


def _load_status(path: Path, universe: pd.DataFrame) -> pd.DataFrame:
    if path.exists():
        status = pd.read_csv(path, dtype={"stock_code": str})
        status["stock_code"] = status.stock_code.map(code6)
    else:
        status = pd.DataFrame({"stock_code": universe.stock_code})
    return universe[["stock_code"]].merge(status, on="stock_code", how="left").astype(object)


def normalize_baostock(frame: pd.DataFrame, stock_code: str) -> tuple[pd.DataFrame, int]:
    out = frame.copy()
    out.columns = [str(column).strip() for column in out.columns]
    required = set(FIELDS.split(","))
    if missing := required - set(out):
        raise ValueError(f"missing_fields={sorted(missing)}")
    out["stock_code"] = code6(stock_code)
    out["trade_date"] = pd.to_datetime(out["date"], errors="coerce")
    for column in ("open", "high", "low", "close", "volume", "amount", "turn"):
        out[column] = pd.to_numeric(out[column], errors="coerce")
    received_after = int(out.trade_date.gt(DATA_CUTOFF).sum())
    out = out.loc[out.trade_date.between(START_DATE, DATA_CUTOFF)].copy()
    out["volume_shares"] = out.volume
    out["amount_cny"] = out.amount
    out["baostock_circulating_turnover"] = out.turn / 100.0
    out["trading_status"] = pd.to_numeric(out.tradestatus, errors="coerce")
    out["is_st"] = pd.to_numeric(out.isST, errors="coerce")
    columns = [
        "stock_code", "trade_date", "open", "high", "low", "close", "volume",
        "amount", "turn", "tradestatus", "isST", "volume_shares", "amount_cny",
        "baostock_circulating_turnover", "trading_status", "is_st",
    ]
    return out[columns].sort_values("trade_date").reset_index(drop=True), received_after


def validate_baostock(frame: pd.DataFrame, stock_code: str) -> None:
    if frame.empty:
        raise ValueError("empty_response")
    dates = pd.to_datetime(frame.trade_date, errors="coerce")
    if frame.stock_code.map(code6).ne(stock_code).any():
        raise ValueError("stock_code_mismatch")
    if dates.isna().any() or dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("invalid_or_duplicate_dates")
    if dates.gt(DATA_CUTOFF).any():
        raise ValueError("date_after_cutoff")
    for column in ("volume_shares", "amount_cny", "baostock_circulating_turnover"):
        values = pd.to_numeric(frame[column], errors="coerce")
        if values.dropna().lt(0).any() or np.isinf(values.dropna()).any():
            raise ValueError(f"invalid_{column}")
    status = pd.to_numeric(frame.trading_status, errors="coerce").dropna()
    if not set(status.unique()).issubset({0, 1}):
        raise ValueError("invalid_trading_status")


def cninfo_headers() -> dict[str, str]:
    import py_mini_racer
    from akshare.stock.stock_share_changes_cninfo import _get_file_content_cninfo

    js = py_mini_racer.MiniRacer()
    js.eval(_get_file_content_cninfo("cninfo.js"))
    return {
        "Accept": "*/*",
        "Accept-Enckey": js.call("getResCode1"),
        "Accept-Encoding": "gzip, deflate",
        "Origin": "https://webapi.cninfo.com.cn",
        "Referer": "https://webapi.cninfo.com.cn/",
        "User-Agent": "Mozilla/5.0",
        "X-Requested-With": "XMLHttpRequest",
    }


def normalize_cninfo_payload(payload: dict, stock_code: str) -> tuple[pd.DataFrame, int]:
    records = payload.get("records", []) if isinstance(payload, dict) else []
    if not records:
        return pd.DataFrame(columns=[
            "stock_code", "change_date", "announcement_date", "information_available_date",
            "total_shares", "circulating_shares", "restricted_shares", "change_reason",
            "event_date_incomplete", "raw_json",
        ]), 0
    raw = pd.DataFrame(records)
    required = {"DECLAREDATE", "VARYDATE", "F003N", "F021N"}
    if missing := required - set(raw):
        raise ValueError(f"cninfo_missing_fields={sorted(missing)}")
    out = pd.DataFrame({
        "stock_code": code6(stock_code),
        "change_date": pd.to_datetime(raw.VARYDATE, errors="coerce"),
        "announcement_date": pd.to_datetime(raw.DECLAREDATE, errors="coerce"),
        "total_shares": pd.to_numeric(raw.F003N, errors="coerce") * 10_000.0,
        "circulating_shares": pd.to_numeric(raw.F021N, errors="coerce") * 10_000.0,
        "restricted_shares": pd.to_numeric(raw.get("F028N"), errors="coerce") * 10_000.0,
        "change_reason": raw.get("F002V", pd.Series(index=raw.index, dtype=object)),
        "raw_json": [json.dumps(row, ensure_ascii=False, default=str) for row in records],
    })
    out["event_date_incomplete"] = out[["change_date", "announcement_date"]].isna().any(axis=1)
    out["information_available_date"] = out[["change_date", "announcement_date"]].max(axis=1)
    after = out[["change_date", "announcement_date"]].max(axis=1).gt(DATA_CUTOFF)
    discarded = int(after.sum())
    out = out.loc[~after].copy()
    columns = [
        "stock_code", "change_date", "announcement_date", "information_available_date",
        "total_shares", "circulating_shares", "restricted_shares", "change_reason",
        "event_date_incomplete", "raw_json",
    ]
    return out[columns].sort_values(["information_available_date", "change_date"]).reset_index(drop=True), discarded


def point_in_time_shares(events: pd.DataFrame, dates: pd.Series) -> pd.DataFrame:
    calendar = pd.DataFrame({"trade_date": pd.to_datetime(dates)}).sort_values("trade_date")
    usable = events.loc[
        ~events.event_date_incomplete.astype(bool)
        & pd.to_numeric(events.total_shares, errors="coerce").gt(0)
        & pd.to_datetime(events.information_available_date, errors="coerce").notna(),
        ["information_available_date", "total_shares", "circulating_shares"],
    ].copy()
    usable["information_available_date"] = pd.to_datetime(usable.information_available_date)
    usable = usable.sort_values("information_available_date").drop_duplicates(
        "information_available_date", keep="last"
    )
    if usable.empty:
        calendar["information_available_date"] = pd.NaT
        calendar["total_shares"] = np.nan
        calendar["circulating_shares"] = np.nan
        return calendar
    return pd.merge_asof(
        calendar, usable, left_on="trade_date", right_on="information_available_date",
        direction="backward", allow_exact_matches=True,
    )


def exact_prior_200_valid(values: pd.Series) -> pd.Series:
    valid = pd.to_numeric(values, errors="coerce").map(lambda x: bool(np.isfinite(x) and x >= 0))
    return valid.shift(1).rolling(200, min_periods=200).sum().eq(200)


def _error_type(exc: Exception) -> str:
    text = str(exc).lower()
    if isinstance(exc, requests.RequestException) or any(x in text for x in ("timeout", "ssl", "connection")):
        return "NETWORK_FAILURE"
    if isinstance(exc, (KeyError, ValueError)):
        return "SCHEMA_OR_DATA_FAILURE"
    return type(exc).__name__.upper()


def run_baostock(root: Path) -> None:
    import baostock as bs

    universe = load_universe(root)
    cache = root / CACHE / "baostock"
    status_path = root / REPORTS / "h7_baostock_download_status.csv"
    status = _load_status(status_path, universe).set_index("stock_code")
    socket.setdefaulttimeout(30)
    login = bs.login()
    if login.error_code != "0":
        raise RuntimeError(f"baostock_login_failed:{login.error_code}:{login.error_msg}")
    consecutive_failures = 0
    try:
        for number, code in enumerate(universe.stock_code, 1):
            path = cache / f"{code}.csv"
            old_state = str(status.at[code, "status"]) if "status" in status else ""
            if old_state in {"SUCCESS", "SKIP_ALREADY_COMPLETE"} and path.exists():
                try:
                    existing = pd.read_csv(path, dtype={"stock_code": str})
                    existing["trade_date"] = pd.to_datetime(existing.trade_date)
                    validate_baostock(existing, code)
                    status.at[code, "status"] = "SKIP_ALREADY_COMPLETE"
                    continue
                except Exception:
                    pass
            existing = pd.DataFrame()
            request_start = START_DATE
            if path.exists():
                try:
                    existing = pd.read_csv(path, dtype={"stock_code": str})
                    existing["trade_date"] = pd.to_datetime(existing.trade_date)
                    validate_baostock(existing, code)
                    if existing.trade_date.max() == DATA_CUTOFF:
                        status.at[code, "status"] = "SKIP_ALREADY_COMPLETE"
                        continue
                    request_start = existing.trade_date.max() + pd.Timedelta(days=1)
                except Exception:
                    existing = pd.DataFrame()
                    request_start = START_DATE
            attempts = 0
            error = ""
            state = "FAILED"
            received_after = 0
            combined = existing
            for attempts in range(1, MAX_ATTEMPTS + 1):
                try:
                    vendor = ("sh." if code.startswith(("5", "6", "9")) else "sz.") + code
                    result = bs.query_history_k_data_plus(
                        vendor, FIELDS, start_date=request_start.date().isoformat(),
                        end_date=DATA_CUTOFF.date().isoformat(), frequency="d", adjustflag="3",
                    )
                    rows = []
                    while result.error_code == "0" and result.next():
                        rows.append(result.get_row_data())
                    if result.error_code != "0":
                        raise RuntimeError(f"{result.error_code}:{result.error_msg}")
                    if not rows and len(existing):
                        combined = existing
                    else:
                        raw = pd.DataFrame(rows, columns=result.fields)
                        fresh, received_after = normalize_baostock(raw, code)
                        combined = pd.concat([existing, fresh], ignore_index=True)
                        combined = combined.drop_duplicates("trade_date", keep="last")
                        combined = combined.sort_values("trade_date").reset_index(drop=True)
                    validate_baostock(combined, code)
                    _atomic_csv(combined, path)
                    state, error = "SUCCESS", ""
                    consecutive_failures = 0
                    break
                except Exception as exc:
                    error = f"{type(exc).__name__}:{exc}"
                    if attempts < MAX_ATTEMPTS:
                        time.sleep(attempts)
            if state == "FAILED":
                consecutive_failures += 1
            status.loc[code, [
                "status", "attempt_count", "error_type", "error_message", "last_attempt_time",
                "date_min", "date_max", "row_count", "rows_after_cutoff_received",
                "rows_after_cutoff_discarded",
            ]] = [
                state, attempts, _error_type(RuntimeError(error)) if error else "", error,
                pd.Timestamp.now().isoformat(), combined.trade_date.min() if len(combined) else "",
                combined.trade_date.max() if len(combined) else "", len(combined), received_after,
                received_after,
            ]
            if number % CHECKPOINT_EVERY == 0:
                _atomic_csv(status.reset_index(), status_path)
                counts = status.status.value_counts().to_dict()
                print(f"BaoStock: completed {number} / {len(universe)} {counts}", flush=True)
            if consecutive_failures >= 20:
                _atomic_csv(status.reset_index(), status_path)
                print("BaoStock paused after 20 consecutive failures", flush=True)
                return
    finally:
        bs.logout()
    _atomic_csv(status.reset_index(), status_path)


def _fetch_cninfo(code: str, headers: dict[str, str]) -> tuple[dict, int]:
    response = requests.post(
        "https://webapi.cninfo.com.cn/api/stock/p_stock2215",
        params={"scode": code, "sdate": "1990-01-01", "edate": DATA_CUTOFF.date().isoformat()},
        headers=headers, timeout=30,
    )
    response.raise_for_status()
    return response.json(), response.status_code


def run_cninfo(root: Path) -> None:
    universe = load_universe(root)
    cache = root / CACHE / "cninfo"
    status_path = root / REPORTS / "h7_cninfo_download_status.csv"
    status = _load_status(status_path, universe).set_index("stock_code")
    headers = cninfo_headers()
    consecutive_failures = 0
    for number, code in enumerate(universe.stock_code, 1):
        path = cache / f"{code}.csv"
        old_state = str(status.at[code, "status"]) if "status" in status else ""
        if old_state in {"SUCCESS_WITH_EVENTS", "SUCCESS_NO_EVENTS"} and path.exists():
            continue
        attempts, error, http_status, received_after = 0, "", math.nan, 0
        state = "NETWORK_FAILURE"
        events = pd.DataFrame()
        for attempts in range(1, MAX_ATTEMPTS + 1):
            try:
                payload, http_status = _fetch_cninfo(code, headers)
                events, received_after = normalize_cninfo_payload(payload, code)
                _atomic_csv(events, path)
                state = "SUCCESS_WITH_EVENTS" if len(events) else "SUCCESS_NO_EVENTS"
                error = ""
                consecutive_failures = 0
                break
            except ValueError as exc:
                state, error = "SCHEMA_FAILURE", f"{type(exc).__name__}:{exc}"
                break
            except Exception as exc:
                error = f"{type(exc).__name__}:{exc}"
                if attempts < MAX_ATTEMPTS:
                    time.sleep(attempts)
                    headers = cninfo_headers()
        if state in {"NETWORK_FAILURE", "SCHEMA_FAILURE"}:
            consecutive_failures += 1
        status.loc[code, [
            "status", "attempt_count", "error_type", "error_message", "last_attempt_time",
            "http_status", "event_count", "rows_after_cutoff_received",
            "rows_after_cutoff_discarded",
        ]] = [
            state, attempts, _error_type(RuntimeError(error)) if error else "", error,
            pd.Timestamp.now().isoformat(), http_status, len(events), received_after, received_after,
        ]
        if number % CHECKPOINT_EVERY == 0:
            _atomic_csv(status.reset_index(), status_path)
            counts = status.status.value_counts().to_dict()
            print(f"CNINFO: completed {number} / {len(universe)} {counts}", flush=True)
            headers = cninfo_headers()
        if consecutive_failures >= 20:
            _atomic_csv(status.reset_index(), status_path)
            print("CNINFO paused after 20 consecutive failures", flush=True)
            return
    _atomic_csv(status.reset_index(), status_path)


def _load_local_validation(root: Path, code: str) -> pd.DataFrame:
    path = root / "data/cache/price" / f"{code}.csv"
    if not path.exists():
        return pd.DataFrame(columns=["trade_date", "local_implied_total_shares", "local_implied_circulating_shares"])
    raw = pd.read_csv(path, usecols=lambda x: x in {"date", "trade_date", "close", "total_market_cap", "circulating_market_cap"})
    date_column = "trade_date" if "trade_date" in raw else "date"
    close = pd.to_numeric(raw.get("close"), errors="coerce")
    out = pd.DataFrame({"trade_date": pd.to_datetime(raw[date_column], errors="coerce")})
    out["local_implied_total_shares"] = pd.to_numeric(raw.get("total_market_cap"), errors="coerce") / close
    out["local_implied_circulating_shares"] = pd.to_numeric(raw.get("circulating_market_cap"), errors="coerce") / close
    return out.loc[out.trade_date.le(DATA_CUTOFF)].drop_duplicates("trade_date", keep="last")


def build_outputs(root: Path) -> None:
    universe = load_universe(root)
    report_dir = root / REPORTS
    report_dir.mkdir(parents=True, exist_ok=True)
    panel_path = root / PANEL
    panel_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = panel_path.with_suffix(".csv.tmp")
    if temporary.exists():
        temporary.unlink()
    exceptions: list[dict] = []
    coverage: list[dict] = []
    wrote_header = False
    for number, code in enumerate(universe.stock_code, 1):
        bao_path = root / CACHE / "baostock" / f"{code}.csv"
        cn_path = root / CACHE / "cninfo" / f"{code}.csv"
        if not bao_path.exists():
            exceptions.append(_exception(code, "baostock", "BAOSTOCK_DOWNLOAD_FAILURE", "", "", "canonical cache absent", True, True))
            coverage.append({"stock_code": code, "daily_rows": 0, "primary_valid_rows": 0, "secondary_valid_rows": 0, "valid_200d_turnover_days": 0})
            continue
        bao = pd.read_csv(bao_path, dtype={"stock_code": str})
        bao["trade_date"] = pd.to_datetime(bao.trade_date)
        validate_baostock(bao, code)
        if cn_path.exists():
            events = pd.read_csv(cn_path, dtype={"stock_code": str})
            for column in ("change_date", "announcement_date", "information_available_date"):
                events[column] = pd.to_datetime(events[column], errors="coerce")
            events["event_date_incomplete"] = events.event_date_incomplete.astype(str).str.lower().eq("true")
        else:
            events = normalize_cninfo_payload({}, code)[0]
            exceptions.append(_exception(code, "cninfo", "CNINFO_NETWORK_FAILURE", "", "", "canonical cache absent", True, False))
        lineage = point_in_time_shares(events, bao.trade_date)
        daily = bao.merge(lineage, on="trade_date", how="left", validate="one_to_one")
        local = _load_local_validation(root, code)
        daily = daily.merge(local, on="trade_date", how="left", validate="one_to_one")
        valid_denominator = pd.to_numeric(daily.total_shares, errors="coerce").gt(0)
        valid_volume = pd.to_numeric(daily.volume_shares, errors="coerce").ge(0)
        daily["total_share_turnover"] = np.where(valid_denominator & valid_volume, daily.volume_shares / daily.total_shares, np.nan)
        daily["primary_turnover_valid"] = daily.total_share_turnover.notna()
        daily["primary_invalid_reason"] = np.where(
            valid_denominator, np.where(valid_volume, "", "INVALID_VOLUME"), "TOTAL_SHARES_UNKNOWN"
        )
        positive_turn = daily.baostock_circulating_turnover.gt(0)
        positive_volume = daily.volume_shares.gt(0)
        daily["baostock_implied_circulating_shares"] = np.where(
            positive_turn & positive_volume,
            daily.volume_shares / daily.baostock_circulating_turnover,
            np.nan,
        )
        daily["cninfo_total_shares"] = daily.total_shares
        daily["cninfo_circulating_shares"] = daily.circulating_shares
        daily["share_information_available_date"] = daily.information_available_date
        daily["data_cutoff"] = DATA_CUTOFF.date().isoformat()
        panel_columns = [
            "stock_code", "trade_date", "volume_shares", "amount_cny", "trading_status", "is_st",
            "cninfo_total_shares", "cninfo_circulating_shares", "share_information_available_date",
            "total_share_turnover", "baostock_circulating_turnover", "primary_turnover_valid",
            "primary_invalid_reason", "local_implied_total_shares", "local_implied_circulating_shares",
            "baostock_implied_circulating_shares", "data_cutoff",
        ]
        daily[panel_columns].to_csv(temporary, mode="a", header=not wrote_header, index=False, encoding="utf-8-sig")
        wrote_header = True
        exact = exact_prior_200_valid(daily.total_share_turnover)
        primary_count = int(daily.primary_turnover_valid.sum())
        secondary_count = int(daily.baostock_circulating_turnover.notna().sum())
        coverage.append({
            "stock_code": code, "daily_rows": len(daily), "primary_valid_rows": primary_count,
            "primary_coverage": primary_count / len(daily), "secondary_valid_rows": secondary_count,
            "secondary_coverage": secondary_count / len(daily),
            "first_valid_200d_date": daily.loc[exact, "trade_date"].min(),
            "valid_200d_turnover_days": int(exact.sum()),
        })
        if events.empty:
            exceptions.append(_exception(code, "cninfo", "CNINFO_NO_HISTORY", daily.trade_date.min(), daily.trade_date.max(), "no historical share events", True, False))
        elif daily.total_shares.isna().any():
            missing = daily.loc[daily.total_shares.isna(), "trade_date"]
            exceptions.append(_exception(code, "cninfo", "NO_OPENING_TOTAL_SHARES", missing.min(), missing.max(), "pre-first-information interval remains unknown", True, False))
        incomplete = events.loc[events.event_date_incomplete]
        if len(incomplete):
            exceptions.append(_exception(code, "cninfo", "CNINFO_INCOMPLETE_EVENT_DATE", incomplete.change_date.min(), incomplete.change_date.max(), f"event_count={len(incomplete)}", True, False))
        total_error = ((daily.local_implied_total_shares - daily.cninfo_total_shares).abs() / daily.cninfo_total_shares).replace([np.inf, -np.inf], np.nan)
        median_error, p95_error = total_error.median(), total_error.quantile(.95)
        if (pd.notna(median_error) and median_error > .10) or (pd.notna(p95_error) and p95_error > .20):
            exceptions.append(_exception(code, "validation", "LARGE_VALIDATION_DISCREPANCY", daily.trade_date.min(), daily.trade_date.max(), f"median={median_error:.6g};p95={p95_error:.6g}", False, False))
        coverage[-1]["local_total_vs_cninfo_median_error"] = median_error
        coverage[-1]["local_total_vs_cninfo_p95_error"] = p95_error
        if number % CHECKPOINT_EVERY == 0:
            print(f"Panel: completed {number} / {len(universe)}", flush=True)
    if wrote_header:
        temporary.replace(panel_path)
    coverage_frame = pd.DataFrame(coverage)
    exceptions_frame = pd.DataFrame(exceptions)
    _atomic_csv(coverage_frame, report_dir / "h7_turnover_coverage_by_stock.csv")
    _atomic_csv(exceptions_frame, report_dir / "h7_turnover_exception_queue.csv")
    thresholds = pd.DataFrame({
        "minimum_valid_days": [500, 750, 1000, 1250],
        "stock_count": [int(coverage_frame.valid_200d_turnover_days.ge(x).sum()) for x in (500, 750, 1000, 1250)],
        "recommended": [False] * 4,
    })
    _atomic_csv(thresholds, report_dir / "h7_turnover_history_thresholds.csv")
    _write_report(root, universe, coverage_frame, exceptions_frame, thresholds)


def _exception(code: str, source: str, kind: str, first: object, last: object, details: str, primary: bool, secondary: bool) -> dict:
    return {
        "stock_code": code, "source": source, "exception_type": kind,
        "first_problem_date": first, "last_problem_date": last, "details": details,
        "primary_turnover_affected": primary, "secondary_turnover_affected": secondary,
        "review_required": True,
    }


def _status_counts(path: Path) -> dict[str, int]:
    if not path.exists():
        return {}
    return pd.read_csv(path).status.value_counts().to_dict()


def _write_report(root: Path, universe: pd.DataFrame, coverage: pd.DataFrame, exceptions: pd.DataFrame, thresholds: pd.DataFrame) -> None:
    bao = _status_counts(root / REPORTS / "h7_baostock_download_status.csv")
    cn = _status_counts(root / REPORTS / "h7_cninfo_download_status.csv")
    primary = coverage.loc[coverage.primary_valid_rows.gt(0)]
    secondary = coverage.loc[coverage.secondary_valid_rows.gt(0)]
    size = pd.read_csv(root / "reports/hypothesis_7/h7_history_sufficiency.csv", dtype={"stock_code": str})
    size = size.loc[size.row_type.eq("stock"), ["stock_code", "latest_total_market_cap"]]
    size["stock_code"] = size.stock_code.map(code6)
    relation = coverage.merge(size, on="stock_code", how="left")
    relation["log_size"] = np.log(pd.to_numeric(relation.latest_total_market_cap, errors="coerce"))
    rho = relation[["valid_200d_turnover_days", "log_size"]].corr(method="spearman").iloc[0, 1]
    exception_stocks = exceptions.stock_code.nunique() if len(exceptions) else 0
    primary_share = len(primary) / len(universe)
    status = "H7_TURNOVER_DATA_READY" if primary_share >= .99 and exception_stocks / len(universe) <= .01 else (
        "H7_TURNOVER_DATA_READY_WITH_EXCEPTIONS" if primary_share >= .90 else "H7_TURNOVER_DATA_INCOMPLETE"
    )
    after = 0
    for path in (root / REPORTS / "h7_baostock_download_status.csv", root / REPORTS / "h7_cninfo_download_status.csv"):
        if path.exists():
            values = pd.to_numeric(pd.read_csv(path).get("rows_after_cutoff_discarded"), errors="coerce")
            after += int(values.fillna(0).sum())
    top = exceptions.exception_type.value_counts().head(10).to_dict() if len(exceptions) else {}
    text = f"""# H7 Full-Market Turnover Data Acquisition

## Data-layer result

`{status}`. This is a cache-first data result, not an H7 hypothesis result.

```text
data_cutoff=2026-08-20
broader_a_stock_count={len(universe)}
baostock_status={json.dumps(bao, ensure_ascii=False)}
cninfo_status={json.dumps(cn, ensure_ascii=False)}
primary_total_share_turnover_stock_count={len(primary)}
primary_total_share_turnover_median_coverage={primary.primary_coverage.median() if len(primary) else math.nan}
primary_total_share_turnover_p10_coverage={primary.primary_coverage.quantile(.10) if len(primary) else math.nan}
secondary_baostock_turn_stock_count={len(secondary)}
secondary_baostock_turn_median_coverage={secondary.secondary_coverage.median() if len(secondary) else math.nan}
exception_stock_count={exception_stocks}
exception_rate={exception_stocks / len(universe)}
top_exception_types={json.dumps(top, ensure_ascii=False)}
history_length_size_spearman={rho}
rows_after_2026_08_20_received={after}
rows_after_2026_08_20_discarded={after}
C2_estimated=false
volume_return_regression_run=false
future_performance_accessed=false
H5_run=false
H6_run=false
MCTS_run=false
Phase_B_run=false
H7_turnover_data_status={status}
```

## Contract and limitations

BaoStock volume is stored in shares, amount in CNY, and vendor turnover percent is converted to a decimal secondary measure. Primary turnover is volume divided by CNINFO point-in-time total shares. CNINFO events become usable only on `max(change_date, announcement_date)` and are applied forward; no later event is backfilled into an earlier date. HTTP 200 with empty records is retained as `SUCCESS_NO_EVENTS`. Local cap/close and BaoStock-implied circulating shares are validation only.

The exception queue records source failures, empty histories, incomplete event dates, unknown opening levels, and large validation discrepancies. Validation discrepancies do not invalidate CNINFO automatically. Exact 200-day eligibility requires the current day plus all 200 preceding observations to be valid, without fill; the history thresholds remain for human selection.

{thresholds.to_markdown(index=False)}

Recommended next step: review the exception queue and choose the minimum valid-history threshold before any H7 regression. No C2 or future-performance analysis was run.
"""
    (root / REPORTS / "h7_turnover_data_acquisition_report.md").write_text(text, encoding="utf-8")


def show_status(root: Path) -> None:
    print(f"broader_a_stock_count={len(load_universe(root))}")
    print(f"BAOSTOCK={_status_counts(root / REPORTS / 'h7_baostock_download_status.csv')}")
    print(f"CNINFO={_status_counts(root / REPORTS / 'h7_cninfo_download_status.csv')}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["baostock", "cninfo", "build", "all", "status"])
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.project_root.resolve()
    if args.command in {"baostock", "all"}:
        run_baostock(root)
    if args.command in {"cninfo", "all"}:
        run_cninfo(root)
    if args.command in {"build", "all"}:
        build_outputs(root)
    if args.command == "status":
        show_status(root)


if __name__ == "__main__":
    main()
