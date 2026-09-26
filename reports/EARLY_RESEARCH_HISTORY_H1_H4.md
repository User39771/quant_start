# Early Research History: H1–H4 and Pre-H5 Development

This archive reconstructs the early project sequence from local records. It records what was attempted and how the recorded evidence was classified; it does not reassess the hypotheses, upgrade historical evidence to out-of-sample evidence, or choose a final-project narrative.

## Executive timeline

| Approximate order | Stage | Recovered evidence identity | What changed next |
|---|---|---|---|
| 2026-06-18 | Market-data realism audit | Read-only data audit | Established that the original cache lacked verified adjusted returns and historical universe membership. |
| 2026-06-28 | AI / commercial-space concept universe | Current-snapshot taxonomy and candidate-universe construction | Eastmoney concept boards reached through AkShare produced a broad, noisy candidate set; business materiality had to be reviewed separately. |
| 2026-07-02 to 2026-07-05 | Stock-pool v1, v1.1, v1.2 | Versioned rule and evidence audits | The pool moved from 113 code-theme rows to a v1.2 split of 1 default, 56 expanded, and 56 excluded rows; the research universe deduplicated to 56 codes. |
| 2026-07-05 to 2026-07-11 | Smoke, qfq, adjusted panel, and research baseline | Smoke-only, then adjusted-return research baseline | Raw/unverified close results were replaced by qfq-based research returns, a CSI 300 market calendar, 20-market-day periods, benchmarks, and explicit continuity rules. |
| v1.3 | H1 — MOM60 Factor Research | Completed and frozen `not_supported`; historical current-universe research | Negative MOM40/60/80 results stopped the positive momentum direction and made VOL20 / Liquidity20 the next audited candidates. |
| v1.4 to locked-grid v1.5 | H2 — LOWVOL20 Factor Research | Historical directional support; later frozen research artifact | LOWVOL20 showed positive ranking information and lower risk, but not clean OOS confirmation or execution readiness. A prospective protocol and a long-only prototype were then frozen. |
| v1.5.1 maintenance | LOWVOL20 freeze and maintenance | Frozen artifact; prospective file waiting / append-only; maintenance no-op | Matching hashes and QA moved the result into maintenance rather than repeated active tuning. |
| v1.6 | H3 — Liquidity Filtering | Research-only diagnostic; `not_supported` | A 20-day median amount filter did not improve the primary equal-weight implementability comparison and did not alter LOWVOL20 or the universe. |
| v1.7 | H4A — Theme Breadth Diagnostic | Descriptive market-state diagnostic; `mixed` | Breadth60 did not meet its frozen stability threshold and did not authorize timing or allocation rules. |
| v1.8–v1.9.2 | Post-H4 audit / evidence-role cleanup | Existing history reclassified as `historical_seen`; no clean validation set | MOM60's negative direction generated REV60, but the sign flip added no new information. Evaluation contracts became more explicit. |
| From 2026-07-25 literature reconnaissance into H5 | H5 handoff | Literature-inspired, preregistered mechanism diagnostic | The project moved from a 56-stock theme pool to a broader-A historical backfill and began hypothesis-specific literature-to-design contracts. |

The primary H1 and H2 reports did not print the labels “Hypothesis 1” and “Hypothesis 2.” Their identities are nevertheless recoverable: the later local project brief explicitly calls MOM60 the first formal factor line and LOWVOL20 the second; H3 and H4A are explicitly numbered in their own final reports. No local source assigns those ordinal identities to different studies.

## 1. Thematic-universe and stock-pool foundation

### What existed initially

The earliest recovered universe work was a thematic taxonomy, not a historical constituent database. A manual source-concept mapping contained 44 rows. AkShare names were validated only against Eastmoney concept boards: 25 mappings were exact, 2 were fuzzy candidates, and 17 were not found. The subsequent default build selected seven P0 concepts—AIGC概念, AI智能体, 人工智能, 算力概念, 北斗导航, 卫星互联网, and 商业航天—and retrieved their current constituent snapshots. Those snapshots yielded 1,640 concept-constituent rows and 1,225 universe rows.

The records repeatedly warn that concept membership is noisy and current-snapshot based. A concept-board association measured exposure to the board taxonomy; it did not prove that the theme was economically material to the company. Historical concept membership was not reconstructed. The recovered record does not contain a complete original economic justification for choosing AI and commercial space from all possible themes; on that narrower motivation question, **UNSUPPORTED BY LOCAL RECORD**.

