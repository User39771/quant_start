from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd


def frozen_period_keys(periods: pd.DataFrame) -> list[tuple[pd.Timestamp, pd.Timestamp, int]]:
    frame = periods.copy()
    frame["transaction_cost"] = pd.to_numeric(frame["transaction_cost"], errors="raise")
    mask = (
        frame["universe_name"].eq("research_universe_v1_2")
        & np.isclose(frame["transaction_cost"], 0.0)
        & frame["period_type"].eq("full")
        & frame["headline_included"].astype(str).str.lower().eq("true")
    )
    frame = frame.loc[mask, ["rebalance_date", "next_rebalance_date", "period_trading_days"]].drop_duplicates()
    frame["rebalance_date"] = pd.to_datetime(frame["rebalance_date"], errors="raise")
    frame["next_rebalance_date"] = pd.to_datetime(frame["next_rebalance_date"], errors="raise")
    frame = frame.sort_values(["rebalance_date", "next_rebalance_date"])
    if frame.empty or frame.duplicated(["rebalance_date", "next_rebalance_date"]).any():
        raise ValueError("Frozen full-period grid is empty or duplicated")
    return [(r.rebalance_date, r.next_rebalance_date, int(r.period_trading_days)) for r in frame.itertuples()]


def comparison_flags(left: pd.DataFrame, right: pd.DataFrame) -> tuple[bool, bool]:
    columns = ["rebalance_date", "next_rebalance_date"]
    def keys(frame: pd.DataFrame) -> list[tuple[str, str]]:
        if frame.duplicated(columns).any():
            return []
        return list(map(tuple, frame[columns].astype(str).to_numpy()))
    equal = keys(left) == keys(right) and bool(keys(left))
    return equal, equal


def _run(command: list[str], cwd: Path, allowed: tuple[int, ...] = (0,)) -> int:
    result = subprocess.run(command, cwd=cwd)
    if result.returncode not in allowed:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}")
    return result.returncode


def _copy_versioned(source: Path, root: Path) -> None:
    if source.name.endswith("_v1_2.csv") or source.name.endswith("_v1_2.md"):
        name = source.name.replace("_v1_2", "_locked_grid_v1_5")
    elif source.name.endswith("_v1_4.csv") or source.name.endswith("_v1_4.md"):
        name = source.name.replace("_v1_4", "_locked_grid_v1_5")
    else:
        return
    destination = root / ("data/processed" if source.parent.name == "processed" else "reports") / name
    shutil.copy2(source, destination)
    if destination.suffix == ".md":
        destination.write_text(destination.read_text(encoding="utf-8").replace("v1.2", "locked-grid v1.5").replace("v1.4", "locked-grid v1.5"), encoding="utf-8")


def _summary_metric(path: Path, metric: str) -> object:
    frame = pd.read_csv(path)
    if {"metric", "value"}.issubset(frame.columns):
        row = frame[frame["metric"].eq(metric)]
        return row.iloc[0]["value"] if not row.empty else np.nan
    return np.nan


