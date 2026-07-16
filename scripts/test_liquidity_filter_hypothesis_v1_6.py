from __future__ import annotations

import argparse
import hashlib
import math
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

try:
    from scripts.run_lowvol_locked_grid_prototype_v1_5 import COSTS, METADATA, metrics, simulate
except ModuleNotFoundError:
    from run_lowvol_locked_grid_prototype_v1_5 import COSTS, METADATA, metrics, simulate


MIN_PERIOD_COVERAGE = 0.90
MIN_STUDY_PERIOD_SHARE = 0.90
ATOL = 1e-10
PORTFOLIOS = (
    "UNFILTERED_EW",
    "LIQUIDITY_FILTERED_EW",
    "LOWVOL_Q5_ORIGINAL",
    "LOWVOL_Q5_FILTERED",
)
OUTPUTS = (
    "liquidity_filter_amount_readiness_v1_6.csv",
    "liquidity_filter_periods_v1_6.csv",
    "liquidity_filter_summary_v1_6.csv",
    "liquidity_filter_hypothesis_v1_6.md",
)
PROTECTED = (
    "reports/lowvol_locked_grid_prototype_periods_v1_5_1.csv",
    "scripts/run_lowvol_locked_grid_prototype_v1_5_1.py",
    "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv",
    "data/processed/adjusted_price_panel_v1_2.csv",
    "data/processed/hybrid_benchmark_panel_v1_5.csv",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def strict_bool(series: pd.Series) -> pd.Series:
    mapped = series.astype(str).str.strip().str.lower().map({"true": True, "false": False})
    if mapped.isna().any():
        raise ValueError(
            f"Invalid boolean values: {sorted(series[mapped.isna()].astype(str).unique())}"
        )
    return mapped.astype(bool)


def valid_amount_mean(values: pd.Series, expected_count: int = 20) -> float:
    numeric = pd.to_numeric(values, errors="coerce")
    if len(numeric) != expected_count or not np.isfinite(numeric).all() or not numeric.gt(0).all():
        return math.nan
    return float(numeric.mean())


def median_filter(means: pd.Series) -> tuple[float, pd.Series]:
    numeric = pd.to_numeric(means, errors="coerce")
    eligible = numeric[np.isfinite(numeric)]
    if eligible.empty:
        return math.nan, pd.Series(False, index=means.index, dtype=bool)
    median = float(eligible.median())
    return median, numeric.ge(median) & np.isfinite(numeric)


def classify_conclusion(
    study_period_share: float,
    unfiltered_turnover: float,
    filtered_turnover: float,
    nonzero_cost_relative_wealth: list[float],
) -> str:
    if study_period_share + ATOL < MIN_STUDY_PERIOD_SHARE:
        return "not_supported"
    turnover_not_higher = filtered_turnover <= unfiltered_turnover + ATOL
    wealth_not_lower = all(value >= -ATOL for value in nonzero_cost_relative_wealth)
    strict_improvement = filtered_turnover < unfiltered_turnover - ATOL or any(
        value > ATOL for value in nonzero_cost_relative_wealth
    )
    if turnover_not_higher and wealth_not_lower and strict_improvement:
        return "supported_for_implementability"
    if (
        all(value < -ATOL for value in nonzero_cost_relative_wealth)
        and filtered_turnover >= unfiltered_turnover - ATOL
    ):
        return "not_supported"
    return "mixed"


def load_inputs(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, list[pd.Timestamp]]:
    factor = pd.read_csv(
        root / "data/processed/lowvol20_factor_panel_locked_grid_v1_5.csv",
        dtype={"stock_code": str},
    )
    amount = pd.read_csv(
        root / "data/processed/adjusted_price_panel_v1_2.csv",
        dtype={"stock_code": str},
    )
    benchmark = pd.read_csv(
        root / "data/processed/hybrid_benchmark_panel_v1_5.csv",
        dtype={"benchmark_code": str},
    )
    factor["stock_code"] = factor["stock_code"].str.zfill(6)
    factor["signal_as_of_date"] = pd.to_datetime(factor["signal_as_of_date"], errors="raise")
    for column in ("baseline_eligible", "signal_sample_member", "primary_reliable_signal"):
        factor[column] = strict_bool(factor[column])
    amount["stock_code"] = amount["stock_code"].str.zfill(6)
    amount["trade_date"] = pd.to_datetime(amount["trade_date"], errors="raise")
    amount["amount"] = pd.to_numeric(amount["amount"], errors="coerce")
    benchmark["trade_date"] = pd.to_datetime(benchmark["trade_date"], errors="raise")
    calendar = sorted(
        benchmark.loc[benchmark["benchmark_code"].eq("000300"), "trade_date"].drop_duplicates()
    )
    if (
        len(factor) != 3192
        or factor["stock_code"].nunique() != 56
        or factor["period_index"].nunique() != 57
    ):
        raise ValueError("Frozen factor panel is not the expected 56-stock, 57-period grid")
    if factor.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("Duplicate factor stock-period key")
    return factor, amount, calendar


def validate_amount_contract(amount: pd.DataFrame, factor: pd.DataFrame) -> dict[str, object]:
    missing = amount[amount["amount"].isna()]
    missing_counts = missing.groupby("stock_code").size().to_dict()
    nonpositive = int(amount["amount"].le(0).sum())
    finite_positive = int((np.isfinite(amount["amount"]) & amount["amount"].gt(0)).sum())
    legacy_qfq_missing = sorted(
        code
        for code, group in amount.groupby("stock_code")
        if pd.to_numeric(group["qfq_close"], errors="coerce").notna().sum() == 0
    )
    expected_missing = {"002049": 10, "002131": 3, "301171": 3}
    if (
        len(amount) != 70145
        or amount["stock_code"].nunique() != 56
        or finite_positive != 70129
        or missing_counts != expected_missing
        or nonpositive != 0
        or legacy_qfq_missing != ["002544", "300133"]
    ):
        raise ValueError("Amount data contract differs from the pre-registered readiness state")
    frozen_codes = set(factor["stock_code"])
    if not set(legacy_qfq_missing).issubset(frozen_codes):
        raise ValueError("Legacy QFQ gaps are not represented in the frozen v1.5 factor panel")
    return {
        "source_file": "data/processed/adjusted_price_panel_v1_2.csv",
        "source_column": "amount",
        "unit": "CNY_inferred_not_source_certified",
        "normalization": "pandas.to_numeric; multiplier=1; no fill",
        "raw_rows": len(amount),
        "finite_positive_rows": finite_positive,
        "missing_rows": len(missing),
        "zero_or_nonpositive_rows": nonpositive,
        "row_missing_codes": ";".join(f"{code}:{count}" for code, count in missing_counts.items()),
        "legacy_qfq_only_missing_codes": ";".join(legacy_qfq_missing),
        "date_min": amount["trade_date"].min().date().isoformat(),
        "date_max": amount["trade_date"].max().date().isoformat(),
    }


def build_liquidity_panel(
    factor: pd.DataFrame,
    amount: pd.DataFrame,
    calendar: list[pd.Timestamp],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    amount_lookup = amount.set_index(["stock_code", "trade_date"])["amount"]
    panel_parts: list[pd.DataFrame] = []
    readiness_rows: list[dict[str, object]] = []
    for period_index, raw_group in factor.groupby("period_index", sort=True):
        group = raw_group.copy()
        signal_date = group["signal_as_of_date"].iloc[0]
        window_dates = [date for date in calendar if date <= signal_date][-20:]
        means = []
        for code in group["stock_code"]:
            values = pd.Series(
                [amount_lookup.get((code, pd.Timestamp(date)), math.nan) for date in window_dates],
                dtype=float,
            )
            means.append(valid_amount_mean(values))
        group["mean_amount_20d"] = means
        baseline = group["baseline_eligible"]
        median, passed = median_filter(group.loc[baseline, "mean_amount_20d"])
        group["amount_window_complete"] = np.isfinite(group["mean_amount_20d"])
        group["liquidity_pass"] = False
        group.loc[passed.index, "liquidity_pass"] = passed
        baseline_count = int(baseline.sum())
        complete_count = int((baseline & group["amount_window_complete"]).sum())
        coverage = complete_count / baseline_count if baseline_count else math.nan
        coverage_pass = bool(np.isfinite(coverage) and coverage >= MIN_PERIOD_COVERAGE)
        group["liquidity_median"] = median
        group["eligible_stock_coverage"] = coverage
        group["amount_coverage_pass"] = coverage_pass
        incomplete_codes = sorted(
            group.loc[baseline & ~group["amount_window_complete"], "stock_code"].tolist()
        )
        readiness_rows.append(
            {
                "period_index": int(period_index),
                "rebalance_date": group["rebalance_date"].iloc[0],
                "signal_as_of_date": signal_date.date().isoformat(),
                "baseline_eligible_count": baseline_count,
                "complete_window_count": complete_count,
                "missing_window_count": baseline_count - complete_count,
                "eligible_stock_coverage": coverage,
                "coverage_pass": coverage_pass,
                "liquidity_median": median,
                "filtered_count": int(group["liquidity_pass"].sum()),
                "affected_codes": ";".join(incomplete_codes),
            }
        )
        panel_parts.append(group)
    return pd.concat(panel_parts, ignore_index=True), pd.DataFrame(readiness_rows)


def filtered_q5_codes(group: pd.DataFrame) -> list[str]:
    candidates = group.loc[
        group["liquidity_pass"]
        & group["primary_reliable_signal"]
        & pd.to_numeric(group["lowvol20"], errors="coerce").notna()
    ].sort_values(["lowvol20", "stock_code"], kind="stable")
    if len(candidates) < 5 or candidates["lowvol20"].nunique() < 5:
        return []
    return sorted(candidates.loc[np.array_split(candidates.index.to_numpy(), 5)[-1], "stock_code"])


def selected_codes(group: pd.DataFrame, portfolio: str) -> list[str]:
    if portfolio == "UNFILTERED_EW":
        mask = group["baseline_eligible"]
        return sorted(group.loc[mask, "stock_code"])
    if portfolio == "LIQUIDITY_FILTERED_EW":
        return sorted(group.loc[group["liquidity_pass"], "stock_code"])
    if portfolio == "LOWVOL_Q5_ORIGINAL":
        mask = (
            group["signal_sample_member"]
            & group["primary_reliable_signal"]
            & pd.to_numeric(group["quantile"], errors="coerce").eq(5)
        )
        return sorted(group.loc[mask, "stock_code"])
    if portfolio == "LOWVOL_Q5_FILTERED":
        return filtered_q5_codes(group)
    raise ValueError(f"Unknown portfolio: {portfolio}")


def build_observations(panel: pd.DataFrame) -> dict[str, list[dict[str, object]]]:
    result = {portfolio: [] for portfolio in PORTFOLIOS}
    for period_index, group in panel.groupby("period_index", sort=True):
        coverage_pass = bool(group["amount_coverage_pass"].iloc[0])
        for portfolio in PORTFOLIOS:
            codes = selected_codes(group, portfolio)
            labels = pd.to_numeric(
                group.set_index("stock_code").loc[codes, "forward_return"], errors="coerce"
            )
            missing = sorted(labels[labels.isna()].index.tolist())
            available = labels[labels.notna()]
            target = {code: 1.0 / len(codes) for code in codes} if codes else {}
            result[portfolio].append(
                {
                    "period_index": int(period_index),
                    "rebalance_date": group["rebalance_date"].iloc[0],
                    "next_rebalance_date": group["next_rebalance_date"].iloc[0],
                    "portfolio": portfolio,
                    "baseline_eligible_count": int(group["baseline_eligible"].sum()),
                    "amount_complete_count": int(
                        (group["baseline_eligible"] & group["amount_window_complete"]).sum()
                    ),
                    "filtered_count": int(group["liquidity_pass"].sum()),
                    "eligible_stock_coverage": group["eligible_stock_coverage"].iloc[0],
                    "liquidity_median": group["liquidity_median"].iloc[0],
                    "amount_coverage_pass": coverage_pass,
                    "selected_count": len(codes),
                    "selected_codes": ";".join(codes),
                    "end_price_missing_count": len(missing),
                    "end_price_missing_codes": ";".join(missing),
                    "target": target,
                    "returns": available.to_dict(),
                    "valid": bool(codes) and not missing,
                }
            )
    return result


def simulate_all(observations: dict[str, list[dict[str, object]]]) -> pd.DataFrame:
    frames = []
    for _portfolio, rows in observations.items():
        excluded = [row for row in rows if not row["amount_coverage_pass"]]
        included = [row for row in rows if row["amount_coverage_pass"]]
        for cost in COSTS:
            simulated = simulate(included, cost)
            excluded_frame = pd.DataFrame(
                [
                    {
                        **{
                            key: value
                            for key, value in row.items()
                            if key not in ("target", "returns", "valid")
                        },
                        "transaction_cost": cost,
                        "headline_included": False,
                        "turnover": math.nan,
                        "cost_drag": math.nan,
                        "gross_return": math.nan,
                        "net_return": math.nan,
                        "nav": math.nan,
                        "period_status": "insufficient_amount_coverage",
                    }
                    for row in excluded
                ]
            )
            frames.append(pd.concat([simulated, excluded_frame], ignore_index=True))
    periods = pd.concat(frames, ignore_index=True).sort_values(
        ["portfolio", "transaction_cost", "period_index"]
    )
    periods = periods.assign(**METADATA)
    if periods.duplicated(["period_index", "portfolio", "transaction_cost"]).any():
        raise ValueError("Duplicate output period key")
    expected_rows = len(PORTFOLIOS) * len(COSTS) * 57
    if len(periods) != expected_rows:
        raise ValueError(f"Expected {expected_rows} period rows, got {len(periods)}")
    return periods.reset_index(drop=True)


def summarize(periods: pd.DataFrame, readiness: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    rows = []
    for (portfolio, cost), group in periods.groupby(["portfolio", "transaction_cost"], sort=False):
        row = {"portfolio": portfolio, "transaction_cost": cost, **metrics(group)}
        row["valid_period_count"] = int(group["headline_included"].sum())
        row["end_price_missing_rate"] = (
            group["end_price_missing_count"].sum() / group["selected_count"].sum()
            if group["selected_count"].sum()
            else math.nan
        )
        row["average_eligible_stock_count"] = float(group["baseline_eligible_count"].mean())
        rows.append(row)
    summary = pd.DataFrame(rows)
    summary["relative_wealth_vs_comparator"] = math.nan
    for cost in COSTS:
        base = summary.loc[
            summary["portfolio"].eq("UNFILTERED_EW")
            & np.isclose(summary["transaction_cost"], cost),
            "terminal_nav",
        ].iloc[0]
        q5 = summary.loc[
            summary["portfolio"].eq("LOWVOL_Q5_ORIGINAL")
            & np.isclose(summary["transaction_cost"], cost),
            "terminal_nav",
        ].iloc[0]
        summary.loc[
            summary["portfolio"].eq("LIQUIDITY_FILTERED_EW")
            & np.isclose(summary["transaction_cost"], cost),
            "relative_wealth_vs_comparator",
        ] = summary["terminal_nav"] / base - 1
        summary.loc[
            summary["portfolio"].eq("LOWVOL_Q5_FILTERED")
            & np.isclose(summary["transaction_cost"], cost),
            "relative_wealth_vs_comparator",
        ] = summary["terminal_nav"] / q5 - 1
    unfiltered = summary[
        summary["portfolio"].eq("UNFILTERED_EW") & np.isclose(summary["transaction_cost"], 0)
    ].iloc[0]
    filtered = summary[
        summary["portfolio"].eq("LIQUIDITY_FILTERED_EW")
        & np.isclose(summary["transaction_cost"], 0)
    ].iloc[0]
    relative = summary.loc[
        summary["portfolio"].eq("LIQUIDITY_FILTERED_EW")
        & summary["transaction_cost"].isin([0.001, 0.002]),
        "relative_wealth_vs_comparator",
    ].tolist()
    conclusion = classify_conclusion(
        float(readiness["coverage_pass"].mean()),
        float(unfiltered["average_turnover"]),
        float(filtered["average_turnover"]),
        [float(value) for value in relative],
    )
    summary["primary_conclusion"] = conclusion
    return summary.assign(**METADATA), conclusion


def compact_readiness(
    contract: dict[str, object],
    panel: pd.DataFrame,
    readiness: pd.DataFrame,
) -> pd.DataFrame:
    baseline = panel["baseline_eligible"]
    incomplete = panel.loc[baseline & ~panel["amount_window_complete"]]
    concentration = readiness.loc[readiness["missing_window_count"].gt(0)]
    row = {
        **contract,
        "expected_stock_period_observations": len(panel),
        "baseline_eligible_stock_periods": int(baseline.sum()),
        "complete_windows": int((baseline & panel["amount_window_complete"]).sum()),
        "missing_windows": len(incomplete),
        "affected_stock_count": incomplete["stock_code"].nunique(),
        "affected_stocks": ";".join(sorted(incomplete["stock_code"].unique())),
        "affected_period_count": len(concentration),
        "missingness_time_concentration": ";".join(
            f"{record.rebalance_date}:{record.missing_window_count}"
            for record in concentration.itertuples(index=False)
        ),
        "period_coverage_threshold": MIN_PERIOD_COVERAGE,
        "coverage_pass_periods": int(readiness["coverage_pass"].sum()),
        "coverage_fail_periods": int((~readiness["coverage_pass"]).sum()),
        "coverage_fail_period_indices": ";".join(
            readiness.loc[~readiness["coverage_pass"], "period_index"].astype(str)
        ),
    }
    expected = {
        "expected_stock_period_observations": 3192,
        "baseline_eligible_stock_periods": 3131,
        "complete_windows": 3075,
        "missing_windows": 56,
        "affected_stock_count": 55,
        "affected_period_count": 7,
        "coverage_pass_periods": 56,
        "coverage_fail_periods": 1,
        "coverage_fail_period_indices": "0",
    }
    if any(row[key] != value for key, value in expected.items()):
        raise ValueError("Locked-grid amount readiness differs from the pre-registered table")
    return pd.DataFrame([row])


def markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    shown = frame[columns].copy()
    for column in columns:
        shown[column] = shown[column].map(
            lambda value: (
                "" if pd.isna(value) else f"{value:.6f}" if isinstance(value, float) else str(value)
            )
        )
    header = "| " + " | ".join(columns) + " |"
    separator = "|" + "|".join(["---"] * len(columns)) + "|"
    rows = ["| " + " | ".join(row) + " |" for row in shown.astype(str).to_numpy()]
    return "\n".join([header, separator, *rows])


def render_report(readiness: pd.DataFrame, summary: pd.DataFrame, conclusion: str) -> str:
    failed = readiness.loc[~readiness["coverage_pass"]]
    readiness_table = markdown_table(
        readiness,
        [
            "period_index",
            "rebalance_date",
            "baseline_eligible_count",
            "complete_window_count",
            "missing_window_count",
            "eligible_stock_coverage",
            "coverage_pass",
        ],
    )
    summary_table = markdown_table(
        summary,
        [
            "portfolio",
            "transaction_cost",
            "valid_period_count",
            "cumulative_return",
            "average_turnover",
            "terminal_nav",
            "relative_wealth_vs_comparator",
            "annualized_volatility",
            "period_endpoint_maximum_drawdown",
            "sharpe",
        ],
    )
    return f"""# Hypothesis 3: Liquidity Filtering v1.6

## Research Question

Does a transparent liquidity filter improve implementability proxies in the frozen thematic
universe? The primary comparison is equal-weight unfiltered versus equal-weight
liquidity-filtered portfolios. LOWVOL20 interaction is secondary.

## Amount Contract

- source: `data/processed/adjusted_price_panel_v1_2.csv::amount`
- unit: CNY inferred, not source-contract certified
- normalization: numeric conversion only; multiplier=1; no fill
- valid window: 20 exact CSI 300 market dates through T-1, all finite and strictly positive
- raw coverage: 70,129/70,145 positive finite rows; 16 missing; 0 nonpositive
- row-level missing: 002049=10, 002131=3, 301171=3
- legacy QFQ-only gaps: 002544 and 300133; their amount is complete and frozen v1.5
  supplies the research returns

## Readiness

{readiness_table}

- failed coverage periods: {failed["period_index"].astype(str).str.cat(sep=";") or "none"}
- primary metrics use common coverage-valid periods only; all 57 locked keys remain in the
  period output

## Pre-registered Results

{summary_table}

## Conclusion

- primary_conclusion: `{conclusion}`
- categories: `supported_for_implementability`, `mixed`, `not_supported`
- secondary LOWVOL20 rows do not determine the primary conclusion

## Boundaries

This is a research-only diagnostic and fixed-rule prototype. It does not establish executable
capacity, does not alter LOWVOL20, and is not an investment conclusion.
"""


def run(root: Path) -> int:
    root = root.resolve()
    reports = root / "reports"
    protected_before = {path: sha256(root / path) for path in PROTECTED}
    factor, amount, calendar = load_inputs(root)
    contract = validate_amount_contract(amount, factor)
    panel, readiness = build_liquidity_panel(factor, amount, calendar)
    readiness_summary = compact_readiness(contract, panel, readiness)
    periods = simulate_all(build_observations(panel))
    summary, conclusion = summarize(periods, readiness)
    report = render_report(readiness, summary, conclusion)
    if {path: sha256(root / path) for path in PROTECTED} != protected_before:
        raise RuntimeError("Protected LOWVOL inputs changed during Hypothesis 3")
    reports.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="liquidity_v1_6_", dir=reports) as directory:
        stage = Path(directory)
        readiness_summary.to_csv(stage / OUTPUTS[0], index=False)
        periods.to_csv(stage / OUTPUTS[1], index=False)
        summary.to_csv(stage / OUTPUTS[2], index=False)
        (stage / OUTPUTS[3]).write_text(report, encoding="utf-8")
        for name in OUTPUTS:
            (stage / name).replace(reports / name)
    print(f"primary_conclusion={conclusion}")
    print(f"coverage_pass_periods={int(readiness['coverage_pass'].sum())}/57")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    try:
        return run(args.project_root)
    except Exception as error:
        print(f"Hypothesis 3 failed: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