Business-materiality review entered precisely because concept-board support was insufficient. The first materiality diagnostic placed all 1,225 rows into review and produced a 318-row high-confidence mismatch queue plus a 200-row profile template. The 200-row review preserved 60 seed rows and added 140 reviewed rows. It used official or financial disclosures where available but relied heavily on Sina/Eastmoney F10-style profiles for broad triage; nine `core` rows remained flagged because their evidence was secondary-only. Nineteen manual decisions were subsequently merged, changing status or materiality on six rows. These records preserve the distinction between theme relevance and trading-pool eligibility.

### What changed

The stock pool changed through named versions rather than silent replacement:

- Stock Pool v1 contained 113 code-theme rows: 1 `default`, 54 `expanded`, and 58 `excluded_by_rules`. Its explicit rules included a minimum 20-day average amount of CNY 100 million, minimum market capitalization of CNY 3 billion, exclusion of ST names, and exclusion where `financial_quality_flag=fail`; high valuation was only a risk note.
- v1.1 preserved the 113 evidence rows and exposed four cases where debt-to-assets above 80% had acted as an implicit rule despite not appearing in the rule file.
- v1.2 made that treatment explicit. Debt-to-assets above 80% alone no longer forced hard exclusion; it allowed expanded membership with a leverage-risk flag unless another hard rule applied. The final v1.2 counts were 1 default, 56 expanded, and 56 excluded rows.
- The expanded plus default research set deduplicated repeated theme memberships to 56 unique stock codes. The expanded-only comparison contained 55 unique codes. This 56-code current universe was later frozen on 2026-07-11 in `research_universe_lowvol_freeze_20260711.csv`.

The universe therefore became smaller because business review and explicit financial, size, ST, and liquidity rules replaced broad concept membership. Its changes were auditable at each version. They were not point-in-time changes tied to historical dates.

### What later research inherited

H1–H4 inherited a fixed current-universe historical backfill. They did not inherit a reconstruction of what could actually have been selected at each past rebalance date. Missing `list_date` and `delist_date`, current rather than historical theme membership, and incomplete historical ST/suspension/limit status created survivorship-like and future-universe bias. Later frozen reports therefore set `universe_point_in_time=false`, `formal_performance_conclusion_allowed=false`, and `execution_sim_ready=false`.

The 56-code pool was valuable as a constant research denominator and as a way to compare signals without silently changing membership. It was not evidence that those same 56 names constituted a historically investable theme portfolio.

## 2. Data-layer and baseline foundation

### Data sources

The early public-data strategy separated a raw reusable cache from adjustment enrichment. Local price files were traced primarily to PostgreSQL `public.stock_prices` and treated as raw or adjustment-unverified. The original cache had close, high, low, amount, turnover, and market-cap fields but lacked a cached adjustment factor, verified adjusted close, open, volume, and pre-close. The realism audit found that an adjustment factor existed in the database but had not been cached; historical list/delist dates were absent.

The initial stock-pool smoke baseline therefore used unadjusted or unverified close-to-close returns and was explicitly `smoke_only`. It covered the current v1.2 universe on approximately 20-trading-day intervals and reported cost scenarios of 0 and 0.001, but prohibited formal performance conclusions and benchmark excess-return conclusions.

For qfq enrichment, local diagnostics recorded repeated Eastmoney `push2his` failures and successful Sina daily fallback probes. The adjusted panel ultimately combined `ak.stock_zh_a_daily` as the main source, one `ak.stock_zh_a_hist` contribution, and explicit missing rows. No silent price filling was permitted. The resulting v1.2 panel contained 70,145 rows for 56 stocks from 2020-01-02 through 2026-06-16, with qfq row coverage of 96.359%, no duplicate stock-date keys, two manifest errors, and three partial statuses.

### Adjustment, benchmark, and period structure

The adjusted-return baseline used qfq prices and a valid CSI 300 (`000300`) calendar. The main period structure was a 20-market-day step. A stock was eligible from information available at the rebalance date; if an initially held name lacked the period-end price, the entire period was invalidated rather than reweighting survivors after the fact. The baseline began only after three consecutive valid periods, an ex-post continuity choice that the report disclosed.

