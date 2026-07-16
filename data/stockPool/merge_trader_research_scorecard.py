import csv
import math
import re
import statistics
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

try:
    import akshare as ak
except Exception:
    ak = None


ROOT = Path(__file__).resolve().parent
INPUT = ROOT / "theme_business_review_completed_after_manual.csv"
if not INPUT.exists():
    INPUT = ROOT / "theme_business_review_completed_after_manual (1).csv"

SCORECARD = ROOT / "theme_stock_research_scorecard.csv"
DEFAULT_POOL = ROOT / "default_pool_candidates.csv"
CONDITIONAL_POOL = ROOT / "conditional_watchlist_candidates.csv"
RISK_FLAGS = ROOT / "financial_liquidity_risk_flags.csv"
MANUAL_REQUIRED = ROOT / "manual_research_required.csv"
QA_REPORT = ROOT / "scorecard_QA_report.md"

ALLOWED = {
    "default_candidate",
    "expanded_candidate",
    "watch_only",
    "reject_for_trading_pool",
    "manual_check",
}

FIELDS = [
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
    "market_source_url",
    "market_source_note",
    "financial_source_url",
    "financial_source_note",
    "valuation_source_url",
    "valuation_source_note",
    "catalyst_source_url",
    "catalyst_source_note",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str] = FIELDS) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([{field: clean(row.get(field, "unknown")) for field in fields} for row in rows])


def clean(value: Any) -> str:
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


def code6(value: str) -> str:
    return str(value).strip().zfill(6)


def em_code(code: str) -> str:
    return ("SH" if code6(code).startswith("6") else "SZ") + code6(code)


def finance_url(code: str) -> str:
    return f"https://emweb.securities.eastmoney.com/PC_HSF10/NewFinanceAnalysis/Index?type=web&code={em_code(code)}"


