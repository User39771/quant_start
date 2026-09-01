# MCTS v1 versus Random Search — Historical-Seen Sandbox

```text
experiment_type=mcts_search_sandbox
version=v1
sample_role=historical_seen
descriptive_only=true
alpha_claim_allowed=false
oos_claim_allowed=false
prospective_data_accessed=false
final_test_accessed=false
classification=MCTS_SEARCH_ADVANTAGE_NOT_OBSERVED
```

## Result

This is a search-mechanism diagnostic on historical-seen data. It is neither Alpha discovery nor
OOS evidence. The frozen v0 three-part rule produced: `{"median_best_higher": false, "median_evaluations_to_target_lower": false, "median_rank_diversity_not_lower": true}`.

## Common mask

|   period_index |   signal_target_count |   common_count |   common_coverage | period_valid   |
|---------------:|----------------------:|---------------:|------------------:|:---------------|
|              3 |                    48 |             47 |          0.979167 | True           |
|              4 |                    48 |             48 |          1        | True           |
|              5 |                    48 |             48 |          1        | True           |
|              6 |                    50 |             50 |          1        | True           |
|              7 |                    50 |             50 |          1        | True           |
|              8 |                    51 |             51 |          1        | True           |
|              9 |                    51 |             51 |          1        | True           |
|             10 |                    51 |             51 |          1        | True           |
|             11 |                    51 |             51 |          1        | True           |
|             12 |                    51 |             51 |          1        | True           |
|             13 |                    51 |             51 |          1        | True           |
|             14 |                    51 |             51 |          1        | True           |
|             15 |                    52 |             52 |          1        | True           |
|             16 |                    52 |             52 |          1        | True           |
|             17 |                    52 |             52 |          1        | True           |
|             18 |                    52 |             52 |          1        | True           |
|             19 |                    52 |             52 |          1        | True           |
|             20 |                    53 |             53 |          1        | True           |
|             21 |                    53 |             53 |          1        | True           |
|             22 |                    53 |             53 |          1        | True           |
|             23 |                    54 |             54 |          1        | True           |
|             24 |                    54 |             54 |          1        | True           |
|             25 |                    54 |             54 |          1        | True           |
|             26 |                    54 |             54 |          1        | True           |
|             27 |                    54 |             54 |          1        | True           |
|             28 |                    54 |             54 |          1        | True           |
|             29 |                    54 |             54 |          1        | True           |
|             30 |                    54 |             54 |          1        | True           |
|             31 |                    54 |             54 |          1        | True           |
|             32 |                    54 |             54 |          1        | True           |
|             33 |                    54 |             54 |          1        | True           |
|             34 |                    54 |             54 |          1        | True           |
|             35 |                    54 |             54 |          1        | True           |
|             36 |                    54 |             54 |          1        | True           |
|             37 |                    54 |             54 |          1        | True           |
|             38 |                    54 |             54 |          1        | True           |
|             39 |                    54 |             54 |          1        | True           |
|             40 |                    54 |             54 |          1        | True           |
|             41 |                    54 |             54 |          1        | True           |
|             42 |                    54 |             54 |          1        | True           |
|             43 |                    54 |             54 |          1        | True           |
|             44 |                    54 |             54 |          1        | True           |
|             45 |                    54 |             54 |          1        | True           |
|             46 |                    54 |             54 |          1        | True           |
|             47 |                    54 |             54 |          1        | True           |
|             48 |                    54 |             54 |          1        | True           |
|             49 |                    54 |             54 |          1        | True           |
|             50 |                    54 |             54 |          1        | True           |
|             51 |                    54 |             54 |          1        | True           |
|             52 |                    54 |             54 |          1        | True           |
|             53 |                    54 |             54 |          1        | True           |
|             54 |                    54 |             54 |          1        | True           |
|             55 |                    54 |             54 |          1        | True           |
|             56 |                    54 |             54 |          1        | True           |

## Per-seed comparison

