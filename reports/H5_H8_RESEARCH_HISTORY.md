# H5–H8 Research History

## Executive summary

H5–H8 form one methodological sequence rather than four unrelated experiments. H5 showed that a stable past-return × activity-state pattern could coexist with a contaminated activity measure. H6 improved the comparison by defining abnormal activity relative to each stock's own history, but alternative explanations remained. H7 upgraded both the turnover data and the model, converting a broad “high activity followed by weakness” observation into a more precise dynamic relation: higher relative turnover usually weakened continuation, but generally did not reverse its sign. H8 then moved away from extending the project's own patterns and used externally supplied sign and timing predictions in a stock-level adapted replication. Its overall sign prediction did not replicate, while its timing prediction was directionally consistent with the source paper.

The sequence therefore moved from discovering patterns to distinguishing **measurement**, **empirical phenomenon**, **economic mechanism**, and **replication**. All results below are historical-seen, descriptive or mechanism-diagnostic evidence. None is an Alpha, strategy, out-of-sample, execution, or causal result.

## H5 — Testing whether a literature-inspired activity effect survives better measurement

### Source / motivation

H5 was inspired by Lee and Swaminathan (2000), “Price Momentum and Trading Volume.” It asked whether past-return state and trading-activity state jointly corresponded to different future continuation/reversal paths. The local study was literature-inspired, not a replication.

### Frozen design

H5A used 56 Primary periods (`period_index=1–56`). `RETURN60` and the activity measure were formed at signal time. The activity variable was `AMOUNT_MEAN_20`: the arithmetic mean of positive, finite amount observations over the 20 exact CSI 300 market dates ending on the signal date, with no filling. Stocks were sorted deterministically within each period into LOW/MID/HIGH return and activity states. Outcomes were nested 20D, 60D, and 120D cumulative returns.

The within-return-state contrast was HIGH_ACTIVITY minus LOW_ACTIVITY. For LOW/HIGH_RETURN it was expressed in continuation-aligned returns; MID_RETURN was retained as a raw-return main-effect diagnostic. Signal membership was frozen before outcomes, periods were equally weighted, and the prespecified stability checks used a six-period circular moving-block bootstrap.

### Main result

H5A classified the diagnostic as `H5A_DIAGNOSTICALLY_SUPPORTED`: all six LOW/HIGH_RETURN activity-horizon contrasts passed its frozen stability rule. On the HIGH_RETURN side, the 20D, 60D, and 120D contrasts were respectively **−0.020565, −0.055964, and −0.096672** (about −2.06, −5.60, and −9.67 percentage points). High-activity past winners therefore showed materially weaker continuation than low-activity past winners in this historical sample.

### Measurement complication

The signal-time audit showed that `ACTIVITY_PCT` was strongly related to firm scale: its mean period-level Spearman correlation with log total market capitalization was **+0.664**. Its corresponding correlation with `VOL20` was **+0.436**, and the measure also carried price, return-state, and board-composition exposures. Coarse size stratification retained the original sign in 9/9 return-state/horizon comparisons, but retained a median of only **47.4%** of absolute contrast magnitude and left substantial within-stratum size imbalance. The result was heterogeneous: the HIGH_RETURN contrast retained 98.7%, 92.7%, and 82.2% at 20D/60D/120D, while LOW_RETURN and MID_RETURN attenuated much more. A separate VOL20-only diagnostic retained a median **95.0%** of magnitude, but substantial size imbalance remained. These checks showed that H5A was an amount-ranked multi-exposure state, not a clean volume construct; they did not show that H5A was entirely a size effect.

H5B therefore replaced amount level with the single frozen value-turnover proxy

\[
VT20\_DAILY_{i,s}=\operatorname{mean}_{t\in 20\text{ dates}}\left(\frac{Amount_{i,t}}{TotalMarketCap_{i,t}}\right).
\]

This is only a turnover-like/value-turnover proxy: approximately `(VWAP / Close) × (shares traded / shares outstanding)`, not true turnover. The H5B preregistration prohibited alternative windows, denominators, residualization, neutralization, or a proxy tournament.

