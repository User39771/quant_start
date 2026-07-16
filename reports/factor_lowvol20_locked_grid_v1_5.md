# LOWVOL20 Factor Research locked-grid v1.5

## Research status

- status: completed
- verdict: directionally_supported_for_strategy_prototyping
- research_only=true
- primary_factor=LOWVOL20
- current-universe historical research
- universe_point_in_time=false
- suspension_status_available=false
- execution_sim_ready=false
- formal_performance_conclusion_allowed=false
- no_investment_conclusion=true

The primary estimand is the low-volatility effect conditional on minimum observed
price activity. Flat-price rules are data-quality filters, not suspension
identification or proof of tradability. Results do not generalize to the entire
nominal universe.

## Calendar and horizon

- target_rebalance_step=20_baseline_calendar_entries
- forward interval min/median/max: 20/20.0/20
- interval distribution: 20:57
- approximate_annualization=false

## Readiness

| rebalance_date      |   signal_count |   evaluation_count | readiness_pass   | ic_valid   | quantile_valid   | risk_ic_valid   | period_phase   |
|:--------------------|---------------:|-------------------:|:-----------------|:-----------|:-----------------|:----------------|:---------------|
| 2025-04-17 00:00:00 |             56 |                 56 | True             | True       | True             | True            | main           |
| 2025-05-20 00:00:00 |             56 |                 56 | True             | True       | True             | True            | main           |
| 2025-06-18 00:00:00 |             56 |                 56 | True             | True       | True             | True            | main           |
| 2025-07-16 00:00:00 |             56 |                 56 | True             | True       | True             | True            | main           |
| 2025-08-13 00:00:00 |             56 |                 56 | True             | True       | True             | True            | main           |
| 2025-09-10 00:00:00 |             56 |                 56 | True             | True       | True             | True            | main           |
| 2025-10-16 00:00:00 |             56 |                 56 | True             | True       | True             | True            | main           |
| 2025-11-13 00:00:00 |             56 |                 56 | True             | True       | True             | True            | main           |

## Return effect and risk persistence

| factor_name   | sample_basis                          |   period_count |   mean_rank_ic |   rank_ic_standard_error |   rank_ic_ci_lower |   rank_ic_ci_upper |   mean_risk_persistence_rank_ic |
|:--------------|:--------------------------------------|---------------:|---------------:|-------------------------:|-------------------:|-------------------:|--------------------------------:|
| LOWVOL10      | common_10_20_40_exact_sample          |             57 |      0.0891816 |                0.0313086 |          0.0278168 |           0.150546 |                        0.397143 |
| LOWVOL20      | common_10_20_40_exact_sample          |             57 |      0.0879025 |                0.0321372 |          0.0249135 |           0.150892 |                        0.435514 |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic |             57 |      0.0876262 |                0.0320388 |          0.0248302 |           0.150422 |                        0.437063 |
| LOWVOL20      | lowvol20_primary_reliable_sample      |             57 |      0.0876262 |                0.0320388 |          0.0248302 |           0.150422 |                        0.437063 |
| LOWVOL40      | common_10_20_40_exact_sample          |             57 |      0.104033  |                0.0318531 |          0.0416014 |           0.166466 |                        0.457177 |

| factor_name   | sample_basis                          | portfolio   |   mean_return |   annualized_volatility |   period_endpoint_maximum_drawdown |   mean_forward_realized_volatility |
|:--------------|:--------------------------------------|:------------|--------------:|------------------------:|-----------------------------------:|-----------------------------------:|
| LOWVOL10      | common_10_20_40_exact_sample          | Q1          |   0.00972149  |                0.43062  |                          -0.519512 |                          0.561465  |
| LOWVOL10      | common_10_20_40_exact_sample          | Q2          |   0.0228582   |                0.495168 |                          -0.401718 |                          0.504335  |
| LOWVOL10      | common_10_20_40_exact_sample          | Q3          |   0.0275689   |                0.494748 |                          -0.308627 |                          0.469877  |
| LOWVOL10      | common_10_20_40_exact_sample          | Q4          |   0.0219312   |                0.366727 |                          -0.353511 |                          0.421257  |
| LOWVOL10      | common_10_20_40_exact_sample          | Q5          |   0.0155097   |                0.328645 |                          -0.370117 |                          0.379811  |
| LOWVOL10      | common_10_20_40_exact_sample          | Q5-Q1       |   0.00578826  |                0.255676 |                          -0.416621 |                         -0.181653  |
| LOWVOL10      | common_10_20_40_exact_sample          | Q5-UNIVERSE |  -0.00385517  |                0.163551 |                          -0.411133 |                         -0.089118  |
| LOWVOL10      | common_10_20_40_exact_sample          | UNIVERSE    |   0.0193649   |                0.400925 |                          -0.363502 |                          0.468929  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q1          |   0.00949902  |                0.458396 |                          -0.477711 |                          0.563278  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q2          |   0.0281043   |                0.513909 |                          -0.402055 |                          0.508213  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q3          |   0.0269523   |                0.449925 |                          -0.366133 |                          0.477136  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q4          |   0.0160256   |                0.36526  |                          -0.375547 |                          0.410435  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q5          |   0.0171031   |                0.323371 |                          -0.325586 |                          0.377251  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q5-Q1       |   0.00760404  |                0.288558 |                          -0.361809 |                         -0.186027  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q5-UNIVERSE |  -0.00226185  |                0.180539 |                          -0.35719  |                         -0.0916781 |
| LOWVOL20      | common_10_20_40_exact_sample          | UNIVERSE    |   0.0193649   |                0.400925 |                          -0.363502 |                          0.468929  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q1          |   0.0110307   |                0.464512 |                          -0.482132 |                          0.564333  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q2          |   0.0284704   |                0.512942 |                          -0.402055 |                          0.509519  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q3          |   0.0262695   |                0.44881  |                          -0.366133 |                          0.476932  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q4          |   0.0162064   |                0.366698 |                          -0.375547 |                          0.411072  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q5          |   0.0171617   |                0.323138 |                          -0.325586 |                          0.377269  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q5-Q1       |   0.00613106  |                0.294499 |                          -0.417772 |                         -0.187064  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q5-UNIVERSE |  -0.0025005   |                0.181693 |                          -0.365464 |                         -0.0922178 |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | UNIVERSE    |   0.0196622   |                0.401579 |                          -0.363502 |                          0.469487  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q1          |   0.0110307   |                0.464512 |                          -0.482132 |                          0.564333  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q2          |   0.0284704   |                0.512942 |                          -0.402055 |                          0.509519  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q3          |   0.0262695   |                0.44881  |                          -0.366133 |                          0.476932  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q4          |   0.0162064   |                0.366698 |                          -0.375547 |                          0.411072  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q5          |   0.0171617   |                0.323138 |                          -0.325586 |                          0.377269  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q5-Q1       |   0.00613106  |                0.294499 |                          -0.417772 |                         -0.187064  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q5-UNIVERSE |  -0.0025005   |                0.181693 |                          -0.365464 |                         -0.0922178 |
| LOWVOL20      | lowvol20_primary_reliable_sample      | UNIVERSE    |   0.0196622   |                0.401579 |                          -0.363502 |                          0.469487  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q1          |   0.00783832  |                0.464434 |                          -0.51154  |                          0.569267  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q2          |   0.0251014   |                0.469262 |                          -0.419024 |                          0.512164  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q3          |   0.0241827   |                0.511842 |                          -0.359784 |                          0.462925  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q4          |   0.021156    |                0.35139  |                          -0.325159 |                          0.41883   |
| LOWVOL40      | common_10_20_40_exact_sample          | Q5          |   0.0194865   |                0.3192   |                          -0.339348 |                          0.372344  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q5-Q1       |   0.0116482   |                0.289991 |                          -0.396348 |                         -0.196923  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q5-UNIVERSE |   0.000121592 |                0.183697 |                          -0.366098 |                         -0.096585  |
| LOWVOL40      | common_10_20_40_exact_sample          | UNIVERSE    |   0.0193649   |                0.400925 |                          -0.363502 |                          0.468929  |

