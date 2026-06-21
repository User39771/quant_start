# Market Data Realism Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit and minimally improve return-source realism, point-in-time universe evidence, and sell-side execution constraints without adding factors or widening portfolio search.

**Architecture:** Add a read-only audit script that inspects schema/cache/database metadata and writes CSV/Markdown reports. Keep return-source and execution changes narrowly scoped to `factors.py`, `backtest_engine.py`, and CLI report metadata only when data availability is proven.

**Tech Stack:** Python, pandas, unittest, existing project cache/database utilities.

---

### Task 1: Audit Script And Report

**Files:**
- Create: `scripts/audit_market_data_realism.py`
- Test: `tests/test_market_data_realism_audit.py`

- [ ] Write failing tests for audit categorization from a synthetic schema with `stock_prices_history.adj_factor`, lifecycle fields, and missing suspension flags.
- [ ] Implement schema loading and keyword/category checks without logging credentials.
- [ ] Output `data/processed/market_data_realism_audit.csv` and `reports/market_data_realism_audit.md`.
- [ ] Run `python -m unittest tests.test_market_data_realism_audit`.

### Task 2: Strict Adjusted Return Source

**Files:**
- Modify: `src/aq_factor_lab/factors.py`
- Modify: `src/aq_factor_lab/backtest_engine.py`
- Test: `tests/test_factors.py`
- Test: `tests/test_backtest_engine.py`

- [ ] Write failing tests showing `adjusted_close = close * adj_factor` is grouped by `code` and used for `forward_return_20d`.
- [ ] Write failing tests showing monthly period returns prefer `adjusted_close` and mark `period_return_source=adjusted_close_month_end`.
- [ ] Implement minimal return-source selection while preserving `total_market_cap` fallback.
- [ ] Run targeted tests.

### Task 3: Sell-Side Execution Constraints

**Files:**
- Modify: `src/aq_factor_lab/backtest_engine.py`
- Test: `tests/test_backtest_engine.py`

- [ ] Write failing test where a held stock with `amount == 0` on rebalance date cannot be sold.
- [ ] Implement sell-side tradability check using only same-day fields.
- [ ] Record `attempted_sell_count`, `blocked_sell_count`, `blocked_sell_weight`, `forced_hold_count`, `forced_hold_weight`, and `cash_weight`.
- [ ] Run targeted tests.

### Task 4: CLI Integration And Handoff

**Files:**
- Modify: `src/aq_factor_lab/cli.py`
- Modify: `src/aq_factor_lab/walk_forward.py`
- Modify: `codex.md`

- [ ] Run the audit from the research pipeline or ensure the standalone script refreshes required reports.
- [ ] Update reports to reflect `adjusted_close` if available, otherwise mark `strict_adjusted_return_unavailable`.
- [ ] Run full verification commands requested by the user.
- [ ] Append final findings and caveats to `codex.md`.
