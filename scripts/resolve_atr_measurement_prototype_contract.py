"""Bounded, signal/data-only contract probes. No return or pricing inputs."""

from __future__ import annotations

import argparse
import json
import math
import re
import socket
import time
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/atr_measurement_prototype"
OLD = ROOT / "reports/atr_feasibility"
CUTOFF = "2026-08-20"
DATES = ["2020-02-03", "2020-06-19", "2021-01-04", "2021-12-27",
         "2022-01-04", "2024-01-02", CUTOFF]
CHRONOLOGY = "ESTIMATE_T8_TO_T2_MEASURE_T1"
DMTR_TARGET = "AGGREGATE_A_SHARE_DOLLAR_VOLUME_OVER_TOTAL_MARKET_CAP"
EVENT_WINDOW = "UNRESOLVED_FROM_TEXT"
REQUEST_LOG = OUT / "request_attempts.jsonl"


def csv(frame: pd.DataFrame, name: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    temp = path.with_suffix(".tmp")
    frame.to_csv(temp, index=False, encoding="utf-8-sig")
    temp.replace(path)


def attempts() -> list[dict[str, Any]]:
    if not REQUEST_LOG.exists():
        return []
    return [json.loads(line) for line in REQUEST_LOG.read_text(encoding="utf-8").splitlines()]


def fetch(session: requests.Session, key: str, url: str, *, method: str = "GET",
          params: dict | None = None, data: dict | None = None) -> bytes:
    """Two attempts total per request key, including across process resumes."""
    cache = OUT / "cache" / f"{key}.bin"
    if cache.exists():
        return cache.read_bytes()
    cache.parent.mkdir(parents=True, exist_ok=True)
    previous = [row for row in attempts() if row["request_key"] == key]
    error = previous[-1]["error"] if previous else ""
    for number in range(len(previous) + 1, 3):
        record = dict(request_key=key, url=url, method=method, attempt_count=number,
                      requested_at=pd.Timestamp.now(tz="UTC").isoformat(), status="FAILED",
                      error_type="", error="", http_status=None)
        try:
            response = session.request(method, url, params=params, data=data, timeout=(10, 25))
            record["http_status"] = response.status_code
            response.raise_for_status()
            content = response.content
            if not content:
                raise ValueError("empty_response")
            cache.write_bytes(content)
            record["status"] = "SUCCESS"
        except (requests.RequestException, ValueError) as exc:
            error = str(exc)
            record.update(error_type=type(exc).__name__, error=error)
        with REQUEST_LOG.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        if record["status"] == "SUCCESS":
            time.sleep(0.25)
            return content
        if number < 2:
            time.sleep(2 ** number)
    raise RuntimeError(f"bounded_request_failed:{key}:{error}")


def session_for(source: str) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "Mozilla/5.0", "Referer": source})
    return session


def fixed_sample() -> tuple[pd.DataFrame, pd.DataFrame]:
    old = pd.read_csv(OLD / "atr_event_source_probe.csv", dtype={"stock_code": str},
                      keep_default_na=False)
    summary = old.loc[old.row_type.eq("stock_year_summary")].copy()
    summary["year"] = pd.to_numeric(summary.year).astype(int)
    if len(summary) != 210 or summary.stock_code.nunique() != 30:
        raise ValueError("fixed_30_stock_checkpoint_contract_changed")
    return old, summary.sort_values(["stock_code", "year"])


def phase_a_sample(summary: pd.DataFrame) -> pd.DataFrame:
    chosen = []
    for status in ("SUCCESS", "FAILED"):
        subset = summary.loc[summary.status.eq(status)]
        strata = subset.groupby("board", sort=True).head(1)
        extra = subset.loc[~subset.index.isin(strata.index)]
        chosen.append(pd.concat([strata, extra]).head(5))
    return pd.concat(chosen).sort_values(["stock_code", "year"])


