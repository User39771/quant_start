# Stock Pool v1.2 Adjusted-Return Baseline Result Review

## Research Position

- research_baseline_only=true
- adjusted_return_source=qfq
- current_universe_historical_performance=true
- point_in_time_strategy_backtest=false
- survivorship_or_future_universe_bias=true
- close_to_close_execution_assumption=true
- execution_sim_ready=false
- formal_performance_conclusion_allowed=false
- no_investment_conclusion=true

This document explains the existing adjusted-return baseline outputs. It is a description of the data, calculation scope, and diagnostics. It does not assess strategy quality, issue a security recommendation, or establish an investment conclusion.

## Data Coverage And Scope

The adjusted-price panel contains 70,145 rows for 56 stocks from 2020-01-02 through 2026-06-16. Its qfq row coverage ratio is 0.963590 and stock coverage ratio is 0.964286. The adjusted-price QA found no duplicate stock/date rows and no exact duplicate rows.

The research universe has 56 unique stock codes after multi-theme deduplication. The expanded-only universe has 55. A code that appears under more than one theme is held once in the baseline denominator and is not assigned multiple weights.

Each universe and cost scenario contains 79 rebalance periods: 78 full 20-trading-day periods and one final partial period. The report therefore covers four portfolio scenarios and 12 scenario/benchmark summary rows. The two cost assumptions are 0 and 0.001; the three benchmark codes are 000300, 000852, and 399006.

| Universe | Unique stocks | Headline average coverage | Headline minimum coverage | Headline period count |
| --- | ---: | ---: | ---: | ---: |
| research_universe_v1_2 | 56 | 94.52% | 83.93% | 57 |
| expanded_only_v1_2 | 55 | 94.42% | 83.64% | 57 |

The coverage denominator remains the complete deduplicated universe. No full-sample effective-universe filter was applied. This avoids silently removing stocks on the basis of later data completeness, but it also means coverage must be read alongside the period diagnostics.

## Actual Headline Baseline Window

The first 15 periods are pre-baseline diagnostics because they do not meet the required continuity and coverage conditions. The first valid headline rebalance date is 2021-03-31. The last completed headline period ends on 2025-12-11.

The headline sequence therefore consists of 57 continuous full periods, each spanning 20 common trading days. The final partial period is retained as a diagnostic record only. It is not included in headline cumulative return, CAGR, volatility, Sharpe ratio, Calmar ratio, tracking error, or information ratio.

After the termination point, six periods remain in the source panel. They are preserved as post-termination diagnostics and are not appended to headline NAV. This distinction matters: the source panel continues to 2026-06-16, but the headline NAV does not represent a continuous series through that later date.

## Why Headline NAV Terminates

All four portfolio scenarios terminate at the rebalance interval from 2025-12-11 to 2026-01-12. Stock 002049 had a valid qfq price at the rebalance date and was therefore part of the period's initial eligible target set, but it lacked a valid qfq price at the period end.

The period is consequently marked `end_price_missing` and `invalid_period`. The remaining stocks are not reweighted after the fact: deleting 002049 at the end of the interval would change the portfolio that existed at the period start. For the research universe, the start-date eligible count was 54 of 56; for expanded-only it was 53 of 55. Despite those coverage ratios being above 80%, the missing endpoint price invalidates the complete period.

`scenario_status=terminated_on_invalid_period`, `termination_date=2025-12-11`, and `termination_reason=end_price_missing` should therefore be read as a data-continuity boundary. They do not describe a market event or an investment outcome.

## Reading The Summary Fields

### Scope And Continuity Fields

- `universe_count`: unique stock-code count used as the coverage denominator.
- `scenario_status`: whether the scenario formed a continuous headline sequence or stopped at an invalid period.
- `baseline_start_date`: first rebalance date of the confirmed continuous headline sequence.
- `last_full_period_end`: end date of the last complete period included in headline metrics.
- `termination_date` and `termination_reason`: first post-start period that broke continuity and why.
- `valid_period_count`: complete, continuous headline periods used in metric calculations.
- `invalid_period_count`: full periods failing the period-validity rule across the full calendar, including pre-baseline diagnostics and later diagnostic periods; it is not a count of headline observations.
- `average_coverage_ratio` and `minimum_coverage_ratio`: start-date eligible-stock coverage over headline periods.
- `dropped_stock_period_count`: target stock-periods with a missing endpoint price. The current summary records two such occurrences per scenario across the full calendar.
- `latest_partial_period_return`: diagnostic-only partial-period value. It is blank for the current scenarios because the partial period occurs after headline termination.

