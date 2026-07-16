# LOWVOL20 Locked-Grid Long-Only Prototype v1.5

## Status

- research prototype only
- full_period_count: 57
- period_grid_equal: true
- critical_qa_failures: 0
- formal_performance_conclusion_allowed=false
- execution_sim_ready=false
- no_investment_conclusion=true

## Primary answers

1. Volatility: Q5 0.3231 versus universe 0.4016; lower=true.
2. Endpoint drawdown: Q5 -0.3256 versus universe -0.3635; improved=true.
3. Cumulative return difference: -0.0813; relative wealth: -0.0370.
4. Q5 Sharpe/Sortino/Calmar=0.6692/1.2437/0.5316; universe=0.6169/1.2426/0.5022. Risk-adjusted metrics improved=true.
5. At costs 0.001 and 0.002 Q5 relative wealth versus the matched universe remains negative (-0.0660, -0.0942); the direction is unchanged.
6. Top five positive Q5 periods account for 42.80% of positive arithmetic period returns; this is a concentration diagnostic, not a deletion rule.
7. Q5-Q1 is a factor diagnostic and is not an executable A-share long-short strategy.

Confirmed suspension and unresolved missing observations are recorded separately. No forward-fill, backfill, next-day substitution, inverse-volatility weighting, parameter search, timing, stop loss, momentum, reversal, or liquidity filter is used.
