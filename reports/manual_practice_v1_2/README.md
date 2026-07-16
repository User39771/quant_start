# Manual Practice v1.2

This directory is a learning exercise built from the existing adjusted-return baseline.

## Selected Scenario

- universe: `research_universe_v1_2`
- transaction_cost: `0.0`
- benchmark: `000300`
- headline period count: `57`
- period range: `2021-04-29` to `2025-12-11`
- rolling Sharpe window: `12` rebalance periods

## Exercises

1. `nav_vs_benchmark.png`: compound period returns into NAV with
   `NAV_t = NAV_(t-1) * (1 + r_t)`.
2. `period_endpoint_drawdown.png`: calculate drawdown from the running NAV peak.
   The lowest period-end drawdown is `-36.73%`. This is not daily
   maximum drawdown and can miss intraperiod losses.
3. `rolling_sharpe.png`: compute a rolling zero-risk-free-rate Sharpe from period
   returns, annualized with `sqrt(252 / 20)`.

## Research Limits

- research_baseline_only=true
- current_universe_historical_performance=true
- point_in_time_strategy_backtest=false
- survivorship_or_future_universe_bias=true
- close_to_close_execution_assumption=true
- execution_sim_ready=false
- formal_performance_conclusion_allowed=false
- no investment conclusion

The outputs help practice financial time-series analysis. They are not a trading
recommendation and should not be interpreted as evidence of future performance.
