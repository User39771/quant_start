# H5A Activity Main Effect Decomposition Audit

## Technical summary

**ACTIVITY_MULTI_FACTOR_PROXY.** The frozen H5A activity proxy is not a clean one-dimensional trading-activity measure. Across the 56 Primary signal periods, ACTIVITY_PCT has mean period Spearman correlations of **0.664** with log total market cap, **0.222** with log RAW price, **0.436** with VOL20, and **0.244** with RETURN60. This audit uses signal-time characteristics only and does not recompute or inspect state-conditioned future performance.

The safest interpretation is that AMOUNT_MEAN20/ACTIVITY_PCT is an **amount-based multi-factor proxy** whose exposure must be separated from a pure turnover or liquidity interpretation. The largest observed confound is identified below from the absolute signal-time correlations. No causal claim follows.

## Raw amount ranks encode large scale separation

ACTIVITY_PCT is the within-period average rank of AMOUNT_MEAN20, so its Spearman relationship with log amount is mechanically one. Across periods, the raw amount cross-section had a median p10 of **23,327,388**, median of **85,268,569**, and median p90 of **459,968,353** currency units. The typical period median raw amount by frozen activity state was LOW **30,587,568**, MID **85,290,990**, and HIGH **297,980,215**.

| covariate            |   LOW_ACTIVITY |   MID_ACTIVITY |   HIGH_ACTIVITY |
|:---------------------|---------------:|---------------:|----------------:|
| log_amount_mean_20   |         17.236 |         18.262 |          19.512 |
| log_raw_signal_price |          2.298 |          2.378 |           2.703 |
| log_total_market_cap |         21.887 |         22.494 |          23.413 |
| vol20                |          0.287 |          0.388 |           0.486 |

## Size is historically dated but not fully vintage-audited

Signal-date total and circulating market-cap fields are available for **100.0%** of H5A Primary members. Their status is `HISTORICAL_DATED_NOT_VINTAGE_AUDITED`: values vary by historical date, but the underlying share/effective-date lineage has not been independently audited. They are acceptable for this descriptive contamination audit, not for a claim of fully reconstructed point-in-time fundamentals or turnover.

Within size terciles, ACTIVITY_PCT retains spread; therefore activity is not exactly identical to size state. The detailed size-tercile occupancy and IQR are in `h5a_activity_characteristics.csv`.

## Price, volatility and return-state exposure remain visible

RAW signal-date close is the preferred price-level diagnostic; QFQ absolute price is also reported but its scale depends on the adjustment base. VOL20 exactly reuses the existing 21-price/20-return annualized sample-standard-deviation and flat-price reliability contract. No alternative window was calculated.

Mean period Spearman by frozen RETURN state:

| covariate            |   LOW_RETURN |   MID_RETURN |   HIGH_RETURN |
|:---------------------|-------------:|-------------:|--------------:|
| log_raw_signal_price |        0.212 |        0.163 |         0.193 |
| log_total_market_cap |        0.706 |        0.677 |         0.635 |
| return_60            |       -0.143 |        0.076 |         0.365 |
| vol20                |        0.341 |        0.373 |         0.443 |

The conditional table shows whether size, price and volatility exposure remains after restricting comparisons to LOW/MID/HIGH_RETURN. It is descriptive and is not a controlled-return regression.

## Board composition is measurable; industry evidence is sparse

Board membership is fully code-derived. The most over- and underrepresented board in each activity state is:

| activity_state   | most_under   | most_over   |
|:-----------------|:-------------|:------------|
| HIGH_ACTIVITY    | STAR         | SZ_MAIN     |
| LOW_ACTIVITY     | SZ_MAIN      | STAR        |
| MID_ACTIVITY     | SH_MAIN      | CHINEXT     |

Current SW industry labels cover only **4.0%** of Primary members and are not point-in-time. The following are the largest industries inside that mapped subset only; they must not be generalized to broader-A:

| activity_state   | category          |   weight |   weight_difference |
|:-----------------|:------------------|---------:|--------------------:|
| HIGH_ACTIVITY    | 软件开发/IT服务   |    0.024 |               0.008 |
| HIGH_ACTIVITY    | 数字媒体/文化科技 |    0.023 |               0.007 |
| HIGH_ACTIVITY    | 教育              |    0.016 |               0.006 |
| LOW_ACTIVITY     | 轨交设备/软件     |    0.032 |               0.026 |
| LOW_ACTIVITY     | 化工新材料        |    0.031 |               0.026 |
| LOW_ACTIVITY     | 军工电子/航空装备 |    0.030 |               0.020 |
| MID_ACTIVITY     | 软件开发          |    0.020 |               0.009 |
| MID_ACTIVITY     | 军工电子/航空装备 |    0.019 |               0.009 |
| MID_ACTIVITY     | 影视传媒          |    0.017 |               0.001 |

## Listing age and other unavailable controls

No reliable local listing-date table exists. `listing_age_at_signal` is therefore unavailable and was not inferred from first price appearance. The local turnover field was also excluded because its denominator lineage is unresolved. No current snapshot was backfilled into historical periods.

## Interpretation boundary

H5A established a historical_seen association between frozen activity states and future paths. This audit shows what the signal-time activity proxy co-represents; it does not ask what future-return effect survives controls. The H5A result should currently be described as an association for an amount-ranked state that also carries size, price, volatility and composition exposures—not as evidence that trading activity alone causes continuation or reversal.

## Recommended next step

The most valuable next design step is to preregister one confound-control study beginning with the largest verified signal-time exposure, while retaining the frozen H5A states and without searching alternative proxies. Do not execute that control until the student approves a separate plan. Historical size lineage and broader-A point-in-time industry/listing data remain the highest-value data-quality improvements.

## Further questions

- Can the source owner document how historical total/circulating market cap and share counts were reconstructed?
- Can broader-A historical industry effective dates and listing dates be sourced without opening prospective/final data?
- Should a later, separately approved design distinguish activity from size using a single preregistered stratification rather than iterative neutralization?

## Method and limitations

- Primary periods: `period_index=1–56`; period 0 excluded by the existing low-coverage rule.
- Frozen H5A activity membership was reconstructed with the formal H5A function and reconciled exactly to official stock counts; no state was redefined.
- All numeric summaries first use within-period cross-sections and then give each period equal weight.
- Correlations are period-level Spearman summaries; no p-values, future returns, regressions, neutralization or proxy search are used.
- Industry uses a current, incomplete 200-code mapping (`industry_point_in_time=false`).
- Current-universe survivorship bias remains.

## Audit identity

analysis_type=post_h5a_explanatory_audit; sample_role=historical_seen; causal_claim_allowed=false; alpha_claim_allowed=false; future_return_analysis_run=false; H5A_reoptimized=false; MCTS_run=false; Phase_B_run=false
