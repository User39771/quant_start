# H5B VT20_DAILY Historical-Seen Descriptive Diagnostic

## Technical summary

H5B completed all 56 locked historical-seen periods under the preregistered VT20 contract. All nine Primary contrasts have 56 valid period observations; invalid period-state-horizon cells: **0**. H5B has the same direction as the directly read formal H5A contrast in **7/9** comparisons. The runner does not assign a preservation category; that interpretation remains a human decision.

This is a derived historical-seen mechanism diagnostic, not Alpha discovery, independent validation, OOS evidence, a strategy result or a causal test.

## LOW/HIGH_RETURN contrasts provide the six Primary comparisons

`G_h` is HIGH_VT minus LOW_VT continuation-aligned arithmetic-mean return within the same RETURN_STATE. Medians are descriptive only.

| return_state   |   horizon |   valid_periods |   mean_contrast |   median_contrast_descriptive |   direction_consistency |   bootstrap_lower_90 |   bootstrap_upper_90 |   loo_sign_consistency |
|:---------------|----------:|----------------:|----------------:|------------------------------:|------------------------:|---------------------:|---------------------:|-----------------------:|
| LOW_RETURN     |        20 |              56 |        0.001521 |                      0.004262 |                0.607143 |            -0.007445 |             0.00961  |               0.964286 |
| LOW_RETURN     |        60 |              56 |       -0.002585 |                      0.009119 |                0.357143 |            -0.025947 |             0.017814 |               0.964286 |
| LOW_RETURN     |       120 |              56 |       -0.008304 |                      0.013309 |                0.446429 |            -0.043856 |             0.023445 |               1        |
| HIGH_RETURN    |        20 |              56 |       -0.002854 |                     -0.007399 |                0.571429 |            -0.01376  |             0.008533 |               0.982143 |
| HIGH_RETURN    |        60 |              56 |       -0.009781 |                     -0.017347 |                0.660714 |            -0.031967 |             0.014775 |               1        |
| HIGH_RETURN    |       120 |              56 |       -0.017912 |                     -0.028731 |                0.660714 |            -0.05106  |             0.018503 |               1        |

## MID_RETURN provides the three preregistered raw-return contrasts

`D_h` is HIGH_VT minus LOW_VT arithmetic-mean raw return. It is reported completely and does not independently establish a turnover mechanism.

| return_state   |   horizon |   valid_periods |   mean_contrast |   median_contrast_descriptive |   direction_consistency |   bootstrap_lower_90 |   bootstrap_upper_90 |   loo_sign_consistency |
|:---------------|----------:|----------------:|----------------:|------------------------------:|------------------------:|---------------------:|---------------------:|-----------------------:|
| MID_RETURN     |        20 |              56 |       -0.00209  |                     -0.001822 |                0.535714 |            -0.009369 |             0.005963 |               1        |
| MID_RETURN     |        60 |              56 |       -0.001692 |                     -0.007183 |                0.607143 |            -0.019929 |             0.01872  |               0.946429 |
| MID_RETURN     |       120 |              56 |       -0.005678 |                     -0.018927 |                0.607143 |            -0.036674 |             0.02693  |               1        |

## The formal H5A comparison is read directly, not recomputed

Magnitude ratio is `abs(H5B contrast) / abs(formal H5A contrast)`; it has no success threshold.

| return_state   |   horizon |   h5a_amount_contrast |   h5b_vt20_contrast | direction_same   |   magnitude_ratio |
|:---------------|----------:|----------------------:|--------------------:|:-----------------|------------------:|
| LOW_RETURN     |        20 |              0.018664 |            0.001521 | True             |          0.081514 |
| LOW_RETURN     |        60 |              0.043096 |           -0.002585 | False            |          0.059992 |
| LOW_RETURN     |       120 |              0.07886  |           -0.008304 | False            |          0.105299 |
| MID_RETURN     |        20 |             -0.016536 |           -0.00209  | True             |          0.12641  |
| MID_RETURN     |        60 |             -0.043959 |           -0.001692 | True             |          0.038489 |
| MID_RETURN     |       120 |             -0.076021 |           -0.005678 | True             |          0.074688 |
| HIGH_RETURN    |        20 |             -0.020565 |           -0.002854 | True             |          0.138786 |
| HIGH_RETURN    |        60 |             -0.055964 |           -0.009781 | True             |          0.174766 |
| HIGH_RETURN    |       120 |             -0.096672 |           -0.017912 | True             |          0.185283 |

