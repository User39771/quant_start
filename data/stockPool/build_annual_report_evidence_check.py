import csv
import math
import re
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import akshare as ak
import requests
from pypdf import PdfReader


ROOT = Path(__file__).resolve().parent
SCORECARD = ROOT / "theme_stock_research_scorecard.csv"
MANUAL = ROOT / "manual_research_required.csv"
RULES = ROOT / "stock_pool_rules.csv"
CACHE = ROOT / "annual_report_cache"
CACHE.mkdir(exist_ok=True)

OUT_ALL = ROOT / "annual_report_evidence_check.csv"
OUT_CORE = ROOT / "core_stock_evidence_review.csv"
OUT_MANUAL = ROOT / "manual_stock_evidence_review.csv"
OUT_DECISIONS = ROOT / "pool_decision_suggestions.csv"
OUT_QA = ROOT / "evidence_QA_report.md"

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
    "answer_q1_external_sales",
    "answer_q2_disclosure_support",
    "answer_q3_financial_risk",
    "answer_q4_pool_decision",
    "decision_reason",
    "falsification_condition",
    "manual_followup_needed",
]

DECISION_FIELDS = [
    "code",
    "name",
    "theme",
    "current_review_status",
    "current_final_pool_suggestion",
    "evidence_strength",
    "answer_q4_pool_decision",
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
    "AI",
    "AIGC",
    "算力",
    "智算",
    "大模型",
    "智能体",
    "服务器",
    "GPU",
    "算法",
    "机器视觉",
    "智能语音",
    "数据中心",
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
]
REVENUE_TERMS = ["收入", "营收", "销售", "营业收入", "主营业务收入"]
ORDER_TERMS = ["订单", "客户", "合同", "中标", "交付", "供应", "项目", "应用于", "服务于"]
PRODUCT_TERMS = ["产品", "系统", "平台", "解决方案", "模块", "芯片", "设备", "终端", "软件", "服务"]


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


def choose_scope(score: list[dict[str, str]], manual: list[dict[str, str]]) -> tuple[list[dict[str, str]], set[tuple[str, str]]]:
    manual_keys = {(code6(row["code"]), row["theme"]) for row in manual}
    rows_by_key = {(code6(row["code"]), row["theme"]): row for row in score}
    core_keys = {(code6(row["code"]), row["theme"]) for row in score if row["review_status"] == "core"}
    keys = sorted(manual_keys | core_keys)
    return [rows_by_key[key] for key in keys if key in rows_by_key], manual_keys


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
    for idx, page in enumerate(reader.pages[:max_pages]):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        if text:
            chunks.append(text)
    text = "\n".join(chunks)
    return re.sub(r"\s+", " ", text)


def keywords_for(row: dict[str, str]) -> list[str]:
    base = AI_KEYWORDS if row["theme"] == "AI" else SPACE_KEYWORDS
    claim = row.get("theme_business_description", "") + " " + row.get("primary_business", "")
    extra = []
    for token in re.findall(r"[\u4e00-\u9fffA-Za-z0-9]{2,}", claim):
        if token in {"公司", "业务", "相关", "产品", "服务", "收入", "主营"}:
            continue
        if any(k in token or token in k for k in base):
            extra.append(token)
    out = []
    for token in base + extra:
        if token not in out:
            out.append(token)
    return out


def snippets(text: str, keywords: list[str], required_terms: list[str] | None = None, limit: int = 3) -> list[str]:
    out: list[str] = []
    for kw in keywords:
        for match in re.finditer(re.escape(kw), text, flags=re.IGNORECASE):
            start = max(0, match.start() - 90)
            end = min(len(text), match.end() + 150)
            snip = text[start:end].strip()
            if required_terms and not any(term in snip for term in required_terms):
                continue
            if snip and all(snip[:80] not in existing for existing in out):
                out.append(snip)
            if len(out) >= limit:
                return out
    return out


def evidence_from_text(row: dict[str, str], text: str) -> dict[str, str]:
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


