# ruff: noqa: E501
"""Signal/data-only feasibility audit for a paper-like abnormal turnover ratio.

This module deliberately does not import or construct future returns.  Its only
outputs are source inventories, coverage diagnostics, bounded announcement
metadata probes, and measurement-contract feasibility notes.
"""

from __future__ import annotations

import argparse
import json
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

START_DATE = "2020-01-01"
END_DATE = "2026-08-20"
MAX_PROBE_STOCKS = 30
EVENT_WINDOW_CONTRACT = "UNRESOLVED_FROM_TEXT"
EVENT_CATEGORIES = {
    "earnings": ("年报", "半年报", "一季报", "三季报", "业绩快报"),
    "M&A": ("收购", "并购", "重组", "重大资产"),
    "ownership_change": ("控制权", "实际控制人", "权益变动", "股权变动"),
    "repurchase": ("回购",),
    "major_capital_investment": ("重大投资", "对外投资", "投资建设", "项目投资"),
    "large_shareholder_trade": ("增持", "减持", "大股东", "持股变动"),
    "debt_issuance": ("公司债", "可转债", "债券发行", "发行债券"),
    "equity_issuance": ("增发", "配股", "非公开发行", "向特定对象发行"),
    "managerial_turnover": (
        "辞任",
        "辞职",
        "聘任",
        "任命",
        "离任",
        "董事长",
        "总经理",
        "财务负责人",
        "董事会秘书",
    ),
    "cash_dividend_announcement": ("利润分配", "分红", "现金红利", "权益分派"),
}


def code6(value: Any) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[-6:].zfill(6)


def board_from_code(code: str) -> str:
    if code.startswith(("300", "301")):
        return "CHINEXT"
    if code.startswith("688"):
        return "STAR"
    if code.startswith(("600", "601", "603", "605")):
        return "SH_MAIN"
    return "SZ_MAIN"


def classify_title(title: str) -> list[str]:
    clean = str(title).replace("<em>", "").replace("</em>", "")
    return [name for name, words in EVENT_CATEGORIES.items() if any(w in clean for w in words)]


def select_probe_sample(root: Path) -> pd.DataFrame:
    availability = pd.read_csv(
        root / "reports/hypothesis_7/final_contract/h7_regression_row_availability_by_stock.csv",
        dtype={"stock_code": str},
        usecols=["stock_code", "board", "size_quartile"],
    )
    availability["stock_code"] = availability["stock_code"].map(code6)
    availability = availability.dropna(subset=["size_quartile"]).copy()
    availability = availability.sort_values(["board", "size_quartile", "stock_code"])

    chosen: list[str] = []
    # Guarantee board x size-quartile coverage before adding industry-labelled names.
    for _, group in availability.groupby(["board", "size_quartile"], sort=True):
        chosen.append(group.iloc[0]["stock_code"])

    review_path = root / "theme_business_review_completed_001_200.csv"
    review = pd.read_csv(review_path, dtype={"code": str})
    review["stock_code"] = review["code"].map(code6)
    review = review.dropna(subset=["sw_industry"]).drop_duplicates("stock_code")
    candidates = availability.merge(
        review[["stock_code", "name", "sw_industry"]], on="stock_code", how="left"
    )
    labelled = candidates.dropna(subset=["sw_industry"]).sort_values(["sw_industry", "stock_code"])
    seen_industries: set[str] = set()
    for row in labelled.itertuples(index=False):
        if len(chosen) >= MAX_PROBE_STOCKS:
            break
        if row.sw_industry not in seen_industries and row.stock_code not in chosen:
            chosen.append(row.stock_code)
            seen_industries.add(row.sw_industry)

    for code in availability["stock_code"]:
        if len(chosen) >= MAX_PROBE_STOCKS:
            break
        if code not in chosen:
            chosen.append(code)

    sample = availability[availability["stock_code"].isin(chosen[:MAX_PROBE_STOCKS])].copy()
    sample = sample.merge(
        review[["stock_code", "name", "sw_industry"]], on="stock_code", how="left"
    )
    sample["selection_rule"] = "board_size_strata_then_distinct_local_industry"
    return sample.sort_values("stock_code").reset_index(drop=True)


def aggregate_price_cache(root: Path) -> tuple[pd.DataFrame, dict[str, Any]]:
    files = sorted((root / "data/cache/price").glob("*.csv"))
    frames: list[pd.DataFrame] = []
    summaries: list[pd.DataFrame] = []
    total_rows = 0
    valid_stocks: set[str] = set()
    for index, path in enumerate(files, start=1):
        try:
            frame = pd.read_csv(
                path,
                usecols=["date", "amount", "total_market_cap", "circulating_market_cap"],
                low_memory=False,
            )
        except (ValueError, pd.errors.EmptyDataError):
            continue
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        for column in ("amount", "total_market_cap", "circulating_market_cap"):
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
        frame = frame[(frame["date"] >= START_DATE) & (frame["date"] <= END_DATE)]
        total_rows += len(frame)
        if frame["amount"].notna().any():
            valid_stocks.add(code6(path.stem))
        frames.append(frame)
        if len(frames) >= 250 or index == len(files):
            batch = pd.concat(frames, ignore_index=True)
            valid = batch.loc[batch["date"].notna()].copy()
            for column in ("amount", "total_market_cap", "circulating_market_cap"):
                valid[f"{column}_valid"] = np.isfinite(valid[column]) & (valid[column] > 0)
                valid[f"{column}_value"] = valid[column].where(valid[f"{column}_valid"], 0.0)
            summary = valid.groupby("date", as_index=False).agg(
                sum_amount=("amount_value", "sum"),
                amount_count=("amount_valid", "sum"),
                sum_total_cap=("total_market_cap_value", "sum"),
                total_cap_count=("total_market_cap_valid", "sum"),
                sum_circulating_cap=("circulating_market_cap_value", "sum"),
                circulating_cap_count=("circulating_market_cap_valid", "sum"),
            )
            summaries.append(summary)
            frames = []
    daily = pd.concat(summaries, ignore_index=True).groupby("date", as_index=False).sum()
    daily["dmtr_total_cap"] = daily["sum_amount"] / daily["sum_total_cap"]
    daily["dmtr_circulating_cap"] = daily["sum_amount"] / daily["sum_circulating_cap"]
    meta = {"file_count": len(files), "stock_count": len(valid_stocks), "row_count": total_rows}
    return daily.sort_values("date"), meta


def turnover_window_availability(root: Path) -> dict[str, Any]:
    files = sorted((root / "data/cache/h7_turnover/baostock").glob("*.csv"))
    estimation_rows: list[int] = []
    candidate_count = 0
    failures = 0
    stocks_with_candidate = 0
    date_min: pd.Timestamp | None = None
    date_max: pd.Timestamp | None = None
    total_rows = 0
    for path in files:
        try:
            frame = pd.read_csv(
                path,
                usecols=["trade_date", "baostock_circulating_turnover", "trading_status"],
                low_memory=False,
            )
        except (ValueError, pd.errors.EmptyDataError):
            continue
        frame["trade_date"] = pd.to_datetime(frame["trade_date"], errors="coerce")
        turn = pd.to_numeric(frame["baostock_circulating_turnover"], errors="coerce")
        status = pd.to_numeric(frame["trading_status"], errors="coerce")
        valid = frame[frame["trade_date"].notna() & np.isfinite(turn) & (turn >= 0) & (status == 1)]
        total_rows += len(frame)
        if valid.empty:
            continue
        local_min = valid["trade_date"].min()
        local_max = valid["trade_date"].max()
        date_min = local_min if date_min is None else min(date_min, local_min)
        date_max = local_max if date_max is None else max(date_max, local_max)
        monthly = valid.groupby(valid["trade_date"].dt.to_period("M")).size().sort_index()
        stock_candidates = 0
        for measurement_month in monthly.index:
            history = [measurement_month - offset for offset in range(1, 8)]
            if all(month in monthly.index and monthly[month] > 0 for month in history):
                candidate_count += 1
                stock_candidates += 1
                estimation_rows.append(int(sum(monthly[month] for month in history)))
            else:
                failures += 1
        stocks_with_candidate += int(stock_candidates > 0)
    values = np.asarray(estimation_rows, dtype=float)
    return {
        "file_count": len(files),
        "row_count": total_rows,
        "date_start": "" if date_min is None else date_min.date().isoformat(),
        "date_end": "" if date_max is None else date_max.date().isoformat(),
        "monthly_candidate_count": candidate_count,
        "stocks_with_candidate": stocks_with_candidate,
        "months_failing_history_requirement": failures,
        "median_estimation_daily_rows": float(np.median(values)) if values.size else np.nan,
        "p10_estimation_daily_rows": float(np.quantile(values, 0.1)) if values.size else np.nan,
        "p90_estimation_daily_rows": float(np.quantile(values, 0.9)) if values.size else np.nan,
    }


