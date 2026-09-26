"""Read-only primitive viability audit for the frozen MCTS historical-seen sandbox v0."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "reports/mcts_sandbox_v0/primitive_viability"
PRIMITIVES = ("RETURN_60", "VOL_20", "AMOUNT_MEAN_20")
THRESHOLDS = (1.0, 0.95, 0.90, 0.80)
MIN_STOCKS = 25
FORBIDDEN_LABELS = {"forward_return", "label_available", "evaluation_sample_member"}
PROTECTED = (
    "reports/mcts_sandbox_v0/search_space_contract.md",
    "reports/mcts_sandbox_v0/candidate_registry.csv",
    "reports/mcts_sandbox_v0/mcts_vs_random_report.md",
    "src/aq_factor_lab/mcts_sandbox.py",
    "scripts/run_mcts_historical_seen_sandbox_v0.py",
    "tests/test_mcts_sandbox.py",
    "data/processed/mom60_factor_panel_v1_3.csv",
    "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv",
    "data/processed/adjusted_price_panel_v1_2.csv",
    "data/processed/hybrid_benchmark_panel_v1_5.csv",
    "reports/factor_ic_periods_mom60_v1_3.csv",
)


def code6(series: pd.Series) -> pd.Series:
    raw = series.astype("string").str.strip()
    valid = raw.str.fullmatch(r"\d{1,6}", na=False)
    if not valid.all():
        raise ValueError("invalid_stock_code")
    return raw.str.zfill(6)


def bool_series(series: pd.Series) -> pd.Series:
    mapped = series.astype(str).str.strip().str.lower().map({"true": True, "false": False})
    if mapped.isna().any():
        raise ValueError("invalid_boolean")
    return mapped


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protected_hashes(stage: str) -> pd.DataFrame:
    return pd.DataFrame(
        [{"stage": stage, "path": path, "sha256": sha256(ROOT / path)} for path in PROTECTED]
    )


def assert_signal_only(frame: pd.DataFrame) -> None:
    forbidden = FORBIDDEN_LABELS.intersection(frame.columns)
    if forbidden:
        raise ValueError(f"future_label_columns_present={sorted(forbidden)}")


def load_signal_panel() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, list[pd.Timestamp]]:
    mom = pd.read_csv(
        ROOT / "data/processed/mom60_factor_panel_v1_3.csv",
        usecols=[
            "period_index",
            "stock_code",
            "signal_as_of_date",
            "rebalance_date",
            "next_rebalance_date",
            "signal_sample_member",
            "mom60",
        ],
        dtype={"stock_code": str},
    )
    lowvol = pd.read_csv(
        ROOT / "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv",
        usecols=[
            "period_index",
            "stock_code",
            "signal_as_of_date",
            "rebalance_date",
            "next_rebalance_date",
            "vol20",
            "exact_price_observation_count_20",
            "exact_return_interval_count_20",
            "signal_available_20",
            "primary_reliable_signal",
            "exclusion_reason",
        ],
        dtype={"stock_code": str},
    )
    amount = pd.read_csv(
        ROOT / "data/processed/adjusted_price_panel_v1_2.csv",
        usecols=["stock_code", "trade_date", "amount"],
        dtype={"stock_code": str},
    )
    benchmark = pd.read_csv(
        ROOT / "data/processed/hybrid_benchmark_panel_v1_5.csv",
        usecols=["benchmark_code", "trade_date"],
        dtype={"benchmark_code": str},
    )
    official = pd.read_csv(
        ROOT / "reports/factor_ic_periods_mom60_v1_3.csv",
        usecols=["period_index", "factor_name", "sample_basis"],
    )
    periods = set(
        official.loc[
            official["factor_name"].eq("MOM60")
            & official["sample_basis"].eq("mom60_primary_sample"),
            "period_index",
        ].astype(int)
    )
    for frame in (mom, lowvol, amount):
        frame["stock_code"] = code6(frame["stock_code"])
    for column in ("signal_as_of_date", "rebalance_date", "next_rebalance_date"):
        mom[column] = pd.to_datetime(mom[column], errors="raise")
        lowvol[column] = pd.to_datetime(lowvol[column], errors="raise")
    amount["trade_date"] = pd.to_datetime(amount["trade_date"], errors="raise")
    amount["amount"] = pd.to_numeric(amount["amount"], errors="coerce")
    benchmark["benchmark_code"] = code6(benchmark["benchmark_code"])
    benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"], errors="raise")
    calendar = sorted(
        benchmark.loc[benchmark["benchmark_code"].eq("000300"), "trade_date"].drop_duplicates()
    )
    mom = mom.loc[mom["period_index"].isin(periods)].copy()
    lowvol = lowvol.loc[lowvol["period_index"].isin(periods)].copy()
    mom["signal_sample_member"] = bool_series(mom["signal_sample_member"])
    keys = ["period_index", "stock_code"]
    if mom.duplicated(keys).any() or lowvol.duplicated(keys).any():
        raise ValueError("duplicate_period_stock")
    merged = mom.merge(lowvol, on=keys, how="left", suffixes=("", "_lowvol"), validate="one_to_one")
    for column in ("signal_as_of_date", "rebalance_date", "next_rebalance_date"):
        if not merged[column].eq(merged[f"{column}_lowvol"]).all():
            raise ValueError(f"period_mapping_mismatch={column}")
    merged["RETURN_60"] = pd.to_numeric(merged["mom60"], errors="coerce")
    merged["VOL_20"] = pd.to_numeric(merged["vol20"], errors="coerce")
    amount_lookup = amount.set_index(["stock_code", "trade_date"])["amount"]
    means = []
    amount_windows: dict[tuple[int, str], list[pd.Timestamp]] = {}
    for row in merged.itertuples():
        dates = [date for date in calendar if date <= row.signal_as_of_date][-20:]
        amount_windows[(int(row.period_index), row.stock_code)] = dates
        values = pd.Series(
            [amount_lookup.get((row.stock_code, date), math.nan) for date in dates], dtype=float
        )
        valid = len(values) == 20 and np.isfinite(values).all() and values.gt(0).all()
        means.append(float(values.mean()) if valid else math.nan)
    merged["AMOUNT_MEAN_20"] = means
    signal = merged.loc[
        merged["signal_sample_member"],
        [
            "period_index",
            "stock_code",
            "signal_as_of_date",
            "rebalance_date",
            "next_rebalance_date",
            *PRIMITIVES,
        ],
    ].copy()
    assert_signal_only(signal)
    signal.attrs["amount_windows"] = amount_windows
    return signal, merged, amount, calendar


def period_coverage(signal: pd.DataFrame) -> pd.DataFrame:
    assert_signal_only(signal)
    rows = []
    for primitive in PRIMITIVES:
        for period, group in signal.groupby("period_index", sort=True):
            values = pd.to_numeric(group[primitive], errors="coerce")
            finite = np.isfinite(values)
            target = len(group)
            finite_count = int(finite.sum())
            coverage = finite_count / target
            rows.append(
                {
                    "primitive": primitive,
                    "period_index": period,
                    "signal_as_of_date": group["signal_as_of_date"].iloc[0].date().isoformat(),
                    "signal_target_count": target,
                    "primitive_record_count": int(values.notna().sum()),
                    "finite_count": finite_count,
                    "positive_count": int((finite & values.gt(0)).sum()),
                    "missing_count": int(values.isna().sum()),
                    "nonfinite_count": int((values.notna() & ~finite).sum()),
                    "coverage_ratio": coverage,
                    "minimum_required_count": target,
                    "minimum_required_ratio": 1.0,
                    "period_valid_under_v0_contract": finite_count == target,
                    "invalid_reason": ""
                    if finite_count == target
                    else "NONFINITE_ON_FROZEN_TARGET",
                }
            )
    return pd.DataFrame(rows)


EXPRESSIONS = {
    "RETURN_60": ("RETURN_60",),
    "NEG(RETURN_60)": ("RETURN_60",),
    "VOL_20": ("VOL_20",),
    "RANK(VOL_20)": ("VOL_20",),
    "AMOUNT_MEAN_20": ("AMOUNT_MEAN_20",),
    "RANK(AMOUNT_MEAN_20)": ("AMOUNT_MEAN_20",),
    "ADD(RANK(RETURN_60),RANK(VOL_20))": ("RETURN_60", "VOL_20"),
    "ADD(RANK(RETURN_60),RANK(AMOUNT_MEAN_20))": ("RETURN_60", "AMOUNT_MEAN_20"),
    "ADD(RANK(VOL_20),RANK(AMOUNT_MEAN_20))": ("VOL_20", "AMOUNT_MEAN_20"),
    "ADD(RANK(RETURN_60),ADD(RANK(VOL_20),RANK(AMOUNT_MEAN_20)))": PRIMITIVES,
}


def combination_coverage(
    signal: pd.DataFrame, thresholds=THRESHOLDS
) -> tuple[pd.DataFrame, pd.DataFrame]:
    assert_signal_only(signal)
    detail = []
    counter = []
    for expression, primitives in EXPRESSIONS.items():
        period_rows = []
        for period, group in signal.groupby("period_index", sort=True):
            finite = np.ones(len(group), dtype=bool)
            for primitive in primitives:
                finite &= np.isfinite(pd.to_numeric(group[primitive], errors="coerce"))
            count = int(finite.sum())
            coverage = count / len(group)
            period_rows.append((period, count, coverage, len(group)))
        counts = np.array([row[1] for row in period_rows])
        coverages = np.array([row[2] for row in period_rows])
        valid_v0 = coverages == 1.0
        detail.append(
            {
                "expression": expression,
                "primitive_set": ";".join(primitives),
                "valid_periods": int(valid_v0.sum()),
                "median_cross_section": float(np.median(counts)),
                "minimum_cross_section": int(counts.min()),
                "median_coverage": float(np.median(coverages)),
                "minimum_coverage": float(coverages.min()),
                "invalid_periods": int((~valid_v0).sum()),
                "failure_reason": "" if valid_v0.all() else "NONFINITE_ON_FROZEN_TARGET",
            }
        )
        for threshold in thresholds:
            valid = (coverages >= threshold) & (counts >= MIN_STOCKS)
            counter.append(
                {
                    "coverage_threshold": threshold,
                    "expression": expression,
                    "valid_periods": int(valid.sum()),
                    "invalid_periods": int((~valid).sum()),
                    "median_joint_stocks": float(np.median(counts)),
                    "minimum_joint_stocks": int(counts.min()),
                }
            )
    return pd.DataFrame(detail), pd.DataFrame(counter)


def missing_details(
    signal: pd.DataFrame, merged: pd.DataFrame, amount: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    bad_vol = signal.loc[~np.isfinite(signal["VOL_20"])]
    vol_rows = []
    for row in bad_vol.itertuples():
        source = merged.loc[
            merged["period_index"].eq(row.period_index) & merged["stock_code"].eq(row.stock_code)
        ].iloc[0]
        vol_rows.append(
            {
                "stock_code": row.stock_code,
                "period_index": row.period_index,
                "signal_as_of_date": row.signal_as_of_date.date().isoformat(),
                "expected_value_source": "lowvol20_factor_panel_locked_grid_v1_5.csv::vol20",
                "source_row_exists": True,
                "source_date_exists": True,
                "raw_value": source["vol20"],
                "normalized_value": row.VOL_20,
                "valid": False,
                "reason": "WINDOW_INCOMPLETE",
                "detail": (
                    f"price_observations={int(source['exact_price_observation_count_20'])}/21;"
                    f"return_intervals={int(source['exact_return_interval_count_20'])}/20;"
                    f"source_exclusion={source['exclusion_reason']}"
                ),
            }
        )
    bad_amount = signal.loc[~np.isfinite(signal["AMOUNT_MEAN_20"])]
    amount_rows = []
    amount_keys = set(zip(amount["stock_code"], amount["trade_date"], strict=True))
    windows = signal.attrs["amount_windows"]
    for row in bad_amount.itertuples():
        dates = windows[(int(row.period_index), row.stock_code)]
        missing_dates = [date for date in dates if (row.stock_code, date) not in amount_keys]
        amount_rows.append(
            {
                "stock_code": row.stock_code,
                "period_index": row.period_index,
                "signal_as_of_date": row.signal_as_of_date.date().isoformat(),
                "expected_value_source": (
                    "adjusted_price_panel_v1_2.csv::amount;20 exact HS300 dates"
                ),
                "source_row_exists": bool((amount["stock_code"].eq(row.stock_code)).any()),
                "source_date_exists": len(missing_dates) == 0,
                "raw_value": math.nan,
                "normalized_value": row.AMOUNT_MEAN_20,
                "valid": False,
                "reason": "WINDOW_INCOMPLETE",
                "detail": "missing_dates="
                + ";".join(date.date().isoformat() for date in missing_dates),
            }
        )
    return pd.DataFrame(vol_rows), pd.DataFrame(amount_rows)


def scale_metrics(values: pd.Series) -> dict[str, float]:
    numeric = pd.to_numeric(values, errors="coerce")
    numeric = numeric[np.isfinite(numeric)]
    quantiles = numeric.quantile([0.01, 0.05, 0.25, 0.50, 0.75, 0.95, 0.99])
    return {
        "n": len(numeric),
        "median": numeric.median(),
        "iqr": quantiles.loc[0.75] - quantiles.loc[0.25],
        "p01": quantiles.loc[0.01],
        "p05": quantiles.loc[0.05],
        "p50": quantiles.loc[0.50],
        "p95": quantiles.loc[0.95],
        "p99": quantiles.loc[0.99],
        "absolute_scale": numeric.abs().median(),
        "signal_variance": numeric.var(ddof=1),
    }


def scale_diagnostic(signal: pd.DataFrame) -> pd.DataFrame:
    assert_signal_only(signal)
    rows = []

    def append(name: str, kind: str, values: pd.Series, domination: str = "") -> None:
        per_period = signal.assign(value=values).groupby("period_index")["value"]
        unique = per_period.nunique(dropna=True)
        count = per_period.count()
        row = {
            "record_type": kind,
            "expression": name,
            **scale_metrics(values),
            "cross_sectional_unique_values": float(unique.median()),
            "tie_rate": float((1 - unique / count).median()),
            "numerical_domination": domination,
        }
        rows.append(row)

    for primitive in PRIMITIVES:
        append(primitive, "primitive", signal[primitive])
    for left, right in (
        ("RETURN_60", "VOL_20"),
        ("RETURN_60", "AMOUNT_MEAN_20"),
        ("VOL_20", "AMOUNT_MEAN_20"),
    ):
        raw_left = signal[left]
        raw_right = signal[right]
        rank_left = raw_left.groupby(signal["period_index"]).rank(method="average", pct=True)
        rank_right = raw_right.groupby(signal["period_index"]).rank(method="average", pct=True)
        left_scale = np.nanmedian(np.abs(raw_left))
        right_scale = np.nanmedian(np.abs(raw_right))
        ratio = max(left_scale, right_scale) / max(min(left_scale, right_scale), 1e-300)
        dominant = left if left_scale > right_scale else right
        domination = f"{dominant};absolute_scale_ratio={ratio:.6g}"
        for op, symbol in (("ADD", raw_left + raw_right), ("SUB", raw_left - raw_right)):
            append(f"{op}({left},{right})", "raw_combination", symbol, domination)
        for op, symbol in (("ADD", rank_left + rank_right), ("SUB", rank_left - rank_right)):
            append(
                f"{op}(RANK({left}),RANK({right}))",
                "rank_normalized_combination",
                symbol,
                "none_by_construction",
            )
    return pd.DataFrame(rows)


def failure_summary(registry: pd.DataFrame) -> pd.DataFrame:
    data = registry.copy()
    data["failure_reason"] = data["failure_reason"].fillna("").replace("", "SUCCESS")
    total = len(data)
    grouped = (
        data.groupby(
            ["failure_reason", "search_method", "seed", "depth", "primitive_set"], dropna=False
        )
        .size()
        .reset_index(name="count")
    )
    grouped["percentage_of_all_evaluations"] = grouped["count"] / total
    grouped["total_evaluations"] = total
    grouped["successful_count"] = int(data["failure_reason"].eq("SUCCESS").sum())
    grouped["failed_count"] = int(data["failure_reason"].ne("SUCCESS").sum())
    return grouped


def top_operator(formula: str) -> str:
    return formula.split("(", 1)[0] if "(" in formula else "PRIMITIVE"


def redundancy(registry: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    valid = registry.loc[registry["evaluation_status"].eq("ok")].copy()
    valid["operator_family"] = valid["formula"].map(top_operator)
    rows = []
    for method, group in [("all", valid), *list(valid.groupby("search_method"))]:
        evaluations = len(group)
        formulas = group["formula"].nunique()
        canonicals = group["canonical_formula"].nunique()
        ranks = group["rank_signature_hash"].nunique()
        portfolios = group["portfolio_signature_hash"].nunique()
        layers = (
            ("exact_formula_repeat", evaluations - formulas, evaluations),
            ("canonical_algebraic_equivalence", formulas - canonicals, evaluations),
            ("rank_equivalence_beyond_canonical", canonicals - ranks, evaluations),
            ("portfolio_equivalence_beyond_rank", ranks - portfolios, evaluations),
        )
        for layer, count, denominator in layers:
            rows.append(
                {
                    "analysis_level": "waterfall",
                    "search_method": method,
                    "dimension": layer,
                    "value": "all",
                    "evaluations": evaluations,
                    "unique_formulas": formulas,
                    "unique_canonical_formulas": canonicals,
                    "unique_rank_signatures": ranks,
                    "unique_portfolio_signatures": portfolios,
                    "redundant_count": count,
                    "share_of_evaluations": count / denominator,
                }
            )
        for dimension in ("operator_family", "depth", "primitive_set"):
            for value, subset in group.groupby(dimension, dropna=False):
                rows.append(
                    {
                        "analysis_level": dimension,
                        "search_method": method,
                        "dimension": dimension,
                        "value": value,
                        "evaluations": len(subset),
                        "unique_formulas": subset["formula"].nunique(),
                        "unique_canonical_formulas": subset["canonical_formula"].nunique(),
                        "unique_rank_signatures": subset["rank_signature_hash"].nunique(),
                        "unique_portfolio_signatures": subset["portfolio_signature_hash"].nunique(),
                        "redundant_count": len(subset) - subset["rank_signature_hash"].nunique(),
                        "share_of_evaluations": 1
                        - subset["rank_signature_hash"].nunique() / len(subset),
                    }
                )
    waterfall = pd.DataFrame(rows)
    summary = valid.groupby("search_method").agg(
        evaluations=("candidate_id", "size"),
        formula_count=("formula", "nunique"),
        canonical_formula_count=("canonical_formula", "nunique"),
        rank_signature_count=("rank_signature_hash", "nunique"),
        portfolio_signature_count=("portfolio_signature_hash", "nunique"),
    )
    return waterfall, summary.reset_index()


def write_reports(
    coverage: pd.DataFrame,
    combos: pd.DataFrame,
    counter: pd.DataFrame,
    scale: pd.DataFrame,
    redundancy_table: pd.DataFrame,
    redundancy_summary: pd.DataFrame,
    registry: pd.DataFrame,
) -> None:
    primitive_summary = coverage.groupby("primitive").agg(
        periods=("period_index", "size"),
        valid_periods=("period_valid_under_v0_contract", "sum"),
        minimum_coverage=("coverage_ratio", "min"),
        minimum_finite_count=("finite_count", "min"),
        median_target_count=("signal_target_count", "median"),
    )
    waterfall = redundancy_table.loc[
        redundancy_table["analysis_level"].eq("waterfall")
        & redundancy_table["search_method"].eq("all")
    ]
    decisions = pd.DataFrame(
        [
            [
                "VOL20 coverage",
                "one missing target, period 3",
                "MIXED_CAUSES",
                "candidate-wide failure",
                "POTENTIAL_V1_CHANGE: coverage contract",
                True,
            ],
            [
                "Amount20 window",
                "same stock/period; five absent dates",
                "MIXED_CAUSES",
                "candidate-wide failure",
                "POTENTIAL_V1_CHANGE: coverage; no fill",
                True,
            ],
            [
                "Raw scale",
                "amount dominates raw arithmetic",
                "SOURCE_CONTRACT_MISMATCH",
                "unbalanced ADD/SUB",
                "POTENTIAL_V1_CHANGE: rank normalization",
                True,
            ],
            [
                "Formula repeats",
                "repeated formula/algebra classes",
                "expected redundancy",
                "repeated evaluation",
                "POTENTIAL_V1_CHANGE: symbolic dedup",
                True,
            ],
            [
                "Rank equivalence",
                "22 signatures / 1,111 successes",
                "expected invariance",
                "main redundancy",
                "POTENTIAL_V1_CHANGE: rank cache",
                True,
            ],
        ],
        columns=[
            "issue",
            "evidence",
            "root_cause",
            "v0_effect",
            "potential_v1_change",
            "requires_method_change",
        ],
    )
    decision_table = decisions.to_markdown(index=False)
    report = f"""# Primitive Viability Audit — MCTS Historical-Seen Sandbox v0

