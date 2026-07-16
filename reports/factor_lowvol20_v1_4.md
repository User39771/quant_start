# LOWVOL20 Factor Research v1.4

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
- interval distribution: 20:56
- approximate_annualization=false

## Readiness

| rebalance_date      |   signal_count |   evaluation_count | readiness_pass   | ic_valid   | quantile_valid   | risk_ic_valid   | period_phase   |
|:--------------------|---------------:|-------------------:|:-----------------|:-----------|:-----------------|:----------------|:---------------|
| 2025-04-17 00:00:00 |             54 |                 54 | True             | True       | True             | True            | main           |
| 2025-05-20 00:00:00 |             54 |                 54 | True             | True       | True             | True            | main           |
| 2025-06-18 00:00:00 |             54 |                 54 | True             | True       | True             | True            | main           |
| 2025-07-16 00:00:00 |             54 |                 54 | True             | True       | True             | True            | main           |
| 2025-08-13 00:00:00 |             54 |                 54 | True             | True       | True             | True            | main           |
| 2025-09-10 00:00:00 |             54 |                 54 | True             | True       | True             | True            | main           |
| 2025-10-16 00:00:00 |             54 |                 54 | True             | True       | True             | True            | main           |
| 2025-11-13 00:00:00 |             54 |                 54 | True             | True       | True             | True            | main           |

## Return effect and risk persistence

| factor_name   | sample_basis                          |   period_count |   mean_rank_ic |   rank_ic_standard_error |   rank_ic_ci_lower |   rank_ic_ci_upper |   mean_risk_persistence_rank_ic |
|:--------------|:--------------------------------------|---------------:|---------------:|-------------------------:|-------------------:|-------------------:|--------------------------------:|
| LOWVOL10      | common_10_20_40_exact_sample          |             55 |      0.0939639 |                0.0331763 |          0.0289383 |           0.158989 |                        0.400224 |
| LOWVOL20      | common_10_20_40_exact_sample          |             55 |      0.0925686 |                0.033342  |          0.0272183 |           0.157919 |                        0.432425 |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic |             56 |      0.0920461 |                0.0326407 |          0.0280704 |           0.156022 |                        0.434187 |
| LOWVOL20      | lowvol20_primary_reliable_sample      |             56 |      0.0920461 |                0.0326407 |          0.0280704 |           0.156022 |                        0.434187 |
| LOWVOL40      | common_10_20_40_exact_sample          |             55 |      0.106749  |                0.0331756 |          0.0417248 |           0.171773 |                        0.45768  |

