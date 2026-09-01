"""Run preregistered H8 stock-level adapted Eq.9; no model or threshold search."""

# ruff: noqa: E501 -- explicit research contract and report prose.
from __future__ import annotations

import argparse
import sys
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import wilcoxon

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts import extend_h8_ca_and_recompute_thresholds as ext
from scripts import resolve_h8_corporate_action_lineage as ca
from scripts import resolve_h8_final_contract as h8

OUT = Path("reports/hypothesis_8")
PREREG = OUT / "h8_preregistration_v1.md"
MEMBERSHIP = OUT / "h8_sample_membership_v1.csv"
ANALYSIS_START = pd.Timestamp("2020-02-11")
FORMATION_CUTOFF = pd.Timestamp("2026-08-19")
FINAL_ENDPOINT = pd.Timestamp("2026-08-20")
PRIMARY_MIN_ROWS = 750
LONG_MIN_ROWS = 1000
EXPECTED_PRIMARY = 474
EXPECTED_LONG = 312
DEPENDENTS = ("CLOSE_TO_CLOSE", "OVERNIGHT", "INTRADAY")
X_NAMES = (
    "intercept",
    "MON_x_r",
    "TUE_x_r",
    "WED_x_r",
    "THU_x_r",
    "FRI_x_r",
    "V_x_r",
    "V2_x_r",
    "DNEG_x_V_x_r3",
    "DPOS_x_V_x_r3",
    "sigma2_1000_x_r",
)


def require_preregistration(root: Path) -> int:
    path = root / PREREG
    text = path.read_text(encoding="utf-8")
    required = (
        "PRIMARY_750_ROLE_FIXED_BEFORE_GAMMA=true",
        "LONG_HISTORY_1000_ROLE_FIXED_BEFORE_GAMMA=true",
        "TIMING_CONTRAST = DELTA_IN - DELTA_OUT",
        "human_interpretation_required=true",
    )
    if not all(x in text for x in required):
        raise RuntimeError("PREREGISTRATION_INCOMPLETE")
    return path.stat().st_mtime_ns


def build_membership(source: pd.DataFrame) -> pd.DataFrame:
    membership = pd.DataFrame(
        {
            "stock_code": source.stock_code.str.zfill(6),
            "board": source.board,
            "final_matched_rows": source.final_matched_rows.astype(int),
            "garch_status": source.garch_status,
            "selected_segment_start": source.segment_start,
            "selected_segment_end": source.segment_end,
            "ca_event_count": source.ca_event_count.astype(int),
            "primary_750_member": source.garch_status.eq("GARCH_SUCCESS")
            & source.final_matched_rows.ge(PRIMARY_MIN_ROWS),
            "long_history_1000_member": source.garch_status.eq("GARCH_SUCCESS")
            & source.final_matched_rows.ge(LONG_MIN_ROWS),
            "historical_mean_circulating_market_cap": source.historical_mean_circulating_market_cap,
        }
    )
    membership["exclusion_reason"] = np.select(
        [
            membership.garch_status.ne("GARCH_SUCCESS"),
            membership.final_matched_rows.lt(PRIMARY_MIN_ROWS),
        ],
        ["GARCH_NUMERIC_FAILURE", "BELOW_PRIMARY_750"],
        default="PRIMARY_750_MEMBER",
    )
    if (
        len(membership) != 2790
        or not membership.stock_code.is_unique
        or membership.primary_750_member.sum() != EXPECTED_PRIMARY
        or membership.long_history_1000_member.sum() != EXPECTED_LONG
        or (membership.long_history_1000_member & ~membership.primary_750_member).any()
    ):
        raise RuntimeError("SAMPLE_FREEZE_MISMATCH")
    return membership.sort_values("stock_code").reset_index(drop=True)


def freeze_membership(root: Path) -> pd.DataFrame:
    source = pd.read_csv(
        root / ext.OUT / "h8_extended_final_clean_stock_rows.csv", dtype={"stock_code": str}
    )
    membership = build_membership(source)
    ca.atomic_csv(membership.sort_values("stock_code"), root / MEMBERSHIP)
    return membership


def scaling_fixture(r_pp: float, v: float, sigma2: float, negative: bool) -> tuple[float, ...]:
    return (
        v * r_pp,
        v**2 * r_pp,
        float(negative) * v * r_pp**3,
        float(not negative) * v * r_pp**3,
        1000 * sigma2 * r_pp,
    )


