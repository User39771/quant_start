# ALPHA_JUNGLE_QLIB_C0 one-time Final Test report

## 1. Frozen candidate identities

- GRAMMAR_RANDOM: `Add(Vari(Neg(Less(volume,volume)),30),Vari(Sub(Med(close,30),Std(close,20)),3))`
- DIRECT_LLM: `Neg(Corr(Pct(close,5),Pct(volume,5),20))`
- LLM_GUIDED_MCTS: `Neg(Ma(Corr(Pct(close,5),Pct(volume,5),20),5))`
- ALPHA158_BENCHMARK: `ROC20`

No candidate was generated, edited, replaced, or selected using Final Test.

## 2. Final-Test metrics

| Source | Mean RankIC | RankIR | Positive-day ratio | Turnover | Coverage |
|---|---:|---:|---:|---:|---:|
| GRAMMAR_RANDOM | 0.0167526888083 | 0.133704296093 | 0.555555555556 | 0.283493761141 | 1 |
| DIRECT_LLM | 0.0388748591978 | 0.256570488189 | 0.605769230769 | 0.288698752228 | 1 |
| LLM_GUIDED_MCTS | 0.0417116939345 | 0.277622432629 | 0.614316239316 | 0.182745098039 | 1 |
| ALPHA158_BENCHMARK | 0.0246429393628 | 0.120032980299 | 0.528846153846 | 0.435222816399 | 1 |

## 3. Train → Validation → Test preservation

| Source | Train RankIC | Validation RankIC | Test RankIC | T→V sign | V→T sign | T→T sign | Test/Validation |
|---|---:|---:|---:|---|---|---|---:|
| GRAMMAR_RANDOM | 0.0320662282797 | 0.073375247711 | 0.0167526888083 | True | True | True | 0.228315260676 |
| DIRECT_LLM | 0.0598463174344 | 0.0648622710304 | 0.0388748591978 | True | True | True | 0.599344712731 |
| LLM_GUIDED_MCTS | 0.0607004891461 | 0.0624619281569 | 0.0417116939345 | True | True | True | 0.667793889259 |
| ALPHA158_BENCHMARK | 0.031523917463 | 0.0219825069402 | 0.0246429393628 | True | True | True | 1.12102497817 |

## 4. Year-by-year stability

| Source | 2021 | 2022 | 2023 | 2024 through 11-14 | Years sharing full sign |
|---|---:|---:|---:|---:|---:|
| GRAMMAR_RANDOM | 0.00734288026622 | -0.000894687274719 | 0.0299463341783 | 0.0328502309532 | 3/4 |
| DIRECT_LLM | 0.0321897852485 | 0.0807145847934 | -0.0153002080344 | 0.0609304842969 | 3/4 |
| LLM_GUIDED_MCTS | 0.0372675647319 | 0.0886483650374 | -0.00908828242215 | 0.0513520923444 | 3/4 |
| ALPHA158_BENCHMARK | 0.0190221953383 | 0.0432961523155 | 0.00951265485213 | 0.0270988824965 | 4/4 |

## 5. Alpha158 benchmark comparison

Only frozen `B_SELECTED=ROC20` was evaluated on Final Test. The other 157 Alpha158 features were not read for Test outcomes. Validation `B_MEDIAN` remains contextual Validation evidence; no Test-period Alpha158 median or Test-selected benchmark was created.

## 6. Search-method conclusion

Final classification: **MIXED**.

The frozen MCTS Validation-advantage rule had already failed before Test and remains failed. Final Test assesses only preservation of the selected candidate; it cannot reopen or convert the failed Validation criterion. Search-process evidence, checkpoint Validation evidence, and selected-candidate Test preservation remain separate.

## 7. Limitations

This is a historical benchmark experiment, not live out-of-sample evidence and not a trading-value claim. Accepted-per-call remains operational secondary because provider failures differed. No candidate was selected using Test, and no Test-based reselection, sign flip, parameter change, or formula variant is permitted.

`FINAL_TEST_ACCESSED=true`

`FINAL_TEST_CONSUMED=true`

`FINAL_TEST_LOCKED=true`
