import csv
from collections import Counter
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
INPUT_V1_1 = ROOT / "pool_decision_suggestions_v1_1.csv"
SCORECARD = ROOT / "theme_stock_research_scorecard.csv"
RULES_V1 = ROOT / "stock_pool_rules.csv"

OUT_RULES = ROOT / "stock_pool_rules_v1_2.csv"
OUT_SUGGESTIONS = ROOT / "pool_decision_suggestions_v1_2.csv"
OUT_DEFAULT = ROOT / "default_pool_v1_2.csv"
OUT_EXPANDED = ROOT / "expanded_pool_v1_2.csv"
OUT_EXCLUDED_RULES = ROOT / "excluded_by_rules_v1_2.csv"
OUT_EXCLUDED_BIZ = ROOT / "excluded_by_business_mismatch_v1_2.csv"
OUT_RESOLUTION = ROOT / "rule_exception_resolution_v1_2.csv"
OUT_QA = ROOT / "stock_pool_v1_2_QA_report.md"

TRADING_LABELS = {
    "default",
    "expanded",
    "watch",
    "excluded_by_rules",
    "excluded_by_business_mismatch",
}
BUSINESS_LABELS = {"theme_confirmed", "theme_partial", "theme_weak", "theme_rejected"}
YES_NO = {"yes", "no"}

MANUAL_CASES = {
    ("000938", "AI"): {
        "trading_pool_decision": "expanded",
        "rule_exception_resolution": "allow_expanded",
        "leverage_risk_flag": "yes",
        "financial_risk_level": "medium",
        "default_pool_allowed": "no",
        "reason": (
            "business evidence confirmed/core; no explicit hard rule hit; "
            "debt_to_asset>80% alone should not hard-exclude; but inventory, covenant "
            "and leverage risk require monitoring."
        ),
    },
    ("300857", "AI"): {
        "trading_pool_decision": "expanded",
        "rule_exception_resolution": "allow_expanded_with_high_risk_flag",
        "leverage_risk_flag": "yes",
        "financial_risk_level": "high",
        "default_pool_allowed": "no",
        "reason": (
            "business evidence confirmed; no explicit hard rule hit; AI/compute growth "
            "and positive CFO support expanded inclusion; leveraged expansion and capex "
            "risk require high-risk label."
        ),
    },
    ("002313", "AI"): {
        "trading_pool_decision": "excluded_by_rules",
        "rule_exception_resolution": "keep_excluded_explicit_hard_rules",
        "leverage_risk_flag": "yes",
        "financial_risk_level": "high",
        "default_pool_allowed": "no",
        "reason": (
            "explicit hard rules hit: financial_quality_flag=fail, market_cap<30亿, "
            "avg_amount_20d<1亿. debt_to_asset>80% is secondary, not the primary "
            "exclusion reason."
        ),
    },
    ("300212", "AI"): {
        "trading_pool_decision": "excluded_by_rules",
        "rule_exception_resolution": "keep_excluded_explicit_hard_rules",
        "leverage_risk_flag": "yes",
        "financial_risk_level": "high",
        "default_pool_allowed": "no",
        "reason": (
            "explicit hard rules hit: ST and financial_quality_flag=fail. "
            "debt_to_asset>80% is secondary."
        ),
    },
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def code6(value: str) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())
    return digits.zfill(6)[-6:]


def num(value: str):
    text = str(value or "").strip().replace(",", "").replace("%", "")
    if text.lower() in {"", "unknown", "nan", "none"}:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def explicit_hard_rule_hits(score: dict[str, str]) -> list[str]:
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


def leverage_risk(score: dict[str, str]) -> tuple[str, str]:
    debt = num(score.get("debt_to_asset"))
    if debt is not None and debt > 80:
        return "yes", "debt_to_asset>80%"
    return "no", "none"


def base_financial_risk_level(
    explicit_hits: list[str],
    leverage_flag: str,
    score: dict[str, str],
) -> str:
    if explicit_hits:
        return "high"
    if leverage_flag == "yes":
        return "medium"
    if score.get("valuation_flag") in {"high", "loss_or_negative"}:
        return "medium"
    if score.get("financial_quality_flag") == "caution" or score.get("liquidity_flag") == "caution":
        return "medium"
    return "low"