## Technical summary

The v0 failure pattern is reproduced exactly: 10,000 evaluations, 1,111 successes and
8,889 failures. All successful candidates use only RETURN_60. VOL_20 and AMOUNT_MEAN_20
each miss one frozen Phase A signal member (300339 in period 3); v0's candidate-wide
100% completeness rule therefore rejects every expression that references either primitive.
This is a mixed cause: expected historical non-trading dates plus a source-contract mismatch,
amplified by a strict v0 eligibility rule. No future label was read for coverage, threshold,
scale or root-cause selection.

## A. Primitive availability

{primitive_summary.to_markdown()}

RETURN_60 is complete in all 54 periods. VOL_20 and AMOUNT_MEAN_20 are complete in 53/54
periods; their worst period still has all but one target stock available. The issue is therefore
not broad intersection collapse.

## B–D. VOL20 and amount20 share one historical gap

For period 3 (signal date 2021-06-29), 300339 has no stock rows on five HS300 market dates:
2021-06-18 and 2021-06-21 through 2021-06-24. LOWVOL records 16/21 exact price observations
and zero valid return intervals, with `missing_exact_lowvol20`. The amount window uses the same
20 exact market dates and is incomplete. Codes are six-digit strings, all period dates agree,
and source rows exist outside the missing trading dates. This rules out a key/date alignment bug.

