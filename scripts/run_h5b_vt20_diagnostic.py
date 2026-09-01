"""Run the preregistered historical-seen H5B VT20 diagnostic."""

# ruff: noqa: E501 -- generated report prose is intentionally readable.

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from scripts.run_h5a_trading_activity_reversal_timing_v1 import (
        HORIZONS,
        RETURN_STATES,
        _build_stock_outcomes,
        _load_inputs,
        _load_needed_prices,
        _period_dates,
        continuation_aligned,
        direction_consistency,
        loo_sign_consistency,
        moving_block_interval,
        path_category,
    )
else:
    from run_h5a_trading_activity_reversal_timing_v1 import (
        HORIZONS,
        RETURN_STATES,
        _build_stock_outcomes,
        _load_inputs,
        _load_needed_prices,
        _period_dates,
        continuation_aligned,
        direction_consistency,
        loo_sign_consistency,
        moving_block_interval,
        path_category,
    )

VT_STATES = ("LOW_VT", "MID_VT", "HIGH_VT")
OUTPUT_DIR = Path("reports/hypothesis_5b")

IDENTITY = {
    "analysis_stage": "H5B_historical_seen_descriptive_diagnostic",
    "sample_role": "historical_seen",
    "derived_hypothesis": True,
    "future_return_accessed": True,
    "H5B_performance_run": True,
    "alpha_claim_allowed": False,
    "oos_claim_allowed": False,
    "causal_claim_allowed": False,
    "alternative_proxy_tested": False,
    "network_download_performed": False,
    "MCTS_run": False,
    "Phase_B_run": False,
    "prospective_data_accessed": False,
    "final_test_accessed": False,
}


def _bool(series: pd.Series) -> pd.Series:
    return series.astype(str).str.lower().eq("true")


def load_signal_states(root: Path) -> pd.DataFrame:
    panel = pd.read_csv(
        root / OUTPUT_DIR / "h5b_vt20_signal_panel.csv",
        dtype={"stock_code": str},
    )
    forbidden = [
        column
        for column in panel.columns
        if any(token in column.lower() for token in ("future", "forward", "endpoint"))
    ]
    if forbidden:
        raise ValueError(f"signal_panel_contains_outcomes={forbidden}")
    panel["signal_as_of_date"] = pd.to_datetime(panel["signal_as_of_date"], errors="raise")
    panel["vt20_valid"] = _bool(panel["vt20_valid"])
    states = panel.loc[panel["vt20_valid"]].rename(
        columns={"RETURN_STATE": "return_state", "VT20_STATE": "activity_state"}
    )
    if set(states["period_index"].unique()) != set(range(1, 57)):
        raise ValueError("primary_periods_not_1_to_56")
    if states.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("duplicate_h5b_signal_key")
    if not states["return_state"].isin(RETURN_STATES).all():
        raise ValueError("invalid_return_state")
    if not states["activity_state"].isin(VT_STATES).all():
        raise ValueError("invalid_vt20_state")
    return states