def normalize_announcements(items: list[dict], code: str, year: int,
                            page: int, total: int) -> list[dict]:
    rows = []
    for item in items:
        if str(item.get("secCode", code)).zfill(6) != code:
            raise ValueError("cross_stock_response")
        stamp = pd.to_datetime(item.get("announcementTime"), unit="ms", utc=True)
        date = stamp.tz_convert("Asia/Shanghai").date().isoformat()
        if not f"{year}-01-01" <= date <= min(f"{year}-12-31", CUTOFF):
            raise ValueError("out_of_requested_date_response")
        link = "http://static.cninfo.com.cn/" + str(item.get("adjunctUrl", ""))
        rows.append(dict(stock_code=code, stock_name=item.get("secName", ""),
                         announcement_date=date,
                         announcement_title=re.sub("</?em>", "", item["announcementTitle"]),
                         announcement_category_if_available=item.get("announcementCategory", ""),
                         announcement_link=link, source="CNINFO_OFFICIAL", stock_year=year,
                         source_page=page, source_total_count=total,
                         announcement_id=str(item.get("announcementId", ""))))
    return rows


def complete_pagination() -> None:
    old, all_summary = fixed_sample()
    phase_a = phase_a_sample(all_summary)
    csv(phase_a[["stock_code", "year", "board", "size_quartile", "status"]],
        "atr_pagination_phase_a_sample.csv")
    metadata: list[dict] = []
    statuses: list[dict] = []
    with session_for("http://www.cninfo.com.cn/") as session:
        try:
            orgs = json.loads(fetch(session, "cninfo_org_map",
                                   "http://www.cninfo.com.cn/new/data/szse_stock.json"))
            mapping = {row["code"]: row["orgId"] for row in orgs["stockList"]}
            setup_error = ""
        except (ValueError, KeyError, RuntimeError) as exc:
            mapping, setup_error = {}, str(exc)

        def stock_year(item, phase: str) -> None:
            code, year = item.stock_code, int(item.year)
            rows: list[dict] = []
            total, error, count_changed = None, "", False
            first_page_reused = item.status == "SUCCESS"
            page_count = 0
            try:
                if first_page_reused:
                    total = int(item.total_announcements)
                    prior = old.loc[old.row_type.eq("announcement_sample")
                                    & old.stock_code.eq(code) & old.year.astype(str).eq(str(year))]
                    for entry in prior.itertuples(index=False):
                        rows.append(dict(stock_code=code, stock_name="",
                            announcement_date=entry.announcement_date[:10],
                            announcement_title=entry.title,
                            announcement_category_if_available="",
                            announcement_link=entry.announcement_link, source="CNINFO_OFFICIAL",
                            stock_year=year, source_page=1, source_total_count=total,
                            announcement_id=Path(entry.announcement_link).stem))
                    page_count = 1
                page, pages = (2, math.ceil(total / 30)) if total is not None else (1, 1)
                while page <= pages:
                    if setup_error:
                        raise RuntimeError(setup_error)
                    payload = dict(pageNum=str(page), pageSize="30", column="szse",
                        tabName="fulltext", plate="", stock=f"{code},{mapping[code]}",
                        searchkey="", secid="", category="", trade="",
                        seDate=f"{year}-01-01~{min(f'{year}-12-31', CUTOFF)}",
                        sortName="", sortType="", isHLtitle="true")
                    result = json.loads(fetch(session, f"cninfo_{code}_{year}_p{page}",
                        "http://www.cninfo.com.cn/new/hisAnnouncement/query", method="POST",
                        data=payload))
                    current_total = int(result["totalAnnouncement"])
                    items = result.get("announcements") or []
                    if not isinstance(items, list) or current_total < 0:
                        raise ValueError("invalid_pagination_schema")
                    if total is None:
                        total, pages = current_total, math.ceil(current_total / 30)
                    elif total != current_total:
                        count_changed = True
                        raise ValueError(f"source_total_changed:{total}->{current_total}")
                    rows.extend(normalize_announcements(items, code, year, page, total))
                    page_count += 1
                    page += 1
            except (ValueError, KeyError, RuntimeError, TypeError) as exc:
                error = f"{type(exc).__name__}:{exc}"
            unique = len({row["announcement_id"] or row["announcement_link"] for row in rows})
            complete = not error and total is not None and len(rows) == unique == total
            if not error and not complete:
                error = "source_count_or_dedup_mismatch"
            record = dict(stock_code=code, stock_year=year, phase=phase,
                original_first_page_status=item.status, first_page_reused=first_page_reused,
                source_total_announcements=total, retrieved_rows=len(rows), unique_rows=unique,
                pages_retrieved=page_count, source_count_changed=count_changed,
                status="EVENT_HISTORY_COMPLETE_METADATA_ONLY" if complete else "EVENT_HISTORY_PARTIAL",
                error=error)
            statuses.append(record)
            metadata.extend(rows)
            csv(pd.DataFrame(statuses), "atr_full_event_pagination_status.csv")
            csv(pd.DataFrame(metadata, columns=["stock_code", "stock_name", "announcement_date",
                "announcement_title", "announcement_category_if_available", "announcement_link",
                "source", "stock_year", "source_page", "source_total_count", "announcement_id"]),
                "atr_complete_event_metadata_probe.csv")
            print(f"pagination {phase} {code}/{year}: {record['status']} {len(rows)}/{total}", flush=True)

        for item in phase_a.itertuples(index=False):
            stock_year(item, "A")
        rate = sum(row["status"] == "EVENT_HISTORY_COMPLETE_METADATA_ONLY" for row in statuses) / len(phase_a)
        server_failures = sum(row["http_status"] in (502, 504) for row in attempts()
                              if row["request_key"].startswith("cninfo"))
        expand = rate >= .9 and server_failures < 2
        print(f"phase_A_success_rate={rate}; 502_504_attempts={server_failures}; expand={expand}", flush=True)
        if expand:
            keys = set(zip(phase_a.stock_code, phase_a.year, strict=True))
            for item in all_summary.itertuples(index=False):
                if (item.stock_code, item.year) not in keys:
                    stock_year(item, "B")