The adjusted baseline retained three index comparisons—`000300`, `000852`, and `399006`—over identical endpoints. Its cost scenarios were 0 and 0.001 per unit of turnover. Turnover used drifted prior weights rather than a simple target-to-target difference. The research-universe headline series used 56 stocks and 57 continuous full periods, beginning 2021-03-31 and ending 2025-12-11. The final partial period and post-termination periods remained diagnostics rather than being appended to the headline NAV.

These files supplied the minimum infrastructure required by H1–H4: normalized six-digit codes, qfq signal and outcome prices, a market-calendar authority, frozen period endpoints, exact missing-data rules, equal-weight universe comparisons, cost-sensitivity conventions, and benchmark alignment.

### Research limitations already known

Before H1, the project already knew that:

- the 2026 stock pool was backfilled through history rather than reconstructed point in time;
- qfq was vendor-adjusted data, not independently audited total-return accounting;
- historical ST, suspension, limit-up/down, and complete trade status were unavailable;
- close-to-close returns did not simulate executable fills;
- capacity and participation limits could not be established from amount alone;
- endpoint-only maximum drawdown could understate intraperiod losses;
- missing qfq endpoints could terminate an otherwise high-coverage series.

Those limitations stayed attached to the factor and diagnostic results rather than being solved by them.

## 3. H1 — MOM60 Factor Research v1.3

### Research question

Within the current AI and commercial-space universe, did higher return over the preceding 60 market days predict higher cross-sectional return over the next approximately 20 trading days?

### Motivation

The primary local records register the positive momentum question but do not document a paper, mentor instruction, or dated observation as its source. Motivation beyond the registered question is **UNSUPPORTED BY LOCAL RECORD**.

### Design

MOM60 was the primary factor. MOM40 and MOM80 were secondary robustness windows on a common sample; they were not separate headline discoveries. The signal ended on the CSI 300 market day before rebalance. Forward return ran from the rebalance-date qfq close to the next rebalance-date qfq close, approximately 20 trading days later. There was no forward fill, backfill, or raw-close substitution.

The current-universe panel retained all research-universe stocks and inherited each period's baseline-eligible codes. Quantiles were assigned on the signal sample before outcome availability was inspected; Q1 was the lowest momentum group and Q5 the highest. Rank IC, quintile returns, Q5−Q1, Q5−universe, stability splits, and MOM40/60/80 common-sample checks were reported. The main MOM60 sample had 54 periods from 2021-06-30 through 2025-11-13; the original report separated 31 “development” and 23 “historical validation” periods.

No transaction-cost model was part of this factor verdict. Q5−Q1 was explicitly a research diagnostic, not an executable A-share long-short portfolio. The stage was described at the time as historical chronological validation, not clean preregistered out-of-sample confirmation. Later evidence-role audits classified all of these already-viewed rows as `HISTORICAL_SEEN`; that later label does not turn the original split into clean validation.

### Main result

The registered positive direction was not supported. Across all 54 primary periods, mean Rank IC was −0.09191 and mean Q5−Q1 return was −0.02042 per period. In the 23-period historical-validation segment, mean Rank IC was −0.12645 and mean Q5−Q1 was −0.03689. `auxiliary_pass_count=0`, and removing the best spread period left mean Q5−Q1 at −0.04167.

The common 53-period robustness sample also opposed positive momentum: mean Rank IC was −0.10445 for MOM40, −0.09606 for MOM60, and −0.11399 for MOM80; all corresponding Q5−Q1 means were negative. The frozen verdict was `not_supported`.

### Problems / limitations

The current-universe bias, lack of a point-in-time stock pool, and absence of execution status remained. The validation segment was historical and already observable, not pristine OOS evidence. Quantile monotonicity was absent, and the Q5−Q1 diagnostic was not tradable evidence. The negative sign rejected the registered positive momentum direction; it did not by itself confirm a reversal factor.

### Why it continued / stopped

The freeze review blocked a MOM60 strategy prototype and instructed the project to stop the positive momentum direction. It allowed only a separately registered reversal question later. Immediately after the freeze, the v1.3 readiness work treated VOL20 and amount-based Liquidity20 as conditional research candidates. This is the documented bridge to H2, not evidence that H1 was silently retuned.

## 4. H2 — LOWVOL20 Factor Research

### Research question

