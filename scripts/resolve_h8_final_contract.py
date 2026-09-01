"""Bounded H8 data-contract audit; no real Eq.9 design or outcome regression."""

# ruff: noqa: E501 -- compact explicit audit contracts and report prose.
from __future__ import annotations

import argparse
import time
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from arch import __version__ as arch_version
from arch import arch_model

OUT = Path("reports/hypothesis_8/final_contract")
BAO = Path("data/cache/h7_turnover/baostock")
QFQ = Path("data/cache/h5a_broader_a_qfq_v1")
MAPPING = Path("reports/hypothesis_8/design_mapping")
CUTOFF = pd.Timestamp("2026-05-11")
OVERLAP_START = pd.Timestamp("2020-12-28")
THRESHOLDS = (750, 1000, 1250, 1500)
QUARTILES = ("Q1_SMALL", "Q2", "Q3", "Q4_LARGE")
GARCH_KWARGS = dict(mean="Zero", vol="GARCH", p=1, q=1, dist="normal", rescale=False)


def positive(x):
    return (x > 0) & np.isfinite(x)


def board(code):
    if code.startswith(("600", "601", "603", "605")):
        return "SH_MAIN"
    if code.startswith(("000", "001", "002", "003")):
        return "SZ_MAIN"
    return "EXCLUDED_BOARD"


def paper_v(turn, active):
    logs = np.log(turn.where(active & positive(turn)))
    return (logs - logs.shift(1).rolling(22, min_periods=22).mean()).clip(lower=0)


def factor_transitions(raw_close, qfq_close):
    """Flag unequal adjacent ratios, NOT certified corporate-action events."""
    factor = (qfq_close / raw_close).where(positive(raw_close) & positive(qfq_close))
    paired = factor.notna() & factor.shift(1).notna()
    close = pd.Series(
        np.isclose(factor, factor.shift(1), rtol=1e-6, atol=1e-10), index=factor.index
    )
    return factor, paired, paired & ~close


def transition_clean_rows(paired, flagged):
    """Candidate rule only: both r_t and its next endpoint need clean lineage."""
    clean = paired & ~flagged
    return clean & clean.shift(-1, fill_value=False)


def raw_presence(raw, calendar):
    active = raw.trading_status.eq(1)
    close = active & positive(raw.close)
    prior22 = (
        (active & positive(raw.baostock_circulating_turnover))
        .shift(1, fill_value=False)
        .rolling(22, min_periods=22)
        .sum()
        .eq(22)
    )
    current = close & close.shift(1, fill_value=False)
    p1 = (
        current
        & prior22
        & active
        & positive(raw.baostock_circulating_turnover)
        & close.shift(-1, fill_value=False)
    )
    p1 &= pd.Series(calendar <= CUTOFF, index=calendar)
    p2 = p1 & (active & positive(raw.open)).shift(-1, fill_value=False)
    return p1, p2, current


def load_raw(root, code, calendar):
    raw = pd.read_csv(
        root / BAO / f"{code}.csv",
        usecols=[
            "trade_date",
            "open",
            "close",
            "baostock_circulating_turnover",
            "trading_status",
            "is_st",
        ],
    )
    raw.trade_date = pd.to_datetime(raw.trade_date)
    if raw.trade_date.duplicated().any() or not raw.trade_date.is_monotonic_increasing:
        raise ValueError(f"invalid_raw_keys:{code}")
    # User's current-local-observed-history ST rule, not lifetime nor point-in-time.
    ever_st = bool(raw.is_st.eq(1).any())
    st_after_cutoff = bool((raw.is_st.eq(1) & raw.trade_date.gt(CUTOFF)).any())
    st_end = raw.trade_date.max().date().isoformat()
    raw = raw.set_index("trade_date").reindex(calendar)
    return raw, ever_st, st_after_cutoff, st_end