def official_raw_probe() -> None:
    rows = []
    with session_for("https://www.sse.com.cn/") as sse, session_for("https://www.szse.cn/") as szse:
        for exchange, session in (("SZSE", szse), ("SSE", sse)):
            for date in DATES:
                key = f"{exchange.lower()}_{date}"
                try:
                    if exchange == "SZSE":
                        content = fetch(session, key, "http://www.szse.cn/api/report/ShowReport",
                            params={"SHOWTYPE": "xlsx", "CATALOGID": "1803_sczm", "TABKEY": "tab1",
                                    "txtQueryDate": date})
                        raw = pd.read_excel(BytesIO(content), engine="openpyxl")
                        csv(raw, f"cache/{key}_parsed.csv")
                        evidence = json.dumps(raw.head(7).to_dict("records"), ensure_ascii=False, default=str)
                    else:
                        content = fetch(session, key, "https://query.sse.com.cn/commonQuery.do",
                            params={"sqlId": "COMMON_SSE_SJ_GPSJ_CJGK_MRGK_C",
                                "PRODUCT_CODE": "01,02,03,11,17", "type": "inParams", "SEARCH_DATE": date})
                        result = json.loads(content)
                        evidence = json.dumps(result.get("result", []), ensure_ascii=False)
                    status, error = "RESPONSE_SAVED_PENDING_SEMANTIC_VALIDATION", ""
                except (RuntimeError, ValueError, KeyError) as exc:
                    status, error, evidence = "FAILED", str(exc), ""
                rows.append(dict(exchange=exchange, requested_date=date, status=status,
                                 error=error, response_evidence=evidence))
                csv(pd.DataFrame(rows), "atr_official_dmtr_probe.csv")
                print(f"official {exchange} {date}: {status}", flush=True)
        for name, url in (
            ("sse_legacy_page", "https://www.sse.com.cn/market/stockdata/overview/day/index_his.shtml"),
            ("sse_current_page", "https://www.sse.com.cn/market/stockdata/overview/day/"),
        ):
            try:
                fetch(sse, name, url)
            except RuntimeError as exc:
                print(str(exc), flush=True)