def evidence_strength(ev: dict[str, str], report_found: bool) -> tuple[str, str, str]:
    if not report_found:
        return "missing", "unclear", "none"
    has_business = ev["has_business"]
    has_revenue = ev["has_revenue"]
    has_order = ev["has_order"]
    has_product = ev["has_product"]
    if has_business and has_product and (has_revenue or has_order):
        return "strong", "yes", "strong"
    if has_business and has_product:
        return "medium", "yes", "partial"
    if has_business:
        return "weak", "unclear", "weak"
    return "missing", "unclear", "none"


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


def pool_decision(row: dict[str, str], strength: str, q1: str, q2: str, q3: str) -> tuple[str, str, str]:
    rules_ok = passes_pool_rules(row)
    if q3 == "high" or not rules_ok:
        return (
            "reject",
            "不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high",
            "若后续财务质量修复、流动性达标且公告证据显示主题业务对外销售，可重新评估",
        )
    if q1 == "no":
        return (
            "reject",
            "未确认主题业务对外销售，不应进入交易股票池",
            "若年报披露外部客户、订单或收入，可重新评估",
        )
    if strength in {"missing", "weak"}:
        return (
            "watch",
            "年报证据不足，不能进入默认池；仅保留观察或人工复核",
            "若补充年报/半年报/公告中的收入、订单、客户或产品证据，可上调",
        )
    if row["review_status"] == "core" and strength == "strong" and q3 == "low":
        return (
            "default",
            "core 且年报证据强，基础财务/流动性过滤通过",
            "若主题收入、订单或产品披露消失，或财务质量转 fail，应降级",
        )
    return (
        "expanded",
        "有年报业务证据但不满足默认池全部严格条件，或当前为 conditional",
        "若后续收入/订单证据增强且规则过滤持续通过，可重新评估默认/扩展层级",
    )


def build() -> None:
    score = read_csv(SCORECARD)
    manual = read_csv(MANUAL)
    rules = read_csv(RULES)
    scope, manual_keys = choose_scope(score, manual)
    rows: list[dict[str, str]] = []
    fetch_errors: list[str] = []
    pdf_text_failures: list[str] = []

    for idx, row in enumerate(scope, 1):
        code = code6(row["code"])
        report = {}
        text = ""
        report_found = False
        try:
            report = latest_report(code)
            if report:
                report_found = True
                pdf = download_pdf(code, report)
                if pdf:
                    text = extract_pdf_text(pdf)
        except Exception as exc:
            fetch_errors.append(f"{code} {row['name']}: {type(exc).__name__}: {exc}")
        if report_found and not text:
            pdf_text_failures.append(f"{code} {row['name']} {report.get('title', '')}")

        ev = evidence_from_text(row, text) if text else {
            "annual_report_business_evidence": "未能抽取年报正文；仅保留公告查询结果",
            "annual_report_revenue_evidence": "未能抽取年报正文",
            "order_or_customer_evidence": "未能抽取年报正文",
            "product_evidence": "未能抽取年报正文",
            "has_business": False,
            "has_revenue": False,
            "has_order": False,
            "has_product": False,
        }
        strength, q1, q2 = evidence_strength(ev, report_found and bool(text))
        q3, financial_note = financial_risk(row)
        q4, reason, falsification = pool_decision(row, strength, q1, q2, q3)

        manual_needed = "yes" if (
            (row["review_status"] == "core" and strength not in {"strong", "medium"})
            or q4 in {"watch", "reject"}
            or (code, row["theme"]) in manual_keys
        ) else "no"
        if row["review_status"] == "core" and strength != "strong" and q4 == "default":
            q4 = "expanded"
            reason = "core 但年报证据未达到 strong，按严格规则不得进入默认池"
            manual_needed = "yes"

        source = report.get("title", "未找到巨潮年报")
        evidence_url = report.get("pdf_url") or report.get("detail_url") or "unknown"
        out = {
            "code": code,
            "name": row["name"],
            "theme": row["theme"],
            "current_review_status": row["review_status"],
            "current_final_pool_suggestion": row["final_pool_suggestion"],
            "theme_business_claim": row["theme_business_description"],
            "annual_report_business_evidence": ev["annual_report_business_evidence"],
            "annual_report_revenue_evidence": ev["annual_report_revenue_evidence"],
            "order_or_customer_evidence": ev["order_or_customer_evidence"],
            "product_evidence": ev["product_evidence"],
            "financial_risk_evidence": financial_note,
            "evidence_source": source,
            "evidence_url": evidence_url,
            "evidence_report_period": infer_period(report.get("title", ""), report.get("time", "")),
            "evidence_strength": strength,
            "answer_q1_external_sales": q1,
            "answer_q2_disclosure_support": q2,
            "answer_q3_financial_risk": q3,
            "answer_q4_pool_decision": q4,
            "decision_reason": reason,
            "falsification_condition": falsification,
            "manual_followup_needed": manual_needed,
        }
        rows.append(out)
        print(f"processed {idx}/{len(scope)} {code} {row['name']} {row['theme']} {strength} -> {q4}")
        time.sleep(0.2)

    write_csv(OUT_ALL, rows, FIELDS)
    write_csv(OUT_CORE, [r for r in rows if r["current_review_status"] == "core"], FIELDS)
    write_csv(OUT_MANUAL, [r for r in rows if (r["code"], r["theme"]) in manual_keys], FIELDS)
    write_csv(OUT_DECISIONS, rows, DECISION_FIELDS)
    write_qa(rows, manual_keys, rules, fetch_errors, pdf_text_failures)
    print(f"rows={len(rows)}")
    print(f"strength={dict(sorted(Counter(r['evidence_strength'] for r in rows).items()))}")
    print(f"decision={dict(sorted(Counter(r['answer_q4_pool_decision'] for r in rows).items()))}")


