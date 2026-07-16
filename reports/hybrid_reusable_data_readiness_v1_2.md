# Hybrid Reusable Data Readiness v1.2

- raw_base_ready: true
- benchmark_ready: true
- adjusted_return_ready: false
- execution_sim_ready: false
- formal_performance_conclusion_allowed: false
- stock_coverage: 56/56 (100.00%)
- missing_required_benchmarks: none
- manifest_status_counts: {'ok': 59}
- gap_counts: {'missing_high': 4, 'missing_low': 4, 'missing_amount': 3}

## Price Adjustment Judgement
- Existing `data/cache/price` files are treated as raw/unverified prices.
- Evidence: `akshare_code_inventory_v1_2` traces the cache primarily to PostgreSQL `public.stock_prices`; sampled files do not include `qfq_close`, `adj_factor`, or adjustment metadata.
- Therefore `adjusted_flag=false` for raw base panel rows.

## Caveats
- Raw base data can support cache-coverage checks and smoke close baselines only.
- Missing qfq/open/volume/pre_close keeps adjusted return and execution simulation readiness false.
- No silent forward fill is applied to missing stock prices.