def apply_v1_2_decision(row: dict[str, str], score: dict[str, str]) -> dict[str, str]:
    out = dict(row)
    out["code"] = code6(row.get("code", ""))
    key = (out["code"], out.get("theme", ""))

    explicit_hits = explicit_hard_rule_hits(score)
    leverage_flag, leverage_reason = leverage_risk(score)
    risk_level = base_financial_risk_level(explicit_hits, leverage_flag, score)
    manual = MANUAL_CASES.get(key)

    out["explicit_hard_rule_hit"] = "; ".join(explicit_hits) if explicit_hits else "none"
    out["leverage_risk_flag"] = leverage_flag
    out["leverage_risk_reason"] = leverage_reason
    out["rule_exception_resolution"] = "not_applicable"
    out["financial_risk_level"] = risk_level
    out["default_pool_allowed"] = "yes" if leverage_flag == "no" and not explicit_hits else "no"
    out["v1_2_decision_reason"] = "v1.1 decision preserved; no v1.2 manual override required."

    if row.get("valuation_flag") == "high" or score.get("valuation_flag") == "high":
        out["valuation_risk_note_v1_2"] = "valuation=high is a risk note only; not an exclusion rule."
    else:
        out["valuation_risk_note_v1_2"] = "none"

    if manual:
        out["trading_pool_decision"] = manual["trading_pool_decision"]
        out["rule_exception_resolution"] = manual["rule_exception_resolution"]
        out["leverage_risk_flag"] = manual["leverage_risk_flag"]
        out["financial_risk_level"] = manual["financial_risk_level"]
        out["default_pool_allowed"] = manual["default_pool_allowed"]
        out["v1_2_decision_reason"] = manual["reason"]
    elif out.get("business_evidence_decision") == "theme_rejected":
        out["trading_pool_decision"] = "excluded_by_business_mismatch"
        out["default_pool_allowed"] = "no"
        out["v1_2_decision_reason"] = "business evidence rejected; excluded by business mismatch."
    elif explicit_hits:
        out["trading_pool_decision"] = "excluded_by_rules"
        out["default_pool_allowed"] = "no"
        out["v1_2_decision_reason"] = (
            "explicit hard rule hit(s): " + "; ".join(explicit_hits)
        )
    elif out.get("trading_pool_decision") == "excluded_by_rules" and leverage_flag == "yes":
        out["trading_pool_decision"] = "expanded"
        out["rule_exception_resolution"] = "auto_allow_expanded_debt_only"
        out["default_pool_allowed"] = "no"
        out["v1_2_decision_reason"] = (
            "debt_to_asset>80% alone is not a hard exclusion in v1.2; allowed in "
            "expanded_pool with leverage_risk_flag."
        )
    elif out.get("trading_pool_decision") == "default" and leverage_flag == "yes":
        out["trading_pool_decision"] = "expanded"
        out["default_pool_allowed"] = "no"
        out["rule_exception_resolution"] = "downgrade_default_for_leverage"
        out["v1_2_decision_reason"] = "default_pool does not accept debt_to_asset>80%."

    if "answer_q4_pool_decision" in out:
        out["answer_q4_pool_decision"] = out["trading_pool_decision"]
    return out