H5B completed all 56 periods, agreed in direction with H5A in **7/9** fixed comparisons, and used 262,589 VT20-valid stock-periods versus 262,636 H5A signal-ready observations. Its HIGH_RETURN contrasts were **−0.002854, −0.009781, and −0.017912** at 20D/60D/120D, only **13.9%, 17.5%, and 18.5%** of the corresponding H5A magnitudes. All six LOW/HIGH_RETURN H5B 90% descriptive intervals included zero. VT20 reduced but did not remove size exposure: its mean period-level Spearman correlation with log market capitalization was **−0.267**; its correlation with `VOL20` rose to **+0.671**.

### Interpretation

H5 provides stronger evidence for the existence of a stable historical past-return × amount-state pattern than for a clean trading-volume mechanism. The more turnover-like fixed measurement preserved much of the directional ordering but greatly weakened the magnitudes, and it introduced its own small-stock and volatility tilts. H5 neither replicated the source paper nor proved a volume mechanism.

### Why the study stopped / moved to H6

The project did not search across VT windows, denominators, residualized activity, or further proxies after seeing H5A and H5B. H6 instead changed the question from cross-sectional activity level to abnormal activity relative to each stock's own history, reducing direct scale contamination without reopening a proxy search.

### Research lesson

Stable empirical patterns do not guarantee a correct economic interpretation. A poorly isolated measurement can produce apparently clean and persistent results while combining several exposures.

## H6 — From cross-sectional activity levels to own-history abnormal activity

### Source / motivation

H6 was inspired by Gervais, Kaniel, and Mingelgrin (2001), “The High-Volume Return Premium,” and by the measurement problem exposed in H5. It was an adapted mechanism diagnostic using amount rather than the source study's share-volume construct, not an exact replication.

### Frozen design

For each formation date, H6 ranked that stock's current daily amount within the exact 50-market-day window from `t−49` through `t`, inclusive. The date-neutral midrank was

\[
midrank=n_{less}+(n_{equal}+1)/2.
\]

`LOW_SHOCK` was `midrank ≤ 5`, `HIGH_SHOCK` was `midrank ≥ 46`, and the remaining ranks were `NORMAL`; zero amount was retained. The inherited H5 `RETURN_STATE` was not reassigned. Primary periods were 3–56 (54 periods); periods 1–2 were early-history diagnostics only. The Primary horizon was 20D, with nested 5D and 10D paths as descriptive secondary horizons. Future returns began at the close of the next CSI 300 market date, avoiding same-close entry.

### Main result

The Primary raw-return contrast was HIGH_SHOCK minus LOW_SHOCK. At 20D its period-equal mean was **−0.008726** for LOW_RETURN, **−0.007997** for MID_RETURN, and **−0.023781** for HIGH_RETURN (about −0.873, −0.800, and −2.378 percentage points). The corresponding 90% descriptive intervals were all below zero. Thus unusually high amount was followed by weaker returns across all three inherited past-return states, with the largest weakness among past winners.

### Measurement complication

The fixed market-normalized-amount robustness preserved the sign in 9/9 state × horizon comparisons. At 20D its LOW/MID/HIGH_RETURN contrasts were about **−1.054, −0.974, and −2.365 percentage points**, each using all 54 Primary periods. This weakens the simple explanation that the result came only from an unnormalized marketwide amount shock, but it does not identify a mechanism.

The fixed formation-return Middle40 diagnostic suffered severe sample loss: its 20D LOW/MID/HIGH contrasts used only **5, 15, and 33** periods. LOW and MID intervals crossed zero; HIGH remained negative at about 79.8% of the Primary magnitude. The local-trend diagnostic also found `|rho| ≥ 0.50` in **31.26%** of HIGH_SHOCK and **44.23%** of LOW_SHOCK observations. Formation-day return and slow local trend therefore remained material alternative explanations.

### Interpretation

Defining activity against a stock's own history produced a cleaner negative abnormal-activity association than H5B, especially among past winners. It improved measurement but did not establish that abnormal activity, attention, or any other mechanism caused underperformance. It was not an Alpha or execution result and did not reproduce the source paper's positive high-volume premium.

### Why the study stopped / moved to H7

Searching other history windows, z-scores, ratios, detrending, or residualized activity measures would have reopened specification search. The next useful step required both a better turnover measure and a more structured dynamic return–activity model, motivating H7.

### Research lesson

A more plausible measurement can improve a design, but orderly results cannot become a mechanism conclusion while important alternative explanations remain unidentified.

