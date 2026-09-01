"""Run the post-H5A historical-seen size-stratified diagnostic."""

# ruff: noqa: E501 -- report prose is kept readable in the generated Markdown.

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from scripts.audit_h5a_activity_main_effect import (
        _load_raw_covariates,
        standardized_difference,
    )
    from scripts.run_h5a_trading_activity_reversal_timing_v1 import (
        HORIZONS,
        RETURN_STATES,
        _assign_states,
        _build_stock_outcomes,
        _contrast_summary,
        _load_inputs,
        _load_needed_prices,
        _period_cells,
        _period_dates,
        direction_consistency,
        loo_sign_consistency,
        moving_block_interval,
        ordinal_groups,
    )
else:
    from audit_h5a_activity_main_effect import (
        _load_raw_covariates,
        standardized_difference,
    )
    from run_h5a_trading_activity_reversal_timing_v1 import (
        HORIZONS,
        RETURN_STATES,
        _assign_states,
        _build_stock_outcomes,
        _contrast_summary,
        _load_inputs,
        _load_needed_prices,
        _period_cells,
        _period_dates,
        direction_consistency,
        loo_sign_consistency,
        moving_block_interval,
        ordinal_groups,
    )

OUTPUT_DIR = Path("reports/hypothesis_5a")
SIZE_STATES = ("SMALL", "MID_SIZE", "LARGE")
MIN_CELL_COUNT = 25
MIN_OUTCOME_COVERAGE = 0.80

IDENTITY = {
    "analysis_type": "post_h5a_size_control_diagnostic",
    "sample_role": "historical_seen",
    "descriptive_only": True,
    "causal_claim_allowed": False,
    "alpha_claim_allowed": False,
    "oos_claim_allowed": False,
    "size_data_status": "HISTORICAL_DATED_NOT_VINTAGE_AUDITED",
    "activity_state_redefined": False,
    "return_state_redefined": False,
    "future_horizons_changed": False,
    "alternative_proxy_tested": False,
    "volatility_control_run": False,
    "MCTS_run": False,
    "Phase_B_run": False,
}


