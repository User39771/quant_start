# Commercial-space event study specification v1.3

## Stage metadata

- `stage`: `phase_1_evidence_readiness_spec`
- `version`: `1.3`
- `status`: `phase_1_complete_phase_2_blocked`
- `assessment_date`: `2026-07-11`
- `model_effort`: `gpt-5.6-sol high`
- `event`: `长征十号乙首飞及一级火箭成功回收`
- `event_date`: `2026-07-10`
- `verified_event`: `true` (user-confirmed; not re-verified)
- `event_truth_reverification_required`: `false`
- `implementation_status`: `not_started`; this phase specifies the study only
- `inputs`: `data/processed/backtest_universe_research_v1_2.csv`; `data/cache/price/*.csv`; `data/processed/formal_price_panel_v1_2.csv`; `data/processed/formal_benchmark_panel_v1_2.csv`; `data/processed/formal_trade_calendar_v1_2.csv`; official URLs in the evidence CSV
- `outputs`: `reports/commercial_space_event_evidence_v1_3.csv`; `reports/commercial_space_event_readiness_v1_3.csv`; this specification
- `changed_files`: exactly the three outputs above
- `overall_readiness`: `blocked` until complete stock-window prices and benchmarks exist
- `blockers`: G1 event-window prices and G2 benchmarks/control
- `next_stage_recommendation`: wait until event day `+5` is observable, fetch/validate data, rerun all gates, then implement phase 2 without changing the freeze

## Timing conclusion

The launch occurred at 12:15 China Standard Time on Friday 2026-07-10 and first-stage recovery followed about six minutes later. The outcome therefore occurred during the 11:30-13:00 midday break. The earliest located official web page with minute-level publication metadata is the Beijing Economic-Technological Development Area page stamped 14:43, during afternoon trading. CASC and CNSA pages carry the same date but no publication minute.

For a daily study, the first tradable reaction day and `t=0` are 2026-07-10; trading resumed at 13:00. The close-to-close `t=0` return includes both the pre-event morning and the post-event afternoon, so it cannot identify an intraday causal reaction. If an authoritative source later establishes that first public disclosure was after 15:00, shift `t=0` to the next exchange trading day and rebuild every window. No shift is applied under current evidence.

## Prior expectations

The outcome was not wholly unanticipated. A February 2026 China Manned Space Agency disclosure documented controlled splashdown and retrieval work for the Long March 10 first stage. A government-hosted report dated 2026-04-17 explicitly described an expected Long March 10B first flight with a sea net-recovery test, although its forecast date did not occur and it was not operator guidance. Treat the successful controlled net capture as the realized outcome against a partially anticipated attempt, and report `[-5,-1]` pre-drift rather than assigning all movement to new information on `t=0`.

## Frozen stock set

Freeze the 12 unique `theme=商业航天` rows in `data/processed/backtest_universe_research_v1_2.csv`. The file was created on 2026-07-05, before the event, and has SHA-256 `E468C04445CC19E158A7F0ED2F875A92660BC827A7C0860A169157377C7EABF5`. Its company evidence URLs are dated before the event and each row is marked `theme_confirmed` with `strong` evidence. No stock may be added or removed using returns observed on or after 2026-07-10.

The file metadata and underlying company-evidence dates are consistent with a pre-event selection, but the universe CSV is untracked in Git and no independent timestamped snapshot was located. Therefore event-date membership is unverified, not proven point-in-time. Before phase 2, preserve an external or version-controlled pre-event provenance record if one exists; otherwise disclose the set as a current file whose pre-event status cannot be independently established. It is not a historical constituent series for earlier placebo dates.

### Multi-theme handling

The v1.2 source is row-per-stock-theme. Build the event-study sample by unique stock code, not by source row. `002049 紫光国微` is the only overlap (`AI|商业航天`): include it once with one equal weight in the primary sample, retain both labels as metadata, and report a pre-registered sensitivity excluding it. Never duplicate returns, weights, or denominators because a stock has multiple themes.

## Registered windows and data

Use an exchange trading-day index:

- Diagnostic event window: `[-5,+5]`.
- Immediate reaction: `[0,+1]`.
- Short reaction: `[0,+5]`.
- Pre-drift diagnostic: `[-5,-1]`.
- Liquidity baseline: `[-25,-6]`.

Require adjusted daily close, amount, and consistently scaled turnover for every stock from `t=-26` through `t=+5` so the `t=-25` return has a prior close. Require benchmark closes over the same dates. Do not forward-fill or backfill. A suspension produces a missing stock-day return and a disclosed denominator change, not a zero return. The primary complete-window estimate requires all 12 names to have every required return in the stated window; an available-case daily panel may be shown only as a labelled diagnostic.

## Returns, abnormal returns, and CAR

