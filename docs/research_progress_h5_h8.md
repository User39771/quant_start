# H5–H8 research progress

This note is a Mentor-facing map of the completed H5–H8 sequence. It summarizes saved preregistrations and final reports; it does not recompute results or promote any result to Alpha, causality, or out-of-sample evidence.

## Shared research identity

- Market: A-shares, using a current broader-A universe applied historically rather than point-in-time constituents.
- Sample role: `historical_seen`.
- Signal discipline: signal-time membership and states are fixed before future outcomes; missing future endpoints do not redefine signals.
- Interpretation boundary: descriptive/mechanism diagnostics only; no trading, causal, OOS, or investment claim.
- Important data limits: survivorship/future-universe bias, current-vintage QFQ prices, imperfect historical share lineage, and no missing-price imputation.

## H5 — trading-activity state and reversal timing

**Question.** Inspired by Lee & Swaminathan (2000), H5 asks whether past-return state and trading-activity state jointly distinguish future continuation and reversal paths.

**Design.** H5A freezes RETURN60 and raw `AMOUNT_MEAN_20` cross-sectional states over 56 Primary periods, then examines nested 20D/60D/120D cumulative returns. H5B keeps the return states and replaces the activity construct with the preregistered turnover-like `VT20_DAILY` signal.

**Evidence.** H5A reports 6/6 stable LOW/HIGH_RETURN activity-horizon contrasts. The subsequent signal-time audit finds mean period Spearman correlation of 0.664 between ACTIVITY_PCT and log market capitalization, while size stratification retains a median 47.4% of absolute contrast magnitude. H5B agrees with H5A in 7/9 fixed comparisons, but its absolute magnitude ratios are only about 0.04–0.19 and all six Primary 90% descriptive intervals include zero.

**Interpretation.** A paper-like historical pattern is visible, but raw amount is an amount-ranked multi-exposure proxy. The effect does not survive the construct change with comparable magnitude, so the repository does not claim a pure turnover mechanism or Alpha.

Start with:

- `reports/hypothesis_5a/h5a_preregistration_and_implementation_plan.md`
- `reports/hypothesis_5a/h5a_diagnostic_report.md`
- `reports/hypothesis_5a/h5a_activity_main_effect_audit.md`
- `reports/hypothesis_5a/h5a_size_control_diagnostic.md`
- `reports/hypothesis_5b/h5b_vt20_preregistration.md`
- `reports/hypothesis_5b/h5b_diagnostic_report.md`
- `scripts/run_h5a_trading_activity_reversal_timing_v1.py`
- `scripts/run_h5b_vt20_diagnostic.py`

## H6 — own-history abnormal activity

**Question.** Inspired by Gervais, Kaniel & Mingelgrin (2001), H6 asks whether a stock's own-history abnormal daily amount, conditional on the inherited H5 RETURN_STATE, corresponds to different subsequent paths.

**Design.** A 50-market-day own-history midrank defines LOW/NORMAL/HIGH shock states. Periods 3–56 are Primary; 20D is the main horizon and 5D/10D are nested path descriptions. The design is amount-based, not a replication of share-volume sorting.

**Evidence.** The 20D HIGH_SHOCK−LOW_SHOCK mean is −0.873, −0.800 and −2.378 percentage points for LOW, MID and HIGH_RETURN. Each descriptive 90% interval lies below zero, and market-normalized amount preserves the direction. Formation-return and slow-trend diagnostics do not eliminate alternative explanations.

**Interpretation.** The negative abnormal-activity association is broad and reasonably stable in this historical sample, especially on the winner side. Its economic mechanism remains unresolved; it is not the positive high-volume premium of the source paper and is not an execution result.

Start with:

- `reports/hypothesis_6/h6_abnormal_activity_data_readiness.md`
- `reports/hypothesis_6/h6_daily_amount_preregistration.md`
- `reports/hypothesis_6/h6_diagnostic_report.md`
- `scripts/run_h6_daily_amount_abnormal_activity_v1.py`

## H7 — dynamic volume–return relation

**Question.** Inspired by Llorente et al. (2002), H7 asks whether relative turnover changes the conditional return relation at the individual-stock level and whether that relation varies with size.

