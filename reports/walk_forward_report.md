# Walk-Forward Validation Report

- validation_type=rolling_train_select_test_evaluate
- parameter_source=existing_portfolio_experiments_only
- in_sample_best_is_not_strategy_proof=true

## Split Results

| split   | train_start   | train_end   | test_start   | test_end   | selection_metric         | selected_experiment                    |   train_selected_metric |   test_annualized_return |   test_annualized_excess_return |   test_information_ratio |   test_annualized_turnover |   test_average_holding_count |
|:--------|:--------------|:------------|:-------------|:-----------|:-------------------------|:---------------------------------------|------------------------:|-------------------------:|--------------------------------:|-------------------------:|---------------------------:|-----------------------------:|
| wf_1    | 2020-01-31    | 2022-12-31  | 2022-12-31   | 2023-12-31 | annualized_excess_return | top200_equal                           |                 -0.0391 |                  -0.0979 |                         -0.0448 |                  -0.3999 |                    16.4081 |                      200.182 |
| wf_2    | 2021-01-31    | 2023-12-31  | 2023-12-31   | 2026-04-30 | annualized_excess_return | top100_buy100_sell300_max_turnover_0.5 |                 -0.0163 |                   0.2336 |                         -0.0828 |                  -0.6364 |                     6.2138 |                      382.63  |

## Overall

- out_of_sample_overall_annualized_excess_return=-0.06377747765
- out_of_sample_average_information_ratio=-0.5181605268
- out_of_sample_average_turnover=11.31095376
- parameter_stability=unstable
- out_of_sample_negative_excess=yes

## Caveats

- Do not treat the full-sample best portfolio setting as evidence of a valid strategy.
- Walk-forward splits still inherit current universe survivorship risk.
- total_market_cap return proxy is not strict adjusted-price return.
- Same-day zero amount, zero volume, one-price locked, and halt/status sell blocks are forced holds; explicit limit-down exit prices remain incomplete.