def inspect_stock(root, code, calendar):
    raw, ever_st, later_st, st_end = load_raw(root, code, calendar)
    p1, p2, _ = raw_presence(raw, calendar)
    qpath = root / QFQ / f"{code}.csv"
    q = pd.Series(np.nan, index=calendar)
    if qpath.exists():
        frame = pd.read_csv(qpath, usecols=["trade_date", "qfq_close"])
        frame.trade_date = pd.to_datetime(frame.trade_date)
        if frame.trade_date.duplicated().any() or not frame.trade_date.is_monotonic_increasing:
            raise ValueError(f"invalid_qfq_keys:{code}")
        q = frame.set_index("trade_date").qfq_close.reindex(calendar)
    factor, paired, flagged = factor_transitions(raw.close, q)
    overlap = factor.notna()
    three = overlap & overlap.shift(1, fill_value=False) & overlap.shift(-1, fill_value=False)
    diffs = factor.diff().abs()[paired]
    relative = (factor / factor.shift(1) - 1).abs()[paired]
    longest_run = 0
    current_run = 0
    for ok in paired & ~flagged:
        current_run = current_run + 1 if ok else 0
        longest_run = max(longest_run, current_run)
    row = dict(
        stock_code=code,
        board=board(code),
        observed_ever_st=ever_st,
        observed_st_after_formation_cutoff=later_st,
        st_history_end=st_end,
        qfq_file_present=qpath.exists(),
        overlap_rows=int(overlap.sum()),
        overlap_start=str(calendar[overlap][0].date()) if overlap.any() else "",
        overlap_end=str(calendar[overlap][-1].date()) if overlap.any() else "",
        adjacent_factor_pairs=int(paired.sum()),
        ratio_change_flags=int(flagged.sum()),
        ratio_change_flag_share=float(flagged.sum() / paired.sum()) if paired.any() else np.nan,
        abs_ratio_diff_p10=diffs.quantile(0.1),
        abs_ratio_diff_median=diffs.median(),
        abs_ratio_diff_p90=diffs.quantile(0.9),
        relative_ratio_diff_median=relative.median(),
        longest_unchanged_pair_run=longest_run,
        raw_p1_upper_bound=int(p1.sum()),
        raw_p2_upper_bound=int(p2.sum()),
        overlap_p1_upper_bound=int((p1 & three).sum()),
        overlap_p2_upper_bound=int((p2 & three).sum()),
        overlap_first_formation=str(calendar[p1 & three][0].date()) if (p1 & three).any() else "",
        naive_clean_p1_count_NOT_VALIDATED=int((p1 & transition_clean_rows(paired, flagged)).sum()),
        certified_corporate_action_transition_rows="UNKNOWN",
        final_potential_h8_rows="UNKNOWN",
        detector_status="NOT_CERTIFIED_RATIO_FLAGS_ARE_NOT_EVENTS",
    )
    return row


def choose_probe(candidates):
    """At most 50, deterministic SH/SZ x size strata, history-spanning selection."""
    chosen = []
    for (_, _), group in candidates.groupby(["board", "size_quartile"], sort=True):
        group = group.sort_values(["overlap_p1_upper_bound", "stock_code"])
        n = min(6, len(group))
        chosen.extend(group.iloc[np.linspace(0, len(group) - 1, n).astype(int)].stock_code)
    remaining = candidates.loc[~candidates.stock_code.isin(chosen)].sort_values(
        ["overlap_p1_upper_bound", "stock_code"]
    )
    if len(chosen) < 50 and len(remaining):
        n = min(50 - len(chosen), len(remaining))
        chosen.extend(remaining.iloc[np.linspace(0, len(remaining) - 1, n).astype(int)].stock_code)
    return list(dict.fromkeys(chosen))[:50]


def longest_segment(values):
    """Never compress gaps into consecutive GARCH dates or fill missing returns."""
    valid = values.notna() & np.isfinite(values)
    segments = valid.ne(valid.shift()).cumsum()
    lengths = values[valid].groupby(segments[valid]).size()
    if lengths.empty:
        return values.iloc[:0]
    return values[(segments == lengths.idxmax()) & valid]