## H7 — Upgrading both turnover measurement and the dynamic return–activity model

### Source / motivation

H7 was inspired by Llorente, Michaely, Saar, and Wang (2002), “Dynamic Volume-Return Relation of Individual Stocks.” It made two changes at once: an explicit turnover denominator with dated share lineage, and an individual-stock dynamic regression. It was D05-inspired, not an exact replication.

### Frozen design

Primary `TOTAL_SHARE_TURNOVER` was **BaoStock volume in shares divided by CNINFO point-in-time total shares**. CNINFO share events were aligned at `max(change_date, announcement_date)`; the pre-first-event interval was not backfilled from future information. The secondary measurement was BaoStock circulating-share turnover on exact matched rows. Known lineage exceptions were retained as limitations rather than silently filled with market-cap-implied shares or other denominators.

For each active formation observation, H7 defined `LOG_TURNOVER = ln(TOTAL_SHARE_TURNOVER)` and

\[
V_{i,t}=LOG\_TURNOVER_{i,t}-\operatorname{mean}(LOG\_TURNOVER_{i,t-1},\ldots,LOG\_TURNOVER_{i,t-200}),
\]

where the baseline was the stock's last 200 strictly prior active, positive, finite turnover observations. Suspended formation rows were invalid rather than converted to zero; formation observations with `isST=1` were excluded. The Primary stock-level 1D equation was

\[
R_{i,t+1}=C0_i+C1_iR_{i,t}+C2_i(V_{i,t}R_{i,t})+\varepsilon_{i,t+1}.
\]

The Primary required at least 750 valid rows; a nested 1,000-row subset, 2D/5D horizons, matched secondary turnover, and size diagnostics were frozen robustness analyses.

### Main result

The Primary contained **4,470** stocks and had no numerical regression failures. The cross-sectional C2 distribution had mean **−0.017355**, median **−0.017805**, and **61.745%** negative values. Higher relative turnover therefore usually shifted the conditional return slope in a more negative direction.

The effective slope `C1 + C2·V` nevertheless generally remained positive. At each stock's V p10, p50, and p90, the cross-sectional median effective slopes were **0.056104, 0.043942, and 0.028045**, with positive shares of **74.79%, 80.07%, and 71.48%**. Thus higher activity usually weakened continuation; it did not generally imply outright reversal.

The nested 1,000-row sample contained 3,944 stocks and preserved the same stored coefficients for overlapping stocks. On exact matched rows, Primary total-share and secondary circulating-share implementations produced C2 correlation **0.984301** and sign agreement **0.969128**; their means were −0.017355 and −0.017389.

### Measurement complication

The size diagnostic ran on 4,467 stocks. C2 means were **−0.024584, −0.024578, −0.018781, and −0.001480** from Q1_SMALL through Q4_LARGE. Spearman(C2, size) was **+0.139302**, and the standardized-size slope was **+0.009466** (90% CI +0.007841 to +0.011091). The preregistered source-consistent size direction was negative, so the observed positive relation did not cleanly support the paper's proposed private-information/risk-sharing interpretation. Size is not a pure information-asymmetry measure in any case.

The 2D and 5D C2 medians were **−0.044335** and **−0.078040**, with correlations of 0.803 and 0.546 and sign agreement of 0.798 and 0.717 relative to 1D. This shows persistence across the fixed horizons, not exclusion of microstructure or causal validation.

### Interpretation

H7 sharpened the empirical phenomenon: relative turnover was associated with weaker short-run return continuation, while continuation usually remained positive even at high activity. A negative C2 did not establish that turnover caused reversal or validate the source paper's private-information/risk-sharing mechanism.

### Why the study stopped / moved to H8

The dynamic relation was sufficiently clear for the approved research purpose. Further turnover definitions, history lengths, interactions, horizons, or residualization would expand researcher degrees of freedom. H8 therefore moved to an independent literature-derived test with explicit externally supplied predictions.

### Research lesson

Better data and a more structured model can turn a vague “high volume followed by weakness” observation into a precise dynamic relation. That precision still does not convert an empirical phenomenon into proof of an economic mechanism.

## H8 — From mechanism speculation to prediction-based adapted replication

### Source / motivation