Could lower trailing volatility distinguish stocks with better next-period cross-sectional returns and lower future risk inside the same current thematic universe, conditional on a minimum observed-price reliability screen?

### Motivation

The v1.3 readiness audit examined VOL20 after MOM60 was frozen and found exact-window research feasible but exposed a specific measurement risk: flat closes could represent suspension or source gaps rather than genuine low volatility. The local records do not tie the original LOWVOL20 choice to an external paper. Its documented motivation was therefore the next feasible factor candidate plus the need to test a reliability-aware volatility measure.

### Design

`VOL20` was the standard deviation of 20 simple daily returns formed from exactly 21 qfq closes ending at signal date; `LOWVOL20=-VOL20`, so Q5 was the lowest-volatility quintile. The signal date preceded rebalance and the forward interval was approximately 20 market days. The frozen reliability screen required at least three unique closes, at least five nonzero returns, and no zero-return run longer than five days. Quantiles were formed before outcome availability. LOWVOL10 and LOWVOL40 appeared only as fixed common-sample robustness windows.

The final locked-grid history used the 56-stock frozen universe and 57 period keys from 2021-03-31 through 2025-11-13. Rank IC, Q5−Q1, Q5−universe, forward realized-volatility persistence, endpoint drawdown, concentration, time stability, and descriptive intervals were reported. The original factor verdict did not depend on transaction costs; the later long-only prototype applied 0, 0.001, and 0.002 per unit of turnover against the contemporaneously reliable equal-weight universe.

As with H1, the historical factor stage was not clean OOS. The separate v1.5 prospective protocol froze future rules on 2026-07-11 and distinguished `revised_history`, `pipeline_unseen_retrospective_extension`, and `prospective_holdout` periods. Historical rows did not become prospective merely because the later protocol existed.

### Main result

The final locked-grid report classified LOWVOL20 as `directionally_supported_for_strategy_prototyping`. Across 57 periods, mean Rank IC was 0.08763 and mean risk-persistence Rank IC was 0.43706. In the report's historical-validation segment, mean Rank IC was 0.08274 and mean Q5−Q1 was 0.01951, but their descriptive 95% intervals crossed zero. Q5 had lower annualized period-return volatility than Q1 (0.32314 versus 0.46451) and a less severe endpoint drawdown (−0.32559 versus −0.48213).

The same report also showed the return trade-off: Q5 mean return was 0.01716 versus 0.01966 for the contemporaneous universe, with mean Q5−universe of −0.00250. In the frozen v1.5.1 long-only prototype, zero-cost Q5 cumulative return was 1.11706 versus 1.19836 for the universe; Q5 relative wealth was −0.03698. The cost-0.001 and cost-0.002 scenarios reduced Q5 cumulative return to 1.04636 and 0.97797. Thus the local wording “risk reduction with modest return sacrifice and cost sensitivity” is the bounded result; it is not unconditional return improvement.

### Problems / limitations

The study could not distinguish all suspension-induced flat paths from genuine low volatility using close-only data. Current-universe bias, revised qfq history, missing trading-status fields, endpoint-only drawdown, and the non-executability of Q5−Q1 remained. Historical intervals crossed zero, and no clean OOS performance conclusion was allowed.

### Why it continued / stopped

LOWVOL20 did not stop as an unsupported factor. It moved into a tightly frozen long-only prototype and an append-only prospective protocol. After v1.5.1 corrected the label-blind universe comparison without changing any current-data result, the artifact passed signoff and entered maintenance. Further tuning of lookbacks, thresholds, weights, or overlays was prohibited. That maintenance history is expanded in Section 7.

## 5. H3 — Hypothesis 3: Liquidity Filtering v1.6

### Research question

Would a transparent liquidity filter improve implementability proxies in the frozen thematic universe? The primary comparison was filtered equal weight versus unfiltered equal weight. Filtering LOWVOL20 Q5 was secondary.

### Motivation

This stage addressed implementation concern rather than proposing liquidity as a return-predictive factor. The earlier Liquidity20 readiness audit had shown that trailing amount was usable as a bounded research proxy but that volume, certified turnover units, point-in-time float shares, participation limits, and execution states were unavailable. H3 therefore tested one transparent filter rather than claiming a capacity model.

### Design

