# Hypothesis 5A — Trading-Activity State and Reversal-Timing Diagnostic

## Conclusion

**H5A_DIAGNOSTICALLY_SUPPORTED**

This is a historical-seen mechanism diagnostic, not Alpha discovery, OOS evidence, a strategy test, or a causal replication. Primary used 56 locked periods (`period_index=1–56`); period 0 remained a predeclared low-coverage diagnostic. Primary invalid period-cells after the fixed count/coverage rules: **0**. Stable LOW/HIGH_RETURN activity-horizon contrasts under the preregistered rule: **6/6**.

## 1–4. Winner/loser paths and coarse reversal horizons

`C_h` is continuation-aligned: raw future return for HIGH_RETURN and its negative for LOW_RETURN. All outcomes are nested cumulative returns from rebalance close. A first observed negative cumulative C identifies only a coarse horizon, not an exact reversal date.

| return_state   | activity_state   |   horizon |   across_period_mean_aligned |   across_period_median_aligned | path_category         |
|:---------------|:-----------------|----------:|-----------------------------:|-------------------------------:|:----------------------|
| HIGH_RETURN    | HIGH_ACTIVITY    |        20 |                    -0.001673 |                      -0.005511 | NO_CLEAR_PATH         |
| HIGH_RETURN    | HIGH_ACTIVITY    |        60 |                     0.00178  |                      -0.017721 | NO_CLEAR_PATH         |
| HIGH_RETURN    | HIGH_ACTIVITY    |       120 |                     0.007923 |                      -0.011728 | NO_CLEAR_PATH         |
| HIGH_RETURN    | LOW_ACTIVITY     |        20 |                     0.018893 |                       0.020226 | CONTINUATION_PERSISTS |
| HIGH_RETURN    | LOW_ACTIVITY     |        60 |                     0.057744 |                       0.058006 | CONTINUATION_PERSISTS |
| HIGH_RETURN    | LOW_ACTIVITY     |       120 |                     0.104595 |                       0.100772 | CONTINUATION_PERSISTS |
| HIGH_RETURN    | MID_ACTIVITY     |        20 |                     0.010055 |                       0.010217 | CONTINUATION_PERSISTS |
| HIGH_RETURN    | MID_ACTIVITY     |        60 |                     0.033699 |                       0.031631 | CONTINUATION_PERSISTS |
| HIGH_RETURN    | MID_ACTIVITY     |       120 |                     0.059888 |                       0.051506 | CONTINUATION_PERSISTS |
| LOW_RETURN     | HIGH_ACTIVITY    |        20 |                    -0.006826 |                       0.004737 | REVERSAL_OBSERVED     |
| LOW_RETURN     | HIGH_ACTIVITY    |        60 |                    -0.01825  |                      -0.0001   | REVERSAL_OBSERVED     |
| LOW_RETURN     | HIGH_ACTIVITY    |       120 |                    -0.030723 |                       0.012044 | REVERSAL_OBSERVED     |
| LOW_RETURN     | LOW_ACTIVITY     |        20 |                    -0.02549  |                      -0.025579 | REVERSAL_OBSERVED     |
| LOW_RETURN     | LOW_ACTIVITY     |        60 |                    -0.061345 |                      -0.065061 | REVERSAL_OBSERVED     |
| LOW_RETURN     | LOW_ACTIVITY     |       120 |                    -0.109584 |                      -0.095264 | REVERSAL_OBSERVED     |
| LOW_RETURN     | MID_ACTIVITY     |        20 |                    -0.016194 |                      -0.00318  | REVERSAL_OBSERVED     |
| LOW_RETURN     | MID_ACTIVITY     |        60 |                    -0.04042  |                      -0.029113 | REVERSAL_OBSERVED     |
| LOW_RETURN     | MID_ACTIVITY     |       120 |                    -0.067772 |                      -0.048615 | REVERSAL_OBSERVED     |

## 5. Activity interaction within return states

`G` is HIGH_ACTIVITY minus LOW_ACTIVITY continuation-aligned return within the same past-return state. MID_ACTIVITY is used to test ordering.

