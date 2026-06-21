from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .portfolio_experiments import (
    PortfolioExperimentConfig,
    default_portfolio_experiments,
    run_portfolio_experiments,
)
from .utils import parse_cache_date


@dataclass(frozen=True)
class WalkForwardSplit:
    name: str
    train_start: str
    train_end: str
    test_start: str
    test_end: str


def default_walk_forward_splits(panel: pd.DataFrame) -> list[WalkForwardSplit]:
    dates = sorted(parse_cache_date(panel["date"]).dropna().dt.to_period("M").unique()) if "date" in panel else []
    if len(dates) < 48:
        return []
    first = dates[0].to_timestamp("M").date().isoformat()
    last = dates[-1].to_timestamp("M").date().isoformat()
    split_a_train_end = dates[min(35, len(dates) - 13)].to_timestamp("M").date().isoformat()
    split_a_test_end = dates[min(47, len(dates) - 1)].to_timestamp("M").date().isoformat()
    split_b_train_start = dates[min(12, len(dates) - 36)].to_timestamp("M").date().isoformat()
    split_b_train_end = dates[min(47, len(dates) - 13)].to_timestamp("M").date().isoformat()
    return [
        WalkForwardSplit("wf_1", first, split_a_train_end, split_a_train_end, split_a_test_end),
        WalkForwardSplit("wf_2", split_b_train_start, split_b_train_end, split_b_train_end, last),
    ]


