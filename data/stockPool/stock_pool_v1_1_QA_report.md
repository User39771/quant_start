# Stock Pool v1.1 QA Report

Generated at: 2026-07-04T22:59:40

## Scope
- Input v1 evidence rows: 113
- v1.1 preserves original annual-report evidence fields and trading_pool_decision.
- v1.1 narrows manual follow-up to business evidence issues and non-explicit rule exceptions.

## stock_pool_rules.csv
- 最低日均成交额: 1亿 (保证基本流动性)
- 最低市值: 30亿 (避免过小盘噪声)
- ST: 一律剔除 (降低退市/流动性风险)
- financial_quality_flag=fail: 剔除 (财务质量不支持)
- valuation=high: 不剔除 (但 manual题材股常高估需结合增长)
- conditional: 不进默认池 (只进扩展研究池)

## Label Distribution
- trading_pool_decision: {'default': 1, 'excluded_by_rules': 58, 'expanded': 54}
- business_manual_review_needed: {'no': 113}
- rule_exception_review_needed: {'no': 109, 'yes': 4}

## Manual Follow-up
- manual_followup_true_required.csv rows: 4
- implicit_rule_exceptions.csv rows: 4
- affected_rows.csv debt_to_asset>80% rows: 4

## debt_to_asset>80% Check
- debt_to_asset>80% was used as an implicit high-risk rule in v1 logic, but it is not listed in stock_pool_rules.csv.
- 000938 紫光股份 AI: debt_to_asset=81.8492 trading=excluded_by_rules
- 002313 日海智能 AI: debt_to_asset=98.0906 trading=excluded_by_rules
- 300212 *ST易录 AI: debt_to_asset=113.16 trading=excluded_by_rules
- 300857 协创数据 AI: debt_to_asset=81.4821 trading=excluded_by_rules

## QA Checks
- Code format: 6-digit text strings
- Original trading_pool_decision: preserved
- Original evidence fields: preserved
- Manual business review is not automatically assigned to all excluded_by_rules rows

## Cleanup
- Removed explicit process/temp files: agent_a_liquidity_metrics.csv; agent_a_liquidity_notes.md; agent_b_financial_notes.md; agent_b_financial_quality.csv; agent_c_catalyst_risk.csv; agent_d_valuation_metrics.csv; agent_d_valuation_notes.md; tmp_test_report.pdf; tmp_test_report_full.pdf
- Preserved source inputs, v1/v1.1 outputs, scripts, and annual_report_cache for audit/reproducibility.

## Validation Errors
- None