H8 used Yao and Yang (2026), “Positive feedback trading, the T+1 rule, and asymmetric return reversals in China,” *Economic Modelling* 164, 107783. Its frozen official label was `STOCK_LEVEL_ADAPTED_REPLICATION` within a `MECHANISM_REPLICATION_DIAGNOSTIC`. The paper's Primary was index-level; the local Primary adapted its stock-level Eq. 9 because the required four-index aggregate turnover was unavailable. H8 was neither an exact/full replication, H7 robustness, nor causal identification of T+1 behavior.

### Frozen design

P1 (SIGN) predicted `gamma31 < 0`, economically weaker `gamma32`, and

\[
DELTA\_GAMMA=gamma31-gamma32<0.
\]

`gamma31` and `gamma32` were the negative- and nonnegative-conditioning-return cubic interactions in the frozen 11-column stock-level Eq. 9. P2 (TIMING) used identical stocks, conditioning dates, rows, and X matrices while changing only the dependent variable:

\[
r^{CC}_{t+1}=close_{t+1}/close_t-1,\quad
r^{OUT}_{t+1}=open_{t+1}/close_t-1,\quad
r^{IN}_{t+1}=close_{t+1}/open_{t+1}-1.
\]

Its adapted prediction was `TIMING_CONTRAST = DELTA_IN − DELTA_OUT < 0`. The design used BaoStock raw OHLC, circulating turnover, explicit corporate-action row exclusions, an exact-prior-22 turnover transform, a zero-mean normal GARCH(1,1), and the longest corporate-action-clean segment. The Primary threshold was 750 rows; 1,000 rows defined a nested sensitivity.

### Main result

The Primary contained **474** stocks. All three components fit successfully for every stock (**1,422** fits; no numerical failures).

P1 did not replicate overall. Close-to-close median `gamma31` was **+0.002017**, median `gamma32` was **+0.001789**, and median `DELTA_GAMMA` was **+0.000439**; only **40.93%** of deltas were negative. The joint frozen negative sign structure was therefore absent in the full Primary sample.

P2 was directionally consistent with the source prediction. Median overnight `DELTA_GAMMA` was **+0.000815**, median intraday delta was **−0.000340**, and median intraday-minus-overnight timing contrast was **−0.001055**. The timing contrast was negative for **67.93%** of stocks. The nested 312-stock long-history sensitivity was similar: median timing contrast **−0.001041** with **69.23%** negative, while its close-to-close median delta remained positive at **+0.000481**.

### Measurement complication

The sample was strongly selected toward stocks with fewer observed corporate actions and longer uninterrupted histories; the paper's institutional T+1-versus-T+0 comparison and price-limit robustness were unavailable. The local period was 2020–2026 rather than 2002–2021, and the paper's 2,400-day individual-history condition could not be reproduced. Stock-level coefficient noise, cross-sectional dependence, current-universe survivorship, in-sample GARCH, and turnover-denominator approximation remain material limitations.

Secondary size evidence was heterogeneous. Close-to-close delta medians were positive in Q1–Q3 (**+0.001548, +0.000845, +0.000697**) and negative in Q4–Q5 (**−0.000182, −0.001426**). This was a prespecified descriptive paper comparison, not a replacement for the full-sample P1 result.

### Interpretation

H8 is a **mixed / partial replication**. Its overall sign prediction did not match the source-paper prediction, while the timing decomposition displayed the predicted direction. Timing consistency does not override the failed sign prediction, and neither component proves a T+1 mechanism, positive-feedback trading, Alpha, or a strategy.

### Why the study stopped

The mixed evidence was retained as mixed. The project did not search new subgroups, timing definitions, interactions, or specifications to make the local data resemble the paper more closely. Questions raised by the result may inform later literature work, but they do not retroactively change H8.

### Research lesson

Valuable literature-driven research turns published theory into prespecified, falsifiable predictions and accepts that one experiment may contain both supporting and opposing evidence. The purpose is not to make local data support a paper, but to sustain a literature → prediction → experiment → new-question loop.

## H5–H8 methodological progression