**Design.** The Primary uses total-share turnover, a 200-active-day strictly prior baseline, at least 750 valid regression rows, and a fixed 1D stock-level model. A nested 1,000-row sample, 2D/5D horizons, circulating-turnover matching, and size diagnostics are secondary.

**Evidence.** The Primary contains 4,470 stocks with no numerical regression failures. C2 has median −0.0178 and is negative for 61.7% of stocks. The sign broadly persists in long-history, 2D/5D, and matched-denominator checks. Size is heterogeneous: C2 means move from about −0.0246 in Q1/Q2 to −0.00148 in Q4, and the cross-sectional size slope is positive.

**Interpretation.** H7 documents a historical dynamic volume-return relation and size heterogeneity, but it is not causal or OOS. A later related-literature review showed that the empirical extension was not sufficiently novel to justify further expansion. The process lesson is to complete novelty and related-work checks before expensive data acquisition and estimation.

Start with:

- `reports/hypothesis_7/h7_dynamic_volume_return_data_readiness.md`
- `reports/hypothesis_7/final_contract/h7_final_contract_readiness.md`
- `reports/hypothesis_7/h7_dynamic_volume_return_preregistration_v1.md`
- `reports/hypothesis_7/h7_dynamic_volume_return_report_v1.md`
- `scripts/run_h7_dynamic_volume_return_v1.py`

## H8 — T+1 sign-asymmetric adapted replication

**Question.** H8 maps Yao & Yang (2026) into a feasible stock-level adapted replication: does the predicted sign asymmetry and overnight/intraday timing structure appear in the selected A-share sample?

**Design.** Before estimation, the project freezes corporate-action exclusions, matched return components, exact-prior-22 transformation, zero-mean GARCH(1,1), an 11-column Eq.9 design, a 750-row Primary threshold and a nested 1,000-row sensitivity. The original paper's index-level and institutional tests cannot be fully reproduced.

**Evidence.** Primary contains 474 stocks and 1,422 successful fits. Full-sample close-to-close `delta_gamma` has median +0.000439 and 40.9% negative share, so its direction does not support a full paper-consistent replication. The intraday-minus-overnight timing contrast has median −0.001055 and 67.9% negative share. Size-quintile close-to-close medians move from positive in Q1–Q3 to −0.000182 in Q4 and −0.001426 in Q5.

**Interpretation.** The proper summary is partial and heterogeneous replication evidence: the timing dimension and larger-cap subset are closer to the paper prediction, while the full-sample Primary is not. Selection toward long, corporate-action-light histories and the stock-level adaptation materially limit the claim.

Start with:

- `reports/hypothesis_8/design_mapping/h8_equation_mapping.md`
- `reports/hypothesis_8/final_contract/h8_final_contract_resolution.md`
- `reports/hypothesis_8/h8_preregistration_v1.md`
- `reports/hypothesis_8/h8_report_v1.md`
- `scripts/run_h8_yao_yang_adapted_replication_v1.py`

## Why MCTS is not the headline

The MCTS v0/v1 work is a historical-seen search-mechanism sandbox. It tests registry completeness, formula/rank/portfolio equivalence, and equal-budget MCTS versus Random Search. Both saved comparison reports classify the search advantage as not observed under their frozen rules. The sandbox therefore supplies tooling lessons, not an Alpha result. Future search, if any, should begin with economically meaningful primitives extracted from literature and independently validated before combination.

## Literature anchors

1. Lee, C. M. C. & Swaminathan, B. (2000), “Price Momentum and Trading Volume,” *The Journal of Finance* 55(5), 2017–2069. https://doi.org/10.1111/0022-1082.00280
2. Gervais, S., Kaniel, R. & Mingelgrin, D. H. (2001), “The High-Volume Return Premium,” *The Journal of Finance* 56(3), 877–919. https://doi.org/10.1111/0022-1082.00349
3. Llorente, G., Michaely, R., Saar, G. & Wang, J. (2002), “Dynamic Volume-Return Relation of Individual Stocks,” *Review of Financial Studies* 15(4), 1005–1047. https://doi.org/10.1093/rfs/15.4.1005
4. Yao, J. & Yang, Y. (2026), “Positive feedback trading, the T+1 rule, and asymmetric return reversals in China,” *Economic Modelling* 164, 107783.