def design_matrix(r_pp, v, sigma2, weekdays) -> np.ndarray:
    r_pp, v, sigma2 = map(np.asarray, (r_pp, v, sigma2))
    weekday = np.asarray(weekdays)
    columns = [np.ones(len(r_pp))]
    columns.extend((weekday == day) * r_pp for day in range(5))
    columns.extend(
        [
            v * r_pp,
            v**2 * r_pp,
            (r_pp < 0) * v * r_pp**3,
            (r_pp >= 0) * v * r_pp**3,
            1000 * sigma2 * r_pp,
        ]
    )
    return np.column_stack(columns)


def fit_garch(segment: pd.Series):
    result = dict(status="GARCH_NUMERIC_FAILURE", error="", warning="")
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fit = h8.arch_model(segment, **h8.GARCH_KWARGS).fit(disp="off", update_freq=0)
        variance = fit.conditional_volatility**2
        ok = (
            fit.convergence_flag == 0
            and np.isfinite(fit.params).all()
            and np.isfinite(variance).all()
            and (variance > 0).all()
            and variance.index.equals(segment.index)
        )
        result.update(
            status="GARCH_SUCCESS" if ok else "GARCH_NUMERIC_FAILURE",
            error="" if ok else "fixed_model_validation_failed",
            warning=" | ".join(f"{w.category.__name__}: {w.message}" for w in caught),
        )
        return variance if ok else None, result
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}:{exc}"
        return None, result


def stock_design(root: Path, member, dates: pd.DatetimeIndex):
    code = member.stock_code
    raw, ever_st, _, _ = h8.load_raw(root, code, dates)
    if ever_st or h8.board(code) not in {"SH_MAIN", "SZ_MAIN"}:
        raise RuntimeError(f"candidate_identity_changed:{code}")
    events = pd.read_csv(root / ca.CACHE / "baostock" / f"{code}.csv")
    p1, p2, current = ext.raw_presence(raw, dates, FORMATION_CUTOFF)
    event, contaminated = ca.contamination_mask(dates, events.dividOperateDate)
    close = raw.loc[(raw.index >= ANALYSIS_START) & (raw.index <= FORMATION_CUTOFF), "close"]
    returns = (close / close.shift(1) - 1).where(current.loc[close.index] & ~event.loc[close.index])
    returns = returns.where(np.isfinite(returns))
    segment = h8.longest_segment(returns)
    expected_start = pd.to_datetime(member.selected_segment_start)
    expected_end = pd.to_datetime(member.selected_segment_end)
    if segment.empty or segment.index[0] != expected_start or segment.index[-1] != expected_end:
        raise RuntimeError(f"selected_segment_mismatch:{code}")
    sigma2, garch = fit_garch(segment)
    if sigma2 is None:
        return None, garch
    active = raw.trading_status.eq(1)
    v = h8.paper_v(raw.baostock_circulating_turnover, active)
    r_decimal = raw.close / raw.close.shift(1) - 1
    cc = raw.close.shift(-1) / raw.close - 1
    overnight = raw.open.shift(-1) / raw.close - 1
    intraday = raw.close.shift(-1) / raw.open.shift(-1) - 1
    base = p2 & ~contaminated & pd.Series(dates >= ANALYSIS_START, index=dates)
    base &= pd.Series(dates <= FORMATION_CUTOFF, index=dates) & dates.isin(segment.index)
    frame = pd.DataFrame(
        {
            "r_decimal": r_decimal,
            "r_pp": 100 * r_decimal,
            "V": v,
            "sigma2": sigma2.reindex(dates),
            "weekday": dates.weekday,
            "CLOSE_TO_CLOSE": 100 * cc,
            "OVERNIGHT": 100 * overnight,
            "INTRADAY": 100 * intraday,
        },
        index=dates,
    ).loc[base]
    required = ["r_decimal", "r_pp", "V", "sigma2", "CLOSE_TO_CLOSE", "OVERNIGHT", "INTRADAY"]
    if not np.isfinite(frame[required]).all().all() or not (frame.sigma2 > 0).all():
        raise RuntimeError(f"matched_nonfinite:{code}")
    if len(frame) != int(member.final_matched_rows):
        raise RuntimeError(f"matched_row_count_mismatch:{code}:{len(frame)}:{member.final_matched_rows}")
    x = design_matrix(frame.r_pp, frame.V, frame.sigma2, frame.weekday)
    if x.shape[1] != 11 or not np.isfinite(x).all():
        raise RuntimeError(f"invalid_design:{code}")
    if not np.all((np.column_stack([(frame.weekday == d) for d in range(5)]).sum(axis=1)) == 1):
        raise RuntimeError(f"weekday_contract_failed:{code}")
    return (frame, x), garch


