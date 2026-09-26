# Research Methodology Lessons

## Executive summary

The `quant_start` project evolved through factor results, data audits, literature-derived diagnostics, and the Robinhood Chain study. Its most durable output is not a single factor or coefficient, but a progressively stricter understanding of what a historical result means. Six lessons organize that development:

1. a universe is part of the hypothesis, not merely an input table;
2. technical correctness does not guarantee point-in-time correctness;
3. missingness and illiquidity can mark limits of observability rather than repairable dirt;
4. leakage can enter through sample and rule choices even when the factor formula contains no future return;
5. QA rules define the interpretable sample and therefore the empirical estimand; and
6. research governance protects evidence identities without forbidding exploration or new questions.

These lessons do not imply that human judgment should be eliminated, that stricter filtering is always better, or that exploratory work is inferior. The governing principle is to make judgment documented and evidence-informed, freeze the current claim before its outcome is used, preserve the identity of post-outcome diagnostics, and allow old results to generate genuinely new studies. In short: **freeze the claim, not the curiosity**.

## 1. Universe construction is part of the hypothesis

### Initial problem

Early thematic-universe work could easily treat database concept membership as if it were verified economic exposure. The generated concept universe contained 1,225 rows across seven selected AI and commercial-space concepts. Its own report warned that concept constituents were noisy current snapshots and that `concept_exposure_score` measured concept-board exposure, not confirmed stock relevance.

Three distinct questions were therefore entangled:

- does a database or concept board associate the company with the theme?
- is the theme economically material to the company's business?
- was that membership knowable at the historical research date?

### What went wrong / what risk appeared

Concept support did not imply business materiality. The first materiality pass left all 1,225 rows for review and placed 318 rows in a high-confidence mismatch queue. In the detailed 200-row review, many companies lacked disclosed theme revenue ratios; broad triage often relied on secondary F10-style business profiles, and nine `core` cases with secondary-only evidence were explicitly flagged. This was evidence-quality variation, not a reason to pretend the database label was sufficient.

Separately, historical listing and theme membership could not be reconstructed point in time. The market-data realism audit found no usable `list_date` or `delist_date`, and current `is_active` fields could not recover historical membership. Consequently, the 56-stock research pool was a current universe applied retrospectively, with survivorship and future-universe bias. It was not a historical point-in-time thematic backtest.

### Rule adopted

The project separated four layers:

1. generated concept membership;
2. business-materiality evidence;
3. recorded human review or exception decisions; and
4. the frozen research universe used by a specific study.

Human judgment was retained as a legitimate research input. The requirement was that it be evidence-informed, recorded, and applied before the relevant outcomes—not that it disappear. Generated concept files, manual business profiles, override files, review outputs, and post-manual audits remained separate artifacts. Later universe changes required a new version or an explicit research revision rather than a silent reclassification of the existing study.

### Project examples

- `theme_stock_universe_report.md` identifies concept exposure as a taxonomy/research input rather than a recommendation or business-materiality decision.
- `theme_business_materiality_report.md` routes business evidence through a separate diagnostic and review layer.
- The 200-row business review records 19 manual-decision rows and six changed status/materiality decisions in `post_manual_decision_audit.md`.
- Stock-pool v1.2 records 113 input and output rows, explicit hard rules, preserved evidence fields, and 56 expanded-pool names. Its QA reports no validation errors.
- The LOWVOL20 prospective protocol froze exactly 56 six-digit A-share codes on 2026-07-11 in `research_universe_lowvol_freeze_20260711.csv`; membership could not change because of later prices, news, filings, or outcomes.

### Final lesson

主题股票池不是简单的数据准备，而是研究假设的一部分。数据源的分类、真实业务实质和历史时点可知性必须分别审视；可靠研究既不能盲信数据库标签，也不必排斥人的经验判断。关键是让判断建立在可靠证据之上、过程可记录，并在观察结果前冻结。

Data sources shape the entire experiment. Selecting them requires careful analysis of reliable information together with documented human experience and judgment. In this project's ordering, point-in-time availability was more consequential than business materiality, and business materiality was more consequential than cosmetic database cleanliness.

## 2. Point-in-time correctness is part of measurement design

### Initial problem

A historical value can be numerically correct when calculated today and still be unavailable to a researcher at the historical date. The issue applies to prices, share counts, industry classifications, corporate actions, and the timing of signal and outcome data.

### What went wrong / what risk appeared