| factor_name   | sample_basis                          | portfolio   |   mean_return |   annualized_volatility |   period_endpoint_maximum_drawdown |   mean_forward_realized_volatility |
|:--------------|:--------------------------------------|:------------|--------------:|------------------------:|-----------------------------------:|-----------------------------------:|
| LOWVOL10      | common_10_20_40_exact_sample          | Q1          |   0.00819902  |                0.434132 |                          -0.522228 |                          0.565649  |
| LOWVOL10      | common_10_20_40_exact_sample          | Q2          |   0.0268859   |                0.554451 |                          -0.40703  |                          0.51172   |
| LOWVOL10      | common_10_20_40_exact_sample          | Q3          |   0.0200182   |                0.454537 |                          -0.333638 |                          0.474662  |
| LOWVOL10      | common_10_20_40_exact_sample          | Q4          |   0.0209843   |                0.37009  |                          -0.332353 |                          0.424132  |
| LOWVOL10      | common_10_20_40_exact_sample          | Q5          |   0.0157866   |                0.336571 |                          -0.374429 |                          0.38072   |
| LOWVOL10      | common_10_20_40_exact_sample          | Q5-Q1       |   0.0075876   |                0.255923 |                          -0.26982  |                         -0.184929  |
| LOWVOL10      | common_10_20_40_exact_sample          | Q5-UNIVERSE |  -0.00265707  |                0.16624  |                          -0.379366 |                         -0.0925476 |
| LOWVOL10      | common_10_20_40_exact_sample          | UNIVERSE    |   0.0186828   |                0.403411 |                          -0.367283 |                          0.471936  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q1          |   0.00710181  |                0.465421 |                          -0.461111 |                          0.567049  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q2          |   0.0285535   |                0.512788 |                          -0.430314 |                          0.51315   |
| LOWVOL20      | common_10_20_40_exact_sample          | Q3          |   0.023007    |                0.460139 |                          -0.400378 |                          0.4822    |
| LOWVOL20      | common_10_20_40_exact_sample          | Q4          |   0.0152212   |                0.366306 |                          -0.348065 |                          0.413182  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q5          |   0.0182389   |                0.331888 |                          -0.319166 |                          0.381368  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q5-Q1       |   0.011137    |                0.298961 |                          -0.328784 |                         -0.185682  |
| LOWVOL20      | common_10_20_40_exact_sample          | Q5-UNIVERSE |  -0.000204831 |                0.186459 |                          -0.317304 |                         -0.0919    |
| LOWVOL20      | common_10_20_40_exact_sample          | UNIVERSE    |   0.0186828   |                0.403411 |                          -0.367283 |                          0.471936  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q1          |   0.0118801   |                0.47312  |                          -0.467671 |                          0.568629  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q2          |   0.0284824   |                0.507379 |                          -0.430314 |                          0.511006  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q3          |   0.0242164   |                0.456619 |                          -0.400378 |                          0.480645  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q4          |   0.0157349   |                0.362664 |                          -0.348065 |                          0.412001  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q5          |   0.0194927   |                0.330547 |                          -0.319166 |                          0.380297  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q5-Q1       |   0.00761258  |                0.3048   |                          -0.328784 |                         -0.188333  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | Q5-UNIVERSE |  -0.000478745 |                0.184969 |                          -0.318373 |                         -0.092075  |
| LOWVOL20      | lowvol20_all_exact_windows_diagnostic | UNIVERSE    |   0.0199715   |                0.405343 |                          -0.367283 |                          0.472372  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q1          |   0.0118801   |                0.47312  |                          -0.467671 |                          0.568629  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q2          |   0.0284824   |                0.507379 |                          -0.430314 |                          0.511006  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q3          |   0.0242164   |                0.456619 |                          -0.400378 |                          0.480645  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q4          |   0.0157349   |                0.362664 |                          -0.348065 |                          0.412001  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q5          |   0.0194927   |                0.330547 |                          -0.319166 |                          0.380297  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q5-Q1       |   0.00761258  |                0.3048   |                          -0.328784 |                         -0.188333  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | Q5-UNIVERSE |  -0.000478745 |                0.184969 |                          -0.318373 |                         -0.092075  |
| LOWVOL20      | lowvol20_primary_reliable_sample      | UNIVERSE    |   0.0199715   |                0.405343 |                          -0.367283 |                          0.472372  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q1          |   0.00683029  |                0.465874 |                          -0.476344 |                          0.575771  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q2          |   0.0238365   |                0.479191 |                          -0.448895 |                          0.514677  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q3          |   0.0216278   |                0.513528 |                          -0.374988 |                          0.468705  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q4          |   0.0190882   |                0.357275 |                          -0.326572 |                          0.423892  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q5          |   0.0208956   |                0.328906 |                          -0.348829 |                          0.373753  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q5-Q1       |   0.0140653   |                0.295551 |                          -0.398995 |                         -0.202018  |
| LOWVOL40      | common_10_20_40_exact_sample          | Q5-UNIVERSE |   0.00245192  |                0.187938 |                          -0.370968 |                         -0.0995151 |
| LOWVOL40      | common_10_20_40_exact_sample          | UNIVERSE    |   0.0186828   |                0.403411 |                          -0.367283 |                          0.471936  |

| segment               |   q5_minus_q1_volatility |    vol_se |    vol_lo |     vol_hi |   q5_minus_q1_drawdown |    dd_se |      dd_lo |    dd_hi |
|:----------------------|-------------------------:|----------:|----------:|-----------:|-----------------------:|---------:|-----------:|---------:|
| historical_validation |                -0.174035 | 0.0999687 | -0.359272 | 0.00414989 |              0.0672777 | 0.091463 | -0.0264443 | 0.336312 |

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
| historical_validation_mean_rank_ic         | 0.08867178760533968                              | ok       | lowvol20_primary_reliable_sample |
| rank_ic_standard_error                     | 0.053700909062594844                             | ok       | lowvol20_primary_reliable_sample |
| rank_ic_ci_lower                           | -0.016581994157346208                            | ok       | lowvol20_primary_reliable_sample |
| rank_ic_ci_upper                           | 0.19392556936802557                              | ok       | lowvol20_primary_reliable_sample |
| historical_validation_mean_q5_q1           | 0.0188980271672651                               | ok       | lowvol20_primary_reliable_sample |
| q5_q1_standard_error                       | 0.020910088687506906                             | ok       | lowvol20_primary_reliable_sample |
| q5_q1_ci_lower                             | -0.02208574666024844                             | ok       | lowvol20_primary_reliable_sample |
| q5_q1_ci_upper                             | 0.05988180099477863                              | ok       | lowvol20_primary_reliable_sample |
| primary_evidence_pass_count                | 4                                                | ok       | lowvol20_primary_reliable_sample |
| auxiliary_evidence_pass_count              | 8                                                | ok       | lowvol20_primary_reliable_sample |
| all_exact_validation_mean_rank_ic          | 0.08867178760533968                              | ok       | lowvol20_primary_reliable_sample |
| all_exact_validation_mean_q5_q1            | 0.0188980271672651                               | ok       | lowvol20_primary_reliable_sample |
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
