# H8 final design-matrix schema — synthetic only

Paper anchor: existing h8_equation_mapping.md, Yao & Yang (2026), PDF pp.4–6 Eq.7/Eq.9. No real design matrix or response vector is built by this audit.

| Column | Exact expression | Unit / time |
|---|---|---|
| intercept | 1 | constant |
| MON/TUE/WED/THU/FRI times r | 1{weekday(t)=d} * r_pp_t | five conditioning-day slopes |
| V times r | V_t * r_pp_t | percentage points |
| V squared times r | V_t^2 * r_pp_t | percentage points |
| negative cubic | 1{r_t<0} * V_t * r_pp_t^3 | pp cubed |
| nonnegative cubic | 1{r_t>=0} * V_t * r_pp_t^3 | pp cubed; includes zero |
| variance interaction | (1000*sigma2_decimal_t) * r_pp_t | decimal-squared variance * pp |

11 columns in total. No standalone r_t in addition to all five weekday interactions.
Synthetic numerical example: decimal r=0.01 -> r_pp=1; V=2; sigma2_decimal=0.0004.
V*r=2; V^2*r=4; negative cubic=0; nonnegative cubic=2; variance interaction=0.4.
For r=-0.01, negative cubic=-2 and nonnegative cubic=0. At r=0 all slope interactions are0 but intercept remains1.

GARCH input retains 0.01, not1.0. Conditional variance is not percentage-point-squared. No hidden factor100/10000/1000000 is applied to cubic columns.

Separate dependent-variable formulas (not evaluated on local data here): cc=close_(t+1)/close_t-1; out=open_(t+1)/close_t-1; in=close_(t+1)/open_(t+1)-1; convert each to pp for its own equation. Multiplicative identity exact; additive coefficient identity prohibited.

Synthetic GARCH tests use fixed parameters and fixed backcast for causality checks; fitted parameters/default backcast are in-sample and not prospective. Price lineage is still unresolved, so the schema is not authorization to fit.

Deterministic synthetic rank=11/11, rows=500. No coefficients estimated.
