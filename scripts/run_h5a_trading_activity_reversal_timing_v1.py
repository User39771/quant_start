"""Run the preregistered historical-seen H5A mechanism diagnostic."""

# ruff: noqa: E501 -- report prose is intentionally kept readable in the generated Markdown.

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

HORIZONS = (20, 60, 120)
ACTIVITY_STATES = ("LOW_ACTIVITY", "MID_ACTIVITY", "HIGH_ACTIVITY")
RETURN_STATES = ("LOW_RETURN", "MID_RETURN", "HIGH_RETURN")
MIN_PRIMARY_PERIODS = 45
BLOCK_LENGTH = 6
BOOTSTRAP_REPETITIONS = 10_000
BOOTSTRAP_SEED = 20260721
OUTPUT_DIR = Path("reports/hypothesis_5a")

IDENTITY = {
    "sample_role": "historical_seen",
    "research_type": "mechanism_diagnostic",
    "descriptive_only": True,
    "alpha_claim_allowed": False,
    "oos_claim_allowed": False,
    "strategy_claim_allowed": False,
    "universe_point_in_time": False,
    "survivorship_bias_possible": True,
    "prospective_data_accessed": False,
    "final_test_accessed": False,
    "MCTS_run": False,
    "Phase_B_run": False,
}


def code6(value: object) -> str:
    digits = "".join(character for character in str(value) if character.isdigit())
    return digits[-6:].zfill(6)


def ordinal_groups(frame: pd.DataFrame, column: str, labels: tuple[str, ...]) -> pd.Series:
    """Assign deterministic near-equal groups; stock_code is the fixed tie breaker."""
    ordered = frame.sort_values([column, "stock_code"], kind="stable")
    result = pd.Series(pd.NA, index=frame.index, dtype="string")
    for label, indices in zip(
        labels, np.array_split(ordered.index.to_numpy(), len(labels)), strict=True
    ):
        result.loc[indices] = label
    return result


def continuation_aligned(return_state: pd.Series, values: pd.Series) -> pd.Series:
    aligned = pd.Series(np.nan, index=values.index, dtype=float)
    aligned.loc[return_state.eq("HIGH_RETURN")] = values.loc[
        return_state.eq("HIGH_RETURN")
    ]
    aligned.loc[return_state.eq("LOW_RETURN")] = -values.loc[
        return_state.eq("LOW_RETURN")
    ]
    return aligned


def path_category(values: list[float]) -> str:
    if len(values) != 3 or not np.isfinite(values).all():
        return "NO_CLEAR_PATH"
    signs = np.sign(values)
    negative = np.flatnonzero(signs < 0)
    if len(negative):
        first = int(negative[0])
        if np.all(signs[:first] >= 0) and np.all(signs[first:] <= 0):
            return "REVERSAL_OBSERVED"
    if np.all(np.asarray(values) >= 0) and all(
        a >= b for a, b in zip(values, values[1:], strict=False)
    ):
        if any(a > b for a, b in zip(values, values[1:], strict=False)):
            return "ATTENUATES"
    if np.all(np.asarray(values) > 0):
        return "CONTINUATION_PERSISTS"
    return "NO_CLEAR_PATH"


def moving_block_interval(
    values: pd.Series,
    block_length: int = BLOCK_LENGTH,
    repetitions: int = BOOTSTRAP_REPETITIONS,
    seed: int = BOOTSTRAP_SEED,
) -> tuple[float, float]:
    data = pd.to_numeric(values, errors="coerce").dropna().to_numpy(float)
    if not len(data):
        return math.nan, math.nan
    rng = np.random.default_rng(seed)
    blocks = math.ceil(len(data) / block_length)
    starts = rng.integers(0, len(data), size=(repetitions, blocks))
    offsets = np.arange(block_length)
    samples = data[(starts[..., None] + offsets) % len(data)].reshape(repetitions, -1)
    means = samples[:, : len(data)].mean(axis=1)
    return float(np.quantile(means, 0.05)), float(np.quantile(means, 0.95))


