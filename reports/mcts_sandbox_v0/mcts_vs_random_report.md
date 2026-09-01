# MCTS v0 versus Random Search — Historical-Seen Sandbox

```text
experiment_type=mcts_search_sandbox
sample_role=historical_seen
descriptive_only=true
alpha_claim_allowed=false
oos_claim_allowed=false
prospective_data_accessed=false
final_test_accessed=false
result_type=search_mechanism_diagnostic
```

## Result

MCTS did not show a search-efficiency advantage within this
historical_seen sandbox under the frozen three-part comparison rule. This is a
search-mechanism diagnostic, not Alpha discovery or OOS evidence.

## Search and redundancy

- primitives: `RETURN_60, VOL_20, AMOUNT_MEAN_20`; operators: `NEG, RANK, ADD, SUB, MUL`;
  maximum depth: `4`
- reward: mean per-period Spearman RankIC of the formula as written; no future-selected direction
- evaluations: MCTS `5000`; Random `5000`
- distinct formula strings: `3275`
- canonical formulas: `2833`
- unique exact rank signals: `22`
- unique Q5 portfolios: `19`
- overall rank-information redundancy: `98.02%`

## Per-seed comparison

| search_method   |     seed |   candidate_evaluations |   best_reward |   common_reward_p90_target |   evaluations_to_target |   syntactically_unique_count |   canonical_formula_count |   unique_rank_signal_count |   unique_portfolio_count |   portfolio_equivalent_count |   redundancy_rate |   failed_count |   runtime_seconds |
|:----------------|---------:|------------------------:|--------------:|---------------------------:|------------------------:|-----------------------------:|--------------------------:|---------------------------:|-------------------------:|-----------------------------:|------------------:|---------------:|------------------:|
| mcts            | 20260721 |                    1000 |     0.091907  |                   0.091907 |                      10 |                          524 |                       355 |                         10 |                        9 |                           58 |          0.850746 |            933 |          26.6679  |
| mcts            | 20260722 |                    1000 |     0.091907  |                   0.091907 |                      57 |                          514 |                       355 |                          8 |                        8 |                           66 |          0.878788 |            934 |          26.5925  |
| mcts            | 20260723 |                    1000 |     0.091907  |                   0.091907 |                      44 |                          519 |                       351 |                         10 |                        9 |                           62 |          0.83871  |            938 |           8.62933 |
| mcts            | 20260724 |                    1000 |     0.091907  |                   0.091907 |                      39 |                          533 |                       358 |                          9 |                        8 |                           63 |          0.857143 |            937 |           6.90013 |
| mcts            | 20260725 |                    1000 |     0.091907  |                   0.091907 |                       8 |                          534 |                       369 |                          9 |                        8 |                           77 |          0.883117 |            923 |           8.19307 |
| random          | 20260721 |                    1000 |     0.091907  |                   0.091907 |                      80 |                          610 |                       584 |                          9 |                        8 |                          156 |          0.942675 |            843 |          59.9487  |
| random          | 20260722 |                    1000 |     0.091907  |                   0.091907 |                      33 |                          633 |                       615 |                          9 |                        8 |                          146 |          0.939597 |            851 |          57.9984  |
| random          | 20260723 |                    1000 |     0.0922814 |                   0.091907 |                      40 |                          633 |                       610 |                          8 |                        7 |                          146 |          0.945946 |            852 |          15.4421  |
| random          | 20260724 |                    1000 |     0.091907  |                   0.091907 |                      70 |                          627 |                       595 |                          7 |                        7 |                          148 |          0.95302  |            851 |          15.9058  |
| random          | 20260725 |                    1000 |     0.0922814 |                   0.091907 |                      14 |                          606 |                       585 |                          9 |                        8 |                          170 |          0.947977 |            827 |          23.3588  |

## Top historical diagnostics