The market-data realism audit found that the original local cache lacked adjusted closes or usable cached adjustment factors, while one historical database sample had zero non-null `adj_factor` values. It also found current status without historical listing/delisting lineage. These are not ordinary NA-cleaning problems: using the wrong return basis or a later-known universe can change what the historical variable represents.

Historical denominators created the same problem. A current share count copied backward can produce an arithmetically valid turnover ratio that was not the contemporaneous ratio. Likewise, a share-change date is not enough if the information was announced later. Repairing unknown early history with the first later authoritative level would introduce future information.

### Rule adopted

Point-in-time status became part of each measurement contract. The project asked both:

1. how is the value computed? and
2. when could that value have been known?

Missing historical lineage was preferred to unsupported backfill. Signal dates had to precede evaluation intervals, and outcome availability could not repair signal membership. Price convention was selected for the research question rather than treated as universally superior.

### Project examples

- A-share return studies such as LOWVOL20 and H5–H7 used exact QFQ closes where a return series required corporate-action continuity, while still disclosing that QFQ used the current adjustment vintage.
- H8 deliberately used raw BaoStock OHLC plus explicit corporate-action row exclusions because its stock-level replication required contemporaneous raw open/close relationships. QFQ substitution was prohibited.
- Robinhood RQ2 froze `PRICE_BASIS = RAW_CONTEMPORANEOUS_MARKET_PRICES`: previous close, 20:00 VWAP, and official open had to share the same raw basis. Mixing adjusted daily prices with raw intraday trades was prohibited.
- H7 defined `TOTAL_SHARE_TURNOVER = BaoStock volume_shares / CNINFO point-in-time total_shares`. A CNINFO level became usable only from `max(change_date, announcement_date)` onward. The interval before the first complete usable level remained unknown; it was not filled with a later event, local market-cap/close implied shares, or BaoStock-implied shares.
- H7's data-quality audit retained 35 stocks without an authoritative opening total-share level and explicitly marked local implied shares as useful but not authoritative.

### Final lesson

数据在技术上正确，不代表它在研究时点上正确。真正可靠的历史研究必须同时问：这个值怎么算出来的，以及当时是否已经能够知道它。

**Technical correctness ≠ point-in-time correctness.** There is no single universally correct price or dataset independent of the research question. Adjusted prices are appropriate for some return constructions; raw contemporaneous prices are necessary for others.

## 3. Liquidity, market constraints, and observability

### Initial problem

Missing or thin observations were initially easy to frame as incomplete data that should be repaired. In markets, however, missingness may correspond to a state in which the target variable is not reliably observable: suspension, price limits, sparse executions, insufficient notional, or an absent price anchor.

### What went wrong / what risk appeared

Repair can create a value that the market did not supply. Forward filling a suspended stock, widening a token boundary window after seeing sample loss, or substituting the nearest stock trade for a missing after-hours anchor changes the measurement rather than merely cleaning it.

The opposite risk is also important: strict filtering changes the sample. A liquidity rule may improve the reliability of retained observations while concentrating the study in larger, more active, or otherwise unusual assets. The project therefore treated both observability and attrition as facts to report.

### Rule adopted

Observability rules were frozen before outcome interpretation. If an exact window failed, the row remained missing or was excluded with a deterministic reason. No nearest observation, forward fill, ad hoc substitute, or post-result window widening was permitted. At the same time, exclusions had to be counted by asset, period, and reason so that selection effects remained visible.

Suspension and constrained-market states were not treated as interchangeable with zero activity. Where authoritative historical limit-up/down status was unavailable, the project retained the limitation rather than fabricating a flag from OHLC. It did not assert that every constrained-market price was invalid.

### Project examples

- The A-share liquidity study required 20 exact CSI 300 market dates through T−1, all with finite, strictly positive amount. No fill was allowed. The first low-history diagnostic period had only 1 of 49 complete windows and failed coverage; later Primary periods passed. The frozen filter ultimately received `not_supported`, demonstrating that a cleaner implementability proxy need not improve performance.
- H7 treated suspended formation rows as invalid observations, not zero-turnover days. Its 200-observation turnover baseline used strictly prior active observations; missing dates were not replaced. Authoritative historical price-limit status remained unavailable.
- Robinhood's primary token observation required both 30-minute boundary windows to contain at least five executed swaps and at least USDG 500 quote notional. Available-but-thin rows were not promoted to Primary.
- The stock-side 20:00 anchor required complete pagination, classified trade conditions, at least five eligible executions, at least 100 shares, and at least USD 10,000 notional, with a finite positive VWAP. No last trade, nearest trade, quote midpoint, OHLC, or wider window could substitute.
- E3's frozen premarket QA retained only **22 of 43** prospective rows: 22 GME, zero NVDA, and zero COST. Twenty-one rows failed the duplicate-trade-ID anomaly-review rule. The rule was not relaxed, and the report concluded that the severe, asset-skewed attrition prevented temporal localization of the original pooled association.

