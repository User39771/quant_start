# QFQ Enrichment Readiness v1.2

- stock_coverage_ratio: 96.43%
- row_coverage_ratio: 96.36%
- adjusted_return_ready: true
- execution_sim_ready: false
- formal_performance_conclusion_allowed: false
- duplicate_stock_date_rows: 0
- current_failure_count: 2
- latest_final_status_counts: {'ok': 44, 'cached_ok': 7, 'partial_ok': 3, 'error': 2}

## qfq_raw_alignment_warning
- none

## invalid_cache_symbols
- none

## Caveats
- Coverage denominator is existing raw_base stock_code/trade_date rows, not natural days or a full benchmark calendar.
- qfq enrichment does not add historical ST, suspension, or limit-up/down state.
- This script never enables formal performance conclusions by itself.
