# Portfolio Construction Experiment Report

- objective=turn_existing_factor_scores_into_tradable_portfolios
- factor=composite_alpha_ic_weighted
- rebalance_frequency=monthly
- benchmark=tradable_universe_equal_weight
- transaction_cost_rate=0.002_one_way_per_traded_notional
- sample_inference=in_sample_comparison_only

## Why IC Is Not Portfolio Alpha

- IC strong does not guarantee portfolio alpha because IC measures cross-sectional ordering, while a live portfolio realizes only selected names, weights, turnover, costs, and constraint drag.
- A narrow Top 50 portfolio can amplify fast-factor noise: small rank changes force full exits and entries even when the score spread is economically weak.
- Turnover directly reduces NAV through transaction_cost = turnover * one_way_cost_rate; high annualized turnover can erase a statistically useful signal.
- max_turnover can also create tail positions when weight changes are only partially executed; dust and max_positions controls are used to diagnose and limit that behavior.

## Experiment Metrics

| experiment                                            | annualized_return   | annualized_excess_return   | max_drawdown   | excess_max_drawdown   | sharpe_ratio   | information_ratio   | annualized_turnover   | average_holding_count   | median_holding_count   | max_holding_count   | average_positions_below_10bp   | average_top10_weight   | average_effective_number_of_positions   | average_trade_count   | average_buy_count   | average_sell_count   | average_blocked_sell_count   | average_forced_hold_weight   | average_transaction_cost   | average_active_factor_score   |
|:------------------------------------------------------|:--------------------|:---------------------------|:---------------|:----------------------|:---------------|:--------------------|:----------------------|:------------------------|:-----------------------|:--------------------|:-------------------------------|:-----------------------|:----------------------------------------|:----------------------|:--------------------|:---------------------|:-----------------------------|:-----------------------------|:---------------------------|:------------------------------|
| baseline_top50_equal_no_buffer                        |                     |                            |                |                       |                |                     |                       |                         |                        |                     |                                |                        |                                         |                       |                     |                      |                              |                              |                            |                               |
| top100_equal                                          |                     |                            |                |                       |                |                     |                       |                         |                        |                     |                                |                        |                                         |                       |                     |                      |                              |                              |                            |                               |
| top200_equal                                          |                     |                            |                |                       |                |                     |                       |                         |                        |                     |                                |                        |                                         |                       |                     |                      |                              |                              |                            |                               |
| top50_buy50_sell150                                   |                     |                            |                |                       |                |                     |                       |                         |                        |                     |                                |                        |                                         |                       |                     |                      |                              |                              |                            |                               |
| top100_buy100_sell300                                 |                     |                            |                |                       |                |                     |                       |                         |                        |                     |                                |                        |                                         |                       |                     |                      |                              |                              |                            |                               |
| top100_buy100_sell300_max_turnover_0.5                |                     |                            |                |                       |                |                     |                       |                         |                        |                     |                                |                        |                                         |                       |                     |                      |                              |                              |                            |                               |
| top100_buy100_sell300_max_turnover_0.5_dust_maxpos300 |                     |                            |                |                       |                |                     |                       |                         |                        |                     |                                |                        |                                         |                       |                     |                      |                              |                              |                            |                               |

## Interpretation

- baseline_annualized_excess_return=NaN
- baseline_annualized_turnover=NaN
- holding_count_diagnostic.top100_buy100_sell300_max_turnover_0.5=NaN
- holding_count_diagnostic.top100_buy100_sell300_max_turnover_0.5_dust_maxpos300=NaN

## Walk-Forward Comparison

- walk_forward_status=not_run_in_this_report

## Caveats

- sample_inference=in_sample_comparison_only; do not use the best full-sample parameter as proof of strategy validity.
- next_required_validation=walk_forward_or_out_of_sample
- survivorship_bias_caveat=current universe membership may omit delisted historical stocks.
- total_market_cap_return_proxy=not_strict_adjusted_price_return
- sell_side_constraints=same_day_untradable_forced_hold_minimal_model; explicit limit-down exit prices remain incomplete