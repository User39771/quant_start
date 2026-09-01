# H5B VT20_DAILY Historical-Seen Descriptive Diagnostic — Preregistration Draft

## 1. Research identity and provenance

```text
analysis_stage=H5B_signal_construction_and_preregistration
sample_role=historical_seen
derived_hypothesis=true
future_outcome_access_allowed=false
alpha_claim_allowed=false
oos_claim_allowed=false
causal_claim_allowed=false
```

H5B asks whether the H5A past-return × activity path changes when raw `AMOUNT_MEAN20` activity is replaced by a value-turnover proxy with a closer economic relationship to shares turnover. The question was formed after H5A, its size and VOL20 control diagnostics, and the turnover-like feasibility audit were viewed. H5B is therefore a **derived historical-seen mechanism diagnostic**, not independent validation, OOS evidence or a final test.

This document freezes the future diagnostic before any H5B outcome is read or calculated. Signal construction alone does not approve execution.

## 2. Fixed signal and unit contract

For stock *i* and signal date *s*:

```text
VT20_DAILY(i,s) = mean_t[Amount(i,t) / TotalMarketCap(i,t)]
```

The set of *t* is exactly the signal date and the preceding 19 CSI300 market dates. All 20 amount and denominator observations must be positive and finite. Missing dates invalidate the stock-period; there is no forward fill, backfill, earlier-date substitution or use of post-signal data.

The units remain:

```text
Amount=CNY_INFERRED_NOT_SOURCE_CERTIFIED
TotalMarketCap=CNY_INFERRED_NOT_SOURCE_CERTIFIED
conversion=1.0/1.0
VT20_DAILY=dimensionless
```

`Amount / TotalMarketCap ≈ (VWAP / Close) × (SharesTraded / SharesOutstanding)`. Consequently, VT20 is called a **value-turnover proxy** or **turnover-like activity proxy**, never true turnover, pure turnover, D03 turnover or an independent Alpha.

No VT10/40/60, float-market-cap denominator, signal-date denominator approximation, vendor turnover, residualized proxy or alternative proxy is part of H5B.

## 3. Frozen signal sample and states

- Primary periods are `period_index=1–56`.
- Membership is the formal H5A signal-ready membership; the universe is not rebuilt.
- `RETURN60` and `RETURN_STATE` are inherited from the formal H5A implementation without changing lookback, orientation, grouping or universe.
- Within each period, stocks that are H5A signal-ready and have valid VT20 are sorted by `(VT20_DAILY ascending, stock_code ascending)` and divided into deterministic near-equal `LOW_VT`, `MID_VT`, `HIGH_VT` groups.
- `VT20_PERCENTILE` is descriptive average-rank percentile only; ordinal ordering determines state membership and stock code resolves ties.
- The fixed Primary grid is `RETURN_STATE × VT20_STATE`, or 3×3.

Before outcome execution, all 56 periods must be present, RETURN_STATE must reconcile exactly to H5A, and coverage plus every 3×3 cell's median, minimum and p10 membership must be reported. Any mismatch is blocking.

### Signal construction evidence available at preregistration

The formal signal panel contains 262,636 H5A signal-ready stock-periods and no duplicate `(period_index, stock_code)` keys. VT20 is valid for 262,589 observations. Across 56 Primary periods, median coverage is 99.9799%, minimum coverage is 99.9529% and p10 coverage is 99.9565%. Across all 504 period × 3×3 cells, median membership is 506, minimum membership is 89 and p10 membership is 298.3. RETURN_STATE reconciles exactly to the H5A implementation. These are signal-time construction facts only.

## 4. Named signal-time limitations

The construction audit must retain period-level Spearman summaries for VT20 versus log total market cap, VOL20, raw signal price and RETURN60, plus VT20–size and VT20–VOL20 within each RETURN_STATE.

Known pre-execution characteristics are approximately:

- size: `-0.267`, versus old amount activity `+0.664`;
- VOL20: `+0.671`, versus old amount activity `+0.436`;
- raw price: `+0.025`;
- RETURN60: `+0.284`.

Thus HIGH_VT is tilted toward smaller and more volatile stocks. Size contamination is reduced but not removed, while volatility exposure is stronger. No size/VOL matching, neutralization, residualization or double-control is permitted in H5B. Historical market cap is dated and time-varying but remains `HISTORICAL_DATED_NOT_VINTAGE_AUDITED`; the current-universe sample also retains survivorship bias.

The formal panel reconciliation gives the following mean period-level Spearman correlations:

| Scope | VT20 vs log total market cap | VT20 vs VOL20 |
|---|---:|---:|
| Overall | -0.2671 | 0.6710 |
| LOW_RETURN | -0.2690 | 0.5681 |
| MID_RETURN | -0.3074 | 0.6209 |
| HIGH_RETURN | -0.2729 | 0.6564 |

Overall VT20 correlations are 0.0246 with log raw signal price and 0.2844 with RETURN60. The same size and volatility limitations are therefore visible within every RETURN_STATE, rather than arising solely from mixing return groups.

## 5. Preregistered research question

Primary question:

> When fixed VT20_DAILY replaces the AMOUNT_MEAN20-derived activity state, do past-return state × activity state groups still display different nested 20D→60D→120D continuation/reversal paths?

Derived secondary question:

> Is the previously observed HIGH_RETURN winner-side pattern still visible under VT20 states?

All LOW_RETURN, MID_RETURN and HIGH_RETURN states must be reported. The known winner-side result cannot justify selective reporting.

## 6. Frozen future timing and outcome contract

If separately approved, H5B will reuse H5A's exact 20D, 60D and 120D nested cumulative future returns from rebalance close. It will not search another horizon or redefine endpoint, price, missing-data or no-look-ahead rules.