def num(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if math.isnan(float(value)) or math.isinf(float(value)):
            return None
        return float(value)
    text = str(value).strip().replace("%", "").replace(",", "")
    if text in {"", "unknown", "nan", "None", "False", "--"}:
        return None
    try:
        return float(text)
    except ValueError:
        return cn_amount(text)


def cn_amount(value: Any) -> float | None:
    text = str(value).strip().replace(",", "")
    match = re.match(r"(-?\d+(?:\.\d+)?)(万亿|亿|万)?", text)
    if not match:
        return None
    out = float(match.group(1))
    unit = match.group(2)
    if unit == "万亿":
        return out * 1_000_000_000_000
    if unit == "亿":
        return out * 100_000_000
    if unit == "万":
        return out * 10_000
    return out


def latest_period(columns: list[str], annual: bool) -> str | None:
    periods = [str(c) for c in columns if re.fullmatch(r"\d{8}", str(c))]
    if annual:
        annuals = [p for p in periods if p.endswith("1231")]
        periods = annuals or periods
    return max(periods) if periods else None


def first_metric(frame: Any, metric: str, period: str) -> float | None:
    rows = frame[frame["指标"].astype(str) == metric]
    if rows.empty or period not in frame.columns:
        return None
    return num(rows.iloc[0][period])


def fetch_financial(code: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "revenue_growth_yoy": "unknown",
        "net_profit_growth_yoy": "unknown",
        "gross_margin": "unknown",
        "roe": "unknown",
        "operating_cashflow_to_net_profit": "unknown",
        "receivables_to_revenue": "unknown",
        "inventory_to_revenue": "unknown",
        "debt_to_asset": "unknown",
        "financial_source_url": finance_url(code),
        "financial_source_note": "unknown",
    }
    notes: list[str] = []
    if ak is None:
        result["financial_source_note"] = "akshare unavailable"
        return result
    abstract = None
    period = None
    try:
        abstract = ak.stock_financial_abstract(symbol=code6(code))
        period = latest_period(list(abstract.columns), annual=True)
        if period:
            mapping = {
                "revenue_growth_yoy": "营业总收入增长率",
                "net_profit_growth_yoy": "归属母公司净利润增长率",
                "gross_margin": "毛利率",
                "roe": "净资产收益率(ROE)",
                "operating_cashflow_to_net_profit": "经营活动净现金/归属母公司的净利润",
                "debt_to_asset": "资产负债率",
            }
            for field, metric in mapping.items():
                value = first_metric(abstract, metric, period)
                result[field] = value if value is not None else "unknown"
            notes.append(f"akshare.stock_financial_abstract annual_period={period}")
    except Exception as exc:
        notes.append(f"abstract_error={type(exc).__name__}: {exc}")
    try:
        debt = ak.stock_financial_debt_ths(symbol=code6(code), indicator="按报告期")
        if period:
            candidate = f"{period[:4]}-{period[4:6]}-{period[6:]}"
        else:
            candidate = ""
        if "报告期" in debt.columns and candidate in set(debt["报告期"].astype(str)):
            debt_period = candidate
        else:
            annuals = [x for x in debt["报告期"].astype(str).tolist() if x.endswith("12-31")]
            debt_period = max(annuals) if annuals else str(debt.iloc[0]["报告期"])
        row = debt[debt["报告期"].astype(str) == debt_period].iloc[0]
        revenue = first_metric(abstract, "营业总收入", period) if abstract is not None and period else None
        receivables = cn_amount(row.get("应收票据及应收账款")) or cn_amount(row.get("应收账款"))
        inventory = cn_amount(row.get("存货"))
        if revenue:
            result["receivables_to_revenue"] = receivables / revenue * 100 if receivables is not None else "unknown"
            result["inventory_to_revenue"] = inventory / revenue * 100 if inventory is not None else "unknown"
        notes.append(f"akshare.stock_financial_debt_ths period={debt_period}")
    except Exception as exc:
        notes.append(f"debt_error={type(exc).__name__}: {exc}")
    result["financial_source_note"] = "; ".join(notes) if notes else "unknown"
    return result


def financial_flag(row: dict[str, Any]) -> str:
    vals = {field: num(row.get(field)) for field in [
        "revenue_growth_yoy",
        "net_profit_growth_yoy",
        "gross_margin",
        "roe",
        "operating_cashflow_to_net_profit",
        "receivables_to_revenue",
        "inventory_to_revenue",
        "debt_to_asset",
    ]}
    if vals["net_profit_growth_yoy"] is not None and vals["net_profit_growth_yoy"] < -50:
        return "fail"
    if vals["roe"] is not None and vals["roe"] < -5:
        return "fail"
    if vals["debt_to_asset"] is not None and vals["debt_to_asset"] > 80:
        return "fail"
    if vals["gross_margin"] is not None and vals["gross_margin"] < 0:
        return "fail"
    if vals["operating_cashflow_to_net_profit"] is not None and vals["operating_cashflow_to_net_profit"] < -100:
        return "fail"
    if sum(v is None for v in vals.values()) >= 3:
        return "unknown"
    caution = False
    caution = caution or (vals["revenue_growth_yoy"] is not None and vals["revenue_growth_yoy"] < -20)
    caution = caution or (vals["net_profit_growth_yoy"] is not None and vals["net_profit_growth_yoy"] < 0)
    caution = caution or (vals["roe"] is not None and vals["roe"] < 3)
    caution = caution or (vals["debt_to_asset"] is not None and vals["debt_to_asset"] > 65)
    caution = caution or (vals["operating_cashflow_to_net_profit"] is not None and vals["operating_cashflow_to_net_profit"] < 50)
    caution = caution or (vals["receivables_to_revenue"] is not None and vals["receivables_to_revenue"] > 50)
    caution = caution or (vals["inventory_to_revenue"] is not None and vals["inventory_to_revenue"] > 50)
    return "caution" if caution else "pass"


def final_suggestion(row: dict[str, Any]) -> str:
    if row["is_st"] == "true" or row["suspended_or_zero_volume_flag"] == "true":
        return "reject_for_trading_pool"
    if row["liquidity_flag"] == "fail" or row["financial_quality_flag"] == "fail":
        return "reject_for_trading_pool"
    if row["liquidity_flag"] == "unknown" or row["financial_quality_flag"] == "unknown":
        return "manual_check"
    if row["review_status"] == "core":
        if row["liquidity_flag"] == "pass" and row["financial_quality_flag"] == "pass":
            return "default_candidate"
        return "watch_only"
    if row["review_status"] == "conditional":
        if row["liquidity_flag"] == "pass" and row["financial_quality_flag"] in {"pass", "caution"}:
            return "expanded_candidate"
        return "manual_check"
    return "reject_for_trading_pool"


def main() -> None:
    input_rows = read_csv(INPUT)
    scope = [r for r in input_rows if r["review_status"] in {"core", "conditional"}]
    scope_by_key = {(code6(r["code"]), r["theme"]): r for r in scope}
    a = {(code6(r["code"]), r["theme"]): r for r in read_csv(ROOT / "agent_a_liquidity_metrics.csv")}
    b = {(code6(r["code"]), r["theme"]): r for r in read_csv(ROOT / "agent_b_financial_quality.csv")}
    c = {(code6(r["code"]), r["theme"]): r for r in read_csv(ROOT / "agent_c_catalyst_risk.csv")}
    d = {(code6(r["code"]), r["theme"]): r for r in read_csv(ROOT / "agent_d_valuation_metrics.csv")}

    rows: list[dict[str, Any]] = []
    financial_errors: list[str] = []
    for i, base in enumerate(scope, 1):
        key = (code6(base["code"]), base["theme"])
        liq = a.get(key, {})
        cat = c.get(key, {})
        val = d.get(key, {})
        fin = b.get(key, {})
        if not fin:
            financial_errors.append(f"{key[0]} {key[1]} missing agent_b financial row")
        row: dict[str, Any] = {
            "code": key[0],
            "name": base["name"],
            "theme": base["theme"],
            "review_status": base["review_status"],
            "theme_revenue_materiality": base["theme_revenue_materiality"],
            "primary_business": base["primary_business"],
            "theme_business_description": base["theme_business_description"],
            "market_cap": liq.get("market_cap", "unknown"),
            "avg_amount_20d": liq.get("avg_amount_20d", "unknown"),
            "avg_turnover_20d": liq.get("avg_turnover_20d", "unknown"),
            "return_20d": liq.get("return_20d", "unknown"),
            "return_60d": liq.get("return_60d", "unknown"),
            "volatility_60d": liq.get("volatility_60d", "unknown"),
            "is_st": liq.get("is_st", "unknown"),
            "suspended_or_zero_volume_flag": liq.get("suspended_or_zero_volume_flag", "unknown"),
            "pe_ttm": val.get("pe_ttm", "unknown"),
            "pb": val.get("pb", "unknown"),
            "ps_ttm": val.get("ps_ttm", "unknown"),
            "revenue_growth_yoy": fin.get("revenue_growth_yoy", "unknown"),
            "net_profit_growth_yoy": fin.get("net_profit_growth_yoy", "unknown"),
            "gross_margin": fin.get("gross_margin", "unknown"),
            "roe": fin.get("roe", "unknown"),
            "operating_cashflow_to_net_profit": fin.get("operating_cashflow_to_net_profit", "unknown"),
            "receivables_to_revenue": fin.get("receivables_to_revenue", "unknown"),
            "inventory_to_revenue": fin.get("inventory_to_revenue", "unknown"),
            "debt_to_asset": fin.get("debt_to_asset", "unknown"),
            "liquidity_flag": liq.get("liquidity_flag", "unknown"),
            "valuation_flag": val.get("valuation_flag", "unknown"),
            "catalyst_summary": cat.get("catalyst_summary", "unknown"),
            "risk_note": cat.get("risk_note", "unknown"),
            "market_source_url": liq.get("liquidity_source_url", "unknown"),
            "market_source_note": liq.get("liquidity_source_note", "unknown"),
            "financial_source_url": fin.get("financial_source_url", finance_url(key[0])),
            "financial_source_note": fin.get("financial_source_note", "missing Agent B financial row"),
            "valuation_source_url": val.get("valuation_source_url", "unknown"),
            "valuation_source_note": val.get("valuation_source_note", "unknown"),
            "catalyst_source_url": cat.get("catalyst_source_url", base.get("evidence_url", "unknown")),
            "catalyst_source_note": cat.get("catalyst_source_note", "unknown"),
        }
        row["financial_quality_flag"] = fin.get("financial_quality_flag", financial_flag(row))
        row["final_pool_suggestion"] = final_suggestion(row)
        rows.append(row)
        if i % 20 == 0:
            print(f"merged {i}/{len(scope)}")
        time.sleep(0.001)

    errors: list[str] = []
    if len(rows) != len(scope):
        errors.append(f"row count mismatch: {len(rows)} vs {len(scope)}")
    bad_labels = sorted(set(r["final_pool_suggestion"] for r in rows) - ALLOWED)
    if bad_labels:
        errors.append(f"bad final labels: {bad_labels}")
    dupes = [k for k, v in Counter((r["code"], r["theme"]) for r in rows).items() if v > 1]
    if dupes:
        errors.append(f"duplicate code/theme: {dupes[:10]}")
    contradictions = []
    for r in rows:
        if r["review_status"] == "conditional" and r["final_pool_suggestion"] == "default_candidate":
            contradictions.append(f"{r['code']} {r['name']} conditional default_candidate")
        if r["final_pool_suggestion"] == "default_candidate" and not (
            r["review_status"] == "core"
            and r["liquidity_flag"] == "pass"
            and r["financial_quality_flag"] == "pass"
            and r["is_st"] == "false"
            and r["suspended_or_zero_volume_flag"] == "false"
        ):
            contradictions.append(f"{r['code']} {r['name']} default filter contradiction")
    errors.extend(contradictions)

    write_csv(SCORECARD, rows)
    write_csv(DEFAULT_POOL, [r for r in rows if r["final_pool_suggestion"] == "default_candidate"])
    write_csv(CONDITIONAL_POOL, [r for r in rows if r["final_pool_suggestion"] in {"expanded_candidate", "watch_only", "manual_check"}])
    write_csv(RISK_FLAGS, [
        r for r in rows
        if r["liquidity_flag"] in {"caution", "fail", "unknown"}
        or r["financial_quality_flag"] in {"caution", "fail", "unknown"}
        or r["valuation_flag"] in {"high", "loss_or_negative", "unknown"}
        or r["is_st"] != "false"
        or r["suspended_or_zero_volume_flag"] != "false"
    ])
    write_csv(MANUAL_REQUIRED, [
        r for r in rows
        if r["final_pool_suggestion"] == "manual_check"
        or r["financial_quality_flag"] == "unknown"
        or any(r.get(f) == "unknown" for f in ["market_cap", "avg_amount_20d", "pe_ttm", "revenue_growth_yoy"])
    ])

    missing = {
        f: sum(1 for r in rows if r.get(f) in {"", "unknown", None})
        for f in FIELDS
        if f not in {"risk_note", "catalyst_summary"}
    }
    report = [
        "# Scorecard QA Report",
        "",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Scope",
        f"- Input file: {INPUT.name}",
        f"- Input rows: {len(input_rows)}",
        f"- Researched rows: {len(rows)}",
        f"- Source review_status distribution: {dict(sorted(Counter(r['review_status'] for r in rows).items()))}",
        "",
        "## Output Distribution",
        f"- final_pool_suggestion: {dict(sorted(Counter(r['final_pool_suggestion'] for r in rows).items()))}",
        f"- default_pool_candidates rows: {len(read_csv(DEFAULT_POOL))}",
        f"- conditional_watchlist_candidates rows: {len(read_csv(CONDITIONAL_POOL))}",
        f"- financial_liquidity_risk_flags rows: {len(read_csv(RISK_FLAGS))}",
        f"- manual_research_required rows: {len(read_csv(MANUAL_REQUIRED))}",
        "",
        "## Validation",
        f"- Row count check: {'passed' if len(rows) == len(scope) else 'failed'}",
        f"- Duplicate code/theme check: {'passed' if not dupes else 'failed'}",
        f"- Illegal final_pool_suggestion labels: {bad_labels}",
        f"- Contradiction flags: {len(contradictions)}",
        f"- Validation errors: {len(errors)}",
        "",
        "## Missing Data Counts",
    ]
    present_missing = [(k, v) for k, v in sorted(missing.items()) if v]
    report.extend(f"- {k}: {v}" for k, v in present_missing)
    if not present_missing:
        report.append("- None")
    report.extend([
        "",
        "## Source Notes",
        "- Liquidity data: Agent A, Eastmoney quote and daily kline API.",
        "- Valuation data: Agent D, Eastmoney RPT_VALUEANALYSIS_DET / data.eastmoney.com valuation page.",
        "- Catalyst/risk notes: Agent C, materiality review plus manual audit context.",
        "- Financial quality: Agent B, Eastmoney financial center and Tonghuashun/AkShare financial summaries with missing fields left unknown.",
        "",
        "## Fetch / Calculation Caveats",
    ])
    if financial_errors:
        report.append(f"- Financial endpoint notes containing errors: {len(financial_errors)}; examples: {financial_errors[:10]}")
    else:
        report.append("- No financial endpoint exceptions captured in final merge.")
    report.extend([
        "- This file is a quality-filter and manual-review table only; it is not a buy/sell signal, return forecast, or recommendation.",
        "- Conditional rows are never promoted to default_candidate by rule.",
        "- Core rows only become default_candidate if ST/suspension, liquidity, and financial quality filters pass.",
        "",
        "## Validation Errors",
    ])
    report.extend(f"- {e}" for e in errors) if errors else report.append("- None")
    QA_REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"rows={len(rows)}")
    print(f"suggestions={dict(sorted(Counter(r['final_pool_suggestion'] for r in rows).items()))}")
    print(f"errors={len(errors)}")
    print(f"manual={len(read_csv(MANUAL_REQUIRED))}")


if __name__ == "__main__":
    main()