def garch_probe(returns):
    start = time.perf_counter()
    result = dict(
        nobs=len(returns),
        converged=False,
        parameter_finite=False,
        conditional_variance_finite_share=0.0,
        conditional_variance_positive=False,
        date_alignment=False,
        warning="",
        error="",
        runtime_seconds=0.0,
    )
    try:
        if len(returns) < 2 or not np.isfinite(returns).all():
            raise ValueError("insufficient_or_nonfinite_probe_input")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            fit = arch_model(returns, **GARCH_KWARGS).fit(disp="off", update_freq=0)
        variance = fit.conditional_volatility**2
        result.update(
            converged=fit.convergence_flag == 0,
            parameter_finite=bool(np.isfinite(fit.params).all()),
            conditional_variance_finite_share=float(np.isfinite(variance).mean()),
            conditional_variance_positive=bool((variance > 0).all()),
            date_alignment=variance.index.equals(returns.index),
            warning=" | ".join(f"{w.category.__name__}: {w.message}" for w in caught),
        )
    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    result["runtime_seconds"] = time.perf_counter() - start
    result["success"] = bool(
        result["converged"]
        and result["parameter_finite"]
        and result["conditional_variance_finite_share"] == 1
        and result["conditional_variance_positive"]
        and result["date_alignment"]
    )
    return result


def synthetic_design(decimal_returns, v, sigma2, weekdays):
    """Synthetic fixture only. Not called by any real-data audit path."""
    r = np.asarray(decimal_returns) * 100
    cols = {"intercept": np.ones(len(r))}
    for i, name in enumerate(("MON", "TUE", "WED", "THU", "FRI")):
        cols[name + "_times_r_pp"] = (np.asarray(weekdays) == i) * r
    cols.update(
        V_times_r_pp=v * r,
        V2_times_r_pp=v**2 * r,
        D_NEG_V_r_pp_cubed=(r < 0) * v * r**3,
        D_POS_V_r_pp_cubed=(r >= 0) * v * r**3,
        variance_interaction=1000 * sigma2 * r,
    )
    return pd.DataFrame(cols)


def threshold_comparison(candidates):
    rows = []
    for kind, column in [
        ("RAW_FULL_UPPER_BOUND", "raw_p1_upper_bound"),
        ("OVERLAP_UPPER_BOUND", "overlap_p1_upper_bound"),
        ("FINAL_POTENTIAL_H8_ROWS", None),
    ]:
        for threshold in THRESHOLDS:
            row = dict(
                basis=kind,
                min_rows=threshold,
                stock_count="UNKNOWN",
                share_of_main_board_candidate="UNKNOWN",
                median_nobs="UNKNOWN",
                p10_nobs="UNKNOWN",
                p90_nobs="UNKNOWN",
                SH_MAIN="UNKNOWN",
                SZ_MAIN="UNKNOWN",
                mean_size="UNKNOWN",
                median_size="UNKNOWN",
                history_p10="UNKNOWN",
                history_median="UNKNOWN",
                history_p90="UNKNOWN",
                start_date_min="UNKNOWN",
                start_date_median="UNKNOWN",
                start_date_max="UNKNOWN",
                size_quartile_inclusion_spread="UNKNOWN",
                spearman_rows_log_size="UNKNOWN",
                candidate_pool_spearman_rows_log_size="UNKNOWN",
                certification="UNRESOLVED_PRICE_AND_FINAL_GARCH_ROWS",
            )
            row.update({q + "_inclusion_rate": "UNKNOWN" for q in QUARTILES})
            if column:
                selected = candidates[column].ge(threshold)
                sub = candidates[selected]
                sizes = candidates.historical_mean_circulating_market_cap
                dates = pd.to_datetime(
                    sub.overlap_first_formation
                    if kind == "OVERLAP_UPPER_BOUND"
                    else sub.cache_first_date
                )
                rates = [float(selected[candidates.size_quartile.eq(q)].mean()) for q in QUARTILES]
                row.update(
                    stock_count=len(sub),
                    share_of_main_board_candidate=len(sub) / len(candidates),
                    median_nobs=sub[column].median(),
                    p10_nobs=sub[column].quantile(0.1),
                    p90_nobs=sub[column].quantile(0.9),
                    SH_MAIN=int(sub.board.eq("SH_MAIN").sum()),
                    SZ_MAIN=int(sub.board.eq("SZ_MAIN").sum()),
                    mean_size=sub.historical_mean_circulating_market_cap.mean(),
                    median_size=sub.historical_mean_circulating_market_cap.median(),
                    history_p10=sub.active_ohlc_history_to_audit_cutoff.quantile(0.1),
                    history_median=sub.active_ohlc_history_to_audit_cutoff.median(),
                    history_p90=sub.active_ohlc_history_to_audit_cutoff.quantile(0.9),
                    start_date_min=str(dates.min()),
                    start_date_median=str(dates.median()),
                    start_date_max=str(dates.max()),
                    size_quartile_inclusion_spread=max(rates) - min(rates),
                    spearman_rows_log_size=sub.loc[
                        positive(sub.historical_mean_circulating_market_cap), column
                    ].corr(
                        np.log(
                            sub.loc[
                                positive(sub.historical_mean_circulating_market_cap),
                                "historical_mean_circulating_market_cap",
                            ]
                        ),
                        method="spearman",
                    ),
                    candidate_pool_spearman_rows_log_size=candidates.loc[
                        positive(sizes), column
                    ].corr(np.log(sizes[positive(sizes)]), method="spearman"),
                    certification="UPPER_BOUND_ONLY_EXCLUDES_NEITHER_CA_NOR_GARCH_FAILURES",
                )
                row.update(
                    {q + "_inclusion_rate": rate for q, rate in zip(QUARTILES, rates, strict=True)}
                )
            rows.append(row)
    return pd.DataFrame(rows)


