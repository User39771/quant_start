# H5A Size-Control Diagnostic v1

## Technical summary

This post-H5A historical-seen diagnostic preserves all formal RETURN_STATE, ACTIVITY_STATE, signal memberships and 20D/60D/120D outcomes, then compares the original activity contrast with an equal-weight average across deterministic signal-date size terciles. The size-controlled contrast keeps the original sign in **9/9** return-state/horizon comparisons; all three size strata share one sign in **3/9** comparisons. Median absolute-magnitude retention is **47.4%**.

This is a size-stratified diagnostic, not proof that size has been eliminated or that a pure activity effect has been identified. The proxy remains an **amount-ranked multi-factor state**.

The evidence is heterogeneous and is most naturally read as **size explaining part of the original difference** rather than one uniform A/B/C case. LOW_RETURN retention is **50.2% / 40.5% / 31.3%** at 20D/60D/120D, while HIGH_RETURN retains **98.7% / 92.7% / 82.2%**. MID_RETURN retains **47.4% / 38.6% / 38.3%**. This is a human-readable description, not a mechanical classification gate.

## Original and size-controlled contrasts

For HIGH/LOW_RETURN, values are continuation-aligned HIGH_ACTIVITY minus LOW_ACTIVITY contrasts. MID_RETURN uses the raw future-return difference. Returns are nested cumulative outcomes from rebalance close.

| Return state   |   Horizon |   Original H5A |   Size-controlled |   Retention |   Small |   Mid-size |   Large |
|:---------------|----------:|---------------:|------------------:|------------:|--------:|-----------:|--------:|
| HIGH_RETURN    |        20 |        -0.0206 |           -0.0203 |      0.9875 | -0.026  |    -0.0127 | -0.0034 |
| HIGH_RETURN    |        60 |        -0.056  |           -0.0519 |      0.9267 | -0.0668 |    -0.0376 |  0.0016 |
| HIGH_RETURN    |       120 |        -0.0967 |           -0.0795 |      0.8219 | -0.1091 |    -0.0583 |  0.0315 |
| LOW_RETURN     |        20 |         0.0187 |            0.0094 |      0.5018 | -0.0112 |     0.0108 |  0.0034 |
| LOW_RETURN     |        60 |         0.0431 |            0.0174 |      0.4045 | -0.009  |     0.0228 |  0.0069 |
| LOW_RETURN     |       120 |         0.0789 |            0.0247 |      0.3126 | -0.0001 |     0.0361 |  0.0094 |
| MID_RETURN     |        20 |        -0.0165 |           -0.0078 |      0.4745 |  0.0037 |    -0.0094 | -0.0069 |
| MID_RETURN     |        60 |        -0.044  |           -0.017  |      0.3859 | -0.0161 |    -0.0256 | -0.0049 |
| MID_RETURN     |       120 |        -0.076  |           -0.0291 |      0.3826 | -0.046  |    -0.036  | -0.0148 |

The comparison is descriptive: no retention threshold or new supported/not-supported gate was defined. A retention above 100% means the equal-weight size-stratum contrast is larger in absolute magnitude than the original aggregate, not stronger causal evidence.

Size-controlled stability statistics are:

| Return state   |   Horizon |   valid_periods |   direction_consistency |   loo_sign_consistency |   bootstrap_lower_90 |   bootstrap_upper_90 |
|:---------------|----------:|----------------:|------------------------:|-----------------------:|---------------------:|---------------------:|
| HIGH_RETURN    |        20 |              54 |                  0.7593 |                      1 |              -0.0295 |              -0.0101 |
| HIGH_RETURN    |        60 |              54 |                  0.8333 |                      1 |              -0.0722 |              -0.0312 |
| HIGH_RETURN    |       120 |              54 |                  0.8889 |                      1 |              -0.1083 |              -0.0498 |
| LOW_RETURN     |        20 |              48 |                  0.6667 |                      1 |               0.002  |               0.0165 |
| LOW_RETURN     |        60 |              48 |                  0.6458 |                      1 |               0.0006 |               0.0332 |
| LOW_RETURN     |       120 |              48 |                  0.6667 |                      1 |               0.0023 |               0.0471 |
| MID_RETURN     |        20 |              52 |                  0.6154 |                      1 |              -0.0146 |              -0.001  |
| MID_RETURN     |        60 |              52 |                  0.6731 |                      1 |              -0.0339 |               0.0009 |
| MID_RETURN     |       120 |              52 |                  0.75   |                      1 |              -0.056  |              -0.001  |

## Stratum patterns are not uniform