def parse_szse(frame: pd.DataFrame, date: str) -> dict:
    labels = frame.iloc[:, 0].astype(str).str.strip()
    required = {"主板A股", "创业板A股"}
    if date < "2021-04-06":
        required.add("中小板")
    if not required <= set(labels):
        raise ValueError("missing_A_share_category")
    chosen = labels.isin(required)
    amount_column = next(c for c in frame if "成交金额" in c)
    cap_column = next(c for c in frame if str(c).startswith("总市值"))
    if "元" not in amount_column or "元" not in cap_column:
        raise ValueError("currency_units_unverified")
    values = frame.loc[chosen, [amount_column, cap_column]].astype(str).apply(
        lambda col: pd.to_numeric(col.str.replace(",", ""), errors="raise"))
    return dict(amount_cny=float(values[amount_column].sum()),
                total_cap_cny=float(values[cap_column].sum()),
                included_categories="|".join(sorted(required)), source_unit="CNY",
                date_validation="DATE_PARAMETER_AND_DATE_SENSITIVE_ROWS_NO_PAYLOAD_DATE_ECHO")


def parse_sse(result: list[dict], date: str, legacy: bool = False) -> dict:
    if not result:
        raise ValueError("EMPTY_HISTORICAL_RESULT")
    code, amount, cap, stamp = (("PRODUCT_TYPE", "TX_AMOUNT_FULL", "MKT_VALUE_FULL", "CAL_DATE")
                               if legacy else ("PRODUCT_CODE", "TRADE_AMT", "TOTAL_VALUE", "TRADE_DATE"))
    required = {"1", "48"} if legacy else {"01", "03"}
    chosen = [row for row in result if row[code] in required]
    if {row[code] for row in chosen} != required or len(chosen) != 2:
        raise ValueError("missing_or_duplicate_A_share_categories")
    if any(pd.Timestamp(row[stamp]).strftime("%Y-%m-%d") != date for row in chosen):
        raise ValueError("requested_date_not_honored")
    return dict(amount_cny=sum(float(row[amount]) for row in chosen) * 1e8,
                total_cap_cny=sum(float(row[cap]) for row in chosen) * 1e8,
                included_categories="MAIN_BOARD_A|STAR", source_unit="100M_CNY",
                date_validation="PAYLOAD_DATE_EXACT_MATCH")