For stock `i`, benchmark `m`, and trading day `t`:

`R_it = P_it / P_i,t-1 - 1`

`R_mt = M_t / M_t-1 - 1`

`AR_it,m = R_it - R_mt`

`CR_i[a,b] = product(t=a..b)(1 + R_it) - 1`

`CAR_i,m[a,b] = sum(t=a..b) AR_it,m`

Use the conventional additive CAR as primary. Report geometrically compounded raw cumulative returns separately; do not label compounded abnormal returns as CAR. This is a market-adjusted design, not an estimated market model.

## Benchmarks and control

Report each result without selecting the most favorable adjustment:

1. Raw stock return and cumulative raw return.
2. CSI 1000 (`000852`) market-adjusted abnormal return and CAR as the primary broad benchmark.
3. ChiNext Index (`399006`) adjustment for all names as a sensitivity and as the designated matched-board benchmark for `300xxx/301xxx` names.
4. Commercial-space control adjustment only if a pre-existing concept/industry index has auditable instrument identity, dates, and constituents. Otherwise report this control as unavailable; do not construct it from post-event winners or current constituents.

The commercial-space control is exposed to the event and is therefore a theme-adjusted sensitivity, not an untreated causal control. Validate that `000852` is the CSI 1000 index rather than the same-code Shenzhen stock and that `399006` is the ChiNext index.

## Cross-sectional and liquidity outputs

For each trading day and registered window, report:

- Equal-weight mean and median raw return/cumulative return.
- Equal-weight mean and median abnormal return/CAR for each valid benchmark/control.
- Positive-return share, positive-abnormal-return share, valid-name count, and frozen-name count.
- Per-stock amount ratio `amount_t / median(amount[-25,-6])` and amount change `amount_t / median(amount[-25,-6]) - 1`; summarize both by equal-weight mean and median.
- Per-stock turnover change versus median turnover over `[-25,-6]`, with mean, median, units, and valid count.
- Primary unwinsorized estimates plus a fixed 5th/95th percentile winsorized sensitivity; never tune cutoffs after seeing the event.

Equal weights are over unique stock codes with valid observations for that metric. Freeze membership and disclose every denominator change.

## Placebos and pre-drift

Draw non-overlapping pseudo-event dates from the prior 120 exchange trading days, weekday-matched where feasible. Exclude dates whose `[-5,+5]` windows overlap the true event window or another selected placebo. Apply the identical 12-code freeze, windows, benchmark rules, amount metrics, and aggregation. Report the true statistic's percentile in the placebo distribution; do not call it a causal p-value.

Because the set is not independently proven point-in-time, label all earlier placebos `unverified_event_date_universe_placebo`. Report `[-5,-1]` raw cumulative return, benchmark-adjusted CAR, and amount change beside the event windows to expose anticipation or leakage.

## Gates and QA

No return, abnormal-return, CAR, or amount-reaction output may be produced until all required gates pass:

| Gate | Status | Pass condition |
|---|---|---|
| Event-window prices | Fail | All 12 stocks have validated adjusted close, amount, and turnover through `+5`, with exact window endpoints and logged failures. |
| Benchmarks/control | Fail | Index-level `000852` and `399006` cover the common window; the commercial-space control is validated or explicitly unavailable. |
| Frozen pre-event set | Unverified | Exactly 12 unique v1.2 commercial-space codes and `002049` is counted once, but an untracked file's modification time and current hash do not independently prove pre-event existence. |
| Announcement timestamp | Pass for daily | Earliest located exact official web timestamp is 14:43 during trading; same-day `t=0` and after-close shift rule are explicit. |

Phase 2 QA must confirm unique stock-date and benchmark-date keys, leading-zero preservation, positive adjusted closes, non-negative amount, consistent turnover units, exact return endpoints, calendar alignment, immutable membership, recorded download failures, and reproducibility of every CAR from daily abnormal returns.

## Interpretation limits

This single event cannot establish causality or a repeatable trading strategy. Daily data mix pre-event morning and post-event afternoon trading. Prior expectations and pre-drift can reduce the measured post-event surprise. The theme control is contaminated by the event. Membership's pre-event status is not independently proven, and earlier placebos do not use historical membership. Results, if phase 2 later passes its gates, are research evidence rather than investment advice.

## Commands and exit codes

| Command / operation | Exit code |
|---|---:|
| `rg --files reports` and targeted repository searches | 0 |
| `git status --short` (dirty-worktree inspection only) | 0 |
| PowerShell `Import-Csv` v1.2 universe, overlap, file-date, SHA-256, and cache-coverage checks | 0 |
| Official-source web search/open for timing, exchange rules, and prior expectations | N/A |
| Final CSV/schema/content QA command | 0 |

The stage made no network data fetch, no event-study implementation, and no writes outside the three declared outputs.