def ols_row(code: str, component: str, x: np.ndarray, y: np.ndarray) -> dict:
    row = dict(
        stock_code=code,
        dependent_component=component,
        nobs=len(y),
        alpha=np.nan,
        gamma1=np.nan,
        gamma2=np.nan,
        gamma31=np.nan,
        gamma32=np.nan,
        delta_gamma=np.nan,
        gamma4=np.nan,
        R2=np.nan,
        rank=np.linalg.matrix_rank(x),
        condition_number=np.linalg.cond(x),
        regression_status="REGRESSION_NUMERIC_FAILURE",
        failure_reason="",
    )
    critical = x[:, 8:11]
    if (
        not np.isfinite(x).all()
        or not np.isfinite(y).all()
        or row["rank"] != 11
        or not np.isfinite(row["condition_number"])
        or np.any(np.ptp(critical, axis=0) == 0)
    ):
        row["failure_reason"] = "nonfinite_singular_or_constant_critical_interaction"
        return row
    try:
        coef, _, _, _ = np.linalg.lstsq(x, y, rcond=None)
        fitted = x @ coef
        sse = float(np.sum((y - fitted) ** 2))
        tss = float(np.sum((y - y.mean()) ** 2))
        if not np.isfinite(coef).all() or not np.isfinite(sse):
            raise ValueError("nonfinite_ols_result")
        row.update(
            alpha=coef[0],
            gamma1=coef[6],
            gamma2=coef[7],
            gamma31=coef[8],
            gamma32=coef[9],
            delta_gamma=coef[8] - coef[9],
            gamma4=coef[10],
            R2=1 - sse / tss if tss > 0 else np.nan,
            regression_status="SUCCESS",
        )
    except Exception as exc:
        row["failure_reason"] = f"{type(exc).__name__}:{exc}"
    return row


def fit_primary(root: Path, membership: pd.DataFrame) -> pd.DataFrame:
    dates = ext.market_calendar(root)
    rows = []
    primary = membership[membership.primary_750_member].sort_values("stock_code")
    for number, member in enumerate(primary.itertuples(index=False), 1):
        built, garch = stock_design(root, member, dates)
        if built is None:
            for component in DEPENDENTS:
                rows.append(
                    dict(
                        stock_code=member.stock_code,
                        dependent_component=component,
                        nobs=0,
                        regression_status="GARCH_NUMERIC_FAILURE",
                        failure_reason=garch["error"],
                    )
                )
            continue
        frame, x = built
        for component in DEPENDENTS:
            rows.append(ols_row(member.stock_code, component, x, frame[component].to_numpy()))
        if number % 50 == 0:
            print(f"H8 Eq9 stocks {number}/{len(primary)}", flush=True)
    result = pd.DataFrame(rows)
    success = result.regression_status.eq("SUCCESS")
    result["coefficient_outlier_flag"] = False
    for _component, group in result[success].groupby("dependent_component"):
        indices = group.index
        flag = pd.Series(False, index=indices)
        for variable in ("gamma31", "gamma32", "delta_gamma"):
            low, high = group[variable].quantile([0.01, 0.99])
            flag |= group[variable].lt(low) | group[variable].gt(high)
        result.loc[indices, "coefficient_outlier_flag"] = flag
    return result


def signed_rank(values) -> tuple[float, float, int]:
    x = pd.Series(values).replace([np.inf, -np.inf], np.nan).dropna()
    x = x[x.ne(0)]
    if x.empty:
        return np.nan, np.nan, 0
    test = wilcoxon(
        x,
        alternative="less",
        zero_method="wilcox",
        correction=False,
        method="auto",
    )
    return float(test.statistic), float(test.pvalue), len(x)


