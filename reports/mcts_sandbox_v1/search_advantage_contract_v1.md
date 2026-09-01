# MCTS Historical-Seen Sandbox v1 — Frozen Search Contract

```text
experiment_type=mcts_search_sandbox
version=v1
sample_role=historical_seen
descriptive_only=true
alpha_claim_allowed=false
oos_claim_allowed=false
prospective_data_accessed=false
final_test_accessed=false
```

- Primitive information: `RETURN_60, VOL_20, AMOUNT_MEAN_20`; searched leaves: `P_RETURN_60, P_VOL_20, P_AMOUNT_MEAN_20`.
- Operators: `NEG, RANK, ADD, SUB, MUL`; maximum expression depth: `4`.
- Common signal mask is the Phase A signal target intersected with finite values of all three raw
  primitives.
- A period is common-valid at coverage >= 95% and at least 25 stocks. No imputation.
- Base primitives use deterministic average-tie cross-sectional percentile ranks within that mask.
- Reward is formula-as-written mean Spearman RankIC; no future-selected direction.
- Both methods use 5 seeds x 1,000 unique reward evaluations, with at most 10,000 proposals per
  seed.
- Canonical hits and signal-only rank-signature hits reuse reward and do not consume unique budget.
- MCTS retains v0 UCT: `mean_reward + sqrt(2)*sqrt(log(parent_visits)/child_visits)`.
- Common threshold is the pooled unique-evaluation reward 90th percentile.
- `MCTS_SEARCH_ADVANTAGE_OBSERVED` requires all three v0 conditions: MCTS median best reward
  > Random, MCTS median unique evaluations-to-threshold < Random, and MCTS median unique rank
  diversity >= Random. If evidence conflicts, classification is `MIXED_SEARCH_MECHANISM_RESULT`;
  otherwise `MCTS_SEARCH_ADVANTAGE_NOT_OBSERVED`.
