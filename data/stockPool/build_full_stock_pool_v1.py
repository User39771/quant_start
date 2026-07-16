import csv
import math
import re
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import akshare as ak
import requests
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
SCORECARD = ROOT / "theme_stock_research_scorecard.csv"
RULES = ROOT / "stock_pool_rules.csv"
PREVIOUS_EVIDENCE = ROOT / "annual_report_evidence_check.csv"
CACHE = ROOT / "annual_report_cache"
CACHE.mkdir(exist_ok=True)

OUT_FULL = ROOT / "annual_report_evidence_check_full_119.csv"
OUT_SUGGEST = ROOT / "pool_decision_suggestions_full_119.csv"
OUT_DEFAULT = ROOT / "default_pool_v1.csv"
OUT_EXPANDED = ROOT / "expanded_pool_v1.csv"
OUT_WATCH = ROOT / "watch_pool_v1.csv"
OUT_EX_RULES = ROOT / "excluded_by_rules_v1.csv"
OUT_EX_BIZ = ROOT / "excluded_by_business_mismatch_v1.csv"
OUT_QA = ROOT / "stock_pool_v1_QA_report.md"

BUSINESS_LABELS = {"theme_confirmed", "theme_partial", "theme_weak", "theme_rejected"}
TRADING_LABELS = {"default", "expanded", "watch", "excluded_by_rules", "excluded_by_business_mismatch"}
STRENGTH_LABELS = {"strong", "medium", "weak", "missing"}

FIELDS = [
    "code",
    "name",
    "theme",
    "current_review_status",
    "current_final_pool_suggestion",
    "theme_business_claim",
    "annual_report_business_evidence",
    "annual_report_revenue_evidence",
    "order_or_customer_evidence",
    "product_evidence",
    "financial_risk_evidence",
    "evidence_source",
    "evidence_url",
    "evidence_report_period",
    "evidence_strength",
    "business_evidence_decision",
    "trading_pool_decision",
    "answer_q1_external_sales",
    "answer_q2_disclosure_support",
    "answer_q3_financial_risk",
    "answer_q4_pool_decision",
    "decision_reason",
    "falsification_condition",
    "manual_followup_needed",
]

SUGGEST_FIELDS = [
    "code",
    "name",
    "theme",
    "current_review_status",
    "current_final_pool_suggestion",
    "evidence_strength",
    "business_evidence_decision",
    "trading_pool_decision",
    "answer_q3_financial_risk",
    "decision_reason",
    "manual_followup_needed",
    "evidence_url",
]

OFFICIAL_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Referer": "http://www.cninfo.com.cn/",
}

AI_KEYWORDS = [
    "人工智能",
    "AIGC",
    "算力",
    "智算",
    "大模型",
    "智能体",
    "AI服务器",
    "服务器",
    "GPU",
    "算法",
    "机器视觉",
    "智能语音",
    "数据中心",
    "AIoT",
]
SPACE_KEYWORDS = [
    "商业航天",
    "航天",
    "卫星",
    "卫星互联网",
    "北斗",
    "导航",
    "GNSS",
    "遥感",
    "雷达",
    "星载",
    "宇航",
    "射频",
    "载荷",
    "惯性导航",
]
REVENUE_TERMS = ["收入", "营收", "销售", "营业收入", "主营业务收入", "实现收入"]
ORDER_TERMS = ["订单", "客户", "合同", "中标", "交付", "供货", "供应", "项目", "应用于", "服务于"]
PRODUCT_TERMS = ["产品", "系统", "平台", "解决方案", "模块", "芯片", "设备", "终端", "软件", "服务"]
WEAK_CONTEXT_TERMS = ["释义", "定义", "风险提示", "未来", "规划", "战略", "积极探索", "拟", "可能"]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows([{field: clean(row.get(field, "unknown")) for field in fields} for row in rows])


def clean(value) -> str:
    if value is None:
        return "unknown"
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return "unknown"
        return f"{value:.6g}"
    text = str(value).replace("\r", " ").replace("\n", " ").strip()
    text = re.sub(r"\s+", " ", text)
    return text if text else "unknown"


def code6(code: str) -> str:
    return str(code).strip().zfill(6)