def profile_listing_dates(root: Path) -> dict[str, Any]:
    files = sorted((root / "data/cache/h7_turnover/cninfo").glob("*.csv"))
    stocks = 0
    dates: list[pd.Timestamp] = []
    for path in files:
        try:
            frame = pd.read_csv(path, usecols=["change_date", "change_reason"], low_memory=False)
        except (ValueError, pd.errors.EmptyDataError):
            continue
        rows = frame[frame["change_reason"].astype(str).str.contains("A股上市", na=False)]
        parsed = pd.to_datetime(rows["change_date"], errors="coerce").dropna()
        if not parsed.empty:
            stocks += 1
            dates.append(parsed.min())
    return {
        "stock_count": stocks,
        "date_start": min(dates).date().isoformat() if dates else "",
        "date_end": max(dates).date().isoformat() if dates else "",
        "universe_count": len(files),
    }


def profile_profit_notices(root: Path) -> dict[str, Any]:
    files = sorted((root / "data/cache/profit").glob("*.csv"))
    stocks = 0
    rows = 0
    dates: list[pd.Timestamp] = []
    report_types: Counter[str] = Counter()
    formats: dict[str, dict[str, int]] = {}
    for path in files:
        try:
            frame = pd.read_csv(
                path,
                usecols=lambda column: column in {"NOTICE_DATE", "REPORT_TYPE", "announce_date"},
                low_memory=False,
            )
        except (ValueError, pd.errors.EmptyDataError):
            continue
        field = "NOTICE_DATE" if "NOTICE_DATE" in frame else "announce_date"
        if field not in frame:
            continue
        parsed = pd.to_datetime(frame[field], errors="coerce")
        valid = parsed.notna()
        window = parsed.between(START_DATE, END_DATE)
        stats = formats.setdefault(field, dict(files=0, valid_stocks=0, valid_rows=0, window_stocks=0, window_rows=0))
        stats["files"] += 1
        stats["valid_stocks"] += int(valid.any())
        stats["valid_rows"] += int(valid.sum())
        stats["window_stocks"] += int(window.any())
        stats["window_rows"] += int(window.sum())
        if valid.any():
            stocks += 1
            rows += int(valid.sum())
            dates.extend([parsed[valid].min(), parsed[valid].max()])
            if "REPORT_TYPE" in frame:
                report_types.update(frame.loc[valid, "REPORT_TYPE"].astype(str))
    return {
        "stock_count": stocks,
        "row_count": rows,
        "date_start": min(dates).date().isoformat() if dates else "",
        "date_end": max(dates).date().isoformat() if dates else "",
        "report_types": "|".join(sorted(report_types)),
        "field_profiles": formats,
    }


def _cninfo_session() -> tuple[requests.Session, dict[str, str]]:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": "http://www.cninfo.com.cn/"})
    response = session.get("http://www.cninfo.com.cn/new/data/szse_stock.json", timeout=30)
    response.raise_for_status()
    mapping = {item["code"]: item["orgId"] for item in response.json()["stockList"]}
    return session, mapping


