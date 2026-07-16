# Quant Research v1.3 Coordinated Sprint Summary

## Executive decision

The sprint is complete at the audit and stage-gate level. All independently executable phase-1 audits were delivered and reviewed. No conditional implementation was approved:

- MOM60 remains frozen as not_supported; Momentum Strategy v1.4 is prohibited.
- QFQ repair is deferred because the frozen baseline and factor study already passed, while repair would create a new data lineage requiring versioned downstream reruns.
- Commercial-space event-study implementation is blocked by missing event-window prices, missing index benchmarks, and unverified pre-event membership provenance.
- VOL20 and amount-based Liquidity20 are conditional research candidates only. Neither is execution-simulation ready.

No investment advice or new strategy-performance conclusion was produced.

## 1. Subagent allocation

| Workstream | Agent role | Model / effort | Output |
|---|---|---|---|
| Repository cartography | repository/data-lineage audit | gpt-5.6-terra / medium | project_structure_for_v1_3.md |
| MOM60 freeze | methodology and result audit | gpt-5.6-sol / high | mom60_v1_3_freeze_review.md |
| QFQ gaps | mechanical cache/endpoint inventory | gpt-5.6-terra / medium | qfq_gap_inventory_v1_3.csv/.md |
| Remaining factors | VOL20/Liquidity20 readiness | gpt-5.6-terra / medium | two readiness CSVs and one report |
| Event study | evidence/readiness/specification | gpt-5.6-sol / high | event evidence, readiness, and spec |
| Independent final review | gate and methodology review | gpt-5.6-sol / high | read-only findings returned to coordinator |

All phase-1 writers owned disjoint report paths. The main thread performed source checks, gate decisions, final tests, frozen-file verification, and corrections raised by independent review.

## 2. Completed tasks

1. Repository structure and full active data lineage documented.
2. Baseline calendar and eligible_codes semantics verified against source.
3. MOM40/60/80 results reconciled and MOM60 frozen.
4. QFQ cache, manifest, adjusted-panel, baseline endpoint, and factor endpoint gaps inventoried.
5. VOL20 and Liquidity20 data readiness assessed without running factor tests.
6. Confirmed-event timing, stock-set rules, windows, benchmark design, placebos, and interpretation limits specified.
7. Main stage-gate review completed.
8. Independent final review completed; event-membership and QFQ-repairability claims were tightened.
9. Focused regressions, schema checks, key checks, and frozen-file hashes verified.

## 3. Tasks not implemented

- No QFQ v1.3 repair cache or adjusted panel was created.
- No baseline, attribution, or factor artifact was regenerated.
- No event-study return calculation was implemented.
- No VOL20 or Liquidity20 hypothesis test was run.
- No reversal factor or Momentum Strategy v1.4 was created.

These are gate decisions, not incomplete silent work.

## 4. Blockers

| Area | Blocker |
|---|---|
| Event prices | All 12 local stock files end at 2026-06-16; event day and +5 are unavailable. |
| Event benchmarks | Required index-level 000852 and 399006 event-window histories are absent; the local same-code 000852 cache is an individual stock. |
| Event membership | The current 12-stock CSV is untracked. Its modification time and current hash do not independently prove pre-event existence. |
| QFQ repair | Two complete failures, three partial caches, and endpoint gaps need a new versioned lineage; 12 inventory rows require network repair. |
| VOL20 | No explicit historical suspension/trading-state data; flat close sequences can produce false low volatility. |
| Liquidity20 | Volume is absent; turnover units/denominator and circulating-cap vintages are not source-certified. |
| Execution simulation | Historical ST, suspension, price-limit, fill, participation, and complete cost data remain unavailable. |

## 5. Changed files

Only these v1.3 reports were created or revised:

    reports/project_structure_for_v1_3.md
    reports/mom60_v1_3_freeze_review.md
    reports/qfq_gap_inventory_v1_3.csv
    reports/qfq_gap_inventory_v1_3.md
    reports/factor_readiness_vol20_v1_3.csv
    reports/factor_readiness_liquidity20_v1_3.csv
    reports/remaining_hypotheses_readiness_v1_3.md
    reports/commercial_space_event_evidence_v1_3.csv
    reports/commercial_space_event_readiness_v1_3.csv
    reports/commercial_space_event_study_spec_v1_3.md
    reports/v1_3_parallel_audit_review.md
    reports/v1_3_coordinated_sprint_summary.md

No source script, test, cache, panel, baseline, attribution, factor-result, or stock-pool file was changed by this sprint.

## 6. Frozen-file verification and evidence scope

A SHA-256 snapshot was taken before subagent writes for every file under data/processed, data/cache, and reports whose full path contains v1_2.

- before files: 105
- after files: 105
- path/hash differences: 0
- result for this 105-file scope: pre/post cryptographic match

Snapshots are outside the repository at %TEMP%/quant_start_v1_2_hashes_before.csv and %TEMP%/quant_start_v1_2_hashes_after.csv.

The initial snapshot accidentally omitted data/stockPool, although that directory is also part of the frozen contract. A current SHA-256 inventory records 10 matching-path files at %TEMP%/quant_start_stockpool_v1_2_current.csv; their latest modification time is 2026-07-05 00:07:36 +08:00, before this sprint, and no agent or main-thread command had a stockPool write path. Therefore no stockPool mutation was observed, but this subset lacks cryptographic pre/post proof. The completion claim is deliberately limited to the evidence available rather than describing all frozen files as hash-compared.

## 7. Commands and exit codes