def assign_size_states(states: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame:
    """Attach signal-date total market cap and deterministic period size terciles."""
    columns = ["period_index", "stock_code", "total_market_cap"]
    merged = states.merge(raw[columns], on=["period_index", "stock_code"], how="left", validate="one_to_one")
    market_cap = pd.to_numeric(merged["total_market_cap"], errors="coerce")
    merged["log_total_market_cap"] = np.log(market_cap.where(market_cap.gt(0)))
    merged["size_state"] = pd.NA
    for _, group in merged.loc[merged["log_total_market_cap"].notna()].groupby(
        "period_index", sort=True
    ):
        merged.loc[group.index, "size_state"] = ordinal_groups(
            group, "log_total_market_cap", SIZE_STATES
        )
    return merged


def size_controlled_period(values: pd.DataFrame) -> pd.DataFrame:
    """Equal-weight available size-stratum contrasts when at least two are valid."""
    grouped = values.groupby(
        ["period_index", "return_state", "horizon"], as_index=False
    ).agg(
        valid_size_strata=("contrast", "count"),
        size_controlled_contrast=("contrast", "mean"),
    )
    grouped.loc[
        grouped["valid_size_strata"].lt(2), "size_controlled_contrast"
    ] = math.nan
    return grouped


def _validate_formal_h5a(root: Path, rebuilt: pd.DataFrame) -> None:
    official = pd.read_csv(root / OUTPUT_DIR / "h5a_period_state_returns.csv")
    keys = ["period_index", "return_state", "activity_state", "horizon"]
    columns = [
        "stock_count",
        "valid_outcome_count",
        "mean_future_return",
        "median_future_return",
        "mean_aligned_return",
        "outcome_coverage",
        "cell_valid",
    ]
    check = rebuilt[keys + columns].merge(
        official[keys + columns], on=keys, suffixes=("_rebuilt", "_official"), validate="one_to_one"
    )
    if len(check) != len(official):
        raise ValueError("formal_h5a_key_reconciliation_failed")
    for column in columns:
        left = check[f"{column}_rebuilt"]
        right = check[f"{column}_official"]
        if column == "cell_valid":
            if not left.astype(bool).equals(right.astype(bool)):
                raise ValueError(f"formal_h5a_reconciliation_failed={column}")
        elif not np.allclose(left, right, atol=1e-12, rtol=1e-10, equal_nan=True):
            raise ValueError(f"formal_h5a_reconciliation_failed={column}")


def _size_cells(states: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    eligible = states.loc[states["size_state"].notna()].copy()
    membership_keys = ["period_index", "return_state", "size_state", "activity_state"]
    membership = eligible.groupby(membership_keys, as_index=False).agg(
        membership_count=("stock_code", "size")
    )
    joined = outcomes.merge(
        eligible[["period_index", "stock_code", "size_state"]],
        on=["period_index", "stock_code"],
        how="inner",
        validate="many_to_one",
    )
    valid = joined.loc[joined["outcome_valid"]].copy()
    grouped = valid.groupby([*membership_keys, "horizon"], as_index=False).agg(
        valid_outcome_count=("future_return", "size"),
        mean_future_return=("future_return", "mean"),
        median_future_return=("future_return", "median"),
        mean_aligned_return=("aligned_return", "mean"),
    )
    grid = membership.assign(_key=1).merge(
        pd.DataFrame({"horizon": HORIZONS, "_key": 1}), on="_key"
    ).drop(columns="_key")
    cells = grid.merge(grouped, on=[*membership_keys, "horizon"], how="left", validate="one_to_one")
    cells["valid_outcome_count"] = cells["valid_outcome_count"].fillna(0).astype(int)
    cells["outcome_coverage"] = cells["valid_outcome_count"] / cells["membership_count"]
    cells["cell_valid"] = cells["membership_count"].ge(MIN_CELL_COUNT) & cells[
        "outcome_coverage"
    ].ge(MIN_OUTCOME_COVERAGE)
    return cells


def _stratum_contrasts(cells: pd.DataFrame) -> pd.DataFrame:
    rows = []
    primary = cells.loc[cells["period_index"].between(1, 56) & cells["cell_valid"]]
    for return_state in RETURN_STATES:
        value_column = (
            "mean_future_return" if return_state == "MID_RETURN" else "mean_aligned_return"
        )
        contrast_type = "raw_activity_D" if return_state == "MID_RETURN" else "aligned_activity_G"
        for size_state in SIZE_STATES:
            for horizon in HORIZONS:
                subset = primary.loc[
                    primary["return_state"].eq(return_state)
                    & primary["size_state"].eq(size_state)
                    & primary["horizon"].eq(horizon)
                ]
                pivot = subset.pivot(
                    index="period_index", columns="activity_state", values=value_column
                ).dropna(subset=["LOW_ACTIVITY", "HIGH_ACTIVITY"])
                for period, row in pivot.iterrows():
                    rows.append(
                        {
                            "period_index": period,
                            "return_state": return_state,
                            "size_state": size_state,
                            "activity_state": "HIGH_MINUS_LOW",
                            "horizon": horizon,
                            "contrast_type": contrast_type,
                            "contrast": row["HIGH_ACTIVITY"] - row["LOW_ACTIVITY"],
                        }
                    )
    return pd.DataFrame(rows)


def _summarize_values(values: pd.Series) -> dict[str, float | int]:
    values = pd.to_numeric(values, errors="coerce").dropna()
    lower, upper = moving_block_interval(values)
    return {
        "valid_periods": len(values),
        "mean_contrast": values.mean(),
        "median_contrast": values.median(),
        "direction_consistency": direction_consistency(values),
        "loo_sign_consistency": loo_sign_consistency(values),
        "bootstrap_lower_90": lower,
        "bootstrap_upper_90": upper,
    }


def _residual_size_imbalance(states: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    valid = states.loc[
        states["period_index"].between(1, 56) & states["size_state"].notna()
    ]
    for (period, return_state, size_state), group in valid.groupby(
        ["period_index", "return_state", "size_state"]
    ):
        high = group.loc[group["activity_state"].eq("HIGH_ACTIVITY"), "log_total_market_cap"]
        low = group.loc[group["activity_state"].eq("LOW_ACTIVITY"), "log_total_market_cap"]
        rows.append(
            {
                "row_type": "period_residual_size_imbalance",
                "period_index": period,
                "return_state": return_state,
                "size_state": size_state,
                "activity_state": "HIGH_MINUS_LOW",
                "horizon": math.nan,
                "mean_size_difference": high.mean() - low.mean(),
                "median_size_difference": high.median() - low.median(),
                "standardized_size_difference": standardized_difference(high, low),
                "high_count": high.notna().sum(),
                "low_count": low.notna().sum(),
            }
        )
    detail = pd.DataFrame(rows)
    summary = detail.groupby(["return_state", "size_state"], as_index=False).agg(
        valid_periods=("period_index", "nunique"),
        mean_size_difference=("mean_size_difference", "mean"),
        median_size_difference=("median_size_difference", "median"),
        standardized_size_difference=("standardized_size_difference", "mean"),
        direction_consistency=(
            "mean_size_difference",
            lambda x: direction_consistency(pd.Series(x)),
        ),
    )
    summary.insert(0, "row_type", "residual_size_imbalance")
    return detail, summary


def _cell_size_summary(cells: pd.DataFrame) -> pd.DataFrame:
    summary = cells.loc[cells["period_index"].between(1, 56)].groupby(
        ["return_state", "size_state", "activity_state"], as_index=False
    ).agg(
        periods=("period_index", "nunique"),
        median_membership=("membership_count", "median"),
        minimum_membership=("membership_count", "min"),
        p10_membership=("membership_count", lambda x: x.quantile(0.10)),
        invalid_cell_horizons=("cell_valid", lambda x: (~x).sum()),
    )
    summary.insert(0, "row_type", "cell_size_summary")
    return summary


def _summary(
    root: Path,
    stratum: pd.DataFrame,
    controlled: pd.DataFrame,
    residual_summary: pd.DataFrame,
    cell_summary: pd.DataFrame,
) -> pd.DataFrame:
    official = pd.read_csv(root / OUTPUT_DIR / "h5a_stability_summary.csv")
    original = official.loc[
        official["contrast_type"].isin(["activity_G", "mid_activity_main_effect"]),
        ["return_state", "horizon", "mean_contrast"],
    ].rename(columns={"mean_contrast": "original_h5a_contrast"})

    controlled_rows = []
    for (return_state, horizon), group in controlled.groupby(["return_state", "horizon"]):
        stats = _summarize_values(group["size_controlled_contrast"])
        controlled_rows.append(
            {
                "row_type": "size_controlled_summary",
                "return_state": return_state,
                "horizon": horizon,
                **stats,
            }
        )
    controlled_summary = pd.DataFrame(controlled_rows)

    stratum_rows = []
    for (return_state, size_state, horizon), group in stratum.groupby(
        ["return_state", "size_state", "horizon"]
    ):
        stratum_rows.append(
            {
                "row_type": "size_stratum_summary",
                "return_state": return_state,
                "size_state": size_state,
                "horizon": horizon,
                **_summarize_values(group["contrast"]),
            }
        )
    stratum_summary = pd.DataFrame(stratum_rows)
    strata = stratum_summary.pivot(
        index=["return_state", "horizon"], columns="size_state", values="mean_contrast"
    ).reset_index().rename(
        columns={"SMALL": "small_contrast", "MID_SIZE": "mid_size_contrast", "LARGE": "large_contrast"}
    )

    comparison = original.merge(
        controlled_summary,
        on=["return_state", "horizon"],
        validate="one_to_one",
    ).merge(strata, on=["return_state", "horizon"], validate="one_to_one")
    comparison["absolute_change"] = comparison["mean_contrast"] - comparison["original_h5a_contrast"]
    comparison["magnitude_retention_ratio"] = np.where(
        comparison["original_h5a_contrast"].ne(0),
        comparison["mean_contrast"].abs() / comparison["original_h5a_contrast"].abs(),
        math.nan,
    )
    comparison["strata_same_direction"] = comparison[
        ["small_contrast", "mid_size_contrast", "large_contrast"]
    ].apply(
        lambda row: len(set(np.sign(row.dropna()))) == 1 and len(row.dropna()) == 3,
        axis=1,
    )
    comparison["row_type"] = "original_vs_size_controlled"
    comparison["size_controlled_contrast"] = comparison["mean_contrast"]
    comparison = comparison.drop(columns="mean_contrast")
    return pd.concat(
        [comparison, stratum_summary, residual_summary, cell_summary],
        ignore_index=True,
        sort=False,
    )


def _markdown(frame: pd.DataFrame, columns: list[str]) -> str:
    shown = frame[columns].copy()
    for column in shown.select_dtypes(include="number"):
        shown[column] = shown[column].map(
            lambda value: "" if pd.isna(value) else f"{value:.4f}"
        )
    return shown.to_markdown(index=False)


def _write_report(path: Path, summary: pd.DataFrame) -> None:
    comparison = summary.loc[summary["row_type"].eq("original_vs_size_controlled")].copy()
    comparison["Return state"] = comparison["return_state"]
    comparison["Horizon"] = comparison["horizon"]
    comparison["Original H5A"] = comparison["original_h5a_contrast"]
    comparison["Size-controlled"] = comparison["size_controlled_contrast"]
    comparison["Retention"] = comparison["magnitude_retention_ratio"]
    comparison["Small"] = comparison["small_contrast"]
    comparison["Mid-size"] = comparison["mid_size_contrast"]
    comparison["Large"] = comparison["large_contrast"]
    comparison = comparison.sort_values(["Return state", "Horizon"])

    residual = summary.loc[summary["row_type"].eq("residual_size_imbalance")]
    cells = summary.loc[summary["row_type"].eq("cell_size_summary")]
    strata = summary.loc[summary["row_type"].eq("size_stratum_summary")]
    retention = comparison["Retention"].replace([np.inf, -np.inf], np.nan).dropna()
    same_sign = int(
        (
            np.sign(comparison["Original H5A"])
            == np.sign(comparison["Size-controlled"])
        ).sum()
    )
    three_strata = int(comparison["strata_same_direction"].sum())
    residual_abs = residual["standardized_size_difference"].abs()
    retention_map = comparison.set_index(["return_state", "horizon"])["Retention"]
    stratum_sign_counts = {
        size: int(
            (
                np.sign(comparison[column])
                == np.sign(comparison["Original H5A"])
            ).sum()
        )
        for size, column in (
            ("SMALL", "Small"),
            ("MID_SIZE", "Mid-size"),
            ("LARGE", "Large"),
        )
    }
    report = f"""# H5A Size-Control Diagnostic v1

## Technical summary

This post-H5A historical-seen diagnostic preserves all formal RETURN_STATE, ACTIVITY_STATE, signal memberships and 20D/60D/120D outcomes, then compares the original activity contrast with an equal-weight average across deterministic signal-date size terciles. The size-controlled contrast keeps the original sign in **{same_sign}/9** return-state/horizon comparisons; all three size strata share one sign in **{three_strata}/9** comparisons. Median absolute-magnitude retention is **{retention.median():.1%}**.

This is a size-stratified diagnostic, not proof that size has been eliminated or that a pure activity effect has been identified. The proxy remains an **amount-ranked multi-factor state**.

The evidence is heterogeneous and is most naturally read as **size explaining part of the original difference** rather than one uniform A/B/C case. LOW_RETURN retention is **{retention_map.loc[('LOW_RETURN', 20)]:.1%} / {retention_map.loc[('LOW_RETURN', 60)]:.1%} / {retention_map.loc[('LOW_RETURN', 120)]:.1%}** at 20D/60D/120D, while HIGH_RETURN retains **{retention_map.loc[('HIGH_RETURN', 20)]:.1%} / {retention_map.loc[('HIGH_RETURN', 60)]:.1%} / {retention_map.loc[('HIGH_RETURN', 120)]:.1%}**. MID_RETURN retains **{retention_map.loc[('MID_RETURN', 20)]:.1%} / {retention_map.loc[('MID_RETURN', 60)]:.1%} / {retention_map.loc[('MID_RETURN', 120)]:.1%}**. This is a human-readable description, not a mechanical classification gate.

## Original and size-controlled contrasts

For HIGH/LOW_RETURN, values are continuation-aligned HIGH_ACTIVITY minus LOW_ACTIVITY contrasts. MID_RETURN uses the raw future-return difference. Returns are nested cumulative outcomes from rebalance close.

{_markdown(comparison, ['Return state', 'Horizon', 'Original H5A', 'Size-controlled', 'Retention', 'Small', 'Mid-size', 'Large'])}

The comparison is descriptive: no retention threshold or new supported/not-supported gate was defined. A retention above 100% means the equal-weight size-stratum contrast is larger in absolute magnitude than the original aggregate, not stronger causal evidence.

Size-controlled stability statistics are:

{_markdown(comparison, ['Return state', 'Horizon', 'valid_periods', 'direction_consistency', 'loo_sign_consistency', 'bootstrap_lower_90', 'bootstrap_upper_90'])}

## Stratum patterns are not uniform

Across the nine return-state/horizon comparisons, SMALL, MID_SIZE and LARGE match the original H5A contrast sign in **{stratum_sign_counts['SMALL']}/9**, **{stratum_sign_counts['MID_SIZE']}/9** and **{stratum_sign_counts['LARGE']}/9** cases, respectively. All three size strata share one direction in only **{three_strata}/9** comparisons. LOW_RETURN is especially heterogeneous: at 20D/60D/120D the SMALL contrasts are negative, while MID_SIZE and LARGE are positive. HIGH_RETURN remains negative in SMALL and MID_SIZE, but LARGE turns slightly positive at 60D and 120D.

{_markdown(strata, ['return_state', 'size_state', 'horizon', 'valid_periods', 'mean_contrast', 'direction_consistency', 'loo_sign_consistency', 'bootstrap_lower_90', 'bootstrap_upper_90'])}

## Size control remains coarse

Within return-state × size-state cells, the mean absolute residual standardized HIGH_ACTIVITY−LOW_ACTIVITY log-market-cap difference is **{residual_abs.mean():.3f}σ** and the maximum is **{residual_abs.max():.3f}σ**. Therefore `COARSE_SIZE_CONTROL_REMAINS_IMPERFECT`: terciles reduce broad composition differences but do not make HIGH_ACTIVITY and LOW_ACTIVITY identical in size.

{_markdown(residual, ['return_state', 'size_state', 'valid_periods', 'mean_size_difference', 'median_size_difference', 'standardized_size_difference', 'direction_consistency'])}

## Cell support

Primary covers period_index 1–56. A period-level size-stratum contrast requires both frozen HIGH_ACTIVITY and LOW_ACTIVITY cells to have at least 25 members and at least 80% valid outcomes; the size-controlled aggregate requires at least two valid size strata. No missing endpoint was filled and no signal member was deleted or reassigned.

Across the 27 return × size × activity cells, median membership is **{cells['median_membership'].median():.1f}**, the smallest observed cell minimum is **{cells['minimum_membership'].min():.0f}**, the median p10 membership is **{cells['p10_membership'].median():.1f}**, and the smallest cell-specific p10 is **{cells['p10_membership'].min():.1f}**. Sparse extreme cells materially limit stratum-level interpretation even though the aggregate requires two valid strata.

## Statistical stability

Size-controlled and size-stratum period contrasts use period-level equal weighting. Descriptive uncertainty reuses the formal H5A six-period circular moving-block bootstrap, 10,000 repetitions and seed 20260721, with direction consistency and leave-one-period-out sign consistency. No new acceptance rule is applied.

## Data and QA

- Size is signal-date `log_total_market_cap`, status `HISTORICAL_DATED_NOT_VINTAGE_AUDITED`; missing values are not imputed.
- Size terciles use `(log_total_market_cap ascending, stock_code ascending)` within each formal signal-ready period.
- Original activity and return states are never reranked inside size cells.
- Rebuilt formal H5A stock counts, outcome counts, returns, aligned returns, coverage and validity flags reconcile to the official H5A period file at numerical tolerance.

## Interpretation boundary and next step

The table shows how much of the already-observed H5A difference survives one coarse size stratification. Size remains a major alternative explanation for LOW_RETURN and MID_RETURN, where the magnitude falls substantially and stratum signs are heterogeneous. It is not a complete substitute explanation for HIGH_RETURN, whose size-controlled values remain close to the original at 20D and 60D and retain the same aggregate sign through 120D. Persistence cannot be renamed a pure trading-activity effect because residual size imbalance, sparse cells, VOL20, price and other known exposures remain. A separately preregistered VOL20 diagnostic may be worth considering after human review; it was not run here.

## Further questions

- Is the residual within-tercile size imbalance acceptable for interpretation, given that regression, matching and finer bins were deliberately prohibited?
- Does the student want to preregister one VOL20-only follow-up, or stop after documenting the multi-factor nature of the proxy?

## Research identity

{'; '.join(f'{key}={str(value).lower() if isinstance(value, bool) else value}' for key, value in IDENTITY.items())}
"""
    path.write_text(report, encoding="utf-8")


def run(root: Path) -> None:
    root = root.resolve()
    features, calendar, availability, resolution = _load_inputs(root)
    states = _assign_states(features)
    if set(states.loc[states["period_index"].between(1, 56), "period_index"].unique()) != set(range(1, 57)):
        raise ValueError("primary_period_mismatch")

    raw = _load_raw_covariates(root, states)
    states_with_size = assign_size_states(states, raw)
    dates = _period_dates(calendar, availability)
    date_columns = ["return_start_date", *[f"endpoint_{h}d_date" for h in HORIZONS]]
    needed_dates = set(pd.to_datetime(dates[date_columns].stack()).tolist())
    prices = _load_needed_prices(root, resolution, set(states["stock_code"]), needed_dates)
    outcomes = _build_stock_outcomes(states, dates, prices)

    formal_cells = _period_cells(states, outcomes)
    _validate_formal_h5a(root, formal_cells)
    _, original_period = _contrast_summary(formal_cells)
    official_summary = pd.read_csv(root / OUTPUT_DIR / "h5a_stability_summary.csv")
    rebuilt_summary, _ = _contrast_summary(formal_cells)
    keys = ["contrast_type", "return_state", "horizon"]
    check = rebuilt_summary.merge(
        official_summary,
        on=keys,
        suffixes=("_rebuilt", "_official"),
        validate="one_to_one",
    )
    if not np.allclose(
        check["mean_contrast_rebuilt"], check["mean_contrast_official"], atol=1e-12, rtol=1e-10
    ):
        raise ValueError("formal_h5a_contrast_reconciliation_failed")

    size_cells = _size_cells(states_with_size, outcomes)
    stratum = _stratum_contrasts(size_cells)
    controlled = size_controlled_period(stratum)
    residual_detail, residual_summary = _residual_size_imbalance(states_with_size)
    cell_summary = _cell_size_summary(size_cells)
    summary = _summary(root, stratum, controlled, residual_summary, cell_summary)

    cells_output = size_cells.assign(row_type="cell_result")
    stratum_output = stratum.assign(row_type="size_stratum_contrast")
    controlled_output = controlled.assign(row_type="size_controlled_contrast")
    original_output = original_period.assign(row_type="original_h5a_period_contrast")
    period_results = pd.concat(
        [cells_output, stratum_output, controlled_output, original_output, residual_detail],
        ignore_index=True,
        sort=False,
    )

    output = root / OUTPUT_DIR
    period_results.to_csv(output / "h5a_size_control_period_results.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(output / "h5a_size_control_summary.csv", index=False, encoding="utf-8-sig")
    _write_report(output / "h5a_size_control_diagnostic.md", summary)
    print("H5A_SIZE_CONTROL_COMPLETE")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    run(args.project_root)


if __name__ == "__main__":
    main()
