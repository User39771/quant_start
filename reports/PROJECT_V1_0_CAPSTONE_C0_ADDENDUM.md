# Quant Start v1.0 Capstone Addendum — Alpha Jungle / MCTS C0

## 1. Why this addendum exists

`PROJECT_V1_0_FINAL_REPORT.md` was frozen before C0 began. C0 is therefore archived here as a separate post-v1.0 capstone evidence cycle. This addendum does not retroactively alter the designs, results, evidence identities, or conclusions of H1–H8 or Robinhood RQ2.

The purpose is narrow: preserve what C0 tested, what it found, what it did not establish, and why its final classification is `MIXED`.

## 2. Research motivation

The earlier MCTS sandbox was too narrow and highly redundant to support a useful method comparison. C0 revisited the paper-informed Alpha Jungle idea with a richer Qlib-compatible formula grammar and a deterministic evaluator. It compared three formal search arms:

- `GRAMMAR_RANDOM`;
- `DIRECT_LLM`;
- `LLM_GUIDED_MCTS`.

Alpha158 remained a benchmark and reference library, not a fourth search arm. C0 asked whether tree-guided search added stable discovery efficiency beyond a simpler LLM baseline under shared data, grammar, model, evaluation, and budget constraints. It did not treat novelty by itself as success, and it was not designed as a direct profitability test.

## 3. Frozen experimental design

The study used historical CSI300 membership from the frozen local Qlib provider and the frozen 10-day forward label with label endpoints isolated inside each split.

| Stage | Frozen interval | Role |
|---|---|---|
| Train search | 2011-01-01 through 2018-12-31 | candidate generation and search guidance |
| Validation | 2019-01-01 through 2020-12-31 | frozen shortlist comparison and selection |
| Final Test | 2021-01-01 through 2024-11-30 | one-time preservation check only |

Formal search stopped at the preregistered rules:

- Random: 100 accepted formulas from 194 proposals;
- Direct LLM: 51 accepted formulas at the 150 charged-call cap;
- MCTS: 100 accepted formulas from 143 charged calls.

The primary three-arm search-efficiency checkpoints were 10, 20, and 50 accepted formulas, the largest accepted budgets reached by all arms. Random@100 and MCTS@100 were secondary endpoints, not equal-budget comparisons with Direct@51. Validation selected one frozen candidate per search arm and `B_SELECTED=ROC20` from the Train-ranked Alpha158 top 10. Only those four identities entered the one-time Final Test. No Test-based reselection was permitted.

## 4. Validation result

The common-checkpoint Validation comparison was:

| Accepted budget | Random RankIC | Direct RankIC | MCTS RankIC |
|---:|---:|---:|---:|
| 10 | -0.0278417533752 | 0.0648622710304 | 0.0648622710304 |
| 20 | -0.0142651813238 | 0.0648622710304 | 0.0648622710304 |
| 50 | 0.00338715674215 | 0.0648622710304 | 0.058244140458 |

The frozen MCTS Validation-advantage rule **FAILED**. Direct and MCTS shared the same canonical checkpoint formula at 10 and 20 accepted formulas:

`Neg(Corr(Pct(close,5),Pct(volume,5),20))`

Its arm-independent Validation metrics were identical, as required. At the final common checkpoint, MCTS did not exceed Direct. Direct had already found the core price–volume interaction family very early. C0 therefore did not establish an additional, stable search-efficiency advantage from MCTS over Direct LLM.

This conclusion was fixed before Final Test and could not be reopened afterward.

## 5. Final-Test preservation

The one-time Final Test evaluated exactly four frozen candidates:

| Source | Frozen identity | Train RankIC | Validation RankIC | Test RankIC | Test turnover |
|---|---|---:|---:|---:|---:|
| Random | `Add(Vari(Neg(Less(volume,volume)),30),Vari(Sub(Med(close,30),Std(close,20)),3))` | 0.0320662282797 | 0.073375247711 | 0.0167526888083 | 0.283493761141 |
| Direct | `Neg(Corr(Pct(close,5),Pct(volume,5),20))` | 0.0598463174344 | 0.0648622710304 | 0.0388748591978 | 0.288698752228 |
| MCTS | `Neg(Ma(Corr(Pct(close,5),Pct(volume,5),20),5))` | 0.0607004891461 | 0.0624619281569 | 0.0417116939345 | 0.182745098039 |
| Alpha158 | `ROC20` / `Ref($close, 20)/$close` | 0.031523917463 | 0.0219825069402 | 0.0246429393628 | 0.435222816399 |

All four retained positive full-period RankIC from Train through Validation and Final Test. Direct and MCTS preserved the same short-horizon price–volume interaction family. The selected MCTS candidate had a slightly higher Test RankIC and lower Test turnover than Direct. Those observations are final-candidate preservation evidence only; they do not retroactively supply the search-efficiency evidence that the frozen Validation rule required.

The yearly diagnostics also preserve uncertainty. Random was slightly negative in 2022, while Direct and MCTS were negative in 2023; each shared its positive full-Test sign in three of four calendar subperiods. ROC20 was positive in all four. These diagnostics did not trigger reselection.

## 6. Final interpretation

C0 is **MIXED**.

Supporting evidence:

- LLM-assisted search found a price–volume interaction family that preserved direction across Train, Validation, and Test;
- the selected MCTS candidate preserved well on Final Test and recorded the highest Test RankIC among the four frozen candidates.

Opposing evidence:

- the preregistration defined the qualitative MCTS search-advantage verdict,
  and its operational Validation rule, frozen before Validation, failed;
- Direct LLM discovered the core family very early;
- the extra complexity of MCTS was not shown to be necessary.

Therefore, C0 provides evidence for a limited empirical price–volume pattern within this historical CSI300 benchmark, but does not establish that MCTS is superior to simpler Direct LLM search. It does not establish a confirmed new Alpha, a live out-of-sample discovery, a profitable strategy, or a causal mechanism.

The study also lacked a controlled cross-model comparison. It cannot allocate the result cleanly among MCTS structure, Direct LLM search, and stronger base-model priors or generation ability.

## 7. Relationship to Quant Start v1.0

The original project progression moved from pattern search to measurement, mechanism diagnostics, replication, and evidence governance. C0 adds a separate capstone sequence:

baseline-controlled search-method evaluation → frozen Validation comparison → one-time Final Test.

This extension reinforces the same governance lesson: a complex method must defeat simple baselines under comparison rules
frozen before the relevant Validation outcomes are visible. At the same time, a method can fail its primary advantage claim while still exposing a bounded empirical phenomenon worth preserving. Neither point changes the frozen v1.0 conclusions.

## 8. Freeze status

- C0 is complete.
- Final Test was accessed once.
- Final Test was consumed.
- Final Test is re-locked.
- No Test-based reselection, formula repair, sign flip, or parameter change is allowed.
- Future work requires a genuinely new evidence cycle.