def num(value) -> float | None:
    text = clean(value).replace(",", "")
    if text in {"unknown", "--", ""}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def latest_report(code: str) -> dict[str, str]:
    df = ak.stock_zh_a_disclosure_report_cninfo(
        symbol=code6(code),
        market="沪深京",
        category="年报",
        start_date="20240101",
        end_date="20260702",
    )
    if df.empty:
        return {}
    reports = df[df["公告标题"].astype(str).str.contains("年度报告", regex=False)]
    reports = reports[~reports["公告标题"].astype(str).str.contains("摘要", regex=False)]
    if reports.empty:
        reports = df
    row = reports.sort_values("公告时间", ascending=False).iloc[0]
    link = str(row["公告链接"])
    parsed = parse_qs(urlparse(link).query)
    org_id = parsed.get("orgId", [""])[0]
    announcement_id = parsed.get("announcementId", [""])[0]
    adjunct = raw_adjunct_url(code6(code), org_id, announcement_id)
    pdf_url = f"http://static.cninfo.com.cn/{adjunct}" if adjunct else ""
    return {
        "title": str(row["公告标题"]),
        "time": str(row["公告时间"])[:10],
        "detail_url": link,
        "pdf_url": pdf_url,
        "org_id": org_id,
        "announcement_id": announcement_id,
    }