def infer_period(title: str, report_time: str) -> str:
    match = re.search(r"(20\d{2})年年度报告", title)
    if match:
        return f"{match.group(1)}年度"
    return report_time or "unknown"


def write_qa(
    rows: list[dict[str, str]],
    manual_keys: set[tuple[str, str]],
    rules: list[dict[str, str]],
    fetch_errors: list[str],
    pdf_text_failures: list[str],
) -> None:
    strength = Counter(r["evidence_strength"] for r in rows)
    decision = Counter(r["answer_q4_pool_decision"] for r in rows)
    core_downgrade = [
        r for r in rows
        if r["current_review_status"] == "core" and r["answer_q4_pool_decision"] != "default"
    ]
    manual_upgrade = [
        r for r in rows
        if (r["code"], r["theme"]) in manual_keys and r["answer_q4_pool_decision"] in {"expanded", "default"}
    ]
    evidence_insufficient = [
        r for r in rows
        if r["evidence_strength"] in {"weak", "missing"}
    ]
    not_default = [
        r for r in rows
        if r["answer_q4_pool_decision"] != "default"
    ]
    validation_errors = validate(rows)
    lines = [
        "# Annual Report Evidence QA Report",
        "",
        f"Generated at: {datetime.now().isoformat(timespec='seconds')}",
        "",
        "## Scope",
        f"- Processed rows: {len(rows)}",
        f"- Core rows: {sum(1 for r in rows if r['current_review_status'] == 'core')}",
        f"- Manual rows: {sum(1 for r in rows if (r['code'], r['theme']) in manual_keys)}",
        "",
        "## Stock Pool Rules Applied",
    ]
    lines.extend(f"- {r.get('规则')}: {r.get('当前值')} ({r.get('原因')})" for r in rules)
    lines.extend([
        "",
        "## Evidence Strength Distribution",
        f"- {dict(sorted(strength.items()))}",
        "",
        "## Suggested Pool Decision Distribution",
        f"- {dict(sorted(decision.items()))}",
        "",
        "## Core Stocks Needing Downgrade Or Follow-up",
    ])
    if core_downgrade:
        lines.extend(
            f"- {r['code']} {r['name']} {r['theme']}: {r['answer_q4_pool_decision']}；{r['decision_reason']}"
            for r in core_downgrade
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Manual Stocks That Can Upgrade To Expanded/Default"])
    if manual_upgrade:
        lines.extend(
            f"- {r['code']} {r['name']} {r['theme']}: {r['answer_q4_pool_decision']}；{r['evidence_strength']}"
            for r in manual_upgrade
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Evidence Insufficient"])
    if evidence_insufficient:
        lines.extend(
            f"- {r['code']} {r['name']} {r['theme']}: strength={r['evidence_strength']}, decision={r['answer_q4_pool_decision']}"
            for r in evidence_insufficient
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Not For Default Pool Under Current Rules"])
    if not_default:
        lines.extend(
            f"- {r['code']} {r['name']} {r['theme']}: decision={r['answer_q4_pool_decision']}；{r['decision_reason']}"
            for r in not_default
        )
    else:
        lines.append("- None")
    lines.extend(["", "## Fetch And Parsing Caveats"])
    if fetch_errors:
        lines.append(f"- Report fetch errors: {len(fetch_errors)}; examples: {fetch_errors[:10]}")
    else:
        lines.append("- Report fetch errors: 0")
    if pdf_text_failures:
        lines.append(f"- PDF text extraction failures: {len(pdf_text_failures)}; examples: {pdf_text_failures[:10]}")
    else:
        lines.append("- PDF text extraction failures: 0")
    lines.extend([
        "- Strong/medium/weak/missing are evidence ratings only, not trading opinions.",
        "- If only a title/detail link exists but no extractable PDF text, evidence is treated as missing.",
        "- If annual report text lacks revenue/order/customer/product evidence, evidence_strength is capped by rule.",
        "",
        "## Validation",
        f"- Validation errors: {len(validation_errors)}",
    ])
    lines.extend(f"- {e}" for e in validation_errors) if validation_errors else lines.append("- None")
    OUT_QA.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validate(rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    allowed_strength = {"strong", "medium", "weak", "missing"}
    allowed_q1 = {"yes", "no", "unclear"}
    allowed_q2 = {"strong", "partial", "weak", "none"}
    allowed_q3 = {"low", "medium", "high"}
    allowed_q4 = {"default", "expanded", "watch", "reject"}
    if len(rows) != len({(r["code"], r["theme"]) for r in rows}):
        errors.append("duplicate code/theme rows detected")
    for r in rows:
        if r["evidence_strength"] not in allowed_strength:
            errors.append(f"{r['code']} invalid evidence_strength {r['evidence_strength']}")
        if r["answer_q1_external_sales"] not in allowed_q1:
            errors.append(f"{r['code']} invalid q1 {r['answer_q1_external_sales']}")
        if r["answer_q2_disclosure_support"] not in allowed_q2:
            errors.append(f"{r['code']} invalid q2 {r['answer_q2_disclosure_support']}")
        if r["answer_q3_financial_risk"] not in allowed_q3:
            errors.append(f"{r['code']} invalid q3 {r['answer_q3_financial_risk']}")
        if r["answer_q4_pool_decision"] not in allowed_q4:
            errors.append(f"{r['code']} invalid q4 {r['answer_q4_pool_decision']}")
        if r["current_review_status"] == "core" and r["evidence_strength"] in {"weak", "missing"} and r["manual_followup_needed"] != "yes":
            errors.append(f"{r['code']} core weak/missing without manual follow-up")
        no_rev_order_product = (
            r["annual_report_revenue_evidence"].startswith("未")
            and r["order_or_customer_evidence"].startswith("未")
            and r["product_evidence"].startswith("未")
        )
        if no_rev_order_product and r["evidence_strength"] == "strong":
            errors.append(f"{r['code']} strong evidence without revenue/order/product")
    return errors


if __name__ == "__main__":
    build()
