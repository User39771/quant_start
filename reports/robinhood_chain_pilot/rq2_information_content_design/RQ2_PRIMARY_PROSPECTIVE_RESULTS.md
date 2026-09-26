# RQ2 Primary Prospective Results

`PRIMARY_RQ2_PROSPECTIVE_ANALYSIS = COMPLETE`

**Research status:** `PILOT_INFORMED_PROSPECTIVE_EXTENSION`  
**Primary inference:** frozen 43-row `PROSPECTIVE_EXTENSION` sample only  
**Estimator:** OLS with HC3 heteroskedasticity-robust standard errors  
**Interval and p-value reference:** Student t with OLS residual degrees of freedom

## Primary result

The MODEL 1 coefficient on `token_deep_return_30m` is **0.304048** (HC3 SE 0.286911; 95% CI [-0.276773, 0.884869]; p = 0.2960). A 0.01 increase in token log return corresponds to an estimated 0.00304048 change in stock 20:00-to-open log return, holding the frozen conventional after-hours control and asset fixed effects constant.

MODEL 1 R² is 0.296663 and adjusted R² is 0.222627. Relative to MODEL 0, ΔR² is 0.0879916, Δ adjusted R² is 0.0748276, and token partial R² is 0.111195.

The estimate is an observational incremental association, not evidence of causal price discovery, exploitable alpha, profitability, or market inefficiency.

## Frozen sample reconciliation

| Scope | N | Date range |
|---|---:|---|
| Pooled | 43 | 2026-07-22 to 2026-09-04 |
| NVDA | 11 | 2026-07-22 to 2026-08-07 |
| GME | 23 | 2026-07-28 to 2026-09-04 |
| COST | 9 | 2026-08-06 to 2026-09-04 |

All 43 rows are prospective-extension, primary-inferential, stock-QA-passing rows. There are no duplicate token/date keys, missing primary variables, discovery rows, or TSLA rows.

## Descriptive statistics

Values are untrimmed log returns. Standard deviation is the sample standard deviation.

| Scope | Variable | Mean | Median | SD | Minimum | Maximum |
|---|---|---:|---:|---:|---:|---:|
| POOLED | `token_deep_return_30m` | 0.00137919 | 0.000515779 | 0.00640899 | -0.0118914 | 0.0304679 |
| POOLED | `stock_post_return` | 0.00141044 | 0.000409026 | 0.0041901 | -0.00455577 | 0.0208294 |
| POOLED | `stock_20_to_open_return` | 0.000308706 | -0.000730844 | 0.00613 | -0.0109233 | 0.0238052 |
| POOLED | `stock_total_open_gap` | 0.00171914 | -0.000474005 | 0.00878335 | -0.0130528 | 0.0249475 |
| NVDA | `token_deep_return_30m` | -0.00143543 | -0.00133632 | 0.00602318 | -0.0118914 | 0.00978083 |
| NVDA | `stock_post_return` | 0.00297408 | 0.00114235 | 0.00737228 | -0.00455577 | 0.0208294 |
| NVDA | `stock_20_to_open_return` | 0.0028193 | 0.00304115 | 0.0101646 | -0.0109233 | 0.0238052 |
| NVDA | `stock_total_open_gap` | 0.00579338 | 0.0109335 | 0.0144498 | -0.0130528 | 0.0249475 |
| GME | `token_deep_return_30m` | 0.0027009 | 0.00114323 | 0.00641128 | -0.0022155 | 0.0304679 |
| GME | `stock_post_return` | 0.000749618 | 0.000493147 | 0.00173341 | -0.00190218 | 0.00423994 |
| GME | `stock_20_to_open_return` | -0.000820483 | -0.000941567 | 0.00350299 | -0.00730052 | 0.00959154 |
| GME | `stock_total_open_gap` | -7.08648e-05 | -0.000520156 | 0.00442063 | -0.00709804 | 0.0138315 |
| COST | `token_deep_return_30m` | 0.0014416 | 0.00306892 | 0.00642954 | -0.00862081 | 0.0102225 |
| COST | `stock_post_return` | 0.00118807 | -9.60401e-06 | 0.00336155 | -0.00216266 | 0.00892071 |
| COST | `stock_20_to_open_return` | 0.000125907 | 0.000145197 | 0.00469202 | -0.00788379 | 0.00954906 |
| COST | `stock_total_open_gap` | 0.00131398 | -0.000474005 | 0.00762018 | -0.00949986 | 0.0184698 |

## Per-asset diagnostics

Sign agreement excludes a row from its denominator only when either return is exactly zero. No row is removed from any other statistic or model.

| Asset | N | Pearson | Spearman | Sign agreement | Simple beta | HC3 SE | 95% CI | p-value | R² |
|---|---:|---:|---:|---:|---:|---:|---|---:|---:|
| NVDA | 11 | 0.705154 | 0.672727 | 0.727273 (11/11; zero exclusions 0) | 1.19 | 0.50687 | [0.0433812, 2.33662] | 0.0435 | 0.497242 |
| GME | 23 | 0.11653 | 0.0602767 | 0.434783 (23/23; zero exclusions 0) | 0.0636696 | 0.404373 | [-0.77727, 0.904609] | 0.8764 | 0.0135793 |
| COST | 9 | 0.480029 | 0.266667 | 0.666667 (9/9; zero exclusions 0) | 0.350306 | 0.347375 | [-0.471106, 1.17172] | 0.3468 | 0.230428 |

