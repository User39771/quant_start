import csv
import math
import re
import statistics
import time
from collections import Counter, defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

import requests

try:
    import akshare as ak
except Exception:  # pragma: no cover - handled at runtime
    ak = None


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "theme_business_review_completed_after_manual.csv"
if not INPUT.exists():
    INPUT = ROOT / "theme_business_review_completed_after_manual (1).csv"

SCOPE = ROOT / "research_scope_core_conditional.csv"
SCORECARD = ROOT / "theme_stock_research_scorecard.csv"
DEFAULT_POOL = ROOT / "default_pool_candidates.csv"
CONDITIONAL_POOL = ROOT / "conditional_watchlist_candidates.csv"
RISK_FLAGS = ROOT / "financial_liquidity_risk_flags.csv"
MANUAL_REQUIRED = ROOT / "manual_research_required.csv"
QA_REPORT = ROOT / "scorecard_QA_report.md"

ALLOWED_SUGGESTIONS = {
    "default_candidate",
    "expanded_candidate",
    "watch_only",
    "reject_for_trading_pool",
    "manual_check",
}

BASE_FIELDS = [
    "code",
    "name",
    "theme",
    "review_status",
    "theme_revenue_materiality",
    "primary_business",
    "theme_business_description",
    "market_cap",
    "avg_amount_20d",
    "avg_turnover_20d",
    "return_20d",
    "return_60d",
    "volatility_60d",
    "is_st",
    "suspended_or_zero_volume_flag",
    "pe_ttm",
    "pb",
    "ps_ttm",
    "revenue_growth_yoy",
    "net_profit_growth_yoy",
    "gross_margin",
    "roe",
    "operating_cashflow_to_net_profit",
    "receivables_to_revenue",
    "inventory_to_revenue",
    "debt_to_asset",
    "financial_quality_flag",
    "liquidity_flag",
    "valuation_flag",
    "catalyst_summary",
    "risk_note",
    "final_pool_suggestion",
]

SOURCE_FIELDS = [
    "market_source_url",
    "market_source_note",
    "financial_source_url",
    "financial_source_note",
    "valuation_source_url",
    "valuation_source_note",
    "catalyst_source_url",
    "catalyst_source_note",
]

OUTPUT_FIELDS = BASE_FIELDS + SOURCE_FIELDS


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] = OUTPUT_FIELDS) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([{k: normalize_cell(row.get(k, "unknown")) for k in fields} for row in rows])


def normalize_cell(value: Any) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "unknown"
        return f"{value:.6g}"
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text if text else "unknown"


def zcode(code: str) -> str:
    return str(code).strip().zfill(6)


def secid(code: str) -> str:
    c = zcode(code)
    market = "1" if c.startswith(("6", "9")) else "0"
    return f"{market}.{c}"


def em_code(code: str) -> str:
    c = zcode(code)
    prefix = "SH" if c.startswith(("6", "9")) else "SZ"
    return f"{prefix}{c}"


def quote_url(code: str) -> str:
    return f"http://push2.eastmoney.com/api/qt/stock/get?secid={secid(code)}"


def kline_url(code: str) -> str:
    return f"http://push2his.eastmoney.com/api/qt/stock/kline/get?secid={secid(code)}&klt=101&fqt=1"


def finance_url(code: str) -> str:
    return f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index?type=web&code={em_code(code)}"


def request_json(url: str, params: dict[str, Any], timeout: int = 18) -> dict[str, Any]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://quote.eastmoney.com/",
    }
    response = requests.get(url, params=params, timeout=timeout, headers=headers)
    response.raise_for_status()
    payload = response.json()
    if payload.get("rc") not in (0, None):
        raise RuntimeError(f"Eastmoney rc={payload.get('rc')}")
    return payload


def fetch_spot_all() -> dict[str, dict[str, Any]]:
    url = "http://push2.eastmoney.com/api/qt/clist/get"
    fields = "f12,f14,f20,f21,f8,f9,f23,f115"
    fs = "m:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048"
    payload = request_json(
        url,
        {
            "pn": 1,
            "pz": 6000,
            "po": 1,
            "np": 1,
            "ut": "bd1d9ddb04089700cf9c27f6f7426281",
            "fltt": 2,
            "invt": 2,
            "fid": "f12",
            "fs": fs,
            "fields": fields,
        },
    )
    diff = payload.get("data", {}).get("diff") or []
    return {zcode(item.get("f12", "")): item for item in diff}