| Stage | Main question | Key methodological change | Main result | What remained unresolved | Why next stage followed |
|---|---|---|---|---|---|
| H5 | Do past-return and activity states distinguish future paths? | Tested raw amount, then one fixed turnover-like proxy | Stable H5A pattern; much smaller H5B magnitudes | Activity measurement mixed size, volatility, and other exposures | Move from cross-sectional level to own-history abnormality |
| H6 | Is a stock unusually active relative to itself? | Exact 50-day own-history rank | Negative HIGH_SHOCK−LOW_SHOCK relation, strongest for winners | Formation return, trend, and other alternatives | Obtain explicit turnover lineage and a dynamic model |
| H7 | How does relative turnover change return continuation? | Point-in-time total-share turnover plus stock-level regression | C2 generally negative, but effective slopes generally positive | Private-information/risk-sharing mechanism not identified | Use independent literature predictions rather than extend H7 |
| H8 | Do externally specified sign and timing predictions replicate? | Prediction-based stock-level adapted replication | Overall sign failed; timing direction matched | Causal T+1 mechanism and unavailable institutional tests | Retain mixed evidence without specification search |

## Verification notes

1. The H7 final report describes the 2D/5D result as “attenuation.” The reported raw C2 magnitudes actually become more negative: medians are −0.017805 at 1D, −0.044335 at 2D, and −0.078040 at 5D. This archive uses the neutral factual wording “persistence across fixed horizons.” The frozen report and outputs were not changed. This is a wording correction, not a change to the approved H7 conclusion.
2. H5 source files use both `AMOUNT_MEAN_20` and the display spelling `AMOUNT_MEAN20`. This archive uses the preregistration's canonical `AMOUNT_MEAN_20`; they refer to the same frozen construct.
3. Rounded percentages in prose are derived directly from the final reports' decimal values. No model, bootstrap, regression, or outcome was recomputed.

## Source map

The archive used the following 15 local files:

| Stage | Source type | Local file | Role |
|---|---|---|---|
| Shared | Research history | `docs/research_progress_h5_h8.md` | Sequence, literature identities, shared limitations |
| H5A | Preregistration | `reports/hypothesis_5a/h5a_preregistration_and_implementation_plan.md` | Frozen variables, periods, contrasts, stopping rule |
| H5A | Final report | `reports/hypothesis_5a/h5a_diagnostic_report.md` | Main paths, contrasts, classification |
| H5A | Final diagnostic | `reports/hypothesis_5a/h5a_size_control_diagnostic.md` | Size contamination and retained magnitudes |
| H5A | Final diagnostic | `reports/hypothesis_5a/h5a_vol20_control_diagnostic.md` | VOL20 control and residual size exposure |
| H5A/H5B | Measurement audit | `reports/hypothesis_5a/turnover_like_proxy_feasibility_audit.md` | Amount/VT20 size, volatility, and price exposure comparison |
| H5B | Preregistration | `reports/hypothesis_5b/h5b_vt20_preregistration.md` | VT20 definition, fixed comparison, prohibited searches |
| H5B | Final report | `reports/hypothesis_5b/h5b_diagnostic_report.md` | Direction agreement and attenuated magnitudes |
| H6 | Preregistration | `reports/hypothesis_6/h6_daily_amount_preregistration.md` | Own-history rank, cutoffs, horizons, robustness rules |
| H6 | Final report | `reports/hypothesis_6/h6_diagnostic_report.md` | Primary contrasts, robustness, trend limitation |
| H7 | Source audit | `reports/hypothesis_7/source_probe/h7_turnover_source_probe_report.md` | BaoStock/CNINFO measurement and date-alignment lineage |
| H7 | Preregistration | `reports/hypothesis_7/h7_dynamic_volume_return_preregistration_v1.md` | Frozen turnover, baseline, equation, samples, diagnostics |
| H7 | Final report | `reports/hypothesis_7/h7_dynamic_volume_return_report_v1.md` | C2, effective slopes, robustness, size results |
| H8 | Preregistration | `reports/hypothesis_8/h8_preregistration_v1.md` | Adaptation, P1/P2 predictions, formulas, fixed sample |
| H8 | Final report | `reports/hypothesis_8/h8_report_v1.md` | Sign, timing, long-history, and size results |

## Archival validation

No H5–H8 analysis was rerun; no data or paper was fetched; no experiment output, frozen input, or result was changed. Every important numerical claim above is traceable to the listed local sources. The four conclusions preserve the approved wording boundaries, retain negative and mixed evidence, and maintain the approved H5 → H8 methodological progression.
