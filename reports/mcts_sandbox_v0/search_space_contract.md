# MCTS Historical-Seen Factor Search Sandbox v0 — Search Contract

```text
experiment_type=mcts_search_sandbox
sample_role=historical_seen
descriptive_only=true
alpha_claim_allowed=false
oos_claim_allowed=false
prospective_data_accessed=false
final_test_accessed=false
search_mechanism_diagnostic=true
```

This contract is frozen before the first real candidate evaluation. The sandbox may read only the already-viewed Phase A MOM60 panel and the historical LOWVOL/Liquidity inputs documented in the research ledger. It must reject paths containing `prospective` or `final_test`.

## Grammar

```text
primitive := RETURN_60 | VOL_20 | AMOUNT_MEAN_20
unary     := NEG(expression) | RANK(expression)
binary    := ADD(expression, expression)
           | SUB(expression, expression)
           | MUL(expression, expression)
expression := primitive | unary | binary
max_expression_depth = 4
```

- `RETURN_60`: existing Phase A `mom60`, formed at `signal_as_of_date` from prior prices.
- `VOL_20`: existing locked LOWVOL20 `vol20`, formed before the forward-return interval.
- `AMOUNT_MEAN_20`: arithmetic mean of 20 exact CSI300 market dates through the signal date; every value must be finite and strictly positive; no fill.
- `REV60` is accepted only as a documented alias of `NEG(RETURN_60)` for equivalence tests. Numeric scalar `2` is accepted only for the required `2 * REV60` equivalence test; random and MCTS generation do not search constants.
- `RANK` is cross-sectional percentile rank within the signal-time candidate target for that period, using average ties.
- Binary operations are elementwise. NaN/Inf, constant signals, insufficient cross-sections, or invalid syntax fail; there is no repair or future-dependent imputation.

The syntactic upper bound through depth 4, before algebraic or information-equivalence removal, is `47,124,036` expressions (`S1=3`; `Sd=3+2*S(d-1)+3*S(d-1)^2`).

## Timing, membership and reward

- Required order: `signal_as_of_date < rebalance_date < next_rebalance_date`.
- Candidate construction uses only signal-date information. `forward_return` is never available to the expression evaluator.
- Base signal membership reuses Phase A `signal_sample_member`; each candidate's target additionally requires a finite signal known at the signal date. Labels cannot change formula values, target membership, ranks, or quantiles.
- Per-period RankIC is Spearman average-rank correlation between the candidate signal as written and Phase A `forward_return`, with at least 25 jointly valid stocks and at least 80% label coverage. Invalid periods remain recorded.
- Fixed reward: arithmetic mean of valid per-period candidate RankIC. `selected_direction=formula_as_written`; no candidate may choose its sign using future returns. NEG is an explicit searched operation and counts in the trial family.
- A candidate fails when it has fewer than 24 valid periods, any non-finite signal output, an all-constant usable signal, invalid syntax, or an invalid date/timing contract.
- Returns, turnover, 20bps cost, drawdown and group results are post-search diagnostics only and never alter reward or search.

## Search algorithms and budget

- Seeds: `20260721, 20260722, 20260723, 20260724, 20260725`.
- Budget: exactly `1000` candidate evaluations per seed per method.
- Random Search samples from the grammar with maximum depth 4.
- MCTS nodes are complete expressions. Expansion replaces one leaf by a grammar production. Selection uses UCT:

```text
UCT(child) = mean_reward(child) + sqrt(2) * sqrt(log(parent_visits) / child_visits)
```

- Expansion order and tie-breaking are seeded and deterministic. Failed candidate reward is `-1.0` for tree backpropagation but remains missing in reported research reward.
- Both methods use identical inputs, validity rules, reward, seeds and evaluation budgets. Parameters cannot change after results are observed.
- Search-efficiency target is the pooled valid-candidate reward 90th percentile, computed once from both methods. A method's evaluations-to-target is the first registry index reaching that common threshold.
- “MCTS showed a search-efficiency advantage” requires all three pre-fixed conditions: MCTS median best reward is greater than Random; MCTS median evaluations-to-target is lower than Random; and MCTS median unique rank-signal count is not lower than Random. Otherwise the wording is “did not show”.

## Equivalence

- Formula equivalence: canonical algebraic representation normalizes aliases, double negation, commutative ADD/MUL order, and nonzero positive scalar multiplication.
- Rank equivalence: exact equality of all valid period/stock cross-sectional rank signatures. Approximate correlations are descriptive and do not merge candidates.
- Portfolio equivalence: exact equality of all valid period Q5 member signatures.
- `REV60`, `-MOM60`, `2 * REV60`, and `rank(-MOM60)` must resolve to one rank-information class and one Q5 class, even when their canonical formulas differ.

## Comparison language

The final classification is only `search_mechanism_diagnostic`. The report may say “MCTS showed / did not show a search-efficiency advantage within this historical_seen sandbox”; it may not claim Alpha, OOS validation, Phase B support, or general MCTS superiority.