| search_method   |     seed |   proposal_attempts |   unique_reward_evaluations |   canonical_cache_hits |   rank_cache_hits |   invalid_attempts |   runtime_seconds | search_status   |   best_reward |   common_reward_p90_target |   unique_evaluations_to_target |   unique_canonical_formulas |   unique_rank_signals |   unique_q5_portfolios |   unique_information_per_100_evaluations |
|:----------------|---------:|--------------------:|----------------------------:|-----------------------:|------------------:|-------------------:|------------------:|:----------------|--------------:|---------------------------:|-------------------------------:|----------------------------:|----------------------:|-----------------------:|-----------------------------------------:|
| mcts            | 20260721 |                9443 |                        1000 |                   6935 |              1392 |                502 |           22.5671 | complete        |      0.15451  |                   0.122945 |                             16 |                        2508 |                  1000 |                    788 |                                      100 |
| mcts            | 20260722 |                9849 |                        1000 |                   7234 |              1497 |                507 |           22.7521 | complete        |      0.15451  |                   0.122945 |                             14 |                        2615 |                  1000 |                    760 |                                      100 |
| mcts            | 20260723 |                9940 |                        1000 |                   7318 |              1502 |                498 |           22.1917 | complete        |      0.15451  |                   0.122945 |                              8 |                        2622 |                  1000 |                    760 |                                      100 |
| mcts            | 20260724 |                9826 |                        1000 |                   7159 |              1552 |                517 |           23.0711 | complete        |      0.15451  |                   0.122945 |                             12 |                        2667 |                  1000 |                    776 |                                      100 |
| mcts            | 20260725 |                9734 |                        1000 |                   7167 |              1466 |                469 |           22.3688 | complete        |      0.15451  |                   0.122945 |                             13 |                        2567 |                  1000 |                    762 |                                      100 |
| random          | 20260721 |                3350 |                        1000 |                   1595 |               659 |                122 |           17.3483 | complete        |      0.157089 |                   0.122945 |                             10 |                        1755 |                  1000 |                    881 |                                      100 |
| random          | 20260722 |                3164 |                        1000 |                   1430 |               637 |                117 |           17.6537 | complete        |      0.156307 |                   0.122945 |                             11 |                        1734 |                  1000 |                    888 |                                      100 |
| random          | 20260723 |                3109 |                        1000 |                   1400 |               624 |                 99 |           17.846  | complete        |      0.155159 |                   0.122945 |                             11 |                        1709 |                  1000 |                    877 |                                      100 |
| random          | 20260724 |                3292 |                        1000 |                   1514 |               692 |                113 |           17.7356 | complete        |      0.155107 |                   0.122945 |                              4 |                        1778 |                  1000 |                    879 |                                      100 |
| random          | 20260725 |                3399 |                        1000 |                   1615 |               681 |                133 |           18.0685 | complete        |      0.157111 |                   0.122945 |                              8 |                        1784 |                  1000 |                    880 |                                      100 |

## Primitive usage

| primitive_set                         |   proposal_count |   unique_canonical_count |   unique_rank_signal_count |   reward_min |   reward_median |   reward_max |
|:--------------------------------------|-----------------:|-------------------------:|---------------------------:|-------------:|----------------:|-------------:|
| P_AMOUNT_MEAN_20                      |             4481 |                      218 |                         12 |   -0.142717  |      -0.142717  |    0.142717  |
| P_AMOUNT_MEAN_20;P_RETURN_60          |            11618 |                     1799 |                        586 |   -0.155804  |      -0.0358471 |    0.156693  |
| P_AMOUNT_MEAN_20;P_RETURN_60;P_VOL_20 |            13369 |                     4310 |                       2679 |   -0.157636  |      -0.0326256 |    0.157111  |
| P_AMOUNT_MEAN_20;P_VOL_20             |            11581 |                     1774 |                        593 |   -0.149792  |      -0.0376303 |    0.152831  |
| P_RETURN_60                           |             4616 |                      251 |                         12 |   -0.0906903 |      -0.0906903 |    0.0906903 |
| P_RETURN_60;P_VOL_20                  |            11900 |                     1847 |                        605 |   -0.105802  |      -0.0491052 |    0.109276  |
| P_VOL_20                              |             4464 |                      236 |                         14 |   -0.0956729 |      -0.0947887 |    0.0956729 |

## Cross-seed top-signal recurrence