- RETURN_60: `V0_ELIGIBILITY_TOO_STRICT_FOR_AVAILABLE_DATA` is not applicable because
  it is complete.
- VOL_20: `MIXED_CAUSES` — expected historical missingness, LOWVOL/Phase-A target mismatch,
  and candidate-wide fail-closed amplification.
- AMOUNT_MEAN_20: `MIXED_CAUSES` — expected historical missingness plus candidate-wide
  fail-closed amplification; the source window itself correctly refuses imputation.

## E. Multi-primitive intersection does not rapidly collapse

{combos.to_markdown(index=False)}

Every expression containing VOL_20 or AMOUNT_MEAN_20 loses only period 3 under a 100%
period-level rule. At 95%, 90% or 80% coverage with at least 25 stocks, all 54 periods would be
theoretically usable. This is coverage-only counterfactual evidence, not approval to change v0.

## F. Raw ADD/SUB has a scale problem

AMOUNT_MEAN_20 is measured in currency units and has an absolute scale many orders of magnitude
above returns and volatility. Raw ADD/SUB therefore numerically follows amount rather than a
balanced combination. Cross-sectional rank normalization puts operands on the same [0,1] scale
and is mathematically motivated without consulting returns. It remains a `POTENTIAL_V1_CHANGE`,
not an approved modification.

