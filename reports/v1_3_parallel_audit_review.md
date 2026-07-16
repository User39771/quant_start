# v1.3 Parallel Audit Review

## Stage metadata

- status: `completed_gate_review`
- inputs: the five phase-1 audit workstreams, frozen v1.2 artifacts, current MOM60 v1.3 artifacts, and targeted source inspection
- outputs: `reports/v1_3_parallel_audit_review.md`
- changed_files: this report only
- commands: targeted `Get-Content`, `Import-Csv`, `rg`, and `git status --short` checks; subagent commands are recorded in their reports
- exit_codes: main-thread inspection commands `0`; subagent audits `0`
- QA summary: all required phase-1 reports exist; output paths are disjoint; no phase-2 writer was run
- blockers: event prices and benchmarks do not cover the event window; QFQ network repairs would create a new data lineage and require downstream reruns
- next-stage recommendation: complete final frozen-file and test verification; defer QFQ repair and event-study implementation

## Subagent review

| Workstream | Model / effort | Status | Main-thread review |
|---|---|---|---|
| Repository cartography | gpt-5.6-terra / medium | pass | Producer paths, baseline `common_calendar()`, `evaluate_period()`, and overwrite risks match targeted source inspection. Understand Anything was not directly callable without creating graph artifacts, so the agent used its method and verified claims against source. |
| MOM60 freeze | gpt-5.6-sol / high | pass | `verdict=not_supported`; focused tests 9/9 and persisted critical QA 14/14 passed. MOM40/60/80 all oppose the registered momentum direction. REV60 was not run. |
| QFQ gap inventory | gpt-5.6-terra / medium | pass with caveats | Inventory distinguishes network gaps, cache/panel reconciliation, and stock-calendar differences. It finds two complete failures (`002544`, `300133`), three partial caches, and one material endpoint gap for `002049`. Cache-only reconciliation rows are not proof that a full adjusted panel can be rebuilt without matching raw-base rows. |
| VOL20 / Liquidity20 readiness | gpt-5.6-terra / medium | conditional | Both are research-only candidates. VOL20 is exposed to false low volatility from unlabelled halts. Amount-based Liquidity20 is possible, but volume is absent and turnover/circulating-cap point-in-time contracts are not verified. Execution simulation remains blocked. |
| Commercial-space event specification | gpt-5.6-sol / high | phase 1 documented; phase 2 blocked | Current set contains 12 unique commercial-space stocks, with `002049` counted once. Its pre-event point-in-time provenance is unverified because the source CSV is untracked. Daily timing is documented, but no local stock or benchmark data covers the event window. |

## Source and lineage checks

The active baseline producer is `scripts/run_adjusted_stock_pool_baseline_v1_2.py`. Its `common_calendar()` uses valid adjusted stock dates intersected with valid HS300 dates. Its `evaluate_period()` defines eligibility from the rebalance-date price only; an eligible stock missing the end price invalidates the period rather than being removed retrospectively. The MOM60 runner separately uses HS300 dates as its market-calendar authority and verifies baseline endpoints against that calendar.

The active adjusted-return chain is:

```text
stock pool v1.2
-> research universe v1.2
-> raw-base and benchmark panels v1.2
-> QFQ enrichment and adjusted panel v1.2
-> adjusted baseline v1.2
-> attribution v1.2
-> MOM60 research v1.3
```

No audit changed these inputs or their producers.

## Gate decisions

### MOM60

- decision: `frozen_not_supported`
- Momentum Strategy v1.4: `not_allowed`
- reversal observation: `post_hoc_exploratory_only`
- reversal confirmed: `false`

### QFQ repair

- decision: `not_approved_in_this_sprint`
- reason: the frozen adjusted panel already passed its research-baseline gate and the frozen MOM60 study completed. The remaining network repairs would create a materially different v1.3 panel and require a versioned baseline, attribution, and factor rerun. Cache-only reconciliation also cannot manufacture raw-base rows absent from the existing panel.
- future trigger: approve a separate versioned repair only when a downstream study requires the missing endpoints, with `data/cache/qfq_repair_v1_3/`, hashes, source manifests, and no v1.2 overwrite.

### Event-study implementation

- decision: `blocked`
- G1 event-window prices: fail; all 12 local stock files end on 2026-06-16.
- G2 benchmarks: fail; required index histories do not cover the event window and the same-code `000852` stock cache is not the CSI 1000 index.
- G3 frozen pre-event set: unverified; current hash and file modification time do not independently prove pre-event existence.
- G4 announcement timing: pass for a daily design only.
- implementation may begin only after event `+5` is observable, G1/G2 pass, and G3 provenance is resolved or explicitly accepted by the user as a non-point-in-time limitation.

### Remaining factor candidates

- VOL20: may proceed only to a separately preregistered research plan. Exact 21-price windows and a suspension/flat-price diagnostic are mandatory. It is not execution-ready.
- Liquidity20: only an amount-based research definition may proceed to a separate plan. Volume-based and capacity/execution claims are unavailable; turnover/cap-normalized variants require documented units and point-in-time lineage.
- priority: VOL20 is the cleaner next hypothesis because it uses the already-audited adjusted-price lineage. This is approval to write a future plan, not approval to run a factor test.

## Conflict and freeze review

The five agents wrote distinct report paths. None wrote a cache, adjusted panel, baseline, attribution artifact, factor artifact, or shared script. The repository was already materially dirty before this sprint; unrelated tracked and untracked files remain untouched. Final verification must compare the pre-sprint v1.2 hash snapshot with a fresh post-sprint snapshot and run focused regression tests before completion.

## Decisions still requiring user approval

1. Whether to open a separate, versioned QFQ repair sprint when the missing endpoints become necessary.
2. Whether VOL20 should receive the next preregistered hypothesis plan.
3. Whether to acquire point-in-time amount/volume/trading-status data before pursuing Liquidity20.
4. Whether to resume the event study after `+5` prices and both index benchmarks are available.

No investment conclusion is produced.