| search_method   |   top_information_distinct_per_seed |   pooled_top_slots |   distinct_top_signatures |   signatures_seen_in_multiple_seeds |   maximum_seed_recurrence |   recurring_slot_share |
|:----------------|------------------------------------:|-------------------:|--------------------------:|------------------------------------:|--------------------------:|-----------------------:|
| mcts            |                                  10 |                 50 |                        12 |                                  11 |                         5 |                   0.76 |
| random          |                                  10 |                 50 |                        36 |                                   8 |                         5 |                   0.28 |

## Redundancy

- successful proposals: 62029
- distinct formula strings: 13940
- canonical formulas: 10435
- unique rank signals: 4407
- unique Q5 portfolios: 3263
- rank-information redundancy: 92.90%

| search_method   |   successful_proposals |   distinct_formulas |   canonical_formulas |   unique_rank_signals |   unique_q5_portfolios |   rank_information_redundancy |   canonical_cache_hits |   rank_cache_hits |
|:----------------|-----------------------:|--------------------:|---------------------:|----------------------:|-----------------------:|------------------------------:|-----------------------:|------------------:|
| mcts            |                  46299 |                7699 |                 4765 |                  1749 |                   1214 |                      0.962224 |                  33890 |              7409 |
| random          |                  15730 |                7729 |                 6976 |                  3678 |                   2924 |                      0.766179 |                   7437 |              3293 |

## Top information-distinct historical diagnostics