def markdown_table(frame):
    lines = [
        "| " + " | ".join(frame.columns) + " |",
        "|" + "|".join(["---"] * len(frame.columns)) + "|",
    ]
    for row in frame.itertuples(index=False, name=None):
        lines.append(
            "| " + " | ".join(f"{x:.6g}" if isinstance(x, float) else str(x) for x in row) + " |"
        )
    return "\n".join(lines)


def protected_metadata(root):
    paths = list((root / "reports/hypothesis_7").rglob("*"))
    paths += [
        root / "scripts/run_h7_dynamic_volume_return_v1.py",
        root / "tests/test_run_h7_dynamic_volume_return_v1.py",
    ]
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in paths if p.is_file()}


def write_reports(root, audit, candidates, probes, thresholds, unchanged):
    out = root / OUT
    out.mkdir(parents=True, exist_ok=True)
    audit.to_csv(out / "h8_price_corporate_action_audit.csv", index=False, encoding="utf-8-sig")
    probes.to_csv(out / "h8_garch_stability_probe.csv", index=False, encoding="utf-8-sig")
    thresholds.to_csv(
        out / "h8_history_threshold_comparison.csv", index=False, encoding="utf-8-sig"
    )
    pairs, flags = int(audit.adjacent_factor_pairs.sum()), int(audit.ratio_change_flags.sum())
    main = audit.board.isin(["SH_MAIN", "SZ_MAIN"])
    success = int(probes.success.sum())
    report = f"""# H8 Final Contract Resolution

## Decision

**PROPOSED_H8_CONTRACT_STATUS=H8_NOT_READY**. Price contract remains unresolved; minimum-history counts cannot be certified before price lineage and final GARCH row validity are resolved. No Eq.9 was fitted. This is not a negative H8 research result.

## Price / corporate actions

Candidate source: **BaoStock raw OHLC**, same-source/date/convention open and close. Diagnostic QFQ source: existing canonical Sina QFQ close, never substituted into raw returns. `PRICE_CONTRACT_UNRESOLVED`; `corporate_action_detector_valid=false` (not validated). The fixed `rtol=1e-6, atol=1e-10` produces **{flags:,} ratio-change flags / {pairs:,} adjacent pairs ({flags / pairs:.4%})**, across {int(audit.overlap_rows.gt(0).sum())} overlapping stocks. These are **not certified corporate-action transition counts**; certified count=UNKNOWN. No tolerance tuning or synthetic QFQ open was used.

Overlap covers {audit.loc[audit.overlap_rows.gt(0), "overlap_start"].min()} through {audit.loc[audit.overlap_rows.gt(0), "overlap_end"].max()} (the extra day is an endpoint, not a later formation date). Per-stock median ratio-change share={audit.ratio_change_flag_share.median():.4%}; median across stocks of within-stock absolute ratio-change median={audit.abs_ratio_diff_median.median():.8g}. Rounded cross-vendor prices can generate ratio jitter; exact cause/authoritative adjustment factors are not established. Dense ratio flags cannot be equated to sparse dividend/split events. The CSV also shows unvalidated naive-clean counts only to expose the consequence of blindly treating these flags as events; they are not eligible H8 rows.

Conditional candidate rule, only after a reliable detector: `RAW_OHLC_WITH_CORPORATE_ACTION_TRANSITION_EXCLUSION`. Exclude both a contaminated conditioning return (t-1 to t) and a contaminated outcome endpoint (t to t+1). Missing factor lineage is unknown, not clean. P2 intraday is same-day but the matched sample shares the exclusion. No price is changed.

`RECOMMENDED_H8_ANALYSIS_START=UNRESOLVED`; prefer the corporate-action-verified start once verification exists. 2020-12-28 is currently **overlap start, not verified start**. Earliest three-date overlap formation would be 2020-12-29. `H8_FORMATION_CUTOFF=2026-05-11`; next endpoint=2026-05-12. Raw full start is not recommended merely to retain an unverified year.

## Return contract — resolved

`RETURN_DECOMPOSITION_CONTRACT=SEPARATE_SIMPLE_RETURN_EQUATIONS`.
Close-to-close = close_(t+1)/close_t - 1; overnight = open_(t+1)/close_t - 1; intraday = close_(t+1)/open_(t+1) - 1.
Exact: 1+cc=(1+out)(1+in). The additive identity and exact coefficient additivity are **not** used. Separate simple-return equations remain mandatory.

## GARCH implementation and numeric probe

arch={arch_version}; installed by this task in the existing Python environment; only arch was added to requirements. Fixed `arch_model(mean='Zero',vol='GARCH',p=1,q=1,dist='normal',rescale=False)`; fit defaults, no optimizer/distribution/model rescue. Inputs are decimal simple returns; sigma squared is decimal-return squared. Regression r is percentage points, variance interaction=(1000*sigma2_decimal)*r_pp.

Deterministic probe: {len(probes)} main-board/non-observed-ST stocks; success={success}, failure={len(probes) - success}. Selection spans SH/SZ, candidate size quartiles and history lengths, before fitting. CSV includes all selected names and failures. It uses the **longest consecutive available raw-return segment within the overlap interval through cutoff**, never bridges missing dates or fills. This is solely a package/numerical probe on uncorrected raw prices, **not a final economic GARCH path**. No return magnitudes, parameters, volatility paths, or outcome relationships are exported.

`GARCH_IMPLEMENTATION_CONTRACT=READY` (synthetic units/alignment checks); `GARCH_FINAL_SAMPLE_CONTRACT=UNRESOLVED_PRICE_LINEAGE`; `full_candidate_garch_feasible=UNKNOWN`. Full-candidate fitting was not run because the price detector has not produced a valid final price sample. Probe failures are GARCH_NUMERIC_FAILURE, never rescued. Even successful raw probes do not guarantee convergence after a future approved corporate-action treatment.

Conditional variance at t uses past residuals at fixed parameters, not a t+1 shift. Parameters and default backcast are in-sample estimated/initialized, not prospective; the synthetic no-look-ahead test fixes both parameters and backcast before perturbing later returns. Once clean-return gaps are defined, missing-day recursion must be made explicit; this task does not promote compressed or longest-segment probe chronology to a full-sample contract.

## Main-board / history comparison

Main-board stocks={int(main.sum())}; observed-ever-ST excluded={int((main & audit.observed_ever_st).sum())}; candidates before history={len(candidates)}. ST exclusion uses **all currently local is_st history through {audit.st_history_end.max()}**, as requested, while prices/turnover and size are bounded at formation cutoff (except the one necessary next-price endpoint). {int((main & audit.observed_st_after_formation_cutoff).sum())} main-board stocks have an ST observation after cutoff. This is deliberately not lifetime-ever-ST or point-in-time selection; post-cutoff status availability is an additional historical-sample-selection limitation. No post-cutoff H8 outcome analysis is made.

The prior feasibility report excluded 403 main-board stocks using history only through formation cutoff; the current full-local-history count above has {int((main & audit.observed_ever_st).sum()) - 403} additional exclusions. Stocks with post-cutoff ST are not all new exclusions: most also had earlier ST observations.

Size is the prior data-only audit's historical mean circulating cap through cutoff. Quartiles are recomputed **within current main-board/non-observed-ST candidates**, with deterministic code tie ordering; {int(candidates.size_quartile.eq("UNKNOWN").sum())} missing-size stocks stay UNKNOWN and are not filled. First observed cache date is not listing date. The comparison contains exact22/current-return/next-endpoint presence, not just active OHLC history; it still cannot establish final CA-clean/GARCH-valid rows.

{markdown_table(thresholds[["basis", "min_rows", "stock_count", "share_of_main_board_candidate", "median_nobs", "SH_MAIN", "SZ_MAIN", "size_quartile_inclusion_spread"]])}

RAW_FULL and OVERLAP are **upper bounds only**, not recommendations, Primary eligibility counts, or interchangeable with final potential H8 rows. Detailed p10/p90, quartile inclusion, size means/medians, observed-history/start-date distributions and Spearman(rows,log_size) are in the CSV. The Spearman field uses the retained subset for each threshold; the separately named candidate-pool field uses the entire pre-threshold candidate pool. These correlations concern sample selection only. Final valid_H8_rows/log_size correlation=UNKNOWN.

The overlap-start 1500-row candidate already has zero stocks before exclusions; its zero inclusion-rate spread means an empty sample, not absence of selection bias. Increasing the nonempty overlap threshold from 750 to 1250 raises the largest-minus-smallest quartile inclusion-rate spread; this is size/history selection evidence, not an H8 effect or a reason to optimize a threshold.

Candidate raw P1/P2 presence rows={int(candidates.raw_p1_upper_bound.sum())}/{int(candidates.raw_p2_upper_bound.sum())}; overlap P1/P2 presence rows={int(candidates.overlap_p1_upper_bound.sum())}/{int(candidates.overlap_p2_upper_bound.sum())}. Matching is provisionally recommended from endpoint presence parity, not certified final row parity. `RECOMMENDED_PRIMARY_MIN_ROWS=HUMAN_JUDGMENT`; long-history sensitivity=UNRESOLVED; no inherited H7 750 rule. Four final thresholds are UNKNOWN, not zero; final threshold freeze is blocked by the price/GARCH lineage gap.

## Retained design and scope

H7_role=PHENOMENON_DIAGNOSTIC; H8_role=MECHANISM_REPLICATION_DIAGNOSTIC; STOCK_LEVEL_ADAPTED_REPLICATION; P1_SIGN=NOT_READY; P2_TIMING=NOT_READY; P3_INSTITUTION=NOT_FEASIBLE.

Turnover is BAOSTOCK_CIRCULATING_TURNOVER, exact prior 22 common-market days, all active positive finite; t excluded. V=max(log(turn_t)-prior22_log_mean,0), retaining V=0. D_NEG=r<0; D_POS=r>=0, retaining zero. Five conditioning-day weekday slopes and no extra standalone r. Only synthetic Eq.9 schema was constructed, see companion Markdown.

Price-limit robustness=UNAVAILABLE_IN_V1; available=false; blocks_primary=false. It weakens institutional mechanism discrimination, not the reason for today's block. No H-share/index/limit downloads or surrogate inference.

## Boundaries / next step

H7 metadata unchanged={unchanged}; H7 not imported, modified, or rerun. H8_results_opened=false; gamma31_estimated=false; gamma32_estimated=false; Eq9_real_data_fit=false; future_performance_selection=false; H5/H6/MCTS/Phase_B_run=false; strategy_backtest_run=false.

Next: human review of **reliable corporate-action lineage** before freezing analysis start or minimum history. Do not reinterpret dense ratio jitter as corporate-action events, relax tolerances, run a different GARCH model, or open H8 results. A future authorized source/lineage resolution is needed; this task downloads no market data and stops here. Data-quality skill kept flags separate from verified events; minimal-implementation skill avoided a new governance framework or full GARCH pass on an invalid price contract.
"""
    (out / "h8_final_contract_resolution.md").write_text(report, encoding="utf-8")
    rng = np.random.default_rng(20260831)
    toy = synthetic_design(
        rng.normal(0, 0.02, 500),
        rng.uniform(0, 2, 500),
        rng.uniform(0.0001, 0.001, 500),
        np.arange(500) % 5,
    )
    schema = """# H8 final design-matrix schema — synthetic only

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
"""
    schema += f"\nDeterministic synthetic rank={np.linalg.matrix_rank(toy.to_numpy())}/{toy.shape[1]}, rows={len(toy)}. No coefficients estimated.\n"
    (out / "h8_final_design_matrix_schema.md").write_text(schema, encoding="utf-8")


