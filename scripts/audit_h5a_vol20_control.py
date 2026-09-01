"""Run the post-H5A historical-seen VOL20-stratified diagnostic."""

# ruff: noqa: E501 -- report prose is kept readable in the generated Markdown.

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from scripts.audit_h5a_activity_main_effect import (
        _load_qfq_covariates,
        _load_raw_covariates,
        standardized_difference,
    )
    from scripts.audit_h5a_size_control import (
        _markdown,
        _summarize_values,
        _validate_formal_h5a,
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
        ordinal_groups,
    )
else:
    from audit_h5a_activity_main_effect import (
        _load_qfq_covariates,
        _load_raw_covariates,
        standardized_difference,
    )
    from audit_h5a_size_control import (
        _markdown,
        _summarize_values,
        _validate_formal_h5a,
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
        ordinal_groups,
    )

OUTPUT_DIR = Path("reports/hypothesis_5a")
VOL_STATES = ("LOW_VOL", "MID_VOL", "HIGH_VOL")
MIN_CELL_COUNT = 25
MIN_OUTCOME_COVERAGE = 0.80

IDENTITY = {
    "analysis_type": "post_h5a_vol20_control_diagnostic",
    "sample_role": "historical_seen",
    "descriptive_only": True,
    "causal_claim_allowed": False,
    "alpha_claim_allowed": False,
    "oos_claim_allowed": False,
    "activity_state_redefined": False,
    "return_state_redefined": False,
    "future_horizons_changed": False,
    "vol20_definition_changed": False,
    "size_control_rerun": False,
    "double_control_run": False,
    "alternative_proxy_tested": False,
    "MCTS_run": False,
    "Phase_B_run": False,
}


def assign_vol_states(
    states: pd.DataFrame, qfq: pd.DataFrame, raw: pd.DataFrame
) -> pd.DataFrame:
    """Attach formal VOL20 and deterministic period terciles without changing H5A states."""
    keys = ["period_index", "stock_code"]
    merged = states.merge(
        qfq[[*keys, "vol20"]], on=keys, how="left", validate="one_to_one"
    ).merge(
        raw[[*keys, "total_market_cap"]], on=keys, how="left", validate="one_to_one"
    )
    market_cap = pd.to_numeric(merged["total_market_cap"], errors="coerce")
    merged["log_total_market_cap"] = np.log(market_cap.where(market_cap.gt(0)))
    merged["vol_state"] = pd.NA
    for _, group in merged.loc[merged["vol20"].notna()].groupby(
        "period_index", sort=True
    ):
        merged.loc[group.index, "vol_state"] = ordinal_groups(
            group, "vol20", VOL_STATES
        )
    return merged


def vol_controlled_period(values: pd.DataFrame) -> pd.DataFrame:
    """Equal-weight available VOL-stratum contrasts when at least two are valid."""
    grouped = values.groupby(
        ["period_index", "return_state", "horizon"], as_index=False
    ).agg(
        valid_vol_strata=("contrast", "count"),
        vol20_controlled_contrast=("contrast", "mean"),
    )
    grouped.loc[
        grouped["valid_vol_strata"].lt(2), "vol20_controlled_contrast"
    ] = math.nan
    return grouped


def _vol_cells(states: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    eligible = states.loc[states["vol_state"].notna()].copy()
    keys = ["period_index", "return_state", "vol_state", "activity_state"]
    membership = eligible.groupby(keys, as_index=False).agg(
        membership_count=("stock_code", "size")
    )
    joined = outcomes.merge(
        eligible[["period_index", "stock_code", "vol_state"]],
        on=["period_index", "stock_code"],
        how="inner",
        validate="many_to_one",
    )
    valid = joined.loc[joined["outcome_valid"]]
    grouped = valid.groupby([*keys, "horizon"], as_index=False).agg(
        valid_outcome_count=("future_return", "size"),
        mean_future_return=("future_return", "mean"),
        median_future_return=("future_return", "median"),
        mean_aligned_return=("aligned_return", "mean"),
    )
    grid = membership.assign(_key=1).merge(
        pd.DataFrame({"horizon": HORIZONS, "_key": 1}), on="_key"
    ).drop(columns="_key")
    cells = grid.merge(grouped, on=[*keys, "horizon"], how="left", validate="one_to_one")
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
        for vol_state in VOL_STATES:
            for horizon in HORIZONS:
                subset = primary.loc[
                    primary["return_state"].eq(return_state)
                    & primary["vol_state"].eq(vol_state)
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
                            "vol_state": vol_state,
                            "activity_state": "HIGH_MINUS_LOW",
                            "horizon": horizon,
                            "contrast_type": contrast_type,
                            "contrast": row["HIGH_ACTIVITY"] - row["LOW_ACTIVITY"],
                        }
                    )
    return pd.DataFrame(rows)