| return_state   |   horizon |   valid_periods |   mean_contrast |   direction_consistency |   bootstrap_lower_90 |   bootstrap_upper_90 |   loo_sign_consistency | activity_ordered   | stability_flag   |
|:---------------|----------:|----------------:|----------------:|------------------------:|---------------------:|---------------------:|-----------------------:|:-------------------|:-----------------|
| LOW_RETURN     |        20 |              56 |        0.018664 |                0.696429 |             0.012584 |             0.024306 |                      1 | True               | True             |
| LOW_RETURN     |        60 |              56 |        0.043096 |                0.785714 |             0.028826 |             0.056771 |                      1 | True               | True             |
| LOW_RETURN     |       120 |              56 |        0.07886  |                0.803571 |             0.049318 |             0.106248 |                      1 | True               | True             |
| HIGH_RETURN    |        20 |              56 |       -0.020565 |                0.75     |            -0.029923 |            -0.011153 |                      1 | True               | True             |
| HIGH_RETURN    |        60 |              56 |       -0.055964 |                0.821429 |            -0.078839 |            -0.033253 |                      1 | True               | True             |
| HIGH_RETURN    |       120 |              56 |       -0.096672 |                0.839286 |            -0.12964  |            -0.063225 |                      1 | True               | True             |

MID_RETURN is a raw-return activity main-effect diagnostic and cannot independently support H5A:

|   horizon |   valid_periods |   mean_contrast |   direction_consistency |   bootstrap_lower_90 |   bootstrap_upper_90 | stability_flag   |
|----------:|----------------:|----------------:|------------------------:|---------------------:|---------------------:|:-----------------|
|        20 |              56 |       -0.016536 |                0.714286 |            -0.023522 |            -0.009514 | False            |
|        60 |              56 |       -0.043959 |                0.785714 |            -0.06133  |            -0.025876 | False            |
|       120 |              56 |       -0.076021 |                0.839286 |            -0.106589 |            -0.043915 | False            |

The non-acceptance interaction contrast `I_h = G_HIGH_RETURN,h - G_LOW_RETURN,h` is:

|   horizon |   valid_periods |   mean_contrast |   median_contrast |   direction_consistency |
|----------:|----------------:|----------------:|------------------:|------------------------:|
|        20 |              56 |       -0.039229 |         -0.046009 |                0.75     |
|        60 |              56 |       -0.099059 |         -0.105472 |                0.839286 |
|       120 |              56 |       -0.175532 |         -0.188294 |                0.839286 |

## 6–7. Concentration and stability

Every period receives equal cross-period weight. Stability uses a calendar-derived six-period circular moving-block bootstrap (10,000 repetitions, seed 20260721), at least 45/56 valid contrasts, direction consistency at least 60%, and leave-one-period-out sign consistency at least 80%. The 90% interval is descriptive uncertainty evidence only; it is not family-wise-error-controlled, Alpha, or OOS significance. Fixed early/late samples are periods 1–28 and 29–56.

## 8. Literature relationship

The design is literature-inspired: it asks whether trading-activity states distinguish continuation and reversal paths within past winner and loser states. It is not a replication because AMOUNT_MEAN20 percentile is not true turnover, the universe is a current-universe historical backfill, and the analysis is descriptive rather than causal. Similar path shapes would therefore be conceptual consistency only; different shapes would not falsify the original literature.

## 9. AI descriptive transfer

AI stocks inherit their broader-A RETURN_STATE and ACTIVITY_STATE; no theme-local quantiles or independent classification are used.

Direction visibility is descriptive and requires both inherited LOW_ACTIVITY and HIGH_ACTIVITY cells in the same AI period:

| return_state   |   horizon |   paired_ai_periods |   ai_mean_G |   broader_a_mean_G | same_direction   |
|:---------------|----------:|--------------------:|------------:|-------------------:|:-----------------|
| LOW_RETURN     |        20 |                  19 |    0.021744 |           0.018664 | True             |
| LOW_RETURN     |        60 |                  19 |    0.054583 |           0.043096 | True             |
| LOW_RETURN     |       120 |                  19 |    0.115353 |           0.07886  | True             |
| HIGH_RETURN    |        20 |                   9 |   -0.032919 |          -0.020565 | True             |
| HIGH_RETURN    |        60 |                   9 |   -0.244822 |          -0.055964 | True             |
| HIGH_RETURN    |       120 |                   9 |   -0.526508 |          -0.096672 | True             |

