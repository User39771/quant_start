# Project Reorganization Proposal

- status: proposal_only
- no files were moved, deleted, or renamed.

## Proposed Shape
- Keep `data/stockPool/` as the auditable stock-pool research ledger.
- Keep active deliverables named with explicit versions, for example `*_v1_2.csv`.
- Add a future `data/stockPool/archive/` only after manual approval; move v1/v1.1 there in one audited migration.
- Keep raw/cache data under `data/cache/`, processed panels under `data/processed/`, and narrative QA under `reports/`.
- Keep executable research scripts in `scripts/`; move reusable library logic into `src/aq_factor_lab/` only when it has tests.

## Risks
- Moving historical stock-pool files before backtest readiness is complete would break audit traceability.
- Old files may encode manual decisions or QA context even when superseded by v1.2.
- Cache directories are large; inventory should use aggregate rows unless a targeted audit needs file-level detail.

## Suggested Future Cleanup Gate
- Produce a manifest mapping every archived file to its successor or reason for retention.
- Run tests and checksum active v1.2 files before and after any move.
- Keep a rollback note in the cleanup PR/report.
