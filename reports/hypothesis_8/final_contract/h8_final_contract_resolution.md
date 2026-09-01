# H8 Final Contract Resolution

## Decision

**PROPOSED_H8_CONTRACT_STATUS=H8_NOT_READY**. Price contract remains unresolved; minimum-history counts cannot be certified before price lineage and final GARCH row validity are resolved. No Eq.9 was fitted. This is not a negative H8 research result.

## Price / corporate actions

Candidate source: **BaoStock raw OHLC**, same-source/date/convention open and close. Diagnostic QFQ source: existing canonical Sina QFQ close, never substituted into raw returns. `PRICE_CONTRACT_UNRESOLVED`; `corporate_action_detector_valid=false` (not validated). The fixed `rtol=1e-6, atol=1e-10` produces **4,709,059 ratio-change flags / 6,190,249 adjacent pairs (76.0722%)**, across 5180 overlapping stocks. These are **not certified corporate-action transition counts**; certified count=UNKNOWN. No tolerance tuning or synthetic QFQ open was used.

Overlap covers 2020-12-28 through 2026-05-12 (the extra day is an endpoint, not a later formation date). Per-stock median ratio-change share=96.6847%; median across stocks of within-stock absolute ratio-change median=8.7583402e-05. Rounded cross-vendor prices can generate ratio jitter; exact cause/authoritative adjustment factors are not established. Dense ratio flags cannot be equated to sparse dividend/split events. The CSV also shows unvalidated naive-clean counts only to expose the consequence of blindly treating these flags as events; they are not eligible H8 rows.

Conditional candidate rule, only after a reliable detector: `RAW_OHLC_WITH_CORPORATE_ACTION_TRANSITION_EXCLUSION`. Exclude both a contaminated conditioning return (t-1 to t) and a contaminated outcome endpoint (t to t+1). Missing factor lineage is unknown, not clean. P2 intraday is same-day but the matched sample shares the exclusion. No price is changed.

`RECOMMENDED_H8_ANALYSIS_START=UNRESOLVED`; prefer the corporate-action-verified start once verification exists. 2020-12-28 is currently **overlap start, not verified start**. Earliest three-date overlap formation would be 2020-12-29. `H8_FORMATION_CUTOFF=2026-05-11`; next endpoint=2026-05-12. Raw full start is not recommended merely to retain an unverified year.

## Return contract — resolved

`RETURN_DECOMPOSITION_CONTRACT=SEPARATE_SIMPLE_RETURN_EQUATIONS`.
Close-to-close = close_(t+1)/close_t - 1; overnight = open_(t+1)/close_t - 1; intraday = close_(t+1)/open_(t+1) - 1.
Exact: 1+cc=(1+out)(1+in). The additive identity and exact coefficient additivity are **not** used. Separate simple-return equations remain mandatory.

## GARCH implementation and numeric probe

arch=8.0.0; installed by this task in the existing Python environment; only arch was added to requirements. Fixed `arch_model(mean='Zero',vol='GARCH',p=1,q=1,dist='normal',rescale=False)`; fit defaults, no optimizer/distribution/model rescue. Inputs are decimal simple returns; sigma squared is decimal-return squared. Regression r is percentage points, variance interaction=(1000*sigma2_decimal)*r_pp.

Deterministic probe: 50 main-board/non-observed-ST stocks; success=50, failure=0. Selection spans SH/SZ, candidate size quartiles and history lengths, before fitting. CSV includes all selected names and failures. It uses the **longest consecutive available raw-return segment within the overlap interval through cutoff**, never bridges missing dates or fills. This is solely a package/numerical probe on uncorrected raw prices, **not a final economic GARCH path**. No return magnitudes, parameters, volatility paths, or outcome relationships are exported.

`GARCH_IMPLEMENTATION_CONTRACT=READY` (synthetic units/alignment checks); `GARCH_FINAL_SAMPLE_CONTRACT=UNRESOLVED_PRICE_LINEAGE`; `full_candidate_garch_feasible=UNKNOWN`. Full-candidate fitting was not run because the price detector has not produced a valid final price sample. Probe failures are GARCH_NUMERIC_FAILURE, never rescued. Even successful raw probes do not guarantee convergence after a future approved corporate-action treatment.

Conditional variance at t uses past residuals at fixed parameters, not a t+1 shift. Parameters and default backcast are in-sample estimated/initialized, not prospective; the synthetic no-look-ahead test fixes both parameters and backcast before perturbing later returns. Once clean-return gaps are defined, missing-day recursion must be made explicit; this task does not promote compressed or longest-segment probe chronology to a full-sample contract.

## Main-board / history comparison

Main-board stocks=3195; observed-ever-ST excluded=405; candidates before history=2790. ST exclusion uses **all currently local is_st history through 2026-08-20**, as requested, while prices/turnover and size are bounded at formation cutoff (except the one necessary next-price endpoint). 201 main-board stocks have an ST observation after cutoff. This is deliberately not lifetime-ever-ST or point-in-time selection; post-cutoff status availability is an additional historical-sample-selection limitation. No post-cutoff H8 outcome analysis is made.