def run(root):
    root = root.resolve()
    before = protected_metadata(root)
    samples = pd.read_csv(root / MAPPING / "h8_sample_feasibility.csv", dtype={"stock_code": str})
    samples.stock_code = samples.stock_code.str.zfill(6)
    universe = pd.read_csv(
        root / "data/processed/h5a_broader_a_universe_v1.csv", dtype={"stock_code": str}
    )
    codes = sorted(
        universe.loc[universe.universe_status.eq("INCLUDED"), "stock_code"].str.zfill(6).unique()
    )
    if len(codes) != 5195 or set(codes) != set(samples.stock_code):
        raise ValueError("universe_mismatch")
    cal = pd.read_csv(
        root / "data/processed/hybrid_benchmark_panel_v1_5.csv", dtype={"benchmark_code": str}
    )
    dates = pd.DatetimeIndex(
        pd.to_datetime(cal.loc[cal.benchmark_code.str.zfill(6).eq("000300"), "trade_date"]).unique()
    ).sort_values()
    calendar = dates[(dates >= "2020-01-01") & (dates <= dates[dates.get_loc(CUTOFF) + 1])]
    records = []
    for i, code in enumerate(codes, 1):
        records.append(inspect_stock(root, code, calendar))
        if i % 250 == 0:
            print(f"Price/data-only audit {i}/{len(codes)}", flush=True)
    audit = pd.DataFrame(records)
    details = samples[
        [
            "stock_code",
            "historical_mean_circulating_market_cap",
            "active_ohlc_history_to_audit_cutoff",
            "cache_first_date",
        ]
    ]
    candidates = (
        audit.loc[audit.board.isin(["SH_MAIN", "SZ_MAIN"]) & ~audit.observed_ever_st]
        .merge(details, on="stock_code", validate="one_to_one")
        .sort_values("stock_code")
    )
    candidates["size_quartile"] = "UNKNOWN"
    valid = positive(candidates.historical_mean_circulating_market_cap)
    candidates.loc[valid, "size_quartile"] = pd.qcut(
        candidates.loc[valid, "historical_mean_circulating_market_cap"].rank(method="first"),
        4,
        labels=QUARTILES,
    ).astype(str)
    probes = []
    for code in choose_probe(candidates):
        raw, _, _, _ = load_raw(root, code, calendar)
        _, _, current = raw_presence(raw, calendar)
        # Only real return calculation in this script; never paired with future outcomes.
        r = (raw.close / raw.close.shift(1) - 1).where(current)
        r = r.loc[(r.index >= OVERLAP_START) & (r.index <= CUTOFF)]
        segment = longest_segment(r)
        row = garch_probe(segment)
        info = candidates.loc[candidates.stock_code.eq(code)].iloc[0]
        row.update(
            stock_code=code,
            board=info.board,
            size_quartile=info.size_quartile,
            probe_start=str(segment.index.min()),
            probe_end=str(segment.index.max()),
            input_contract="RAW_DECIMAL_LONGEST_CONTIGUOUS_SEGMENT_NUMERIC_ONLY",
            final_sigma_validity="UNKNOWN",
        )
        probes.append(row)
        print(f"GARCH numeric probe {len(probes)}/50 success={row['success']}", flush=True)
    probes = pd.DataFrame(probes)
    unchanged = before == protected_metadata(root)
    if not unchanged:
        raise RuntimeError("H7_metadata_changed")
    write_reports(root, audit, candidates, probes, threshold_comparison(candidates), unchanged)
    print("CONTRACT_AUDIT_COMPLETE; H8_NOT_READY; no Eq9 fit", flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    run(parser.parse_args().project_root)