def build_comparison(root: Path) -> tuple[bool, bool]:
    reports = root / "reports"
    frozen = pd.read_csv(reports / "adjusted_stock_pool_baseline_periods_v1_2.csv", dtype=str)
    frozen_keys = pd.DataFrame([(a, b) for a, b, _ in frozen_period_keys(frozen)], columns=["rebalance_date", "next_rebalance_date"])
    replay = pd.read_csv(reports / "adjusted_stock_pool_baseline_periods_locked_grid_v1_5.csv", dtype=str)
    replay = replay[
        replay["universe_name"].eq("research_universe_v1_2")
        & np.isclose(pd.to_numeric(replay["transaction_cost"]), 0.0)
        & replay["period_type"].eq("full")
    ][["rebalance_date", "next_rebalance_date"]].drop_duplicates().sort_values("rebalance_date")
    frozen_keys = frozen_keys.astype(str).sort_values("rebalance_date")
    comparison_valid, grid_equal = comparison_flags(frozen_keys, replay)

    old_factor = reports / "factor_hypothesis_summary_lowvol20_v1_4.csv"
    new_factor = reports / "factor_hypothesis_summary_lowvol20_locked_grid_v1_5.csv"
    rows = []
    old_prices = pd.read_csv(root / "data/processed/adjusted_price_panel_v1_2.csv", dtype={"stock_code": str})
    new_prices = pd.read_csv(root / "data/processed/adjusted_price_panel_v1_5.csv", dtype={"stock_code": str})
    endpoint_dates = set(frozen_keys["rebalance_date"]) | set(frozen_keys["next_rebalance_date"])
    for frame in (old_prices, new_prices):
        frame["stock_code"] = frame["stock_code"].str.zfill(6)
        frame["trade_date"] = pd.to_datetime(frame["trade_date"]).dt.strftime("%Y-%m-%d")
    price_compare = old_prices[old_prices["trade_date"].isin(endpoint_dates)][["stock_code", "trade_date", "adjusted_close"]].merge(
        new_prices[new_prices["trade_date"].isin(endpoint_dates)][["stock_code", "trade_date", "adjusted_close"]],
        on=["stock_code", "trade_date"], suffixes=("_old", "_new"), how="outer", indicator=True,
    )
    common = price_compare[price_compare["_merge"].eq("both")].copy()
    common["absolute_difference"] = (pd.to_numeric(common["adjusted_close_old"]) - pd.to_numeric(common["adjusted_close_new"])).abs()
    for metric, value in {
        "common_endpoint_price_rows": len(common),
        "old_only_endpoint_price_rows": int((price_compare["_merge"] == "left_only").sum()),
        "new_only_endpoint_price_rows": int((price_compare["_merge"] == "right_only").sum()),
        "changed_common_endpoint_rows_gt_1e_8": int((common["absolute_difference"] > 1e-8).sum()),
        "maximum_endpoint_absolute_difference": common["absolute_difference"].max(),
    }.items():
        rows.append({"section": "input_prices", "metric": metric, "v1_4": np.nan, "locked_grid_v1_5": value, "comparison_valid": comparison_valid, "period_grid_equal": grid_equal})
    for metric in (
        "historical_validation_mean_rank_ic", "historical_validation_mean_q5_q1",
        "verdict",
    ):
        rows.append({
            "section": "LOWVOL20", "metric": metric,
            "v1_4": _summary_metric(old_factor, metric),
            "locked_grid_v1_5": _summary_metric(new_factor, metric),
            "comparison_valid": comparison_valid, "period_grid_equal": grid_equal,
        })
    for version, suffix in (("v1_4", "v1_4"), ("locked_grid_v1_5", "locked_grid_v1_5")):
        quantile_returns = pd.read_csv(reports / f"factor_quantile_returns_lowvol20_{suffix}.csv")
        primary = quantile_returns[(quantile_returns["factor_name"] == "LOWVOL20") & (quantile_returns["sample_basis"] == "lowvol20_primary_reliable_sample")]
        validation = primary[pd.to_datetime(primary["rebalance_date"]) >= pd.Timestamp("2024-01-01")]
        pivot = validation.pivot(index="period_index", columns="portfolio", values="period_return")
        q5_universe = float((pivot["Q5"] - pivot["UNIVERSE"]).mean())
        quantile_summary = pd.read_csv(reports / f"factor_quantile_summary_lowvol20_{suffix}.csv")
        summary = quantile_summary[(quantile_summary["factor_name"] == "LOWVOL20") & (quantile_summary["sample_basis"] == "lowvol20_primary_reliable_sample")].set_index("portfolio")
        values = {
            "historical_validation_mean_q5_universe": q5_universe,
            "q1_annualized_volatility": summary.loc["Q1", "annualized_volatility"],
            "q5_annualized_volatility": summary.loc["Q5", "annualized_volatility"],
            "q1_endpoint_drawdown": summary.loc["Q1", "period_endpoint_maximum_drawdown"],
            "q5_endpoint_drawdown": summary.loc["Q5", "period_endpoint_maximum_drawdown"],
        }
        for metric, value in values.items():
            existing = next((row for row in rows if row["section"] == "LOWVOL20" and row["metric"] == metric), None)
            if existing is None:
                existing = {"section": "LOWVOL20", "metric": metric, "v1_4": np.nan, "locked_grid_v1_5": np.nan, "comparison_valid": comparison_valid, "period_grid_equal": grid_equal}
                rows.append(existing)
            existing[version] = value
    old_base = pd.read_csv(reports / "adjusted_stock_pool_baseline_summary_v1_2.csv", dtype=str)
    new_base = pd.read_csv(reports / "adjusted_stock_pool_baseline_summary_locked_grid_v1_5.csv", dtype=str)
    for frame in (old_base, new_base):
        frame["benchmark_code"] = frame["benchmark_code"].str.zfill(6)
    filt = lambda f: f[(f["universe_name"] == "research_universe_v1_2") & np.isclose(pd.to_numeric(f["transaction_cost"]), 0) & (f["benchmark_code"] == "000300")].iloc[0]
    old_row, new_row = filt(old_base), filt(new_base)
    for metric in ("cumulative_return", "annualized_return", "annualized_volatility", "period_endpoint_maximum_drawdown"):
        rows.append({"section": "baseline", "metric": metric, "v1_4": old_row[metric], "locked_grid_v1_5": new_row[metric], "comparison_valid": comparison_valid, "period_grid_equal": grid_equal})
    old_attr = pd.read_csv(reports / "baseline_attribution_summary_v1_2.csv", dtype=str)
    new_attr = pd.read_csv(reports / "baseline_attribution_summary_locked_grid_v1_5.csv", dtype=str)
    for metric in ("stock_positive_contribution_hhi", "stock_absolute_contribution_hhi", "theme_positive_contribution_hhi", "period_positive_contribution_hhi"):
        def attr_value(frame: pd.DataFrame) -> object:
            selected = frame[(frame["metric"] == metric) & np.isclose(pd.to_numeric(frame["transaction_cost"]), 0.0)]
            return selected.iloc[0]["value"] if not selected.empty else np.nan
        rows.append({"section": "attribution", "metric": metric, "v1_4": attr_value(old_attr), "locked_grid_v1_5": attr_value(new_attr), "comparison_valid": comparison_valid, "period_grid_equal": grid_equal})
    pd.DataFrame(rows).to_csv(reports / "locked_grid_v1_4_vs_v1_5_comparison.csv", index=False)
    (reports / "locked_grid_v1_4_vs_v1_5_comparison.md").write_text(
        f"# Locked-grid v1.4 vs v1.5 Comparison\n\n- comparison_valid: {str(comparison_valid).lower()}\n- period_grid_equal: {str(grid_equal).lower()}\n- full_period_count: {len(frozen_keys)}\n- expanded-history comparison_valid: false\n- expanded-history reason: period grids differ and are not directly comparable\n\nOnly identical frozen endpoints are compared. formal_performance_conclusion_allowed=false.\n",
        encoding="utf-8",
    )
    expanded = reports / "v1_4_vs_v1_5_revised_history_comparison.csv"
    if expanded.exists():
        frame = pd.read_csv(expanded)
        frame["comparison_valid"] = False
        frame["period_grid_equal"] = False
        frame["comparison_note"] = "expanded_history_grid_differs_not_directly_comparable"
        frame.to_csv(expanded, index=False)
    return comparison_valid, grid_equal


