import csv
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
EVIDENCE_V1 = ROOT / "annual_report_evidence_check_full_119.csv"
SUGGESTIONS_V1 = ROOT / "pool_decision_suggestions_full_119.csv"
SCORECARD = ROOT / "theme_stock_research_scorecard.csv"
RULES = ROOT / "stock_pool_rules.csv"

OUT_SUGGESTIONS = ROOT / "pool_decision_suggestions_v1_1.csv"
OUT_MANUAL = ROOT / "manual_followup_true_required.csv"
OUT_EXCEPTIONS = ROOT / "implicit_rule_exceptions.csv"
OUT_AFFECTED = ROOT / "affected_rows.csv"
OUT_QA = ROOT / "stock_pool_v1_1_QA_report.md"

BUSINESS_LABELS = {"theme_confirmed", "theme_partial", "theme_weak", "theme_rejected"}
TRADING_LABELS = {
    "default",
    "expanded",
    "watch",
    "excluded_by_rules",
    "excluded_by_business_mismatch",
}
YES_NO = {"yes", "no"}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def code6(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits.zfill(6)[-6:]


def num(value: str):
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if text.lower() in {"", "unknown", "nan", "none"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def explicit_rule_hits(score: dict[str, str]) -> list[str]:
    hits: list[str] = []
    market_cap = num(score.get("market_cap"))
    avg_amount = num(score.get("avg_amount_20d"))
    if score.get("is_st") == "true":
        hits.append("ST")
    if score.get("financial_quality_flag") == "fail":
        hits.append("financial_quality_flag=fail")
    if market_cap is None:
        hits.append("market_cap missing")
    elif market_cap < 3_000_000_000:
        hits.append("market_cap<30亿")
    if avg_amount is None:
        hits.append("avg_amount_20d missing")
    elif avg_amount < 100_000_000:
        hits.append("avg_amount_20d<1亿")
    return hits


def implicit_rule_hits(score: dict[str, str], explicit_hits: list[str]) -> list[str]:
    hits: list[str] = []
    avg_amount_explicit = any(hit.startswith("avg_amount_20d") for hit in explicit_hits)
    debt = num(score.get("debt_to_asset"))
    if debt is not None and debt > 80:
        hits.append("debt_to_asset>80%")
    if score.get("liquidity_flag") == "fail" and not avg_amount_explicit:
        hits.append("liquidity_flag=fail")
    if score.get("suspended_or_zero_volume_flag") == "true" and not avg_amount_explicit:
        hits.append("suspended_or_zero_volume_flag=true")
    return hits


def business_review_needed(row: dict[str, str]) -> tuple[str, str]:
    decision = row.get("business_evidence_decision", "")
    strength = row.get("evidence_strength", "")
    if decision in {"theme_weak", "theme_rejected"}:
        return "yes", f"business evidence decision is {decision}"
    if decision == "theme_partial" or strength in {"weak", "missing"}:
        return "yes", f"business evidence is not strong enough: decision={decision}, strength={strength}"
    return "no", "business evidence is strong/confirmed; no business manual review required"


def enrich_row(row: dict[str, str], score: dict[str, str]) -> dict[str, str]:
    out = dict(row)
    out["code"] = code6(row.get("code", ""))

    explicit_hits = explicit_rule_hits(score)
    implicit_hits = implicit_rule_hits(score, explicit_hits)
    business_needed, business_reason = business_review_needed(row)

    if row.get("trading_pool_decision") == "excluded_by_rules" and implicit_hits:
        rule_exception_needed = "yes"
        rule_reason = (
            "excluded_by_rules uses non-explicit rule factor(s): "
            + "; ".join(implicit_hits)
            + ". Original trading_pool_decision preserved for rule-owner review."
        )
    else:
        rule_exception_needed = "no"
        if row.get("trading_pool_decision") == "excluded_by_rules":
            rule_reason = "excluded_by_rules is explained by explicit stock_pool_rules.csv hit(s): " + "; ".join(explicit_hits)
        else:
            rule_reason = "not excluded_by_rules"

    reasons = []
    if business_needed == "yes":
        reasons.append(business_reason)
    if rule_exception_needed == "yes":
        reasons.append(rule_reason)
    if not reasons:
        reasons.append("manual follow-up not required by v1.1 criteria")

    out["business_manual_review_needed"] = business_needed
    out["rule_exception_review_needed"] = rule_exception_needed
    out["manual_followup_reason"] = " | ".join(reasons)
    out["explicit_rule_hit"] = "; ".join(explicit_hits) if explicit_hits else "none"
    out["implicit_rule_hit"] = "; ".join(implicit_hits) if implicit_hits else "none"
    out["debt_to_asset"] = score.get("debt_to_asset", "unknown")
    out["market_cap"] = score.get("market_cap", "unknown")
    out["avg_amount_20d"] = score.get("avg_amount_20d", "unknown")
    out["is_st"] = score.get("is_st", "unknown")
    out["suspended_or_zero_volume_flag"] = score.get("suspended_or_zero_volume_flag", "unknown")
    out["financial_quality_flag"] = score.get("financial_quality_flag", "unknown")
    out["liquidity_flag"] = score.get("liquidity_flag", "unknown")
    return out


def validate(rows: list[dict[str, str]], evidence_rows: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    if len(rows) != len(evidence_rows):
        errors.append(f"row_count_mismatch expected={len(evidence_rows)} actual={len(rows)}")
    keys = [(r["code"], r["theme"]) for r in rows]
    if len(keys) != len(set(keys)):
        errors.append("duplicate code/theme rows detected")
    for r in rows:
        if len(r.get("code", "")) != 6 or not r.get("code", "").isdigit():
            errors.append(f"{r.get('code')} invalid 6-digit code")
        if r.get("business_evidence_decision") not in BUSINESS_LABELS:
            errors.append(f"{r.get('code')} invalid business_evidence_decision={r.get('business_evidence_decision')}")
        if r.get("trading_pool_decision") not in TRADING_LABELS:
            errors.append(f"{r.get('code')} invalid trading_pool_decision={r.get('trading_pool_decision')}")
        if r.get("business_manual_review_needed") not in YES_NO:
            errors.append(f"{r.get('code')} invalid business_manual_review_needed={r.get('business_manual_review_needed')}")
        if r.get("rule_exception_review_needed") not in YES_NO:
            errors.append(f"{r.get('code')} invalid rule_exception_review_needed={r.get('rule_exception_review_needed')}")
        if not r.get("manual_followup_reason"):
            errors.append(f"{r.get('code')} missing manual_followup_reason")
    return errors


def write_qa(rows: list[dict[str, str]], manual_rows: list[dict[str, str]], exception_rows: list[dict[str, str]], affected_rows: list[dict[str, str]], rules: list[dict[str, str]], errors: list[str]) -> None:
    lines: list[str] = []
    lines.append("# Stock Pool v1.1 QA Report")
    lines.append("")
    lines.append(f"Generated at: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Scope")
    lines.append(f"- Input v1 evidence rows: {len(rows)}")
    lines.append("- v1.1 preserves original annual-report evidence fields and trading_pool_decision.")
    lines.append("- v1.1 narrows manual follow-up to business evidence issues and non-explicit rule exceptions.")
    lines.append("")
    lines.append("## stock_pool_rules.csv")
    for r in rules:
        lines.append(f"- {r.get('规则')}: {r.get('当前值')} ({r.get('原因')})")
    lines.append("")
    lines.append("## Label Distribution")
    lines.append(f"- trading_pool_decision: {dict(sorted(Counter(r['trading_pool_decision'] for r in rows).items()))}")
    lines.append(f"- business_manual_review_needed: {dict(sorted(Counter(r['business_manual_review_needed'] for r in rows).items()))}")
    lines.append(f"- rule_exception_review_needed: {dict(sorted(Counter(r['rule_exception_review_needed'] for r in rows).items()))}")
    lines.append("")
    lines.append("## Manual Follow-up")
    lines.append(f"- manual_followup_true_required.csv rows: {len(manual_rows)}")
    lines.append(f"- implicit_rule_exceptions.csv rows: {len(exception_rows)}")
    lines.append(f"- affected_rows.csv debt_to_asset>80% rows: {len(affected_rows)}")
    lines.append("")
    lines.append("## debt_to_asset>80% Check")
    if affected_rows:
        lines.append("- debt_to_asset>80% was used as an implicit high-risk rule in v1 logic, but it is not listed in stock_pool_rules.csv.")
        for r in affected_rows:
            lines.append(f"- {r['code']} {r['name']} {r['theme']}: debt_to_asset={r.get('debt_to_asset')} trading={r['trading_pool_decision']}")
    else:
        lines.append("- No rows affected.")
    lines.append("")
    lines.append("## QA Checks")
    lines.append("- Code format: 6-digit text strings")
    lines.append("- Original trading_pool_decision: preserved")
    lines.append("- Original evidence fields: preserved")
    lines.append("- Manual business review is not automatically assigned to all excluded_by_rules rows")
    lines.append("")
    lines.append("## Validation Errors")
    if errors:
        lines.extend(f"- {e}" for e in errors)
    else:
        lines.append("- None")
    OUT_QA.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    evidence = read_csv(EVIDENCE_V1)
    scorecard = read_csv(SCORECARD)
    rules = read_csv(RULES)
    score_by_key = {(code6(r["code"]), r["theme"]): r for r in scorecard}

    rows: list[dict[str, str]] = []
    missing_score: list[str] = []
    for row in evidence:
        key = (code6(row["code"]), row["theme"])
        score = score_by_key.get(key)
        if not score:
            missing_score.append(f"{key[0]} {key[1]}")
            score = {}
        rows.append(enrich_row(row, score))

    manual_rows = [
        r for r in rows
        if r["business_manual_review_needed"] == "yes" or r["rule_exception_review_needed"] == "yes"
    ]
    exception_rows = [r for r in rows if r["rule_exception_review_needed"] == "yes"]
    affected_rows = [
        r for r in exception_rows
        if "debt_to_asset>80%" in r.get("implicit_rule_hit", "")
    ]

    base_fields = list(evidence[0].keys())
    fields = [
        *base_fields,
        "business_manual_review_needed",
        "rule_exception_review_needed",
        "manual_followup_reason",
        "explicit_rule_hit",
        "implicit_rule_hit",
        "debt_to_asset",
        "market_cap",
        "avg_amount_20d",
        "is_st",
        "suspended_or_zero_volume_flag",
        "financial_quality_flag",
        "liquidity_flag",
    ]
    suggestion_fields = [
        "code",
        "name",
        "theme",
        "current_review_status",
        "current_final_pool_suggestion",
        "evidence_strength",
        "business_evidence_decision",
        "trading_pool_decision",
        "business_manual_review_needed",
        "rule_exception_review_needed",
        "manual_followup_reason",
        "explicit_rule_hit",
        "implicit_rule_hit",
        "debt_to_asset",
        "market_cap",
        "avg_amount_20d",
        "financial_quality_flag",
        "liquidity_flag",
        "evidence_url",
    ]

    errors = validate(rows, evidence)
    errors.extend(f"missing scorecard row for {item}" for item in missing_score)

    write_csv(OUT_SUGGESTIONS, rows, fields)
    write_csv(OUT_MANUAL, manual_rows, suggestion_fields)
    write_csv(OUT_EXCEPTIONS, exception_rows, suggestion_fields)
    write_csv(OUT_AFFECTED, affected_rows, suggestion_fields)
    write_qa(rows, manual_rows, exception_rows, affected_rows, rules, errors)

    print(f"rows={len(rows)}")
    print(f"manual_rows={len(manual_rows)}")
    print(f"implicit_rule_exceptions={len(exception_rows)}")
    print(f"affected_rows={len(affected_rows)}")
    print(f"validation_errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
