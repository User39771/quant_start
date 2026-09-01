# Hypothesis 7 — Dynamic Volume–Return Relation Diagnostic v1

## Status and identity

This is a D05-inspired, historical-seen individual-stock mechanism diagnostic, not an exact replication, strategy test, Alpha claim, causal identification, or OOS result. `human_interpretation_required=true`.

Interpretation order is fixed: Primary 750 1D; long-history 1,000 1D; 2D/5D; Secondary matched turnover; size heterogeneity. Later diagnostics do not replace Primary.

## Frozen contract and realized sample

- Analysis cutoff: 2026-05-11.
- Primary turnover: TOTAL_SHARE_TURNOVER; Secondary: BAOSTOCK_CIRCULATING_TURNOVER.
- Baseline: last 200 strictly prior active observations; direct natural log; no epsilon.
- Formation: active and non-ST; historical active ST observations remain eligible in the baseline.
- Primary 750 members: 4470/5195 (86.04%).
- Long-history 1,000 members: 3944/5195 (75.92%); nested in Primary: True.
- Primary successful regressions: 4470; numerical failures among eligible regressions: 0.

## Primary 750: 1D C2 distribution

| count | mean | median | std | positive_share | negative_share | p1 | p5 | p10 | p25 | p75 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4470 | -0.0173551 | -0.0178049 | 0.0605171 | 0.38255 | 0.61745 | -0.162342 | -0.115848 | -0.0938501 | -0.0578363 | 0.0220425 | 0.0594356 | 0.0802809 | 0.131225 |

### HAC(5) t-statistic distribution (descriptive only)

| count | mean | median | std | positive_share | negative_share | p1 | p5 | p10 | p25 | p75 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 4470 | -0.369319 | -0.342101 | 1.14582 | 0.38255 | 0.61745 | -3.14081 | -2.28239 | -1.86036 | -1.12577 | 0.422906 | 1.07052 | 1.45547 | 2.15317 |

No per-stock significance count is used because the individual regressions create a large multiple-testing problem.

C2 above zero means higher relative turnover moves the current/future-return conditional slope in a more positive direction; it does not by itself mean momentum or identify private information.

### Effective slopes

| V_point | n | mean | median | p10 | p90 | positive_share |
|---|---|---|---|---|---|---|
| p10 | 4470 | 0.0608233 | 0.0561039 | -0.0509405 | 0.179868 | 0.747875 |
| p50 | 4470 | 0.0479141 | 0.0439423 | -0.0244689 | 0.126174 | 0.800671 |
| p90 | 4470 | 0.030295 | 0.0280454 | -0.0346786 | 0.0982305 | 0.714765 |

## Long-history 1,000 robustness

| count | mean | median | std | positive_share | negative_share | p1 | p5 | p10 | p25 | p75 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 3944 | -0.0160136 | -0.0167942 | 0.0593917 | 0.390467 | 0.609533 | -0.155869 | -0.111329 | -0.0913747 | -0.0558357 | 0.0230906 | 0.0598499 | 0.0797833 | 0.126225 |

| V_point | n | mean | median | p10 | p90 | positive_share |
|---|---|---|---|---|---|---|
| p10 | 3944 | 0.0591534 | 0.0544139 | -0.0510535 | 0.177144 | 0.743915 |
| p50 | 3944 | 0.0471287 | 0.0431268 | -0.0249689 | 0.124927 | 0.796653 |
| p90 | 3944 | 0.030687 | 0.0280968 | -0.0334074 | 0.0982456 | 0.719828 |

| n | correlation | sign_agreement | mean_difference | median_difference |
|---|---|---|---|---|
| 3944 | 1 | 1 | 0 | 0 |

The 1,000-row subset prioritizes longer estimation history but has stronger listing-age/board selection. It is not an alternate Primary and is not more correct.

## 2D/5D microstructure robustness

| horizon | count | mean | median | std | positive_share | negative_share | p1 | p5 | p10 | p25 | p75 | p90 | p95 | p99 | corr_with_1D | sign_agreement_with_1D |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 2D | 4470 | -0.0425028 | -0.0443351 | 0.0904697 | 0.301342 | 0.698658 | -0.252479 | -0.185498 | -0.150967 | -0.102219 | 0.0151308 | 0.0729683 | 0.105047 | 0.193855 | 0.802541 | 0.798434 |
| 5D | 4470 | -0.0699582 | -0.07804 | 0.136557 | 0.268904 | 0.731096 | -0.399179 | -0.261952 | -0.221481 | -0.150067 | 0.00665714 | 0.0943886 | 0.155973 | 0.287978 | 0.546171 | 0.716779 |