def _residual_diagnostics(
    states: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    rows = []
    valid = states.loc[
        states["period_index"].between(1, 56) & states["vol_state"].notna()
    ]
    for (period, return_state, vol_state), group in valid.groupby(
        ["period_index", "return_state", "vol_state"]
    ):
        high = group.loc[group["activity_state"].eq("HIGH_ACTIVITY")]
        low = group.loc[group["activity_state"].eq("LOW_ACTIVITY")]
        for metric, prefix in (
            ("vol20", "vol20"),
            ("log_total_market_cap", "size"),
        ):
            high_values = high[metric]
            low_values = low[metric]
            rows.append(
                {
                    "row_type": f"period_residual_{prefix}_imbalance",
                    "period_index": period,
                    "return_state": return_state,
                    "vol_state": vol_state,
                    "activity_state": "HIGH_MINUS_LOW",
                    "horizon": math.nan,
                    "metric": metric,
                    "mean_difference": high_values.mean() - low_values.mean(),
                    "median_difference": high_values.median() - low_values.median(),
                    "standardized_difference": standardized_difference(
                        high_values, low_values
                    ),
                    "high_count": high_values.notna().sum(),
                    "low_count": low_values.notna().sum(),
                }
            )
    detail = pd.DataFrame(rows)
    summaries = []
    for prefix in ("vol20", "size"):
        subset = detail.loc[detail["row_type"].eq(f"period_residual_{prefix}_imbalance")]
        summary = subset.groupby(["return_state", "vol_state"], as_index=False).agg(
            valid_periods=("period_index", "nunique"),
            mean_difference=("mean_difference", "mean"),
            median_difference=("median_difference", "median"),
            standardized_difference=("standardized_difference", "mean"),
            direction_consistency=(
                "mean_difference", lambda x: direction_consistency(pd.Series(x))
            ),
        )
        summary.insert(0, "row_type", f"residual_{prefix}_imbalance")
        summaries.append(summary)
    return detail, summaries[0], summaries[1]


def _cell_size_summary(cells: pd.DataFrame) -> pd.DataFrame:
    summary = cells.loc[cells["period_index"].between(1, 56)].groupby(
        ["return_state", "vol_state", "activity_state"], as_index=False
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
    residual_vol: pd.DataFrame,
    residual_size: pd.DataFrame,
    cell_summary: pd.DataFrame,
) -> pd.DataFrame:
    official = pd.read_csv(root / OUTPUT_DIR / "h5a_stability_summary.csv")
    original = official.loc[
        official["contrast_type"].isin(["activity_G", "mid_activity_main_effect"]),
        ["return_state", "horizon", "mean_contrast"],
    ].rename(columns={"mean_contrast": "original_h5a_contrast"})
    size = pd.read_csv(root / OUTPUT_DIR / "h5a_size_control_summary.csv")
    size = size.loc[
        size["row_type"].eq("original_vs_size_controlled"),
        ["return_state", "horizon", "size_controlled_contrast", "magnitude_retention_ratio"],
    ].rename(columns={"magnitude_retention_ratio": "size_retention_ratio"})

    controlled_rows = []
    for (return_state, horizon), group in controlled.groupby(["return_state", "horizon"]):
        controlled_rows.append(
            {
                "row_type": "vol20_controlled_summary",
                "return_state": return_state,
                "horizon": horizon,
                **_summarize_values(group["vol20_controlled_contrast"]),
            }
        )
    controlled_summary = pd.DataFrame(controlled_rows)

    stratum_rows = []
    for (return_state, vol_state, horizon), group in stratum.groupby(
        ["return_state", "vol_state", "horizon"]
    ):
        stratum_rows.append(
            {
                "row_type": "vol_stratum_summary",
                "return_state": return_state,
                "vol_state": vol_state,
                "horizon": horizon,
                **_summarize_values(group["contrast"]),
            }
        )
    stratum_summary = pd.DataFrame(stratum_rows)
    strata = stratum_summary.pivot(
        index=["return_state", "horizon"], columns="vol_state", values="mean_contrast"
    ).reset_index().rename(
        columns={"LOW_VOL": "low_vol_contrast", "MID_VOL": "mid_vol_contrast", "HIGH_VOL": "high_vol_contrast"}
    )

    comparison = original.merge(size, on=["return_state", "horizon"], validate="one_to_one").merge(
        controlled_summary, on=["return_state", "horizon"], validate="one_to_one"
    ).merge(strata, on=["return_state", "horizon"], validate="one_to_one")
    comparison["vol20_controlled_contrast"] = comparison["mean_contrast"]
    comparison["absolute_change"] = comparison["vol20_controlled_contrast"] - comparison["original_h5a_contrast"]
    comparison["vol_retention_ratio"] = np.where(
        comparison["original_h5a_contrast"].ne(0),
        comparison["vol20_controlled_contrast"].abs() / comparison["original_h5a_contrast"].abs(),
        math.nan,
    )
    comparison["strata_same_direction"] = comparison[
        ["low_vol_contrast", "mid_vol_contrast", "high_vol_contrast"]
    ].apply(
        lambda row: len(row.dropna()) == 3 and len(set(np.sign(row.dropna()))) == 1,
        axis=1,
    )
    comparison["row_type"] = "original_size_vol20_comparison"
    comparison = comparison.drop(columns="mean_contrast")
    return pd.concat(
        [comparison, stratum_summary, residual_vol, residual_size, cell_summary],
        ignore_index=True,
        sort=False,
    )


def _write_report(path: Path, summary: pd.DataFrame) -> None:
    comparison = summary.loc[summary["row_type"].eq("original_size_vol20_comparison")].copy()
    comparison = comparison.sort_values(["return_state", "horizon"])
    strata = summary.loc[summary["row_type"].eq("vol_stratum_summary")]
    residual_vol = summary.loc[summary["row_type"].eq("residual_vol20_imbalance")]
    residual_size = summary.loc[summary["row_type"].eq("residual_size_imbalance")]
    cells = summary.loc[summary["row_type"].eq("cell_size_summary")]
    retention = comparison.set_index(["return_state", "horizon"])["vol_retention_ratio"]
    same_sign = int(
        (
            np.sign(comparison["original_h5a_contrast"])
            == np.sign(comparison["vol20_controlled_contrast"])
        ).sum()
    )
    three_same = int(comparison["strata_same_direction"].sum())
    sign_counts = {
        label: int(
            (np.sign(comparison[column]) == np.sign(comparison["original_h5a_contrast"])).sum()
        )
        for label, column in (
            ("LOW_VOL", "low_vol_contrast"),
            ("MID_VOL", "mid_vol_contrast"),
            ("HIGH_VOL", "high_vol_contrast"),
        )
    }
    report = f"""# H5A VOL20-Control Diagnostic v1

## Technical summary

This post-H5A historical-seen diagnostic preserves the formal RETURN_STATE, ACTIVITY_STATE, signal membership and 20D/60D/120D outcomes, then equal-weights activity contrasts across deterministic signal-time VOL20 terciles. The VOL20-controlled aggregate keeps the original sign in **{same_sign}/9** comparisons, while all three VOL strata share one sign in **{three_same}/9**. Median absolute-magnitude retention is **{comparison['vol_retention_ratio'].median():.1%}**.

LOW_RETURN retention is **{retention.loc[('LOW_RETURN', 20)]:.1%} / {retention.loc[('LOW_RETURN', 60)]:.1%} / {retention.loc[('LOW_RETURN', 120)]:.1%}**, MID_RETURN is **{retention.loc[('MID_RETURN', 20)]:.1%} / {retention.loc[('MID_RETURN', 60)]:.1%} / {retention.loc[('MID_RETURN', 120)]:.1%}**, and HIGH_RETURN is **{retention.loc[('HIGH_RETURN', 20)]:.1%} / {retention.loc[('HIGH_RETURN', 60)]:.1%} / {retention.loc[('HIGH_RETURN', 120)]:.1%}**. These are descriptive retention ratios, not an acceptance gate.

Among the preregistered human interpretation cases, the evidence is closest to **C: the activity-related difference largely persists within VOL20 states**, with partial attenuation on the HIGH_RETURN winner side. VOL20 explains little of the LOW_RETURN and MID_RETURN aggregate magnitude and roughly one-fifth to one-quarter of HIGH_RETURN magnitude. This is a human-readable interpretation, not a mechanical classification.

## Original, size-controlled and VOL20-controlled contrasts

HIGH/LOW_RETURN values are continuation-aligned HIGH_ACTIVITY−LOW_ACTIVITY contrasts; MID_RETURN is the raw future-return contrast. Size-Control values are read from the completed formal summary and were not rerun.

{_markdown(comparison, ['return_state', 'horizon', 'original_h5a_contrast', 'size_controlled_contrast', 'size_retention_ratio', 'vol20_controlled_contrast', 'vol_retention_ratio'])}

VOL20-controlled stability evidence is:

{_markdown(comparison, ['return_state', 'horizon', 'valid_periods', 'direction_consistency', 'loo_sign_consistency', 'bootstrap_lower_90', 'bootstrap_upper_90'])}

## VOL-stratum patterns

LOW_VOL, MID_VOL and HIGH_VOL match the original H5A sign in **{sign_counts['LOW_VOL']}/9**, **{sign_counts['MID_VOL']}/9** and **{sign_counts['HIGH_VOL']}/9** comparisons. All three strata share one direction in **{three_same}/9**. No stratum result is treated as a separate hypothesis.

For HIGH_RETURN, the LOW_VOL/MID_VOL/HIGH_VOL contrasts are all negative at every horizon: 20D **−1.46% / −1.64% / −1.52%**, 60D **−4.18% / −3.90% / −6.01%**, and 120D **−4.42% / −7.75% / −10.66%**. The winner-side pattern therefore remains visible across volatility strata, although the LOW_VOL 120D magnitude is smaller and some extreme cells have fewer valid periods.

{_markdown(strata, ['return_state', 'vol_state', 'horizon', 'valid_periods', 'mean_contrast', 'direction_consistency', 'loo_sign_consistency', 'bootstrap_lower_90', 'bootstrap_upper_90'])}

## VOL20 control remains coarse

Within return-state × VOL-state cells, the mean absolute residual standardized HIGH_ACTIVITY−LOW_ACTIVITY VOL20 difference is **{residual_vol['standardized_difference'].abs().mean():.3f}σ** and the maximum is **{residual_vol['standardized_difference'].abs().max():.3f}σ**. `COARSE_VOL20_CONTROL_REMAINS_IMPERFECT`: terciles do not make the activity states identical in volatility.

{_markdown(residual_vol, ['return_state', 'vol_state', 'valid_periods', 'mean_difference', 'median_difference', 'standardized_difference', 'direction_consistency'])}

## Size remains an accompanying confound

Without applying any double control, the same VOL strata retain a mean absolute standardized log-market-cap difference of **{residual_size['standardized_difference'].abs().mean():.3f}σ**, with a maximum of **{residual_size['standardized_difference'].abs().max():.3f}σ**. Persistence after VOL stratification therefore cannot establish an activity effect independent of size.

{_markdown(residual_size, ['return_state', 'vol_state', 'valid_periods', 'mean_difference', 'median_difference', 'standardized_difference', 'direction_consistency'])}

## Cell support and method

Across 27 return × VOL × activity cells, median membership is **{cells['median_membership'].median():.1f}**, the smallest observed cell minimum is **{cells['minimum_membership'].min():.0f}**, median p10 membership is **{cells['p10_membership'].median():.1f}**, and the smallest cell-specific p10 is **{cells['p10_membership'].min():.1f}**. Each usable cell requires at least 25 members and 80% outcome coverage; an aggregate period requires at least two valid VOL strata.

The analysis uses period_index 1–56, period-level equal weighting, and the formal H5A six-period circular moving-block bootstrap with 10,000 repetitions and seed 20260721. Missing outcomes are not filled and never alter signal membership.

## Interpretation boundary and next step

This is a VOL20-only diagnostic, not a size+VOL model. VOL20 alone is not a strong substitute explanation for the overall H5A pattern, although it explains part of the HIGH_RETURN magnitude. The largest remaining alternative explanation is size: within VOL strata the residual standardized size difference is much larger than the residual VOL20 difference, and the earlier standalone Size-Control diagnostic substantially reduced LOW_RETURN and MID_RETURN contrasts. Neither attenuation nor persistence identifies a causal or pure activity effect. The proxy remains an **amount-ranked multi-factor state**. A future study could preregister a genuinely turnover-like activity proxy, but no alternative proxy was tested here.

## Further questions

- Does the remaining size imbalance make a separate turnover-like proxy more informative than another layer of controls?
- Should the project stop at documenting confounding, or preregister one economically motivated activity proxy without parameter search?

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

    qfq = _load_qfq_covariates(root, states)
    raw = _load_raw_covariates(root, states)
    states_with_vol = assign_vol_states(states, qfq, raw)
    dates = _period_dates(calendar, availability)
    date_columns = ["return_start_date", *[f"endpoint_{h}d_date" for h in HORIZONS]]
    needed_dates = set(pd.to_datetime(dates[date_columns].stack()).tolist())
    prices = _load_needed_prices(root, resolution, set(states["stock_code"]), needed_dates)
    outcomes = _build_stock_outcomes(states, dates, prices)

    formal_cells = _period_cells(states, outcomes)
    _validate_formal_h5a(root, formal_cells)
    rebuilt_summary, original_period = _contrast_summary(formal_cells)
    official_summary = pd.read_csv(root / OUTPUT_DIR / "h5a_stability_summary.csv")
    check = rebuilt_summary.merge(
        official_summary,
        on=["contrast_type", "return_state", "horizon"],
        suffixes=("_rebuilt", "_official"),
        validate="one_to_one",
    )
    if not np.allclose(
        check["mean_contrast_rebuilt"], check["mean_contrast_official"], atol=1e-12, rtol=1e-10
    ):
        raise ValueError("formal_h5a_contrast_reconciliation_failed")

    cells = _vol_cells(states_with_vol, outcomes)
    stratum = _stratum_contrasts(cells)
    controlled = vol_controlled_period(stratum)
    residual_detail, residual_vol, residual_size = _residual_diagnostics(states_with_vol)
    cell_summary = _cell_size_summary(cells)
    summary = _summary(root, stratum, controlled, residual_vol, residual_size, cell_summary)

    period_results = pd.concat(
        [
            cells.assign(row_type="cell_result"),
            stratum.assign(row_type="vol_stratum_contrast"),
            controlled.assign(row_type="vol20_controlled_contrast"),
            original_period.assign(row_type="original_h5a_period_contrast"),
            residual_detail,
        ],
        ignore_index=True,
        sort=False,
    )
    output = root / OUTPUT_DIR
    period_results.to_csv(output / "h5a_vol20_control_period_results.csv", index=False, encoding="utf-8-sig")
    summary.to_csv(output / "h5a_vol20_control_summary.csv", index=False, encoding="utf-8-sig")
    _write_report(output / "h5a_vol20_control_diagnostic.md", summary)
    print("H5A_VOL20_CONTROL_COMPLETE")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    run(args.project_root)


if __name__ == "__main__":
    main()