def resolve_official_and_compare() -> None:
    records = []
    for exchange in ("SZSE", "SSE"):
        for date in DATES:
            key = f"{exchange.lower()}_{date}"
            legacy = exchange == "SSE" and date < "2021-12-27"
            if legacy:
                key = f"sse_legacy_{date}"
            row = dict(exchange=exchange, requested_date=date,
                       source="SSE_LEGACY_OFFICIAL" if legacy else exchange + "_OFFICIAL",
                       source_key=key, b_shares_included=False, funds_included=False)
            try:
                if exchange == "SZSE":
                    values = parse_szse(pd.read_csv(OUT / f"cache/{key}_parsed.csv"), date)
                else:
                    values = parse_sse(json.loads((OUT / f"cache/{key}.bin").read_bytes())["result"],
                                       date, legacy)
                row.update(values, status="VALID_BOUNDED_OFFICIAL_A_SHARE_OBSERVATION", error="")
                row["dmtr"] = row["amount_cny"] / row["total_cap_cny"]
            except (ValueError, OSError, KeyError) as exc:
                row.update(status="UNAVAILABLE", error=str(exc))
            records.append(row)
    official = pd.DataFrame(records)
    csv(official, "atr_official_dmtr_probe.csv")
    combined = official.loc[official.status.eq("VALID_BOUNDED_OFFICIAL_A_SHARE_OBSERVATION")]
    combined = combined.groupby("requested_date").agg(
        official_amount_cny=("amount_cny", "sum"), official_total_cap_cny=("total_cap_cny", "sum"),
        exchange_count=("exchange", "nunique"))
    combined = combined.loc[combined.exchange_count.eq(2)].copy()
    combined["official_dmtr"] = combined.official_amount_cny / combined.official_total_cap_cny
    comparison_path = OUT / "atr_dmtr_source_comparison.csv"
    if comparison_path.exists():
        return  # The seven-date local scan is reusable independently of network probes.
    local = {date: dict(sum_amount=0., sum_total_cap=0., matched_amount=0., matched_cap=0.,
                        amount_count=0, cap_count=0, matched_count=0) for date in DATES}
    for path in sorted((ROOT / "data/cache/price").glob("*.csv")):
        if not re.fullmatch(r"\d{6}", path.stem):
            continue
        try:
            frame = pd.read_csv(path, usecols=["date", "amount", "total_market_cap"])
        except (ValueError, pd.errors.EmptyDataError):
            continue
        frame = frame.loc[frame.date.isin(DATES)]
        for entry in frame.itertuples(index=False):
            row = local[entry.date]
            a, c = pd.to_numeric(entry.amount, errors="coerce"), pd.to_numeric(entry.total_market_cap, errors="coerce")
            a_ok, c_ok = np.isfinite(a) and a > 0, np.isfinite(c) and c > 0
            if a_ok:
                row["sum_amount"] += a
                row["amount_count"] += 1
            if c_ok:
                row["sum_total_cap"] += c
                row["cap_count"] += 1
            if a_ok and c_ok:
                row["matched_amount"] += a
                row["matched_cap"] += c
                row["matched_count"] += 1
    frame = pd.DataFrame.from_dict(local, orient="index").join(combined)
    frame["local_reverse_dmtr"] = frame.sum_amount / frame.sum_total_cap
    frame["local_matched_dmtr"] = frame.matched_amount / frame.matched_cap
    frame["relative_difference"] = frame.local_reverse_dmtr / frame.official_dmtr - 1
    frame["comparison_scope"] = "SEVEN_PROBE_DATES_NOT_FULL_TIME_SERIES"
    frame.index.name = "date"
    csv(frame.reset_index(), "atr_dmtr_source_comparison.csv")


def probe_missing_listing_dates() -> None:
    import baostock as bs

    path = OUT / "atr_listing_date_probe.csv"
    frame = pd.read_csv(path, dtype={"stock_code": str}, keep_default_na=False)
    pending = frame.loc[frame.source.eq("MISSING")]
    if len(pending) > 18:
        raise ValueError("IPO_probe_exceeds_fixed_missing_18")
    socket.setdefaulttimeout(15)
    try:
        login = bs.login()
        if login.error_code != "0":
            raise ValueError(f"baostock_login:{login.error_code}:{login.error_msg}")
        for index, row in pending.iterrows():
            key = "ipo_basic_" + row.stock_code
            if any(record["request_key"] == key for record in attempts()):
                continue
            record = dict(request_key=key, url="baostock:query_stock_basic", method="QUERY",
                attempt_count=1, requested_at=pd.Timestamp.now(tz="UTC").isoformat(),
                status="FAILED", error_type="", error="", http_status=None)
            try:
                code = ("sh." if row.stock_code.startswith("6") else "sz.") + row.stock_code
                response = bs.query_stock_basic(code=code)
                if response.error_code != "0":
                    raise ValueError(response.error_msg)
                result = response.get_data()
                dates = pd.to_datetime(result.loc[result.code.eq(code), "ipoDate"], errors="coerce").dropna()
                if len(dates) != 1:
                    raise ValueError("listing_date_missing_or_nonunique")
                frame.loc[index, "listing_date"] = dates.iloc[0].date().isoformat()
                frame.loc[index, "source"] = "BAOSTOCK_STOCK_BASIC_IPODATE"
                record["status"] = "SUCCESS"
                csv(result, f"cache/{key}.csv")
            except Exception as exc:
                record.update(error_type=type(exc).__name__, error=str(exc))
            with REQUEST_LOG.open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(record, ensure_ascii=False) + "\n")
            csv(frame, path.name)
            print(f"IPO {row.stock_code}: {record['status']}", flush=True)
        bs.logout()
    except Exception as exc:
        with REQUEST_LOG.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(dict(request_key="ipo_login", url="baostock:login",
                method="LOGIN", attempt_count=1, status="FAILED", http_status=None,
                error_type=type(exc).__name__, error=str(exc)), ensure_ascii=False) + "\n")