| return_state   | activity_state   |   horizon |   periods |   mean_future_return |   mean_occupancy |
|:---------------|:-----------------|----------:|----------:|---------------------:|-----------------:|
| HIGH_RETURN    | HIGH_ACTIVITY    |        20 |        54 |             0.010635 |         0.326916 |
| HIGH_RETURN    | HIGH_ACTIVITY    |        60 |        54 |             0.02694  |         0.326916 |
| HIGH_RETURN    | HIGH_ACTIVITY    |       120 |        54 |             0.051122 |         0.326916 |
| HIGH_RETURN    | LOW_ACTIVITY     |        20 |         9 |             0.121616 |         0.025815 |
| HIGH_RETURN    | LOW_ACTIVITY     |        60 |         9 |             0.289491 |         0.025815 |
| HIGH_RETURN    | LOW_ACTIVITY     |       120 |         9 |             0.755843 |         0.025815 |
| HIGH_RETURN    | MID_ACTIVITY     |        20 |        38 |             0.031261 |         0.050164 |
| HIGH_RETURN    | MID_ACTIVITY     |        60 |        38 |             0.127995 |         0.050164 |
| HIGH_RETURN    | MID_ACTIVITY     |       120 |        38 |             0.195259 |         0.050164 |
| LOW_RETURN     | HIGH_ACTIVITY    |        20 |        55 |             0.016166 |         0.26565  |
| LOW_RETURN     | HIGH_ACTIVITY    |        60 |        55 |             0.036223 |         0.26565  |
| LOW_RETURN     | HIGH_ACTIVITY    |       120 |        55 |             0.08755  |         0.26565  |
| LOW_RETURN     | LOW_ACTIVITY     |        20 |        19 |             0.052523 |         0.039635 |
| LOW_RETURN     | LOW_ACTIVITY     |        60 |        19 |             0.10386  |         0.039635 |
| LOW_RETURN     | LOW_ACTIVITY     |       120 |        19 |             0.174914 |         0.039635 |
| LOW_RETURN     | MID_ACTIVITY     |        20 |        48 |             0.03027  |         0.095079 |
| LOW_RETURN     | MID_ACTIVITY     |        60 |        48 |             0.085838 |         0.095079 |
| LOW_RETURN     | MID_ACTIVITY     |       120 |        48 |             0.188378 |         0.095079 |
| MID_RETURN     | HIGH_ACTIVITY    |        20 |        56 |             0.028896 |         0.214768 |
| MID_RETURN     | HIGH_ACTIVITY    |        60 |        56 |             0.06673  |         0.214768 |
| MID_RETURN     | HIGH_ACTIVITY    |       120 |        56 |             0.112591 |         0.214768 |
| MID_RETURN     | LOW_ACTIVITY     |        20 |        19 |             0.02381  |         0.034578 |
| MID_RETURN     | LOW_ACTIVITY     |        60 |        19 |             0.132832 |         0.034578 |
| MID_RETURN     | LOW_ACTIVITY     |       120 |        19 |             0.232061 |         0.034578 |
| MID_RETURN     | MID_ACTIVITY     |        20 |        48 |             0.037368 |         0.074925 |
| MID_RETURN     | MID_ACTIVITY     |        60 |        48 |             0.14939  |         0.074925 |
| MID_RETURN     | MID_ACTIVITY     |       120 |        48 |             0.191181 |         0.074925 |

## 10. Commercial-space case study

Commercial-space stocks also inherit broader-A states. The following occupancy/path aggregates are low-power descriptions; stock-level rows are retained in `h5a_theme_transfer.csv`.

