# H8 paper equation mapping — design only

Source: local `docs/literature_reconnaissance/papers/source_pdfs/new_papers/Positive feedback trading, the T+1 rule, and asymmetric return reversals in China.pdf`, Yao & Yang (2026), Economic Modelling 164, 107783. Page numbers below are PDF/printed pages. No local H8 coefficients or effects are estimated here.

## Exact baseline algebra (p.6, Eq.9)

\[
r_{t+1}=\alpha+\left[\sum_{i=1}^{5}\beta_iD_i+\gamma_1V_t+\gamma_2V_t^2+\gamma_{31}D_t^-V_tr_t^2+\gamma_{32}D_t^+V_tr_t^2+\gamma_4(1000\sigma_t^2)\right]r_t+\varepsilon_{t+1}.
\]

| Paper component | Future local design-column mapping (not implemented) | Meaning / restriction |
|---|---|---|
| alpha | constant 1 | Intercept included |
| beta_1 through beta_5 | Monday-through-Friday indicator × r_t | Five weekday-specific slopes, not five additive dummies; no extra standalone r_t needed |
| gamma_1 | V_t × r_t | Ordinary turnover-dependent slope, no preregistered standalone sign |
| gamma_2 | V_t² × r_t | Nonlinear turnover-dependent slope, no standalone sign restriction |
| paper_gamma31 | D_NEG_t × V_t × r_t³ | Negative-conditioning-day component |
| paper_gamma32 | D_POS_t × V_t × r_t³ | Nonnegative-conditioning-day component |
| gamma_4 | (1000 × sigma_t²) × r_t | Conditional-variance-dependent slope |

Prediction 1 jointly calls for a negative negative-day coefficient, a weak/near-zero positive-day coefficient, and a negative difference between them. A negative gamma31 by itself is insufficient. Symbols here label the paper's equation, not local estimates.

## Variables, scaling and zero-return rule

- p.4 §3.2: simple close-to-close return `close_t/close_(t-1)-1`.
- p.4 footnote 2 and p.6 footnote 5: regression returns are percentage points; `-1` means `-1%`. Cubic interaction scaling must respect that convention.
- p.5 Eq.7: raw turnover is daily volume / float-adjusted shares outstanding. `Vbar_t = ln(raw_t) - sum(ln(raw_(t-s)), s=1..22)/22`, excluding t. `V_t=max(Vbar_t,0)`; low-turnover rows remain, with V=0.
- p.5 §3.2: **D_NEG=1{r_t<0}; D_POS=1{r_t>=0}**, not strictly positive. Zero-return rows stay; all displayed r_t-multiplied columns equal zero on those rows.
- p.5 Table 2: zero-mean GARCH(1,1), conditional variance displayed ×10^-4; Eq.9 scales variance by 1000. This supports variance in decimal-return-squared units while r in regression is percentage points. Author code is not locally available to settle all rescaling details, innovation distribution, initialization and optimizer conventions.
- p.5 weekday paragraph specifies Monday–Friday interactions with lagged r_t, but does not separately document an implementation index for D_i. Proposed local convention is conditioning-day t; exact code-level matching remains to be confirmed.

## P2 decomposition (p.4 Eq.6; §5)

Paper labels overnight as `close_t -> open_(t+1)` and intraday as `open_(t+1) -> close_(t+1)` and writes daily=overnight+intraday. For conventional simple returns, exact identity instead is:

`1+r_cc = (1+r_overnight)*(1+r_intraday)`.

Hence `r_cc = r_overnight+r_intraday+r_overnight*r_intraday`. The additive expression is only an approximation for the conventional component denominators. Switching to log returns would make addition exact but would not match the paper's explicit simple-return definition. The author code is referenced via Mendeley Data on p.14 but is not present locally and was not downloaded. **RETURN_DECOMPOSITION_CONTRACT_STATUS=UNRESOLVED**; a conventional-simple-return local design requires an explicitly approved approximation and must not assert exact coefficient additivity.

## Paper-to-local sample mapping (pp.9–10, §7, Table 11)

The paper's main evidence is index-level. Stock-by-stock Eq.9 is a diagnostic, estimated separately for next-day close-to-close and intraday returns. Its universe is main-board A-shares in 2002–2021, excluding any stock ever ST/*ST during that period; at least 2400 trading days; excludes ChiNext, STAR and B-shares; final 1331 stocks. Size is average circulating market cap over the period, sorted into quintiles (p.10 prose and Table 13). Table 12's caption refers to median circulating cap, an internal wording discrepancy to retain rather than silently resolve. Size is a small-stock alternative-explanation diagnostic, not a Primary and not an explanation of H7 size results.

## Unresolved fidelity details / recommendation only

- No suspension mapping is stated in the local paper text. Recommend exact preceding 22 common-market days with active positive turnover and invalidation for gaps; report the last-22-active alternative only as availability comparison, not a selected second specification.
- Table 2 mentions 21 fewer observations from a 22-day initialization, whereas Eq.7 explicitly requires 22 strictly prior observations. Follow Eq.7 for a leakage-free candidate; author-code parity is unverified.
- CSMAR adjustment settings and raw OHLC corporate-action treatment are not specified. BaoStock raw OHLC is internally consistent but not certified identical to CSMAR; raw ex-dividend/ex-right gaps can mechanically affect overnight observations.
- BaoStock circulating shares is the nearest available economic denominator, not proven identical to float-adjusted shares. H7 total-share turnover is AVAILABLE_BUT_NOT_PAPER_PRIMARY (the paper itself mentions total shares as an unreported robustness in p.5 footnote 3).
- No equation is estimated; no stock threshold, sample, pricing rule or GARCH implementation is frozen by this mapping.

H7 remains PHENOMENON_DIAGNOSTIC. H8 would be MECHANISM_REPLICATION_DIAGNOSTIC, not H7 robustness. `H8_results_opened=false; gamma_estimated=false; network_download_performed=false`.