Across the nine return-state/horizon comparisons, SMALL, MID_SIZE and LARGE match the original H5A contrast sign in **5/9**, **9/9** and **7/9** cases, respectively. All three size strata share one direction in only **3/9** comparisons. LOW_RETURN is especially heterogeneous: at 20D/60D/120D the SMALL contrasts are negative, while MID_SIZE and LARGE are positive. HIGH_RETURN remains negative in SMALL and MID_SIZE, but LARGE turns slightly positive at 60D and 120D.

| return_state   | size_state   |   horizon |   valid_periods |   mean_contrast |   direction_consistency |   loo_sign_consistency |   bootstrap_lower_90 |   bootstrap_upper_90 |
|:---------------|:-------------|----------:|----------------:|----------------:|------------------------:|-----------------------:|---------------------:|---------------------:|
| HIGH_RETURN    | LARGE        |        20 |              11 |         -0.0034 |                  0.5455 |                 0.8182 |              -0.0153 |               0.009  |
| HIGH_RETURN    | LARGE        |        60 |              11 |          0.0016 |                  0.5455 |                 0.5455 |              -0.0194 |               0.0234 |
| HIGH_RETURN    | LARGE        |       120 |              11 |          0.0315 |                  0.6364 |                 1      |              -0.0078 |               0.0709 |
| HIGH_RETURN    | MID_SIZE     |        20 |              54 |         -0.0127 |                  0.7037 |                 1      |              -0.0236 |              -0.0002 |
| HIGH_RETURN    | MID_SIZE     |        60 |              54 |         -0.0376 |                  0.7593 |                 1      |              -0.0598 |              -0.014  |
| HIGH_RETURN    | MID_SIZE     |       120 |              54 |         -0.0583 |                  0.7778 |                 1      |              -0.0906 |              -0.0244 |
| HIGH_RETURN    | SMALL        |        20 |              55 |         -0.026  |                  0.7818 |                 1      |              -0.0363 |              -0.0145 |
| HIGH_RETURN    | SMALL        |        60 |              55 |         -0.0668 |                  0.8545 |                 1      |              -0.0883 |              -0.0452 |
| HIGH_RETURN    | SMALL        |       120 |              55 |         -0.1091 |                  0.9091 |                 1      |              -0.1462 |              -0.0744 |
| LOW_RETURN     | LARGE        |        20 |              45 |          0.0034 |                  0.5111 |                 1      |              -0.003  |               0.0102 |
| LOW_RETURN     | LARGE        |        60 |              45 |          0.0069 |                  0.5333 |                 1      |              -0.0118 |               0.0267 |
| LOW_RETURN     | LARGE        |       120 |              45 |          0.0094 |                  0.6222 |                 1      |              -0.0215 |               0.0397 |
| LOW_RETURN     | MID_SIZE     |        20 |              55 |          0.0108 |                  0.6545 |                 1      |               0.0019 |               0.0193 |
| LOW_RETURN     | MID_SIZE     |        60 |              55 |          0.0228 |                  0.7636 |                 1      |               0.0048 |               0.0389 |
| LOW_RETURN     | MID_SIZE     |       120 |              55 |          0.0361 |                  0.7273 |                 1      |               0.016  |               0.055  |
| LOW_RETURN     | SMALL        |        20 |              11 |         -0.0112 |                  0.6364 |                 0.9091 |              -0.0395 |               0.019  |
| LOW_RETURN     | SMALL        |        60 |              11 |         -0.009  |                  0.4545 |                 0.8182 |              -0.0691 |               0.0501 |
| LOW_RETURN     | SMALL        |       120 |              11 |         -0.0001 |                  0.4545 |                 0.5455 |              -0.0485 |               0.0483 |
| MID_RETURN     | LARGE        |        20 |              52 |         -0.0069 |                  0.5769 |                 1      |              -0.0154 |               0.0016 |
| MID_RETURN     | LARGE        |        60 |              52 |         -0.0049 |                  0.5962 |                 1      |              -0.0238 |               0.0147 |
| MID_RETURN     | LARGE        |       120 |              52 |         -0.0148 |                  0.5577 |                 1      |              -0.043  |               0.0145 |
| MID_RETURN     | MID_SIZE     |        20 |              56 |         -0.0094 |                  0.6429 |                 1      |              -0.0172 |              -0.0012 |
| MID_RETURN     | MID_SIZE     |        60 |              56 |         -0.0256 |                  0.7143 |                 1      |              -0.0446 |              -0.0047 |
| MID_RETURN     | MID_SIZE     |       120 |              56 |         -0.036  |                  0.75   |                 1      |              -0.0712 |               0.0011 |
| MID_RETURN     | SMALL        |        20 |              24 |          0.0037 |                  0.5417 |                 0.9167 |              -0.0086 |               0.0172 |
| MID_RETURN     | SMALL        |        60 |              24 |         -0.0161 |                  0.6667 |                 1      |              -0.0311 |               0.0016 |
| MID_RETURN     | SMALL        |       120 |              24 |         -0.046  |                  0.7917 |                 1      |              -0.0753 |              -0.0166 |