| candidate_id         | search_method   | formula                                                  |   mean_rankic |   median_rankic |   positive_rankic_ratio |   valid_periods |   q5_gross_cumulative_return |   q5_net_cumulative_return_20bps |   average_turnover |   endpoint_maximum_drawdown_gross |   average_selected_count |   portfolio_valid_periods |   period_coverage |   q1_mean_period_return |   q2_mean_period_return |   q3_mean_period_return |   q4_mean_period_return |   q5_mean_period_return |
|:---------------------|:----------------|:---------------------------------------------------------|--------------:|----------------:|------------------------:|----------------:|-----------------------------:|---------------------------------:|-------------------:|----------------------------------:|-------------------------:|--------------------------:|------------------:|------------------------:|------------------------:|------------------------:|------------------------:|------------------------:|
| mcts_20260722_0057   | mcts            | NEG(RETURN_60)                                           |     0.091907  |        0.103737 |                0.648148 |              54 |                      1.05122 |                         0.935524 |           0.543696 |                         -0.309725 |                  10.9074 |                        54 |                 1 |            -0.000705176 |               0.0267675 |               0.0250683 |               0.0158232 |               0.0197178 |
| mcts_20260722_0071   | mcts            | NEG(RETURN_60)                                           |     0.091907  |        0.103737 |                0.648148 |              54 |                      1.05122 |                         0.935524 |           0.543696 |                         -0.309725 |                  10.9074 |                        54 |                 1 |            -0.000705176 |               0.0267675 |               0.0250683 |               0.0158232 |               0.0197178 |
| mcts_20260722_0228   | mcts            | RANK(NEG(RETURN_60))                                     |     0.091907  |        0.103737 |                0.648148 |              54 |                      1.05122 |                         0.935524 |           0.543696 |                         -0.309725 |                  10.9074 |                        54 |                 1 |            -0.000705176 |               0.0267675 |               0.0250683 |               0.0158232 |               0.0197178 |
| random_20260722_0254 | random          | RANK(RANK(NEG(RETURN_60)))                               |     0.091907  |        0.103737 |                0.648148 |              54 |                      1.05122 |                         0.935524 |           0.543696 |                         -0.309725 |                  10.9074 |                        54 |                 1 |            -0.000705176 |               0.0267675 |               0.0250683 |               0.0158232 |               0.0197178 |
| mcts_20260723_0347   | mcts            | RANK(NEG(RETURN_60))                                     |     0.091907  |        0.103737 |                0.648148 |              54 |                      1.05122 |                         0.935524 |           0.543696 |                         -0.309725 |                  10.9074 |                        54 |                 1 |            -0.000705176 |               0.0267675 |               0.0250683 |               0.0158232 |               0.0197178 |
| random_20260723_0380 | random          | NEG(RANK(RETURN_60))                                     |     0.091907  |        0.103737 |                0.648148 |              54 |                      1.05122 |                         0.935524 |           0.543696 |                         -0.309725 |                  10.9074 |                        54 |                 1 |            -0.000705176 |               0.0267675 |               0.0250683 |               0.0158232 |               0.0197178 |
| random_20260723_0661 | random          | SUB(NEG(MUL(RETURN_60,RETURN_60)),RANK(RANK(RETURN_60))) |     0.0922814 |        0.102746 |                0.648148 |              54 |                      1.05122 |                         0.935524 |           0.543696 |                         -0.309725 |                  10.9074 |                        54 |                 1 |            -0.000705176 |               0.0267675 |               0.0250683 |               0.0158232 |               0.0197178 |
| mcts_20260724_0762   | mcts            | NEG(RANK(RETURN_60))                                     |     0.091907  |        0.103737 |                0.648148 |              54 |                      1.05122 |                         0.935524 |           0.543696 |                         -0.309725 |                  10.9074 |                        54 |                 1 |            -0.000705176 |               0.0267675 |               0.0250683 |               0.0158232 |               0.0197178 |
| random_20260724_0244 | random          | NEG(RANK(RETURN_60))                                     |     0.091907  |        0.103737 |                0.648148 |              54 |                      1.05122 |                         0.935524 |           0.543696 |                         -0.309725 |                  10.9074 |                        54 |                 1 |            -0.000705176 |               0.0267675 |               0.0250683 |               0.0158232 |               0.0197178 |
| random_20260725_0014 | random          | SUB(NEG(MUL(RETURN_60,RETURN_60)),RANK(RETURN_60))       |     0.0922814 |        0.102746 |                0.648148 |              54 |                      1.05122 |                         0.935524 |           0.543696 |                         -0.309725 |                  10.9074 |                        54 |                 1 |            -0.000705176 |               0.0267675 |               0.0250683 |               0.0158232 |               0.0197178 |

Return, turnover, 20bps cost, endpoint drawdown and selected-count fields above were
calculated only after search. They did not enter reward and did not trigger any
search-space or parameter change.

## Boundary and evidence

Inputs were restricted to previously viewed historical panels. Input hashes: `{'data/processed/mom60_factor_panel_v1_3.csv': '2c25fb4196da19b24463cdfdb23fa821c85cf22e2d53576d8f13fe792c0aa341', 'data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv': '37330b3c21000c6a0b36c68f7e587628945a910a79b35992160e78d93c36a4e4', 'data/processed/adjusted_price_panel_v1_2.csv': '94529144dd9273d79647a4fc470df97056a04ea443852fe19d9aaaf1af3b0f1e'}`.
The runner rejects any path containing `prospective` or `final_test`. No Phase B file,
decision, threshold, or output was modified.