def _cninfo_query(
    session: requests.Session,
    org_map: dict[str, str],
    code: str,
    start: str,
    end: str,
    *,
    keyword: str = "",
    category: str = "",
) -> dict[str, Any]:
    payload = {
        "pageNum": "1",
        "pageSize": "30",
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{code},{org_map[code]}",
        "searchkey": keyword,
        "secid": "",
        "category": category,
        "trade": "",
        "seDate": f"{start}~{end}",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    response = session.post(
        "http://www.cninfo.com.cn/new/hisAnnouncement/query", data=payload, timeout=30
    )
    response.raise_for_status()
    return response.json()


def run_announcement_probe(sample: pd.DataFrame, checkpoint: Path | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    completed: set[tuple[str, int]] = set()
    if checkpoint is not None and checkpoint.exists():
        prior = pd.read_csv(checkpoint, dtype={"stock_code": str}, keep_default_na=False)
        rows = prior.to_dict("records")
        summaries = prior[
            (prior["row_type"] == "stock_year_summary")
            & prior["status"].isin(["SUCCESS", "FAILED"])
        ]
        completed = {
            (code6(row.stock_code), int(float(row.year))) for row in summaries.itertuples(index=False)
        }
    # Failed requests are completed observations of source stability, not retry work.
    expected = {(code6(code), year) for code in sample.stock_code for year in range(2020, 2027)}
    parameters_done = {
        row.get("probe_type") for row in rows if row.get("row_type") == "parameter_test"
    }
    if expected <= completed and {"keyword", "category"} <= parameters_done:
        return pd.DataFrame(rows)
    try:
        session, org_map = _cninfo_session()
    except Exception as exc:  # network probe failure remains evidence, not a crash
        for item in sample.itertuples(index=False):
            rows.append(
                {
                    "row_type": "stock_probe_failure",
                    "stock_code": item.stock_code,
                    "board": item.board,
                    "size_quartile": item.size_quartile,
                    "industry": item.sw_industry,
                    "year": "",
                    "probe_type": "unfiltered_stock_year_metadata",
                    "query_value": "",
                    "status": "FAILED",
                    "total_announcements": "",
                    "sampled_announcements": 0,
                    "announcement_date": "",
                    "title": "",
                    "event_candidates": "",
                    "announcement_link": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        return pd.DataFrame(rows)

    for item in sample.itertuples(index=False):
        for year in range(2020, 2027):
            if (item.stock_code, year) in completed:
                continue
            start = f"{year}-01-01"
            end = min(f"{year}-12-31", END_DATE)
            try:
                if item.stock_code not in org_map:
                    raise ValueError(f"CNINFO_org_mapping_missing:{item.stock_code}")
                result = _cninfo_query(session, org_map, item.stock_code, start, end)
                announcements = result.get("announcements") or []
                rows.append(
                    {
                        "row_type": "stock_year_summary",
                        "stock_code": item.stock_code,
                        "board": item.board,
                        "size_quartile": item.size_quartile,
                        "industry": item.sw_industry,
                        "year": year,
                        "probe_type": "unfiltered_stock_year_metadata",
                        "query_value": "",
                        "status": "SUCCESS",
                        "total_announcements": int(result.get("totalAnnouncement") or 0),
                        "sampled_announcements": len(announcements),
                        "announcement_date": "",
                        "title": "",
                        "event_candidates": "",
                        "announcement_link": "",
                        "error": "",
                    }
                )
                for announcement in announcements:
                    stamp = pd.to_datetime(
                        announcement.get("announcementTime"), unit="ms", utc=True, errors="coerce"
                    )
                    if pd.notna(stamp):
                        stamp = stamp.tz_convert("Asia/Shanghai").tz_localize(None)
                    title = str(announcement.get("announcementTitle") or "")
                    rows.append(
                        {
                            "row_type": "announcement_sample",
                            "stock_code": item.stock_code,
                            "board": item.board,
                            "size_quartile": item.size_quartile,
                            "industry": item.sw_industry,
                            "year": year,
                            "probe_type": "unfiltered_stock_year_metadata",
                            "query_value": "",
                            "status": "SUCCESS",
                            "total_announcements": "",
                            "sampled_announcements": "",
                            "announcement_date": "" if pd.isna(stamp) else stamp.isoformat(),
                            "title": title.replace("<em>", "").replace("</em>", ""),
                            "event_candidates": "|".join(classify_title(title)),
                            "announcement_link": "http://static.cninfo.com.cn/"
                            + str(announcement.get("adjunctUrl") or ""),
                            "error": "",
                        }
                    )
            except Exception as exc:
                rows.append(
                    {
                        "row_type": "stock_year_summary",
                        "stock_code": item.stock_code,
                        "board": item.board,
                        "size_quartile": item.size_quartile,
                        "industry": item.sw_industry,
                        "year": year,
                        "probe_type": "unfiltered_stock_year_metadata",
                        "query_value": "",
                        "status": "FAILED",
                        "total_announcements": "",
                        "sampled_announcements": 0,
                        "announcement_date": "",
                        "title": "",
                        "event_candidates": "",
                        "announcement_link": "",
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )
            if checkpoint is not None:
                save_probe_checkpoint(rows, checkpoint)
            time.sleep(0.05)

    # Explicitly verify that both keyword and category parameters are accepted.
    parameter_tests = [
        ("keyword", "回购", "", ""),
        ("category", "年报", "", "category_ndbg_szsh"),
    ]
    first = sample.iloc[0]
    for probe_type, value, keyword, category in parameter_tests:
        if any(
            row.get("row_type") == "parameter_test"
            and row.get("probe_type") == probe_type
            for row in rows
        ):
            continue
        try:
            result = _cninfo_query(
                session,
                org_map,
                first["stock_code"],
                START_DATE,
                END_DATE,
                keyword=value if probe_type == "keyword" else keyword,
                category=category,
            )
            rows.append(
                {
                    "row_type": "parameter_test",
                    "stock_code": first["stock_code"],
                    "board": first["board"],
                    "size_quartile": first["size_quartile"],
                    "industry": first["sw_industry"],
                    "year": "",
                    "probe_type": probe_type,
                    "query_value": value,
                    "status": "SUCCESS",
                    "total_announcements": int(result.get("totalAnnouncement") or 0),
                    "sampled_announcements": len(result.get("announcements") or []),
                    "announcement_date": "",
                    "title": "",
                    "event_candidates": "",
                    "announcement_link": "",
                    "error": "",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "row_type": "parameter_test",
                    "stock_code": first["stock_code"],
                    "board": first["board"],
                    "size_quartile": first["size_quartile"],
                    "industry": first["sw_industry"],
                    "year": "",
                    "probe_type": probe_type,
                    "query_value": value,
                    "status": "FAILED",
                    "total_announcements": "",
                    "sampled_announcements": 0,
                    "announcement_date": "",
                    "title": "",
                    "event_candidates": "",
                    "announcement_link": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
        if checkpoint is not None:
            save_probe_checkpoint(rows, checkpoint)
    session.close()
    return pd.DataFrame(rows)


def save_probe_checkpoint(rows: list[dict[str, Any]], path: Path) -> None:
    temporary = path.with_suffix(".tmp")
    pd.DataFrame(rows).to_csv(temporary, index=False, encoding="utf-8-sig")
    temporary.replace(path)


def probe_construct_sources(cutoff: str) -> list[dict[str, Any]]:
    import akshare as ak

    rows: list[dict[str, Any]] = []
    probes = [
        ("monthly_new_investor_accounts", "stock_account_statistics_em", {}),
        ("analyst_report_count", "stock_research_report_em", {"symbol": "000001"}),
        ("fund_holding_proxy", "stock_fund_stock_holder", {"symbol": "000001"}),
    ]
    date_columns = {
        "monthly_new_investor_accounts": "数据日期",
        "analyst_report_count": "日期",
        "fund_holding_proxy": "截止日期",
    }
    for variable, endpoint, kwargs in probes:
        try:
            frame = getattr(ak, endpoint)(**kwargs)
            date_column = date_columns[variable]
            dates = pd.to_datetime(frame.get(date_column), errors="coerce")
            dates = dates[dates <= pd.Timestamp(cutoff)]
            rows.append(
                {
                    "variable": variable,
                    "source": endpoint,
                    "status": "SUCCESS",
                    "rows_through_cutoff": int(dates.notna().sum()),
                    "date_start": dates.min().date().isoformat() if dates.notna().any() else "",
                    "date_end": dates.max().date().isoformat() if dates.notna().any() else "",
                    "fields": "|".join(map(str, frame.columns)),
                    "error": "",
                }
            )
        except Exception as exc:
            rows.append(
                {
                    "variable": variable,
                    "source": endpoint,
                    "status": "FAILED",
                    "rows_through_cutoff": 0,
                    "date_start": "",
                    "date_end": "",
                    "fields": "",
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return rows


def inventory_rows(
    root: Path,
    price_meta: dict[str, Any],
    turnover_meta: dict[str, Any],
    listing: dict[str, Any],
    profit: dict[str, Any],
) -> list[dict[str, Any]]:
    def row(
        component: str,
        available: bool,
        path: str,
        field: str,
        start: str,
        end: str,
        stocks: int,
        count: int,
        match: str,
        limitation: str,
    ) -> dict[str, Any]:
        return {
            "paper_component": component,
            "local_available": available,
            "local_path": path,
            "local_field": field,
            "date_start": start,
            "date_end": end,
            "stock_count": stocks,
            "row_count": count,
            "definition_match": match,
            "known_limitation": limitation,
        }

    return [
        row(
            "A_daily_individual_turnover",
            True,
            "data/cache/h7_turnover/baostock/*.csv",
            "baostock_circulating_turnover",
            turnover_meta["date_start"],
            turnover_meta["date_end"],
            turnover_meta["file_count"],
            turnover_meta["row_count"],
            "CLOSE_ECONOMIC_MATCH",
            "Circulating-share denominator; paper denominator semantics not fully verified.",
        ),
        row(
            "B_daily_volume",
            True,
            "data/cache/h7_turnover/baostock/*.csv",
            "volume_shares",
            turnover_meta["date_start"],
            turnover_meta["date_end"],
            turnover_meta["file_count"],
            turnover_meta["row_count"],
            "AVAILABLE",
            "Trading-status filtering remains necessary.",
        ),
        row(
            "C_daily_amount",
            True,
            "data/cache/price/*.csv",
            "amount",
            START_DATE,
            END_DATE,
            price_meta["stock_count"],
            price_meta["row_count"],
            "AVAILABLE_UNIT_INFERRED",
            "Currency unit is inferred as CNY, not source-certified in cache.",
        ),
        row(
            "D_circulating_shares",
            True,
            "data/cache/h7_turnover/cninfo/*.csv",
            "circulating_shares; information_available_date",
            START_DATE,
            END_DATE,
            5180,
            0,
            "PARTIAL",
            "35 stocks lack an opening total-share level; free-float semantics are not established.",
        ),
        row(
            "E_total_shares",
            True,
            "data/cache/h7_turnover/cninfo/*.csv",
            "total_shares; information_available_date",
            START_DATE,
            END_DATE,
            5180,
            0,
            "PARTIAL",
            "Current-universe history and incomplete announcement dates remain.",
        ),
        row(
            "F_daily_market_cap",
            True,
            "data/cache/price/*.csv",
            "total_market_cap; circulating_market_cap",
            START_DATE,
            END_DATE,
            price_meta["file_count"],
            price_meta["row_count"],
            "HISTORICAL_DATED_NOT_VINTAGE_AUDITED",
            "Vendor cap lineage and historical universe membership are not point-in-time audited.",
        ),
        row(
            "G_listing_date",
            listing["stock_count"] > 0,
            "data/cache/h7_turnover/cninfo/*.csv",
            "change_reason=A股上市; change_date",
            listing["date_start"],
            listing["date_end"],
            listing["stock_count"],
            listing["stock_count"],
            "PARTIAL",
            f"Missing explicit listing record for {listing['universe_count'] - listing['stock_count']} current-universe stocks.",
        ),
        row(
            "H_trading_status",
            True,
            "data/cache/h7_turnover/baostock/*.csv",
            "trading_status",
            turnover_meta["date_start"],
            turnover_meta["date_end"],
            turnover_meta["file_count"],
            turnover_meta["row_count"],
            "CLOSE_MATCH",
            "BaoStock vendor status.",
        ),
        row(
            "I_board",
            True,
            "reports/hypothesis_7/h7_sample_membership_v1.csv",
            "board",
            START_DATE,
            END_DATE,
            5195,
            5195,
            "STATIC_CODE_DERIVED",
            "Current board label, not point-in-time board history.",
        ),
        row(
            "J_ST_status",
            True,
            "data/cache/h7_turnover/baostock/*.csv",
            "is_st",
            turnover_meta["date_start"],
            turnover_meta["date_end"],
            turnover_meta["file_count"],
            turnover_meta["row_count"],
            "CLOSE_MATCH",
            "Vendor daily flag.",
        ),
        row(
            "K_announcements",
            False,
            "none",
            "none",
            "",
            "",
            0,
            0,
            "NOT_LOCAL",
            "H7 CNINFO files are share-lineage events, not a general announcement corpus.",
        ),
        row(
            "L_corporate_actions",
            True,
            "data/cache/h8_corporate_actions/baostock/*.csv",
            "dividOperateDate",
            START_DATE,
            "2026-05-12",
            2790,
            0,
            "IMPLEMENTATION_DATE_ONLY",
            "Cannot substitute for dividend announcement date.",
        ),
        row(
            "M_financial_report_disclosure_dates",
            True,
            "data/cache/profit/*.csv",
            "NOTICE_DATE; REPORT_TYPE; announce_date (DB notice_date)",
            profit["date_start"],
            profit["date_end"],
            profit["stock_count"],
            profit["row_count"],
            "LOCAL_STRUCTURED",
            f"Notice-date fields available; report types={profit['report_types']}. DB mapping: config/db_mapping.json profit.ann_date_column=notice_date. Complete event history and first-release/revision semantics not validated.",
        ),
        row(
            "N_shareholder_management_events",
            True,
            "data/cache/h7_turnover/cninfo/*.csv",
            "change_reason; announcement_date",
            START_DATE,
            END_DATE,
            5180,
            0,
            "LOCAL_PARTIAL",
            "Share-capital lineage is not a complete management/shareholder announcement corpus.",
        ),
        row(
            "O_market_level_daily_aggregate",
            False,
            "constructible from data/cache/price/*.csv",
            "sum(amount)/sum(cap)",
            START_DATE,
            END_DATE,
            price_meta["stock_count"],
            price_meta["row_count"],
            "CONSTRUCTIBLE_ADAPTED",
            "Reverse aggregation of current universe is not point-in-time market-wide history.",
        ),
        row(
            "P_historical_size",
            True,
            "data/cache/price/*.csv",
            "total_market_cap; circulating_market_cap",
            START_DATE,
            END_DATE,
            price_meta["file_count"],
            price_meta["row_count"],
            "PARTIAL",
            "Historical dated but vendor vintage and universe are not point-in-time audited.",
        ),
        row(
            "Q_institutional_holdings",
            False,
            "none",
            "none",
            "",
            "",
            0,
            0,
            "NOT_LOCAL",
            "Public fund-holding data are a proxy, not total institutional ownership.",
        ),
        row(
            "R_analyst_research_reports",
            False,
            "none",
            "none",
            "",
            "",
            0,
            0,
            "NOT_LOCAL",
            "A bounded public report-list probe is required.",
        ),
        row(
            "S_investor_sentiment_accounts",
            False,
            "none",
            "none",
            "",
            "",
            0,
            0,
            "NOT_LOCAL",
            "A bounded public monthly-account-statistics probe is required.",
        ),
    ]


def dmtr_mapping_rows(daily: pd.DataFrame) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for candidate, cap, count in (
        ("aggregate_amount_over_total_market_cap", "sum_total_cap", "total_cap_count"),
        (
            "aggregate_amount_over_circulating_market_cap",
            "sum_circulating_cap",
            "circulating_cap_count",
        ),
    ):
        valid = (daily["sum_amount"] > 0) & (daily[cap] > 0)
        early = valid & (daily["date"] < "2021-01-01")
        output.append(
            {
                "paper_component": "DMTR",
                "paper_target": "aggregate dollar trading volume / market value of all stocks",
                "project_candidate": candidate,
                "classification": "ADAPTED_CONSTRUCTIBLE",
                "evidence": f"valid_days={int(valid.sum())}; participation_median={daily.loc[valid, count].median():.0f}; participation_min={daily.loc[valid, count].min():.0f}; early_valid_days={int(early.sum())}",
                "limitation": "Current-5195 reverse aggregation is survivorship-biased and not a point-in-time full-market aggregate; denominator semantics are not frozen.",
            }
        )
    return output


def event_feasibility(probe: pd.DataFrame, profit: dict[str, Any]) -> pd.DataFrame:
    probe = probe.fillna("")
    samples = probe[probe["row_type"] == "announcement_sample"].copy()
    summary = probe[probe["row_type"] == "stock_year_summary"]
    successful = summary[summary["status"] == "SUCCESS"]
    rows: list[dict[str, Any]] = []
    for category in EVENT_CATEGORIES:
        matches = samples[
            samples["event_candidates"]
            .astype(str)
            .str.split("|")
            .apply(lambda values, name=category: name in values)
        ]
        if category == "earnings":
            local_mapping = "LOCAL_STRUCTURED"
            status = "LOCAL_DISCLOSURE_DATES_AVAILABLE_COMPLETENESS_UNVERIFIED"
            limitation = f"Local NOTICE_DATE/announce_date verified for {profit['stock_count']} stocks, {profit['row_count']} rows; historical event completeness and first-release dates remain unverified. CNINFO title probe is sampled."
        elif category == "major_capital_investment":
            local_mapping = "LOCAL_ANNOUNCEMENT_SEARCH"
            status = "TEXT_CLASSIFICATION_REQUIRED"
            limitation = "Title keywords cannot reliably distinguish materiality; no PDF/full-text classification was run."
        else:
            local_mapping = "LOCAL_ANNOUNCEMENT_SEARCH"
            status = "FEASIBLE_WITH_AMBIGUITY" if len(matches) else "UNKNOWN_FROM_BOUNDED_PROBE"
            limitation = (
                "Title/category discovery is auditable but not an exhaustive event classifier."
            )
        rows.append(
            {
                "event_category": category,
                "local_mapping": local_mapping,
                "probe_candidate_rows": len(matches),
                "stocks_with_candidate": matches["stock_code"].nunique(),
                "announcement_date_nonmissing_rate": float(
                    matches["announcement_date"].ne("").mean()
                )
                if len(matches)
                else np.nan,
                "feasibility_status": status,
                "classification_ambiguity": "HIGH"
                if category
                in {
                    "M&A",
                    "ownership_change",
                    "major_capital_investment",
                    "large_shareholder_trade",
                }
                else "MEDIUM",
                "known_limitation": limitation,
            }
        )
    rows.append(
        {
            "event_category": "split_share_reform",
            "local_mapping": "NOT_LOCAL",
            "probe_candidate_rows": 0,
            "stocks_with_candidate": 0,
            "announcement_date_nonmissing_rate": np.nan,
            "feasibility_status": "NOT_RELEVANT_TO_MODERN_SAMPLE",
            "classification_ambiguity": "NONE",
            "known_limitation": "No dummy is manufactured for the 2020-2026 sample.",
        }
    )
    rows.append(
        {
            "event_category": "probe_pipeline",
            "local_mapping": "BOUNDED_CNINFO_METADATA",
            "probe_candidate_rows": len(samples[samples["event_candidates"].ne("")]),
            "stocks_with_candidate": samples.loc[
                samples["event_candidates"].ne(""), "stock_code"
            ].nunique(),
            "announcement_date_nonmissing_rate": float(samples["announcement_date"].ne("").mean())
            if len(samples)
            else np.nan,
            "feasibility_status": "SOURCE_STABILITY_UNRESOLVED"
            if len(successful) < len(summary) or summary.empty
            else "SCALABILITY_NOT_ESTABLISHED_BY_FIRST_PAGE_PROBE",
            "classification_ambiguity": "HIGH",
            "known_limitation": "Stock-year totals are exact API counts; candidate counts cover only first-page metadata samples and are not completeness estimates.",
        }
    )
    return pd.DataFrame(rows)


def construct_validation_rows(public: list[dict[str, Any]]) -> pd.DataFrame:
    by_variable = {row["variable"]: row for row in public}
    accounts = by_variable.get("monthly_new_investor_accounts", {})
    analyst = by_variable.get("analyst_report_count", {})
    fund = by_variable.get("fund_holding_proxy", {})
    return pd.DataFrame(
        [
            {
                "construct": "size",
                "exact_available": True,
                "proxy_available": True,
                "proxy_definition": "historical daily total/circulating market cap",
                "historical_frequency": "daily",
                "coverage": "5195 current-universe cache files",
                "status": "PARTIAL",
                "limitation": "Monthly pre-measurement values are mechanically feasible, but vintage and point-in-time universe lineage are not audited.",
            },
            {
                "construct": "institutional_ownership",
                "exact_available": False,
                "proxy_available": fund.get("status") == "SUCCESS",
                "proxy_definition": "fund holdings / circulating shares; not all institutional investors",
                "historical_frequency": "quarterly/latest endpoint-dependent",
                "coverage": f"single-stock bounded probe rows={fund.get('rows_through_cutoff', 0)}",
                "status": "PARTIAL_PROXY_ONLY"
                if fund.get("status") == "SUCCESS"
                else "NOT_FEASIBLE",
                "limitation": "Fund holdings cannot be labelled paper IO; public endpoint history/completeness is not established.",
            },
            {
                "construct": "analyst_coverage",
                "exact_available": False,
                "proxy_available": analyst.get("status") == "SUCCESS",
                "proxy_definition": "monthly distinct report institutions or report count",
                "historical_frequency": "dated reports",
                "coverage": f"single-stock bounded probe {analyst.get('date_start', '')}..{analyst.get('date_end', '')}; rows={analyst.get('rows_through_cutoff', 0)}",
                "status": "REPORT_COUNT_AND_INSTITUTION_COUNT_PROXY"
                if analyst.get("status") == "SUCCESS"
                else "NOT_FEASIBLE",
                "limitation": "No analyst-name field; cannot reproduce distinct analysts following the firm.",
            },
            {
                "construct": "new_individual_stock_accounts",
                "exact_available": False,
                "proxy_available": accounts.get("status") == "SUCCESS",
                "proxy_definition": "Eastmoney mirror of monthly stock-account statistics",
                "historical_frequency": "monthly",
                "coverage": f"{accounts.get('date_start', '')}..{accounts.get('date_end', '')}; rows={accounts.get('rows_through_cutoff', 0)}",
                "status": "MONTHLY_SERIES_INCOMPLETE"
                if accounts.get("status") == "SUCCESS"
                else "NOT_FEASIBLE",
                "limitation": "Probe ends before 2026 and is not directly sourced from an archived CSDC release; continuous 2020-2026 paper-frequency validation is unavailable.",
            },
        ]
    )


def build_report(
    sample: pd.DataFrame,
    daily: pd.DataFrame,
    turnover: dict[str, Any],
    listing: dict[str, Any],
    probe: pd.DataFrame,
    events: pd.DataFrame,
    constructs: pd.DataFrame,
) -> str:
    probe_summary = probe[probe["row_type"] == "stock_year_summary"]
    successful = int((probe_summary["status"] == "SUCCESS").sum())
    total = len(probe_summary)
    dmtr_valid = int(((daily["sum_amount"] > 0) & (daily["sum_total_cap"] > 0)).sum())
    qa = [
        "No future-return file or field was loaded.",
        "No ATR-return relation, outcome sort, Fama-MacBeth regression, portfolio, Alpha, or backtest was computed.",
        "Chronology is fixed as estimation months t-8..t-2, application month t-1, with month t forbidden.",
        "ATR is mapped as a sum of signed daily residuals, never absolute or squared residuals.",
        "Both total-cap and circulating-cap DMTR candidates are audited without outcome selection.",
        "Announcement/disclosure dates are distinguished from implementation and ex-dates.",
        "IPO six-month exclusion coverage is explicitly measured.",
        "Institutional ownership and analyst coverage proxies are not labelled exact.",
        "An incomplete monthly account series is not promoted to paper-frequency sentiment data.",
        f"CNINFO probe is bounded to {len(sample)}/{MAX_PROBE_STOCKS} deterministic stocks and first-page metadata per stock-year.",
        "No full-market announcement corpus or announcement PDF was downloaded.",
        "H5/H6/H7/H8, MCTS, Phase B, prospective, and final-test artifacts were not run or modified.",
    ]
    event_lines = "\n".join(
        f"- {row.event_category}: {row.feasibility_status} (sample candidates={row.probe_candidate_rows})"
        for row in events.itertuples(index=False)
        if row.event_category != "probe_pipeline"
    )
    qa_lines = "\n".join(f"{i}. {text}" for i, text in enumerate(qa, start=1))
    return (
        f"""# Pre-H9 ATR Measurement Feasibility Audit

## Scope and conclusion

This is a signal/data-only measurement audit. It does not define H9 and does not estimate any relation between ATR and a later return. The closest available individual turnover is BaoStock circulating-share turnover, a **CLOSE_ECONOMIC_MATCH**, not a proven exact match to the paper. A daily market control is mechanically constructible, but both local DMTR candidates reverse-aggregate the current 5,195-stock universe and therefore are not point-in-time historical market aggregates.

**ATR core classification: `ADAPTED_ATR_CORE_FEASIBLE`.** Turnover history supports {turnover["monthly_candidate_count"]:,} stock-measurement-month candidates across {turnover["stocks_with_candidate"]:,} stocks, with seven preceding calendar months and a measurement month. The adaptation remains material because the event-window convention could not be uniquely verified from accessible full text, event-title classification is incomplete, and DMTR/universe semantics are not an exact paper replication.

**Construct validation: `CONSTRUCT_VALIDATION_WEAK`.** Historical size is partially feasible. Exact institutional ownership and exact analyst count are absent; available fund/report fields are proxies. The public monthly new-account series observed in the bounded probe ends in 2023-08 and does not provide continuous 2020-2026 coverage.

## Paper target and chronology

The external target is Pan, Tang and Xu, *Speculative Trading and Stock Returns*, Review of Finance 20(5), 1835-1865, DOI 10.1093/rof/rfv059. For measurement month t-1, the normal-turnover model uses months t-8 through t-2; its fitted coefficients are applied to daily observations in t-1. ATR is the sum of signed daily residual turnover in t-1. Month t is a later pricing period and is prohibited here.

The journal article page and issue metadata were accessible, but the publisher full text is subscriber-only and the public SSRN PDF could not be retrieved in this environment. A secondary replication appendix describes a seven-month daily normal-turnover regression and aggregation of residuals, but its notation compresses the timeline. Accordingly, the requested Appendix chronology governs this audit and any body/Appendix notation difference remains unresolved until a human reads the full article. The phrase “3 days surrounding events” could not be mapped uniquely to trading-day offsets: `EVENT_WINDOW_CONTRACT={EVENT_WINDOW_CONTRACT}`. No alternative 1D/3D/5D windows were tested.

## Local measurement evidence

- Individual turnover: BaoStock `baostock_circulating_turnover`, 5,195 files, {turnover["row_count"]:,} daily rows, {turnover["date_start"]} through {turnover["date_end"]}.
- Estimation availability: candidate stock-months={turnover["monthly_candidate_count"]:,}; stocks with candidates={turnover["stocks_with_candidate"]:,}; median/p10/p90 estimation daily rows={turnover["median_estimation_daily_rows"]:.0f}/{turnover["p10_estimation_daily_rows"]:.0f}/{turnover["p90_estimation_daily_rows"]:.0f}.
- DMTR: {dmtr_valid:,} valid local aggregate days. Candidate A is aggregate amount / total market cap; candidate B is aggregate amount / circulating market cap. Candidate A is closer to the stated dollar-volume/market-value wording, but is not frozen as Primary because total-versus-float semantics still need paper confirmation.
- IPO exclusion: explicit `A股上市` lineage is available for {listing["stock_count"]:,}/{listing["universe_count"]:,} current-universe stocks. The six-month exclusion is therefore only partially feasible; missing listing records may not be replaced by first local price date.
- Market aggregate point-in-time status: `CURRENT_UNIVERSE_REVERSE_AGGREGATE_NOT_POINT_IN_TIME`.

## Bounded announcement probe

The deterministic probe used {len(sample)} stocks, covers every available board × size-quartile stratum, and then adds locally reviewed industry labels without using any return. CNINFO was queried only for metadata in 2020-01-01..2026-08-20. Stock-year summary calls succeeded for {successful}/{total}; `totalAnnouncement` is an API count, while only the first 30 metadata rows per stock-year were sampled. Thus sampled event-candidate counts are discovery evidence, not recall estimates.

{event_lines}

Local `NOTICE_DATE` coverage is partial; see the inventory and earnings row for measured counts. Profit-cache file count must not be treated as disclosure-date coverage. H8 corporate-action `dividOperateDate` remains an implementation/ex-date cross-check only. Major capital investment and broad ownership/M&A labels require text review; no PDF or NLP batch was run. Split-share reform is `NOT_RELEVANT_TO_MODERN_SAMPLE` and no dummy is created.

## Design-matrix feasibility

The schema `intercept + DMTR + event-category dummies` is feasible. A paper-style rank/collinearity test is not final because event-window offsets are unresolved and first-page title samples are not a complete event history. All-zero and rare columns must be failed or reported per stock estimation window; they must not be silently dropped after seeing a measurement result. No fitted residual or monthly ATR signal was produced in this audit.

## Construct-validation feasibility

| construct | status | exact | proxy | limitation |
|---|---|---:|---:|---|
"""
        + "\n".join(
            f"| {row.construct} | {row.status} | {str(row.exact_available).lower()} | {str(row.proxy_available).lower()} | {row.limitation} |"
            for row in constructs.itertuples(index=False)
        )
        + f"""

## Data-quality verdict

The evidence is adequate for an **adapted measurement prototype**, not for claiming a paper-exact replication or that ATR has already been validated as speculative trading. The largest data blocker is a complete, classified, announcement-date event history. The largest definition blocker is the unresolved paper event-day window plus unconfirmed total-versus-float denominator semantics for DTR/DMTR.

## QA

{qa_lines}

```text
experiment_type=atr_measurement_feasibility_audit
sample_role=historical_seen_and_bounded_public_metadata_probe
signal_data_only=true
future_returns_loaded=false
ATR_return_relation_computed=false
H9_defined=false
MCTS_run=false
H5_H6_H7_H8_rerun=false
Phase_B_run=false
prospective_data_accessed=false
final_test_accessed=false
```
"""
    )


def finalize_existing(project_root: Path) -> dict[str, Any]:
    """Finish the interrupted audit from persisted evidence, with no network calls."""
    root = project_root.resolve()
    output = root / "reports/atr_feasibility"
    probe = pd.read_csv(output / "atr_event_source_probe.csv", dtype={"stock_code": str}, keep_default_na=False)
    sample = select_probe_sample(root)
    summary = probe.loc[probe.row_type.eq("stock_year_summary")].copy()
    summary["year"] = pd.to_numeric(summary.year).astype(int)
    expected = {(code, year) for code in sample.stock_code for year in range(2020, 2027)}
    observed = set(zip(summary.stock_code, summary.year, strict=True))
    if observed != expected or summary.duplicated(["stock_code", "year"]).any():
        raise ValueError("Checkpoint must contain exactly one outcome for each of the fixed 210 stock-years")
    if not summary.status.isin(["SUCCESS", "FAILED"]).all():
        raise ValueError("Checkpoint contains unfinished stock-year outcomes")
    samples = probe.loc[probe.row_type.eq("announcement_sample")].copy()
    samples["year"] = pd.to_numeric(samples.year).astype(int)
    samples["is_candidate"] = samples.event_candidates.ne("")
    samples["multiple_categories"] = samples.event_candidates.str.contains("|", regex=False)
    samples["has_date"] = pd.to_datetime(samples.announcement_date, errors="coerce").notna()
    diagnostics = summary[["stock_code", "year", "board", "size_quartile", "industry", "status", "total_announcements", "sampled_announcements", "error"]].copy()
    counts = samples.groupby(["stock_code", "year"]).agg(
        sampled_metadata_rows=("is_candidate", "size"),
        paper_relevant_candidate_announcements=("is_candidate", "sum"),
        multiple_category_candidates=("multiple_categories", "sum"),
        announcement_date_rows=("has_date", "sum"),
    )
    diagnostics = diagnostics.merge(counts, on=["stock_code", "year"], how="left")
    # Failed requests remain missing, never a zero-event observation.
    for column in counts.columns:
        diagnostics.loc[diagnostics.status.eq("SUCCESS"), column] = diagnostics.loc[diagnostics.status.eq("SUCCESS"), column].fillna(0)
    diagnostics["keyword_only_events"] = diagnostics.paper_relevant_candidate_announcements
    diagnostics["unresolved_candidate_events"] = diagnostics.paper_relevant_candidate_announcements
    diagnostics["structured_event_matches"] = pd.NA
    diagnostics["structured_match_status"] = "NOT_PERFORMED_NOT_ZERO"
    diagnostics["candidate_scope"] = "FIRST_PAGE_ONLY_NOT_COMPLETE_EVENT_HISTORY"
    diagnostics.to_csv(output / "atr_event_stock_year_diagnostics.csv", index=False, encoding="utf-8-sig")

    profit = profile_profit_notices(root)
    inventory = pd.read_csv(output / "atr_local_data_inventory.csv", keep_default_na=False)
    notice = inventory.paper_component.eq("M_financial_report_disclosure_dates")
    for column in ("stock_count", "row_count", "date_start", "date_end"):
        inventory.loc[notice, column] = profit[column]
    inventory.loc[notice, "local_field"] = "NOTICE_DATE; REPORT_TYPE; announce_date (DB notice_date)"
    inventory.loc[notice, "known_limitation"] = "Two cache schemas; DB announce_date maps to profit_sheets.notice_date. First-release/revision semantics and complete stock-year/report-type coverage not validated."
    inventory.to_csv(output / "atr_local_data_inventory.csv", index=False, encoding="utf-8-sig")
    events = event_feasibility(probe, profit)
    events.to_csv(output / "atr_event_category_feasibility.csv", index=False, encoding="utf-8-sig")
    constructs = pd.read_csv(output / "atr_construct_validation_feasibility.csv", keep_default_na=False)
    constructs.loc[constructs.construct.eq("analyst_coverage"), "limitation"] = "Existing probe did not establish usable analyst-name history; this is not proof that the source never provides analyst fields. Original raw probe error was not persisted."
    constructs.loc[constructs.construct.eq("institutional_ownership"), "limitation"] = "No usable fund-holding history established by existing probe; not evidence of universal unavailability. Original raw probe error was not persisted. Fund holdings are not total institutional ownership."
    constructs.to_csv(output / "atr_construct_validation_feasibility.csv", index=False, encoding="utf-8-sig")
    failed = int(summary.status.eq("FAILED").sum())
    parameters = probe.loc[probe.row_type.eq("parameter_test")]
    result = {
        "audit_status": "COMPLETE_SIGNAL_DATA_ONLY",
        "checkpoint_stock_year_requests": len(summary),
        "checkpoint_successful": len(summary) - failed,
        "checkpoint_failed": failed,
        "remaining_stock_year_requests": 0,
        "new_network_requests_this_recovery": 0,
        "stock_year_success_rate": (len(summary) - failed) / len(summary),
        "parameter_tests": parameters[["probe_type", "status", "error"]].to_dict("records"),
        "network_failure_evidence": summary.loc[summary.status.eq("FAILED"), "error"].value_counts().to_dict(),
        "individual_turnover_available": True,
        "best_local_turnover_candidate": "BAOSTOCK_CIRCULATING_TURNOVER",
        "turnover_definition_match": "CLOSE_ECONOMIC_MATCH",
        "market_turnover_constructible": "ADAPTED_MECHANICALLY_CONSTRUCTIBLE",
        "recommended_DMTR_candidate": "AMOUNT_OVER_TOTAL_CAP_PROVISIONAL_NOT_FROZEN",
        "market_aggregate_point_in_time_status": "CURRENT_UNIVERSE_REVERSE_AGGREGATE_NOT_POINT_IN_TIME",
        "paper_estimation_window_feasible": "CALENDAR_HISTORY_AVAILABLE_NOT_COMPLETE_DESIGN_VALIDATED",
        "paper_measurement_month_feasible": "OBSERVED_MONTH_AVAILABLE_FULL_MONTH_COMPLETENESS_NOT_VALIDATED",
        "IPO_6M_exclusion_feasible": "PARTIAL_5177_OF_5195",
        "events": events.set_index("event_category").feasibility_status.to_dict(),
        "event_announcement_date_coverage": "5310_OF_5310_SAMPLED_ROWS_ONLY_FULL_COVERAGE_UNKNOWN",
        "sampled_metadata_rows": len(samples),
        "sampled_keyword_candidates": int(samples.is_candidate.sum()),
        "multiple_category_candidate_count": int(samples.multiple_categories.sum()),
        "multiple_category_candidate_rate": float(samples.multiple_categories.sum() / samples.is_candidate.sum()),
        "classification_precision_or_recall": "NOT_ESTIMATED_NO_GOLD_LABELS_OR_COMPLETE_HISTORY",
        "event_pipeline_scalable": "NOT_ESTABLISHED_SOURCE_STABILITY_UNRESOLVED",
        "event_window_contract": EVENT_WINDOW_CONTRACT,
        "design_matrix_rank": "NOT_IDENTIFIABLE_UNRESOLVED_EVENT_WINDOW_AND_INCOMPLETE_HISTORY",
        "local_disclosure_field_profiles": profit["field_profiles"],
        "size": "PARTIAL",
        "institutional_ownership_exact": False,
        "institutional_ownership_proxy": "NOT_ESTABLISHED_BY_EXISTING_PROBE",
        "analyst_coverage_exact": False,
        "analyst_coverage_proxy": "NOT_ESTABLISHED_BY_EXISTING_PROBE",
        "monthly_new_investor_accounts": "INCOMPLETE_2015_04_TO_2023_08_EXISTING_PROBE",
        "sentiment_validation_status": "MONTHLY_SERIES_INCOMPLETE_NOT_CONTINUOUS_2020_2026",
        "ATR_core_replication_class": "ADAPTED_ATR_CORE_FEASIBLE",
        "ATR_core_class_scope": "CONDITIONAL_MEASUREMENT_PROTOTYPE_ONLY_NOT_READY_TO_FIT_OR_PAPER_EXACT",
        "construct_validation_strength": "CONSTRUCT_VALIDATION_WEAK",
        "largest_data_blocker": "COMPLETE_CLASSIFIED_ANNOUNCEMENT_DATE_HISTORY_AND_SOURCE_STABILITY",
        "largest_definition_blocker": "EVENT_WINDOW_AND_TOTAL_VS_FLOAT_DENOMINATOR",
        "future_returns_loaded": False,
        "ATR_return_relation_computed": False,
        "H9_defined": False,
        "MCTS_run": False,
        "recommended_next_step": "STOP_HUMAN_PAPER_AND_MEASUREMENT_REVIEW",
    }
    result["event_announcement_date_coverage"] = f"{int(samples.has_date.sum())}_OF_{len(samples)}_SAMPLED_ROWS_ONLY_FULL_COVERAGE_UNKNOWN"
    (output / "atr_feasibility_summary.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    path = output / "atr_measurement_feasibility_report.md"
    report = path.read_text(encoding="utf-8").split("\n## Recovery review and final evidence")[0]
    report = report.replace("Earnings events have the strongest local contract because 5,195 profit-cache files contain `NOTICE_DATE` and report type.", "Earnings disclosure fields occur in two formats: 3 stock files have `NOTICE_DATE`/`REPORT_TYPE`; 5,192 have `announce_date` mapped from database `notice_date`. The former inventory missed the second format. Complete event-history coverage and first-release/revision semantics remain unverified.")
    report = report.replace("earnings: FEASIBLE_WITH_LOCAL_NOTICE_DATE", "earnings: LOCAL_DISCLOSURE_DATES_AVAILABLE_COMPLETENESS_UNVERIFIED")
    report = report.replace("No analyst-name field; cannot reproduce distinct analysts following the firm.", "The existing probe did not establish usable analyst-name history; source-wide field absence is not proven.")
    report += f"""

## Recovery review and final evidence

Recovery on 2026-09-05 found that the old process had already completed all 210 fixed stock-year attempts and written the six planned outputs on 2026-09-03 at 22:46. No ATR audit process remained. The source checkpoint has been preserved without rewriting or retrying requests. There were no remaining stock-year requests and no new network calls in this recovery.

### Measurement definition validity

`ADAPTED_ATR_CORE_FEASIBLE` is a **conditional feasibility class for a future adapted prototype**, not a ready-to-fit event-adjusted ATR or validated paper replication. The event-day offsets and denominator semantics remain unresolved. The design-matrix schema is available, but rank, event-window dummy frequency, all-zero columns and collinearity cannot be certified from an incomplete first-page event history with unfrozen timing. No artificial event window or formal ATR was fitted.

### Local data coverage

The 336,492 stock-month count is a calendar-history availability diagnostic: each preceding month merely needs at least one valid turnover observation. It does not enforce a minimum regression observation count, IPO exclusion, full measurement-month coverage, or a complete event design. August 2026 ends at the fixed August 20 cutoff and is not a complete calendar month. The prior run did not persist its failed-history count or daily DMTR table; those are unavailable as detailed artifacts and have not been recreated by rerunning the broad audit.

Disclosure schema diagnostics: `{json.dumps(profit['field_profiles'], ensure_ascii=False)}`. These are date-field counts, not independent unique earnings events. `announce_date` lineage is `config/db_mapping.json` → `profit_sheets.notice_date` via `src/aq_factor_lab/db_source.py`; no synthetic report-date lag was substituted. Q1/semiannual/Q3/annual labels were observed in the three `REPORT_TYPE` files, not verified for every stock-year. Existing historical-size and H7/H8 data are reused. H8 implementation/ex-date data still cannot replace dividend announcement dates.

DMTR participation in the persisted mapping has median 4,802 and minimum 68, so “1,562 valid days” means mechanically positive aggregates, not full-market coverage. The existing aggregation masks amount and cap independently; matched numerator/denominator membership, cap units/vintages, explicit listing-date filtering and historical delisted membership are not certified. Inventory market-cap stock_count=5,197 is actually a cache-file count, not verified distinct valid cap-stock coverage. These limitations prohibit treating the candidate as a point-in-time paper DMTR.

### Event discoverability

There are {len(samples):,} sampled metadata rows, {int(samples.has_date.sum()):,} parseable dates, and {int(samples.is_candidate.sum()):,} keyword candidate announcements. {int(samples.multiple_categories.sum())} candidates match multiple categories; this is a mechanical overlap statistic, not classification error or precision. Every keyword candidate remains unvalidated; structured matches were not performed and are recorded as missing, not zero. Per-stock/year diagnostics are in `atr_event_stock_year_diagnostics.csv`; failed requests retain unknown counts. Candidate absence on a first page does not mean event absence. No PDF was downloaded.

### Source/network scalability

`event_pipeline_scalable=NOT_ESTABLISHED_SOURCE_STABILITY_UNRESOLVED`. Stock-year success is {len(summary)-failed}/210 ({(len(summary)-failed)/len(summary):.2%}); {failed} failures remain source/environment reliability evidence. The checkpoint records 20 HTTP 504, 12 HTTP 502 and one ReadTimeout; the latter identifies an existing localhost proxy path, so failures are not all attributed uniquely to CNINFO. No proxy configuration was changed. Keyword parameter testing succeeded; category testing failed with an additional HTTP 504. All 34 failed requests remain preserved, including that parameter test. First-page successes do not establish pagination throughput or a complete event pipeline.

Construct-validation source calls had already finished. Their raw responses/errors were not persisted by the old script; existing summarized failures are retained without claiming that IO/analyst data can never be obtained. No replacement requests were made. Monthly accounts remain incomplete and are not presented as continuous 2020–2026 sentiment validation.

Final machine-readable fields: `atr_feasibility_summary.json`. The work stops at this feasibility audit; H9 is not defined or run.
"""
    path.write_text(report, encoding="utf-8")
    return result


def run(project_root: Path, network_probe: bool) -> None:
    root = project_root.resolve()
    output = root / "reports/atr_feasibility"
    output.mkdir(parents=True, exist_ok=True)
    if not network_probe and (output / "atr_event_source_probe.csv").exists():
        raise ValueError("Existing checkpoint must not be overwritten by a disabled probe; use --finalize-existing")

    sample = select_probe_sample(root)
    if len(sample) > MAX_PROBE_STOCKS:
        raise RuntimeError("bounded probe sample exceeds 30 stocks")
    daily, price_meta = aggregate_price_cache(root)
    turnover = turnover_window_availability(root)
    listing = profile_listing_dates(root)
    profit = profile_profit_notices(root)

    inventory = pd.DataFrame(inventory_rows(root, price_meta, turnover, listing, profit))
    inventory.to_csv(output / "atr_local_data_inventory.csv", index=False, encoding="utf-8-sig")

    mapping = [
        {
            "paper_component": "individual_DTR",
            "paper_target": "daily individual share turnover",
            "project_candidate": "BaoStock circulating-share turnover",
            "classification": "CLOSE_ECONOMIC_MATCH",
            "evidence": "H7 lineage and 5,195 valid files",
            "limitation": "Circulating denominator may differ from paper shares-outstanding convention.",
        },
        {
            "paper_component": "TOTAL_SHARE_TURNOVER_comparison",
            "paper_target": "shares traded / total shares",
            "project_candidate": "BaoStock volume plus CNINFO dated total-share lineage",
            "classification": "ADAPTED_COMPARISON_FEASIBLE_WITH_EXCEPTIONS",
            "evidence": "5,180 share-lineage stocks; 35 lack opening total-share level",
            "limitation": "Not automatically Primary; no outcome-based choice is permitted.",
        },
        {
            "paper_component": "estimation_chronology",
            "paper_target": "estimate t-8..t-2; apply in t-1; month t excluded",
            "project_candidate": "calendar-month lag mapping",
            "classification": "FEASIBLE",
            "evidence": f"candidate_stock_months={turnover['monthly_candidate_count']}",
            "limitation": "Paper body/Appendix notation requires final human full-text check.",
        },
        {
            "paper_component": "monthly_ATR",
            "paper_target": "sum of signed daily residual turnover",
            "project_candidate": "signed residual sum contract",
            "classification": "FEASIBLE_NOT_COMPUTED",
            "evidence": "synthetic test only",
            "limitation": "No formal ATR series is produced by this audit.",
        },
        {
            "paper_component": "event_window",
            "paper_target": "three days surrounding events",
            "project_candidate": "none",
            "classification": EVENT_WINDOW_CONTRACT,
            "evidence": "publisher full text restricted; public working-paper PDF unavailable",
            "limitation": "No offset convention is invented or searched.",
        },
        {
            "paper_component": "market_universe",
            "paper_target": "historical A-share market",
            "project_candidate": "current 5,195-stock broader-A historical backfill",
            "classification": "CURRENT_UNIVERSE_REVERSE_AGGREGATE_NOT_POINT_IN_TIME",
            "evidence": "existing broader-A/H7 contracts",
            "limitation": "Survivorship and delisted-stock omissions remain.",
        },
    ]
    mapping.extend(dmtr_mapping_rows(daily))

    if network_probe:
        probe = run_announcement_probe(sample, output / "atr_event_source_probe.csv")
        public = probe_construct_sources(END_DATE)
    else:
        probe = pd.DataFrame(
            [
                {
                    "row_type": "probe_not_run",
                    "stock_code": "",
                    "board": "",
                    "size_quartile": "",
                    "industry": "",
                    "year": "",
                    "probe_type": "",
                    "query_value": "",
                    "status": "NOT_RUN",
                    "total_announcements": "",
                    "sampled_announcements": 0,
                    "announcement_date": "",
                    "title": "",
                    "event_candidates": "",
                    "announcement_link": "",
                    "error": "network probe disabled",
                }
            ]
        )
        public = []
    probe.to_csv(output / "atr_event_source_probe.csv", index=False, encoding="utf-8-sig")

    events = event_feasibility(probe, profit)
    events.to_csv(output / "atr_event_category_feasibility.csv", index=False, encoding="utf-8-sig")
    constructs = construct_validation_rows(public)
    constructs.to_csv(
        output / "atr_construct_validation_feasibility.csv", index=False, encoding="utf-8-sig"
    )
    pd.DataFrame(mapping).to_csv(
        output / "atr_paper_to_project_mapping.csv", index=False, encoding="utf-8-sig"
    )
    report = build_report(sample, daily, turnover, listing, probe, events, constructs)
    (output / "atr_measurement_feasibility_report.md").write_text(report, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--network-probe", action="store_true")
    parser.add_argument("--finalize-existing", action="store_true")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    if args.finalize_existing:
        if args.network_probe:
            raise ValueError("--finalize-existing must remain offline")
        print(json.dumps(finalize_existing(args.project_root), ensure_ascii=False, indent=2))
    else:
        run(args.project_root, args.network_probe)
