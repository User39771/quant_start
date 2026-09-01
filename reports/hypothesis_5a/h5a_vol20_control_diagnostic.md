# H5A VOL20-Control Diagnostic v1

## Technical summary

This post-H5A historical-seen diagnostic preserves the formal RETURN_STATE, ACTIVITY_STATE, signal membership and 20D/60D/120D outcomes, then equal-weights activity contrasts across deterministic signal-time VOL20 terciles. The VOL20-controlled aggregate keeps the original sign in **9/9** comparisons, while all three VOL strata share one sign in **9/9**. Median absolute-magnitude retention is **95.0%**.

LOW_RETURN retention is **100.5% / 99.3% / 95.0%**, MID_RETURN is **95.0% / 94.2% / 95.4%**, and HIGH_RETURN is **72.4% / 77.8% / 80.7%**. These are descriptive retention ratios, not an acceptance gate.

Among the preregistered human interpretation cases, the evidence is closest to **C: the activity-related difference largely persists within VOL20 states**, with partial attenuation on the HIGH_RETURN winner side. VOL20 explains little of the LOW_RETURN and MID_RETURN aggregate magnitude and roughly one-fifth to one-quarter of HIGH_RETURN magnitude. This is a human-readable interpretation, not a mechanical classification.

## Original, size-controlled and VOL20-controlled contrasts

HIGH/LOW_RETURN values are continuation-aligned HIGH_ACTIVITY−LOW_ACTIVITY contrasts; MID_RETURN is the raw future-return contrast. Size-Control values are read from the completed formal summary and were not rerun.

| return_state   |   horizon |   original_h5a_contrast |   size_controlled_contrast |   size_retention_ratio |   vol20_controlled_contrast |   vol_retention_ratio |
|:---------------|----------:|------------------------:|---------------------------:|-----------------------:|----------------------------:|----------------------:|
| HIGH_RETURN    |        20 |                 -0.0206 |                    -0.0203 |                 0.9875 |                     -0.0149 |                0.7244 |
| HIGH_RETURN    |        60 |                 -0.056  |                    -0.0519 |                 0.9267 |                     -0.0435 |                0.7777 |
| HIGH_RETURN    |       120 |                 -0.0967 |                    -0.0795 |                 0.8219 |                     -0.078  |                0.8072 |
| LOW_RETURN     |        20 |                  0.0187 |                     0.0094 |                 0.5018 |                      0.0187 |                1.0046 |
| LOW_RETURN     |        60 |                  0.0431 |                     0.0174 |                 0.4045 |                      0.0428 |                0.9933 |
| LOW_RETURN     |       120 |                  0.0789 |                     0.0247 |                 0.3126 |                      0.075  |                0.9505 |
| MID_RETURN     |        20 |                 -0.0165 |                    -0.0078 |                 0.4745 |                     -0.0157 |                0.9502 |
| MID_RETURN     |        60 |                 -0.044  |                    -0.017  |                 0.3859 |                     -0.0414 |                0.9419 |
| MID_RETURN     |       120 |                 -0.076  |                    -0.0291 |                 0.3826 |                     -0.0725 |                0.954  |

VOL20-controlled stability evidence is:

| return_state   |   horizon |   valid_periods |   direction_consistency |   loo_sign_consistency |   bootstrap_lower_90 |   bootstrap_upper_90 |
|:---------------|----------:|----------------:|------------------------:|-----------------------:|---------------------:|---------------------:|
| HIGH_RETURN    |        20 |              56 |                  0.6607 |                      1 |              -0.0235 |              -0.006  |
| HIGH_RETURN    |        60 |              56 |                  0.75   |                      1 |              -0.0662 |              -0.0193 |
| HIGH_RETURN    |       120 |              56 |                  0.8393 |                      1 |              -0.1138 |              -0.0393 |
| LOW_RETURN     |        20 |              56 |                  0.7143 |                      1 |               0.012  |               0.0244 |
| LOW_RETURN     |        60 |              56 |                  0.8393 |                      1 |               0.0289 |               0.0553 |
| LOW_RETURN     |       120 |              56 |                  0.8214 |                      1 |               0.0445 |               0.1016 |
| MID_RETURN     |        20 |              56 |                  0.6964 |                      1 |              -0.0225 |              -0.0081 |
| MID_RETURN     |        60 |              56 |                  0.8571 |                      1 |              -0.0573 |              -0.0234 |
| MID_RETURN     |       120 |              56 |                  0.8393 |                      1 |              -0.1022 |              -0.0392 |

## VOL-stratum patterns

LOW_VOL, MID_VOL and HIGH_VOL match the original H5A sign in **9/9**, **9/9** and **9/9** comparisons. All three strata share one direction in **9/9**. No stratum result is treated as a separate hypothesis.

For HIGH_RETURN, the LOW_VOL/MID_VOL/HIGH_VOL contrasts are all negative at every horizon: 20D **−1.46% / −1.64% / −1.52%**, 60D **−4.18% / −3.90% / −6.01%**, and 120D **−4.42% / −7.75% / −10.66%**. The winner-side pattern therefore remains visible across volatility strata, although the LOW_VOL 120D magnitude is smaller and some extreme cells have fewer valid periods.