Continuation-aligned returns remain:

- HIGH_RETURN: `C_h = future_return_h`;
- LOW_RETURN: `C_h = -future_return_h`;
- MID_RETURN: use raw future return.

These horizons identify only a **coarse first observed reversal horizon**. A sign change between two cumulative endpoints cannot identify an exact reversal date.

For every `period × RETURN_STATE × VT20_STATE × horizon`, signal membership is fixed before the future outcome is loaded and never changes afterward. A cell is outcome-valid only when its fixed signal membership is at least 25 stocks and at least 80% of those members have valid future outcomes for that horizon. Future missingness must not change signal states, remove members from the frozen membership list, trigger reassignment, or cause the remaining stocks to be re-ranked. A period-level `HIGH_VT − LOW_VT` contrast exists only when both fixed-side cells are outcome-valid under these rules.

## 7. Fixed contrasts and complete reporting

Within the same RETURN_STATE, the fixed comparison is `HIGH_VT − LOW_VT`:

- LOW_RETURN and HIGH_RETURN: `G_h = C_HIGH_VT,h − C_LOW_VT,h`;
- MID_RETURN: `D_h = R_HIGH_VT,h − R_LOW_VT,h`.

MID_VT is retained to assess LOW/MID/HIGH ordering. HIGH-vs-MID or MID-vs-LOW may be displayed but cannot replace the Primary contrast after results are seen.

The Primary cell return at every period, state and horizon is the **arithmetic mean** of valid member returns within the fixed cell, subject to the membership and 80% coverage contract above. Every Primary period contrast, coarse path classification and cross-period interpretation uses these cell arithmetic means. Cell medians may be reported only as descriptive distribution summaries; they do not enter the Primary contrast, path classification or final interpretation.

The H5A/H5B comparison table is frozen as:

| Return state | Horizon | H5A Amount contrast | H5B VT20 contrast | Direction same? | Magnitude ratio |
|---|---:|---:|---:|---|---:|

Magnitude ratio is descriptive and has no mechanical success threshold. This table asks how a historical pattern changes under a more turnover-like proxy; it is not a proxy tournament or an outperformance test.

The `H5A Amount contrast` column must be read directly from the existing formal H5A summary artifact. It must not be recomputed on the H5B-valid subset or otherwise restricted to stocks with valid VT20. The very small difference between formal H5A membership and VT20-valid H5B coverage must be disclosed as a comparison limitation.

## 8. Frozen statistical description

H5B reuses the H5A statistical contract:

```text
cross_period_weighting=equal_period_weight
moving_block_length=6
bootstrap_repetitions=10000
bootstrap_seed=20260721
bootstrap_interval=90_percent_descriptive
minimum_valid_period_contrasts=45/56
direction_consistency_threshold=60_percent
leave_one_period_out_same_sign_threshold=80_percent
```

For each state and horizon, report mean, median, direction consistency and leave-one-period-out sign consistency. The moving-block interval is descriptive uncertainty/stability evidence, not family-wise-error-controlled, Alpha or OOS significance. No new multiple-testing system or H5A acceptance gate is introduced.

## 9. Path and final descriptive categories

Each state retains the coarse path labels:

- `CONTINUATION_PERSISTS`
- `ATTENUATES`
- `REVERSAL_OBSERVED`
- `NO_CLEAR_PATH`

After the runner has produced the fixed descriptive outputs, a human reviewer may assign exactly one of:

- `PATTERN_LARGELY_PRESERVED`: winner/loser directions broadly remain and multiple horizons retain visible gradients;
- `PATTERN_PARTIALLY_PRESERVED`: the pattern remains only on some sides/horizons or is materially weaker;
- `PATTERN_NOT_PRESERVED`: the prior pattern disappears or reverses under VT20;
- `INCONCLUSIVE`: timing, state, coverage or essential QA prevents interpretation.

These are human interpretation categories, not algorithmic acceptance rules or independent statistical validation. The runner must not assign them from the qualitative wording above. It reports only:

- six LOW_RETURN/HIGH_RETURN Primary contrasts: two return states × three horizons;
- three MID_RETURN contrasts: one return state × three horizons;
- the count whose direction matches the directly read formal H5A contrast;
- the descriptive magnitude ratio;
- moving-block bootstrap, direction-consistency and leave-one-period-out descriptions.

The final interpretation is performed by the human reviewer. A data or QA failure may be reported factually, but the runner does not convert the results into `PATTERN_LARGELY_PRESERVED`, `PATTERN_PARTIALLY_PRESERVED`, `PATTERN_NOT_PRESERVED` or `INCONCLUSIVE`.

## 10. Interpretation fixed before outcomes

- If largely preserved, conclude only that the H5A pattern is not entirely a raw-amount/size mechanical result and a more turnover-like state carries a similar historical pattern. Size and VOL20 confounding remain.
- If materially weaker, conclude that a substantial portion of H5A depended on the multi-factor exposures in raw amount.
- If absent or reversed, conclude that the H5A activity-mechanism interpretation is not robust to the fixed turnover-like proxy and may reflect size, volatility or other raw-amount components.

All three outcomes are acceptable. None authorizes an Alpha, strategy, causal, OOS or final-test claim.

## 11. Execution and stop boundary

This draft plus the signal panel must receive human approval before any H5B outcome file is read or calculated. A future approved runner must stop after the fixed H5B diagnostic and must not automatically test another proxy, lookback, neutralization, MCTS, Phase B, prospective data or final-test data.

Current status:

```text
future_return_accessed=false
H5B_performance_run=false
alternative_proxy_tested=false
network_download_performed=false
MCTS_run=false
Phase_B_run=false
human_approval_required_before_execution=true
```
