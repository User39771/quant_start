# AkShare Fetch Diagnostics v1.2

- AkShare version: 1.18.64
- total_calls: 30

## Status Counts
- benchmark | ak.index_zh_a_hist | error: 3
- benchmark | ak.stock_zh_index_daily_tx | ok: 3
- stock | ak.stock_zh_a_hist | error: 24

## Stock Date Window Patterns
- 000063: both full and short windows fail
- 000681: both full and short windows fail
- 000901: both full and short windows fail
- 000938: both full and short windows fail
- 000977: both full and short windows fail
- 300857: both full and short windows fail

## Stock Raw vs QFQ Patterns
- no raw/qfq split failure pattern detected

## Benchmark Endpoint Patterns
- 000300: index_zh_a_hist_ok=false, tx_fallback_status=ok
- 000852: index_zh_a_hist_ok=false, tx_fallback_status=ok
- 399006: index_zh_a_hist_ok=false, tx_fallback_status=ok

## Interpretation
- Treat this report as endpoint diagnostics only; it does not validate formal data readiness.
- Prefer conclusions directly supported by the CSV rows above.
