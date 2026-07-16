# MOM60 v1.3 Freeze Review

## Stage metadata

- status: `completed_frozen`
- inputs:
  - `scripts/test_mom60_hypothesis_v1_3.py`
  - `tests/test_mom60_hypothesis_v1_3.py`
  - `data/processed/mom60_factor_panel_v1_3.csv`
  - `reports/factor_data_readiness_v1_3.csv`
  - `reports/factor_ic_periods_mom60_v1_3.csv`
  - `reports/factor_ic_summary_mom60_v1_3.csv`
  - `reports/factor_quantile_returns_mom60_v1_3.csv`
  - `reports/factor_quantile_summary_mom60_v1_3.csv`
  - `reports/factor_stability_mom60_v1_3.csv`
  - `reports/factor_hypothesis_summary_v1_3.csv`
  - `reports/factor_research_qa_v1_3.csv`
  - `reports/factor_mom60_v1_3.md`
- outputs: `reports/mom60_v1_3_freeze_review.md`
- changed_files: `reports/mom60_v1_3_freeze_review.md`
- commands: see **Command audit** below
- exit_codes: discovery/inspection `0`; focused tests `0`; artifact consistency check `0`
- QA: `pass`; focused tests `9/9`, failures `0`; persisted critical checks `14/14`, failures `0`
- blockers: Momentum Strategy v1.4 is blocked by the `not_supported` MOM60 verdict
- next-stage recommendation: freeze MOM60 v1.3 and do not start Momentum Strategy v1.4; only a separately registered, independent reversal study may be considered later

## Freeze decision

- completion: `confirmed`
- verdict: `not_supported`
- MOM40/60/80 directionally consistent: `true`, consistently against the registered momentum direction
- Momentum Strategy v1.4: `blocked`
- momentum_strategy_prototyping_allowed: `false`
- research artifacts modified: `false`
- research parameters modified: `false`
- primary factor: `MOM60`
- primary lookback trading days: `60`
- forward horizon trading days: `20`

Both registered primary historical-validation criteria are negative. MOM60 v1.3 is complete and frozen as `not_supported`; the evidence does not permit Momentum Strategy v1.4.

## Primary and validation metrics

| sample / segment | periods | mean Rank IC | Rank IC positive ratio | mean Q5-Q1 | mean Q5-universe | Q5 cumulative NAV | universe cumulative NAV |
|---|---:|---:|---:|---:|---:|---:|---:|
| primary (`all_history`) | 54 | -0.09190702401919379 | 0.35185185185185186 | -0.02042295744908466 | -0.0182380375933173 | 0.639751255730188 | 1.858750214893257 |
| historical validation | 23 | -0.12644745936399354 | 0.30434782608695654 | -0.03688790577648458 | -0.02612511601769885 | 1.0125536061085396 | 1.8616757474932015 |

Additional persisted checks: `auxiliary_pass_count=0`; `leave_best_period_mean_q5_q1=-0.04167197392583228`. Historical validation is chronological historical validation, not clean preregistered out-of-sample confirmation.

## Lookback consistency

The common MOM40/60/80 robustness sample has 53 periods. All three lookbacks have negative mean Rank IC and negative mean Q5-Q1, so they are directionally consistent against momentum.

| factor | mean Rank IC | Rank IC positive ratio | mean Q5-Q1 | Q5-Q1 cumulative NAV | quantile-return Spearman |
|---|---:|---:|---:|---:|---:|
| MOM40 | -0.10445175362567775 | 0.2830188679245283 | -0.027031610287584967 | 0.20920331195465594 | -0.7 |
| MOM60 | -0.09605645762438611 | 0.33962264150943394 | -0.021226593241473607 | 0.28385214807354264 | -0.1 |
| MOM80 | -0.11398946507913196 | 0.3018867924528302 | -0.016400747980725144 | 0.35799916517834063 | -0.6 |

For all three lookbacks, `q5_above_q1=false`, `q5_above_universe=false`, and `strictly_monotonic=false`. This consistency rejects the registered momentum direction; it does not confirm reversal.

## QA and failures

- Focused unit suite: `9/9` passed; failures `0`; errors `0`; exit code `0`.
- Persisted QA: `14/14` critical checks passed; failures `0`; critical failures `0`.
- Factor panel: `3192` rows and `3192` unique `(period_index, stock_code)` keys.
- Locked metadata: `primary_factor=MOM60`, lookback `60`, forward horizon `20`.
- The research-producing script was not run because it writes the frozen factor/results artifacts. REV60 was not run.

## Conclusion boundaries

