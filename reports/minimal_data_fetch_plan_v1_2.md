# Stock Pool v1.2 Minimal Data Fetch Plan

## Purpose

Move from the stock pool v1.2 smoke baseline to formal data readiness by fetching only the active research-universe data needed for a formal baseline check.

This is not a full A-share refetch, not a point-in-time strategy backtest, and not an investment conclusion.

## Scope

- Required stocks: unique codes from `data/processed/backtest_universe_research_v1_2.csv`.
- Required benchmarks: `000300`, `000852`.
- Optional benchmark: `399006`.
- Existing data layer endpoints:
  - stocks: `akshare.stock_zh_a_hist`
  - benchmarks: `akshare.index_zh_a_hist`

## Output Files

- `data/processed/formal_price_panel_v1_2.csv`
- `data/processed/formal_benchmark_panel_v1_2.csv`
- `data/processed/formal_trade_calendar_v1_2.csv`
- `data/processed/formal_price_fetch_manifest_v1_2.csv`
- `reports/minimal_data_fetch_failures_v1_2.csv`
- `reports/formal_data_readiness_report_v1_2.md`

## Readiness Gates

- Research-universe stock coverage is at least 95%.
- Every covered stock has raw OHLC, qfq OHLC, volume, amount, and computed pre_close.
- Required benchmarks `000300` and `000852` are present.
- No duplicate stock/date rows.
- No nonpositive OHLC or qfq_close.
- No unresolved critical failures.
- `300378` has high/low and reaches the target end date.

## Command

```powershell
python scripts\fetch_formal_data_v1_2.py --sleep 3 --max-attempts 3
```

Use `--dry-run --no-write` to validate orchestration without fetching or writing outputs.