### Final lesson

数据缺失或流动性不足不一定只是需要修复的脏数据；它可能意味着该市场状态下变量无法被可靠观测，如涨停、跌停、停牌，或 Robinhood Chain 这类新兴市场中的交易稀疏。研究者不能为了保留样本随意填补，也必须承认严格过滤会改变研究样本。

**Observed ≠ necessarily fully informative.** Filtering may improve measurement quality and simultaneously introduce selection effects.

## 4. Label blindness and sample isolation

### Initial problem

Look-ahead is not confined to a formula that explicitly references a future return. It can enter through universe repair, eligibility thresholds, exceptions, sample membership, anomaly treatment, or a decision to retain only rows with available outcomes.

### What went wrong / what risk appeared

If stocks are ranked only after future-label availability is known, missing outcomes can change historical signal groups. If a pilot result is later folded into a nominally prospective analysis, discovery observations can masquerade as independent validation. A technically backward-looking signal is therefore not sufficient to establish label blindness.

### Rule adopted

The project separated **signal samples** from **evaluation samples**. Membership and ranks were determined using signal-time fields; future missingness could invalidate evaluation but could not remove a signal member and trigger reranking. It also separated **discovery** from **prospective-extension** evidence. Outcome-seen data remained useful for measurement debugging, phenomenon discovery, and hypothesis generation, but could not be relabeled as untouched validation.

### Project examples

- The LOWVOL20 protocol assigned quantiles from the reliable signal sample before inspecting future-label availability. Its freeze review explicitly checked that the evaluation sample was a subset of the signal sample.
- Phase A's protocol classified all previously viewed 2021–2025 MOM/REV evidence as `historical_seen`. The earlier “validation” interval could not be reclaimed as clean validation merely because a later script read an earlier development segment first.
- The Robinhood NVDA pilot had already inspected 20 dated outcomes. The holdout amendment retained those rows as `DISCOVERY` rather than deleting them, but excluded them from Primary inference.
- Before prospective stock outcomes were fetched, a price-free bridge and manifest froze 80 robust token rows: 20 discovery NVDA rows and 60 prospective-extension candidates (NVDA 13, GME 29, COST 18). Stock QA later reduced the Primary inferential sample to **43** rows (NVDA 11, GME 23, COST 9) using predeclared rules. The first model used only those 43 prospective-extension rows; no discovery or TSLA row entered.
- The project truthfully labeled the design `PILOT_INFORMED_PROSPECTIVE_EXTENSION`, not a fully outcome-naive preregistration. Discovery-inclusive analysis remained optional secondary exploration.

### Final lesson

研究中的信息泄漏不只发生在公式里，也可能发生在样本选择、阈值设定和例外处理里。样本成员资格应尽可能在 outcome 不可见时确定；已经看过结果的数据仍然可以用于探索、测量和提出新问题，但必须与真正未见结果的验证样本隔离。

Discovery data do not become useless after outcomes are seen. Their scientific role changes.

## 5. QA as research design

### Initial problem

QA can be mistaken for a final engineering checklist: remove duplicates, convert numbers, and confirm that code ran. In research, a validity rule determines which observations can carry the intended economic meaning.

### What went wrong / what risk appeared

A technically valid record may still be an invalid observation for the research question: an after-hours VWAP with too few executions, an official open inferred from the first 09:30 trade rather than the official auction, a turnover denominator filled from future share information, or a volatility signal formed from long runs of unchanged prices.

Conversely, a technically correct frozen QA rule may make a planned question unanswerable. Relaxing that rule because the remaining sample is small would change the estimand after learning the inconvenience. Scientific inconvenience is not a QA bug.

### Rule adopted

The operative chain became:

> **QA rule → sample definition → empirical estimand**

QA was treated as a measurement and identification contract. Thresholds, exact windows, duplicate handling, price conventions, condition codes, coverage requirements, and exclusion reasons were frozen before the relevant outcome analysis. Rules changed only for a demonstrated design or implementation error, not to increase N or improve a coefficient.