For each period, the study calculated mean `amount` over the 20 exact CSI 300 market dates through T−1. All 20 values had to be finite and strictly positive; no filling was allowed. Among baseline-eligible names with valid windows, the filter retained stocks with mean amount greater than or equal to the contemporaneous cross-sectional median. Period-level amount coverage had to reach 90%.

The raw amount field contained 70,129 positive finite values out of 70,145 rows, with 16 missing and no nonpositive values. Period 0 had only 1 of 49 complete windows and failed; periods 1–56 passed, creating a 56-period common sample from 2021-04-29 through 2025-11-13. Portfolio scenarios were unfiltered equal weight, liquidity-filtered equal weight, original LOWVOL Q5, and filtered LOWVOL Q5, under cost rates 0, 0.001, and 0.002. The conclusion rule used the equal-weight comparison; LOWVOL interaction could not determine the primary conclusion.

Evidence role: research-only diagnostic and fixed-rule prototype. This was liquidity as observability / implementability, not liquidity as a standalone predictive factor. The earlier `factor_readiness_liquidity20_v1_3.csv` was only a candidate-family readiness audit and did not run a predictive liquidity factor.

### Main result

The primary conclusion was `not_supported`. At cost rates 0, 0.001, and 0.002, liquidity-filtered equal-weight cumulative returns were 0.37410, 0.35840, and 0.34287, versus 1.18704, 1.18003, and 1.17304 for unfiltered equal weight. Average turnover was also higher for the filtered portfolio (0.20718 versus 0.05899).

The secondary LOWVOL interaction moved in the same unfavorable direction: filtered Q5 cumulative returns were 0.40332, 0.35523, and 0.30875, compared with 1.14327, 1.07294, and 1.00487 for original Q5 across the three cost scenarios. Those rows did not establish a separate cause and did not override the primary design.

### Problems / limitations

`amount` was inferred to be CNY but was not source-contract certified. The filter did not estimate executable capacity, bid-ask spread, impact, participation, suspension, price-limit, or exit feasibility. Its relative performance combined sample selection and portfolio composition and therefore could not isolate a causal “liquidity effect.”

### Why it continued / stopped

The fixed filter failed its own implementability classification: it did not reduce turnover relative to unfiltered equal weight and produced lower relative wealth at nonzero costs. The report explicitly states that it did not alter LOWVOL20 and did not establish capacity. No threshold search or universe rewrite followed; the project moved to a different diagnostic question, theme breadth.

## 6. H4 — Hypothesis 4A: Theme Breadth Diagnostic v1.7

### Research question

Did the fraction of eligible stocks trading above their own 60-market-day mean at signal time relate stably to the next locked period's equal-weight return or drawdown? Separate scopes were overall, AI, and commercial space.

### Motivation

The project records classify this as a descriptive market-state diagnostic after LOWVOL20 and the failed liquidity filter. A more specific source—paper, mentor suggestion, or dated observation—is **UNSUPPORTED BY LOCAL RECORD**.

### Design

Breadth60 used adjusted closes on signal date and the prior 59 CSI 300 market dates. A stock counted above breadth when its signal-date adjusted close exceeded the mean of the complete 60-date window. No forward information or filling entered the signal. Overall, AI, and commercial-space breadth used theme weights while the portfolio itself kept each stock only once.

Coverage had to reach 90%; period indices 0–5 failed, leaving 51 valid periods per scope. The two overall core outcomes were next-period baseline gross return and baseline within-period drawdown magnitude. Daily volatility and negative-return status were supporting outcomes. LOWVOL Q5 return, relative return, volatility reduction, and drawdown reduction were secondary interactions.

The frozen diagnostic-support rule required at least 46 periods, absolute Spearman correlation of at least 0.25, sign stability after excluding the largest one and three contributions, leave-one-out sign agreement of at least 80%, and no excessive top-three concentration. Tie-aware terciles described low, middle, and high breadth states. Circular-shift p-values were descriptive and were not treated as i.i.d. formal tests. Evidence role: `DIAGNOSTIC`, not timing, allocation, or Alpha research.

### Main result

The overall classification was `mixed`. Neither core relation met the frozen stability threshold. Overall Breadth60 versus next-period baseline gross return had Spearman −0.1628; breadth versus drawdown magnitude had Spearman +0.1601. Neither relation was monotonic across the three breadth states, and the circular-shift p-values were 0.2549 and 0.3529.