def run(root: Path) -> int:
    root = Path(root).resolve()
    frozen_periods = pd.read_csv(root / "reports/adjusted_stock_pool_baseline_periods_v1_2.csv", dtype=str)
    keys = frozen_period_keys(frozen_periods)
    if len(keys) != 57:
        raise ValueError(f"Expected 57 frozen full periods, got {len(keys)}")
    with tempfile.TemporaryDirectory(prefix="locked_grid_v1_5_") as directory:
        stage = Path(directory)
        (stage / "scripts").mkdir(parents=True)
        (stage / "data/processed").mkdir(parents=True)
        (stage / "reports").mkdir()
        (stage / "scripts/__init__.py").write_text("", encoding="ascii")
        for name in ("run_adjusted_stock_pool_baseline_v1_2.py", "analyze_baseline_attribution_v1_2.py", "test_lowvol20_hypothesis_v1_4.py"):
            shutil.copy2(root / "scripts" / name, stage / "scripts" / name)
        shutil.copy2(root / "data/processed/adjusted_price_panel_v1_5.csv", stage / "data/processed/adjusted_price_panel_v1_2.csv")
        shutil.copy2(root / "data/processed/hybrid_benchmark_panel_v1_5.csv", stage / "data/processed/hybrid_benchmark_panel_v1_2.csv")
        shutil.copy2(root / "data/processed/research_universe_lowvol_freeze_20260711.csv", stage / "data/processed/backtest_universe_research_v1_2.csv")
        expanded = root / "data/processed/backtest_universe_expanded_only_v1_2.csv"
        if expanded.exists():
            shutil.copy2(expanded, stage / "data/processed" / expanded.name)
        pd.DataFrame(keys, columns=["rebalance_date", "next_rebalance_date", "period_trading_days"]).to_csv(stage / "frozen_grid.csv", index=False)
        helper = stage / "run_locked.py"
        helper.write_text(
            "import pandas as pd\nimport scripts.run_adjusted_stock_pool_baseline_v1_2 as m\n"
            "g=pd.read_csv('frozen_grid.csv')\n"
            "b=[m.Boundary(pd.Timestamp(r.rebalance_date),pd.Timestamp(r.next_rebalance_date),int(r.period_trading_days),'full') for r in g.itertuples()]\n"
            "m.rebalance_boundaries=lambda _calendar:b\nraise SystemExit(m.main())\n",
            encoding="utf-8",
        )
        _run([sys.executable, "run_locked.py"], stage)
        _run([sys.executable, "scripts/analyze_baseline_attribution_v1_2.py"], stage)
        lowvol_code = _run([sys.executable, "scripts/test_lowvol20_hypothesis_v1_4.py", "--project-root", str(stage)], stage, (0, 1))
        for source in list((stage / "reports").iterdir()) + list((stage / "data/processed").glob("lowvol20_factor_panel_v1_4.csv")):
            _copy_versioned(source, root)
    comparison_valid, grid_equal = build_comparison(root)
    status = "allowed" if lowvol_code == 0 and comparison_valid and grid_equal else "blocked"
    (root / "reports/locked_grid_stage_gate_v1_5.md").write_text(
        f"# Locked-grid Stage Gate v1.5\n\n- locked_grid_lowvol_status: {'completed' if lowvol_code == 0 else 'research_not_ready'}\n- period_grid_equal: {str(grid_equal).lower()}\n- comparison_valid: {str(comparison_valid).lower()}\n- q5_long_only_prototype: {status}\n- expanded_history: exploratory_and_blocked\n- expanded_history_blocker: suspension-aware portfolio accounting is not specified\n- parameters_changed: false\n",
        encoding="utf-8",
    )
    return 0 if comparison_valid and grid_equal else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args(argv)
    return run(args.project_root)


if __name__ == "__main__":
    raise SystemExit(main())
