# MOM60 Factor Research v1.3

## Research question

Does higher 60-market-day momentum predict higher forward approximately 20-day
cross-sectional returns inside the current AI and commercial-space universe?

## Status

- research_status: `completed`
- verdict: `not_supported`
- primary factor: `MOM60`
- main period count: `54`
- historical validation period count: `23`

## Hypothesis registration

- Primary: MOM60 predicts higher forward approximately 20-day cross-sectional returns.
- MOM40 and MOM80 are secondary robustness checks on a common signal sample.
- Direction epsilon: `1e-12`

## Data readiness

| rebalance_date | jointly_usable_count | jointly_usable_ratio | readiness_pass | ic_valid | quantile_valid | period_phase |
|---|---|---|---|---|---|---|
| 2025-04-17 00:00:00 | 54.0 | 1.0 | True | True | True | main |
| 2025-05-20 00:00:00 | 54.0 | 1.0 | True | True | True | main |
| 2025-06-18 00:00:00 | 54.0 | 1.0 | True | True | True | main |
| 2025-07-16 00:00:00 | 54.0 | 1.0 | True | True | True | main |
| 2025-08-13 00:00:00 | 54.0 | 1.0 | True | True | True | main |
| 2025-09-10 00:00:00 | 54.0 | 1.0 | True | True | True | main |
| 2025-10-16 00:00:00 | 54.0 | 1.0 | True | True | True | main |
| 2025-11-13 00:00:00 | 54.0 | 1.0 | True | True | True | main |

## Leakage controls

Signals end on the market day before rebalance. Quantiles are assigned on the
signal sample before forward-label availability is applied. Exact market-calendar
endpoints are required; no forward-fill, backfill, or raw-close fallback is used.

## Universe and period selection

The complete panel contains every current-universe stock for every baseline headline
period. Baseline eligible codes are inherited unchanged. Signal samples are formed
before label availability; evaluation samples are used only after quantile assignment.

## Rank IC results

| factor_name | sample_basis | period_count | mean_rank_ic | median_rank_ic | rank_ic_positive_ratio | rank_ic_t_stat | annualized_icir |
|---|---|---|---|---|---|---|---|
| MOM40 | common_40_60_80_robustness_sample | 53 | -0.10445175362567775 | -0.1169048980369735 | 0.2830188679245283 | -3.439651391538702 | -1.6771108432048953 |
| MOM60 | common_40_60_80_robustness_sample | 53 | -0.09605645762438611 | -0.11481065011900514 | 0.33962264150943394 | -2.9857432089723672 | -1.455793550215827 |
| MOM60 | mom60_primary_sample | 54 | -0.09190702401919379 | -0.10373656195677719 | 0.35185185185185186 | -2.8815370259243944 | -1.3919146216921547 |
| MOM80 | common_40_60_80_robustness_sample | 53 | -0.11398946507913196 | -0.14199279711884752 | 0.3018867924528302 | -3.4671547530789386 | -1.690520977143812 |

## Quantile results