AI and commercial-space core correlations remained below the 0.25 threshold in absolute value. The stronger values appeared only in secondary LOWVOL interactions: overall breadth versus Q5-relative return was 0.3524, with AI 0.3305 and commercial space 0.3088. The report prohibited those secondary relations from promoting the result to `diagnostically_supported` or altering LOWVOL20.

### Problems / limitations

Only 51 valid locked periods were available. Strict complete-window breadth measured continuously observable names; suspensions and missing prices could change the denominator. The commercial-space denominator was small, theme membership remained current-snapshot based, and the analysis was descriptive rather than causal.

### Why it continued / stopped

H4A did not authorize a 4B strategy stage. The report required `diagnostically_supported` plus human approval before any separate 4B could even be drafted. Because the result was `mixed`, no timing or position-sizing rule followed. The next project-wide work focused on auditing evidence roles, literature reconnaissance, and a more explicit hypothesis-development process.

## 7. LOWVOL20 freeze and maintenance history

LOWVOL20 is H2, not a separate fifth early hypothesis. It receives a separate archival section because its history continued after the factor test.

The v1.4 freeze review confirmed that the factor panel, QA, summaries, and report agreed on `LOWVOL20=-VOL20`, exact 21-close windows, the CSI 300 calendar, the fixed eligible-code contract, and no filling or raw-close substitution. In the original 56-period main interval, the reliable and all-exact masks were identical: 2,962 stock-period rows and zero flat-price reliability exclusions. The original historical-validation point estimates were mean Rank IC 0.08867 and mean Q5−Q1 0.01890, with both descriptive 95% intervals crossing zero.

The 2026-07-11 prospective protocol then froze the 56-stock universe, factor formula, reliability rules, approximately 20-day rebalance boundaries, Q5 equal weighting, benchmarks, and costs of 0, 0.001, and 0.002. It prohibited momentum, reversal, liquidity, stop-loss, timing, multifactor overlays, alternate Top N, alternate windows, and threshold searches. Future results were append-only. A period could be `PROSPECTIVE` only if its rebalance date was strictly after the freeze date and its complete outcome period had ended.

The later locked-grid v1.5 history used all 57 period keys and retained the directional verdict. The v1.5.1 prototype corrected the universe comparator to use the reliable signal sample rather than the evaluation sample. On the current data this changed no membership, returns, risk values, or conclusions. Human signoff on 2026-07-12 froze v1.5.1 as the research-artifact baseline for prospective append; it did not approve formal performance or execution claims.

By 2026-07-14 the artifact's hash matched its frozen manifest and all structure and reconciliation checks passed. The approved maintenance action was a no-op: do not reconstruct or replace a matching artifact. LOWVOL20 was therefore simultaneously a main historical factor candidate, a frozen long-only research prototype, and the subject of a prospective append-only protocol. It entered maintenance because its identities and rules were frozen and no completed prospective evidence justified reopening the design—not because its historical result had become formal confirmation.

## 8. Liquidity / liquidity-filter work

The bounded liquidity history had two distinct designs.

First, v1.3 performed readiness work on a possible `Liquidity20` research proxy. It found that exact 20-market-day trailing amount was usable on 13,064 of 13,290 eligible stock-endpoint windows (98.30%) and that amount and a vendor turnover field each had 70,129 of 70,145 nonmissing rows. But volume was absent throughout; turnover units and denominator were inferred rather than documented; circulating market-cap vintages were unverified; and suspension, limit, participation, and fill data were missing. The readiness audit selected no threshold and ran no predictive test.

Second, H3 used only the source-supported amount proxy in one frozen implementability rule: retain names at or above the within-period median 20-day mean amount, conditional on exact positive observations and 90% period coverage. It compared this filtered portfolio directly with the unfiltered equal-weight portfolio. This was not a test that higher liquidity predicted higher individual-stock returns; it was a test of whether a simple screening rule improved turnover / wealth outcomes under fixed costs.

The result was `not_supported`, coverage was sufficient for 56 periods, and the filter neither improved the primary comparison nor justified changing the universe. The study stopped without searching other quantiles, fixed CNY cutoffs, volume rules, turnover denominators, or capacity assumptions. The 100-million-CNY stock-pool entry rule and the H3 median filter are also distinct: the former helped construct the v1.2 current universe; the latter was a period-by-period research overlay within the already frozen universe.

## 9. Transition into H5