## Size control remains coarse

Within return-state × size-state cells, the mean absolute residual standardized HIGH_ACTIVITY−LOW_ACTIVITY log-market-cap difference is **0.890σ** and the maximum is **1.234σ**. Therefore `COARSE_SIZE_CONTROL_REMAINS_IMPERFECT`: terciles reduce broad composition differences but do not make HIGH_ACTIVITY and LOW_ACTIVITY identical in size.

| return_state   | size_state   |   valid_periods |   mean_size_difference |   median_size_difference |   standardized_size_difference |   direction_consistency |
|:---------------|:-------------|----------------:|-----------------------:|-------------------------:|-------------------------------:|------------------------:|
| HIGH_RETURN    | LARGE        |              56 |                 0.7352 |                   0.584  |                         1.0412 |                  1      |
| HIGH_RETURN    | MID_SIZE     |              56 |                 0.1072 |                   0.1568 |                         0.4623 |                  0.9821 |
| HIGH_RETURN    | SMALL        |              56 |                 0.2438 |                   0.2543 |                         0.9989 |                  1      |
| LOW_RETURN     | LARGE        |              56 |                 0.8415 |                   0.7328 |                         1.2341 |                  1      |
| LOW_RETURN     | MID_SIZE     |              56 |                 0.1598 |                   0.2118 |                         0.6801 |                  1      |
| LOW_RETURN     | SMALL        |              56 |                 0.2212 |                   0.2315 |                         0.9468 |                  1      |
| MID_RETURN     | LARGE        |              56 |                 0.8786 |                   0.7668 |                         1.185  |                  1      |
| MID_RETURN     | MID_SIZE     |              56 |                 0.1324 |                   0.1728 |                         0.5558 |                  1      |
| MID_RETURN     | SMALL        |              56 |                 0.216  |                   0.2273 |                         0.9087 |                  0.9821 |

## Cell support

Primary covers period_index 1–56. A period-level size-stratum contrast requires both frozen HIGH_ACTIVITY and LOW_ACTIVITY cells to have at least 25 members and at least 80% valid outcomes; the size-controlled aggregate requires at least two valid size strata. No missing endpoint was filled and no signal member was deleted or reassigned.

Across the 27 return × size × activity cells, median membership is **166.5**, the smallest observed cell minimum is **1**, the median p10 membership is **115.0**, and the smallest cell-specific p10 is **5.0**. Sparse extreme cells materially limit stratum-level interpretation even though the aggregate requires two valid strata.

## Statistical stability

Size-controlled and size-stratum period contrasts use period-level equal weighting. Descriptive uncertainty reuses the formal H5A six-period circular moving-block bootstrap, 10,000 repetitions and seed 20260721, with direction consistency and leave-one-period-out sign consistency. No new acceptance rule is applied.

## Data and QA

- Size is signal-date `log_total_market_cap`, status `HISTORICAL_DATED_NOT_VINTAGE_AUDITED`; missing values are not imputed.
- Size terciles use `(log_total_market_cap ascending, stock_code ascending)` within each formal signal-ready period.
- Original activity and return states are never reranked inside size cells.
- Rebuilt formal H5A stock counts, outcome counts, returns, aligned returns, coverage and validity flags reconcile to the official H5A period file at numerical tolerance.

## Interpretation boundary and next step

The table shows how much of the already-observed H5A difference survives one coarse size stratification. Size remains a major alternative explanation for LOW_RETURN and MID_RETURN, where the magnitude falls substantially and stratum signs are heterogeneous. It is not a complete substitute explanation for HIGH_RETURN, whose size-controlled values remain close to the original at 20D and 60D and retain the same aggregate sign through 120D. Persistence cannot be renamed a pure trading-activity effect because residual size imbalance, sparse cells, VOL20, price and other known exposures remain. A separately preregistered VOL20 diagnostic may be worth considering after human review; it was not run here.

## Further questions

- Is the residual within-tercile size imbalance acceptable for interpretation, given that regression, matching and finer bins were deliberately prohibited?
- Does the student want to preregister one VOL20-only follow-up, or stop after documenting the multi-factor nature of the proxy?

## Research identity

analysis_type=post_h5a_size_control_diagnostic; sample_role=historical_seen; descriptive_only=true; causal_claim_allowed=false; alpha_claim_allowed=false; oos_claim_allowed=false; size_data_status=HISTORICAL_DATED_NOT_VINTAGE_AUDITED; activity_state_redefined=false; return_state_redefined=false; future_horizons_changed=false; alternative_proxy_tested=false; volatility_control_run=false; MCTS_run=false; Phase_B_run=false
