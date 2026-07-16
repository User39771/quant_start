# Adjusted Stock Pool Research Baseline v1.2

- research_baseline_only=true
- adjusted_return_source=qfq
- current_universe_historical_performance=true
- point_in_time_strategy_backtest=false
- survivorship_or_future_universe_bias=true
- close_to_close_execution_assumption=true
- execution_sim_ready=false
- formal_performance_conclusion_allowed=false
- no_investment_conclusion=true
- no investment conclusion

## Method

Eligibility uses rebalance-date qfq data only. A missing target end price invalidates the whole period; survivors are not reweighted.
No full-sample effective-universe filter is applied; the complete deduplicated stock pool remains the coverage denominator.
The baseline starts at the first of three consecutive valid 20-trading-day periods. This ex-post continuity choice is disclosed and is not point-in-time.
The final partial period is provisional and excluded from all headline metrics.
Annualized volatility, Sharpe, tracking error, and information ratio use sqrt(252/20). CAGR uses actual calendar days from baseline start to last full-period end.
`period_endpoint_maximum_drawdown` uses rebalance-period endpoint NAV and can understate daily intraperiod maximum drawdown.

## Scenario Summary

- research_universe_v1_2, cost=0.0, benchmark=000300: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=56, average_coverage=0.8788265306122448, minimum_coverage=0.8571428571428571, cumulative_return=0.18315623582720186, latest_partial_return=nan, benchmark_comparison_valid=true
- research_universe_v1_2, cost=0.0, benchmark=000852: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=56, average_coverage=0.8788265306122448, minimum_coverage=0.8571428571428571, cumulative_return=0.18315623582720186, latest_partial_return=nan, benchmark_comparison_valid=true
- research_universe_v1_2, cost=0.0, benchmark=399006: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=56, average_coverage=0.8788265306122448, minimum_coverage=0.8571428571428571, cumulative_return=0.18315623582720186, latest_partial_return=nan, benchmark_comparison_valid=true
- research_universe_v1_2, cost=0.001, benchmark=000300: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=56, average_coverage=0.8788265306122448, minimum_coverage=0.8571428571428571, cumulative_return=0.18138568300349478, latest_partial_return=nan, benchmark_comparison_valid=true
- research_universe_v1_2, cost=0.001, benchmark=000852: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=56, average_coverage=0.8788265306122448, minimum_coverage=0.8571428571428571, cumulative_return=0.18138568300349478, latest_partial_return=nan, benchmark_comparison_valid=true
- research_universe_v1_2, cost=0.001, benchmark=399006: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=56, average_coverage=0.8788265306122448, minimum_coverage=0.8571428571428571, cumulative_return=0.18138568300349478, latest_partial_return=nan, benchmark_comparison_valid=true
- expanded_only_v1_2, cost=0.0, benchmark=000300: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=55, average_coverage=0.8766233766233765, minimum_coverage=0.8545454545454545, cumulative_return=0.17555340714352652, latest_partial_return=nan, benchmark_comparison_valid=true
- expanded_only_v1_2, cost=0.0, benchmark=000852: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=55, average_coverage=0.8766233766233765, minimum_coverage=0.8545454545454545, cumulative_return=0.17555340714352652, latest_partial_return=nan, benchmark_comparison_valid=true
- expanded_only_v1_2, cost=0.0, benchmark=399006: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=55, average_coverage=0.8766233766233765, minimum_coverage=0.8545454545454545, cumulative_return=0.17555340714352652, latest_partial_return=nan, benchmark_comparison_valid=true
- expanded_only_v1_2, cost=0.001, benchmark=000300: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=55, average_coverage=0.8766233766233765, minimum_coverage=0.8545454545454545, cumulative_return=0.17378928170575314, latest_partial_return=nan, benchmark_comparison_valid=true
- expanded_only_v1_2, cost=0.001, benchmark=000852: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=55, average_coverage=0.8766233766233765, minimum_coverage=0.8545454545454545, cumulative_return=0.17378928170575314, latest_partial_return=nan, benchmark_comparison_valid=true
- expanded_only_v1_2, cost=0.001, benchmark=399006: status=terminated_on_invalid_period, start=2020-01-02, last_full_period_end=2021-03-03, termination_reason=end_price_missing, universe_count=55, average_coverage=0.8766233766233765, minimum_coverage=0.8545454545454545, cumulative_return=0.17378928170575314, latest_partial_return=nan, benchmark_comparison_valid=true

## QA

- qa_issue_rows=148
- stock_return_outlier=128
- end_price_missing=8
- baseline_terminated=4
- portfolio_return_outlier=4
- partial_final_period=4

## Caveats

- The universe was built with 2026 information, creating current-universe and survivorship-like bias.
- Historical ST, suspension, limit-up/down, and complete execution status are unavailable.
- Close-to-close returns are not executable trade prices.
- Extreme returns are flagged but retained unless a hard price/date/key QA rule fails.
- This output validates data and research plumbing only; it does not establish strategy effectiveness.