def raw_adjunct_url(code: str, org_id: str, announcement_id: str) -> str:
    if not org_id:
        return ""
    payload = {
        "pageNum": "1",
        "pageSize": "30",
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{code},{org_id}",
        "searchkey": "",
        "secid": "",
        "category": "category_ndbg_szsh",
        "trade": "",
        "seDate": "2024-01-01~2026-07-02",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    response = requests.post(
        "http://www.cninfo.com.cn/new/hisAnnouncement/query",
        data=payload,
        headers=OFFICIAL_HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    for item in response.json().get("announcements") or []:
        if str(item.get("announcementId")) == str(announcement_id):
            return str(item.get("adjunctUrl") or "")
    return ""


def download_pdf(code: str, report: dict[str, str]) -> Path | None:
    if not report.get("pdf_url"):
        return None
    target = CACHE / f"{code6(code)}_{report['announcement_id']}.pdf"
    if target.exists() and target.stat().st_size > 100_000:
        return target
    response = requests.get(report["pdf_url"], headers=OFFICIAL_HEADERS, timeout=90)
    response.raise_for_status()
    if not response.content.startswith(b"%PDF"):
        return None
    target.write_bytes(response.content)
    return target


def extract_pdf_text(path: Path, max_pages: int = 260) -> str:
    reader = PdfReader(str(path))
    chunks: list[str] = []
    for page in reader.pages[:max_pages]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            chunks.append(text)
    return re.sub(r"\s+", " ", "\n".join(chunks))


def infer_period(title: str, report_time: str) -> str:
    match = re.search(r"(20\d{2})年年度报告", title)
    if match:
        return f"{match.group(1)}年度"
    return report_time or "unknown"


def keywords_for(row: dict[str, str]) -> list[str]:
    base = AI_KEYWORDS if row["theme"] == "AI" else SPACE_KEYWORDS
    claim = row.get("theme_business_description", "") + " " + row.get("primary_business", "")
    extra: list[str] = []
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", claim):
        if token in {"公司", "业务", "相关", "产品", "服务", "收入", "主营", "应用"}:
            continue
        if any(token in kw or kw in token for kw in base):
            extra.append(token)
    out: list[str] = []
    for token in base + extra:
        if token not in out:
            out.append(token)
    return out


def snippets(text: str, keywords: list[str], required_terms: list[str] | None = None, limit: int = 3) -> list[str]:
    out: list[str] = []
    for kw in keywords:
        flags = 0 if re.search(r"[\u4e00-\u9fff]", kw) else re.IGNORECASE
        for match in re.finditer(re.escape(kw), text, flags=flags):
            start = max(0, match.start() - 120)
            end = min(len(text), match.end() + 180)
            snip = text[start:end].strip()
            if required_terms and not any(term in snip for term in required_terms):
                continue
            if not is_meaningful_snippet(snip, required_terms):
                continue
            if snip and all(snip[:90] not in existing for existing in out):
                out.append(snip)
            if len(out) >= limit:
                return out
    return out


def is_meaningful_snippet(snip: str, required_terms: list[str] | None) -> bool:
    if len(snip) < 30:
        return False
    # 纯释义段或风险段不能单独支持 strong，但若同时有收入/订单/产品词可保留为辅助。
    if required_terms is None and any(term in snip[:80] for term in ["释义项", "释义内容", "目录"]):
        return False
    if required_terms is None and sum(term in snip for term in WEAK_CONTEXT_TERMS) >= 3:
        return False
    return True


def evidence_from_text(row: dict[str, str], text: str) -> dict[str, object]:
    kws = keywords_for(row)
    business = snippets(text, kws, limit=3)
    revenue = snippets(text, kws, REVENUE_TERMS, limit=2)
    orders = snippets(text, kws, ORDER_TERMS, limit=2)
    products = snippets(text, kws, PRODUCT_TERMS, limit=2)
    return {
        "annual_report_business_evidence": " | ".join(business) if business else "未在年报正文中抽取到明确主题业务段落",
        "annual_report_revenue_evidence": " | ".join(revenue) if revenue else "未抽取到主题业务收入拆分或收入段落",
        "order_or_customer_evidence": " | ".join(orders) if orders else "未抽取到主题相关订单/客户/合同证据",
        "product_evidence": " | ".join(products) if products else "未抽取到主题相关产品/系统/平台证据",
        "has_business": bool(business),
        "has_revenue": bool(revenue),
        "has_order": bool(orders),
        "has_product": bool(products),
    }


def financial_risk(row: dict[str, str]) -> tuple[str, str]:
    risks = []
    if row.get("is_st") == "true":
        risks.append("ST")
    if row.get("suspended_or_zero_volume_flag") == "true":
        risks.append("停牌/零成交")
    if row.get("financial_quality_flag") == "fail":
        risks.append("financial_quality_flag=fail")
    if row.get("liquidity_flag") == "fail":
        risks.append("liquidity_flag=fail")
    if row.get("financial_quality_flag") == "caution":
        risks.append("financial_quality_flag=caution")
    if row.get("liquidity_flag") == "caution":
        risks.append("liquidity_flag=caution")
    if row.get("valuation_flag") in {"high", "loss_or_negative"}:
        risks.append(f"valuation_flag={row.get('valuation_flag')}")
    debt = num(row.get("debt_to_asset"))
    if debt is not None and debt > 70:
        risks.append(f"debt_to_asset={debt:.1f}%")
    if any(r in risks for r in ["ST", "停牌/零成交", "financial_quality_flag=fail", "liquidity_flag=fail"]) or (debt is not None and debt > 80):
        level = "high"
    elif risks:
        level = "medium"
    else:
        level = "low"
    return level, "；".join(risks) if risks else "未见评分卡层面的明显财务/流动性高风险标记"


def evidence_decisions(ev: dict[str, object], report_has_text: bool) -> tuple[str, str, str, str]:
    if not report_has_text:
        return "missing", "theme_weak", "unclear", "none"
    has_business = bool(ev["has_business"])
    has_revenue = bool(ev["has_revenue"])
    has_order = bool(ev["has_order"])
    has_product = bool(ev["has_product"])
    if has_business and has_product and (has_revenue or has_order):
        return "strong", "theme_confirmed", "yes", "strong"
    if has_business and (has_product or has_revenue or has_order):
        return "medium", "theme_partial", "yes", "partial"
    if has_business:
        return "weak", "theme_weak", "unclear", "weak"
    return "missing", "theme_rejected", "unclear", "none"


def passes_pool_rules(row: dict[str, str]) -> bool:
    market_cap = num(row.get("market_cap"))
    amount = num(row.get("avg_amount_20d"))
    return (
        row.get("is_st") == "false"
        and row.get("financial_quality_flag") != "fail"
        and row.get("liquidity_flag") != "fail"
        and market_cap is not None
        and market_cap >= 3_000_000_000
        and amount is not None
        and amount >= 100_000_000
    )


def trading_decision(row: dict[str, str], business_decision: str, strength: str, q3: str) -> tuple[str, str, str]:
    if business_decision == "theme_rejected":
        return (
            "excluded_by_business_mismatch",
            "年报/公告未能支持主题业务对外销售，按业务不匹配排除",
            "若后续年报/半年报/公告披露收入、订单、客户或产品证据，可重新评估业务匹配",
        )
    if q3 == "high" or not passes_pool_rules(row):
        return (
            "excluded_by_rules",
            "主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤",
            "若财务质量、流动性和市值成交额修复且主题证据仍成立，可重新评估交易池层级",
        )
    if row["review_status"] == "core" and business_decision == "theme_confirmed" and q3 == "low":
        return (
            "default",
            "core 且主题证据确认，基础财务/流动性规则通过",
            "若主题收入、订单或产品披露消失，或财务/流动性规则转为不通过，应降级",
        )
    if business_decision in {"theme_confirmed", "theme_partial"}:
        return (
            "expanded",
            "主题证据成立或部分成立，但当前不是默认池严格条件；conditional 不进默认池",
            "若后续证据和规则过滤均增强，可重新评估默认/扩展层级",
        )
    return (
        "watch",
        "主题证据较弱但未完全证伪，暂入观察层",
        "若补充年报/半年报/公告中的外部销售证据，可上调；若长期无证据，应排除",
    )


def build_row(row: dict[str, str], previous_by_key: dict[tuple[str, str], dict[str, str]]) -> tuple[dict[str, str], str | None, str | None]:
    code = code6(row["code"])
    key = (code, row["theme"])
    report = {}
    text = ""
    fetch_error = None
    text_failure = None
    try:
        report = latest_report(code)
        if report:
            pdf = download_pdf(code, report)
            if pdf:
                text = extract_pdf_text(pdf)
    except Exception as exc:
        fetch_error = f"{code} {row['name']}: {type(exc).__name__}: {exc}"
    if report and not text:
        text_failure = f"{code} {row['name']} {report.get('title', '')}"

    if text:
        ev = evidence_from_text(row, text)
    else:
        prev = previous_by_key.get(key, {})
        ev = {
            "annual_report_business_evidence": prev.get("annual_report_business_evidence") or "未能抽取年报正文；仅保留公告查询结果",
            "annual_report_revenue_evidence": prev.get("annual_report_revenue_evidence") or "未能抽取年报正文",
            "order_or_customer_evidence": prev.get("order_or_customer_evidence") or "未能抽取年报正文",
            "product_evidence": prev.get("product_evidence") or "未能抽取年报正文",
            "has_business": False,
            "has_revenue": False,
            "has_order": False,
            "has_product": False,
        }

    strength, business_decision, q1, q2 = evidence_decisions(ev, bool(text))
    q3, financial_note = financial_risk(row)
    trade, reason, falsification = trading_decision(row, business_decision, strength, q3)
    manual_followup = "yes" if (
        business_decision in {"theme_weak", "theme_rejected"}
        or trade in {"watch", "excluded_by_rules", "excluded_by_business_mismatch"}
        or row.get("final_pool_suggestion") == "manual_check"
    ) else "no"

    evidence_url = report.get("pdf_url") or report.get("detail_url") or previous_by_key.get(key, {}).get("evidence_url") or "unknown"
    out = {
        "code": code,
        "name": row["name"],
        "theme": row["theme"],
        "current_review_status": row["review_status"],
        "current_final_pool_suggestion": row["final_pool_suggestion"],
        "theme_business_claim": row["theme_business_description"],
        "annual_report_business_evidence": str(ev["annual_report_business_evidence"]),
        "annual_report_revenue_evidence": str(ev["annual_report_revenue_evidence"]),
        "order_or_customer_evidence": str(ev["order_or_customer_evidence"]),
        "product_evidence": str(ev["product_evidence"]),
        "financial_risk_evidence": financial_note,
        "evidence_source": report.get("title") or previous_by_key.get(key, {}).get("evidence_source") or "未找到巨潮年报",
        "evidence_url": evidence_url,
        "evidence_report_period": infer_period(report.get("title", ""), report.get("time", "")) if report else previous_by_key.get(key, {}).get("evidence_report_period", "unknown"),
        "evidence_strength": strength,
        "business_evidence_decision": business_decision,
        "trading_pool_decision": trade,
        "answer_q1_external_sales": q1,
        "answer_q2_disclosure_support": q2,
        "answer_q3_financial_risk": q3,
        "answer_q4_pool_decision": trade,
        "decision_reason": reason,
        "falsification_condition": falsification,
        "manual_followup_needed": manual_followup,
    }
    return out, fetch_error, text_failure


def validate(rows: list[dict[str, str]], expected_count: int) -> list[str]:
    errors: list[str] = []
    if len(rows) != expected_count:
        errors.append(f"row_count_mismatch expected={expected_count} actual={len(rows)}")
    if len(rows) != len({(r["code"], r["theme"]) for r in rows}):
        errors.append("duplicate code/theme rows detected")
    for r in rows:
        if not r["evidence_url"] or r["evidence_url"] == "unknown":
            errors.append(f"{r['code']} {r['theme']} missing evidence_url")
        if r["evidence_strength"] not in STRENGTH_LABELS:
            errors.append(f"{r['code']} invalid evidence_strength={r['evidence_strength']}")
        if r["business_evidence_decision"] not in BUSINESS_LABELS:
            errors.append(f"{r['code']} invalid business_evidence_decision={r['business_evidence_decision']}")
        if r["trading_pool_decision"] not in TRADING_LABELS:
            errors.append(f"{r['code']} invalid trading_pool_decision={r['trading_pool_decision']}")
        if r["business_evidence_decision"] == "theme_confirmed" and r["trading_pool_decision"] == "excluded_by_business_mismatch":
            errors.append(f"{r['code']} confirmed business but excluded_by_business_mismatch")
        if r["business_evidence_decision"] == "theme_rejected" and r["trading_pool_decision"] != "excluded_by_business_mismatch":
            errors.append(f"{r['code']} rejected business not excluded_by_business_mismatch")
    # 同一股票不同主题可以使用同一 PDF，但不应复用完全相同的业务证据文本。
    by_code: dict[str, list[dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_code[r["code"]].append(r)
    for code, grouped in by_code.items():
        if len({r["theme"] for r in grouped}) > 1:
            snippets = Counter(r["annual_report_business_evidence"] for r in grouped)
            if any(count > 1 and snippet != "未在年报正文中抽取到明确主题业务段落" for snippet, count in snippets.items()):
                errors.append(f"{code} duplicated business evidence across themes")
    return errors


def important_cases(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    priority: list[dict[str, str]] = []
    priority.extend([r for r in rows if r["trading_pool_decision"] == "default"])
    priority.extend([r for r in rows if r["business_evidence_decision"] == "theme_confirmed" and r["trading_pool_decision"] == "excluded_by_rules"])
    priority.extend([r for r in rows if r["business_evidence_decision"] in {"theme_weak", "theme_rejected"}])
    priority.extend([r for r in rows if r["trading_pool_decision"] == "expanded"])
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for row in priority:
        key = (row["code"], row["theme"])
        if key not in seen:
            seen.add(key)
            out.append(row)
        if len(out) >= 10:
            break
    return out


def write_qa(rows: list[dict[str, str]], score_count: int, rules: list[dict[str, str]], fetch_errors: list[str], text_failures: list[str], validation_errors: list[str]) -> None:
    manual = [r for r in rows if r["manual_followup_needed"] == "yes"]
    lines = [
        "# Stock Pool v1 QA Report",
        "",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Scope",
        f"- theme_stock_research_scorecard.csv rows: {score_count}",
        f"- Output rows: {len(rows)}",
        "- Note: user requested full_119 naming; current input file contains 113 code/theme rows, so outputs cover 113 rows.",
        "",
        "## Stock Pool Rules Applied",
    ]
    lines.extend(f"- {r.get('规则')}: {r.get('当前值')} ({r.get('原因')})" for r in rules)
    lines.extend([
        "",
        "## Label Distribution",
        f"- evidence_strength: {dict(sorted(Counter(r['evidence_strength'] for r in rows).items()))}",
        f"- business_evidence_decision: {dict(sorted(Counter(r['business_evidence_decision'] for r in rows).items()))}",
        f"- trading_pool_decision: {dict(sorted(Counter(r['trading_pool_decision'] for r in rows).items()))}",
        "",
        "## Manual Follow-up Needed",
        f"- Count: {len(manual)}",
    ])
    lines.extend(
        f"- {r['code']} {r['name']} {r['theme']}: {r['business_evidence_decision']} / {r['trading_pool_decision']}；{r['decision_reason']}"
        for r in manual
    )
    lines.extend(["", "## 10 Important Judgment Cases"])
    for r in important_cases(rows):
        lines.append(
            f"- {r['code']} {r['name']} {r['theme']}: business={r['business_evidence_decision']}, trading={r['trading_pool_decision']}, strength={r['evidence_strength']}；{r['decision_reason']}"
        )
    lines.extend([
        "",
        "## QA Checks",
        f"- Row coverage check: {'passed' if len(rows) == score_count else 'failed'}",
        f"- evidence_url non-empty: {'passed' if all(r['evidence_url'] and r['evidence_url'] != 'unknown' for r in rows) else 'failed'}",
        f"- Illegal labels / duplicates / theme-mixing checks: {'passed' if not validation_errors else 'failed'}",
        f"- Report fetch errors: {len(fetch_errors)}",
        f"- PDF text extraction failures: {len(text_failures)}",
        "",
        "## Fetch / Extraction Caveats",
    ])
    if fetch_errors:
        lines.append(f"- Fetch error examples: {fetch_errors[:10]}")
    else:
        lines.append("- Fetch error examples: none")
    if text_failures:
        lines.append(f"- Text extraction failure examples: {text_failures[:10]}")
    else:
        lines.append("- Text extraction failure examples: none")
    lines.extend([
        "- business_evidence_decision is based on official annual-report text extraction by theme-specific keywords.",
        "- trading_pool_decision separately applies stock_pool_rules.csv plus scorecard risk flags; financial failure does not imply business mismatch.",
        "",
        "## Validation Errors",
    ])
    lines.extend(f"- {e}" for e in validation_errors) if validation_errors else lines.append("- None")
    OUT_QA.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build() -> None:
    score = read_csv(SCORECARD)
    rules = read_csv(RULES)
    previous = read_csv(PREVIOUS_EVIDENCE) if PREVIOUS_EVIDENCE.exists() else []
    previous_by_key = {(code6(r["code"]), r["theme"]): r for r in previous}
    rows: list[dict[str, str]] = []
    fetch_errors: list[str] = []
    text_failures: list[str] = []
    for idx, row in enumerate(score, 1):
        out, fetch_error, text_failure = build_row(row, previous_by_key)
        rows.append(out)
        if fetch_error:
            fetch_errors.append(fetch_error)
        if text_failure:
            text_failures.append(text_failure)
        print(f"processed {idx}/{len(score)} {out['code']} {out['name']} {out['theme']} {out['business_evidence_decision']} -> {out['trading_pool_decision']}")
        time.sleep(0.12)

    validation_errors = validate(rows, len(score))
    write_csv(OUT_FULL, rows, FIELDS)
    write_csv(OUT_SUGGEST, rows, SUGGEST_FIELDS)
    write_csv(OUT_DEFAULT, [r for r in rows if r["trading_pool_decision"] == "default"], FIELDS)
    write_csv(OUT_EXPANDED, [r for r in rows if r["trading_pool_decision"] == "expanded"], FIELDS)
    write_csv(OUT_WATCH, [r for r in rows if r["trading_pool_decision"] == "watch"], FIELDS)
    write_csv(OUT_EX_RULES, [r for r in rows if r["trading_pool_decision"] == "excluded_by_rules"], FIELDS)
    write_csv(OUT_EX_BIZ, [r for r in rows if r["trading_pool_decision"] == "excluded_by_business_mismatch"], FIELDS)
    write_qa(rows, len(score), rules, fetch_errors, text_failures, validation_errors)
    print(f"rows={len(rows)}")
    print(f"business={dict(sorted(Counter(r['business_evidence_decision'] for r in rows).items()))}")
    print(f"trading={dict(sorted(Counter(r['trading_pool_decision'] for r in rows).items()))}")
    print(f"validation_errors={len(validation_errors)}")


if __name__ == "__main__":
    build()