def direction_consistency(values: pd.Series) -> float:
    data = pd.to_numeric(values, errors="coerce").dropna().to_numpy(float)
    mean = data.mean() if len(data) else math.nan
    if not np.isfinite(mean) or mean == 0:
        return math.nan
    return float((np.sign(data) == np.sign(mean)).mean())


def loo_sign_consistency(values: pd.Series) -> float:
    data = pd.to_numeric(values, errors="coerce").dropna().to_numpy(float)
    if len(data) < 2 or data.mean() == 0:
        return math.nan
    total = data.sum()
    loo = (total - data) / (len(data) - 1)
    return float((np.sign(loo) == np.sign(data.mean())).mean())


def classify_result(contrast: pd.DataFrame, path_categories: dict[tuple[str, str], str]) -> str:
    core = contrast.loc[
        contrast["contrast_type"].eq("activity_G")
        & contrast["return_state"].isin(["LOW_RETURN", "HIGH_RETURN"])
    ]
    if len(core) != 6 or core["valid_periods"].lt(MIN_PRIMARY_PERIODS).any():
        return "H5A_INCONCLUSIVE"

    side_supported = []
    for state in ("LOW_RETURN", "HIGH_RETURN"):
        side = core.loc[core["return_state"].eq(state)]
        stable = side.loc[side["stability_flag"]]
        stable_signs = np.sign(stable["mean_contrast"])
        categories = {path_categories.get((state, activity)) for activity in ACTIVITY_STATES}
        supported = (
            len(stable) >= 2
            and len(set(stable_signs)) == 1
            and len(categories - {None}) >= 2
        )
        side_supported.append(supported)
    if any(side_supported):
        return "H5A_DIAGNOSTICALLY_SUPPORTED"

    if core["stability_flag"].any():
        return "H5A_MIXED"
    for state in ("LOW_RETURN", "HIGH_RETURN"):
        ordered = core.loc[core["return_state"].eq(state) & core["activity_ordered"]]
        if len(ordered) >= 2 and len(set(np.sign(ordered["mean_contrast"]))) == 1:
            return "H5A_MIXED"
    mid = contrast.loc[contrast["contrast_type"].eq("mid_activity_main_effect")]
    if int(mid["stability_flag"].sum()) >= 2:
        return "H5A_MIXED"
    return "H5A_NOT_SUPPORTED"