def fetch_kline_metrics(code: str) -> dict[str, Any]:
    payload = request_json(
        "http://push2his.eastmoney.com/api/qt/stock/kline/get",
        {
            "secid": secid(code),
            "fields1": "f1,f2,f3,f4,f5,f6",
            "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
            "klt": "101",
            "fqt": "1",
            "beg": "20240101",
            "end": "20500101",
        },
    )
    klines = payload.get("data", {}).get("klines") or []
    parsed: list[dict[str, float | str]] = []
    for line in klines:
        parts = line.split(",")
        if len(parts) < 11:
            continue
        try:
            parsed.append(
                {
                    "date": parts[0],
                    "close": float(parts[2]),
                    "volume": float(parts[5]),
                    "amount": float(parts[6]),
                    "pct": float(parts[8]),
                    "turnover": float(parts[10]),
                }
            )
        except ValueError:
            continue
    if not parsed:
        return {
            "avg_amount_20d": "unknown",
            "avg_turnover_20d": "unknown",
            "return_20d": "unknown",
            "return_60d": "unknown",
            "volatility_60d": "unknown",
            "suspended_or_zero_volume_flag": "true",
            "market_source_note": "Eastmoney kline returned no usable rows",
        }

    last20 = parsed[-20:]
    last60 = parsed[-60:]
    avg_amount_20d = statistics.fmean(float(r["amount"]) for r in last20) if last20 else math.nan
    avg_turnover_20d = statistics.fmean(float(r["turnover"]) for r in last20) if last20 else math.nan
    zero_or_missing = len(last20) < 10 or all(float(r["amount"]) <= 0 or float(r["volume"]) <= 0 for r in last20)

    def period_return(period: int) -> Any:
        if len(parsed) <= period:
            return "unknown"
        start = float(parsed[-period - 1]["close"])
        end = float(parsed[-1]["close"])
        if start == 0:
            return "unknown"
        return (end / start - 1) * 100

    vol = "unknown"
    if len(last60) >= 20:
        daily = [float(r["pct"]) for r in last60]
        vol = statistics.pstdev(daily) * math.sqrt(244)

    return {
        "avg_amount_20d": avg_amount_20d,
        "avg_turnover_20d": avg_turnover_20d,
        "return_20d": period_return(20),
        "return_60d": period_return(60),
        "volatility_60d": vol,
        "suspended_or_zero_volume_flag": "true" if zero_or_missing else "false",
        "market_source_note": f"Eastmoney daily qfq kline; latest_trade_date={parsed[-1]['date']}; rows={len(parsed)}; generated={date.today().isoformat()}",
    }


