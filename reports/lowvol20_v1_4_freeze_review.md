# LOWVOL20 Factor Research v1.4 Freeze Review

## Audit status

- status: passed_and_frozen
- audit type: read-only result audit
- research rerun: false
- parameter changes: none
- strategy implementation: none
- verdict: directionally_supported_for_strategy_prototyping
- formal_performance_conclusion_allowed: false
- execution_sim_ready: false
- no_investment_conclusion: true

The audit reran tests and independently recomputed persisted metrics from existing
CSV outputs. It did not rerun the production LOWVOL20 research script or any
other factor.

## Artifact consistency

The runner, test suite, factor panel, QA, summary CSVs and Markdown report use
the same fixed contracts:

- primary factor: LOWVOL20 = -VOL20
- primary sample: lowvol20_primary_reliable_sample
- diagnostic sample: lowvol20_all_exact_windows_diagnostic
- primary horizon: 21 exact prices forming 20 returns
- authoritative signal calendar: valid 000300 dates
- frozen baseline eligible_codes
- current-universe historical research
- no fill, backfill or raw-close substitution

All 11 declared outputs exist. CSV metadata consistently contains the research,
factor and conclusion-boundary fields. The factor panel has:

- rows: 3,192
- unique period_index/stock_code keys: 3,192
- unique stocks: 56
- headline periods: 57
- duplicate keys: 0
- malformed six-digit stock codes: 0
- observed forward market interval values: only 20

The persisted report verdict and hypothesis-summary verdict agree.

## Test verification

### LOWVOL20 and MOM60

Command:

    python -m unittest tests.test_lowvol20_hypothesis_v1_4 tests.test_mom60_hypothesis_v1_3 -v

- exit code: 0
- tests: 20
- failures: 0
- errors: 0

The LOWVOL20 integration test exercised all three runner statuses in a temporary
project tree:

- completed: exit 0
- research_not_ready: exit 1
- duplicate-key critical input error: exit 2

### Baseline and attribution regressions

Command:

    python -m unittest tests.test_adjusted_stock_pool_baseline_v1_2 tests.test_baseline_attribution_v1_2 -v

- exit code: 0
- tests: 26
- failures: 0
- errors: 0

Total: 46/46 tests passed.

## Critical QA

factor_research_qa_lowvol20_v1_4.csv contains eight critical checks:

| Check | Result |
|---|---|
| Factor panel row count | pass |
| Unique factor-panel keys | pass |
| Baseline endpoints in 000300 calendar | pass |
| Signal dates before rebalance dates | pass |
| LOWVOL20 equals negative VOL20 | pass |
| Evaluation sample is a signal-sample subset | pass |
| Q5-Q1 return reconciliation | pass |
| Primary factor remains locked | pass |

- critical QA failures: 0
- non-critical QA failures: 0

## Primary versus all-exact samples

### Stock-period counts

Across all 57 stored periods:

| Sample | Stock-period rows |
|---|---:|
| Baseline-eligible with exact LOWVOL20 window | 2,963 |
| Primary reliable signal sample | 2,963 |
| Excluded by flat-price reliability rule | 0 |

Across the 56 periods in the continuous main research interval:

| Sample | Stock-period rows |
|---|---:|
| All-exact diagnostic sample | 2,962 |
| Primary reliable sample | 2,962 |
| Excluded by flat-price reliability rule | 0 |

No stock code and no period were excluded by the flat-price reliability rule
after an exact LOWVOL20 window was available. Every baseline-eligible exact
window satisfied:

- at least three unique closes
- at least five non-zero daily returns
- no zero-return run longer than five days

Therefore the primary and all-exact masks are genuinely identical for the
tested main interval. Their equal Rank IC and quantile results are expected and
are not caused by a sample-mask error.

The single pre-start diagnostic period has lower exact-window coverage, but that
comes from unavailable exact history, not from flat-price reliability
exclusions. It is not included in the main results.

## Metric reconciliation

All values below were recomputed from the existing period-level IC and quantile
files and match the persisted hypothesis and risk summaries.

### Historical validation return evidence

| Metric | Recomputed | Persisted summary |
|---|---:|---:|
| Mean Rank IC | 0.08867178760533968 | 0.08867178760533968 |
| Mean Q5-Q1 forward return | 0.01889802716726507 | 0.01889802716726510 |
| Rank IC standard error | 0.053700909062594844 | 0.053700909062594844 |
| Rank IC 95% interval | [-0.0165819942, 0.1939255694] | same |
| Q5-Q1 standard error | 0.020910088687506906 | 0.020910088687506906 |
| Q5-Q1 95% interval | [-0.0220857467, 0.0598818010] | same |

Both point estimates are positive, but both descriptive 95% intervals cross
zero. This supports the registered directional verdict; it is not statistical
confirmation or clean out-of-sample evidence.

### Historical validation risk evidence

| Metric | Value |
|---|---:|
| Q1 annualized period-return volatility | 0.5447871119343223 |
| Q5 annualized period-return volatility | 0.3707518176756721 |
| Q5-Q1 volatility difference | -0.1740352942586502 |
| Q1 period-end maximum drawdown | -0.2601904019812786 |
| Q5 period-end maximum drawdown | -0.1929127442487371 |
| Q5-Q1 drawdown improvement | 0.0672776577325416 |
| Q1 mean forward realized volatility | 0.5887640331221295 |
| Q5 mean forward realized volatility | 0.4197353698546680 |
| LOWVOL20 vs negative forward volatility Rank IC | 0.3830876442853472 |

The Q5 group has lower period-return volatility, a less severe period-end
drawdown and lower subsequent realized volatility than Q1. Period-end drawdown
is not a daily maximum drawdown and may miss intraperiod losses.

### Full-main-sample equality

For both lowvol20_primary_reliable_sample and
lowvol20_all_exact_windows_diagnostic:

- IC periods: 56
- Q5-Q1 periods: 56
- all-history mean Rank IC: 0.09204608483171059
- all-history mean Q5-Q1: 0.007612580061646905

This equality reconciles with the zero reliability-rule exclusions above.

## Frozen-file verification

Before LOWVOL20 implementation, SHA-256 hashes were recorded for frozen v1.2
and MOM60 inputs/results. The same 126 paths were hashed again after
implementation, production output generation, tests and this audit.

- before paths: 126
- after paths: 126
- path/hash differences: 0

No frozen v1.2 or MOM60 file changed.

Hash comparison command:

    $before = Import-Csv "$env:TEMP\lowvol20_frozen_before.csv"
    $after = foreach ($row in $before) {
        $hash = Get-FileHash -LiteralPath $row.Path -Algorithm SHA256
        [pscustomobject]@{Path=$row.Path; Hash=$hash.Hash}
    }
    Compare-Object $before $after -Property Path,Hash

The comparison returned no rows and exit code 0.

## Frozen conclusion

    verdict=directionally_supported_for_strategy_prototyping
    formal_performance_conclusion_allowed=false
    execution_sim_ready=false

This permits only a separately planned, research-only low-volatility strategy
prototype. It does not validate an investable strategy, establish causal or
clean out-of-sample evidence, remove current-universe bias, or prove that the
constituents were continuously tradable.