| Command | Exit |
|---|---:|
| python -m unittest tests.test_adjusted_stock_pool_baseline_v1_2 -v | 0 |
| python -m unittest tests.test_baseline_attribution_v1_2 -v | 0 |
| python -m unittest tests.test_mom60_hypothesis_v1_3 -v | 0 |
| python -m unittest tests.test_adjusted_price_panel_QA_v1_2 -v | 0 |
| v1.3 report schema/key checks | 0 |
| adjusted/factor panel key, code, and date checks | 0 |
| frozen v1.2 processed/cache/report pre/post hash comparison | 0 |
| stockPool current hash and modification-time inventory | 0 |
| git diff --check | 1 |

git diff --check reports a pre-existing blank line at EOF in modified README.md plus line-ending warnings in pre-existing dirty files. This sprint did not edit those files. The project-instruction live run_research.py command was intentionally not run because it is an older generic writer, may fetch data, and would mutate unrelated non-frozen outputs; it is not a validator for this v1.2/v1.3 lineage.

## 8. Test and QA summary

- adjusted baseline: 19/19 tests passed
- attribution: 7/7 tests passed
- MOM60: 9/9 tests passed
- adjusted-panel QA: 11/11 tests passed
- total focused regressions: 46/46 passed
- QFQ inventory: 133 rows, required columns present, no duplicate stock_code/gap_type, all codes six digits
- event evidence: 19 unique records
- event readiness: 5 unique gates; overall blocked
- adjusted panel: 70,145 rows, no duplicate stock/date, all six-digit codes, no invalid dates
- MOM60 factor panel: 3,192 rows, no duplicate period/code, all six-digit codes

## 9. Data repair comparison

No data repair was approved, so there is no repaired panel to compare:

- v1.2 data changes: 0
- new QFQ cache files: 0
- live fetches: 0
- baseline/factor reruns: 0

The QFQ inventory finds complete failures for 002544 and 300133, partial caches for 002049, 002131, and 301171, one known baseline endpoint gap for 002049, 12 network-required inventory rows, and 95 cache/panel reconciliation rows. The 95 reconciliation rows are diagnostic. A QFQ cache row cannot create an adjusted-panel date when the raw-base left side lacks that date.

## 10. Readiness conclusions

### MOM60

- verdict: not_supported
- historical-validation mean Rank IC: -0.1264474594
- historical-validation mean Q5-Q1: -0.0368879058
- MOM40/60/80: consistently negative for the registered momentum direction
- momentum_strategy_prototyping_allowed: false
- reversal observation: post_hoc=true, reversal_confirmed=false

### VOL20

- availability: partially_available
- stock coverage with at least one exact window: 54/56
- research allowed: conditional
- execution simulation allowed: false
- next action: a separate preregistered plan with exact 21-close windows and explicit suspension/flat-price diagnostics

### Liquidity20

- availability: partially_available
- amount-based exact-window research: conditional
- volume-based research: unavailable
- turnover/cap-normalized research: blocked pending unit and point-in-time lineage
- execution simulation allowed: false

VOL20 is the cleaner candidate for the next plan because it stays within the audited adjusted-price lineage. This does not authorize a test.

## 11. Event-study status

- confirmed event fact: retained as user-confirmed
- truth re-verification: not performed
- daily timing evidence: documented
- event-window prices: fail
- benchmarks: fail
- current 12-stock membership cardinality: verified
- pre-event point-in-time provenance: unverified
- implementation: blocked

Phase 2 requires event +5 prices, valid index benchmarks, and either proof of pre-event membership provenance or explicit user acceptance of the non-point-in-time limitation.

## 12. Methodology corrections from independent review

The final reviewer initially rejected sprint completion on four points. They were handled as follows:

1. Frozen checksum/test evidence: 105 processed/cache/report files have full pre/post proof. The omitted stockPool subset has current hashes, pre-sprint timestamps, and no observed write path; the limitation is disclosed rather than overstated.
2. Event membership: G3 changed from pass to unverified.
3. MOM60 output contract: the structure report now records the writer's actual generic and MOM60-specific filenames; all are frozen for future studies.
4. QFQ repairability: cache/panel rows are now described as lineage reconciliation, not automatically cache-repairable.

No conditional implementation became eligible after these corrections.

## 13. Reproducibility

Every audit report records inputs, outputs, changed files, commands, exit codes, QA, blockers, and next-stage recommendation. Phase-1 audits did not fetch data. All generated files are CSV or Markdown and can be inspected without a proprietary runtime.

## 14. Suggested next hypothesis

The next defensible research-planning candidate is VOL20, provided its future plan preregisters signal at T-1 on the authoritative market calendar, exactly 21 close observations for 20 returns, no filling or stock-specific date substitution, a halt/flat-price diagnostic, and research-only interpretation with current-universe bias. This sprint does not approve implementation or claim that low volatility works.

## 15. Decisions requiring user approval

1. Approve or reject a separate VOL20 hypothesis plan.
2. Decide whether a future QFQ v1.3 repair is worth a full versioned downstream rerun.
3. Supply or approve acquisition of point-in-time volume, turnover, float-cap, and trading-status data before Liquidity20/execution work.
4. Provide a timestamped pre-event stock-pool snapshot if one exists, or explicitly accept the event set as non-point-in-time.
5. Resume event-study preparation only after +5 data and valid benchmarks are available.

## Fixed conclusion boundary

- formal_performance_conclusion_allowed=false
- execution_sim_ready=false
- no_investment_conclusion=true