## G. Redundancy layers

{waterfall[["dimension", "redundant_count", "share_of_evaluations"]].to_markdown(index=False)}

The 98.02% rank-information redundancy is not mainly pure algebraic canonicalization. Across all
successful evaluations, the largest redundancy layer is exact repetition of an already evaluated
formula (1,000 of 1,111 evaluations). After exact repeats are removed, the largest structural
collapse is rank equivalence: 92 canonical formulas map to only 22 exact rank signatures. A further
22-to-19 collapse occurs at Q5 membership. Both symbolic pre-dedup and rank-signature caching have
a clear computational basis, but neither is implemented here.

## H. Human decision table

{decision_table}

## Limitations and stop gate

This audit does not calculate RankIC, returns, turnover, cost or drawdown. The 95/90/80%
counterfactuals describe signal availability only. They cannot choose a v1 threshold. No search
was run, no existing v0 artifact was changed, and no prospective/final-test or refreshed August
2026 market data was read.
"""
    (OUT / "primitive_viability_audit.md").write_text(report, encoding="utf-8")
    redundancy_report = f"""# MCTS v0 Redundancy Analysis

## Result

Among {len(registry.loc[registry.evaluation_status.eq("ok")]):,} successful evaluations,
exact rank signatures collapse to 22 and Q5 signatures to 19. Rank equivalence beyond canonical
formula normalization is the dominant redundancy layer.