def _load_inputs(root: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    features = pd.read_csv(
        root / "data/processed/h5a_broader_a_signal_features_v1.csv",
        dtype={"stock_code": str},
    )
    calendar = pd.read_csv(root / "data/processed/h5a_broader_a_signal_calendar_v1.csv")
    availability = pd.read_csv(
        root / "data/processed/h5a_broader_a_future_endpoint_availability_v1.csv",
        dtype={"stock_code": str},
    )
    resolution = pd.read_csv(
        root / "reports/hypothesis_5a_broader_a/source_resolution_report.csv",
        dtype={"stock_code": str},
    )
    features["stock_code"] = features["stock_code"].map(code6)
    features["signal_as_of_date"] = pd.to_datetime(
        features["signal_as_of_date"], errors="raise"
    )
    availability["stock_code"] = availability["stock_code"].map(code6)
    resolution["stock_code"] = resolution["stock_code"].map(code6)
    for column in ("signal_ready", "return60_valid", "amount20_valid"):
        features[column] = features[column].astype(str).str.lower().eq("true")
    if features.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("duplicate_signal_feature_key")
    if availability.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("duplicate_endpoint_availability_key")
    if features["period_index"].nunique() != 57 or calendar["period_index"].nunique() != 57:
        raise ValueError("locked_period_count_mismatch")
    counts = features.groupby("period_index")["signal_ready"].sum()
    if int(counts.loc[0]) != 68 or not counts.loc[1:56].ge(1000).all():
        raise ValueError("primary_period_eligibility_mismatch")
    return features, calendar, availability, resolution


def _assign_states(features: pd.DataFrame) -> pd.DataFrame:
    ready = features.loc[features["signal_ready"]].copy()
    ready["return_state"] = pd.NA
    ready["activity_state"] = pd.NA
    for _, group in ready.groupby("period_index", sort=True):
        ready.loc[group.index, "return_state"] = ordinal_groups(
            group, "return_60", RETURN_STATES
        )
        ready.loc[group.index, "activity_state"] = ordinal_groups(
            group, "amount_mean_20", ACTIVITY_STATES
        )
    return ready


def _period_dates(calendar: pd.DataFrame, availability: pd.DataFrame) -> pd.DataFrame:
    date_columns = [f"endpoint_{h}d_date" for h in HORIZONS]
    if any(availability.groupby("period_index")[column].nunique().gt(1).any() for column in date_columns):
        raise ValueError("endpoint_date_not_unique_within_period")
    endpoints = availability.groupby("period_index", as_index=False)[date_columns].first()
    dates = calendar.rename(columns={"rebalance_date_if_existing": "return_start_date"}).merge(
        endpoints, on="period_index", validate="one_to_one"
    )
    for column in ["signal_as_of_date", "return_start_date", *date_columns]:
        dates[column] = pd.to_datetime(dates[column], errors="raise")
    if not (dates["signal_as_of_date"] < dates["return_start_date"]).all():
        raise ValueError("signal_not_before_return_start")
    return dates


def _load_needed_prices(
    root: Path, resolution: pd.DataFrame, codes: set[str], needed_dates: set[pd.Timestamp]
) -> pd.DataFrame:
    wanted = {date.strftime("%Y-%m-%d") for date in needed_dates}
    paths = resolution.loc[
        resolution["stock_code"].isin(codes) & resolution["canonical_price_path"].notna(),
        ["stock_code", "canonical_price_path"],
    ]
    rows = []
    for item in paths.itertuples(index=False):
        path = root / str(item.canonical_price_path)
        frame = pd.read_csv(path, usecols=["trade_date", "qfq_close"])
        frame["trade_date"] = frame["trade_date"].astype(str).str[:10]
        frame = frame.loc[frame["trade_date"].isin(wanted)].copy()
        if frame["trade_date"].duplicated().any():
            raise ValueError(f"duplicate_qfq_date={item.stock_code}")
        frame["qfq_close"] = pd.to_numeric(frame["qfq_close"], errors="coerce")
        if ((~np.isfinite(frame["qfq_close"])) | frame["qfq_close"].le(0)).any():
            raise ValueError(f"invalid_qfq_close={item.stock_code}")
        frame.insert(0, "stock_code", item.stock_code)
        rows.append(frame)
    prices = pd.concat(rows, ignore_index=True)
    prices["trade_date"] = pd.to_datetime(prices["trade_date"], errors="raise")
    if prices.duplicated(["stock_code", "trade_date"]).any():
        raise ValueError("duplicate_loaded_price_key")
    return prices


def _build_stock_outcomes(
    states: pd.DataFrame, dates: pd.DataFrame, prices: pd.DataFrame
) -> pd.DataFrame:
    base = states.merge(dates, on=["period_index", "signal_as_of_date"], validate="many_to_one")
    start = prices.rename(columns={"trade_date": "return_start_date", "qfq_close": "start_close"})
    base = base.merge(start, on=["stock_code", "return_start_date"], how="left", validate="many_to_one")
    outputs = []
    for horizon in HORIZONS:
        endpoint_column = f"endpoint_{horizon}d_date"
        endpoint = prices.rename(
            columns={"trade_date": endpoint_column, "qfq_close": "endpoint_close"}
        )
        frame = base.merge(
            endpoint,
            on=["stock_code", endpoint_column],
            how="left",
            validate="many_to_one",
        )
        valid = (
            np.isfinite(frame["start_close"])
            & frame["start_close"].gt(0)
            & np.isfinite(frame["endpoint_close"])
            & frame["endpoint_close"].gt(0)
        )
        frame["future_return"] = np.where(
            valid, frame["endpoint_close"] / frame["start_close"] - 1, np.nan
        )
        frame["outcome_valid"] = valid
        frame["horizon"] = horizon
        frame["aligned_return"] = continuation_aligned(
            frame["return_state"], frame["future_return"]
        )
        outputs.append(
            frame[
                [
                    "period_index",
                    "signal_as_of_date",
                    "return_start_date",
                    endpoint_column,
                    "stock_code",
                    "return_state",
                    "activity_state",
                    "horizon",
                    "future_return",
                    "aligned_return",
                    "outcome_valid",
                ]
            ].rename(columns={endpoint_column: "endpoint_date"})
        )
    return pd.concat(outputs, ignore_index=True)


def _period_cells(states: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
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
    result["analysis_role"] = np.where(
        result["period_index"].eq(0), "low_coverage_diagnostic", "primary"
    )
    return result


def _state_paths(period_cells: pd.DataFrame) -> tuple[pd.DataFrame, dict[tuple[str, str], str]]:
    primary = period_cells.loc[
        period_cells["period_index"].between(1, 56) & period_cells["cell_valid"]
    ]
    paths = primary.groupby(
        ["return_state", "activity_state", "horizon"], as_index=False
    ).agg(
        valid_periods=("mean_future_return", "count"),
        across_period_mean=("mean_future_return", "mean"),
        across_period_median=("mean_future_return", "median"),
        mean_of_cell_medians=("median_future_return", "mean"),
        across_period_mean_aligned=("mean_aligned_return", "mean"),
        across_period_median_aligned=("mean_aligned_return", "median"),
        median_stock_count=("stock_count", "median"),
        minimum_stock_count=("stock_count", "min"),
    )
    categories: dict[tuple[str, str], str] = {}
    for (return_state, activity_state), group in paths.groupby(
        ["return_state", "activity_state"], sort=False
    ):
        ordered = group.sort_values("horizon")
        category = (
            path_category(ordered["across_period_mean_aligned"].tolist())
            if return_state != "MID_RETURN"
            else "NOT_APPLICABLE"
        )
        categories[(return_state, activity_state)] = category
        paths.loc[group.index, "path_category"] = category
    paths.insert(0, "analysis_scope", "broader_a")
    paths.insert(1, "row_type", "state_path")
    return paths, categories


def _ordered(low: float, middle: float, high: float) -> bool:
    return bool((low <= middle <= high) or (low >= middle >= high))


def _contrast_row(
    return_state: str,
    horizon: int,
    pivot: pd.DataFrame,
    contrast_type: str,
    acceptance_used: bool,
) -> tuple[dict, pd.Series]:
    complete = pivot.dropna(subset=list(ACTIVITY_STATES)).copy()
    values = complete["HIGH_ACTIVITY"] - complete["LOW_ACTIVITY"]
    lower, upper = moving_block_interval(values)
    low = float(complete["LOW_ACTIVITY"].mean()) if len(complete) else math.nan
    middle = float(complete["MID_ACTIVITY"].mean()) if len(complete) else math.nan
    high = float(complete["HIGH_ACTIVITY"].mean()) if len(complete) else math.nan
    direction = direction_consistency(values)
    loo = loo_sign_consistency(values)
    row = {
        "contrast_type": contrast_type,
        "return_state": return_state,
        "horizon": horizon,
        "valid_periods": int(len(values)),
        "mean_contrast": float(values.mean()) if len(values) else math.nan,
        "median_contrast": float(values.median()) if len(values) else math.nan,
        "direction_consistency": direction,
        "bootstrap_lower_90": lower,
        "bootstrap_upper_90": upper,
        "loo_sign_consistency": loo,
        "early_mean": float(values.loc[values.index <= 28].mean()),
        "late_mean": float(values.loc[values.index >= 29].mean()),
        "low_activity_mean": low,
        "mid_activity_mean": middle,
        "high_activity_mean": high,
        "activity_ordered": _ordered(low, middle, high),
        "acceptance_used": acceptance_used,
    }
    row["stability_flag"] = bool(
        acceptance_used
        and row["valid_periods"] >= MIN_PRIMARY_PERIODS
        and row["activity_ordered"]
        and np.isfinite(lower)
        and np.isfinite(upper)
        and (lower > 0 or upper < 0)
        and np.isfinite(direction)
        and direction >= 0.60
        and np.isfinite(loo)
        and loo >= 0.80
    )
    values.index.name = "period_index"
    return row, values


def _contrast_summary(period_cells: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    primary = period_cells.loc[
        period_cells["period_index"].between(1, 56) & period_cells["cell_valid"]
    ].copy()
    rows = []
    period_values = []
    for return_state in RETURN_STATES:
        value_column = "mean_future_return" if return_state == "MID_RETURN" else "mean_aligned_return"
        contrast_type = (
            "mid_activity_main_effect" if return_state == "MID_RETURN" else "activity_G"
        )
        for horizon in HORIZONS:
            subset = primary.loc[
                primary["return_state"].eq(return_state) & primary["horizon"].eq(horizon)
            ]
            pivot = subset.pivot(index="period_index", columns="activity_state", values=value_column)
            row, values = _contrast_row(
                return_state,
                horizon,
                pivot,
                contrast_type,
                return_state != "MID_RETURN",
            )
            rows.append(row)
            period_values.append(
                values.rename("contrast").reset_index().assign(
                    return_state=return_state, horizon=horizon, contrast_type=contrast_type
                )
            )
    period_contrasts = pd.concat(period_values, ignore_index=True)
    for horizon in HORIZONS:
        high = period_contrasts.loc[
            period_contrasts["return_state"].eq("HIGH_RETURN")
            & period_contrasts["horizon"].eq(horizon),
            ["period_index", "contrast"],
        ].rename(columns={"contrast": "g_high"})
        low = period_contrasts.loc[
            period_contrasts["return_state"].eq("LOW_RETURN")
            & period_contrasts["horizon"].eq(horizon),
            ["period_index", "contrast"],
        ].rename(columns={"contrast": "g_low"})
        interaction = high.merge(low, on="period_index", validate="one_to_one")
        values = interaction["g_high"] - interaction["g_low"]
        rows.append(
            {
                "contrast_type": "interaction_I",
                "return_state": "HIGH_MINUS_LOW_RETURN",
                "horizon": horizon,
                "valid_periods": int(len(values)),
                "mean_contrast": float(values.mean()),
                "median_contrast": float(values.median()),
                "direction_consistency": direction_consistency(values),
                "bootstrap_lower_90": math.nan,
                "bootstrap_upper_90": math.nan,
                "loo_sign_consistency": math.nan,
                "early_mean": float(values.loc[interaction["period_index"].le(28)].mean()),
                "late_mean": float(values.loc[interaction["period_index"].ge(29)].mean()),
                "low_activity_mean": math.nan,
                "mid_activity_mean": math.nan,
                "high_activity_mean": math.nan,
                "activity_ordered": False,
                "acceptance_used": False,
                "stability_flag": False,
            }
        )
    return pd.DataFrame(rows), period_contrasts


def _theme_transfer(root: Path, outcomes: pd.DataFrame) -> pd.DataFrame:
    universe = pd.read_csv(
        root / "data/processed/research_universe_lowvol_freeze_20260711.csv",
        dtype={"code": str},
    )
    universe["code"] = universe["code"].map(code6)
    memberships = []
    for theme, token in (("AI", "AI"), ("COMMERCIAL_SPACE", "商业航天")):
        part = universe.loc[universe["theme"].str.contains(token, na=False), ["code", "name"]].copy()
        part["theme_scope"] = theme
        memberships.append(part)
    membership = pd.concat(memberships, ignore_index=True).rename(columns={"code": "stock_code"})
    theme = outcomes.loc[outcomes["period_index"].between(1, 56)].merge(
        membership, on="stock_code", how="inner", validate="many_to_many"
    )
    state_keys = [
        "theme_scope",
        "period_index",
        "return_state",
        "activity_state",
        "horizon",
    ]
    aggregate = theme.groupby(state_keys, as_index=False).agg(
        stock_count=("stock_code", "size"),
        valid_outcome_count=("future_return", "count"),
        mean_future_return=("future_return", "mean"),
        median_future_return=("future_return", "median"),
    )
    totals = theme.groupby(["theme_scope", "period_index", "horizon"])["stock_code"].nunique()
    aggregate["state_occupancy"] = aggregate.apply(
        lambda row: row["stock_count"]
        / totals.loc[(row["theme_scope"], row["period_index"], row["horizon"])],
        axis=1,
    )
    aggregate.insert(0, "row_type", "theme_state_summary")
    aggregate["stock_code"] = ""
    aggregate["name"] = ""
    aggregate["individual_future_return"] = math.nan

    space = theme.loc[theme["theme_scope"].eq("COMMERCIAL_SPACE")].copy()
    space.insert(0, "row_type", "commercial_space_stock")
    space["stock_count"] = 1
    space["valid_outcome_count"] = space["outcome_valid"].astype(int)
    space["state_occupancy"] = math.nan
    space["mean_future_return"] = math.nan
    space["median_future_return"] = math.nan
    space["individual_future_return"] = space["future_return"]
    columns = [
        "row_type",
        "theme_scope",
        "period_index",
        "stock_code",
        "name",
        "return_state",
        "activity_state",
        "horizon",
        "stock_count",
        "valid_outcome_count",
        "state_occupancy",
        "mean_future_return",
        "median_future_return",
        "individual_future_return",
    ]
    return pd.concat([aggregate[columns], space[columns]], ignore_index=True)


def _markdown_table(frame: pd.DataFrame, columns: list[str]) -> str:
    shown = frame[columns].copy()
    for column in shown.select_dtypes(include="number"):
        shown[column] = shown[column].map(lambda value: "" if pd.isna(value) else f"{value:.6f}")
    return shown.to_markdown(index=False)


def _ai_direction_table(theme: pd.DataFrame, core_contrasts: pd.DataFrame) -> pd.DataFrame:
    ai = theme.loc[
        theme["row_type"].eq("theme_state_summary")
        & theme["theme_scope"].eq("AI")
        & theme["return_state"].isin(["LOW_RETURN", "HIGH_RETURN"])
    ].copy()
    ai["aligned_mean"] = np.where(
        ai["return_state"].eq("LOW_RETURN"),
        -ai["mean_future_return"],
        ai["mean_future_return"],
    )
    rows = []
    for return_state in ("LOW_RETURN", "HIGH_RETURN"):
        for horizon in HORIZONS:
            subset = ai.loc[
                ai["return_state"].eq(return_state) & ai["horizon"].eq(horizon)
            ]
            pivot = subset.pivot(
                index="period_index", columns="activity_state", values="aligned_mean"
            ).dropna(subset=["LOW_ACTIVITY", "HIGH_ACTIVITY"])
            ai_g = float((pivot["HIGH_ACTIVITY"] - pivot["LOW_ACTIVITY"]).mean())
            broader_g = float(
                core_contrasts.loc[
                    core_contrasts["return_state"].eq(return_state)
                    & core_contrasts["horizon"].eq(horizon),
                    "mean_contrast",
                ].iloc[0]
            )
            rows.append(
                {
                    "return_state": return_state,
                    "horizon": horizon,
                    "paired_ai_periods": len(pivot),
                    "ai_mean_G": ai_g,
                    "broader_a_mean_G": broader_g,
                    "same_direction": bool(
                        np.isfinite(ai_g) and ai_g != 0 and np.sign(ai_g) == np.sign(broader_g)
                    ),
                }
            )
    return pd.DataFrame(rows)


def _write_report(
    path: Path,
    classification: str,
    paths: pd.DataFrame,
    contrasts: pd.DataFrame,
    theme: pd.DataFrame,
    period_cells: pd.DataFrame,
) -> None:
    core_paths = paths.loc[paths["return_state"].isin(["LOW_RETURN", "HIGH_RETURN"])]
    path_table = core_paths[
        [
            "return_state",
            "activity_state",
            "horizon",
            "across_period_mean_aligned",
            "across_period_median_aligned",
            "path_category",
        ]
    ]
    core_contrasts = contrasts.loc[contrasts["contrast_type"].eq("activity_G")]
    mid = contrasts.loc[contrasts["contrast_type"].eq("mid_activity_main_effect")]
    interaction = contrasts.loc[contrasts["contrast_type"].eq("interaction_I")]
    ai = theme.loc[theme["row_type"].eq("theme_state_summary") & theme["theme_scope"].eq("AI")]
    space = theme.loc[
        theme["row_type"].eq("theme_state_summary")
        & theme["theme_scope"].eq("COMMERCIAL_SPACE")
    ]
    ai_summary = ai.groupby(["return_state", "activity_state", "horizon"], as_index=False).agg(
        periods=("period_index", "nunique"),
        mean_future_return=("mean_future_return", "mean"),
        mean_occupancy=("state_occupancy", "mean"),
    )
    space_summary = space.groupby(
        ["return_state", "activity_state", "horizon"], as_index=False
    ).agg(
        periods=("period_index", "nunique"),
        mean_future_return=("mean_future_return", "mean"),
        mean_occupancy=("state_occupancy", "mean"),
    )
    ai_direction = _ai_direction_table(theme, core_contrasts)
    primary = period_cells.loc[period_cells["period_index"].between(1, 56)]
    invalid_cells = int((~primary["cell_valid"]).sum())
    stable_count = int(core_contrasts["stability_flag"].sum())
    report = f"""# Hypothesis 5A — Trading-Activity State and Reversal-Timing Diagnostic

## Conclusion

**{classification}**

This is a historical-seen mechanism diagnostic, not Alpha discovery, OOS evidence, a strategy test, or a causal replication. Primary used 56 locked periods (`period_index=1–56`); period 0 remained a predeclared low-coverage diagnostic. Primary invalid period-cells after the fixed count/coverage rules: **{invalid_cells}**. Stable LOW/HIGH_RETURN activity-horizon contrasts under the preregistered rule: **{stable_count}/6**.

## 1–4. Winner/loser paths and coarse reversal horizons

`C_h` is continuation-aligned: raw future return for HIGH_RETURN and its negative for LOW_RETURN. All outcomes are nested cumulative returns from rebalance close. A first observed negative cumulative C identifies only a coarse horizon, not an exact reversal date.

{_markdown_table(path_table, list(path_table.columns))}

## 5. Activity interaction within return states

`G` is HIGH_ACTIVITY minus LOW_ACTIVITY continuation-aligned return within the same past-return state. MID_ACTIVITY is used to test ordering.

{_markdown_table(core_contrasts, ['return_state', 'horizon', 'valid_periods', 'mean_contrast', 'direction_consistency', 'bootstrap_lower_90', 'bootstrap_upper_90', 'loo_sign_consistency', 'activity_ordered', 'stability_flag'])}

MID_RETURN is a raw-return activity main-effect diagnostic and cannot independently support H5A:

{_markdown_table(mid, ['horizon', 'valid_periods', 'mean_contrast', 'direction_consistency', 'bootstrap_lower_90', 'bootstrap_upper_90', 'stability_flag'])}

The non-acceptance interaction contrast `I_h = G_HIGH_RETURN,h - G_LOW_RETURN,h` is:

{_markdown_table(interaction, ['horizon', 'valid_periods', 'mean_contrast', 'median_contrast', 'direction_consistency'])}

## 6–7. Concentration and stability

Every period receives equal cross-period weight. Stability uses a calendar-derived six-period circular moving-block bootstrap (10,000 repetitions, seed 20260721), at least 45/56 valid contrasts, direction consistency at least 60%, and leave-one-period-out sign consistency at least 80%. The 90% interval is descriptive uncertainty evidence only; it is not family-wise-error-controlled, Alpha, or OOS significance. Fixed early/late samples are periods 1–28 and 29–56.

## 8. Literature relationship

The design is literature-inspired: it asks whether trading-activity states distinguish continuation and reversal paths within past winner and loser states. It is not a replication because AMOUNT_MEAN20 percentile is not true turnover, the universe is a current-universe historical backfill, and the analysis is descriptive rather than causal. Similar path shapes would therefore be conceptual consistency only; different shapes would not falsify the original literature.

## 9. AI descriptive transfer

AI stocks inherit their broader-A RETURN_STATE and ACTIVITY_STATE; no theme-local quantiles or independent classification are used.

Direction visibility is descriptive and requires both inherited LOW_ACTIVITY and HIGH_ACTIVITY cells in the same AI period:

{_markdown_table(ai_direction, ['return_state', 'horizon', 'paired_ai_periods', 'ai_mean_G', 'broader_a_mean_G', 'same_direction'])}

{_markdown_table(ai_summary, ['return_state', 'activity_state', 'horizon', 'periods', 'mean_future_return', 'mean_occupancy'])}

## 10. Commercial-space case study

Commercial-space stocks also inherit broader-A states. The following occupancy/path aggregates are low-power descriptions; stock-level rows are retained in `h5a_theme_transfer.csv`.

{_markdown_table(space_summary, ['return_state', 'activity_state', 'horizon', 'periods', 'mean_future_return', 'mean_occupancy'])}

## 11–12. Classification and H5B gate

Final classification: **{classification}**. Theme evidence cannot change it. H5A does not automatically open H5B. Any H5B work requires a separate human review and preregistration; no strategy, MCTS, Phase B, prospective, or final-test process was run.

## Limitations

- `universe_point_in_time=false`; survivorship bias is possible.
- AMOUNT_MEAN20 mixes trading activity, company scale, and price-level exposure.
- The sample is historical_seen and has been viewed by earlier project research.
- Missing or suspended endpoint prices are not filled; outcome missingness never changes signal-time state membership.
- Nested 20D/60D/120D returns identify only coarse first-observed reversal horizons.

## Research identity

{'; '.join(f'{key}={str(value).lower() if isinstance(value, bool) else value}' for key, value in IDENTITY.items())}
"""
    path.write_text(report, encoding="utf-8")


def run(root: Path) -> str:
    root = root.resolve()
    output = root / OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    features, calendar, availability, resolution = _load_inputs(root)
    states = _assign_states(features)
    dates = _period_dates(calendar, availability)
    date_columns = ["return_start_date", *[f"endpoint_{h}d_date" for h in HORIZONS]]
    needed_dates = set(pd.to_datetime(dates[date_columns].stack()).tolist())
    prices = _load_needed_prices(root, resolution, set(states["stock_code"]), needed_dates)
    outcomes = _build_stock_outcomes(states, dates, prices)
    period_cells = _period_cells(states, outcomes)
    paths, categories = _state_paths(period_cells)
    contrasts, _ = _contrast_summary(period_cells)
    classification = classify_result(contrasts, categories)
    theme = _theme_transfer(root, outcomes)

    period_cells.to_csv(output / "h5a_period_state_returns.csv", index=False, encoding="utf-8-sig")
    paths.to_csv(output / "h5a_state_path_summary.csv", index=False, encoding="utf-8-sig")
    contrasts.to_csv(output / "h5a_stability_summary.csv", index=False, encoding="utf-8-sig")
    theme.to_csv(output / "h5a_theme_transfer.csv", index=False, encoding="utf-8-sig")
    _write_report(
        output / "h5a_diagnostic_report.md",
        classification,
        paths,
        contrasts,
        theme,
        period_cells,
    )
    return classification


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    classification = run(args.project_root)
    print(f"H5A_COMPLETE classification={classification}")


if __name__ == "__main__":
    main()