This is current-universe historical research with `universe_point_in_time=false`, `formal_performance_conclusion_allowed=false`, `execution_sim_ready=false`, and `no_investment_conclusion=true`. The result supports only the MOM60 `not_supported` freeze decision. It is not evidence of implementable reversal alpha, formal performance, execution readiness, or an investment conclusion.

## Post-hoc exploratory observation

- observation: `medium-horizon reversal may merit future independent research`
- post_hoc: `true`
- reversal_confirmed: `false`
- momentum_strategy_prototyping_allowed: `false`

This observation is exploratory only. Any reversal work must be independently registered with an untouched validation design and must not be treated as Momentum Strategy v1.4.

## Command audit

Read-only discovery and inspection commands used (exit code `0`):

```powershell
git status --short
rg --files | rg -i 'mom60|momentum|v1_3|v1\.3|freeze|historical|validation|result|test'
Get-Content -Raw scripts\test_mom60_hypothesis_v1_3.py
Get-Content -Raw tests\test_mom60_hypothesis_v1_3.py
Get-Content -Raw reports\factor_mom60_v1_3.md
Get-Content -Raw reports\mom60_v1_3_freeze_review.md
Get-Content -Raw reports\factor_hypothesis_summary_v1_3.csv
Get-Content -Raw reports\factor_research_qa_v1_3.csv
Get-Content -Raw reports\factor_ic_summary_mom60_v1_3.csv
Get-Content -Raw reports\factor_quantile_summary_mom60_v1_3.csv
Get-Content -Raw reports\factor_stability_mom60_v1_3.csv
Get-Content -Raw reports\factor_data_readiness_v1_3.csv
Get-Content reports\mom60_v1_3_freeze_review.md -TotalCount 300
Get-Content reports\factor_ic_summary_mom60_v1_3.csv -TotalCount 20
Get-Content reports\factor_quantile_summary_mom60_v1_3.csv -TotalCount 30
Get-Content reports\factor_stability_mom60_v1_3.csv -TotalCount 40
Get-Content reports\factor_hypothesis_summary_v1_3.csv -TotalCount 20
Get-Content reports\factor_research_qa_v1_3.csv -TotalCount 60
rg -n "def (summarize|build_qa|main)|assess_hypothesis|validation|historical|LOOKBACKS|PRIMARY_FACTOR|outputs|to_csv|write_text|REV60" scripts\test_mom60_hypothesis_v1_3.py tests\test_mom60_hypothesis_v1_3.py reports\factor_mom60_v1_3.md
Get-Content tests\test_mom60_hypothesis_v1_3.py -TotalCount 400
```

Focused non-mutating unit test (exit code `0`):

```powershell
python -B -m unittest tests.test_mom60_hypothesis_v1_3 -v
```

Read-only artifact consistency assertion (exit code `0`):

```powershell
python -B -c "from pathlib import Path; import pandas as pd; p=Path('.'); panel=pd.read_csv(p/'data/processed/mom60_factor_panel_v1_3.csv',dtype={'stock_code':str}); qa=pd.read_csv(p/'reports/factor_research_qa_v1_3.csv'); hyp=pd.read_csv(p/'reports/factor_hypothesis_summary_v1_3.csv').set_index('metric')['value']; ic=pd.read_csv(p/'reports/factor_ic_summary_mom60_v1_3.csv'); qs=pd.read_csv(p/'reports/factor_quantile_summary_mom60_v1_3.csv'); st=pd.read_csv(p/'reports/factor_stability_mom60_v1_3.csv'); robust=ic[ic.sample_basis.eq('common_40_60_80_robustness_sample')]; spreads=qs[qs.sample_basis.eq('common_40_60_80_robustness_sample') & qs.portfolio.eq('Q5-Q1')]; hist=st[st.segment.eq('historical_validation')].iloc[0]; assert hyp['verdict']=='not_supported'; assert len(panel)==3192 and len(panel.drop_duplicates(['period_index','stock_code']))==3192; assert len(qa)==14 and qa['critical'].all() and qa['pass'].all(); assert set(robust.factor_name)=={'MOM40','MOM60','MOM80'} and (robust.mean_rank_ic<0).all() and (spreads.mean_return<0).all(); assert float(hist.mean_rank_ic)<0 and float(hist.mean_q5_q1)<0; assert panel.primary_factor.eq('MOM60').all() and panel.primary_lookback_trading_days.eq(60).all() and panel.forward_horizon_trading_days.eq(20).all(); print('verdict=not_supported panel_rows=3192 unique_keys=3192 qa_total=14 qa_pass=14 qa_fail=0 critical_fail=0 robust_factors=MOM40,MOM60,MOM80 robust_mean_ic_all_negative=true robust_mean_q5_q1_all_negative=true historical_validation_primary_metrics_negative=true')"
```