def parse_cn_amount(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    text = str(value).strip().replace(",", "")
    if not text or text in {"False", "false", "None", "nan", "--"}:
        return None
    match = re.match(r"(-?\d+(?:\.\d+)?)(万亿|亿|万)?", text)
    if not match:
        return None
    number = float(match.group(1))
    unit = match.group(2)
    if unit == "万亿":
        return number * 1_000_000_000_000
    if unit == "亿":
        return number * 100_000_000
    if unit == "万":
        return number * 10_000
    return number


def num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(float(value)) or math.isinf(float(value)):
            return None
        return float(value)
    text = str(value).strip().replace("%", "").replace(",", "")
    if not text or text in {"False", "false", "None", "nan", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return parse_cn_amount(text)


def first_metric(frame: Any, metric: str, period: str) -> float | None:
    if frame is None or getattr(frame, "empty", True):
        return None
    rows = frame[frame["指标"].astype(str) == metric]
    if rows.empty or period not in frame.columns:
        return None
    return num(rows.iloc[0][period])


def latest_period(columns: list[str], annual: bool = False) -> str | None:
    candidates = [c for c in columns if re.fullmatch(r"\d{8}", str(c))]
    if annual:
        annuals = [c for c in candidates if str(c).endswith("1231")]
        candidates = annuals or candidates
    return max(candidates) if candidates else None


def fetch_financial_metrics(code: str) -> dict[str, Any]:
    if ak is None:
        return {"financial_source_note": "akshare unavailable"}
    c = zcode(code)
    source_bits = []
    result: dict[str, Any] = {
        "revenue_growth_yoy": "unknown",
        "net_profit_growth_yoy": "unknown",
        "gross_margin": "unknown",
        "roe": "unknown",
        "operating_cashflow_to_net_profit": "unknown",
        "receivables_to_revenue": "unknown",
        "inventory_to_revenue": "unknown",
        "debt_to_asset": "unknown",
    }
    abstract = None
    period = None
    try:
        abstract = ak.stock_financial_abstract(symbol=c)
        period = latest_period(list(abstract.columns), annual=True)
        if period:
            result["revenue_growth_yoy"] = first_metric(abstract, "营业总收入增长率", period)
            result["net_profit_growth_yoy"] = first_metric(abstract, "归属母公司净利润增长率", period)
            result["gross_margin"] = first_metric(abstract, "毛利率", period)
            result["roe"] = first_metric(abstract, "净资产收益率(ROE)", period)
            result["operating_cashflow_to_net_profit"] = first_metric(abstract, "经营活动净现金/归属母公司的净利润", period)
            result["debt_to_asset"] = first_metric(abstract, "资产负债率", period)
            source_bits.append(f"akshare.stock_financial_abstract period={period}")
    except Exception as exc:
        source_bits.append(f"abstract_error={type(exc).__name__}: {exc}")

    try:
        debt = ak.stock_financial_debt_ths(symbol=c, indicator="按报告期")
        debt_period = None
        if period and "报告期" in debt.columns and period[0:4] + "-" + period[4:6] + "-" + period[6:8] in set(debt["报告期"].astype(str)):
            debt_period = period[0:4] + "-" + period[4:6] + "-" + period[6:8]
        elif "报告期" in debt.columns:
            annual_rows = [x for x in debt["报告期"].astype(str).tolist() if x.endswith("12-31")]
            debt_period = max(annual_rows) if annual_rows else str(debt.iloc[0]["报告期"])
        if debt_period:
            drow = debt[debt["报告期"].astype(str) == debt_period].iloc[0]
            receivables = parse_cn_amount(drow.get("应收票据及应收账款")) or parse_cn_amount(drow.get("应收账款"))
            inventory = parse_cn_amount(drow.get("存货"))
            revenue = first_metric(abstract, "营业总收入", period) if abstract is not None and period else None
            if revenue and revenue != 0:
                result["receivables_to_revenue"] = receivables / revenue * 100 if receivables is not None else "unknown"
                result["inventory_to_revenue"] = inventory / revenue * 100 if inventory is not None else "unknown"
            source_bits.append(f"akshare.stock_financial_debt_ths period={debt_period}")
    except Exception as exc:
        source_bits.append(f"debt_error={type(exc).__name__}: {exc}")

    result["financial_source_note"] = "; ".join(source_bits) if source_bits else "unknown"
    return result


def flag_liquidity(row: dict[str, Any]) -> str:
    if row.get("suspended_or_zero_volume_flag") == "true":
        return "fail"
    amount = num(row.get("avg_amount_20d"))
    market_cap = num(row.get("market_cap"))
    turnover = num(row.get("avg_turnover_20d"))
    if amount is None or market_cap is None:
        return "unknown"
    if amount >= 100_000_000 and market_cap >= 5_000_000_000 and (turnover is None or turnover >= 0.3):
        return "pass"
    if amount >= 30_000_000 and market_cap >= 2_000_000_000:
        return "caution"
    return "fail"


def flag_financial(row: dict[str, Any]) -> str:
    values = {k: num(row.get(k)) for k in [
        "revenue_growth_yoy",
        "net_profit_growth_yoy",
        "gross_margin",
        "roe",
        "operating_cashflow_to_net_profit",
        "receivables_to_revenue",
        "inventory_to_revenue",
        "debt_to_asset",
    ]}
    if values["net_profit_growth_yoy"] is not None and values["net_profit_growth_yoy"] < -50:
        return "fail"
    if values["roe"] is not None and values["roe"] < -5:
        return "fail"
    if values["debt_to_asset"] is not None and values["debt_to_asset"] > 80:
        return "fail"
    if values["gross_margin"] is not None and values["gross_margin"] < 0:
        return "fail"
    if values["operating_cashflow_to_net_profit"] is not None and values["operating_cashflow_to_net_profit"] < -100:
        return "fail"

    missing = sum(v is None for v in values.values())
    caution = missing >= 3
    caution = caution or (values["revenue_growth_yoy"] is not None and values["revenue_growth_yoy"] < -20)
    caution = caution or (values["net_profit_growth_yoy"] is not None and values["net_profit_growth_yoy"] < 0)
    caution = caution or (values["roe"] is not None and values["roe"] < 3)
    caution = caution or (values["debt_to_asset"] is not None and values["debt_to_asset"] > 65)
    caution = caution or (values["operating_cashflow_to_net_profit"] is not None and values["operating_cashflow_to_net_profit"] < 50)
    caution = caution or (values["receivables_to_revenue"] is not None and values["receivables_to_revenue"] > 50)
    caution = caution or (values["inventory_to_revenue"] is not None and values["inventory_to_revenue"] > 50)
    return "caution" if caution else "pass"


def flag_valuation(row: dict[str, Any]) -> str:
    pe = num(row.get("pe_ttm"))
    pb = num(row.get("pb"))
    ps = num(row.get("ps_ttm"))
    if pe is not None and pe <= 0:
        return "loss_or_negative"
    if pe is None and pb is None and ps is None:
        return "unknown"
    if (pe is not None and pe > 100) or (pb is not None and pb > 15) or (ps is not None and ps > 30):
        return "high"
    return "normal"


def suggestion(row: dict[str, Any]) -> str:
    critical_unknown = any(row.get(k) in {"unknown", ""} for k in ["market_cap", "avg_amount_20d", "financial_quality_flag"])
    if row.get("is_st") == "true" or row.get("suspended_or_zero_volume_flag") == "true":
        return "reject_for_trading_pool"
    if row.get("liquidity_flag") == "fail" or row.get("financial_quality_flag") == "fail":
        return "reject_for_trading_pool"
    if critical_unknown or row.get("liquidity_flag") == "unknown" or row.get("financial_quality_flag") == "unknown":
        return "manual_check"
    if row.get("review_status") == "core":
        if row.get("liquidity_flag") == "pass" and row.get("financial_quality_flag") == "pass":
            return "default_candidate"
        return "watch_only"
    if row.get("review_status") == "conditional":
        if row.get("liquidity_flag") == "pass" and row.get("financial_quality_flag") in {"pass", "caution"}:
            return "expanded_candidate"
        return "manual_check"
    return "reject_for_trading_pool"


def summarize_catalyst(row: dict[str, str]) -> tuple[str, str]:
    materiality = row.get("theme_revenue_materiality", "unknown")
    status = row.get("review_status", "unknown")
    desc = row.get("theme_business_description", "")
    business = row.get("primary_business", "")
    evidence = row.get("evidence_summary", "")
    if status == "core":
        catalyst = f"跟踪主题业务是否继续体现在主营/收入分部中；当前业务基础：{desc or business}"
    else:
        catalyst = f"跟踪主题业务从方案/项目向可量化收入转化；当前业务基础：{desc or business}"
    risk_parts = []
    if status == "conditional":
        risk_parts.append("conditional 行默认不进入默认池，主题收入贡献仍需复核")
    if materiality != "core":
        risk_parts.append(f"theme_revenue_materiality={materiality}，材料性不等同于核心主营")
    if evidence:
        risk_parts.append(f"业务证据摘要：{evidence[:120]}")
    return catalyst[:500], "；".join(risk_parts)[:700] if risk_parts else "需持续核对公告、年报和订单披露，避免概念标签替代收入证据"


def build_scorecard() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    input_rows = read_csv(INPUT)
    scope = [row for row in input_rows if row.get("review_status") in {"core", "conditional"}]
    with SCOPE.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(input_rows[0].keys()))
        writer.writeheader()
        writer.writerows(scope)

    spot_errors: list[str] = []
    try:
        spot = fetch_spot_all()
    except Exception as exc:
        spot = {}
        spot_errors.append(f"spot_all_error={type(exc).__name__}: {exc}")

    rows: list[dict[str, Any]] = []
    market_errors: list[str] = []
    financial_errors: list[str] = []
    for idx, source in enumerate(scope, 1):
        c = zcode(source["code"])
        row: dict[str, Any] = {
            "code": c,
            "name": source.get("name", ""),
            "theme": source.get("theme", ""),
            "review_status": source.get("review_status", ""),
            "theme_revenue_materiality": source.get("theme_revenue_materiality", ""),
            "primary_business": source.get("primary_business", ""),
            "theme_business_description": source.get("theme_business_description", ""),
            "market_source_url": f"{quote_url(c)} | {kline_url(c)}",
            "financial_source_url": finance_url(c),
            "valuation_source_url": quote_url(c),
            "catalyst_source_url": source.get("evidence_url") or "unknown",
            "catalyst_source_note": f"business materiality review evidence_level={source.get('evidence_level', 'unknown')}",
        }

        s = spot.get(c, {})
        row["market_cap"] = s.get("f20", "unknown")
        row["pe_ttm"] = s.get("f115", "unknown")
        row["pb"] = s.get("f23", "unknown")
        row["ps_ttm"] = "unknown"
        row["is_st"] = "true" if "ST" in str(s.get("f14") or source.get("name", "")).upper() else "false"
        row["valuation_source_note"] = "Eastmoney clist f115=PE_TTM, f23=PB; PS unavailable in clist and left unknown"
        try:
            quote = request_json(
                "http://push2.eastmoney.com/api/qt/stock/get",
                {
                    "secid": secid(c),
                    "fields": "f58,f116,f162,f167,f173",
                },
            ).get("data", {})
            if quote.get("f116") not in (None, "-", ""):
                row["market_cap"] = quote.get("f116")
            if row.get("pe_ttm") in (None, "-", "", "unknown") and quote.get("f162") not in (None, "-", ""):
                raw_pe = num(quote.get("f162"))
                row["pe_ttm"] = raw_pe / 100 if raw_pe is not None and raw_pe > 300 else raw_pe
            if row.get("pb") in (None, "-", "", "unknown") and quote.get("f167") not in (None, "-", ""):
                raw_pb = num(quote.get("f167"))
                row["pb"] = raw_pb / 100 if raw_pb is not None and raw_pb > 100 else raw_pb
            if quote.get("f173") not in (None, "-", ""):
                row["ps_ttm"] = quote.get("f173")
            row["valuation_source_note"] = "Eastmoney quote/clist: f115 PE_TTM when available; fallback f162 dynamic PE; f167 PB; f173 PS"
        except Exception as exc:
            market_errors.append(f"{c} quote_error={type(exc).__name__}: {exc}")

        try:
            row.update(fetch_kline_metrics(c))
        except Exception as exc:
            market_errors.append(f"{c} kline_error={type(exc).__name__}: {exc}")
            row.update(
                {
                    "avg_amount_20d": "unknown",
                    "avg_turnover_20d": "unknown",
                    "return_20d": "unknown",
                    "return_60d": "unknown",
                    "volatility_60d": "unknown",
                    "suspended_or_zero_volume_flag": "unknown",
                    "market_source_note": f"kline_error={type(exc).__name__}: {exc}",
                }
            )

        try:
            row.update(fetch_financial_metrics(c))
        except Exception as exc:
            financial_errors.append(f"{c} financial_error={type(exc).__name__}: {exc}")
            row["financial_source_note"] = f"financial_error={type(exc).__name__}: {exc}"
            for field in [
                "revenue_growth_yoy",
                "net_profit_growth_yoy",
                "gross_margin",
                "roe",
                "operating_cashflow_to_net_profit",
                "receivables_to_revenue",
                "inventory_to_revenue",
                "debt_to_asset",
            ]:
                row[field] = "unknown"

        row["liquidity_flag"] = flag_liquidity(row)
        row["financial_quality_flag"] = flag_financial(row)
        row["valuation_flag"] = flag_valuation(row)
        row["catalyst_summary"], row["risk_note"] = summarize_catalyst(source)
        row["final_pool_suggestion"] = suggestion(row)
        rows.append(row)

        if idx % 20 == 0:
            print(f"processed {idx}/{len(scope)}")
        time.sleep(0.05)

    diagnostics = {
        "input_rows": len(input_rows),
        "scope_rows": len(scope),
        "spot_errors": spot_errors,
        "market_errors": market_errors,
        "financial_errors": financial_errors,
    }
    return rows, diagnostics


def validate(rows: list[dict[str, Any]], diagnostics: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if len(rows) != diagnostics["scope_rows"]:
        errors.append(f"row_count_mismatch expected {diagnostics['scope_rows']} got {len(rows)}")
    key_counts = Counter((r["code"], r["theme"]) for r in rows)
    dupes = [k for k, v in key_counts.items() if v > 1]
    if dupes:
        errors.append(f"duplicate code/theme keys: {dupes[:10]}")
    bad_suggestions = sorted(set(r["final_pool_suggestion"] for r in rows) - ALLOWED_SUGGESTIONS)
    if bad_suggestions:
        errors.append(f"bad final_pool_suggestion labels: {bad_suggestions}")
    for row in rows:
        if row["review_status"] == "conditional" and row["final_pool_suggestion"] == "default_candidate":
            errors.append(f"{row['code']} {row['theme']} conditional promoted to default_candidate")
        if row["final_pool_suggestion"] == "default_candidate":
            if row["review_status"] != "core" or row["liquidity_flag"] != "pass" or row["financial_quality_flag"] != "pass":
                errors.append(f"{row['code']} {row['theme']} default_candidate failed required filters")
            if row["is_st"] == "true" or row["suspended_or_zero_volume_flag"] == "true":
                errors.append(f"{row['code']} {row['theme']} default_candidate has ST/suspension flag")
    return errors


def write_outputs(rows: list[dict[str, Any]], diagnostics: dict[str, Any], validation_errors: list[str]) -> None:
    write_csv(SCORECARD, rows)
    write_csv(DEFAULT_POOL, [r for r in rows if r["final_pool_suggestion"] == "default_candidate"])
    write_csv(
        CONDITIONAL_POOL,
        [r for r in rows if r["final_pool_suggestion"] in {"expanded_candidate", "watch_only", "manual_check"}],
    )
    write_csv(
        RISK_FLAGS,
        [
            r
            for r in rows
            if r["liquidity_flag"] in {"caution", "fail", "unknown"}
            or r["financial_quality_flag"] in {"caution", "fail", "unknown"}
            or r["valuation_flag"] in {"high", "loss_or_negative", "unknown"}
            or r["is_st"] == "true"
            or r["suspended_or_zero_volume_flag"] in {"true", "unknown"}
        ],
    )
    write_csv(
        MANUAL_REQUIRED,
        [
            r
            for r in rows
            if r["final_pool_suggestion"] == "manual_check"
            or any(r.get(k) == "unknown" for k in ["market_cap", "avg_amount_20d", "revenue_growth_yoy", "pe_ttm"])
        ],
    )

    dist = Counter(r["final_pool_suggestion"] for r in rows)
    status_dist = Counter(r["review_status"] for r in rows)
    missing_by_col = {
        field: sum(1 for r in rows if r.get(field) in {"unknown", "", None})
        for field in BASE_FIELDS
        if field not in {"ps_ttm"}
    }
    missing_by_col["ps_ttm"] = sum(1 for r in rows if r.get("ps_ttm") in {"unknown", "", None})
    contradictions = []
    for r in rows:
        if r["review_status"] == "core" and r["final_pool_suggestion"] == "default_candidate" and r["theme_revenue_materiality"] == "immaterial":
            contradictions.append(f"{r['code']} {r['name']} core/default but immaterial")
        if r["review_status"] == "conditional" and r["final_pool_suggestion"] == "default_candidate":
            contradictions.append(f"{r['code']} {r['name']} conditional/default")

    report = [
        "# Scorecard QA Report",
        "",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Scope",
        "",
        f"- Input file: {INPUT.name}",
        f"- Input rows: {diagnostics['input_rows']}",
        f"- Researched rows: {len(rows)} (review_status in core/conditional)",
        f"- Review status distribution: {dict(sorted(status_dist.items()))}",
        "",
        "## Output Distribution",
        "",
        f"- final_pool_suggestion: {dict(sorted(dist.items()))}",
        f"- default_pool_candidates rows: {sum(1 for r in rows if r['final_pool_suggestion'] == 'default_candidate')}",
        f"- conditional_watchlist_candidates rows: {sum(1 for r in rows if r['final_pool_suggestion'] in {'expanded_candidate', 'watch_only', 'manual_check'})}",
        f"- financial_liquidity_risk_flags rows: {len(read_csv(RISK_FLAGS))}",
        f"- manual_research_required rows: {len(read_csv(MANUAL_REQUIRED))}",
        "",
        "## Data Sources",
        "",
        "- Market/liquidity/valuation: Eastmoney quote and daily qfq kline HTTP endpoints.",
        "- Financial quality: AkShare stock_financial_abstract and stock_financial_debt_ths where available.",
        "- Catalyst/risk notes: reviewed business-materiality evidence in the input CSV.",
        "",
        "## Validation",
        "",
        f"- Row-count check: {'passed' if len(rows) == diagnostics['scope_rows'] else 'failed'}",
        f"- Duplicate code/theme check: {'passed' if not any(v > 1 for v in Counter((r['code'], r['theme']) for r in rows).values()) else 'failed'}",
        f"- Illegal final_pool_suggestion labels: {sorted(set(r['final_pool_suggestion'] for r in rows) - ALLOWED_SUGGESTIONS)}",
        f"- Contradiction flags: {len(contradictions)}",
        f"- Validation errors: {len(validation_errors)}",
        "",
        "## Missing Data Counts",
        "",
    ]
    report.extend(f"- {k}: {v}" for k, v in sorted(missing_by_col.items()) if v)
    if not any(missing_by_col.values()):
        report.append("- None")
    report.extend(["", "## Fetch Errors", ""])
    if diagnostics["spot_errors"]:
        report.extend(f"- {x}" for x in diagnostics["spot_errors"][:20])
    if diagnostics["market_errors"]:
        report.append(f"- Market endpoint row-level errors: {len(diagnostics['market_errors'])}; first examples: {diagnostics['market_errors'][:10]}")
    if diagnostics["financial_errors"]:
        report.append(f"- Financial endpoint row-level errors: {len(diagnostics['financial_errors'])}; first examples: {diagnostics['financial_errors'][:10]}")
    if not diagnostics["spot_errors"] and not diagnostics["market_errors"] and not diagnostics["financial_errors"]:
        report.append("- None")
    report.extend(["", "## Contradictions", ""])
    report.extend(f"- {x}" for x in contradictions) if contradictions else report.append("- None")
    report.extend(["", "## Validation Errors", ""])
    report.extend(f"- {x}" for x in validation_errors) if validation_errors else report.append("- None")
    report.extend(
        [
            "",
            "## Caveats",
            "",
            "- This scorecard is a quality-filtering and manual-review aid only. It is not a buy/sell signal, return forecast, or stock recommendation.",
            "- Some valuation values come from real-time quote fields and can change intraday.",
            "- PS_TTM is sourced from Eastmoney quote field f173 when available; where unavailable it is left unknown.",
            "- Financial quality uses latest available annual period when present; missing or endpoint-failed fields are not imputed.",
        ]
    )
    QA_REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")


def main() -> None:
    rows, diagnostics = build_scorecard()
    validation_errors = validate(rows, diagnostics)
    write_outputs(rows, diagnostics, validation_errors)
    print(f"scorecard_rows={len(rows)}")
    print(f"suggestions={dict(sorted(Counter(r['final_pool_suggestion'] for r in rows).items()))}")
    print(f"validation_errors={len(validation_errors)}")
    print(f"market_errors={len(diagnostics['market_errors'])}")
    print(f"financial_errors={len(diagnostics['financial_errors'])}")


if __name__ == "__main__":
    main()
