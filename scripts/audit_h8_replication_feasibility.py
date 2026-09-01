"""Offline availability/design audit. No real-data return magnitudes or regressions."""

# ruff: noqa: E501 -- explicit contract wording and compact report tables.
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("reports/hypothesis_8/design_mapping")
BAO = Path("data/cache/h7_turnover/baostock")
QFQ = Path("data/cache/h5a_broader_a_qfq_v1")
UNIVERSE = Path("data/processed/h5a_broader_a_universe_v1.csv")
CALENDAR = Path("data/processed/hybrid_benchmark_panel_v1_5.csv")
AUDIT_END = pd.Timestamp("2026-05-11")  # Comparison boundary only, not an H8 freeze.
START = pd.Timestamp("2020-01-01")


def board(code: str) -> str:
    if code.startswith("688"):
        return "STAR"
    if code.startswith(("300", "301")):
        return "CHINEXT"
    if code.startswith(("600", "601", "603", "605")):
        return "SH_MAIN"
    return "SZ_MAIN"


def positive(values: pd.Series) -> pd.Series:
    return values.gt(0) & np.isfinite(values)


def window_flags(valid: pd.Series) -> tuple[pd.Series, pd.Series]:
    exact = valid & valid.shift(1, fill_value=False).rolling(22, min_periods=22).sum().eq(22)
    active = valid & valid.astype(int).cumsum().shift(1, fill_value=0).ge(22)
    return exact, active


def toy_truncation(values: pd.Series) -> pd.Series:
    """Formula fixture only: this function is never called on local stock data."""
    logs = np.log(values.where(positive(values)))
    return (logs - logs.shift(1).rolling(22, min_periods=22).mean()).clip(lower=0)