| return_state   | vol_state   |   horizon |   valid_periods |   mean_contrast |   direction_consistency |   loo_sign_consistency |   bootstrap_lower_90 |   bootstrap_upper_90 |
|:---------------|:------------|----------:|----------------:|----------------:|------------------------:|-----------------------:|---------------------:|---------------------:|
| HIGH_RETURN    | HIGH_VOL    |        20 |              53 |         -0.0152 |                  0.6981 |                      1 |              -0.0256 |              -0.0042 |
| HIGH_RETURN    | HIGH_VOL    |        60 |              53 |         -0.0601 |                  0.8113 |                      1 |              -0.0827 |              -0.0386 |
| HIGH_RETURN    | HIGH_VOL    |       120 |              53 |         -0.1066 |                  0.8679 |                      1 |              -0.1447 |              -0.0696 |
| HIGH_RETURN    | LOW_VOL     |        20 |              39 |         -0.0146 |                  0.6667 |                      1 |              -0.0281 |               0.0011 |
| HIGH_RETURN    | LOW_VOL     |        60 |              39 |         -0.0418 |                  0.8205 |                      1 |              -0.0796 |               0.0005 |
| HIGH_RETURN    | LOW_VOL     |       120 |              39 |         -0.0442 |                  0.7179 |                      1 |              -0.1002 |               0.0186 |
| HIGH_RETURN    | MID_VOL     |        20 |              56 |         -0.0164 |                  0.7143 |                      1 |              -0.0257 |              -0.006  |
| HIGH_RETURN    | MID_VOL     |        60 |              56 |         -0.039  |                  0.7143 |                      1 |              -0.0608 |              -0.015  |
| HIGH_RETURN    | MID_VOL     |       120 |              56 |         -0.0775 |                  0.8214 |                      1 |              -0.11   |              -0.0418 |
| LOW_RETURN     | HIGH_VOL    |        20 |              45 |          0.0233 |                  0.7333 |                      1 |               0.0163 |               0.0305 |
| LOW_RETURN     | HIGH_VOL    |        60 |              45 |          0.0538 |                  0.7333 |                      1 |               0.0384 |               0.0696 |
| LOW_RETURN     | HIGH_VOL    |       120 |              45 |          0.0814 |                  0.7556 |                      1 |               0.0433 |               0.1184 |
| LOW_RETURN     | LOW_VOL     |        20 |              55 |          0.0154 |                  0.7091 |                      1 |               0.0042 |               0.0239 |
| LOW_RETURN     | LOW_VOL     |        60 |              55 |          0.0391 |                  0.7818 |                      1 |               0.0164 |               0.0575 |
| LOW_RETURN     | LOW_VOL     |       120 |              55 |          0.0708 |                  0.7818 |                      1 |               0.0302 |               0.1052 |
| LOW_RETURN     | MID_VOL     |        20 |              56 |          0.0168 |                  0.7143 |                      1 |               0.0099 |               0.0231 |
| LOW_RETURN     | MID_VOL     |        60 |              56 |          0.0394 |                  0.7857 |                      1 |               0.0247 |               0.0532 |
| LOW_RETURN     | MID_VOL     |       120 |              56 |          0.0729 |                  0.7857 |                      1 |               0.0415 |               0.1024 |
| MID_RETURN     | HIGH_VOL    |        20 |              53 |         -0.0169 |                  0.7358 |                      1 |              -0.0244 |              -0.0094 |
| MID_RETURN     | HIGH_VOL    |        60 |              53 |         -0.0451 |                  0.7736 |                      1 |              -0.0613 |              -0.0284 |
| MID_RETURN     | HIGH_VOL    |       120 |              53 |         -0.0838 |                  0.8679 |                      1 |              -0.1125 |              -0.0562 |
| MID_RETURN     | LOW_VOL     |        20 |              56 |         -0.0148 |                  0.7143 |                      1 |              -0.0241 |              -0.0037 |
| MID_RETURN     | LOW_VOL     |        60 |              56 |         -0.0348 |                  0.75   |                      1 |              -0.0585 |              -0.0066 |
| MID_RETURN     | LOW_VOL     |       120 |              56 |         -0.0537 |                  0.8036 |                      1 |              -0.098  |              -0.0034 |
| MID_RETURN     | MID_VOL     |        20 |              56 |         -0.0156 |                  0.6964 |                      1 |              -0.0226 |              -0.0075 |
| MID_RETURN     | MID_VOL     |        60 |              56 |         -0.0446 |                  0.8214 |                      1 |              -0.0607 |              -0.026  |
| MID_RETURN     | MID_VOL     |       120 |              56 |         -0.078  |                  0.8393 |                      1 |              -0.1103 |              -0.0413 |

## VOL20 control remains coarse

Within return-state × VOL-state cells, the mean absolute residual standardized HIGH_ACTIVITY−LOW_ACTIVITY VOL20 difference is **0.387σ** and the maximum is **0.980σ**. `COARSE_VOL20_CONTROL_REMAINS_IMPERFECT`: terciles do not make the activity states identical in volatility.