| factor_name | sample_basis | portfolio | period_count | mean_return | median_return | cumulative_nav | period_endpoint_drawdown | quantile_return_spearman | strictly_monotonic |
|---|---|---|---|---|---|---|---|---|---|
| MOM40 | common_40_60_80_robustness_sample | Q1 | 53.0 | 0.02760430128098716 | 0.010186700764700225 | 2.916912865452997 | -0.4021988989092997 | nan | nan |
| MOM40 | common_40_60_80_robustness_sample | Q2 | 53.0 | 0.018629088985419623 | 0.007447354613561779 | 2.027816905371441 | -0.3402666919172279 | nan | nan |
| MOM40 | common_40_60_80_robustness_sample | Q3 | 53.0 | 0.02612981228499777 | 0.010065209233727768 | 2.613030119299233 | -0.37973208244241985 | nan | nan |
| MOM40 | common_40_60_80_robustness_sample | Q4 | 53.0 | 0.019394648761605522 | -0.002554344205708285 | 1.9349575366824248 | -0.3847693678927614 | nan | nan |
| MOM40 | common_40_60_80_robustness_sample | Q5 | 53.0 | 0.0005726909934021938 | -0.004580063762899889 | 0.7351530074551504 | -0.468362825586514 | nan | nan |
| MOM40 | common_40_60_80_robustness_sample | Q5-Q1 | 53.0 | -0.027031610287584967 | -0.014766764527600115 | 0.20920331195465594 | -0.7976791081342183 | nan | nan |
| MOM40 | common_40_60_80_robustness_sample | Q5-UNIVERSE | 53.0 | -0.018156162289899053 | -0.02041826699783547 | 0.36204844167248423 | -0.6505581544241268 | nan | nan |
| MOM40 | common_40_60_80_robustness_sample | UNIVERSE | 53.0 | 0.018728853283301244 | 0.00795547153227607 | 1.9483843447615328 | -0.3672826615221544 | nan | nan |
| MOM60 | common_40_60_80_robustness_sample | Q1 | 53.0 | 0.021534588108699196 | -0.0004167417594351191 | 2.230140456421773 | -0.31225028261301024 | nan | nan |
| MOM60 | common_40_60_80_robustness_sample | Q2 | 53.0 | 0.018535203926059424 | 0.009394706232803444 | 2.007035975743761 | -0.32710460009878073 | nan | nan |
| MOM60 | common_40_60_80_robustness_sample | Q3 | 53.0 | 0.025420003256829665 | 0.01022798789578545 | 2.5227484103509497 | -0.36274233595275707 | nan | nan |
| MOM60 | common_40_60_80_robustness_sample | Q4 | 53.0 | 0.0266945009002454 | 0.0013908372157532924 | 2.835648574269321 | -0.39201895147735943 | nan | nan |
| MOM60 | common_40_60_80_robustness_sample | Q5 | 53.0 | 0.0003079948672255923 | -0.02439126837983374 | 0.6767199258261906 | -0.5376165740721222 | nan | nan |
| MOM60 | common_40_60_80_robustness_sample | Q5-Q1 | 53.0 | -0.021226593241473607 | -0.02549783139332953 | 0.28385214807354264 | -0.724953010566376 | nan | nan |
| MOM60 | common_40_60_80_robustness_sample | Q5-UNIVERSE | 53.0 | -0.018420858416075655 | -0.026218167568712106 | 0.35231125816130004 | -0.6605851606079434 | nan | nan |
| MOM60 | common_40_60_80_robustness_sample | UNIVERSE | 53.0 | 0.018728853283301244 | 0.00795547153227607 | 1.9483843447615328 | -0.3672826615221544 | nan | nan |
| MOM60 | mom60_primary_sample | Q1 | 54.0 | 0.019717781549021877 | -0.004104896995818871 | 2.0512204299613916 | -0.3097251547005929 | nan | nan |
| MOM60 | mom60_primary_sample | Q2 | 54.0 | 0.015823218504638855 | 0.007418623272555512 | 1.772824874504896 | -0.3271046000987806 | nan | nan |
| MOM60 | mom60_primary_sample | Q3 | 54.0 | 0.025068260383806384 | 0.009650464211964072 | 2.517485836189559 | -0.36274233595275707 | nan | nan |
| MOM60 | mom60_primary_sample | Q4 | 54.0 | 0.026767506080864232 | 0.0028296465297438186 | 2.9254089958116407 | -0.39201895147735943 | nan | nan |
| MOM60 | mom60_primary_sample | Q5 | 54.0 | -0.0007051759000627851 | -0.02361037750654667 | 0.639751255730188 | -0.5376165740721222 | nan | nan |
| MOM60 | mom60_primary_sample | Q5-Q1 | 54.0 | -0.02042295744908466 | -0.02213388355758948 | 0.2900957550619394 | -0.7316713527889914 | nan | nan |
| MOM60 | mom60_primary_sample | Q5-UNIVERSE | 54.0 | -0.0182380375933173 | -0.025784787893163567 | 0.3491444230436872 | -0.6587794680495374 | nan | nan |
| MOM60 | mom60_primary_sample | UNIVERSE | 54.0 | 0.017532861693254517 | -0.0003618276789682409 | 1.858750214893257 | -0.3672826615221545 | nan | nan |
| MOM80 | common_40_60_80_robustness_sample | Q1 | 53.0 | 0.019932143661974645 | -0.006951593805281905 | 2.1114830835353366 | -0.343063397739237 | nan | nan |
| MOM80 | common_40_60_80_robustness_sample | Q2 | 53.0 | 0.025130976056294267 | 0.00347417850026821 | 2.7726386755127814 | -0.3620273849278963 | nan | nan |
| MOM80 | common_40_60_80_robustness_sample | Q3 | 53.0 | 0.025169098357559934 | 0.009837305561646243 | 2.673205725034306 | -0.3222603083368132 | nan | nan |
| MOM80 | common_40_60_80_robustness_sample | Q4 | 53.0 | 0.018900622555607795 | -0.0009972963678047675 | 1.7936975497124987 | -0.47132327699320864 | nan | nan |
| MOM80 | common_40_60_80_robustness_sample | Q5 | 53.0 | 0.0035313956812495096 | -0.02222239146037904 | 0.7855754668344681 | -0.46286554220983667 | nan | nan |
| MOM80 | common_40_60_80_robustness_sample | Q5-Q1 | 53.0 | -0.016400747980725144 | -0.0201933297355239 | 0.35799916517834063 | -0.6778144313196169 | nan | nan |
| MOM80 | common_40_60_80_robustness_sample | Q5-UNIVERSE | 53.0 | -0.015197457602051736 | -0.021286347855673703 | 0.416955600044446 | -0.6210393829901661 | nan | nan |
| MOM80 | common_40_60_80_robustness_sample | UNIVERSE | 53.0 | 0.018728853283301244 | 0.00795547153227607 | 1.9483843447615328 | -0.3672826615221544 | nan | nan |
| MOM40 | common_40_60_80_robustness_sample | MONOTONICITY | nan | nan | nan | nan | nan | -0.7 | False |
| MOM60 | common_40_60_80_robustness_sample | MONOTONICITY | nan | nan | nan | nan | nan | -0.09999999999999999 | False |
| MOM60 | mom60_primary_sample | MONOTONICITY | nan | nan | nan | nan | nan | -0.09999999999999999 | False |
| MOM80 | common_40_60_80_robustness_sample | MONOTONICITY | nan | nan | nan | nan | nan | -0.6 | False |