H5A used 262,636 signal-ready stock-periods; H5B fixes state membership to the 262,589 VT20-valid observations, a difference of **47** observations. The formal H5A column above was not restricted to this H5B-valid subset, so the small coverage difference remains a comparison limitation.

## Coarse paths use arithmetic-mean cell returns

| return_state   | vt20_state   |   horizon |   valid_periods |   across_period_mean |   across_period_mean_aligned | path_category         |   median_signal_members |   minimum_outcome_coverage |
|:---------------|:-------------|----------:|----------------:|---------------------:|-----------------------------:|:----------------------|------------------------:|---------------------------:|
| HIGH_RETURN    | HIGH_VT      |        20 |              56 |             0.003252 |                     0.003252 | CONTINUATION_PERSISTS |                   825.5 |                   0.993763 |
| HIGH_RETURN    | HIGH_VT      |        60 |              56 |             0.016225 |                     0.016225 | CONTINUATION_PERSISTS |                   825.5 |                   0.992218 |
| HIGH_RETURN    | HIGH_VT      |       120 |              56 |             0.032324 |                     0.032324 | CONTINUATION_PERSISTS |                   825.5 |                   0.990885 |
| HIGH_RETURN    | LOW_VT       |        20 |              56 |             0.006106 |                     0.006106 | CONTINUATION_PERSISTS |                   287   |                   0.988764 |
| HIGH_RETURN    | LOW_VT       |        60 |              56 |             0.026006 |                     0.026006 | CONTINUATION_PERSISTS |                   287   |                   0.991228 |
| HIGH_RETURN    | LOW_VT       |       120 |              56 |             0.050236 |                     0.050236 | CONTINUATION_PERSISTS |                   287   |                   0.994709 |
| HIGH_RETURN    | MID_VT       |        20 |              56 |             0.01064  |                     0.01064  | CONTINUATION_PERSISTS |                   433   |                   0.988484 |
| HIGH_RETURN    | MID_VT       |        60 |              56 |             0.032646 |                     0.032646 | CONTINUATION_PERSISTS |                   433   |                   0.990403 |
| HIGH_RETURN    | MID_VT       |       120 |              56 |             0.058255 |                     0.058255 | CONTINUATION_PERSISTS |                   433   |                   0.991886 |
| LOW_RETURN     | HIGH_VT      |        20 |              56 |             0.015085 |                    -0.015085 | REVERSAL_OBSERVED     |                   349   |                   0.986667 |
| LOW_RETURN     | HIGH_VT      |        60 |              56 |             0.041522 |                    -0.041522 | REVERSAL_OBSERVED     |                   349   |                   0.986667 |
| LOW_RETURN     | HIGH_VT      |       120 |              56 |             0.074255 |                    -0.074255 | REVERSAL_OBSERVED     |                   349   |                   0.986667 |
| LOW_RETURN     | LOW_VT       |        20 |              56 |             0.016606 |                    -0.016606 | REVERSAL_OBSERVED     |                   601.5 |                   0.995526 |
| LOW_RETURN     | LOW_VT       |        60 |              56 |             0.038937 |                    -0.038937 | REVERSAL_OBSERVED     |                   601.5 |                   0.993289 |
| LOW_RETURN     | LOW_VT       |       120 |              56 |             0.065951 |                    -0.065951 | REVERSAL_OBSERVED     |                   601.5 |                   0.991649 |
| LOW_RETURN     | MID_VT       |        20 |              56 |             0.020184 |                    -0.020184 | REVERSAL_OBSERVED     |                   585   |                   0.991507 |
| LOW_RETURN     | MID_VT       |        60 |              56 |             0.049039 |                    -0.049039 | REVERSAL_OBSERVED     |                   585   |                   0.993631 |
| LOW_RETURN     | MID_VT       |       120 |              56 |             0.084449 |                    -0.084449 | REVERSAL_OBSERVED     |                   585   |                   0.993548 |
| MID_RETURN     | HIGH_VT      |        20 |              56 |             0.013393 |                              | NOT_APPLICABLE        |                   382.5 |                   0.993266 |
| MID_RETURN     | HIGH_VT      |        60 |              56 |             0.038216 |                              | NOT_APPLICABLE        |                   382.5 |                   0.991477 |
| MID_RETURN     | HIGH_VT      |       120 |              56 |             0.070057 |                              | NOT_APPLICABLE        |                   382.5 |                   0.991477 |
| MID_RETURN     | LOW_VT       |        20 |              56 |             0.015483 |                              | NOT_APPLICABLE        |                   625.5 |                   0.99562  |
| MID_RETURN     | LOW_VT       |        60 |              56 |             0.039908 |                              | NOT_APPLICABLE        |                   625.5 |                   0.995935 |
| MID_RETURN     | LOW_VT       |       120 |              56 |             0.075735 |                              | NOT_APPLICABLE        |                   625.5 |                   0.9952   |
| MID_RETURN     | MID_VT       |        20 |              56 |             0.017239 |                              | NOT_APPLICABLE        |                   559.5 |                   0.993827 |
| MID_RETURN     | MID_VT       |        60 |              56 |             0.050986 |                              | NOT_APPLICABLE        |                   559.5 |                   0.993927 |
| MID_RETURN     | MID_VT       |       120 |              56 |             0.090574 |                              | NOT_APPLICABLE        |                   559.5 |                   0.99505  |