Attenuation at 2D/5D increases the relevance of a short-horizon microstructure explanation. Persistence only means the relation is not obviously confined to one-day mechanical noise; it does not rule microstructure out.

## Secondary turnover exact-matched robustness

| stock_count | n | correlation | sign_agreement | mean_difference | median_difference | primary_matched_C2_mean | secondary_matched_C2_mean |
|---|---|---|---|---|---|---|---|
| 4470 | 4470 | 0.984301 | 0.969128 | -3.37499e-05 | 3.77217e-07 | -0.0173551 | -0.0173888 |

TOTAL_SHARE_TURNOVER and BAOSTOCK_CIRCULATING_TURNOVER have different denominators. These estimates use exact matched rows so that measurement and sample changes are not conflated.

## Size heterogeneity

| section | group | N | C2_mean | C2_median | C2_positive_share | b_size | HC3_SE | CI90_low | CI90_high | CI95_low | CI95_high | R_squared | spearman_C2_size |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cross_sectional_regression | ALL | 4467 | -0.0173552 | -0.0178077 | 0.382807 | 0.00946613 | 0.000988019 | 0.00784098 | 0.0110913 | 0.00752964 | 0.0114026 | 0.0244574 | 0.139302 |
| size_quartile | Q1_SMALL | 1117 | -0.0245839 | -0.0239316 | 0.346464 |  |  |  |  |  |  |  |  |
| size_quartile | Q2 | 1117 | -0.0245779 | -0.0259669 | 0.33214 |  |  |  |  |  |  |  |  |
| size_quartile | Q3 | 1116 | -0.0187805 | -0.0185816 | 0.361111 |  |  |  |  |  |  |  |  |
| size_quartile | Q4_LARGE | 1117 | -0.0014798 | -0.00144208 | 0.491495 |  |  |  |  |  |  |  |  |

Size diagnostic status: `SUCCESS`. Historical size is measured only on valid Primary dates at or before the cutoff. Missing size never removes a stock from Primary. A negative b_size is only directionally consistent with D05 size heterogeneity; size is not a pure information-asymmetry measure.

C2_hat is a generated first-stage dependent variable. HC3 does not fully account for first-stage estimation error or cross-stock dependence.

## Board composition

| sample | board | stocks | share | C2_mean | C2_median | C2_positive_share |
|---|---|---|---|---|---|---|
| PRIMARY_750 | CHINEXT | 923 | 0.206488 | -0.0142184 | -0.0165347 | 0.385699 |
| PRIMARY_750 | SH_MAIN | 1577 | 0.352796 | -0.0157009 | -0.0157838 | 0.402029 |
| PRIMARY_750 | STAR | 421 | 0.0941834 | -0.0241055 | -0.0247462 | 0.342043 |
| PRIMARY_750 | SZ_MAIN | 1549 | 0.346532 | -0.0190735 | -0.0195664 | 0.371853 |
| LONG_HISTORY_1000 | CHINEXT | 894 | 0.226673 | -0.0147841 | -0.0175679 | 0.38255 |
| LONG_HISTORY_1000 | SH_MAIN | 1479 | 0.375 | -0.0154001 | -0.0151674 | 0.406356 |
| LONG_HISTORY_1000 | STAR | 275 | 0.0697262 | -0.0199581 | -0.0240732 | 0.356364 |
| LONG_HISTORY_1000 | SZ_MAIN | 1296 | 0.3286 | -0.0167248 | -0.017308 | 0.385031 |

Board results are descriptive and help expose listing-age selection; no board-specific hypothesis or model is tested.

## Limitations

- The sample is the current broader-A universe applied historically, with survivorship and future-universe bias; it is not point-in-time.
- QFQ uses the current adjustment vintage. CNINFO total-share lineage has documented exceptions; BaoStock Secondary uses a different circulating-share denominator.
- Authoritative historical price-limit status, quoted bid–ask spreads, and direct analyst-coverage identification are unavailable.
- China's T+1 and market microstructure differ from the U.S. setting studied by D05.
- Size is not a pure information-asymmetry measure; first-stage C2 has estimation error; stocks are not cross-sectionally independent.
- Evidence is sample-internal and historical-seen, not causal, OOS, or an investment conclusion.

## QA and prohibited actions

- elapsed_seconds=113.85
- regression_numeric_failure_count=0
- C2_based_exclusion_count=0
- parameter_search_performed=false
- winsorization_performed=false
- strategy_backtest_run=false
- future_performance_selection_used=false
- MCTS_run=false
- Phase_B_run=false
- PRIMARY_750_ROLE_FIXED_BEFORE_C2=true
- LONG_HISTORY_1000_ROLE_FIXED_BEFORE_C2=true
- 1000_ALLOWED_TO_REPLACE_PRIMARY=false

STOP AFTER H7 REPORT.