### Project examples

- LOWVOL20 required 21 exact QFQ closes, at least three unique closes, at least five nonzero returns, and no zero-return run longer than five days. It used no fill, backfill, or raw-close substitution. In the main interval, no exact-window row failed those reliability criteria; QA established equivalence of Primary and all-exact masks rather than manufacturing a difference.
- H5B froze signal membership before outcomes and required both extreme cells to have at least 25 members and 80% outcome coverage. Future missingness could not reassign states or rerank remaining stocks.
- RQ2 defined unique primary-venue official-open (`Q`) and official-close (`M`) trades, exact half-open time windows, trade-condition classification, pagination completeness, and deterministic exclusion reasons before acquisition.
- RQ2's first Primary model retained all 43 QA-passing rows, including four observations flagged by descriptive influence heuristics. No row was removed based on outcome magnitude or influence.
- E3 is the clearest identification example: the frozen duplicate-ID rule removed every NVDA and COST row from the temporal subset. The correct conclusion was `NO_COHERENT_TEMPORAL_MECHANISM`, not a relaxed anomaly rule or a substitute sample.

### Final lesson

QA 不是研究完成后的技术验收，而是研究设计的一部分。它定义什么 observation 可以被解释；如果严格执行事先合理的 QA 后问题无法识别，正确做法是承认识别失败，而不是事后修改规则直到得到结果。

**Valid computation ≠ valid identification.** Stricter QA is not automatically better science, and maximizing retained sample size is not its objective.

## 6. Research governance: separating confirmation, exploration, and new hypotheses

### Initial problem

Two opposite mistakes are possible. One is to keep changing a frozen study after seeing its result. The other is to conclude that seeing an outcome forbids further curiosity. The project learned to separate the identity of the current evidence package from the continuation of the research programme.

### What went wrong / what risk appeared

The same historical data had supported multiple windows, orientations, factor versions, and later diagnostic questions. Without explicit roles, a post-hoc direction such as REV60 could be mistaken for a new independent factor, or a useful mechanism diagnostic could be presented as though it had been part of the original confirmatory design.

The Robinhood sequence created the same governance challenge in a smaller prospective sample. Some sensitivities were frozen before outcomes, some were optional candidates, and E1/E2 were questions generated after the Primary result. Treating all of them as equally prespecified—or treating all post-outcome work as invalid—would misstate the history.

### Rule adopted

The project used three evidence levels:

#### Level 1 — frozen / confirmatory claim

For the current Primary or mandatory test, once outcomes are visible, parameters, thresholds, horizons, samples, exclusions, controls, estimators, transforms, proxies, and subgroups cannot be changed merely to strengthen the same claim.

#### Level 2 — post-outcome diagnostics / exploration

Researchers may investigate anomalies, robustness, alternative explanations, mechanisms, and measurement concerns. These results retain labels such as `POST_OUTCOME`, `EXPLORATORY`, `SECONDARY`, or `DIAGNOSTIC`; they do not replace the frozen Primary.

#### Level 3 — new research question

An old result may motivate a genuinely new question. The correct sequence is:

> old result → new question → new hypothesis/design → newly frozen test or new evidence cycle

Stopping rules therefore freeze the current study's evidence package. They do not terminate scientific curiosity.

### Project examples

- Phase A registered all known factor variants and treated `REV60 = −MOM60` as the same information family with `orientation_alpha_increment=0`. All 2021–2025 results remained historical-seen; a future prospective test required a one-time, newly frozen evidence cycle.
- H5A's stable amount-state result led to separately labeled post-H5A size and volatility diagnostics, then to a separately preregistered H5B. H5B explicitly prohibited a proxy tournament, alternative VT windows, denominators, neutralization, or residualization.
- H6 froze one 50-day own-history amount rank and prohibited new history windows, z-scores, ratios, detrending, or residual alternatives. H7 separately froze total-share turnover, a 200-active-observation baseline, one Primary equation, and named robustness checks. The H5→H6→H7→H8 progression was a sequence of distinct evidence cycles, not one continuously modified hypothesis.
- Robinhood's pre-outcome contract made one common-session 5-minute-versus-30-minute comparison mandatory. The closure audit correctly identified it as the sole unfinished mandatory sensitivity at 00:41 on 2026-09-21. The comparison was completed later that morning on the same 43 rows and explicitly recorded `MANDATORY_COMMON_SESSION_SENSITIVITY_COMPLETED`; both estimators retained a positive direction, with attenuation under the strict 5-minute measure.
- Discovery-inclusive analysis, TSLA, broad-market controls, and a premarket study were pre-outcome candidates or conditional options, not closure obligations.
- E1's leave-one-session/asset and influence stress and E2's liquidity/NVDA mechanism work were post-outcome diagnostics. They were legitimate explorations but did not replace the frozen Primary. E3 addressed an optional premarket concept in a separately approved terminal diagnostic and retained its identification failure after severe QA attrition.