def build_rules_v1_2(rules_v1: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for row in rules_v1:
        rule = row.get("规则", "")
        current = row.get("当前值", "")
        reason = row.get("原因", "")
        hard_exclude = "yes" if rule in {
            "最低日均成交额",
            "最低市值",
            "ST",
            "financial_quality_flag=fail",
        } else "no"
        default_pool = "apply"
        expanded_pool = "apply"
        if rule in {"最低日均成交额", "最低市值", "ST", "financial_quality_flag=fail"}:
            default_pool = "exclude_on_fail"
            expanded_pool = "exclude_on_fail"
        if rule == "valuation=high":
            default_pool = "risk_note_only"
            expanded_pool = "risk_note_only"
        elif rule == "conditional":
            default_pool = "exclude"
            expanded_pool = "allow"
        rows.append(
            {
                "rule": rule,
                "current_value": current,
                "default_pool": default_pool,
                "expanded_pool": expanded_pool,
                "hard_exclude": hard_exclude,
                "reason": reason,
            }
        )
    rows.append(
        {
            "rule": "debt_to_asset>80%",
            "current_value": "v1.2 explicit leverage rule",
            "default_pool": "exclude",
            "expanded_pool": "allow_with_leverage_risk_flag",
            "hard_exclude": "no, unless another explicit hard rule is hit",
            "reason": (
                "High leverage blocks default_pool but may remain in expanded_pool "
                "with leverage_risk_flag and risk note."
            ),
        }
    )
    return rows


def before_after_counts(rows_v1: list[dict[str, str]], rows_v1_2: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    labels = ["default", "expanded", "excluded_by_rules", "excluded_by_business_mismatch"]
    before = Counter(r.get("trading_pool_decision", "") for r in rows_v1)
    after = Counter(r.get("trading_pool_decision", "") for r in rows_v1_2)
    return {
        label: {"before": before.get(label, 0), "after": after.get(label, 0)}
        for label in labels
    }


def validate(rows: list[dict[str, str]], rows_v1: list[dict[str, str]]) -> list[str]:
    errors: list[str] = []
    if len(rows) != len(rows_v1):
        errors.append(f"row_count_mismatch expected={len(rows_v1)} actual={len(rows)}")
    keys = [(r["code"], r["theme"]) for r in rows]
    if len(keys) != len(set(keys)):
        errors.append("duplicate code/theme rows")
    for r in rows:
        if len(r.get("code", "")) != 6 or not r.get("code", "").isdigit():
            errors.append(f"{r.get('code')} invalid six-digit code")
        if r.get("trading_pool_decision") not in TRADING_LABELS:
            errors.append(f"{r['code']} invalid trading_pool_decision={r.get('trading_pool_decision')}")
        if r.get("business_evidence_decision") not in BUSINESS_LABELS:
            errors.append(f"{r['code']} invalid business_evidence_decision={r.get('business_evidence_decision')}")
        if not r.get("evidence_url"):
            errors.append(f"{r['code']} {r['theme']} missing evidence_url")
        if r.get("leverage_risk_flag") not in YES_NO:
            errors.append(f"{r['code']} invalid leverage_risk_flag={r.get('leverage_risk_flag')}")
    for r in rows:
        if r["trading_pool_decision"] in {"default", "expanded"}:
            if "ST" in r.get("explicit_hard_rule_hit", ""):
                errors.append(f"{r['code']} ST row entered {r['trading_pool_decision']}")
            if "financial_quality_flag=fail" in r.get("explicit_hard_rule_hit", ""):
                errors.append(f"{r['code']} financial_quality_flag=fail row entered {r['trading_pool_decision']}")
            if "market_cap<30亿" in r.get("explicit_hard_rule_hit", ""):
                errors.append(f"{r['code']} market_cap<30亿 row entered {r['trading_pool_decision']}")
            if "avg_amount_20d<1亿" in r.get("explicit_hard_rule_hit", ""):
                errors.append(f"{r['code']} avg_amount_20d<1亿 row entered {r['trading_pool_decision']}")
    required = {
        ("000938", "AI"): "expanded",
        ("300857", "AI"): "expanded",
        ("002313", "AI"): "excluded_by_rules",
        ("300212", "AI"): "excluded_by_rules",
    }
    by_key = {(r["code"], r["theme"]): r for r in rows}
    for key, expected in required.items():
        actual = by_key.get(key, {}).get("trading_pool_decision")
        if actual != expected:
            errors.append(f"{key[0]} {key[1]} expected {expected}, got {actual}")
    for r in rows:
        if (
            r.get("trading_pool_decision") == "excluded_by_rules"
            and r.get("leverage_risk_flag") == "yes"
            and r.get("explicit_hard_rule_hit") == "none"
        ):
            errors.append(f"{r['code']} excluded_by_rules due to debt_to_asset>80% alone")
    return errors


def write_qa(
    rows_v1: list[dict[str, str]],
    rows: list[dict[str, str]],
    errors: list[str],
) -> None:
    counts = before_after_counts(rows_v1, rows)
    manual_rows = [
        r for r in rows
        if (r["code"], r["theme"]) in MANUAL_CASES
    ]
    lines: list[str] = []
    lines.append("# Stock Pool v1.2 QA Report")
    lines.append("")
    lines.append(f"Generated at: {datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Scope")
    lines.append(f"- v1.1 input rows: {len(rows_v1)}")
    lines.append(f"- v1.2 output rows: {len(rows)}")
    lines.append("- No new web data was fetched; v1.2 is derived from v1.1 outputs and scorecard fields.")
    lines.append("- Annual-report evidence text, URLs, strength, and business evidence decisions are preserved.")
    lines.append("")
    lines.append("## Rule Update")
    lines.append("- debt_to_asset>80% is now explicit: default_pool=exclude; expanded_pool=allow_with_leverage_risk_flag; hard_exclude=no unless another explicit hard rule is hit.")
    lines.append("- Explicit hard rules: ST; financial_quality_flag=fail; market_cap<30亿; avg_amount_20d<1亿.")
    lines.append("- valuation=high is retained as a risk note only.")
    lines.append("- conditional rows cannot enter default, but may enter expanded.")
    lines.append("")
    lines.append("## Before / After Counts")
    for label, values in counts.items():
        lines.append(f"- {label}: before={values['before']} after={values['after']}")
    lines.append("")
    lines.append("## Manual Case Final Decisions")
    for r in manual_rows:
        lines.append(
            f"- {r['code']} {r['name']} {r['theme']}: "
            f"trading_pool_decision={r['trading_pool_decision']}; "
            f"rule_exception_resolution={r['rule_exception_resolution']}; "
            f"leverage_risk_flag={r['leverage_risk_flag']}; "
            f"financial_risk_level={r['financial_risk_level']}; "
            f"reason={r['v1_2_decision_reason']}"
        )
    lines.append("")
    lines.append("## QA Checks")
    lines.append("- Row count equals v1.1 input row count")
    lines.append("- No duplicate code/theme rows")
    lines.append("- Labels are restricted to allowed values")
    lines.append("- evidence_url remains non-empty")
    lines.append("- 000938 and 300857 are in expanded_pool_v1_2.csv")
    lines.append("- 002313 and 300212 remain in excluded_by_rules_v1_2.csv")
    lines.append("- No explicit hard-rule hit enters default or expanded")
    lines.append("- debt_to_asset>80% alone does not cause excluded_by_rules")
    lines.append("")
    lines.append("## Validation Errors")
    if errors:
        lines.extend(f"- {error}" for error in errors)
    else:
        lines.append("- None")
    OUT_QA.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    rows_v1 = read_csv(INPUT_V1_1)
    scorecard = read_csv(SCORECARD)
    score_by_key = {(code6(r["code"]), r["theme"]): r for r in scorecard}

    rows: list[dict[str, str]] = []
    for row in rows_v1:
        key = (code6(row["code"]), row["theme"])
        rows.append(apply_v1_2_decision(row, score_by_key.get(key, {})))

    rules = build_rules_v1_2(read_csv(RULES_V1))
    errors = validate(rows, rows_v1)

    base_fields = list(rows_v1[0].keys())
    extra_fields = [
        "explicit_hard_rule_hit",
        "leverage_risk_flag",
        "leverage_risk_reason",
        "rule_exception_resolution",
        "financial_risk_level",
        "default_pool_allowed",
        "valuation_risk_note_v1_2",
        "v1_2_decision_reason",
    ]
    fields = [*base_fields, *[f for f in extra_fields if f not in base_fields]]
    rule_fields = ["rule", "current_value", "default_pool", "expanded_pool", "hard_exclude", "reason"]

    write_csv(OUT_RULES, rules, rule_fields)
    write_csv(OUT_SUGGESTIONS, rows, fields)
    write_csv(OUT_DEFAULT, [r for r in rows if r["trading_pool_decision"] == "default"], fields)
    write_csv(OUT_EXPANDED, [r for r in rows if r["trading_pool_decision"] == "expanded"], fields)
    write_csv(OUT_EXCLUDED_RULES, [r for r in rows if r["trading_pool_decision"] == "excluded_by_rules"], fields)
    write_csv(
        OUT_EXCLUDED_BIZ,
        [r for r in rows if r["trading_pool_decision"] == "excluded_by_business_mismatch"],
        fields,
    )
    write_csv(
        OUT_RESOLUTION,
        [r for r in rows if (r["code"], r["theme"]) in MANUAL_CASES],
        fields,
    )
    write_qa(rows_v1, rows, errors)

    print(f"rows={len(rows)}")
    print(f"counts={dict(sorted(Counter(r['trading_pool_decision'] for r in rows).items()))}")
    print(f"validation_errors={len(errors)}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