| return_state   | vol_state   |   valid_periods |   mean_difference |   median_difference |   standardized_difference |   direction_consistency |
|:---------------|:------------|----------------:|------------------:|--------------------:|--------------------------:|------------------------:|
| HIGH_RETURN    | HIGH_VOL    |              56 |            0.1623 |              0.1446 |                    0.9798 |                  1      |
| HIGH_RETURN    | LOW_VOL     |              56 |           -0.0019 |             -0.003  |                    0.0371 |                  0.5179 |
| HIGH_RETURN    | MID_VOL     |              56 |            0.0162 |              0.0194 |                    0.4039 |                  0.9821 |
| LOW_RETURN     | HIGH_VOL    |              56 |            0.0569 |              0.0487 |                    0.5494 |                  0.9821 |
| LOW_RETURN     | LOW_VOL     |              56 |            0.0031 |              0.0081 |                    0.0974 |                  0.5714 |
| LOW_RETURN     | MID_VOL     |              56 |            0.0145 |              0.0209 |                    0.3598 |                  0.8929 |
| MID_RETURN     | HIGH_VOL    |              56 |            0.0754 |              0.0581 |                    0.6792 |                  1      |
| MID_RETURN     | LOW_VOL     |              56 |           -0.0011 |              0.004  |                   -0.0107 |                  0.4643 |
| MID_RETURN     | MID_VOL     |              56 |            0.0147 |              0.0202 |                    0.3665 |                  0.9464 |

## Size remains an accompanying confound

Without applying any double control, the same VOL strata retain a mean absolute standardized log-market-cap difference of **2.290σ**, with a maximum of **2.776σ**. Persistence after VOL stratification therefore cannot establish an activity effect independent of size.

| return_state   | vol_state   |   valid_periods |   mean_difference |   median_difference |   standardized_difference |   direction_consistency |
|:---------------|:------------|----------------:|------------------:|--------------------:|--------------------------:|------------------------:|
| HIGH_RETURN    | HIGH_VOL    |              56 |            1.1869 |              1.073  |                    1.6198 |                       1 |
| HIGH_RETURN    | LOW_VOL     |              56 |            2.5114 |              2.3676 |                    2.6663 |                       1 |
| HIGH_RETURN    | MID_VOL     |              56 |            1.8842 |              1.863  |                    2.2206 |                       1 |
| LOW_RETURN     | HIGH_VOL    |              56 |            1.4325 |              1.337  |                    1.9397 |                       1 |
| LOW_RETURN     | LOW_VOL     |              56 |            2.2891 |              2.1809 |                    2.7585 |                       1 |
| LOW_RETURN     | MID_VOL     |              56 |            1.8542 |              1.7922 |                    2.4816 |                       1 |
| MID_RETURN     | HIGH_VOL    |              56 |            1.3113 |              1.2026 |                    1.7709 |                       1 |
| MID_RETURN     | LOW_VOL     |              56 |            2.513  |              2.4023 |                    2.7762 |                       1 |
| MID_RETURN     | MID_VOL     |              56 |            1.9095 |              1.9304 |                    2.3757 |                       1 |

## Cell support and method

Across 27 return × VOL × activity cells, median membership is **148.5**, the smallest observed cell minimum is **6**, median p10 membership is **102.0**, and the smallest cell-specific p10 is **11.0**. Each usable cell requires at least 25 members and 80% outcome coverage; an aggregate period requires at least two valid VOL strata.

The analysis uses period_index 1–56, period-level equal weighting, and the formal H5A six-period circular moving-block bootstrap with 10,000 repetitions and seed 20260721. Missing outcomes are not filled and never alter signal membership.

## Interpretation boundary and next step

This is a VOL20-only diagnostic, not a size+VOL model. VOL20 alone is not a strong substitute explanation for the overall H5A pattern, although it explains part of the HIGH_RETURN magnitude. The largest remaining alternative explanation is size: within VOL strata the residual standardized size difference is much larger than the residual VOL20 difference, and the earlier standalone Size-Control diagnostic substantially reduced LOW_RETURN and MID_RETURN contrasts. Neither attenuation nor persistence identifies a causal or pure activity effect. The proxy remains an **amount-ranked multi-factor state**. A future study could preregister a genuinely turnover-like activity proxy, but no alternative proxy was tested here.

## Further questions

- Does the remaining size imbalance make a separate turnover-like proxy more informative than another layer of controls?
- Should the project stop at documenting confounding, or preregister one economically motivated activity proxy without parameter search?

## Research identity

analysis_type=post_h5a_vol20_control_diagnostic; sample_role=historical_seen; descriptive_only=true; causal_claim_allowed=false; alpha_claim_allowed=false; oos_claim_allowed=false; activity_state_redefined=false; return_state_redefined=false; future_horizons_changed=false; vol20_definition_changed=false; size_control_rerun=false; double_control_run=false; alternative_proxy_tested=false; MCTS_run=false; Phase_B_run=false
