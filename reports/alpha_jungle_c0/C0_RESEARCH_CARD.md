# Testing whether Alpha-Jungle-style MCTS adds value beyond simpler LLM-assisted factor search

## 1. Research question

Under fixed Qlib data, formula grammar, Sol-medium model, deterministic evaluator, and search budgets, does LLM-guided MCTS discover cross-period-preserving formulaic factors more efficiently than grammar-random and simpler Direct LLM?

C0 is a **search-method comparison**, not a direct trading-profitability test. It is a paper-informed historical benchmark and bounded adaptation. Discovering a genuinely new Alpha was not the primary success criterion, especially given the prior literature and the mature Alpha158 factor library.

## 2. Why C0 was conducted

The earlier MCTS sandbox was narrow and highly redundant. C0 revisited the Alpha Jungle idea with a richer Qlib-compatible formula grammar and explicit baselines. The goal was to test whether the extra tree-search structure earned its complexity under frozen, baseline-controlled rules, while retaining any empirical pattern that emerged even if the method claim failed.

## 3. Frozen design

| Element | Frozen specification |
|---|---|
| Universe | Historical CSI300 membership in the existing Qlib provider |
| Label | Frozen 10-day forward label with split-end isolation |
| Train | 2011-01-01 through 2018-12-31 |
| Validation | 2019-01-01 through 2020-12-31 |
| Final Test | 2021-01-01 through 2024-11-30; one-time, consumed and re-locked |
| Arms | `GRAMMAR_RANDOM`, `DIRECT_LLM`, `LLM_GUIDED_MCTS` |
| Formal stopping outcomes | Random: 100 accepted / 194 proposals; Direct: 51 accepted / 150 charged calls; MCTS: 100 accepted / 143 charged calls |
| Primary common checkpoints | 10 / 20 / 50 accepted formulas |
| Benchmark | Alpha158 reference library; frozen `B_SELECTED=ROC20` |

Train search reward guided search within each arm. Cross-arm Validation used arm-independent mean daily cross-sectional Spearman RankIC. Exactly one frozen candidate per arm and ROC20 entered the one-time Final Test.

## 4. Primary result

The frozen MCTS Validation-advantage rule **FAILED**. C0 therefore did not establish that MCTS provides a stable Validation search-efficiency advantage over Direct LLM. Final Test did not and cannot rescue that failed criterion.

At the common Validation checkpoints, Direct and MCTS tied at 10 and 20 accepted formulas because both used `Neg(Corr(Pct(close,5),Pct(volume,5),20))`. At 50, Direct retained Validation RankIC 0.0648622710304 while the MCTS checkpoint leader recorded 0.058244140458.

## 5. Empirical finding

Direct and MCTS repeatedly discovered a short-horizon price–volume interaction family:

| Arm | Frozen final candidate | Train RankIC | Validation RankIC | Final-Test RankIC | Final-Test turnover |
|---|---|---:|---:|---:|---:|
| Direct LLM | `Neg(Corr(Pct(close,5),Pct(volume,5),20))` | 0.0598463174344 | 0.0648622710304 | 0.0388748591978 | 0.288698752228 |
| LLM-guided MCTS | `Neg(Ma(Corr(Pct(close,5),Pct(volume,5),20),5))` | 0.0607004891461 | 0.0624619281569 | 0.0417116939345 | 0.182745098039 |

Both retained positive RankIC through Train → Validation → Final Test. This is **a limited but real empirical finding within the frozen CSI300 historical benchmark**.

## 6. Interpretation

Empirically, the experiment found a price-volume interaction family that preserved direction across Train, Validation, and Final Test. Methodologically, however, the experiment did not establish that MCTS adds stable value over simpler Direct LLM search.

The finding is not a confirmed new Alpha, live out-of-sample discovery, profitable strategy, or identified causal mechanism. C0’s final classification is **MIXED**.

## 7. Important uncertainty

The experiment did not contain a controlled cross-model comparison. It therefore cannot identify how much of the result came from:

- MCTS structure;
- Direct LLM search;
- stronger base-model priors or generation ability.

This remains a limitation, not a resolved conclusion. Direct found the core family early, so the observed result does not show that MCTS complexity was necessary.

## 8. Why the study stopped

All frozen stages were completed: Train search, one-time Validation, and one-time Final Test. The Validation method criterion failed; the selected candidates were nevertheless preserved and evaluated without Test-based reselection. Final Test is consumed and re-locked. Further tuning, reselection, or formula modification would violate the evidence boundary and requires a genuinely new research cycle.

## 9. Research lesson

复杂方法是否值得使用，不能看它是否能产生更多候选，或者最终是否碰巧得到略好的结果，而必须和简单 baseline 在事先冻结的比较规则下正面竞争。

另一方面，一篇论文的方法即使没有完整复现其优势，也可能在实验中暴露出新的、值得继续研究的经验现象。这里不能排除基础模型能力升级对结果的影响；在当前实验中真正留下来的东西，可能并不是 MCTS 本身，而是 Direct 与 MCTS 都反复发现的 price-volume interaction family。

