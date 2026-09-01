# Hypothesis 8 v1 Preregistration

```text
hypothesis_id=H8
research_type=MECHANISM_REPLICATION_DIAGNOSTIC
paper=Yao_and_Yang_2026
replication_class=STOCK_LEVEL_ADAPTED_REPLICATION
paper_primary_level=INDEX_LEVEL
local_primary_level=STOCK_LEVEL
PRIMARY_750_ROLE_FIXED_BEFORE_GAMMA=true
LONG_HISTORY_1000_ROLE_FIXED_BEFORE_GAMMA=true
human_interpretation_required=true
```

## Research question and research identity

This study asks whether the sign asymmetry and next-day timing structure predicted by Yao, Jing and Yang, Yiwen (2026), “Positive feedback trading, the T+1 rule, and asymmetric return reversals in China,” *Economic Modelling* 164, 107783, appear in the project’s newer selected A-share main-board sample.

This is a stock-level adapted replication and mechanism diagnostic. The paper’s primary design is index-level; its Section 7 stock-level analysis is diagnostic. Because the project does not have reliable aggregate turnover for the paper’s four indices, stock-level Eq.9 is the local Primary. This is neither an exact nor a full replication and cannot establish Alpha, a trading strategy, or a causal T+1 mechanism.

H7 remains a frozen `PHENOMENON_DIAGNOSTIC` about continuation under relative activity. H8 is not H7 robustness, does not import or rerun H7 research logic, and neither study changes the other’s status.

## Frozen predictions

P1 SIGN asks whether, in paper-style above-trend turnover states, negative-return conditioning days have stronger next-day turnover-dependent reversal than nonnegative-return days. The central coefficients are `gamma31`, `gamma32`, and `DELTA_GAMMA = gamma31 - gamma32`. The paper-consistent structure is `gamma31 < 0`, gamma32 economically weaker, and `DELTA_GAMMA < 0`; gamma31 alone is insufficient.

P2 TIMING asks whether this sign-asymmetric relation is concentrated in day t+1 intraday return, rather than overnight return. Close-to-close, overnight, and intraday equations use identical conditioning dates, X matrices, stocks, and stock-date rows; only the dependent variable changes. The adapted paired diagnostic is `TIMING_CONTRAST = DELTA_IN - DELTA_OUT`, expected below zero.

P3 institutional comparison is `NOT_FEASIBLE`: the project lacks matched H-share prices, turnover, and the paper’s AHXA/AHXH index data. No board, size, or period split substitutes for T+1 versus T+0. Price-limit robustness is `UNAVAILABLE_IN_V1` and does not block Primary; no return- or OHLC-based synthetic limit flag is allowed.

## Frozen data, time, and sample

- `DATA_CUTOFF=2026-08-20`; `ANALYSIS_START=2020-02-11`; `FORMATION_CUTOFF=2026-08-19`; `FINAL_ENDPOINT=2026-08-20`.
- Universe is SH and SZ main-board stocks only. ChiNext, STAR and B-shares are excluded.
- Entire stocks with any locally observed `isST=1` through 2026-08-20 are excluded. This observed-ever-ST rule is not lifetime-ever-ST and the current/local universe is not point-in-time.
- Corporate actions use `BAOSTOCK_QUERY_ADJUST_FACTOR`, status `BAOSTOCK_CA_SOURCE_ACCEPTED_WITH_LIMITATIONS`. Validation before results consists of the 40-stock BaoStock probe, 193/193 CNINFO exact-date matches, and 20/20 incremental exact-date matches.
- Raw BaoStock OHLC is the only price source. Explicit corporate-action rows are excluded; raw prices are not adjusted and QFQ prices are not substituted.
- If t or t+1 is an explicit CA event date, that stock-date is excluded from all three dependent-variable equations, including intraday, to preserve one matched sample.

Each final row must belong to the frozen candidate set; have successful fixed GARCH; lie from 2020-02-11 through 2026-08-19 and inside the stock’s selected longest CA-clean segment; have exact-prior-22 valid turnover, current return, V, sign dummies, finite positive sigma2, valid next open/close, no t/t+1 CA event, and a conditioning-date weekday.

Before Eq.9, membership is frozen from `h8_extended_final_clean_stock_rows.csv`. `PRIMARY_MIN_ROWS=750` is the only Primary and must contain 474 stocks. `LONG_HISTORY_MIN_ROWS=1000` is a nested sensitivity and must contain 312 stocks; it reuses the same full-period stock estimates and does not refit a 1000-row window. Thresholds 1250 and 1500 remain sample diagnostics only and receive no formal gamma result tree.

## Frozen variables

All returns are simple returns. Conditioning return is `r_t_decimal = close_t / close_(t-1) - 1`, and regression scale is `r_t_pp = 100*r_t_decimal`, so 1% equals 1.0. Dependent variables, converted to percentage points before regression, are:

- `r_cc_(t+1) = close_(t+1)/close_t - 1`;
- `r_out_(t+1) = open_(t+1)/close_t - 1`;
- `r_in_(t+1) = close_(t+1)/open_(t+1) - 1`.

The exact simple-return relation is `1+r_cc=(1+r_out)(1+r_in)`. Neither return nor coefficient additivity is assumed.