Q5-Q1 is a research diagnostic, not an executable A-share long-short strategy.

## Time stability

| segment | status | period_count | mean_rank_ic | rank_ic_positive_ratio | mean_q5_q1 | mean_q5_universe | cumulative_q5_nav | cumulative_universe_nav |
|---|---|---|---|---|---|---|---|---|
| all_history | ok | 54.0 | -0.09190702401919379 | 0.35185185185185186 | -0.02042295744908466 | -0.0182380375933173 | 0.639751255730188 | 1.858750214893257 |
| development | ok | 31.0 | -0.06628024940853594 | 0.3870967741935484 | -0.008207028044884712 | -0.012386334246195507 | 0.6318196408275993 | 0.9984285487932665 |
| historical_validation | ok | 23.0 | -0.12644745936399354 | 0.30434782608695654 | -0.03688790577648458 | -0.02612511601769885 | 1.0125536061085396 | 1.8616757474932015 |
| year_2021 | ok | 7.0 | -0.05087592951606643 | 0.42857142857142855 | -0.0023632598251841727 | -0.007090115155965192 | 1.060433545306898 | 1.1296737156431316 |
| year_2022 | ok | 12.0 | -0.08579599748301188 | 0.4166666666666667 | -0.010248260409787366 | -0.006422422303724894 | 0.7870007507621444 | 0.8791845064260887 |
| year_2023 | ok | 12.0 | -0.055750354604667186 | 0.3333333333333333 | -0.009574660474807376 | -0.021439707324633798 | 0.7570673522595103 | 1.005272820002519 |
| year_2024 | ok | 12.0 | -0.1191729534893924 | 0.25 | -0.024889450401637907 | -0.019162822272477283 | 1.065045592253725 | 1.3533296065267868 |
| year_2025 | ok | 11.0 | -0.13438328395446747 | 0.36363636363636365 | -0.049977129821771854 | -0.03372034555794056 | 0.950713860019731 | 1.3756262617139106 |

## MOM40/60/80 sensitivity

The MOM60 primary sample and the common 40/60/80 robustness sample are reported
separately through `sample_basis`. Robustness results cannot replace MOM60.

## Concentration diagnostics

Best/worst Rank IC periods, best/worst Q5-Q1 periods, all period spreads, and
equal-weighted Q5 stock contributions are stored in `factor_stability_mom60_v1_3.csv`.

## Hypothesis assessment

| metric | value | status | sample_basis |
|---|---|---|---|
| historical_validation_mean_rank_ic | -0.12644745936399354 | ok | mom60_primary_sample |
| historical_validation_mean_q5_q1 | -0.03688790577648458 | ok | mom60_primary_sample |
| auxiliary_pass_count | 0 | ok | mom60_primary_sample |
| leave_best_period_mean_q5_q1 | -0.04167197392583228 | ok | mom60_primary_sample |
| verdict | not_supported | ok | mom60_primary_sample |

## Limitations

- current-universe / survivorship-like bias remains.
- This is historical chronological validation, not clean preregistered OOS confirmation.
- Q5-Q1 is a research diagnostic, not an executable A-share long-short portfolio.
- formal_performance_conclusion_allowed=false
- execution_sim_ready=false
- no_investment_conclusion=true

## Next-stage decision

Stop the momentum strategy direction.
