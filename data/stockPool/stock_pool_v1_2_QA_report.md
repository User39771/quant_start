# Stock Pool v1.2 QA Report

Generated at: 2026-07-05T00:07:36

## Scope
- v1.1 input rows: 113
- v1.2 output rows: 113
- No new web data was fetched; v1.2 is derived from v1.1 outputs and scorecard fields.
- Annual-report evidence text, URLs, strength, and business evidence decisions are preserved.

## Rule Update
- debt_to_asset>80% is now explicit: default_pool=exclude; expanded_pool=allow_with_leverage_risk_flag; hard_exclude=no unless another explicit hard rule is hit.
- Explicit hard rules: ST; financial_quality_flag=fail; market_cap<30亿; avg_amount_20d<1亿.
- valuation=high is retained as a risk note only.
- conditional rows cannot enter default, but may enter expanded.

## Before / After Counts
- default: before=1 after=1
- expanded: before=54 after=56
- excluded_by_rules: before=58 after=56
- excluded_by_business_mismatch: before=0 after=0

## Manual Case Final Decisions
- 000938 紫光股份 AI: trading_pool_decision=expanded; rule_exception_resolution=allow_expanded; leverage_risk_flag=yes; financial_risk_level=medium; reason=business evidence confirmed/core; no explicit hard rule hit; debt_to_asset>80% alone should not hard-exclude; but inventory, covenant and leverage risk require monitoring.
- 002313 日海智能 AI: trading_pool_decision=excluded_by_rules; rule_exception_resolution=keep_excluded_explicit_hard_rules; leverage_risk_flag=yes; financial_risk_level=high; reason=explicit hard rules hit: financial_quality_flag=fail, market_cap<30亿, avg_amount_20d<1亿. debt_to_asset>80% is secondary, not the primary exclusion reason.
- 300212 *ST易录 AI: trading_pool_decision=excluded_by_rules; rule_exception_resolution=keep_excluded_explicit_hard_rules; leverage_risk_flag=yes; financial_risk_level=high; reason=explicit hard rules hit: ST and financial_quality_flag=fail. debt_to_asset>80% is secondary.
- 300857 协创数据 AI: trading_pool_decision=expanded; rule_exception_resolution=allow_expanded_with_high_risk_flag; leverage_risk_flag=yes; financial_risk_level=high; reason=business evidence confirmed; no explicit hard rule hit; AI/compute growth and positive CFO support expanded inclusion; leveraged expansion and capex risk require high-risk label.

## QA Checks
- Row count equals v1.1 input row count
- No duplicate code/theme rows
- Labels are restricted to allowed values
- evidence_url remains non-empty
- 000938 and 300857 are in expanded_pool_v1_2.csv
- 002313 and 300212 remain in excluded_by_rules_v1_2.csv
- No explicit hard-rule hit enters default or expanded
- debt_to_asset>80% alone does not cause excluded_by_rules

## Validation Errors
- None
