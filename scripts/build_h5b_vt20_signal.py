"""Publish the fixed H5B VT20 signal panel without reading outcome data."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from scripts.audit_turnover_like_proxy_feasibility import (
        _windows,
        validate_primary_periods,
        value_turnover,
    )
    from scripts.run_h5a_trading_activity_reversal_timing_v1 import (
        _assign_states,
        code6,
        ordinal_groups,
    )
else:
    from audit_turnover_like_proxy_feasibility import (
        _windows,
        validate_primary_periods,
        value_turnover,
    )
    from run_h5a_trading_activity_reversal_timing_v1 import (
        _assign_states,
        code6,
        ordinal_groups,
    )

OUTPUT_DIR = Path("reports/hypothesis_5b")
VT_STATES = ("LOW_VT", "MID_VT", "HIGH_VT")
RETURN_STATES = ("LOW_RETURN", "MID_RETURN", "HIGH_RETURN")
FORBIDDEN_COLUMN_PARTS = (
    "future",
    "forward",
    "endpoint",
    "20d_return",
    "60d_return",
    "120d_return",
)


def assert_signal_time_columns(columns: list[str] | pd.Index) -> None:
    bad = [
        column
        for column in columns
        if any(part in column.lower() for part in FORBIDDEN_COLUMN_PARTS)
    ]
    if bad:
        raise ValueError(f"outcome_columns_forbidden={bad}")


def assign_vt20_states(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["VT20_PERCENTILE"] = np.nan
    result["VT20_STATE"] = pd.NA
    eligible = result["signal_ready"] & result["vt20_valid"]
    for _, group in result.loc[eligible].groupby("period_index", sort=True):
        result.loc[group.index, "VT20_PERCENTILE"] = group["VT20_DAILY"].rank(
            method="average", pct=True
        )
        result.loc[group.index, "VT20_STATE"] = ordinal_groups(
            group, "VT20_DAILY", VT_STATES
        )
    return result


def validate_reused_return_states(formal: pd.DataFrame, audited: pd.DataFrame) -> None:
    keys = ["period_index", "stock_code"]
    left = formal[keys + ["return_state"]].sort_values(keys).reset_index(drop=True)
    right = audited[keys + ["return_state"]].sort_values(keys).reset_index(drop=True)
    if not left[keys].equals(right[keys]) or not left["return_state"].equals(right["return_state"]):
        raise ValueError("h5a_membership_or_return_state_mismatch")


def _load_formal_h5a_states(root: Path) -> pd.DataFrame:
    features = pd.read_csv(
        root / "data/processed/h5a_broader_a_signal_features_v1.csv",
        dtype={"stock_code": str},
    )
    assert_signal_time_columns(features.columns)
    features["stock_code"] = features["stock_code"].map(code6)
    features["signal_as_of_date"] = pd.to_datetime(features["signal_as_of_date"], errors="raise")
    for column in ("signal_ready", "return60_valid", "amount20_valid"):
        features[column] = features[column].astype(str).str.lower().eq("true")
    states = _assign_states(features)
    states = states.loc[states["period_index"].between(1, 56)].copy()
    validate_primary_periods(states["period_index"])
    if states.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("duplicate_h5a_signal_key")
    return states


def _load_audited_vt20(root: Path) -> pd.DataFrame:
    path = root / "reports/hypothesis_5a/turnover_like_proxy_signal_values.csv"
    columns = [
        "period_index",
        "signal_as_of_date",
        "stock_code",
        "return_state",
        "vt20_daily",
        "vt20_valid",
        "vol20",
        "log_total_market_cap",
        "log_raw_signal_price",
    ]
    audited = pd.read_csv(path, usecols=columns, dtype={"stock_code": str})
    assert_signal_time_columns(audited.columns)
    audited["stock_code"] = audited["stock_code"].map(code6)
    audited["signal_as_of_date"] = pd.to_datetime(audited["signal_as_of_date"], errors="raise")
    audited["vt20_valid"] = audited["vt20_valid"].astype(str).str.lower().eq("true")
    if audited.duplicated(["period_index", "stock_code"]).any():
        raise ValueError("duplicate_audited_vt20_key")
    validate_primary_periods(audited["period_index"])
    return audited


def _fill_input_day_counts(root: Path, panel: pd.DataFrame) -> pd.Series:
    counts = pd.Series(np.where(panel["vt20_valid"], 20, np.nan), index=panel.index)
    invalid = panel.loc[~panel["vt20_valid"]]
    if invalid.empty:
        return counts.astype("Int64")
    windows = _windows(root, panel)
    resolution = pd.read_csv(
        root / "reports/hypothesis_5a_broader_a/source_resolution_report.csv",
        dtype={"stock_code": str},
    )
    resolution["stock_code"] = resolution["stock_code"].map(code6)
    paths = resolution.set_index("stock_code")["canonical_amount_path"].dropna().to_dict()
    for code, group in invalid.groupby("stock_code"):
        raw = pd.read_csv(
            root / str(paths[code]),
            usecols=["date", "amount", "total_market_cap"],
        )
        raw["date"] = pd.to_datetime(raw["date"], errors="raise")
        raw = raw.set_index("date")
        for row in group.itertuples():
            selected = raw.reindex(windows[int(row.period_index)])
            counts.loc[row.Index] = int(
                value_turnover(selected["amount"], selected["total_market_cap"]).notna().sum()
            )
    return counts.astype("Int64")


def build_signal_panel(root: Path) -> pd.DataFrame:
    formal = _load_formal_h5a_states(root)
    audited = _load_audited_vt20(root)
    validate_reused_return_states(formal, audited)
    keys = ["period_index", "signal_as_of_date", "stock_code"]
    panel = formal[keys + ["return_60", "return_state", "signal_ready"]].merge(
        audited.drop(columns="return_state"), on=keys, how="left", validate="one_to_one"
    )
    if panel["vt20_valid"].isna().any():
        raise ValueError("missing_audited_vt20_members")
    panel = panel.rename(
        columns={
            "return_60": "RETURN60",
            "return_state": "RETURN_STATE",
            "vt20_daily": "VT20_DAILY",
            "vol20": "VOL20",
        }
    )
    panel["input_days_count"] = _fill_input_day_counts(root, panel)
    panel = assign_vt20_states(panel)
    if not panel.loc[panel["vt20_valid"], "input_days_count"].eq(20).all():
        raise ValueError("valid_vt20_without_20_inputs")
    if panel.loc[panel["vt20_valid"], "VT20_STATE"].isna().any():
        raise ValueError("valid_vt20_without_state")
    columns = [
        "period_index",
        "signal_as_of_date",
        "stock_code",
        "RETURN60",
        "RETURN_STATE",
        "VT20_DAILY",
        "VT20_PERCENTILE",
        "VT20_STATE",
        "VOL20",
        "log_total_market_cap",
        "log_raw_signal_price",
        "vt20_valid",
        "input_days_count",
    ]
    assert_signal_time_columns(columns)
    return panel[columns].sort_values(["period_index", "stock_code"]).reset_index(drop=True)


def _period_spearman(panel: pd.DataFrame, scope: str, column: str) -> pd.Series:
    sample = panel.loc[panel["vt20_valid"]]
    if scope != "ALL":
        sample = sample.loc[sample["RETURN_STATE"].eq(scope)]
    return sample.groupby("period_index").apply(
        lambda group: group["VT20_DAILY"].corr(group[column], method="spearman"),
        include_groups=False,
    )


def build_summary(panel: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict] = []
    coverage = panel.groupby("period_index").agg(
        members=("stock_code", "size"), valid=("vt20_valid", "sum")
    )
    for period, row in coverage.iterrows():
        rows.append(
            {
                "summary_type": "period_coverage",
                "scope": "ALL",
                "period_index": period,
                "metric": "vt20_coverage",
                "n": int(row["members"]),
                "value": row["valid"] / row["members"],
                "minimum": int(row["valid"]),
                "maximum": int(row["members"]),
            }
        )
    cells = (
        panel.loc[panel["vt20_valid"]]
        .groupby(["period_index", "RETURN_STATE", "VT20_STATE"])
        .size()
        .reindex(
            pd.MultiIndex.from_product(
                [range(1, 57), RETURN_STATES, VT_STATES],
                names=["period_index", "RETURN_STATE", "VT20_STATE"],
            ),
            fill_value=0,
        )
        .rename("cell_size")
        .reset_index()
    )
    for (return_state, vt_state), group in cells.groupby(["RETURN_STATE", "VT20_STATE"]):
        values = group["cell_size"]
        rows.append(
            {
                "summary_type": "cell_size_distribution",
                "scope": return_state,
                "period_index": "ALL",
                "VT20_STATE": vt_state,
                "metric": "cell_size",
                "n": len(values),
                "mean": values.mean(),
                "median": values.median(),
                "p10": values.quantile(0.10),
                "p90": values.quantile(0.90),
                "minimum": values.min(),
                "maximum": values.max(),
            }
        )
    rows.append(
        {
            "summary_type": "overall_3x3_cell_size",
            "scope": "ALL",
            "period_index": "ALL",
            "metric": "cell_size",
            "n": len(cells),
            "mean": cells["cell_size"].mean(),
            "median": cells["cell_size"].median(),
            "p10": cells["cell_size"].quantile(0.10),
            "p90": cells["cell_size"].quantile(0.90),
            "minimum": cells["cell_size"].min(),
            "maximum": cells["cell_size"].max(),
        }
    )
    correlations = {
        "log_total_market_cap": ("ALL", *RETURN_STATES),
        "VOL20": ("ALL", *RETURN_STATES),
        "log_raw_signal_price": ("ALL",),
        "RETURN60": ("ALL",),
    }
    for column, scopes in correlations.items():
        for scope in scopes:
            values = _period_spearman(panel, scope, column).dropna()
            rows.append(
                {
                    "summary_type": "period_spearman_summary",
                    "scope": scope,
                    "period_index": "ALL",
                    "metric": column,
                    "n": len(values),
                    "mean": values.mean(),
                    "median": values.median(),
                    "p10": values.quantile(0.10),
                    "p90": values.quantile(0.90),
                    "minimum": values.min(),
                    "maximum": values.max(),
                }
            )
    return pd.DataFrame(rows)


def run(root: Path) -> None:
    root = root.resolve()
    output = root / OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    panel = build_signal_panel(root)
    summary = build_summary(panel)
    panel.to_csv(output / "h5b_vt20_signal_panel.csv", index=False, encoding="utf-8")
    summary.to_csv(output / "h5b_vt20_signal_summary.csv", index=False, encoding="utf-8")
    print("H5B_VT20_SIGNAL_CONSTRUCTION_COMPLETE")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path("."))
    args = parser.parse_args()
    run(args.project_root)


if __name__ == "__main__":
    main()