The asset-level coefficient directions are broadly consistent: NVDA positive, GME positive, COST positive. These diagnostics have small samples (NVDA 11, GME 23, COST 9) and are not three independent confirmatory tests.

## MODEL 0 — frozen baseline

`stock_20_to_open_return ~ asset fixed effects + stock_post_return`

N = 43; R² = 0.208671; adjusted R² = 0.147799. The `stock_post_return` coefficient is 0.573668 (HC3 SE 0.588101; 95% CI [-0.61588, 1.76322]; p = 0.3353).

## MODEL 1 — primary RQ2 model

`stock_20_to_open_return ~ asset fixed effects + stock_post_return + token_deep_return_30m`

N = 43; R² = 0.296663; adjusted R² = 0.222627. The primary token beta is 0.304048 (HC3 SE 0.286911; 95% CI [-0.276773, 0.884869]; p = 0.2960). The `stock_post_return` coefficient is 0.461305 (HC3 SE 0.558043; 95% CI [-0.668395, 1.591]; p = 0.4136).

COST is the fixed-effect reference asset. All coefficients, including the two asset indicators, are preserved in `rq2_primary_prospective_model_coefficients.csv`.

## Incremental information

- ΔR² = 0.0879916
- Δ adjusted R² = 0.0748276
- Partial R² = 0.111195
- Formula: `(SSE_MODEL_0 - SSE_MODEL_1) / SSE_MODEL_0`

The partial R² uses ordinary nested-model SSE from the same frozen rows and regressors. HC3 changes coefficient uncertainty, not OLS fitted values or SSE.

## Influence diagnostics

Standard MODEL 1 diagnostics flagged 4 of 43 rows under descriptive heuristics: leverage > 2p/N, absolute externally studentized residual > 2, or Cook's distance > 4/N.
Flagged keys: NVDA 2026-07-23, NVDA 2026-08-04, NVDA 2026-08-05, GME 2026-09-04.
No observation was removed and the model was not rerun after exclusion.

## Interpretation

1. **Direction:** the primary beta is positive.
2. **Magnitude:** beta = 0.304048; a 0.01 token log-return increase maps to an estimated 0.00304048 stock log-return change, conditional on the frozen controls.
3. **Uncertainty:** the 95% CI is [-0.276773, 0.884869], with width 1.16164.
4. **Asset consistency:** directions are broadly consistent across the three small per-asset samples.
5. **Adjusted fit:** adding the token term changes adjusted R² by 0.0748276.
6. **Partial R²:** the token term accounts for 0.111195 of MODEL 0 residual SSE under the nested-model definition.
7. **p-value:** 0.2960, treated as one descriptive uncertainty diagnostic rather than a success threshold.
8. **Sample size:** N = 43 limits precision and the stability of pooled and asset-level estimates.

The prospective result is directionally consistent with incremental information: the pooled token coefficient is positive, all three asset-level simple coefficients are positive, adjusted R² rises by 0.0748276, and partial R² is 0.111195. The evidence is not decisive. The pooled HC3 interval spans materially negative through materially positive values, the estimate is imprecise, four observations cross descriptive influence heuristics, and N = 43 is small. The defensible reading is a positive but uncertain incremental association with a meaningful in-sample fit improvement, not a causal, trading, or guaranteed forecasting result. This is prospective evidence from the frozen extension sample, but the overall project remains pilot-informed rather than fully preregistered or fully outcome-naive.

## Limitations

- The pooled sample has 43 rows across only three assets and is unbalanced by asset.
- Asset-level diagnostics are especially imprecise at N = 11, 23, and 9.
- The design estimates association, not causality, price leadership, trading profitability, or market inefficiency.
- The overall design was informed by an earlier exploratory NVDA pilot, although these 43 outcomes form the protected prospective extension.
- Alpaca historical REST lacks metadata needed to reconstruct every historical correction/cancel chain; the accepted QA limitation remains.
- Token and stock VWAP anchors can retain measurement noise even after the frozen robustness and stock-QA gates.
- No sensitivity analysis, alternative specification, leave-one-out regression, or observation exclusion was run.

## Plots

- `rq2_primary_prospective_plots/rq2_primary_token_vs_stock_scatter.png`
- `rq2_primary_prospective_plots/rq2_primary_token_added_variable_plot.png`

## Freeze confirmations

ONLY THE FROZEN 43-ROW PROSPECTIVE PRIMARY SAMPLE WAS USED.

NO DISCOVERY ROW WAS INCLUDED.

NO TSLA ROW WAS INCLUDED.

NO SAMPLE MEMBERSHIP WAS CHANGED AFTER SEEING RESULTS.

NO QA RULE WAS CHANGED AFTER SEEING RESULTS.

NO OBSERVATION WAS REMOVED BASED ON OUTCOME MAGNITUDE OR INFLUENCE.

NO ALTERNATIVE MODEL WAS SELECTED BASED ON SIGNIFICANCE.

NO SENSITIVITY ANALYSIS WAS RUN.

NO PROFITABILITY OR TRADING CLAIM WAS TESTED.

## Next action

HUMAN / SOL REVIEW OF PRIMARY PROSPECTIVE RQ2 RESULTS BEFORE SENSITIVITY ANALYSES