def run_walk_forward_validation(
    panel: pd.DataFrame,
    experiments: list[PortfolioExperimentConfig] | None = None,
    *,
    splits: list[WalkForwardSplit] | None = None,
    selection_metric: str = "annualized_excess_return",
    transaction_cost_rate: float = 0.002,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    configs = experiments if experiments is not None else default_portfolio_experiments()
    wf_splits = splits if splits is not None else default_walk_forward_splits(panel)
    metric_rows: list[dict[str, object]] = []
    nav_rows: list[pd.DataFrame] = []
    for split in wf_splits:
        train_panel = _slice_panel(panel, split.train_start, split.train_end)
        train_metrics, _train_nav = run_portfolio_experiments(
            train_panel,
            configs,
            transaction_cost_rate=transaction_cost_rate,
        )
        selected_name = _select_experiment(train_metrics, selection_metric)
        selected_config = next(config for config in configs if config.name == selected_name)
        test_panel = _slice_panel(panel, split.test_start, split.test_end)
        test_metrics, test_nav = run_portfolio_experiments(
            test_panel,
            [selected_config],
            transaction_cost_rate=transaction_cost_rate,
        )
        test_row = test_metrics.iloc[0].to_dict() if not test_metrics.empty else {}
        train_row = train_metrics[train_metrics["experiment"] == selected_name]
        train_value = train_row[selection_metric].iloc[0] if not train_row.empty and selection_metric in train_row else np.nan
        metric_rows.append(
            {
                "split": split.name,
                "train_start": split.train_start,
                "train_end": split.train_end,
                "test_start": split.test_start,
                "test_end": split.test_end,
                "selection_metric": selection_metric,
                "selected_experiment": selected_name,
                "train_selected_metric": train_value,
                "test_annualized_return": test_row.get("annualized_return"),
                "test_annualized_excess_return": test_row.get("annualized_excess_return"),
                "test_information_ratio": test_row.get("information_ratio"),
                "test_annualized_turnover": test_row.get("annualized_turnover"),
                "test_average_holding_count": test_row.get("average_holding_count"),
            }
        )
        if not test_nav.empty:
            nav = test_nav.copy()
            nav.insert(0, "split", split.name)
            nav_rows.append(nav)
    nav_frame = pd.concat(nav_rows, ignore_index=True) if nav_rows else pd.DataFrame()
    return pd.DataFrame(metric_rows), nav_frame


def save_walk_forward_outputs(metrics: pd.DataFrame, nav: pd.DataFrame, output_dir: Path, report_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_dir.mkdir(parents=True, exist_ok=True)
    metrics.to_csv(output_dir / "walk_forward_metrics.csv", index=False, encoding="utf-8-sig")
    nav.to_csv(output_dir / "walk_forward_nav.csv", index=False, encoding="utf-8-sig")
    report_path = report_dir / "walk_forward_report.md"
    report_path.write_text(render_walk_forward_report(metrics, nav), encoding="utf-8")
    return report_path


def render_walk_forward_report(metrics: pd.DataFrame, nav: pd.DataFrame) -> str:
    lines = [
        "# Walk-Forward Validation Report",
        "",
        "- validation_type=rolling_train_select_test_evaluate",
        "- parameter_source=existing_portfolio_experiments_only",
        "- in_sample_best_is_not_strategy_proof=true",
        "",
        "## Split Results",
        "",
    ]
    lines += _table(metrics) if not metrics.empty else ["No walk-forward splits were generated."]
    lines += ["", "## Overall", ""]
    if metrics.empty:
        lines.append("- out_of_sample_overall_annualized_excess_return=NaN")
    else:
        excess = pd.to_numeric(metrics["test_annualized_excess_return"], errors="coerce")
        ir = pd.to_numeric(metrics["test_information_ratio"], errors="coerce")
        turnover = pd.to_numeric(metrics["test_annualized_turnover"], errors="coerce")
        selected = metrics["selected_experiment"].dropna().astype(str)
        lines += [
            f"- out_of_sample_overall_annualized_excess_return={_fmt(excess.mean())}",
            f"- out_of_sample_average_information_ratio={_fmt(ir.mean())}",
            f"- out_of_sample_average_turnover={_fmt(turnover.mean())}",
            f"- parameter_stability={'stable' if selected.nunique() <= 1 else 'unstable'}",
            f"- out_of_sample_negative_excess={'yes' if excess.mean() < 0 else 'no'}",
        ]
    lines += [
        "",
        "## Caveats",
        "",
        "- Do not treat the full-sample best portfolio setting as evidence of a valid strategy.",
        "- Walk-forward splits still inherit current universe survivorship risk.",
        "- total_market_cap return proxy is not strict adjusted-price return.",
        "- Same-day zero amount, zero volume, one-price locked, and halt/status sell blocks are forced holds; explicit limit-down exit prices remain incomplete.",
    ]
    return "\n".join(lines)


def _slice_panel(panel: pd.DataFrame, start: str, end: str) -> pd.DataFrame:
    if panel.empty or "date" not in panel:
        return panel.head(0).copy()
    frame = panel.copy()
    dates = parse_cache_date(frame["date"])
    mask = dates.ge(pd.Timestamp(start)) & dates.le(pd.Timestamp(end))
    return frame.loc[mask].copy()


def _select_experiment(metrics: pd.DataFrame, selection_metric: str) -> str:
    if metrics.empty or selection_metric not in metrics:
        raise ValueError(f"selection_metric unavailable: {selection_metric}")
    ranked = metrics.copy()
    ranked[selection_metric] = pd.to_numeric(ranked[selection_metric], errors="coerce")
    ranked = ranked.dropna(subset=[selection_metric]).sort_values(selection_metric, ascending=False)
    if ranked.empty:
        raise ValueError(f"selection_metric has no valid values: {selection_metric}")
    return str(ranked.iloc[0]["experiment"])


def _table(frame: pd.DataFrame) -> list[str]:
    display = frame.copy()
    for column in display.columns:
        if pd.api.types.is_float_dtype(display[column]):
            display[column] = display[column].map(lambda value: "" if pd.isna(value) else f"{value:.4f}")
    return display.to_markdown(index=False).splitlines()


def _fmt(value: object) -> str:
    if value is None or pd.isna(value):
        return "NaN"
    return f"{float(value):.10g}"