### Return, Risk, And Cost Fields

- `cumulative_return`: compounded net return across headline periods only, calculated as the product of `(1 + net_return)` minus one.
- `annualized_return`: CAGR over the calendar days from `baseline_start_date` to `last_full_period_end`.
- `annualized_volatility`: standard deviation of headline net period returns, annualized with `sqrt(252/20)`.
- `sharpe_ratio`: mean headline net period return divided by its standard deviation, with risk-free rate set to zero and the same annualization factor.
- `period_endpoint_maximum_drawdown`: minimum drawdown calculated from NAV at rebalance-period endpoints. It can understate maximum drawdown occurring inside a period because daily portfolio NAV is not simulated.
- `calmar_ratio`: annualized return divided by the absolute value of endpoint maximum drawdown when drawdown is non-zero.
- `positive_period_ratio`: share of headline periods with positive net return.
- `average_turnover`: average rebalancing turnover, based on drifted previous-period weights rather than a simple comparison of two target weight vectors.
- `total_cost_drag`: sum of `turnover * transaction_cost` over headline periods. It is zero in the 0-cost scenario and a mechanical sensitivity value in the 0.001 scenario.

These fields are descriptive statistics of the fixed current universe under the stated calculation rules. They are not a statement about future results, tradeability, or allocation suitability.

## Benchmark Comparison Interpretation

Each benchmark uses the same 57 headline period start/end dates as the portfolio. `benchmark_comparison_valid=true` for all 12 summary rows means the corresponding benchmark had valid endpoint closes for those exact intervals. It is a date-coverage check, not a validation of the stock pool or an assessment of the portfolio.

- `benchmark_cumulative_return`, `benchmark_annualized_return`, and `benchmark_annualized_volatility` apply the same interval set and annualization convention to the index close series.
- `benchmark_period_endpoint_maximum_drawdown` is the benchmark analogue of the portfolio endpoint drawdown measure and has the same intraperiod limitation.
- `portfolio_minus_benchmark_cumulative_return` is the arithmetic difference between the two interval-matched cumulative returns. It is not a forecast and is not the compounded active-return path.
- `active_return` is the portfolio net period return minus the benchmark period return.
- `tracking_error` is the annualized standard deviation of active returns across headline periods.
- `information_ratio` is the mean active return divided by the standard deviation of active returns, using the same `sqrt(252/20)` factor.

The benchmark outputs are historical comparisons of a current-universe research baseline. They must not be read as evidence of a tradable alpha process or as an investment conclusion.

## QA Signals And Remaining Limits

The baseline QA records 176 issue rows: 60 pre-baseline diagnostics, 8 endpoint-price-missing records, 4 termination records, 96 stock return outliers, 4 portfolio return outliers, and 4 final-partial-period records. Return outliers are review flags only; they were not automatically removed from otherwise valid headline periods.

The upstream qfq manifest still has two latest `error` statuses (002544 and 300133) and three latest `partial_ok` statuses (002049, 002131, and 301171). These rows are documented as data caveats. They do not change the explicit termination rule described above.

The principal limits are:

- The stock pool uses 2026 information, producing current-universe and survivorship-like bias when viewed over earlier history.
- Qfq values are vendor-adjusted prices rather than independently audited total-return data.
- Historical ST, suspension, limit-up/down, and complete trading-status fields are unavailable. The close-to-close calculation is not a simulation of executable orders.
- The missing 002049 endpoint prevents extending the continuous headline NAV beyond 2025-12-11. Later data cannot be joined onto the same headline series without changing the stated continuity rule.
- Endpoint-only drawdown and 20-trading-day sampling do not expose intraperiod path risk.

## Evidence Sources

- `reports/adjusted_stock_pool_baseline_summary_v1_2.csv`: metric values and benchmark comparisons.
- `reports/adjusted_stock_pool_baseline_periods_v1_2.csv`: period phases, coverage, eligibility, termination, and partial-period treatment.
- `reports/adjusted_stock_pool_baseline_nav_v1_2.csv`: headline NAV and benchmark endpoint alignment.
- `reports/adjusted_stock_pool_baseline_qa_v1_2.csv`: diagnostic counts and issue classifications.
- `reports/adjusted_price_panel_QA_v1_2.md`: adjusted-price coverage, panel grain, and upstream qfq caveats.