By the end of H4, the local record contained one unsupported positive factor direction (MOM60), one directionally supported but historically seen risk-oriented factor (LOWVOL20), one unsupported implementability filter, and one mixed breadth diagnostic. It also contained an uncompleted event study stopped by a data gate. Existing results had been viewed repeatedly, so the v1.9 protocol work made the evidence-role problem explicit: 2021–2025 MOM60/REV60 observations were `historical_seen`, clean development and validation sets were unavailable, and REV60 was only the sign reversal of the same 60-day ranking information.

Literature reconnaissance became a distinct project stage on 2026-07-25. The local reconnaissance archive records 88 registry items, 30 core items, and 13 deep reads; it explicitly prohibited implementing signals or choosing a best factor during reconnaissance. The transition was therefore procedural as well as substantive: ideas were increasingly tied to named literature, and each new hypothesis received a hypothesis-specific preregistration, measurement contract, frozen comparisons, stopping rules, and explicit `historical_seen` interpretation.

H5 inherited several early assets: the requirement that signal membership be fixed before outcomes, exact market-calendar windows, no imputation of missing prices, explicit sample roles, documented current-universe bias, and separation of descriptive evidence from Alpha or execution claims. It did not simply extend the 56-stock theme test. H5A moved to a broader-A current-universe historical backfill and asked a literature-inspired return-state × trading-activity question over 56 primary periods, using a hypothesis-specific preregistration and 20D/60D/120D outcome paths. The handoff is consistent with `H5_H8_RESEARCH_HISTORY.md`: H5 was inspired by Lee and Swaminathan (2000), was not an exact replication, and treated amount-based activity as a mechanism diagnostic whose measurement later required audit.

What made H5 the next chosen question, rather than another candidate in the literature registry, is not fully recorded. On that selection decision, **UNSUPPORTED BY LOCAL RECORD**.

## Early-stage synthesis table

| Stage | Main question | Evidence role | Key design | Main result | Main limitation | Why next stage followed |
|---|---|---|---|---|---|---|
| Theme universe | Which current AI / commercial-space names belong in a reviewable candidate set? | Taxonomy / review input | Seven Eastmoney concept boards via AkShare; business-materiality review | 1,225 universe rows, then 113 reviewed code-theme rows | Current snapshot; concept tag not business materiality | Versioned evidence and trading rules narrowed the pool. |
| Stock pool v1.2 | Which reviewed rows enter default, expanded, or excluded sets? | Frozen rule audit | ST, quality, CNY 3bn cap, CNY 100m amount hard rules; leverage rule clarified | 1 default, 56 expanded, 56 excluded; 56 unique research codes | Not historical membership | Created a stable denominator for research. |
| Adjusted baseline | Can the current pool be measured on qfq endpoints and fixed periods? | Research baseline | qfq closes, CSI 300 calendar, 20-day periods, 0/10bp cost scenarios | 57 continuous headline periods; plumbing accepted | Missing trade state, future-universe bias, endpoint gaps | Enabled signal studies with explicit boundaries. |
| H1 MOM60 | Does high 60-day return predict high next-period return? | Historical current-universe study; later `HISTORICAL_SEEN` | MOM60 primary, MOM40/80 robustness, 54 periods | `not_supported`; validation mean IC −0.12645, Q5−Q1 −0.03689 | Not clean OOS; no point-in-time universe | Positive momentum stopped; next feasible factor audited. |
| H2 LOWVOL20 | Does low trailing volatility rank better and reduce future risk? | Historical directional factor evidence; frozen artifact | −VOL20, exact 21 closes, reliability screen, 57 locked periods | `directionally_supported_for_strategy_prototyping`; lower Q5 risk, modest return sacrifice | Descriptive intervals crossed zero; close-only tradability limits | Froze prototype and prospective protocol. |
| H3 Liquidity filter | Does a median 20-day amount filter improve implementability? | Research-only diagnostic | Exact positive amount, ≥median filter, 56 periods, 0/10/20bp costs | `not_supported`; filtered return and turnover comparison unfavorable | Amount is not capacity or causal liquidity | Stopped filter search; moved to market-state diagnostic. |
| H4A Breadth60 | Does signal-time breadth relate to next-period return / drawdown? | `DIAGNOSTIC`, `mixed` | Above-own-60-day-mean share; 51 valid periods; frozen stability threshold | Core Spearman −0.1628 and +0.1601; neither stable | Small thematic sample and observable-denominator effects | No 4B; evidence-role and literature process became central. |
| H5 handoff | Do return and activity states distinguish future paths? | `HISTORICAL_SEEN` mechanism diagnostic | Broader-A backfill, preregistered 3×3 states, 20/60/120D paths | Outside this archive's result scope | Broader universe still not point in time; activity construct mixed exposures | Begins the existing H5–H8 history. |

