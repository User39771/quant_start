# QFQ Source Diagnostics v1.2

- total_calls: 12
- Eastmoney push2his failure concentration: 6 rows mention push2his.eastmoney.com
- Sina daily fallback candidate: yes
- Eastmoney qfq available in diagnostics: no

## Status Summary
- 000063 | eastmoney_hist | full | error: 1
- 000063 | eastmoney_hist | short | error: 1
- 000063 | sina_daily | full | ok: 1
- 000063 | sina_daily | short | ok: 1
- 300378 | eastmoney_hist | full | error: 1
- 300378 | eastmoney_hist | short | error: 1
- 300378 | sina_daily | full | ok: 1
- 300378 | sina_daily | short | ok: 1
- 300857 | eastmoney_hist | full | error: 1
- 300857 | eastmoney_hist | short | error: 1
- 300857 | sina_daily | full | ok: 1
- 300857 | sina_daily | short | ok: 1

## Interpretation
- Diagnostic only; no qfq enrichment cache was written.
- If Sina daily succeeds with usable qfq rows, next step is to add source_order=["cache","sina_daily","eastmoney_hist"] to enrich_qfq_slow_v1_2.py.
