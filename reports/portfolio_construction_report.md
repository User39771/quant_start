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

| experiment                                            |   annualized_return |   annualized_excess_return |   max_drawdown |   excess_max_drawdown |   sharpe_ratio |   information_ratio |   annualized_turnover |   average_holding_count |   median_holding_count |   max_holding_count |   average_positions_below_10bp |   average_top10_weight |   average_effective_number_of_positions |   average_trade_count |   average_buy_count |   average_sell_count |   average_blocked_sell_count |   average_forced_hold_weight |   average_transaction_cost |   average_active_factor_score |
|:------------------------------------------------------|--------------------:|---------------------------:|---------------:|----------------------:|---------------:|--------------------:|----------------------:|------------------------:|-----------------------:|--------------------:|-------------------------------:|-----------------------:|----------------------------------------:|----------------------:|--------------------:|---------------------:|-----------------------------:|-----------------------------:|---------------------------:|------------------------------:|
| baseline_top50_equal_no_buffer                        |              0.0552 |                    -0.064  |        -0.2253 |               -0.2506 |         0.3822 |             -0.3467 |               17.6842 |                 49.2787 |                     50 |                  51 |                         0      |                 0.1964 |                                 50.1    |               76.5246 |             39.0492 |              36.4754 |                       0.0984 |                       0.002  |                     0.0029 |                        1.3158 |
| top100_equal                                          |              0.0677 |                    -0.0503 |        -0.1951 |               -0.2364 |         0.4374 |             -0.2824 |               16.5425 |                 98.5246 |                    100 |                 102 |                         0      |                 0.0982 |                                100.167  |              146.41   |             74.5574 |              68.1639 |                       0.1639 |                       0.0016 |                     0.0028 |                        1.2264 |
| top200_equal                                          |              0.0675 |                    -0.0486 |        -0.2017 |               -0.245  |         0.4372 |             -0.3101 |               15.3775 |                196.951  |                    200 |                 203 |                         0      |                 0.0491 |                                200.233  |              281.361  |            143.213  |             126.574  |                       0.2295 |                       0.0011 |                     0.0026 |                        1.1183 |
| top50_buy50_sell150                                   |              0.0802 |                    -0.0434 |        -0.1885 |               -0.2347 |         0.5183 |             -0.1881 |               12.5691 |                 49.2623 |                     50 |                  51 |                         0      |                 0.1964 |                                 50.0833 |               55.9344 |             28.8525 |              25.7869 |                       0.082  |                       0.0016 |                     0.0021 |                        1.2933 |
| top100_buy100_sell300                                 |              0.0893 |                    -0.0332 |        -0.1626 |               -0.2175 |         0.5641 |             -0.1436 |               10.8999 |                 98.5574 |                    100 |                 102 |                         0      |                 0.0982 |                                100.2    |              106.492  |             54.9672 |              44.5738 |                       0.1967 |                       0.002  |                     0.0018 |                        1.1955 |
| top100_buy100_sell300_max_turnover_0.5                |              0.0933 |                    -0.0317 |        -0.1375 |               -0.2605 |         0.6108 |             -0.1297 |                5.9613 |                376.344  |                    440 |                 522 |                       190.984  |                 0.096  |                                158.63   |              374.312  |             93.6885 |               1.2787 |                       0.4754 |                       0.0014 |                     0.001  |                        0.9516 |
| top100_buy100_sell300_max_turnover_0.5_dust_maxpos300 |              0.0974 |                    -0.0277 |        -0.1569 |               -0.233  |         0.6327 |             -0.1048 |                6.0572 |                195.41   |                    193 |                 273 |                        21.5082 |                 0.0983 |                                144.792  |              211.639  |             92.0492 |              18.8361 |                       0.2459 |                       0.0015 |                     0.001  |                        0.9918 |

## Interpretation

- baseline_annualized_excess_return=-0.06401220699
- baseline_annualized_turnover=17.68421666
- best_in_sample_by_excess_return=top100_buy100_sell300_max_turnover_0.5_dust_maxpos300
- best_in_sample_annualized_excess_return=-0.02767341451
- best_in_sample_information_ratio=-0.104830595
- excess_return_improvement_vs_baseline=0.03633879249
- turnover_change_vs_baseline=-11.62704112
- result_diagnosis=excess_return_improved_but_remains_negative
- holding_count_diagnostic.top100_buy100_sell300_max_turnover_0.5=376.3442623
- holding_count_diagnostic.top100_buy100_sell300_max_turnover_0.5_dust_maxpos300=195.4098361

## Walk-Forward Comparison

| split   | selected_experiment                    |   test_annualized_return |   test_annualized_excess_return |   test_information_ratio |   test_annualized_turnover |
|:--------|:---------------------------------------|-------------------------:|--------------------------------:|-------------------------:|---------------------------:|
| wf_1    | top200_equal                           |                  -0.0979 |                         -0.0448 |                  -0.3999 |                    16.4081 |
| wf_2    | top100_buy100_sell300_max_turnover_0.5 |                   0.2336 |                         -0.0828 |                  -0.6364 |                     6.2138 |

- walk_forward_average_test_excess=-0.06377747765
- walk_forward_parameter_stability=unstable
- walk_forward_negative_excess=yes
- validation_status=failed_out_of_sample_excess_remains_negative

## Caveats

- sample_inference=in_sample_comparison_only; do not use the best full-sample parameter as proof of strategy validity.
- next_required_validation=walk_forward_or_out_of_sample
- survivorship_bias_caveat=current universe membership may omit delisted historical stocks.
- total_market_cap_return_proxy=not_strict_adjusted_price_return
- sell_side_constraints=same_day_untradable_forced_hold_minimal_model; explicit limit-down exit prices remain incomplete