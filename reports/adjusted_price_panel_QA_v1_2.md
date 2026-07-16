# Adjusted Price Panel QA v1.2

This report checks data quality only. It does not run a strategy, does not produce an investment conclusion, and does not modify source CSV files.

## Decisions
- data_quality_pass: true
- adjusted_return_baseline_allowed: true
- formal_performance_conclusion_allowed: false
- execution_sim_ready: false

Downstream join/backtest code must apply `code6` normalization before using this panel, because CSV readers can drop leading zeros from `stock_code`.

## Core Metrics
- rows: 70145
- stocks: 56
- universe stocks: 56
- parsed date range: 2020-01-02 to 2026-06-16
- row_coverage_ratio: 0.96359
- stock_coverage_ratio: 0.964286
- duplicate stock/date rows: 0
- exact duplicate rows: 0

## Issue Counts
- by severity: {'Medium': 5}
- manifest_partial_ok_status: 3
- manifest_error_status: 2

## Latest Manifest Status
- ok: 44
- cached_ok: 7
- partial_ok: 3
- error: 2
- latest error stocks: 002544, 300133
- latest partial_ok stocks: 002049, 002131, 301171

## Source Distribution
- ak.stock_zh_a_daily: rows=66322, stocks=53
- missing: rows=2554, stocks=5
- ak.stock_zh_a_hist: rows=1269, stocks=1

## Caveats
- `formal_performance_conclusion_allowed` remains false even if adjusted-return baseline is allowed.
- `execution_sim_ready` remains false because historical ST, suspension, and limit-up/down states are still missing.
- Return outliers and qfq/raw alignment warnings are review flags, not automatic investment conclusions.
