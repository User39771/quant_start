# Hypothesis 8 v1 — Stock-Level Adapted Replication

`research_type=MECHANISM_REPLICATION_DIAGNOSTIC`; `replication_class=STOCK_LEVEL_ADAPTED_REPLICATION`; `descriptive_pattern_metrics_only`; `human_interpretation_required=true`.

The formal preregistration was written before membership freeze and before the first real Eq.9 fit. Primary contains 474 stocks at the fixed 750-row threshold; the fixed 1000-row long-history sensitivity contains 312 nested stocks. Successful Eq.9 fits=1422; regression numeric failures=0. No coefficient-based exclusion occurred.

## Level 1 — empirical facts: P1 close-to-close

| metric      |   N |        mean |      median |        IQR |          p10 |        p90 |   negative_share |   wilcoxon_stat |   wilcoxon_p_one_sided |
|:------------|----:|------------:|------------:|-----------:|-------------:|-----------:|-----------------:|----------------:|-----------------------:|
| gamma31     | 474 | 0.001903    | 0.00201664  | 0.00352751 | -0.00140495  | 0.00515253 |         0.221519 |             nan |             nan        |
| gamma32     | 474 | 0.0017092   | 0.00178946  | 0.00259228 | -0.000700289 | 0.00399556 |         0.185654 |             nan |             nan        |
| delta_gamma | 474 | 0.000193798 | 0.000439131 | 0.0030435  | -0.00284834  | 0.00296763 |         0.409283 |           66014 |               0.999443 |

The table reports the frozen distribution summaries. Gamma32 is not described as zero from a nonsignificant test. Whether its economic magnitude is weak relative to gamma31, and whether the joint gamma31/gamma32/delta structure is paper-consistent, requires human interpretation.

## Level 1 — empirical facts: P2 timing

| component                | metric          |   N |         mean |       median |        IQR |   negative_share |   wilcoxon_stat |   wilcoxon_p_one_sided |
|:-------------------------|:----------------|----:|-------------:|-------------:|-----------:|-----------------:|----------------:|-----------------------:|
| CLOSE_TO_CLOSE           | delta_gamma     | 474 |  0.000193798 |  0.000439131 | 0.0030435  |         0.409283 |           66014 |            0.999443    |
| OVERNIGHT                | delta_gamma     | 474 |  0.000695172 |  0.000814836 | 0.00194231 |         0.310127 |           83983 |            1           |
| INTRADAY                 | delta_gamma     | 474 | -0.000582469 | -0.00033987  | 0.00253237 |         0.567511 |           42687 |            2.57995e-06 |
| INTRADAY_MINUS_OVERNIGHT | timing_contrast | 474 | -0.00127764  | -0.00105534  | 0.00371218 |         0.679325 |           30713 |            5.1188e-18  |

`TIMING_CONTRAST=DELTA_IN-DELTA_OUT`. CC, overnight and intraday use identical stock-date rows and X matrices; only Y differs. Simple-return and coefficient additivity are not assumed. Whether the observed intraday-versus-overnight distribution is paper-consistent requires human interpretation.

## Long-history 1000 nested sensitivity

| component                | metric          |   N |       median |   negative_share |   primary_750_median |   difference_in_median |   primary_750_negative_share |   difference_in_negative_share |   wilcoxon_p_one_sided |
|:-------------------------|:----------------|----:|-------------:|-----------------:|---------------------:|-----------------------:|-----------------------------:|-------------------------------:|-----------------------:|
| CLOSE_TO_CLOSE           | delta_gamma     | 312 |  0.000480543 |         0.397436 |          0.000439131 |            4.1412e-05  |                     0.409283 |                   -0.0118468   |            0.999855    |
| OVERNIGHT                | delta_gamma     | 312 |  0.000869563 |         0.282051 |          0.000814836 |            5.47266e-05 |                     0.310127 |                   -0.0280753   |            1           |
| INTRADAY                 | delta_gamma     | 312 | -0.000307095 |         0.567308 |         -0.00033987  |            3.27758e-05 |                     0.567511 |                   -0.000202856 |            0.000173491 |
| INTRADAY_MINUS_OVERNIGHT | timing_contrast | 312 | -0.00104121  |         0.692308 |         -0.00105534  |            1.41331e-05 |                     0.679325 |                    0.0129828   |            7.00196e-14 |

These are the same full selected-segment stock estimates restricted to the nested 1000-row members, not refitted 1000-observation windows and not an alternate Primary.

## Secondary size-quintile diagnostic

