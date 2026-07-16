# Project Structure for v1.3

## Stage Metadata

| Field | Value |
|---|---|
| model / effort | gpt-5.6-terra medium |
| status | completed: read-only repository cartography |
| inputs | current dirty worktree; source scripts; tests; existing v1.2/v1.3 artifacts; Git status |
| outputs | this report only |
| changed_files | `reports/project_structure_for_v1_3.md` |
| commands | `rg --files`; targeted `rg`; `Get-Content`; `Import-Csv`; `git status --short`; `git log --oneline -12` |
| exit_codes | source-inspection commands completed with `0`; two PowerShell wildcard read attempts returned nonzero because PowerShell did not expand the wildcard, then targeted `rg --glob` commands succeeded; no pipeline was run |
| QA summary | lineage claims were verified against the named producers and focused tests; current gate reports were read, not regenerated |
| blockers | worktree is materially dirty and concurrent work owns source/data/report paths. The required live `run_research.py` command was intentionally not run: it writes outside this task's sole permitted output. |
| next-stage recommendation | freeze/checksum the v1.2 input contract, then use explicitly versioned v1.3 writers in serialized order. |

`Understand Anything` was available as an installed skill but not callable as a direct tool in this task. Its full graph workflow would write `.understand-anything/` artifacts, which conflicts with the sole-output restriction. Conclusions below were independently verified from source.

## Directory Structure

```text
quant_start/
  src/aq_factor_lab/                 reusable research library
    data_layer/                      cache-first AkShare public-data service
    data_collection/                 bounded thematic data collector
  scripts/                           executable pipelines, diagnostics, research writers
  data/
    stockPool/                       auditable v1.2 pool ledger and pool builder
    cache/price/                     legacy raw cache
    cache/qfq_enrichment_v1_2/       per-symbol qfq cache
    processed/                       versioned panels, universes, manifests
    collected/                       thematic collector outputs
  reports/                           QA, baseline, attribution, and v1.3 research artifacts
  tests/                             unittest coverage, including script-level imports
  config/, configs/                  mapping, purity rules, and thematic config
  unused/                            non-active material
```

The generic `scripts/run_research.py` invokes the older package CLI. It is not the v1.2 adjusted-baseline lineage and must not regenerate frozen artifacts.

## Active Chain and Producers

```text
data/stockPool/*_v1_2.csv
  -> prepare_backtest_data_v1_2.py
  -> backtest_universe_{research,expanded_only}_v1_2.csv
  -> build_hybrid_reusable_data_v1_2.py
  -> raw_base_price_panel_v1_2.csv + hybrid_benchmark_panel_v1_2.csv
  -> enrich_qfq_slow_v1_2.py
  -> qfq_enrichment_panel_v1_2.csv + adjusted_price_panel_v1_2.csv
  -> build_adjusted_price_panel_QA_v1_2.py
  -> run_adjusted_stock_pool_baseline_v1_2.py
  -> adjusted_stock_pool_baseline_{periods,nav,summary,qa}_v1_2.csv
  -> analyze_baseline_attribution_v1_2.py
  -> baseline_attribution_{period_stock,stock,theme,summary,qa}_v1_2.csv
  -> test_mom60_hypothesis_v1_3.py
  -> mom60_factor_panel_v1_3.csv + factor_*_mom60_v1_3 outputs
```

| Stage | Producer | Inputs | Outputs it writes or overwrites |
|---|---|---|---|
| stock-pool | `data/stockPool/build_stock_pool_v1_2.py` | rule/decision inputs in `data/stockPool/` | pool rules, suggestions, default/expanded/excluded/resolution CSVs and QA markdown |
| universe/inventory | `scripts/prepare_backtest_data_v1_2.py` | expanded/default v1.2 pools, legacy price cache | two universes, unverified smoke price panel, inventory/readiness/reorg reports |
| raw + benchmarks | `scripts/build_hybrid_reusable_data_v1_2.py` | research universe, `data/cache/price/`, Tencent index fetch | raw-base panel, hybrid benchmark panel, manifest, gaps/readiness reports |
| qfq enrichment | `scripts/enrich_qfq_slow_v1_2.py` | research universe, raw-base panel, qfq cache/live Sina then Eastmoney | qfq cache, qfq panel, adjusted panel, manifest, failures/readiness |
| adjusted-panel QA | `scripts/build_adjusted_price_panel_QA_v1_2.py` | adjusted panel, qfq manifest, raw-base panel, research universe | adjusted-panel issues, summary, markdown QA |
| baseline | `scripts/run_adjusted_stock_pool_baseline_v1_2.py` | research/expanded universes, adjusted panel, hybrid benchmarks | adjusted baseline periods, NAV, summary, QA, markdown |
| attribution | `scripts/analyze_baseline_attribution_v1_2.py` | baseline periods/NAV, adjusted panel, research universe | period-stock, stock, theme, summary, QA CSVs and markdown |
| factor research | `scripts/test_mom60_hypothesis_v1_3.py` | baseline periods, adjusted panel, research universe, hybrid benchmarks | MOM40/60/80 panel/readiness/IC/quantile/stability/hypothesis/QA artifacts and markdown |

