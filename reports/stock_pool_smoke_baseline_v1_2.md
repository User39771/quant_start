# Stock Pool Smoke Baseline v1.2

- smoke_only=true
- performance_conclusion_allowed=false
- baseline_type=current_universe_historical_performance
- not point-in-time strategy backtest
- no investment conclusion
- return_source=close_to_close_unadjusted_or_unverified
- rebalance_frequency=20_trading_days

## Scenario Summary
- expanded_only_v1_2 cost=0.0: nav=2.9685857622502065; min_coverage=0.01818181818181818; formal_performance_conclusion=forbidden
- expanded_only_v1_2 cost=0.001: nav=2.954860425830847; min_coverage=0.01818181818181818; formal_performance_conclusion=forbidden
- research_universe_v1_2 cost=0.0: nav=2.9941696079523603; min_coverage=0.017857142857142856; formal_performance_conclusion=forbidden
- research_universe_v1_2 cost=0.001: nav=2.980343501344103; min_coverage=0.017857142857142856; formal_performance_conclusion=forbidden

## Caveats
- Current universe is a 2026 v1.2 stock pool, so historical results have future-looking universe bias.
- Price data is not verified qfq adjusted close.
- Missing open/volume/pre_close, historical ST, suspension, and limit-up/down fields.
- No verified benchmark, so no excess return conclusion.
- Low-coverage periods are diagnostics only.
- 300378 high/low/date coverage issue remains from readiness report; close-to-close smoke can continue with caveat.

## Readiness Metadata
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
- benchmark: no verified full-window benchmark panel is

## Coverage Diagnostics
- low_coverage_periods=60

## Next Minimal Data Fetch Plan
- Fetch only the 56 active/research universe stocks, not all A-shares.
- Fetch qfq OHLC, volume, pre_close.
- Repair 300378 high/low/date coverage.
- Fetch benchmarks: 沪深300 + 中证1000; optionally 创业板指.
- Record failed symbols to CSV; no silent skips.