| size_quintile   | metric         |   size_n |       median |        IQR |   negative_share |   wilcoxon_p_one_sided |
|:----------------|:---------------|---------:|-------------:|-----------:|-----------------:|-----------------------:|
| Q1              | gamma31_cc     |       95 |  0.00275895  | 0.00339883 |         0.136842 |          nan           |
| Q1              | gamma32_cc     |       95 |  0.00102743  | 0.00277247 |         0.263158 |          nan           |
| Q1              | delta_cc       |       95 |  0.00154762  | 0.00214712 |         0.178947 |            1           |
| Q1              | delta_intraday |       95 |  9.42483e-05 | 0.00212519 |         0.463158 |            0.761977    |
| Q2              | gamma31_cc     |       95 |  0.00254006  | 0.00314964 |         0.168421 |          nan           |
| Q2              | gamma32_cc     |       95 |  0.00156708  | 0.00249217 |         0.178947 |          nan           |
| Q2              | delta_cc       |       95 |  0.000845435 | 0.00250783 |         0.305263 |            0.999994    |
| Q2              | delta_intraday |       95 | -0.000247022 | 0.0024003  |         0.568421 |            0.0496696   |
| Q3              | gamma31_cc     |       95 |  0.00194793  | 0.00349717 |         0.2      |          nan           |
| Q3              | gamma32_cc     |       95 |  0.00155134  | 0.00249353 |         0.157895 |          nan           |
| Q3              | delta_cc       |       95 |  0.000697467 | 0.002566   |         0.368421 |            0.993757    |
| Q3              | delta_intraday |       95 | -0.000673835 | 0.00242574 |         0.610526 |            0.00259474  |
| Q4              | gamma31_cc     |       95 |  0.00198275  | 0.00322196 |         0.231579 |          nan           |
| Q4              | gamma32_cc     |       95 |  0.00223931  | 0.00251034 |         0.178947 |          nan           |
| Q4              | delta_cc       |       95 | -0.000181797 | 0.00328377 |         0.505263 |            0.261594    |
| Q4              | delta_intraday |       95 | -0.000503318 | 0.00259526 |         0.568421 |            0.00550118  |
| Q5              | gamma31_cc     |       94 |  0.000923595 | 0.00410079 |         0.37234  |          nan           |
| Q5              | gamma32_cc     |       94 |  0.002203    | 0.00212245 |         0.148936 |          nan           |
| Q5              | delta_cc       |       94 | -0.00142565  | 0.00313433 |         0.691489 |            4.73437e-06 |
| Q5              | delta_intraday |       94 | -0.00116144  | 0.00345064 |         0.62766  |            0.000186932 |

Quintiles use average historical circulating market capitalization within Primary 750. This is paper-comparison description only; it is not a size regression and does not explain H7.

## Contract and QA

- analysis 2020-02-11 through formation 2026-08-19; final endpoint 2026-08-20;
- BaoStock raw OHLC, circulating turnover, explicit CA row exclusion, exact-prior-22 transform, and matched CC/OUT/IN rows;
- zero-mean GARCH(1,1), normal, decimal simple returns, `arch 8.0.0`, longest CA-clean segment only;
- 11-column full-rank Eq.9 design, conditioning-date weekday, percentage-point returns, decimal-squared sigma2;
- preregistration mtime ns=1788224249238047600; threshold search=false; winsorization=false; H7 rerun=false; strategy/backtest=false.

## Limitations

This is a stock-level adaptation of an index-level Primary over 2020–2026 rather than the paper’s 2002–2021 period. The paper’s 2400-day stock-history requirement cannot be reproduced. The current/local universe is not point-in-time; observed-ever-ST is not lifetime-ever-ST. BaoStock circulating turnover is only a close economic match to the paper denominator. Raw OHLC plus explicit CA-row exclusion and the CA source accepted with limitations are local adaptations.

The longest-clean-segment rule strongly selects stocks with fewer observed CA events and longer uninterrupted histories: pre-result sample diagnostics show Spearman(CA events, final rows) about -0.679 and median event count seven among candidates versus one in the 750 and 1000 samples. P3 institutional comparison and price-limit robustness are unavailable. GARCH is fitted in-sample, stock coefficients contain estimation noise, stocks are cross-sectionally dependent, and simple-return CC/OUT/IN coefficients are not additive.

No T+1 causal mechanism, positive-feedback trader identification, Alpha, strategy, or investment conclusion is permitted. Level 2 paper-consistency judgment is reserved for human review; Level 3 mechanism claims are prohibited.

Key factual medians: gamma31_CC=0.002016640723999914; gamma32_CC=0.0017894604599496197; delta_CC=0.00043913102173225894; delta_OUT=0.0008148358869173558; delta_IN=-0.00033987040413607957; timing contrast=-0.00105534345229907. Long-history delta_CC=0.0004805430004285044. Size-quintile CC delta medians: Q1=0.0015476153252945712, Q2=0.00084543485259677, Q3=0.0006974669948610485, Q4=-0.00018179719363714542, Q5=-0.0014256526743808527.

STOP AFTER H8 REPORT.