def sign_dummies(values: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    return values < 0, values >= 0


def toy_components(previous_close: float, next_open: float, next_close: float) -> tuple[float, float, float]:
    """Synthetic formula QA; no real-data return analysis."""
    return next_close / previous_close - 1, next_open / previous_close - 1, next_close / next_open - 1


def h7_metadata(root: Path) -> dict[str, tuple[int, int]]:
    files = list((root / "reports/hypothesis_7").rglob("*"))
    files += [root / "scripts/run_h7_dynamic_volume_return_v1.py", root / "tests/test_run_h7_dynamic_volume_return_v1.py"]
    return {str(p): (p.stat().st_size, p.stat().st_mtime_ns) for p in files if p.is_file()}


def table(frame: pd.DataFrame) -> str:
    if frame.empty:
        return "No observations."
    lines = ["| " + " | ".join(frame.columns) + " |", "|" + "|".join(["---"] * len(frame.columns)) + "|"]
    for row in frame.itertuples(index=False, name=None):
        lines.append("| " + " | ".join(f"{v:.6g}" if isinstance(v, float) else str(v) for v in row) + " |")
    return "\n".join(lines)


def inspect_stock(root: Path, code: str, calendar: pd.DatetimeIndex) -> tuple[dict, dict]:
    raw = pd.read_csv(root / BAO / f"{code}.csv", usecols=["trade_date", "open", "high", "low", "close", "volume_shares", "baostock_circulating_turnover", "trading_status", "is_st"])
    raw["trade_date"] = pd.to_datetime(raw.trade_date)
    if raw.trade_date.duplicated().any() or not raw.trade_date.is_monotonic_increasing:
        raise ValueError(f"invalid_date_keys:{code}")
    full_start, full_end = raw.trade_date.min(), raw.trade_date.max()
    raw = raw.set_index("trade_date").reindex(calendar)
    for column in raw:
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
    formation = pd.Series(calendar <= AUDIT_END, index=calendar)
    observed = raw.trading_status.notna() & formation
    active = raw.trading_status.eq(1)
    suspended = raw.trading_status.eq(0) & formation
    turn = raw.baostock_circulating_turnover
    valid_turn = active & positive(turn)
    exact, active22 = window_flags(valid_turn)
    close_ok = active & positive(raw.close)
    open_ok = active & positive(raw.open)
    ohlc_ok = close_ok & open_ok & positive(raw.high) & positive(raw.low)
    ohlc_bad = ohlc_ok & ((raw.low > raw.open) | (raw.low > raw.close) | (raw.high < raw.open) | (raw.high < raw.close) | (raw.low > raw.high))
    current_ok = close_ok & close_ok.shift(1, fill_value=False) & formation
    next_close = close_ok.shift(-1, fill_value=False)
    next_open = open_ok.shift(-1, fill_value=False)
    p1 = current_ok & exact & next_close
    p1_active22 = current_ok & active22 & next_close
    p2 = p1 & next_open
    # Equality only, never computing return magnitude or its relationship with turnover.
    zero = current_ok & raw.close.eq(raw.close.shift(1))
    ever_st = bool((raw.is_st.eq(1) & formation).any())
    st_formation = raw.is_st.eq(1)
    qpath = root / QFQ / f"{code}.csv"
    qfq_present = pd.Series(False, index=calendar)
    qfq_min = qfq_max = ""
    if qpath.exists():
        q = pd.read_csv(qpath, usecols=["trade_date", "qfq_close"])
        q.trade_date = pd.to_datetime(q.trade_date)
        if q.trade_date.duplicated().any():
            raise ValueError(f"duplicate_qfq:{code}")
        qfq_min, qfq_max = str(q.trade_date.min().date()), str(q.trade_date.max().date())
        qfq_present.loc[calendar.isin(q.loc[positive(q.qfq_close), "trade_date"])] = True
    qfq_p1 = exact & formation & qfq_present & qfq_present.shift(1, fill_value=False) & qfq_present.shift(-1, fill_value=False)
    cap_mean = np.nan
    cap_count = 0
    cap_path = root / "data/cache/price" / f"{code}.csv"
    if cap_path.exists():
        cap = pd.read_csv(cap_path, usecols=lambda x: x in {"date", "trade_date", "circulating_market_cap"})
        if "circulating_market_cap" in cap:
            dates = pd.to_datetime(cap["trade_date" if "trade_date" in cap else "date"], errors="coerce")
            values = pd.to_numeric(cap.circulating_market_cap, errors="coerce")
            selected = dates.between(START, AUDIT_END) & positive(values)
            cap_count = int(selected.sum())
            if cap_count:
                cap_mean = float(values[selected].mean())
    history = int((ohlc_ok & formation).sum())
    sample = {
        "stock_code": code, "board": board(code), "cache_first_date": str(full_start.date()), "cache_last_date": str(full_end.date()),
        "active_ohlc_history_to_audit_cutoff": history, "observed_ever_st": ever_st,
        "st_history_scope": "2020_to_audit_cutoff_only_not_full_2002_2021", "listing_date": "UNKNOWN",
        "paper_fidelity_candidate": board(code) in {"SH_MAIN", "SZ_MAIN"} and not ever_st and history >= 2400,
        "modern_any_potential_p1": bool(p1.any()), "potential_p1_rows": int(p1.sum()),
        "potential_p2_rows": int(p2.sum()), "potential_p1_nonst_formation_rows": int((p1 & ~st_formation).sum()),
        "potential_p1_active22_rows": int(p1_active22.sum()), "historical_mean_circulating_market_cap": cap_mean,
        "size_observation_count": cap_count, "history_left_truncated": full_start <= pd.Timestamp("2020-01-02"),
    }
    ready = {
        "stock_code": code, "observed_rows": int(observed.sum()), "active_rows": int((active & formation).sum()),
        "active_positive_turnover_rows": int((valid_turn & formation).sum()), "active_zero_turnover_rows": int((active & formation & turn.eq(0)).sum()),
        "active_missing_turnover_rows": int((active & formation & turn.isna()).sum()), "suspended_rows": int(suspended.sum()),
        "suspended_zero_volume_rows": int((suspended & raw.volume_shares.eq(0)).sum()),
        "suspended_zero_turnover_rows": int((suspended & turn.eq(0)).sum()), "suspended_missing_turnover_rows": int((suspended & turn.isna()).sum()),
        "exact22_rows": int((exact & formation).sum()), "active22_rows": int((active22 & formation).sum()),
        "open_positive_active_rows": int((open_ok & formation).sum()), "close_positive_active_rows": int((close_ok & formation).sum()),
        "active_missing_or_invalid_open": int((active & formation & ~open_ok).sum()),
        "ohlc_inconsistent_rows": int((ohlc_bad & formation).sum()), "current_return_presence_rows": int(current_ok.sum()),
        "zero_current_return_rows": int(zero.sum()), "potential_p1_rows": int(p1.sum()), "potential_p2_rows": int(p2.sum()),
        "reopening_after_suspension_rows": int((active & formation & raw.trading_status.shift(1).eq(0)).sum()),
        "qfq_potential_p1_rows": int(qfq_p1.sum()), "qfq_date_min": qfq_min, "qfq_date_max": qfq_max,
    }
    return sample, ready


def mapping(ready: pd.DataFrame, samples: pd.DataFrame, arch_available: bool) -> pd.DataFrame:
    coverage = f"{int(samples.modern_any_potential_p1.sum())}/5195 potential stocks; no minimum chosen"
    span = "2020-01-02..2026-05-11 formation; next endpoint 2026-05-12"
    bao_path = str(BAO)
    rows = [
        ("A close-to-close return", "simple return; regression percentage points (p4,p6)", "yes_presence_only", "close", bao_path, "ADAPTED", span, coverage, "raw corporate actions; CSMAR adjustment unspecified", "ADAPTED_REPLICATION_FEASIBLE"),
        ("B open price", "CSMAR opening price (p4)", "yes", "open", bao_path, "ADAPTED", span, "5195 caches", "different vendor", "ADAPTED_REPLICATION_FEASIBLE"),
        ("C close price", "CSMAR closing price (p4)", "yes", "close; qfq_close", bao_path + ";" + str(QFQ), "ADAPTED", span, "5195 raw; 5180 QFQ", "QFQ canonical has no open", "ADAPTED_REPLICATION_FEASIBLE"),
        ("D daily trading volume", "daily trading volume (p5)", "yes", "volume_shares", bao_path, "CLOSE_ECONOMIC_MATCH", span, "5195 caches", "vendor differences", "ADAPTED_REPLICATION_FEASIBLE"),
        ("E float-adjusted shares", "float-adjusted shares outstanding (p5)", "partial", "CNINFO circulating_shares; vendor implicit denominator", "data/cache/h7_turnover/cninfo", "UNKNOWN", span, "5195 event caches, not exact free-float lineage", "circulating is not proven free-float-adjusted", "DATA_SUPPLEMENT_REQUIRED"),
        ("F raw turnover", "volume / float-adjusted shares (p5)", "yes_candidate", "baostock_circulating_turnover", bao_path, "CLOSE_ECONOMIC_MATCH", span, coverage, "detailed float adjustment UNKNOWN; total_share_turnover is AVAILABLE_BUT_NOT_PAPER_PRIMARY", "ADAPTED_REPLICATION_FEASIBLE"),
        ("G 22-day lagged history", "strict t-1..t-22 log mean, then max(detrended,0) (p5 Eq7)", "yes_availability_only", "baostock_circulating_turnover; trading_status", bao_path, "ADAPTED", span, coverage, "suspension rule unstated; 21-day Table2 warmup note conflicts with Eq7", "ADAPTED_REPLICATION_FEASIBLE"),
        ("H negative dummy", "1{r_t<0} (p5)", "yes_formula", "close_t vs close_t-1", bao_path, "EXACT_FORMULA", span, coverage, "only equality counts computed", "ADAPTED_REPLICATION_FEASIBLE"),
        ("I positive dummy", "1{r_t>=0}, includes zero (p5)", "yes_formula", "close_t vs close_t-1", bao_path, "EXACT_FORMULA", span, coverage, "prompt strict-positive candidate differs from paper", "ADAPTED_REPLICATION_FEASIBLE"),
        ("J conditional variance", "zero-mean GARCH(1,1), variance control scaled 1000 (p5)", str(arch_available), "not estimated", "Python environment: arch", "UNRESOLVED", "not generated", "0 real models", "arch absent; innovation/initialization/code scaling unresolved", "DATA_SUPPLEMENT_REQUIRED"),
        ("K weekday interaction", "five weekday indicators each multiply r_t (p5,p6)", "yes", "trade_date.weekday", bao_path, "EXACT_ALGEBRA", span, coverage, "conditioning-date convention should be explicit", "ADAPTED_REPLICATION_FEASIBLE"),
        ("L overnight return", "close_t -> open_t+1 (p4 Eq6)", "yes_endpoints", "close; open", bao_path, "PARTIAL", span, coverage, "raw action gaps; additive decomposition unresolved", "ADAPTED_REPLICATION_FEASIBLE"),
        ("M intraday return", "open_t+1 -> close_t+1 (p4 Eq6)", "yes_endpoints", "open; close", bao_path, "PARTIAL", span, coverage, "same source raw; exact author implementation absent", "ADAPTED_REPLICATION_FEASIBLE"),
        ("N price-limit status", "exclude conditioning limit-down days (p11-12)", "no", "not available", "reports/hypothesis_7/final_contract/h7_final_contract_readiness.md", "MISSING", "none", "0 authoritative stock-days", "no exact historical rule and listing/reform/limit-price set", "DATA_SUPPLEMENT_REQUIRED"),
        ("O A/H matched sample", "same dual-listed firms; A/H prices and turnover (p5,p8-9)", "no", "not available", "local data inventory", "MISSING", "none", "0 matched pairs", "no H-share panel or A/H mapping; no substitute", "NOT_FEASIBLE"),
        ("P stock size", "average circulating cap; stock quintiles (p10)", "partial", "circulating_market_cap", "data/cache/price", "ADAPTED", "2021 onward mostly; cutoff bounded", str(int(samples.historical_mean_circulating_market_cap.notna().sum())), "Table12 median wording vs prose/Table13 mean; no latest-size fill", "ADAPTED_REPLICATION_FEASIBLE"),
        ("Q ST status", "ever ST/*ST during 2002-2021 excluded (p9)", "partial", "is_st", bao_path, "MATERIAL_DEFINITION_DIFFERENCE", span, "5195 recent histories", "cannot establish ever-ST before 2020", "DATA_SUPPLEMENT_REQUIRED"),
        ("R main-board membership", "main-board only; no ChiNext/STAR/B shares (p9)", "yes_current_codes", "stock_code", str(UNIVERSE), "ADAPTED", "current-universe", "5195 codes", "300 and 301 both ChiNext; no historical universe", "ADAPTED_REPLICATION_FEASIBLE"),
        ("S listing/history length", ">=2400 trading days, roughly ten years (p9-10)", "insufficient", "observed active OHLC rows", bao_path, "MATERIAL_DEFINITION_DIFFERENCE", span, "0 meeting 2400", "first cache date is not listing date", "NOT_FEASIBLE"),
    ]
    columns = ["PAPER_COMPONENT", "PAPER_DEFINITION", "LOCAL_DATA_AVAILABLE", "LOCAL_FIELD", "LOCAL_PATH", "DEFINITION_MATCH", "TIME_COVERAGE", "STOCK_COVERAGE", "KNOWN_DIFFERENCE", "REPLICATION_STATUS"]
    result = pd.DataFrame(rows, columns=columns)
    result["NOTES"] = "Feasibility only; no H8 results; see h8_equation_mapping.md for source pages"
    return result


def run(root: Path) -> None:
    root = root.resolve()
    before = h7_metadata(root)
    u = pd.read_csv(root / UNIVERSE, dtype={"stock_code": str})
    codes = sorted(u.loc[u.universe_status.eq("INCLUDED"), "stock_code"].str.zfill(6).unique())
    if len(codes) != 5195:
        raise ValueError("universe_count_mismatch")
    c = pd.read_csv(root / CALENDAR, dtype={"benchmark_code": str})
    dates = pd.DatetimeIndex(pd.to_datetime(c.loc[c.benchmark_code.str.zfill(6).eq("000300"), "trade_date"]).unique()).sort_values()
    end = dates[dates.get_loc(AUDIT_END) + 1]
    calendar = dates[(dates >= START) & (dates <= end)]
    records, readiness = [], []
    for code in codes:
        sample, ready = inspect_stock(root, code, calendar)
        records.append(sample)
        readiness.append(ready)
    samples, ready = pd.DataFrame(records), pd.DataFrame(readiness)
    valid_size = samples.historical_mean_circulating_market_cap.notna()
    samples["size_quartile"] = "UNKNOWN"
    samples.loc[valid_size, "size_quartile"] = pd.qcut(samples.loc[valid_size, "historical_mean_circulating_market_cap"].rank(method="first"), 4, labels=["Q1_SMALL", "Q2", "Q3", "Q4_LARGE"]).astype(str)
    arch_available = importlib.util.find_spec("arch") is not None
    output = root / OUT
    output.mkdir(parents=True, exist_ok=True)
    samples.to_csv(output / "h8_sample_feasibility.csv", index=False, encoding="utf-8-sig")
    ready.to_csv(output / "h8_return_component_readiness.csv", index=False, encoding="utf-8-sig")
    mapping(ready, samples, arch_available).to_csv(output / "h8_paper_to_project_mapping.csv", index=False, encoding="utf-8-sig")
    totals = ready.select_dtypes(include=np.number).sum()
    thresholds = pd.DataFrame([{"history_days": n, "stocks": int(samples.active_ohlc_history_to_audit_cutoff.ge(n).sum())} for n in (750, 1000, 1250, 1500, 2000, 2400)])
    groups = []
    for name, mask in [("A_paper_fidelity", samples.paper_fidelity_candidate), ("A_main_no_observed_ST_before_history", samples.board.isin(["SH_MAIN", "SZ_MAIN"]) & ~samples.observed_ever_st), ("B_modern_any_P1_no_min_chosen", samples.modern_any_potential_p1)]:
        sub = samples.loc[mask]
        groups.append({"candidate": name, "N": len(sub), "history_median": sub.active_ohlc_history_to_audit_cutoff.median(), "history_min": sub.active_ohlc_history_to_audit_cutoff.min(), "history_max": sub.active_ohlc_history_to_audit_cutoff.max(), "observed_ever_ST": int(sub.observed_ever_st.sum()), "board_counts": str(sub.board.value_counts().to_dict()), "size_quartiles": str(sub.size_quartile.value_counts().to_dict())})
    unchanged = before == h7_metadata(root)
    if not unchanged:
        raise RuntimeError("H7_metadata_changed_during_audit")
    zero_share = totals.zero_current_return_rows / totals.current_return_presence_rows
    report = f"""# H8 Replication Feasibility & Design Mapping

## Decision summary

**Current execution readiness: H8_NOT_READY.** Recommended design direction, not a freeze: **STOCK_LEVEL_P1_P2_ADAPTED_REPLICATION**, conditional on resolving return decomposition/price treatment and a small GARCH dependency/implementation decision. No H8 coefficients, effects, significance, or real-data GARCH were computed.

Paper Primary is INDEX_LEVEL; Section 7 individual-stock analysis is DIAGNOSTIC. The current repository cannot faithfully reproduce index Primary or the 2400-day stock contract. H8 is not H7 robustness and cannot rescue or invalidate H7.

## Source and equation fidelity

The local 15-page PDF was checked at pp.4-6 (variables, Eq.7/Eq.9), pp.9-10 (Section 7/Table11), pp.11-12 (price limits), and p.14 (code availability). See `h8_equation_mapping.md` for the full algebra, controls and source anchors.

- Raw turnover target: daily volume / float-adjusted shares outstanding.
- Best local candidate: BAOSTOCK_CIRCULATING_TURNOVER; **CLOSE_ECONOMIC_MATCH**, not EXACT_MATCH. Existing H7 source-probe documentation labels the vendor denominator circulating shares. Its detailed free-float adjustments are not established by local package code; no correlation was used to certify identity.
- TOTAL_SHARE_TURNOVER is AVAILABLE_BUT_NOT_PAPER_PRIMARY; total and circulating/free-float denominators are not interchangeable.
- Recommended measurement: PAPER_STYLE_22D_TRUNCATED_TURNOVER, not H7's 200D deviation. No real detrended series was constructed in this audit.
- Recommend exact prior 22 CSI300 market dates, all active with positive finite turnover; gap invalidates the window. The paper does not specify stock-suspension handling. Last-22-active is reported only as a coverage alternative, not selected based on results.
- Paper D_POS includes zero (r>=0). Keep zero-return rows; their r-multiplied regressors are zero. This corrects the strict-positive candidate in the request using p.5.
- GARCH: arch_available={arch_available}; no dependency installed and no model estimated. A zero-mean GARCH(1,1) path requires a minimal package addition and explicit unit/initialization choices; weekday columns are available from dates.
- Equation algebra is fully mapped; exact implementation parity is **partial**, because author code, variance scaling details, suspension handling and decomposition are unresolved.

## Data-only coverage

Audit comparison interval: {calendar.min().date()} through {AUDIT_END.date()} for formation, with next endpoint {end.date()}. This does not freeze H8 cutoff. BaoStock full cache dates range {samples.cache_first_date.min()} through {samples.cache_last_date.max()}; this audit does not expand formation to those later dates.

| Measure | Value |
|---|---:|
| Universe | 5195 |
| Active rows | {int(totals.active_rows)} |
| Active positive turnover rate | {totals.active_positive_turnover_rows / totals.active_rows:.8%} |
| Active zero turnover | {int(totals.active_zero_turnover_rows)} |
| Active missing turnover | {int(totals.active_missing_turnover_rows)} |
| Suspended rows | {int(totals.suspended_rows)} |
| Suspended zero volume | {int(totals.suspended_zero_volume_rows)} |
| Suspended zero turnover / missing turnover | {int(totals.suspended_zero_turnover_rows)} / {int(totals.suspended_missing_turnover_rows)} |
| Exact22 usable rows / positive-active-current denominator | {int(totals.exact22_rows)} / {int(totals.active_positive_turnover_rows)} |
| Exact22 coverage | {totals.exact22_rows / totals.active_positive_turnover_rows:.6%} |
| Last22-active usable rows | {int(totals.active22_rows)} |
| Last22-active coverage | {totals.active22_rows / totals.active_positive_turnover_rows:.6%} |
| Active positive opens / closes | {int(totals.open_positive_active_rows)} / {int(totals.close_positive_active_rows)} |
| Active missing/invalid opens | {int(totals.active_missing_or_invalid_open)} |
| OHLC ordering inconsistencies | {int(totals.ohlc_inconsistent_rows)} |
| Potential P1 rows (before GARCH; exact22, active adjacent prices) | {int(totals.potential_p1_rows)} |
| Potential P2 rows (same plus next open) | {int(totals.potential_p2_rows)} |
| QFQ close alternative potential P1 rows (presence only) | {int(totals.qfq_potential_p1_rows)} |
| Canonical QFQ files / date span | {int(ready.qfq_date_min.ne('').sum())} / {ready.loc[ready.qfq_date_min.ne(''), 'qfq_date_min'].min()}..{ready.loc[ready.qfq_date_max.ne(''), 'qfq_date_max'].max()} |
| Potential stock count, any P1 row, no history threshold chosen | {int(samples.modern_any_potential_p1.sum())} |
| Zero current-return observations / valid current-price pairs | {int(totals.zero_current_return_rows)} / {int(totals.current_return_presence_rows)} |
| Zero current-return share | {zero_share:.8%} |
| Reopening after observed suspension | {int(totals.reopening_after_suspension_rows)} |
| Potential P1 after formation ST exclusion (candidate only) | {int(samples.potential_p1_nonst_formation_rows.sum())} |

Prices are checked by presence/positivity/equality and OHLC ordering only. No real next-day return magnitudes, sign-conditioned outcomes or return-turnover association were calculated. Strict adjacent active-price coverage omits reopening rows whose previous market-date quote is suspended/stale; it never bridges gaps.

## Sample mapping, no threshold choice

{table(thresholds)}

Counts above use active positive same-source OHLC days through the audit cutoff, not fitted regression rows. Final usable rows would be lower after lag/endpoint and GARCH requirements. All 2400-day counts are zero; selecting 750 instead is **not** authorized by this audit.

{table(pd.DataFrame(groups))}

ST selection impact: current main boards contain {int(samples.board.isin(['SH_MAIN', 'SZ_MAIN']).sum())} stocks; {int((samples.board.isin(['SH_MAIN', 'SZ_MAIN']) & samples.observed_ever_st).sum())} have observed ST history. The modern any-P1 candidate loses {int((samples.modern_any_potential_p1 & samples.observed_ever_st).sum())} stocks under an observed-ever-ST exclusion, leaving {int((samples.modern_any_potential_p1 & ~samples.observed_ever_st).sum())}. These are coverage comparisons, not chosen H8 filters.

Ever-ST means observed within available 2020-cutoff history only, not a certified 2002-2021/lifetime record. Main-board classification treats both 300 and 301 as ChiNext and 688 as STAR; no existing H7 code/classification was changed. Size quartiles use available historical mean circulating market cap through the audit cutoff, not current/latest size. First observed cache date is not listing date; listing-age selection is only visible through observed history length and left truncation.

## Price and decomposition decisions

BaoStock download script requests adjustflag=3 (raw), and cached open/high/low/close are same source/date/convention. This is the preferred **candidate** for paired intraday/overnight endpoints. It is not proven identical to CSMAR adjustment choices. Raw corporate-action gaps can contaminate overnight returns, so raw is not automatically economically clean.

Canonical broader-A QFQ contains close only, not QFQ open or an authoritative matched adjustment-factor series. It cannot guarantee consistent open/close adjustment or certify cross-ex-date overnight treatment. **QFQ_OVERNIGHT_REPLICATION_RISK=true** denotes an unverified pairing/adjustment risk, not proof that consistent QFQ necessarily creates artificial returns. Do not combine raw open with QFQ close.

**RETURN_DECOMPOSITION_CONTRACT_STATUS=UNRESOLVED.** The PDF explicitly defines simple returns yet writes an additive overnight/intraday identity. Conventional simple components obey the multiplicative identity and differ from the sum by their cross-product; only synthetic identity QA was run. Author code was not found locally or downloaded. No covert log-return substitution.

## Index and institutional inventory

| Paper index | Code | Local matching price/open/close/volume/turnover/float denominator | Full replication |
|---|---|---|---|
| SSE Composite | 000001 | none certified as index | false |
| SSE A-Share | 000002 | none certified as index | false |
| SZSE Component | 399001 | none | false |
| SZSE A-Share | 399107 | none | false |

Local benchmark panels contain CSI300 (000300), CSI1000 (000852), and ChiNext (399006), not these four targets; formal_benchmark_panel_v1_2 has no rows. Stock-cache 000001/000002 are stocks, not index observations. No constituent median turnover is substituted for aggregate index turnover. **INDEX_PRIMARY_REPLICATION=NOT_FEASIBLE** with current data.

No local H-share daily panel, H-share turnover, matched A/H identities or AHXA/AHXH panel was found in the data inventory. **P3_INSTITUTION_FEASIBLE=false**; no board, size or pre/post surrogate is used.

## Remaining mechanisms and limits

Authoritative historical limit prices/status and complete historical listing/board/ST/reform exception rules are unavailable. **historical_limit_status_ready=false; LOCAL_LIMIT_STATUS_CONSTRUCTIBLE=false** under current inputs. Price-limit robustness needs data supplementation; no return-near-10% or close==low inference is used.

**MARGIN_REFORM_REPLICATION_RELEVANT=false**: 2020-onward history has no pre-2010 period. The local candidate misses 2002-2019 market regimes and includes COVID/post-COVID and post-2021 observations. Modern broader-A adds ChiNext/STAR absent from paper stock sample. It is current-universe historical backfill, not point-in-time, with survivorship/future-universe bias. Formal paper algebra does not fix these limitations.

## Feasibility classification and human decisions

| Component | Classification | Qualification |
|---|---|---|
| P1 SIGN | ADAPTED_REPLICATION_FEASIBLE | Data presence; GARCH dependency/scaling and final sample unresolved |
| P2 TIMING | ADAPTED_REPLICATION_FEASIBLE | Same-source OHLC available; decomposition and corporate-action contract unresolved |
| P3 INSTITUTION | NOT_FEASIBLE | No A/H data |
| STOCK-LEVEL SIZE | ADAPTED_REPLICATION_FEASIBLE | Diagnostic only; recent historical coverage; no H7-gradient objective |
| PRICE-LIMIT ROBUSTNESS | DATA_SUPPLEMENT_REQUIRED | Authoritative status/rules missing |

Recommended next step: human review of raw-price corporate-action/decomposition convention, exact22 suspension rule, modern versus main-board sample and explicit minimum history, and minimal zero-mean GARCH dependency/unit contract. Then draft a separate H8 preregistration; do not run it now. Architecture direction is stock-level P1/P2 adapted, while current execution status remains H8_NOT_READY. No recommendation is based on local H8 coefficients.

## Boundary verification

H7 unchanged metadata check={unchanged} (size/mtime only; no hash framework). H7 was not imported or rerun. H7 role=PHENOMENON_DIAGNOSTIC; H8 role=MECHANISM_REPLICATION_DIAGNOSTIC.

`H8_results_opened=false; gamma_estimated=false; network_download_performed=false; MCTS_run=false; Phase_B_run=false; strategy_backtest_run=false; H7_rerun=false; H7_modified=false`.

The audit follows a data-quality workflow: denominators, temporal boundaries, unknown definitions and missing dependencies are separated from design feasibility. STOP AFTER FEASIBILITY / DESIGN MAPPING.
"""
    (output / "h8_replication_feasibility_report.md").write_text(report, encoding="utf-8")
    print(f"AUDIT_COMPLETE stocks={len(samples)} p1_stocks={samples.modern_any_potential_p1.sum()} p1_rows={int(totals.potential_p1_rows)} p2_rows={int(totals.potential_p2_rows)} zero_share={zero_share:.10f} arch_available={arch_available} H7_unchanged={unchanged}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path("."))
    run(parser.parse_args().project_root)
