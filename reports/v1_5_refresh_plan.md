# v1.5 Full-Refresh Design and Current Gap Scan

## Scope and scan result

- stage: `Subagent C / first-stage read-only scan`
- status: `complete_with_refresh_required`
- run date: `2026-07-11`
- network requests: `0`
- cache/panel writes: `0`
- frozen artifacts changed: `0`
- universe input: `data/processed/backtest_universe_research_v1_2.csv` has 57 rows and exactly 56 unique six-digit codes. `002049` is intentionally present in two themes; the refresh universe is the deduplicated 56-code set.
- local authoritative-calendar maximum: `2026-06-16` from the existing `000300` benchmark panel. Stock qfq cache and benchmark panels also reach that date; raw-base `300378` stops at `2026-06-12`.
- inventory: `reports/v1_5_refresh_inventory.csv` contains 56 stock rows plus `000300`, `000852`, and `399006`.

## Existing v1.2 lineage

| Artifact | Existing source / implementation | Current use in v1.5 scan |
|---|---|---|
| qfq cache | `data/cache/qfq_enrichment_v1_2/*.csv`; writer `scripts/enrich_qfq_slow_v1_2.py` | Read-only baseline only; 54 cache files, with `002544` and `300133` absent. |
| raw-base panel | `data/processed/raw_base_price_panel_v1_2.csv`; legacy `data/cache/price/*.csv`; builder `scripts/build_hybrid_reusable_data_v1_2.py` | Date anchor and raw-data lineage only. |
| qfq / adjusted panels | `qfq_enrichment_panel_v1_2.csv`, `adjusted_price_panel_v1_2.csv`; writer `enrich_qfq_slow_v1_2.py` | Valid qfq rows are the sole adjusted-close input; raw close is not a substitute. |
| benchmark panel | `hybrid_benchmark_panel_v1_2.csv`; builder `build_hybrid_reusable_data_v1_2.py` | Calendar anchor and benchmark lineage only. |
| manifests | `qfq_fetch_manifest_v1_2.csv`, `hybrid_data_manifest_v1_2.csv`, `formal_price_fetch_manifest_v1_2.csv` | Records cache/panel lineage and historical failures; no mutation. |

## Data-source implementation findings

- Stock qfq producer: `scripts/enrich_qfq_slow_v1_2.py` uses `ak.stock_zh_a_daily(..., adjust="qfq")` first, then `ak.stock_zh_a_hist(..., adjust="qfq")`. It normalizes six-digit codes, dates, and positive `qfq_close`, and records both attempts in the manifest.
- Existing retry behavior is usable: `safe_fetch` has five attempts, 20-second timeout, and short randomized backoff. The v1.5 wrapper should preserve bounded retries/rate limiting and create new cache/manifest paths, never write v1.2 paths.
- Raw-base producer: `scripts/build_hybrid_reusable_data_v1_2.py` reads the legacy price cache and marks it `adjusted_flag=false`; it cannot supply qfq values.
- Index producers: the hybrid builder uses the index-only `ak.stock_zh_index_daily_tx` with `sh000300`, `sh000852`, and `sz399006`. The generic data layer also exposes `akshare.index_zh_a_hist`; it must be used only as a fallback after identity validation, never through a stock endpoint.

## Required refresh execution order

1. Create independent `data/cache/qfq_refresh_v1_5/` and `data/cache/benchmark_refresh_v1_5/`, then write an attempt-level manifest and failure CSV. Request all 56 unique stocks from `2020-01-02` through the latest available run-date trading day. Pre-listing absence is valid; failed symbols remain explicit failures.
2. For every stock, use `ak.stock_zh_a_daily` qfq, then `ak.stock_zh_a_hist` qfq. Validate schema, six-digit code, positive qfq prices, sorted unique dates, and overlap continuity before accepting either result. Existing v1.2 cache may seed only a failed new source, must be labelled `seeded_from_v1_2`, overlap-compared, and must not manufacture future dates.
3. Refresh `000300`, `000852`, and `399006` with index endpoints. Require code and instrument identity: `000300=CSI 300`, `000852=CSI 1000`, `399006=ChiNext Price Index`. Verify returned source metadata/name where provided, the exchange-qualified request symbol, positive prices, and zero duplicate `(benchmark_code, trade_date)` keys. Reject a stock endpoint result even when its numeric code matches.
4. Build the v1.5 adjusted panel only from accepted qfq rows, with `adjusted_close=qfq_close`, normalized `YYYY-MM-DD` dates, six-digit text codes, and no forward/back fill. Gate all downstream work on adjusted-panel QA.

## Known gaps requiring explicit manifest treatment

- `002544` and `300133`: current qfq status `error`, zero legal cache rows, and each misses all 1,269 raw-base dates. Both require a full new-source attempt and must remain failures if both qfq sources fail.
- `002049`: `partial_ok`, 1,551 qfq rows; 10 missing raw-base dates from `2025-12-30` to `2026-01-14`, including `2026-01-12` baseline endpoint.
- `002131`: `partial_ok`, 1,559 qfq rows; three missing raw-base dates from `2026-01-16` to `2026-01-20`.
- `301171`: `partial_ok`, 921 qfq rows; three missing raw-base dates from `2026-01-15` to `2026-01-19`; dates before its listing are expected absences, not fetch failures.
- All other symbols still require the full-history attempt. Existing `ok` or `cached_ok` is not an exemption from the versioned refresh.

## Stage metadata

- inputs: `backtest_universe_research_v1_2.csv`; v1.2 qfq cache, raw-base/qfq/adjusted/benchmark panels, qfq/hybrid/formal manifests, qfq gap/failure/diagnostic reports, and source implementations named above.
- outputs: `reports/v1_5_refresh_inventory.csv`; `reports/v1_5_refresh_plan.md`.
- changed_files: `reports/v1_5_refresh_inventory.csv`, `reports/v1_5_refresh_plan.md` only.
- commands: PowerShell `rg`, `Get-Content`, `Get-ChildItem`, and `Import-Csv` read-only inventory queries.
- exit_codes: all completed scan commands `0`.
- QA summary: 56 unique stock codes confirmed; 59 inventory rows; all required columns present; 3 benchmark panels each have 1,562 rows from `2020-01-02` to `2026-06-16`; index request mapping and stock/index separation verified statically.
- blockers: none for this scan. Historical source availability is not tested because network fetching is prohibited in this stage.
- recommendation: approve the serialized versioned refresh using the order above; do not use `scripts/run_research.py` or generic MOM60 output paths for this chain.