| return_state   | activity_state   |   horizon |   periods |   mean_future_return |   mean_occupancy |
|:---------------|:-----------------|----------:|----------:|---------------------:|-----------------:|
| HIGH_RETURN    | HIGH_ACTIVITY    |        20 |        51 |             0.010567 |         0.281402 |
| HIGH_RETURN    | HIGH_ACTIVITY    |        60 |        51 |             0.054525 |         0.281402 |
| HIGH_RETURN    | HIGH_ACTIVITY    |       120 |        51 |             0.078665 |         0.281402 |
| HIGH_RETURN    | LOW_ACTIVITY     |        20 |         3 |            -0.038076 |         0.083333 |
| HIGH_RETURN    | LOW_ACTIVITY     |        60 |         3 |             0.106072 |         0.083333 |
| HIGH_RETURN    | LOW_ACTIVITY     |       120 |         3 |             0.106613 |         0.083333 |
| HIGH_RETURN    | MID_ACTIVITY     |        20 |        25 |             0.003914 |         0.127212 |
| HIGH_RETURN    | MID_ACTIVITY     |        60 |        25 |             0.029146 |         0.127212 |
| HIGH_RETURN    | MID_ACTIVITY     |       120 |        25 |             0.057817 |         0.127212 |
| LOW_RETURN     | HIGH_ACTIVITY    |        20 |        39 |             0.009324 |         0.184615 |
| LOW_RETURN     | HIGH_ACTIVITY    |        60 |        39 |             0.026461 |         0.184615 |
| LOW_RETURN     | HIGH_ACTIVITY    |       120 |        39 |             0.03876  |         0.184615 |
| LOW_RETURN     | LOW_ACTIVITY     |        20 |        16 |             0.08803  |         0.125947 |
| LOW_RETURN     | LOW_ACTIVITY     |        60 |        16 |             0.171257 |         0.125947 |
| LOW_RETURN     | LOW_ACTIVITY     |       120 |        16 |             0.244654 |         0.125947 |
| LOW_RETURN     | MID_ACTIVITY     |        20 |        35 |             0.051287 |         0.158788 |
| LOW_RETURN     | MID_ACTIVITY     |        60 |        35 |             0.128225 |         0.158788 |
| LOW_RETURN     | MID_ACTIVITY     |       120 |        35 |             0.126135 |         0.158788 |
| MID_RETURN     | HIGH_ACTIVITY    |        20 |        47 |             0.013647 |         0.202128 |
| MID_RETURN     | HIGH_ACTIVITY    |        60 |        47 |             0.058776 |         0.202128 |
| MID_RETURN     | HIGH_ACTIVITY    |       120 |        47 |             0.127878 |         0.202128 |
| MID_RETURN     | LOW_ACTIVITY     |        20 |        27 |             0.011413 |         0.110157 |
| MID_RETURN     | LOW_ACTIVITY     |        60 |        27 |             0.036959 |         0.110157 |
| MID_RETURN     | LOW_ACTIVITY     |       120 |        27 |             0.000401 |         0.110157 |
| MID_RETURN     | MID_ACTIVITY     |        20 |        53 |             0.019478 |         0.207004 |
| MID_RETURN     | MID_ACTIVITY     |        60 |        53 |             0.084271 |         0.207004 |
| MID_RETURN     | MID_ACTIVITY     |       120 |        53 |             0.191788 |         0.207004 |

## 11–12. Classification and H5B gate

Final classification: **H5A_DIAGNOSTICALLY_SUPPORTED**. Theme evidence cannot change it. H5A does not automatically open H5B. Any H5B work requires a separate human review and preregistration; no strategy, MCTS, Phase B, prospective, or final-test process was run.

## Limitations

- `universe_point_in_time=false`; survivorship bias is possible.
- AMOUNT_MEAN20 mixes trading activity, company scale, and price-level exposure.
- The sample is historical_seen and has been viewed by earlier project research.
- Missing or suspended endpoint prices are not filled; outcome missingness never changes signal-time state membership.
- Nested 20D/60D/120D returns identify only coarse first-observed reversal horizons.

## Research identity

sample_role=historical_seen; research_type=mechanism_diagnostic; descriptive_only=true; alpha_claim_allowed=false; oos_claim_allowed=false; strategy_claim_allowed=false; universe_point_in_time=false; survivorship_bias_possible=true; prospective_data_accessed=false; final_test_accessed=false; MCTS_run=false; Phase_B_run=false
