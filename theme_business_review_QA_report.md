# Theme Business Review QA Report

## Process

- Rows 61-200 were split into four 35-row ranges. Agents B/C/D produced range CSVs; Agent A did not finish in time, so rows 61-95 were completed in the main process with conservative secondary-source evidence.
- Seed rows 1-60 were preserved exactly and prepended to the reviewed rows.
- Evidence preference was official/financial disclosure first, but most rows use Sina/Eastmoney F10 style business profiles because they are consistent, auditable secondary sources for broad business-materiality triage.

## Validation Results

- Seed rows: 60
- New rows: 140
- Final rows: 200
- Duplicate key multiset check: passed
- Required-field and allowed-label checks: passed
- Suspicious contradiction flags: 9
- Manual decision rows: 19

## Label Distribution

- Rows 61-200 review_status: {'conditional': 66, 'core': 10, 'reject': 31, 'watchlist': 33}
- Rows 1-200 review_status: {'conditional': 97, 'core': 19, 'reject': 39, 'unknown': 1, 'watchlist': 44}
- Rows 61-200 materiality: {'core': 10, 'immaterial': 32, 'transition': 70, 'unknown': 28}

## Suspicious Flags

- Row 30 2151 北斗星通: core status with secondary-only evidence
- Row 36 2230 科大讯飞: core status with secondary-only evidence
- Row 37 2236 大华股份: core status with secondary-only evidence
- Row 56 2465 海格通信: core status with secondary-only evidence
- Row 75 2829 星网宇达: core status with secondary-only evidence
- Row 81 2935 天奥电子: core status with secondary-only evidence
- Row 92 300045 华力创通: core status with secondary-only evidence
- Row 95 300053 航宇微: core status with secondary-only evidence
- Row 187 301050 雷电微力: core status with secondary-only evidence

## Known Caveats

- Many rows lack disclosed theme revenue ratios; classification therefore emphasizes business identity and whether the theme is a customer-facing revenue line rather than mere concept tags.
- Secondary F10 pages are suitable for broad triage but should be replaced with annual-report section citations for stocks promoted into the default universe.
- `core` rows with secondary-only evidence were retained where the business identity directly matched satellite/navigation/space or AI infrastructure, and are surfaced for human review where material.

## Unknown Rows

- None.