Primary turnover is BaoStock circulating turnover, a close economic match—not an exact denominator match—to volume divided by float-adjusted shares. For each t, the preceding 22 common-market dates, excluding t, must all have `tradestatus=1` and positive finite turnover. Define `LTURN=ln(TURN)`, `VBAR_t=LTURN_t-mean(LTURN_(t-1)...LTURN_(t-22))`, and `V_t=max(VBAR_t,0)`. Rows with V=0 remain. H7 total-share turnover and alternative windows or transforms are prohibited.

`D_NEG=1{r_t<0}` and `D_POS=1{r_t>=0}`; zero return belongs to D_POS and no third state is created.

## Frozen GARCH chronology

Use `arch==8.0.0` and `arch_model(decimal_simple_returns, mean="Zero", vol="GARCH", p=1, q=1, dist="normal", rescale=False)`. Conditional variance remains in decimal-return-squared units. For each candidate, identify every CA-clean consecutive return segment between 2020-02-11 and 2026-08-19, choose the longest, and choose the earliest when tied. Fit exactly one model on that segment. No segment concatenation, alternate distribution/optimizer, shared parameters, or failed-model rescue is allowed. A numerical failure excludes the stock before regression.

This chronology strongly selects stocks with fewer observed corporate-action events and longer uninterrupted histories. Before H8 results, Spearman(CA event count, final rows) was approximately -0.679; all candidates had median seven events, while both the 750 and 1000 samples had median one. The final sample must not be described as representative of the entire A-share main board.

## Frozen Eq.9 design and estimation

For every stock and each of CC, OUT and IN, estimate time-series unweighted OLS with the same 11-column X matrix:

1. intercept;
2. `MON_t*r_t_pp`;
3. `TUE_t*r_t_pp`;
4. `WED_t*r_t_pp`;
5. `THU_t*r_t_pp`;
6. `FRI_t*r_t_pp`;
7. `gamma1 column = V_t*r_t_pp`;
8. `gamma2 column = V_t^2*r_t_pp`;
9. `gamma31 column = D_NEG_t*V_t*r_t_pp^3`;
10. `gamma32 column = D_POS_t*V_t*r_t_pp^3`;
11. `gamma4 column = (1000*sigma2_t)*r_t_pp`.

The weekday is t’s weekday and exactly one weekday slope is active. No standalone r term is added. Before fit, X and Y must be finite, X must have rank 11, the condition number must be finite, and critical interactions must not be constant. A failing stock/component is `REGRESSION_NUMERIC_FAILURE`; rows, outliers, or stocks are not removed to rescue it. No winsorization or weighted/pooled/panel/Fama–MacBeth/regularized estimator is permitted.

The scaling fixture is fixed: for `r_decimal=0.01`, `r_pp=1`, `V=2`, and `sigma2=0.0004`, the V, V-squared, positive cubic, and variance columns equal 2, 4, 2, and 0.4. For `r_pp=-1`, the negative cubic column equals -2.

## Frozen aggregation and tests

For Primary-750 CC, report N, mean, median, standard deviation, p10, p25, p75, p90, IQR, and negative shares for gamma31, gamma32, and DELTA. The fixed P1 test is `scipy.stats.wilcoxon(DELTA_nonzero_finite, alternative="less", zero_method="wilcox", correction=False, method="auto")`. A nonsignificant gamma32 is not proof of zero; “weak relative to gamma31” is allowed only if effect sizes support it.

For CC, OUT and IN, report the same DELTA distribution and one-sided Wilcoxon. For `TIMING_CONTRAST=DELTA_IN-DELTA_OUT`, report mean, median, IQR, negative share, and the same one-sided Wilcoxon. Coefficient additivity is neither tested nor assumed.

The nested 1000-stock sensitivity re-aggregates the already estimated Primary coefficients and compares medians and negative shares; it never replaces Primary. Within Primary 750, average historical circulating market capitalization forms deterministic stock-level size quintiles for secondary paper comparison. Each quintile reports CC gamma31/gamma32 medians and IQRs, CC DELTA median/IQR/negative share/Wilcoxon, and intraday DELTA. No size regression or H7 interpretation is allowed.

Runner output is `descriptive_pattern_metrics_only`; `human_interpretation_required=true`. It cannot emit H8_SUPPORTED, H8_REJECTED, T1_CONFIRMED, POSITIVE_FEEDBACK_CONFIRMED, or MECHANISM_IDENTIFIED.

## Prohibited searches and limitations

No alternative turnover, lookback, sign cutoff, GARCH, threshold, cutoff, CA rule, segment model, return transform, institutional/industry/size interaction, price-limit proxy, reform split, sentiment, ownership, H5/H6 variable, H7 rerun, strategy, or backtest is permitted. Extreme coefficients are flagged at the cross-sectional top/bottom 1% but retained and not refitted.

Required limitations are: stock-level adaptation of an index-level Primary; 2020–2026 rather than 2002–2021; inability to meet the paper’s 2400-day individual-history requirement; 750 Primary and 1000 sensitivity roles; current-universe survivorship; observed-ever-ST rather than lifetime-ever-ST; turnover denominator approximation; raw-OHLC plus explicit-row-exclusion adaptation; limited CA-source validation; strong CA-frequency and uninterrupted-history selection; unavailable P3 and price-limit robustness; in-sample GARCH rather than prospective forecasting; nonadditive simple-return components and coefficients; noisy stock-level estimates; cross-sectional dependence among stocks; and no Alpha, strategy, investment, or causal mechanism conclusion.