EVENT_RULES = {
    "EARNINGS": "年度报告|季度报告|半年报|年报|一季报|三季报|业绩快报",
    "M_AND_A_OR_MAJOR_OWNERSHIP_CHANGE": "收购|并购|重组|重大资产|控制权|实际控制人|权益变动|股权变动",
    "REPURCHASE": "回购",
    "MAJOR_CAPITAL_INVESTMENT": "重大投资|对外投资|投资建设|项目投资",
    "LARGE_SHAREHOLDER_PURCHASE_SALE": "增持|减持|大股东|持股变动",
    "DEBT_ISSUANCE": "公司债|可转债|债券发行|发行债券",
    "EQUITY_ISSUANCE": "增发|配股|非公开发行|向特定对象发行",
    "KEY_MANAGERIAL_TURNOVER": "辞任|辞职|聘任|任命|离任|董事长|总经理|财务负责人|董事会秘书",
    "CASH_DIVIDEND_ANNOUNCEMENT": "利润分配|分红|现金红利|权益分派",
}


def earnings_period(title: str) -> str:
    match = re.search(r"(20\d{2})", title)
    if not match:
        return ""
    month = ("03-31" if re.search("第一季度|一季报", title) else
             "09-30" if re.search("第三季度|三季报", title) else
             "06-30" if re.search("半年度|半年报", title) else
             "12-31" if re.search("年度报告|年报", title) else "")
    return f"{match[1]}-{month}" if month else ""


def classify_event(title: str, category: str) -> str:
    if category == "EARNINGS" and earnings_period(title):
        if re.search("摘要|英文|更正|修订|补充|取消|审议|意见|核查|问询|审计|说明", title):
            return "TITLE_AMBIGUOUS"
        if re.search(r"报告(?:全文)?(?:[（(]全文[）)])?$", title):
            return "TITLE_HIGH_CONFIDENCE"
    if category == "REPURCHASE" and "回购股份方案" in title and "意见" not in title:
        return "TITLE_HIGH_CONFIDENCE"
    # Materiality, managerial importance and ownership event stages need human labels.
    return "TITLE_AMBIGUOUS"