## Verification notes

1. **H1/H2 numbering (minor).** The primary MOM60 and LOWVOL20 titles omit “H1” and “H2.” The later local project brief calls them the first and second formal lines, while the following reports are explicitly “Hypothesis 3” and “Hypothesis 4A.” This archive uses that locally supported sequence; no conflicting assignment was found.
2. **LOWVOL20 v1.4 versus locked-grid v1.5 (minor versioning).** The v1.4 freeze review reports 56 main periods and historical-validation mean Rank IC 0.08867 / Q5−Q1 0.01890. The final locked-grid v1.5 report contains 57 locked periods and reports 0.08274 / 0.01951 for its historical-validation summary. These are versioned sample-grid results, not averaged or silently reconciled. The H2 headline uses the final locked-grid source and preserves the v1.4 figures only in the freeze-history subsection.
3. **Prototype v1.5 versus v1.5.1 (minor supersession).** v1.5.1 corrected the label-blind universe comparator. Its diff states that the current dataset's membership, returns, risk, and conclusion were unchanged. Prototype numbers in this archive use v1.5.1.
4. No material conflict was found in H1–H4 identity, factor definition, universe size, support label, LOWVOL20 role, liquidity result, or H5 handoff.
5. No experiment was rerun; no data was fetched; no performance result was recomputed beyond reading, counting, and comparing stored rows; no hypothesis was reinterpreted with later outcomes; and no final-project narrative was selected.

## Source map

Thirty-three local files were used. Primary and final sources control numerical and design claims; later synthesis files were used only for sequence labels and the H5 boundary.

### Universe and stock pool

1. `reports/akshare_concept_validation_report.md`
2. `reports/theme_stock_universe_report.md`
3. `reports/theme_business_materiality_report.md`
4. `theme_business_review_QA_report.md`
5. `data/stockPool/post_manual_decision_audit.md`
6. `data/stockPool/stock_pool_v1_QA_report.md`
7. `data/stockPool/stock_pool_v1_1_QA_report.md`
8. `data/stockPool/stock_pool_v1_2_QA_report.md`

### Data and baseline

9. `reports/market_data_realism_audit.md`
10. `reports/backtest_data_readiness_report.md`
11. `reports/qfq_source_diagnostics_v1_2.md`
12. `reports/adjusted_price_panel_QA_v1_2.md`
13. `reports/stock_pool_smoke_baseline_v1_2.md`
14. `reports/adjusted_stock_pool_baseline_v1_2.md`
15. `reports/baseline_result_review_v1_2.md`

### H1 and H2 / LOWVOL20

16. `reports/factor_mom60_v1_3.md`
17. `reports/mom60_v1_3_freeze_review.md`
18. `reports/remaining_hypotheses_readiness_v1_3.md`
19. `reports/lowvol20_v1_4_freeze_review.md`
20. `reports/factor_lowvol20_locked_grid_v1_5.md`
21. `reports/lowvol20_prospective_protocol_v1_5.md`
22. `reports/lowvol_locked_grid_prototype_v1_5_1.md`
23. `reports/lowvol_locked_grid_prototype_v1_5_1_signoff.md`
24. `reports/lowvol20_maintenance_mode_v1_5_1.md`

### H3, H4, and sequence / handoff

25. `reports/liquidity_filter_hypothesis_v1_6.md`
26. `scripts/test_liquidity_filter_hypothesis_v1_6.py`
27. `reports/theme_breadth_hypothesis_v1_7.md`
28. `scripts/run_theme_breadth_diagnostic_v1_7.py`
29. `reports/student_project_brief_v1.md`
30. `reports/H5_H8_RESEARCH_HISTORY.md`
31. `docs/literature_reconnaissance/00_scope_and_status.md`
32. `reports/hypothesis_5a/h5a_preregistration_and_implementation_plan.md`
33. `reports/lowvol_locked_grid_prototype_summary_v1_5_1.csv`