### Final lesson

研究纪律的目的不是限制发现，而是保护不同证据的身份。对于已经冻结的验证性问题，看到结果后不应通过不断改变参数、样本或 specification 来强化同一个结论；但从旧实验中寻找异常、机制和新问题本身是科学研究的重要组成部分。事后发现应如实标记为 exploratory，并可以发展成新的 hypothesis，在新的设计或未见数据中继续检验。

**Freeze the claim, not the curiosity.** A study should stop expanding when its frozen Primary and mandatory prespecified checks are complete and remaining questions require materially new hypotheses or designs—not merely because the result looks good or bad, the researcher is tired, or imaginable robustness checks have been exhausted.

## Methodological progression

| Lesson | Initial naive view | Research risk discovered | Rule adopted | Representative project example |
|---|---|---|---|---|
| Universe construction | A concept-board list is the research universe | Database exposure, business materiality, and historical knowability differ | Separate generated membership, evidence review, human decision, and frozen version | 1,225 concept rows → reviewed materiality layer → v1.2 pool → frozen 56-stock universe |
| Point-in-time correctness | A correct formula produces a valid historical value | Later-known adjustment, membership, or denominator information can leak backward | Freeze price basis, information dates, and no-future-backfill rules by question | H7 uses CNINFO shares only from `max(change_date, announcement_date)` |
| Observability | Missing/thin rows should be repaired | Repair invents prices; strict filters change composition | Exact-window gates, deterministic missingness, explicit attrition | Robinhood token/stock anchors and E3's 22/43 asset-skewed subset |
| Sample isolation | No future return in the formula means no leakage | Membership, thresholds, and exceptions can be outcome-aware | Separate signal/evaluation and discovery/prospective roles | 20 NVDA discovery rows excluded from the frozen 43-row Primary extension |
| QA as design | QA is post-hoc technical acceptance | Valid computation may not identify the intended question | Treat QA as a measurement + identification contract | E3 retained `NO_COHERENT_TEMPORAL_MECHANISM` instead of relaxing duplicate-ID QA |
| Evidence governance | Either keep optimizing or stop exploring | Frozen claims and useful post-outcome questions lose distinct identities | Three evidence levels; mandatory/candidate/post-outcome inventory; new cycles | H5→H8 and RQ2 Primary→E1/E2/E3→mandatory common-session closure |

## Verification notes

1. The thematic-review architecture and audit files support separation of generated concept data, business evidence, human decisions, and frozen study universes. They cannot prove the universal negative claim that no generated file was ever edited out of band at any point in the project's history. The archive therefore states the evidenced artifact structure and recorded audits rather than an absolute forensic guarantee.
2. Evidence quality in the 200-row business-materiality triage varied. Most later rows used auditable secondary F10-style sources, and nine `core` cases with secondary-only evidence were flagged; the QA report recommended annual-report citations before promotion into the default universe. The later v1.2 stock-pool QA states that annual-report evidence fields were preserved. This is a documented maturation of the review process, not evidence that every early decision used primary company disclosure.
3. `rq2_closure_audit.md` reports `MANDATORY_SENSITIVITY_REMAINS` because it was written before the common-session sensitivity. Local creation times and the later `common_5m_vs_30m_summary.md` closure statement establish the subsequent completion. The earlier audit was not modified or treated as if it had known the later result.
4. Historical A-share price-limit data were repeatedly documented as unavailable. Limit-up/limit-down remain valid market-mechanism examples in the approved lesson, but the project did not claim to have fully measured those states in every A-share study.

## Source map

The archive used the following 23 local source files:

| Lesson | Source type | Local file | Claim supported |
|---|---|---|---|
| 1 | Universe | `reports/theme_stock_universe_report.md` | Concept taxonomy is a current-snapshot research input, not verified materiality |
| 1 | Business review | `reports/theme_business_materiality_report.md` | Separate materiality layer and mismatch queue |
| 1 | QA audit | `theme_business_review_QA_report.md` | Evidence hierarchy, manual decisions, and evidence-quality caveats |
| 1 | Manual-review audit | `data/stockPool/post_manual_decision_audit.md` | Recorded human decisions and changed classifications |
| 1 | Universe QA | `data/stockPool/stock_pool_v1_2_QA_report.md` | Versioned pool rules, 56-name expanded pool, evidence preservation |
| 1, 4 | Preregistration | `reports/lowvol20_prospective_protocol_v1_5.md` | Frozen 56-stock universe, immutable membership, signal-before-label rule |
| 2 | Data audit | `reports/market_data_realism_audit.md` | Adjustment, listing/delisting, status, and as-of-data limitations |
| 2, 3 | Data-lineage audit | `reports/hypothesis_7/data_quality/h7_turnover_data_quality_report.md` | Share information dates, no future fill, suspension and lineage exceptions |
| 2, 6 | Preregistration | `reports/hypothesis_7/h7_dynamic_volume_return_preregistration_v1.md` | Turnover/baseline contract and bounded robustness family |
| 2 | Preregistration | `reports/hypothesis_8/h8_preregistration_v1.md` | Raw-price/corporate-action adaptation and frozen H8 design |
| 3 | Final report | `reports/liquidity_filter_hypothesis_v1_6.md` | Exact amount windows, coverage, and unsupported liquidity result |
| 4, 5 | Freeze audit | `reports/lowvol20_v1_4_freeze_review.md` | Signal/evaluation subset rule, deterministic QA, frozen evidence |
| 4, 6 | Design contract | `reports/research_execution_plan_v1_9_1.md` | Historical-seen identity, sample roles, thresholds, stopping rules |
| 3–6 | Design contract | `reports/robinhood_chain_pilot/rq2_information_content_design/RQ2_INFORMATION_CONTENT_DESIGN_CONTRACT.md` | Token observability, sample roles, Primary model, sensitivities |
| 4 | Holdout amendment | `reports/robinhood_chain_pilot/rq2_information_content_design/RQ2_PILOT_DISCLOSURE_AND_HOLDOUT_AMENDMENT.md` | Exact discovery dates and prospective-extension separation |
| 2, 3, 5 | QA contract | `reports/robinhood_chain_pilot/rq2_information_content_design/RQ2_STOCK_DATA_QA_CONTRACT.md` | Raw basis, official prices, exact gates, deterministic exclusions |
| 4–6 | Final report | `reports/robinhood_chain_pilot/rq2_information_content_design/RQ2_PRIMARY_PROSPECTIVE_RESULTS.md` | Frozen 43-row sample and no post-result sample/QA changes |
| 6 | Closure audit | `reports/robinhood_chain_pilot/rq2_information_content_design/closure_audit/rq2_closure_audit.md` | Mandatory/candidate/post-outcome sensitivity classification |
| 6 | Mandatory sensitivity | `reports/robinhood_chain_pilot/rq2_information_content_design/common_5m_vs_30m/common_5m_vs_30m_summary.md` | Completion of the sole mandatory sensitivity |
| 3, 5, 6 | Final diagnostic | `reports/robinhood_chain_pilot/rq2_information_content_design/e3_temporal_localization/e3_temporal_summary.md` | Severe QA attrition and retained identification limitation |
| 6 | Preregistration | `reports/hypothesis_5b/h5b_vt20_preregistration.md` | Prohibition of proxy tournament and result-driven alternatives |
| 6 | Preregistration | `reports/hypothesis_6/h6_daily_amount_preregistration.md` | Frozen own-history design and specification-search boundary |
| 6 | Archival synthesis | `reports/H5_H8_RESEARCH_HISTORY.md` | Verified H5→H8 sequence as distinct evidence cycles |

## Archival validation

No hypothesis, backtest, sensitivity, model, factor performance calculation, or data acquisition was rerun. No external source was used, and no frozen input, outcome, QA threshold, universe, or experiment output was changed. The six lessons remain the human-approved lessons; every concrete project example is traceable to the source map. Outcome-seen exploration is labeled as exploration or a later evidence cycle, human judgment is treated as a documented input rather than a defect, and “freeze the claim, not the curiosity” is preserved without overstating the project's causal, production, or institutional maturity.