def build_period_cells(states: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    keys = ["period_index", "return_state", "activity_state"]
    membership = states.groupby(keys, as_index=False).agg(stock_count=("stock_code", "size"))
    valid = outcomes.loc[outcomes["outcome_valid"]].copy()
    grouped = valid.groupby([*keys, "horizon"], as_index=False).agg(
        valid_outcome_count=("future_return", "size"),
        mean_future_return=("future_return", "mean"),
        median_future_return=("future_return", "median"),
        q25_future_return=("future_return", lambda values: values.quantile(0.25)),
        q75_future_return=("future_return", lambda values: values.quantile(0.75)),
        mean_aligned_return=("aligned_return", "mean"),
        median_aligned_return=("aligned_return", "median"),
    )
    grid = membership.assign(_key=1).merge(
        pd.DataFrame({"horizon": HORIZONS, "_key": 1}), on="_key"
    ).drop(columns="_key")
    result = grid.merge(grouped, on=[*keys, "horizon"], how="left", validate="one_to_one")
    result["valid_outcome_count"] = result["valid_outcome_count"].fillna(0).astype(int)
    result["outcome_coverage"] = result["valid_outcome_count"] / result["stock_count"]
    result["iqr_future_return"] = result["q75_future_return"] - result["q25_future_return"]
    result["cell_valid"] = result["stock_count"].ge(25) & result["outcome_coverage"].ge(0.80)
    return result.rename(columns={"activity_state": "vt20_state"})


def build_path_summary(period_cells: pd.DataFrame) -> pd.DataFrame:
    valid = period_cells.loc[period_cells["cell_valid"]]
    paths = valid.groupby(["return_state", "vt20_state", "horizon"], as_index=False).agg(
        valid_periods=("mean_future_return", "count"),
        across_period_mean=("mean_future_return", "mean"),
        across_period_median=("mean_future_return", "median"),
        mean_of_cell_medians=("median_future_return", "mean"),
        across_period_mean_aligned=("mean_aligned_return", "mean"),
        across_period_median_aligned=("mean_aligned_return", "median"),
        median_signal_members=("stock_count", "median"),
        minimum_signal_members=("stock_count", "min"),
        minimum_outcome_coverage=("outcome_coverage", "min"),
    )
    paths["path_category"] = "NOT_APPLICABLE"
    for (return_state, _vt_state), group in paths.groupby(
        ["return_state", "vt20_state"], sort=False
    ):
        if return_state == "MID_RETURN":
            continue
        ordered = group.sort_values("horizon")
        category = path_category(ordered["across_period_mean_aligned"].tolist())
        paths.loc[group.index, "path_category"] = category
    paths.insert(0, "row_type", "state_path")
    return paths


def build_contrasts(period_cells: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    valid = period_cells.loc[period_cells["cell_valid"]].copy()
    summaries = []
    period_rows = []
    for return_state in RETURN_STATES:
        value_column = "mean_future_return" if return_state == "MID_RETURN" else "mean_aligned_return"
        contrast_type = "mid_raw_D" if return_state == "MID_RETURN" else "aligned_G"
        for horizon in HORIZONS:
            subset = valid.loc[
                valid["return_state"].eq(return_state) & valid["horizon"].eq(horizon)
            ]
            pivot = subset.pivot(index="period_index", columns="vt20_state", values=value_column)
            if {"LOW_VT", "HIGH_VT"}.issubset(pivot.columns):
                complete = pivot.dropna(subset=["LOW_VT", "HIGH_VT"])
                values = complete["HIGH_VT"] - complete["LOW_VT"]
            else:
                complete = pivot.iloc[0:0]
                values = pd.Series(dtype=float, index=complete.index)
            lower, upper = moving_block_interval(values)
            summaries.append(
                {
                    "contrast_type": contrast_type,
                    "return_state": return_state,
                    "horizon": horizon,
                    "valid_periods": len(values),
                    "mean_contrast": values.mean(),
                    "median_contrast_descriptive": values.median(),
                    "direction_consistency": direction_consistency(values),
                    "bootstrap_lower_90": lower,
                    "bootstrap_upper_90": upper,
                    "loo_sign_consistency": loo_sign_consistency(values),
                    "low_vt_mean": complete["LOW_VT"].mean() if "LOW_VT" in complete else math.nan,
                    "mid_vt_mean": complete["MID_VT"].mean() if "MID_VT" in complete else math.nan,
                    "high_vt_mean": complete["HIGH_VT"].mean() if "HIGH_VT" in complete else math.nan,
                }
            )
            period_rows.append(
                values.rename("contrast")
                .reset_index()
                .assign(
                    contrast_type=contrast_type,
                    return_state=return_state,
                    horizon=horizon,
                )
            )
    return pd.DataFrame(summaries), pd.concat(period_rows, ignore_index=True)


def compare_formal_h5a(root: Path, h5b: pd.DataFrame) -> pd.DataFrame:
    h5a = pd.read_csv(root / "reports/hypothesis_5a/h5a_stability_summary.csv")
    h5a = h5a.loc[
        h5a["return_state"].isin(RETURN_STATES)
        & h5a["contrast_type"].isin(["activity_G", "mid_activity_main_effect"]),
        ["return_state", "horizon", "mean_contrast"],
    ].rename(columns={"mean_contrast": "h5a_amount_contrast"})
    if len(h5a) != 9 or h5a.duplicated(["return_state", "horizon"]).any():
        raise ValueError("formal_h5a_summary_not_nine_unique_contrasts")
    comparison = h5b.merge(h5a, on=["return_state", "horizon"], validate="one_to_one")
    comparison = comparison.rename(columns={"mean_contrast": "h5b_vt20_contrast"})
    comparison["direction_same"] = np.sign(comparison["h5b_vt20_contrast"]) == np.sign(
        comparison["h5a_amount_contrast"]
    )
    comparison["magnitude_ratio"] = (
        comparison["h5b_vt20_contrast"].abs() / comparison["h5a_amount_contrast"].abs()
    )
    return comparison[
        [
            "return_state",
            "horizon",
            "h5a_amount_contrast",
            "h5b_vt20_contrast",
            "direction_same",
            "magnitude_ratio",
        ]
    ]


def _table(frame: pd.DataFrame, columns: list[str]) -> str:
    shown = frame[columns].copy()
    for column in shown.select_dtypes(include="number"):
        shown[column] = shown[column].map(lambda value: "" if pd.isna(value) else f"{value:.6f}")
    return shown.to_markdown(index=False)


def write_report(
    path: Path,
    states: pd.DataFrame,
    period_cells: pd.DataFrame,
    paths: pd.DataFrame,
    contrasts: pd.DataFrame,
    comparison: pd.DataFrame,
) -> None:
    core = contrasts.loc[contrasts["return_state"].isin(["LOW_RETURN", "HIGH_RETURN"])]
    mid = contrasts.loc[contrasts["return_state"].eq("MID_RETURN")]
    invalid_cells = int((~period_cells["cell_valid"]).sum())
    same = int(comparison["direction_same"].sum())
    total = len(comparison)
    coverage_gap = 262636 - len(states)
    report = f"""# H5B VT20_DAILY Historical-Seen Descriptive Diagnostic

## Technical summary

H5B completed all 56 locked historical-seen periods under the preregistered VT20 contract. All nine Primary contrasts have {int(contrasts['valid_periods'].min())} valid period observations; invalid period-state-horizon cells: **{invalid_cells}**. H5B has the same direction as the directly read formal H5A contrast in **{same}/{total}** comparisons. The runner does not assign a preservation category; that interpretation remains a human decision.

This is a derived historical-seen mechanism diagnostic, not Alpha discovery, independent validation, OOS evidence, a strategy result or a causal test.

## LOW/HIGH_RETURN contrasts provide the six Primary comparisons

`G_h` is HIGH_VT minus LOW_VT continuation-aligned arithmetic-mean return within the same RETURN_STATE. Medians are descriptive only.

{_table(core, ['return_state', 'horizon', 'valid_periods', 'mean_contrast', 'median_contrast_descriptive', 'direction_consistency', 'bootstrap_lower_90', 'bootstrap_upper_90', 'loo_sign_consistency'])}

## MID_RETURN provides the three preregistered raw-return contrasts

`D_h` is HIGH_VT minus LOW_VT arithmetic-mean raw return. It is reported completely and does not independently establish a turnover mechanism.

{_table(mid, ['return_state', 'horizon', 'valid_periods', 'mean_contrast', 'median_contrast_descriptive', 'direction_consistency', 'bootstrap_lower_90', 'bootstrap_upper_90', 'loo_sign_consistency'])}

## The formal H5A comparison is read directly, not recomputed

Magnitude ratio is `abs(H5B contrast) / abs(formal H5A contrast)`; it has no success threshold.

{_table(comparison, ['return_state', 'horizon', 'h5a_amount_contrast', 'h5b_vt20_contrast', 'direction_same', 'magnitude_ratio'])}

H5A used 262,636 signal-ready stock-periods; H5B fixes state membership to the 262,589 VT20-valid observations, a difference of **{coverage_gap}** observations. The formal H5A column above was not restricted to this H5B-valid subset, so the small coverage difference remains a comparison limitation.

## Coarse paths use arithmetic-mean cell returns

{_table(paths, ['return_state', 'vt20_state', 'horizon', 'valid_periods', 'across_period_mean', 'across_period_mean_aligned', 'path_category', 'median_signal_members', 'minimum_outcome_coverage'])}

Path categories use the three horizon-level across-period means, not cell medians. They identify only coarse cumulative paths and cannot locate an exact reversal date.

## Membership and outcome coverage passed the frozen rules

Signal membership was frozen before outcomes. Every cell required at least 25 signal members and at least 80% future-outcome coverage; future missingness did not alter state assignment or membership. A period contrast was formed only where both LOW_VT and HIGH_VT cells were valid. Minimum signal membership was **{int(period_cells['stock_count'].min())}** and minimum outcome coverage was **{period_cells['outcome_coverage'].min():.2%}**.

## Uncertainty is descriptive

All periods receive equal cross-period weight. The 90% circular moving-block interval uses block length 6, 10,000 repetitions and seed 20260721. Direction consistency and leave-one-period-out sign consistency are reported without creating an automatic H5B category. These statistics do not provide family-wise-error-controlled, Alpha or OOS significance.

## Human interpretation and limitations

The human reviewer should compare the nine fixed contrasts, their {same}/{total} direction agreement, magnitude ratios, coarse paths and stability descriptions against the preregistered interpretation framework. The runner intentionally does not label the result `PATTERN_LARGELY_PRESERVED`, `PATTERN_PARTIALLY_PRESERVED`, `PATTERN_NOT_PRESERVED` or `INCONCLUSIVE`.

VT20 remains materially related to VOL20 and negatively related to size. Historical market-cap vintage lineage is not audited, and the universe is current rather than point-in-time. Consequently, any visible path remains a turnover-like multi-exposure historical association, not a pure turnover effect.

## Stop boundary

No alternative proxy, lookback, neutralization, MCTS, Phase B, prospective data or final-test data was run. Further work requires a separate human decision.

## Research identity

{'; '.join(f'{key}={str(value).lower() if isinstance(value, bool) else value}' for key, value in IDENTITY.items())}
"""
    path.write_text(report, encoding="utf-8")


def run(root: Path) -> None:
    root = root.resolve()
    output = root / OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    states = load_signal_states(root)
    _, calendar, availability, resolution = _load_inputs(root)
    dates = _period_dates(calendar, availability)
    date_columns = ["return_start_date", *[f"endpoint_{horizon}d_date" for horizon in HORIZONS]]
    needed_dates = set(pd.to_datetime(dates[date_columns].stack()).tolist())
    prices = _load_needed_prices(root, resolution, set(states["stock_code"]), needed_dates)
    outcome_states = states.rename(columns={"vt20_state": "activity_state"}) if "vt20_state" in states else states
    outcomes = _build_stock_outcomes(outcome_states, dates, prices)
    outcomes["aligned_return"] = continuation_aligned(outcomes["return_state"], outcomes["future_return"])
    period_cells = build_period_cells(outcome_states, outcomes)
    paths = build_path_summary(period_cells)
    contrasts, period_contrasts = build_contrasts(period_cells)
    comparison = compare_formal_h5a(root, contrasts)

    period_cells.to_csv(output / "h5b_period_state_returns.csv", index=False, encoding="utf-8-sig")
    paths.to_csv(output / "h5b_state_path_summary.csv", index=False, encoding="utf-8-sig")
    contrasts.to_csv(output / "h5b_contrast_summary.csv", index=False, encoding="utf-8-sig")
    period_contrasts.to_csv(output / "h5b_period_contrasts.csv", index=False, encoding="utf-8-sig")
    comparison.to_csv(output / "h5b_h5a_comparison.csv", index=False, encoding="utf-8-sig")
    write_report(
        output / "h5b_diagnostic_report.md",
        states,
        period_cells,
        paths,
        contrasts,
        comparison,
    )
    print("H5B_DIAGNOSTIC_COMPLETE human_interpretation_required=true")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    run(args.project_root)


if __name__ == "__main__":
    main()