def classification_and_earnings() -> None:
    metadata_path = OUT / "atr_complete_event_metadata_probe.csv"
    metadata = pd.read_csv(metadata_path, dtype={"stock_code": str, "announcement_id": str},
                           keep_default_na=False)
    orgs = json.loads((OUT / "cache/cninfo_org_map.bin").read_bytes())["stockList"]
    names = {row["code"]: row["zwjc"] for row in orgs}
    categories = {}
    for path in (OUT / "cache").glob("cninfo_*_p*.bin"):
        for row in json.loads(path.read_bytes()).get("announcements") or []:
            categories[str(row["announcementId"])] = row.get("announcementType", "")
    metadata["stock_name"] = metadata.stock_name.mask(metadata.stock_name.eq(""), metadata.stock_code.map(names))
    metadata["announcement_category_if_available"] = metadata.announcement_id.map(categories).fillna("")
    csv(metadata, metadata_path.name)
    candidates, review = [], []
    for category, pattern in EVENT_RULES.items():
        positives = metadata.loc[metadata.announcement_title.str.contains(pattern, regex=True)].copy()
        positives["paper_event_category"] = category
        positives["classification_source"] = np.where(
            positives.announcement_category_if_available.ne(""),
            "TITLE_RULE_OFFICIAL_CATEGORY_CODE_RETAINED_UNMAPPED", "TITLE_RULE")
        positives["classification_confidence"] = positives.announcement_title.map(
            lambda title: classify_event(title, category))
        positives["eligible_as_frozen_dummy"] = False
        candidates.append(positives)
        selected = positives.sort_values(["stock_code", "announcement_date", "announcement_id"]).head(30).copy()
        selected["review_sample_role"] = "POSITIVE_CANDIDATE"
        review.append(selected)
        # Review lexical near-misses separately; these are not gold-label negatives.
        near = metadata.loc[~metadata.index.isin(positives.index)
                            & metadata.announcement_title.str.contains("审议|意见|核查|进展", regex=True)].head(5).copy()
        near["paper_event_category"] = category
        near["classification_source"] = "RULE_NONMATCH_REVIEW_CONTROL"
        near["classification_confidence"] = "UNCLASSIFIED"
        near["eligible_as_frozen_dummy"] = False
        near["review_sample_role"] = "NEAR_MISS_NEGATIVE_CANDIDATE_NOT_GOLD"
        review.append(near)
    candidates = pd.concat(candidates, ignore_index=True)
    csv(candidates, "atr_event_classification_candidates.csv")
    queue = pd.concat(review, ignore_index=True)
    queue["human_label"] = ""
    queue["allowed_labels"] = "TRUE_PAPER_EVENT|FALSE_POSITIVE|AMBIGUOUS"
    queue["review_note"] = ""
    csv(queue, "atr_event_manual_review_queue.csv")
    earnings = candidates.loc[candidates.paper_event_category.eq("EARNINGS")].copy()
    earnings["report_period"] = earnings.announcement_title.map(earnings_period)
    filings = earnings.loc[earnings.classification_confidence.eq("TITLE_HIGH_CONFIDENCE")
                           & earnings.report_period.ne("")]
    first = filings.groupby(["stock_code", "report_period"]).agg(
        first_observed_original_disclosure=("announcement_date", "min"),
        original_filing_rows=("announcement_id", "size"),
        original_filing_dates=("announcement_date", "nunique"))
    local_rows = []
    for code in sorted(metadata.stock_code.unique()):
        local = pd.read_csv(ROOT / f"data/cache/profit/{code}.csv",
            usecols=lambda col: col in {"report_date", "announce_date", "REPORT_DATE", "NOTICE_DATE", "REPORT_TYPE"})
        period = "REPORT_DATE" if "REPORT_DATE" in local else "report_date"
        notice = "NOTICE_DATE" if "NOTICE_DATE" in local else "announce_date"
        periods = pd.to_datetime(local[period], errors="coerce")
        notices = pd.to_datetime(local[notice], errors="coerce")
        normalized = pd.DataFrame(dict(report_period=periods.dt.strftime("%Y-%m-%d"),
                                        disclosure=notices.dt.strftime("%Y-%m-%d")))
        normalized = normalized.loc[periods.ge("2019-12-31") & notices.le(CUTOFF)]
        for report_period, group in normalized.groupby("report_period"):
            local_rows.append(dict(stock_code=code, report_period=report_period,
                local_notice_min=group.disclosure.min(), local_notice_max=group.disclosure.max(),
                local_rows=len(group), local_notice_dates=group.disclosure.nunique(), local_field=notice))
    cross = pd.DataFrame(local_rows).merge(first.reset_index(), on=["stock_code", "report_period"], how="outer")
    cross["local_equals_first_observed"] = cross.local_notice_min.eq(cross.first_observed_original_disclosure)
    cross["first_disclosure_status"] = np.where(cross.first_observed_original_disclosure.notna(),
        "FIRST_OBSERVED_ORIGINAL_REPORT_TITLE_NOT_INDEPENDENTLY_VERIFIED",
        "FIRST_DISCLOSURE_UNRESOLVED")
    cross["cache_revision_limit"] = "DB_NORMALIZER_KEEPS_LATEST_VERSION_NOT_GUARANTEED_FIRST_DISCLOSURE"
    csv(cross, "atr_earnings_disclosure_crosscheck.csv")
    counts = candidates.groupby(["stock_code", "stock_year", "paper_event_category"]).size().rename("candidate_count").reset_index()
    csv(counts, "atr_event_category_counts.csv")