Current artifact cardinalities support this lineage: the research universe has 57 rows but 56 unique stocks; the expanded universe has 56 rows; the adjusted panel has 70,145 rows; the hybrid benchmark panel has 4,686 rows; baseline periods/NAV have 316/684 rows.

## Calendar and Eligibility Contract

The authoritative baseline calendar is `common_calendar()` in `scripts/run_adjusted_stock_pool_baseline_v1_2.py:131`: sorted intersection of all valid qfq stock dates and valid positive-close HS300 (`000300`) dates. `rebalance_boundaries()` advances exactly 20 entries, marking a final shorter interval `partial`. This is the only baseline calendar.

There is no function named `eligible_codes`; it is a baseline period-output field constructed by `evaluate_period()` at `scripts/run_adjusted_stock_pool_baseline_v1_2.py:169`:

1. Normalize and deduplicate the fixed universe upstream.
2. Select only universe codes with a valid qfq price on the rebalance/start date.
3. Sort them and join them with `;`; record all start-ineligible codes separately.
4. Give every eligible code equal target weight.
5. Require coverage of at least 0.80 and require every selected code to have an end-date price. A missing end price invalidates the full period rather than reweighting survivors.

Attribution's `parse_eligible_codes()` and factor research's `parse_codes()` require exact `eligible_count`, six numeric digits, and no duplicates. Attribution replays only these codes. MOM60 keeps every research-universe stock in its panel but marks the inherited eligible list as `baseline_eligible`.

The MOM60 writer deliberately uses a related but different calendar: all unique valid HS300 dates in `market_calendar()` (`scripts/test_mom60_hypothesis_v1_3.py:71`) and rejects any baseline endpoint not in it. It does not license weekday calendars, other index calendars, forward fill, backfill, or raw-close fallback.

## Data Lineage and Authority

- **Universe:** `prepare_backtest_data_v1_2.py` produces `backtest_universe_research_v1_2.csv` by concatenating default and expanded pool rows; it is current-universe history and retains survivorship risk.
- **Raw base panel:** the hybrid builder normalizes `data/cache/price/*.csv` to `raw_base_price_panel_v1_2.csv`; raw rows are not adjusted return inputs.
- **QFQ cache/panel:** enrichment uses a complete per-symbol cache when available, otherwise tries Sina then Eastmoney. It writes `data/cache/qfq_enrichment_v1_2/<code>.csv`, `qfq_enrichment_panel_v1_2.csv`, and a fetch manifest/failure log.
- **Adjusted panel:** enrichment joins raw and qfq data into `adjusted_price_panel_v1_2.csv`. Baseline accepts only `adjusted_flag=true` records with positive `adjusted_close == qfq_close` (tolerance `1e-10`); it never falls back to raw close.
- **Benchmark:** baseline consumes `hybrid_benchmark_panel_v1_2.csv`; required hybrid series are HS300 (`000300`) and CSI 1000 (`000852`), with ChiNext (`399006`) optional. HS300 is the calendar anchor.
- **Formal branch:** `fetch_formal_data_v1_2.py` writes `formal_{price,benchmark,trade_calendar,price_fetch_manifest}_v1_2.csv`, using `aq_factor_lab.data_layer`. The current formal readiness report says `formal_ready: false`, coverage `1/5`, missing `000300,000852`, and 10 critical failures. It is an alternative/partial branch, not a baseline input.

Current adjusted-panel QA allows the research baseline: 56 universe stocks, 96.359% row coverage, 96.429% stock coverage, and no duplicate stock-date keys. It explicitly keeps `formal_performance_conclusion_allowed=false` and `execution_sim_ready=false`.

## Frozen v1.2 Contract

Treat these as immutable v1.3 inputs. Do not regenerate them in place.

1. `data/stockPool/{default_pool,expanded_pool,pool_decision_suggestions,excluded_by_rules,excluded_by_business_mismatch,rule_exception_resolution,stock_pool_rules}_v1_2.csv` and `stock_pool_v1_2_QA_report.md`.
2. `data/processed/{backtest_universe_research,backtest_universe_expanded_only,raw_base_price_panel,qfq_enrichment_panel,qfq_fetch_manifest,adjusted_price_panel,hybrid_benchmark_panel,hybrid_data_manifest}_v1_2.csv`.
3. `reports/{adjusted_price_panel_QA,adjusted_price_panel_summary,adjusted_price_panel_issues,qfq_enrichment_readiness,qfq_enrichment_failures,hybrid_reusable_data_readiness,hybrid_data_gaps}_v1_2.*`.
4. Every `reports/adjusted_stock_pool_baseline_*_v1_2.*` and `reports/baseline_attribution_*_v1_2.*` artifact.

## Allowed v1.3 Writes

