# Backtest Data Readiness Report

- generated_at: 2026-07-05T00:45:14
- baseline_type: current_universe_historical_performance
- point_in_time_strategy_backtest: no
- performance_conclusion_allowed: no
- baseline_status: smoke_only
- reason: qfq adjusted close / adjusted_close is missing or unverified in the reusable cache.

## Generated Data Prep Outputs
- data/processed/backtest_universe_expanded_only_v1_2.csv
- data/processed/backtest_universe_research_v1_2.csv
- data/processed/backtest_price_panel_v1_2.csv

## Universe Coverage
### expanded_only_v1_2
- rows: 56
- unique_codes: 55
- missing_price_files: 0 []
- date_range_by_code: start 2020-01-02..2022-11-21; end 2026-06-12..2026-06-16
- duplicate_code_date_rows: 0
- non_weekday_rows: 0
- abnormal_price_rows: 0
- missing_required_fields: {'high': 1, 'low': 1}
- missing_execution_fields: {'open': 55, 'volume': 55, 'pre_close': 55, 'adjusted_close_or_adj_factor': 55}
- missing_adjusted_close_or_adj_factor_codes: 55

### research_universe_v1_2
- rows: 57
- unique_codes: 56
- missing_price_files: 0 []
- date_range_by_code: start 2020-01-02..2022-11-21; end 2026-06-12..2026-06-16
- duplicate_code_date_rows: 0
- non_weekday_rows: 0
- abnormal_price_rows: 0
- missing_required_fields: {'high': 1, 'low': 1}
- missing_execution_fields: {'open': 56, 'volume': 56, 'pre_close': 56, 'adjusted_close_or_adj_factor': 56}
- missing_adjusted_close_or_adj_factor_codes: 56

## Explicit Data Gaps
- qfq adjusted close / adjusted_close / adj_factor: missing or unverified for reusable price cache.
- open: missing from data/cache/price cache.
- volume: missing from data/cache/price cache.
- pre_close: missing from data/cache/price cache.
- historical ST flags: not available in current price panel.
- suspension/trading status: not available as explicit historical field.
- limit-up/limit-down fields: not available; high/low/close/pre_close are insufficient because pre_close is missing.
- benchmark: no verified full-window benchmark panel is available.
- 300378: missing high/low and stale at 2026-06-12 in reusable price cache.

## Benchmark Candidates
- 000300: missing; files=none
- 399006: missing; files=none
- 000852: candidate_unverified; files=data/cache/cashflow/000852.csv; data/cache/price/000852.csv; data/cache/profit/000852.csv
- 000905: candidate_unverified; files=data/cache/cashflow/000905.csv; data/cache/price/000905.csv; data/cache/profit/000905.csv
- 000985: candidate_unverified; files=data/cache/cashflow/000985.csv; data/cache/price/000985.csv; data/cache/profit/000985.csv

## Data Reuse Decision
- Reuse data/stockPool/*_v1_2.csv as stock-pool source of truth.
- Reuse data/cache/price/*.csv for smoke price coverage and unadjusted/unverified price panel only.
- Reuse data/processed/pipeline_manifest.json and reports/market_data_realism_audit.md as prior QA evidence.
- Do not use current cache for formal performance conclusions until adjusted prices and tradability fields are added.

## Minimal Fetch Plan For A Later Turn
- Fetch only active research universe codes, not all A-shares.
- Fetch qfq OHLC or at least qfq adjusted close, volume, and pre_close for 56 unique active codes.
- Patch 300378 high/low/date coverage first.
- Fetch benchmark series for HS300 and at least one growth/small-cap comparator.
- Use sleep/retry and write failures to CSV; do not silently skip failed symbols.

## Smoke Baseline Rules
- First smoke baseline may use expanded_only_v1_2 equal weight with 20 trading day rebalance.
- The report title and metadata must state current_universe_historical_performance and not_point_in_time_backtest.
- No official performance conclusion is allowed before adjusted returns and tradability fields are available.
- price_panel_rows: 70145