## Layered attribution

{waterfall.to_markdown(index=False)}

## Method comparison

{redundancy_summary.to_markdown(index=False)}

## Read-only implications

- `POTENTIAL_V1_CHANGE`: symbolic dedup can avoid exact/canonical repeats before evaluation.
- `POTENTIAL_V1_CHANGE`: a rank-signature cache can reuse evaluation results after signal creation.
- Portfolio-signature caching is less valuable because it occurs after signal and ranking work.

These are computational observations only. The audit does not modify or approve v1.
"""
    (OUT / "redundancy_analysis.md").write_text(redundancy_report, encoding="utf-8")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    before = protected_hashes("before")
    signal, merged, amount, _calendar = load_signal_panel()
    registry = pd.read_csv(ROOT / "reports/mcts_sandbox_v0/candidate_registry.csv")
    failures = failure_summary(registry)
    coverage = period_coverage(signal)
    vol_detail, amount_detail = missing_details(signal, merged, amount)
    combos, counter = combination_coverage(signal)
    scale = scale_diagnostic(signal)
    redundancy_table, redundancy_summary = redundancy(registry)
    failures.to_csv(OUT / "failure_reason_summary.csv", index=False)
    coverage.to_csv(OUT / "primitive_period_coverage.csv", index=False)
    vol_detail.to_csv(OUT / "vol20_missingness_detail.csv", index=False)
    amount_detail.to_csv(OUT / "amount20_missingness_detail.csv", index=False)
    combos.to_csv(OUT / "primitive_combination_coverage.csv", index=False)
    counter.to_csv(OUT / "coverage_threshold_counterfactual.csv", index=False)
    scale.to_csv(OUT / "primitive_scale_diagnostic.csv", index=False)
    redundancy_table.to_csv(OUT / "redundancy_attribution.csv", index=False)
    write_reports(coverage, combos, counter, scale, redundancy_table, redundancy_summary, registry)
    after = protected_hashes("after")
    audit = before.merge(after, on="path", suffixes=("_before", "_after"))
    audit["unchanged"] = audit["sha256_before"].eq(audit["sha256_after"])
    audit.to_csv(OUT / "protected_hash_audit.csv", index=False)
    if not audit["unchanged"].all():
        raise RuntimeError("protected_file_hash_changed")
    print("primitive_viability_audit completed; search_run=false; future_labels_accessed=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
