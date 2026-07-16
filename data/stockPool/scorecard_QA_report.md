# Scorecard QA Report

Generated at: 2026-07-02T09:48:09

## Scope
- Input file: theme_business_review_completed_after_manual (1).csv
- Input rows: 200
- Researched rows: 113
- Source review_status distribution: {'conditional': 93, 'core': 20}

## Output Distribution
- final_pool_suggestion: {'default_candidate': 1, 'expanded_candidate': 48, 'manual_check': 9, 'reject_for_trading_pool': 47, 'watch_only': 8}
- default_pool_candidates rows: 1
- conditional_watchlist_candidates rows: 65
- financial_liquidity_risk_flags rows: 104
- manual_research_required rows: 9

## Validation
- Row count check: passed
- Duplicate code/theme check: passed
- Illegal final_pool_suggestion labels: []
- Contradiction flags: 0
- Validation errors: 0

## Missing Data Counts
- inventory_to_revenue: 5
- roe: 1

## Source Notes
- Liquidity data: Agent A, Eastmoney quote and daily kline API.
- Valuation data: Agent D, Eastmoney RPT_VALUEANALYSIS_DET / data.eastmoney.com valuation page.
- Catalyst/risk notes: Agent C, materiality review plus manual audit context.
- Financial quality: Agent B, Eastmoney financial center and Tonghuashun/AkShare financial summaries with missing fields left unknown.

## Fetch / Calculation Caveats
- No financial endpoint exceptions captured in final merge.
- This file is a quality-filter and manual-review table only; it is not a buy/sell signal, return forecast, or recommendation.
- Conditional rows are never promoted to default_candidate by rule.
- Core rows only become default_candidate if ST/suspension, liquidity, and financial quality filters pass.

## Validation Errors
- None
