# Formal Data Readiness Report v1.2

- baseline_mode: formal_data_readiness
- no investment conclusion
- not a point-in-time strategy backtest
- formal_ready: false
- research_universe_coverage: 1/5 (20.00%)
- duplicate_stock_date_rows: 0
- missing_qfq_close_count: 0
- missing_required_price_values: 0
- invalid_price_count: 0
- pre_close_failure_count: 0
- missing_required_benchmarks: 000300,000852
- critical_failure_count: 10
- fixed_300378: true
- manifest_status_counts: {'error': 10, 'ok': 2}

## Missing Date Sample
- none

## Caveats
- AkShare qfq prices are vendor-adjusted and not independently audited.
- Historical ST, suspension, and limit-up/down fields remain incomplete unless a separate trading-status source is added.
- pre_close is computed from qfq_close for stocks and close for benchmarks.
- This report checks data readiness only; it does not run a strategy backtest.