| candidate_id          | search_method   | formula                                                                                                                                         | primitive_set                         |   mean_rankic |   median_rankic |   positive_rankic_ratio |   valid_periods |   q5_gross_cumulative_return |   q5_net_cumulative_return_20bps |   average_turnover |   endpoint_maximum_drawdown_gross |   average_selected_count |   portfolio_valid_periods |   period_coverage |   q1_mean_period_return |   q2_mean_period_return |   q3_mean_period_return |   q4_mean_period_return |   q5_mean_period_return |
|:----------------------|:----------------|:------------------------------------------------------------------------------------------------------------------------------------------------|:--------------------------------------|--------------:|----------------:|------------------------:|----------------:|-----------------------------:|---------------------------------:|-------------------:|----------------------------------:|-------------------------:|--------------------------:|------------------:|------------------------:|------------------------:|------------------------:|------------------------:|------------------------:|
| random_20260725_01516 | random          | SUB(MUL(NEG(P_VOL_20),MUL(P_RETURN_60,P_AMOUNT_MEAN_20)),RANK(P_AMOUNT_MEAN_20))                                                                | P_AMOUNT_MEAN_20;P_RETURN_60;P_VOL_20 |      0.157111 |        0.186514 |                0.777778 |              54 |                      3.24614 |                          3.09307 |           0.349332 |                         -0.286816 |                  10.9074 |                        54 |                 1 |            -1.18433e-05 |               0.0126185 |               0.0201747 |               0.0213844 |               0.0317806 |
| random_20260721_02134 | random          | SUB(MUL(NEG(P_AMOUNT_MEAN_20),MUL(P_RETURN_60,P_VOL_20)),P_AMOUNT_MEAN_20)                                                                      | P_AMOUNT_MEAN_20;P_RETURN_60;P_VOL_20 |      0.157089 |        0.186514 |                0.777778 |              54 |                      3.24614 |                          3.09307 |           0.349332 |                         -0.286816 |                  10.9074 |                        54 |                 1 |            -1.18433e-05 |               0.0126185 |               0.0201747 |               0.0213844 |               0.0317806 |
| random_20260721_02570 | random          | SUB(NEG(P_AMOUNT_MEAN_20),MUL(MUL(P_RETURN_60,P_RETURN_60),MUL(P_AMOUNT_MEAN_20,P_RETURN_60)))                                                  | P_AMOUNT_MEAN_20;P_RETURN_60          |      0.156693 |        0.183114 |                0.759259 |              54 |                      3.14192 |                          3.00173 |           0.327393 |                         -0.308501 |                  10.9074 |                        54 |                 1 |            -0.00169154  |               0.0136166 |               0.0233745 |               0.0191822 |               0.0314185 |
| random_20260722_00836 | random          | MUL(SUB(MUL(P_AMOUNT_MEAN_20,P_AMOUNT_MEAN_20),ADD(P_AMOUNT_MEAN_20,P_AMOUNT_MEAN_20)),SUB(MUL(P_RETURN_60,P_RETURN_60),NEG(P_AMOUNT_MEAN_20))) | P_AMOUNT_MEAN_20;P_RETURN_60          |      0.156307 |        0.211401 |                0.759259 |              54 |                      3.03884 |                          2.89143 |           0.353397 |                         -0.288071 |                  10.9074 |                        54 |                 1 |            -0.00199481  |               0.0147111 |               0.0241706 |               0.0178427 |               0.0310653 |
| random_20260721_01997 | random          | SUB(NEG(RANK(P_AMOUNT_MEAN_20)),MUL(ADD(P_VOL_20,P_RETURN_60),P_AMOUNT_MEAN_20))                                                                | P_AMOUNT_MEAN_20;P_RETURN_60;P_VOL_20 |      0.156191 |        0.185533 |                0.796296 |              54 |                      2.84303 |                          2.69851 |           0.363868 |                         -0.286816 |                  10.9074 |                        54 |                 1 |             0.00219869  |               0.010391  |               0.0258741 |               0.0180399 |               0.0298021 |
| mcts_20260724_02711   | mcts            | NEG(ADD(MUL(P_RETURN_60,P_AMOUNT_MEAN_20),P_AMOUNT_MEAN_20))                                                                                    | P_AMOUNT_MEAN_20;P_RETURN_60          |      0.15451  |        0.172283 |                0.777778 |              54 |                      3.38322 |                          3.22865 |           0.34184  |                         -0.308501 |                  10.9074 |                        54 |                 1 |             0.00159968  |               0.0124654 |               0.0217274 |               0.0179829 |               0.0326293 |
| mcts_20260725_02490   | mcts            | NEG(MUL(P_AMOUNT_MEAN_20,ADD(P_RETURN_60,P_AMOUNT_MEAN_20)))                                                                                    | P_AMOUNT_MEAN_20;P_RETURN_60          |      0.153065 |        0.173958 |                0.740741 |              54 |                      2.78332 |                          2.64822 |           0.343938 |                         -0.308501 |                  10.9074 |                        54 |                 1 |             0.00179454  |               0.0106494 |               0.0256642 |               0.0182458 |               0.0299457 |
| mcts_20260724_03114   | mcts            | NEG(MUL(P_AMOUNT_MEAN_20,ADD(P_VOL_20,P_RETURN_60)))                                                                                            | P_AMOUNT_MEAN_20;P_RETURN_60;P_VOL_20 |      0.15204  |        0.167755 |                0.796296 |              54 |                      2.10632 |                          1.96544 |           0.43731  |                         -0.325477 |                  10.9074 |                        54 |                 1 |            -0.00255759  |               0.0211641 |               0.0207456 |               0.0207133 |               0.0259731 |
| mcts_20260721_02599   | mcts            | NEG(ADD(P_AMOUNT_MEAN_20,MUL(P_VOL_20,P_RETURN_60)))                                                                                            | P_AMOUNT_MEAN_20;P_RETURN_60;P_VOL_20 |      0.149855 |        0.179569 |                0.722222 |              54 |                      1.86711 |                          1.74449 |           0.410349 |                         -0.315811 |                  10.9074 |                        54 |                 1 |            -0.00220186  |               0.0180038 |               0.0255287 |               0.0204641 |               0.0241897 |
| mcts_20260721_02811   | mcts            | NEG(ADD(P_AMOUNT_MEAN_20,ADD(P_RETURN_60,P_AMOUNT_MEAN_20)))                                                                                    | P_AMOUNT_MEAN_20;P_RETURN_60          |      0.1493   |        0.189994 |                0.740741 |              54 |                      2.42474 |                          2.29042 |           0.378981 |                         -0.314217 |                  10.9074 |                        54 |                 1 |             0.00177484  |               0.0116518 |               0.0219205 |               0.0231231 |               0.0278313 |

Diagnostics did not enter reward and did not alter the search. No prospective/final data was
accessed and no Phase B artifact was modified.