| segment               |   q5_minus_q1_volatility |    vol_se |    vol_lo |       vol_hi |   q5_minus_q1_drawdown |     dd_se |      dd_lo |   dd_hi |
|:----------------------|-------------------------:|----------:|----------:|-------------:|-----------------------:|----------:|-----------:|--------:|
| historical_validation |                 -0.16242 | 0.0904947 | -0.330343 | -0.000775626 |              0.0752606 | 0.0945633 | -0.0375021 | 0.33453 |

Future-return effects and forward realized-volatility persistence are reported
separately. A missing forward risk path never changes the original quantile.

## Primary versus diagnostic samples

LOWVOL20 primary results use lowvol20_primary_reliable_sample. The
lowvol20_all_exact_windows_diagnostic reports direction before flat-price
screening. LOWVOL10/20/40 use common_10_20_40_exact_sample only and cannot
replace the primary conclusion.

## Hypothesis assessment

| metric                                     | value                                            | status   | sample_basis                     |
|:-------------------------------------------|:-------------------------------------------------|:---------|:---------------------------------|
| historical_validation_mean_rank_ic         | 0.0827364854824809                               | ok       | lowvol20_primary_reliable_sample |
| rank_ic_standard_error                     | 0.05251705960527768                              | ok       | lowvol20_primary_reliable_sample |
| rank_ic_ci_lower                           | -0.020196951343863345                            | ok       | lowvol20_primary_reliable_sample |
| rank_ic_ci_upper                           | 0.18566992230882515                              | ok       | lowvol20_primary_reliable_sample |
| historical_validation_mean_q5_q1           | 0.019511486479359148                             | ok       | lowvol20_primary_reliable_sample |
| q5_q1_standard_error                       | 0.018961150507043428                             | ok       | lowvol20_primary_reliable_sample |
| q5_q1_ci_lower                             | -0.01765236851444597                             | ok       | lowvol20_primary_reliable_sample |
| q5_q1_ci_upper                             | 0.05667534147316426                              | ok       | lowvol20_primary_reliable_sample |
| primary_evidence_pass_count                | 4                                                | ok       | lowvol20_primary_reliable_sample |
| auxiliary_evidence_pass_count              | 7                                                | ok       | lowvol20_primary_reliable_sample |
| all_exact_validation_mean_rank_ic          | 0.0827364854824809                               | ok       | lowvol20_primary_reliable_sample |
| all_exact_validation_mean_q5_q1            | 0.019511486479359148                             | ok       | lowvol20_primary_reliable_sample |
| primary_and_all_exact_direction_consistent | True                                             | ok       | lowvol20_primary_reliable_sample |
| verdict                                    | directionally_supported_for_strategy_prototyping | ok       | lowvol20_primary_reliable_sample |

Epsilon is only numerical zero handling, not an economic materiality threshold.
Confidence intervals are descriptive historical-sample uncertainty, not clean
out-of-sample confirmation.

## Limitations

- This is historical chronological validation, not clean preregistered OOS confirmation.
- Current-universe / survivorship-like bias remains.
- Close-only flat-price diagnostics cannot prove continuous tradability.
- Period-end drawdown is not daily maximum drawdown.
- Q5-Q1 is not an executable A-share long-short strategy.
- formal_performance_conclusion_allowed=false
- execution_sim_ready=false
- no_investment_conclusion=true