For this task, the sole allowed write is this report. For an approved MOM60 rerun on the same frozen inputs, the existing writer targets only:

- `data/processed/mom60_factor_panel_v1_3.csv`
- `reports/factor_ic_periods_mom60_v1_3.csv`, `factor_ic_summary_mom60_v1_3.csv`, `factor_quantile_returns_mom60_v1_3.csv`, `factor_quantile_summary_mom60_v1_3.csv`, and `factor_stability_mom60_v1_3.csv`
- `reports/factor_data_readiness_v1_3.csv`, `factor_hypothesis_summary_v1_3.csv`, and `factor_research_qa_v1_3.csv`
- `reports/factor_mom60_v1_3.md`

The three generic MOM60 report names above are occupied and must be treated as frozen. New hypotheses must use hypothesis-specific filenames and must not share any MOM60 path. A data refresh must use a new versioned panel, manifest, QA, baseline, and attribution family rather than reusing v1.2 names.

## Existing Test Coverage

Focused v1.2/v1.3 unittest modules cover the active contracts:

| Area | Tests |
|---|---|
| pool and universe construction | `test_stock_pool_v1_2_rules.py`, `test_prepare_backtest_data_v1_2.py` |
| raw/hybrid/formal/qfq ingestion | `test_build_hybrid_reusable_data_v1_2.py`, `test_fetch_formal_data_v1_2.py`, `test_enrich_qfq_slow_v1_2.py`, diagnostic tests |
| adjusted-panel gate and baseline | `test_adjusted_price_panel_QA_v1_2.py`, `test_adjusted_stock_pool_baseline_v1_2.py` |
| baseline attribution | `test_baseline_attribution_v1_2.py` |
| smoke diagnostic baseline | `test_stock_pool_smoke_baseline_v1_2.py` |
| MOM60 lineage | `test_mom60_hypothesis_v1_3.py` |
| new public data infrastructure | `test_data_layer.py`, `test_data_collection.py` |

These test exact endpoint requirements, no raw fallback, start-date eligibility, duplicate-code rejection, QFQ cache/fallback behavior, coverage gates, benchmark alignment, signal-before-label quantiles, and research boundaries. They were not executed because this task may not write outside the target report.

## Stale, Duplicate, and Overwrite Risks

| Candidate | Finding | Handling |
|---|---|---|
| formal v1.2 panels/calendar | alternate formal branch; not consumed by active baseline and currently not ready | retain as diagnostic evidence; do not substitute silently |
| `backtest_price_panel_v1_2.csv` | legacy smoke/unverified panel; formal fetch uses it only to infer date range | never use as adjusted-return source |
| `qfq_enrichment_panel_v1_2.csv` | intermediate qfq table | retain for audit; baseline reads the joined adjusted panel |
| `stock_pool_smoke_baseline_v1_2.*` | earlier smoke baseline | diagnostic only, not attribution/factor input |
| `scripts/test_mom60_hypothesis_v1_3.py` | executable report writer with a test-like filename | do not rename during research; document it as a writer |
| v1.2 writers | direct `to_csv`/`write_text` overwrite behavior; formal fetch can also `unlink` its target outputs on reset | serialize execution and snapshot/checksum before an approved rerun |
| generic CLI outputs | `run_research.py` writes generic processed/report artifacts outside the frozen lineage | keep it out of v1.2/v1.3 reproducibility work |

## Parallel Write Conflicts and Execution Order

| Parallel activity | Shared paths or semantic dependency | Required order |
|---|---|---|
| pool build vs prepare | stock-pool CSVs -> universe files | pool build, then prepare |
| hybrid build vs qfq enrichment | raw-base panel -> qfq/adjusted outputs | hybrid, then enrichment |
| enrichment vs adjusted QA/baseline | adjusted panel, qfq manifest/readiness | enrichment, then QA, then baseline |
| baseline vs attribution/MOM60 | baseline periods/NAV -> downstream readers | baseline completion and QA gate, then readers |
| attribution vs MOM60 | no direct output collision, both read frozen baseline/panel/universe | may run in parallel only after baseline is frozen |
| formal fetch vs active branch | no direct active baseline write collision, but competing source interpretation | isolate; never treat it as a replacement without migration approval |
| generic research CLI vs all report/data work | generic processed/report output names | do not run concurrently |

Recommended sequence:

1. Record Git status and checksum the frozen v1.2 files above.
2. Run focused tests before any writer. Do not run generic `run_research.py` as v1.2/v1.3 validation.
3. For new data, write a new versioned raw/qfq/adjusted family, then run its QA gate.
4. Build a matching versioned baseline using the HS300 intersection calendar and immutable `eligible_codes` semantics.
5. Run attribution and each factor study from that frozen baseline. Independent downstream studies may then run in parallel if their outputs are distinct.
6. Review QA/research status before interpretation. Existing MOM60 is completed but `not_supported`; it is research-only and says to stop that strategy direction.
