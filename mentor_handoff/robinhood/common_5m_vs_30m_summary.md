# Mandatory Common-Session 5-Minute vs 30-Minute Sensitivity

## Frozen specification and reproduction

The frozen N=43 prospective primary sample reproduced within numerical tolerance: NVDA 11, GME 23, COST 9. The full-sample 30-minute Model 0, Model 1, HC3 coefficient uncertainty, and incremental-fit metrics all match the frozen reference.

The strict estimator uses genuine reconstructable executions and quote-notional-weighted VWAPs in exactly `[19:55,20:00)` and `[03:55,04:00)` America/New_York. A strict-5m row is valid when both exact windows contain at least one qualifying execution and produce finite positive VWAPs. The pre-outcome contract defines no separate 5-minute ≥5-swap or USDG 500 robustness gate; those thresholds belong to primary robust 30-minute eligibility. No fill, nearest-swap substitution, interpolation, widening, or 30-minute substitution was used.

## Common-session composition

N_full = 43; N_common = 43; retained fraction = 100.0%; common date range = 2026-07-22 to 2026-09-04.

| Asset | Full N | Common N | Retained |
|---|---:|---:|---:|
| NVDA | 11 | 11 | 100.0% |
| GME | 23 | 23 | 100.0% |
| COST | 9 | 9 | 100.0% |

Strict-5m failure reasons: None.

## Predictor agreement on identical rows

Pearson = 0.958357; Spearman = 0.912111; sign agreement = 39/43 (90.7%). Exact-zero counts: 30m=0, 5m=0. Means: 30m=0.001379, 5m=0.001281; medians: 30m=0.000516, 5m=0.000930; sample SDs: 30m=0.006409, 5m=0.007657. Mean difference (5m−30m)=-0.000098; median difference=-0.000142; maximum absolute difference=0.007922.

## Three-layer model comparison

All models use OLS, HC3 uncertainty, the same stock outcome and conventional after-hours control, and the same COST-reference asset fixed-effect coding. COMMON_30M and COMMON_5M use identical rows; their Model 0 results match numerically.

| Stage | N | Token beta | HC3 SE | 95% CI | p | ΔR² | Δ adjusted R² | Partial R² |
|---|---:|---:|---:|---|---:|---:|---:|---:|
| FULL_30M_REFERENCE | 43 | 0.304048 | 0.286911 | [-0.276773, 0.884869] | 0.295958 | 0.087992 | 0.074828 | 0.111195 |
| COMMON_30M | 43 | 0.304048 | 0.286911 | [-0.276773, 0.884869] | 0.295958 | 0.087992 | 0.074828 | 0.111195 |
| COMMON_5M | 43 | 0.221986 | 0.266836 | [-0.318195, 0.762168] | 0.410651 | 0.066644 | 0.051233 | 0.084218 |

Sample-composition change (COMMON_30M − FULL_30M): beta 0.000000; ΔR² 0.000000; Δ adjusted R² 0.000000; partial R² 0.000000.

Estimator change on identical rows (COMMON_5M − COMMON_30M): beta -0.082062; ΔR² -0.021347; Δ adjusted R² -0.023594; partial R² -0.026976.

## Descriptive robustness classification

**PATTERN B — SAME DIRECTION, MATERIAL ATTENUATION.**

The common-session 30-minute and strict 5-minute coefficients are both positive, and the two predictors are strongly aligned. Because every frozen row is 5-minute eligible, none of the change is attributable to sample composition. On identical rows, however, the strict-estimator beta is 0.082062 lower (about 27% below the 30-minute beta), while ΔR², Δ adjusted R², and partial R² are each lower by roughly one quarter. The directional association persists, but its estimated magnitude and explanatory contribution are materially attenuated under the stricter boundary estimator.

## Interpretation limitation

The primary positive direction is reasonably stable to exact 5-minute boundary pricing on the same sessions, but the strength of the estimated association is measurement-sensitive: the strict estimator yields a smaller coefficient and lower incremental explanatory contribution. This sensitivity does not invalidate or replace the frozen 30-minute primary result, but it limits claims about the magnitude of the relationship.

## Closure statement

`MANDATORY_COMMON_SESSION_SENSITIVITY_COMPLETED`