def describe(values, *, test=False) -> dict:
    x = pd.Series(values).replace([np.inf, -np.inf], np.nan).dropna()
    row = dict(
        N=len(x),
        mean=x.mean(),
        median=x.median(),
        std=x.std(ddof=1),
        p10=x.quantile(0.10),
        p25=x.quantile(0.25),
        p75=x.quantile(0.75),
        p90=x.quantile(0.90),
        IQR=x.quantile(0.75) - x.quantile(0.25),
        negative_share=x.lt(0).mean(),
        positive_share=x.gt(0).mean(),
    )
    stat, pvalue, nonzero = signed_rank(x) if test else (np.nan, np.nan, 0)
    row.update(wilcoxon_stat=stat, wilcoxon_p_one_sided=pvalue, wilcoxon_N_nonzero=nonzero)
    return row


def successful_wide(coefficients: pd.DataFrame) -> pd.DataFrame:
    good = coefficients[coefficients.regression_status.eq("SUCCESS")]
    fields = ["gamma31", "gamma32", "delta_gamma"]
    wide = good.pivot(index="stock_code", columns="dependent_component", values=fields)
    wide.columns = [f"{metric}_{component}" for metric, component in wide.columns]
    required = [f"{metric}_{component}" for metric in fields for component in DEPENDENTS]
    return wide.dropna(subset=required)


def primary_summaries(coefficients: pd.DataFrame):
    good = coefficients[coefficients.regression_status.eq("SUCCESS")]
    primary_rows = []
    for component in DEPENDENTS:
        group = good[good.dependent_component.eq(component)]
        variables = ("gamma31", "gamma32", "delta_gamma") if component == "CLOSE_TO_CLOSE" else ("delta_gamma",)
        for variable in variables:
            primary_rows.append(
                dict(sample="PRIMARY_750", component=component, metric=variable, **describe(group[variable], test=variable == "delta_gamma"))
            )
    wide = successful_wide(coefficients)
    timing = wide.delta_gamma_INTRADAY - wide.delta_gamma_OVERNIGHT
    p2_rows = [
        dict(sample="PRIMARY_750", component=c, metric="delta_gamma", **describe(wide[f"delta_gamma_{c}"], test=True))
        for c in DEPENDENTS
    ]
    p2_rows.append(dict(sample="PRIMARY_750", component="INTRADAY_MINUS_OVERNIGHT", metric="timing_contrast", **describe(timing, test=True)))
    return pd.DataFrame(primary_rows), pd.DataFrame(p2_rows), wide


def long_summary(wide: pd.DataFrame, membership: pd.DataFrame) -> pd.DataFrame:
    codes = set(membership.loc[membership.long_history_1000_member, "stock_code"])
    subset = wide.loc[wide.index.isin(codes)]
    rows = []
    for component in DEPENDENTS:
        primary = describe(wide[f"delta_gamma_{component}"])
        row = dict(
            sample="LONG_HISTORY_1000",
            component=component,
            metric="delta_gamma",
            **describe(subset[f"delta_gamma_{component}"], test=True),
        )
        row.update(
            primary_750_median=primary["median"],
            difference_in_median=row["median"] - primary["median"],
            primary_750_negative_share=primary["negative_share"],
            difference_in_negative_share=row["negative_share"] - primary["negative_share"],
        )
        rows.append(row)
    timing = subset.delta_gamma_INTRADAY - subset.delta_gamma_OVERNIGHT
    primary_timing = wide.delta_gamma_INTRADAY - wide.delta_gamma_OVERNIGHT
    row = dict(
        sample="LONG_HISTORY_1000",
        component="INTRADAY_MINUS_OVERNIGHT",
        metric="timing_contrast",
        **describe(timing, test=True),
    )
    primary = describe(primary_timing)
    row.update(
        primary_750_median=primary["median"],
        difference_in_median=row["median"] - primary["median"],
        primary_750_negative_share=primary["negative_share"],
        difference_in_negative_share=row["negative_share"] - primary["negative_share"],
    )
    rows.append(row)
    return pd.DataFrame(rows)