def measurement_readiness() -> None:
    _, fixed = fixed_sample()
    listing = pd.read_csv(OUT / "atr_listing_date_probe.csv", dtype={"stock_code": str}).set_index("stock_code")
    status = pd.read_csv(OUT / "atr_full_event_pagination_status.csv", dtype={"stock_code": str})
    complete_keys = {(row.stock_code, row.stock_year) for row in status.itertuples(index=False)
                     if row.status == "EVENT_HISTORY_COMPLETE_METADATA_ONLY"}
    official = pd.read_csv(OUT / "atr_official_dmtr_probe.csv")
    valid_dates = set(official.loc[official.status.eq("VALID_BOUNDED_OFFICIAL_A_SHARE_OBSERVATION")]
                      .groupby("requested_date").filter(lambda group: group.exchange.nunique() == 2).requested_date)
    rows = []
    for code in sorted(fixed.stock_code.unique()):
        frame = pd.read_csv(ROOT / f"data/cache/h7_turnover/baostock/{code}.csv",
            usecols=["trade_date", "baostock_circulating_turnover", "trading_status"])
        frame["trade_date"] = pd.to_datetime(frame.trade_date)
        turnover = pd.to_numeric(frame.baostock_circulating_turnover, errors="coerce")
        trading = pd.to_numeric(frame.trading_status, errors="coerce").eq(1)
        frame = frame.loc[np.isfinite(turnover) & turnover.ge(0) & trading & frame.trade_date.le(CUTOFF)].copy()
        frame["month"] = frame.trade_date.dt.to_period("M")
        listing_date = pd.to_datetime(listing.loc[code, "listing_date"], errors="coerce")
        for month in pd.period_range("2020-01", "2026-08", freq="M"):
            history = frame.loc[frame.month.between(month - 7, month - 1)]
            measured = frame.loc[frame.month.eq(month)]
            seven = history.month.nunique() == 7
            ended = month.end_time.date() < pd.Timestamp(CUTOFF).date()
            ipo_ok = pd.notna(listing_date) and month.start_time >= listing_date + pd.DateOffset(months=6)
            required_dates = pd.concat([history.trade_date, measured.trade_date]).dt.strftime("%Y-%m-%d")
            dmtr_rows = int(required_dates.isin(valid_dates).sum())
            dmtr_ok = len(required_dates) > 0 and dmtr_rows == len(required_dates)
            years = range((month - 7).year, month.year + 1)
            events_ok = all((code, year) in complete_keys for year in years)
            rows.append(dict(stock_code=code, measurement_month=str(month),
                estimation_start=str(month - 7), estimation_end=str(month - 1),
                completed_calendar_month=ended, seven_history_months=seven,
                estimation_nobs=len(history), measurement_nobs=len(measured),
                observed_dmtr_dates=dmtr_rows, required_dmtr_dates=len(required_dates),
                dmtr_complete=dmtr_ok, event_metadata_complete=events_ok,
                event_classification_frozen=False, ipo_six_months_pass=bool(ipo_ok),
                minimum_nobs_threshold="HUMAN_JUDGMENT_NOT_FROZEN",
                calendar_history_candidate=bool(ended and seven and ipo_ok and len(measured)),
                prototype_eligible=False, design_matrix_status="PROTOTYPE_DESIGN_NOT_READY",
                blocker="DAILY_DMTR_NOT_COLLECTED|EVENT_CLASSIFICATION_NOT_FROZEN|DESIGN_RULES_NOT_FROZEN"))
    csv(pd.DataFrame(rows), "atr_measurement_month_readiness.csv")


if __name__ == "__main__":




    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["events", "official", "compare", "ipo", "classify", "readiness"])
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.mode == "events":
        complete_pagination()
    elif args.mode == "official":
        official_raw_probe()
    elif args.mode == "compare":
        resolve_official_and_compare()
    elif args.mode == "ipo":
        probe_missing_listing_dates()
    elif args.mode == "classify":
        classification_and_earnings()
    elif args.mode == "readiness":
        measurement_readiness()