The prior feasibility report excluded 403 main-board stocks using history only through formation cutoff; the current full-local-history count above has 2 additional exclusions. Stocks with post-cutoff ST are not all new exclusions: most also had earlier ST observations.

Size is the prior data-only audit's historical mean circulating cap through cutoff. Quartiles are recomputed **within current main-board/non-observed-ST candidates**, with deterministic code tie ordering; 2 missing-size stocks stay UNKNOWN and are not filled. First observed cache date is not listing date. The comparison contains exact22/current-return/next-endpoint presence, not just active OHLC history; it still cannot establish final CA-clean/GARCH-valid rows.

| basis | min_rows | stock_count | share_of_main_board_candidate | median_nobs | SH_MAIN | SZ_MAIN | size_quartile_inclusion_spread |
|---|---|---|---|---|---|---|---|
| RAW_FULL_UPPER_BOUND | 750 | 2668 | 0.956272 | 1514 | 1448 | 1220 | 0.143472 |
| RAW_FULL_UPPER_BOUND | 1000 | 2601 | 0.932258 | 1514 | 1419 | 1182 | 0.219512 |
| RAW_FULL_UPPER_BOUND | 1250 | 2481 | 0.889247 | 1514 | 1332 | 1149 | 0.305595 |
| RAW_FULL_UPPER_BOUND | 1500 | 1822 | 0.653047 | 1514 | 972 | 850 | 0.362984 |
| OVERLAP_UPPER_BOUND | 750 | 2668 | 0.956272 | 1296 | 1448 | 1220 | 0.143472 |
| OVERLAP_UPPER_BOUND | 1000 | 2601 | 0.932258 | 1296 | 1419 | 1182 | 0.219512 |
| OVERLAP_UPPER_BOUND | 1250 | 2366 | 0.848029 | 1296 | 1263 | 1103 | 0.3099 |
| OVERLAP_UPPER_BOUND | 1500 | 0 | 0 | nan | 0 | 0 | 0 |
| FINAL_POTENTIAL_H8_ROWS | 750 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| FINAL_POTENTIAL_H8_ROWS | 1000 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| FINAL_POTENTIAL_H8_ROWS | 1250 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |
| FINAL_POTENTIAL_H8_ROWS | 1500 | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN | UNKNOWN |

RAW_FULL and OVERLAP are **upper bounds only**, not recommendations, Primary eligibility counts, or interchangeable with final potential H8 rows. Detailed p10/p90, quartile inclusion, size means/medians, observed-history/start-date distributions and Spearman(rows,log_size) are in the CSV. The Spearman field uses the retained subset for each threshold; the separately named candidate-pool field uses the entire pre-threshold candidate pool. These correlations concern sample selection only. Final valid_H8_rows/log_size correlation=UNKNOWN.

The overlap-start 1500-row candidate already has zero stocks before exclusions; its zero inclusion-rate spread means an empty sample, not absence of selection bias. Increasing the nonempty overlap threshold from 750 to 1250 raises the largest-minus-smallest quartile inclusion-rate spread; this is size/history selection evidence, not an H8 effect or a reason to optimize a threshold.

Candidate raw P1/P2 presence rows=3959781/3959781; overlap P1/P2 presence rows=3445647/3445647. Matching is provisionally recommended from endpoint presence parity, not certified final row parity. `RECOMMENDED_PRIMARY_MIN_ROWS=HUMAN_JUDGMENT`; long-history sensitivity=UNRESOLVED; no inherited H7 750 rule. Four final thresholds are UNKNOWN, not zero; final threshold freeze is blocked by the price/GARCH lineage gap.

## Retained design and scope

H7_role=PHENOMENON_DIAGNOSTIC; H8_role=MECHANISM_REPLICATION_DIAGNOSTIC; STOCK_LEVEL_ADAPTED_REPLICATION; P1_SIGN=NOT_READY; P2_TIMING=NOT_READY; P3_INSTITUTION=NOT_FEASIBLE.

Turnover is BAOSTOCK_CIRCULATING_TURNOVER, exact prior 22 common-market days, all active positive finite; t excluded. V=max(log(turn_t)-prior22_log_mean,0), retaining V=0. D_NEG=r<0; D_POS=r>=0, retaining zero. Five conditioning-day weekday slopes and no extra standalone r. Only synthetic Eq.9 schema was constructed, see companion Markdown.

Price-limit robustness=UNAVAILABLE_IN_V1; available=false; blocks_primary=false. It weakens institutional mechanism discrimination, not the reason for today's block. No H-share/index/limit downloads or surrogate inference.

## Boundaries / next step

H7 metadata unchanged=True; H7 not imported, modified, or rerun. H8_results_opened=false; gamma31_estimated=false; gamma32_estimated=false; Eq9_real_data_fit=false; future_performance_selection=false; H5/H6/MCTS/Phase_B_run=false; strategy_backtest_run=false.

Next: human review of **reliable corporate-action lineage** before freezing analysis start or minimum history. Do not reinterpret dense ratio jitter as corporate-action events, relax tolerances, run a different GARCH model, or open H8 results. A future authorized source/lineage resolution is needed; this task downloads no market data and stops here. Data-quality skill kept flags separate from verified events; minimal-implementation skill avoided a new governance framework or full GARCH pass on an invalid price contract.