def size_diagnostic(wide: pd.DataFrame, membership: pd.DataFrame) -> pd.DataFrame:
    size = membership.loc[membership.primary_750_member, ["stock_code", "historical_mean_circulating_market_cap"]].copy()
    size = size[size.stock_code.isin(wide.index)].sort_values(
        ["historical_mean_circulating_market_cap", "stock_code"]
    )
    size["size_quintile"] = ""
    for label, indices in zip(("Q1", "Q2", "Q3", "Q4", "Q5"), np.array_split(size.index, 5), strict=True):
        size.loc[indices, "size_quintile"] = label
    joined = size.set_index("stock_code").join(wide)
    rows = []
    for quintile, group in joined.groupby("size_quintile", sort=True):
        for metric, column in (
            ("gamma31_cc", "gamma31_CLOSE_TO_CLOSE"),
            ("gamma32_cc", "gamma32_CLOSE_TO_CLOSE"),
            ("delta_cc", "delta_gamma_CLOSE_TO_CLOSE"),
            ("delta_intraday", "delta_gamma_INTRADAY"),
        ):
            rows.append(
                dict(
                    size_quintile=quintile,
                    metric=metric,
                    size_n=len(group),
                    **describe(group[column], test=metric in {"delta_cc", "delta_intraday"}),
                )
            )
    return pd.DataFrame(rows)


def md_table(frame: pd.DataFrame, columns: list[str]) -> str:
    return frame[columns].to_markdown(index=False, floatfmt=".6g")


def write_report(root, membership, coefficients, primary, p2, long, size, prereg_time):
    cc = primary[(primary.component == "CLOSE_TO_CLOSE")].set_index("metric")
    timing = p2.set_index("component")
    long_idx = long.set_index("component")
    q = size[size.metric.eq("delta_cc")].set_index("size_quintile")
    fits = int(coefficients.regression_status.eq("SUCCESS").sum())
    failures = int(coefficients.regression_status.eq("REGRESSION_NUMERIC_FAILURE").sum())
    report = f"""# Hypothesis 8 v1 — Stock-Level Adapted Replication

`research_type=MECHANISM_REPLICATION_DIAGNOSTIC`; `replication_class=STOCK_LEVEL_ADAPTED_REPLICATION`; `descriptive_pattern_metrics_only`; `human_interpretation_required=true`.

The formal preregistration was written before membership freeze and before the first real Eq.9 fit. Primary contains {int(membership.primary_750_member.sum())} stocks at the fixed 750-row threshold; the fixed 1000-row long-history sensitivity contains {int(membership.long_history_1000_member.sum())} nested stocks. Successful Eq.9 fits={fits}; regression numeric failures={failures}. No coefficient-based exclusion occurred.

## Level 1 — empirical facts: P1 close-to-close

{md_table(primary[(primary.component == 'CLOSE_TO_CLOSE')], ['metric','N','mean','median','IQR','p10','p90','negative_share','wilcoxon_stat','wilcoxon_p_one_sided'])}

The table reports the frozen distribution summaries. Gamma32 is not described as zero from a nonsignificant test. Whether its economic magnitude is weak relative to gamma31, and whether the joint gamma31/gamma32/delta structure is paper-consistent, requires human interpretation.

## Level 1 — empirical facts: P2 timing

{md_table(p2, ['component','metric','N','mean','median','IQR','negative_share','wilcoxon_stat','wilcoxon_p_one_sided'])}

`TIMING_CONTRAST=DELTA_IN-DELTA_OUT`. CC, overnight and intraday use identical stock-date rows and X matrices; only Y differs. Simple-return and coefficient additivity are not assumed. Whether the observed intraday-versus-overnight distribution is paper-consistent requires human interpretation.

## Long-history 1000 nested sensitivity

{md_table(long, ['component','metric','N','median','negative_share','primary_750_median','difference_in_median','primary_750_negative_share','difference_in_negative_share','wilcoxon_p_one_sided'])}

These are the same full selected-segment stock estimates restricted to the nested 1000-row members, not refitted 1000-observation windows and not an alternate Primary.

## Secondary size-quintile diagnostic

{md_table(size, ['size_quintile','metric','size_n','median','IQR','negative_share','wilcoxon_p_one_sided'])}

Quintiles use average historical circulating market capitalization within Primary 750. This is paper-comparison description only; it is not a size regression and does not explain H7.

## Contract and QA

- analysis 2020-02-11 through formation 2026-08-19; final endpoint 2026-08-20;
- BaoStock raw OHLC, circulating turnover, explicit CA row exclusion, exact-prior-22 transform, and matched CC/OUT/IN rows;
- zero-mean GARCH(1,1), normal, decimal simple returns, `arch 8.0.0`, longest CA-clean segment only;
- 11-column full-rank Eq.9 design, conditioning-date weekday, percentage-point returns, decimal-squared sigma2;
- preregistration mtime ns={prereg_time}; threshold search=false; winsorization=false; H7 rerun=false; strategy/backtest=false.

## Limitations

This is a stock-level adaptation of an index-level Primary over 2020–2026 rather than the paper’s 2002–2021 period. The paper’s 2400-day stock-history requirement cannot be reproduced. The current/local universe is not point-in-time; observed-ever-ST is not lifetime-ever-ST. BaoStock circulating turnover is only a close economic match to the paper denominator. Raw OHLC plus explicit CA-row exclusion and the CA source accepted with limitations are local adaptations.

The longest-clean-segment rule strongly selects stocks with fewer observed CA events and longer uninterrupted histories: pre-result sample diagnostics show Spearman(CA events, final rows) about -0.679 and median event count seven among candidates versus one in the 750 and 1000 samples. P3 institutional comparison and price-limit robustness are unavailable. GARCH is fitted in-sample, stock coefficients contain estimation noise, stocks are cross-sectionally dependent, and simple-return CC/OUT/IN coefficients are not additive.

No T+1 causal mechanism, positive-feedback trader identification, Alpha, strategy, or investment conclusion is permitted. Level 2 paper-consistency judgment is reserved for human review; Level 3 mechanism claims are prohibited.

Key factual medians: gamma31_CC={cc.loc['gamma31','median']}; gamma32_CC={cc.loc['gamma32','median']}; delta_CC={cc.loc['delta_gamma','median']}; delta_OUT={timing.loc['OVERNIGHT','median']}; delta_IN={timing.loc['INTRADAY','median']}; timing contrast={timing.loc['INTRADAY_MINUS_OVERNIGHT','median']}. Long-history delta_CC={long_idx.loc['CLOSE_TO_CLOSE','median']}. Size-quintile CC delta medians: {', '.join(f'{i}={q.loc[i, "median"]}' for i in ('Q1','Q2','Q3','Q4','Q5'))}.

STOP AFTER H8 REPORT.
"""
    (root / OUT / "h8_report_v1.md").write_text(report, encoding="utf-8")