Path categories use the three horizon-level across-period means, not cell medians. They identify only coarse cumulative paths and cannot locate an exact reversal date.

## Membership and outcome coverage passed the frozen rules

Signal membership was frozen before outcomes. Every cell required at least 25 signal members and at least 80% future-outcome coverage; future missingness did not alter state assignment or membership. A period contrast was formed only where both LOW_VT and HIGH_VT cells were valid. Minimum signal membership was **89** and minimum outcome coverage was **98.67%**.

## Uncertainty is descriptive

All periods receive equal cross-period weight. The 90% circular moving-block interval uses block length 6, 10,000 repetitions and seed 20260721. Direction consistency and leave-one-period-out sign consistency are reported without creating an automatic H5B category. These statistics do not provide family-wise-error-controlled, Alpha or OOS significance.

## Human interpretation and limitations

The human reviewer should compare the nine fixed contrasts, their 7/9 direction agreement, magnitude ratios, coarse paths and stability descriptions against the preregistered interpretation framework. The runner intentionally does not label the result `PATTERN_LARGELY_PRESERVED`, `PATTERN_PARTIALLY_PRESERVED`, `PATTERN_NOT_PRESERVED` or `INCONCLUSIVE`.

VT20 remains materially related to VOL20 and negatively related to size. Historical market-cap vintage lineage is not audited, and the universe is current rather than point-in-time. Consequently, any visible path remains a turnover-like multi-exposure historical association, not a pure turnover effect.

## Stop boundary

No alternative proxy, lookback, neutralization, MCTS, Phase B, prospective data or final-test data was run. Further work requires a separate human decision.

## Research identity

analysis_stage=H5B_historical_seen_descriptive_diagnostic; sample_role=historical_seen; derived_hypothesis=true; future_return_accessed=true; H5B_performance_run=true; alpha_claim_allowed=false; oos_claim_allowed=false; causal_claim_allowed=false; alternative_proxy_tested=false; network_download_performed=false; MCTS_run=false; Phase_B_run=false; prospective_data_accessed=false; final_test_accessed=false