def run(root: Path, phase: str):
    root = root.resolve()
    before = h8.protected_metadata(root)
    prereg_time = require_preregistration(root)
    membership = freeze_membership(root)
    if phase == "freeze":
        print("H8 membership frozen before Eq9: Primary=474 Long=312", flush=True)
        return
    if (root / MEMBERSHIP).stat().st_mtime_ns < prereg_time:
        raise RuntimeError("PREREGISTRATION_ORDER_FAILED")
    fixture_pos = scaling_fixture(1.0, 2.0, 0.0004, False)
    fixture_neg = scaling_fixture(-1.0, 2.0, 0.0004, True)
    if fixture_pos != (2.0, 4.0, 0.0, 2.0, 0.4) or fixture_neg != (-2.0, -4.0, -2.0, 0.0, -0.4):
        raise RuntimeError("SCALING_FIXTURE_FAILED")
    start = time.time_ns()
    coefficients = fit_primary(root, membership)
    if start <= prereg_time or start <= (root / MEMBERSHIP).stat().st_mtime_ns:
        raise RuntimeError("REAL_FIT_ORDER_FAILED")
    primary, p2, wide = primary_summaries(coefficients)
    long = long_summary(wide, membership)
    size = size_diagnostic(wide, membership)
    ca.atomic_csv(coefficients, root / OUT / "h8_stock_coefficients_primary_v1.csv")
    ca.atomic_csv(primary, root / OUT / "h8_cross_sectional_summary_primary_v1.csv")
    ca.atomic_csv(long, root / OUT / "h8_long_history_1000_summary_v1.csv")
    ca.atomic_csv(p2, root / OUT / "h8_p2_timing_summary_v1.csv")
    ca.atomic_csv(size, root / OUT / "h8_size_quintile_diagnostic_v1.csv")
    write_report(root, membership, coefficients, primary, p2, long, size, prereg_time)
    if before != h8.protected_metadata(root):
        raise RuntimeError("H7_metadata_changed")
    print("H8 v1 complete: descriptive metrics only; human interpretation required", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    parser.add_argument("--phase", choices=("freeze", "run"), default="run")
    args = parser.parse_args()
    run(args.project_root, args.phase)
