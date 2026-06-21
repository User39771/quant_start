from __future__ import annotations

import argparse
import json
import traceback
from datetime import datetime
from pathlib import Path

import pandas as pd

from .backtest_engine import BacktestConfig, MonthlyRebalanceBacktester
from .config import DEFAULT_SLEEP_SECONDS, ResearchConfig, default_dates
from .data import AkShareClient
from .evaluation import evaluate_factor_panel
from .factors import (
    IC_WEIGHT_FACTORS,
    INDUSTRY_METHOD_NOTE,
    build_factor_panel,
    load_industry_sw_cache,
)
from .portfolio_experiments import (
    default_portfolio_experiments,
    run_portfolio_experiments,
    save_portfolio_experiment_outputs,
)
from .report import save_backtest_outputs, save_outputs
from .utils import parse_cache_date, read_cache_csv
from .walk_forward import run_walk_forward_validation, save_walk_forward_outputs


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="A-share cashflow and moneyflow factor reliability research.")
    parser.add_argument("--years", type=int, default=3, help="Lookback years, default: 3.")
    parser.add_argument("--holding-days", type=int, default=20, help="Forward return window in trading days.")
    parser.add_argument("--max-symbols", type=int, default=None, help="Limit universe size for smoke tests.")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated stock codes, bypassing the universe endpoint.")
    parser.add_argument("--no-cache", action="store_true", help="Ignore cached CSV files and fetch again.")
    parser.add_argument(
        "--fetch-missing-price",
        dest="price_cache_only",
        action="store_false",
        default=True,
        help="Allow run_research to request missing price data from AkShare.",
    )
    parser.add_argument(
        "--cache-only",
        action="store_true",
        help="Use local CSV cache only; missing required price data is skipped without network requests.",
    )
    parser.add_argument(
        "--sleep",
        type=float,
        default=DEFAULT_SLEEP_SECONDS,
        help="Sleep seconds between AkShare requests, default: 10.0.",
    )
    parser.add_argument(
        "--run-backtest",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Generate monthly Top-N equal-weight backtest outputs, default: true.",
    )
    parser.add_argument("--backtest-top-n", type=int, default=50, help="Backtest selected stock count, default: 50.")
    parser.add_argument(
        "--transaction-cost-rate",
        type=float,
        default=0.002,
        help="Backtest one-way transaction cost rate, default: 0.002.",
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    start, end = default_dates(args.years)
    config = ResearchConfig(
        root_dir=args.root,
        start_date=start,
        end_date=end,
        holding_days=args.holding_days,
        max_symbols=args.max_symbols,
        sleep_seconds=args.sleep,
        use_cache=not args.no_cache,
        price_cache_only=args.price_cache_only,
        cache_only=args.cache_only,
    )
    print(f"[{datetime.now():%H:%M:%S}] Loading universe...")
    client = AkShareClient(config)
    if args.symbols.strip():
        symbols = [item.strip().zfill(6) for item in args.symbols.split(",") if item.strip()]
        universe = pd.DataFrame(
            {
                "code": symbols,
                "name": symbols,
                "industry": [None] * len(symbols),
                "market_cap": [None] * len(symbols),
                "float_market_cap": [None] * len(symbols),
            }
        )
    else:
        universe = client.universe()
    print(f"Universe size after filters: {len(universe)}")

    stocks = []
    for idx, row in universe.iterrows():
        code = row["code"]
        name = row["name"]
        print(f"[{idx + 1}/{len(universe)}] Fetching {code} {name}")
        failure_count = len(client.failures)
        try:
            stocks.append(client.stock_data(row))
        except Exception as exc:
            if len(client.failures) == failure_count:
                client._record_failure(code, name, "stock", exc)
            print(f"  skipped: {exc}")
        if idx + 1 < len(universe):
            client.sleep_between_symbols()

    industry_cache = load_industry_sw_cache(config.cache_dir, universe["code"].astype(str).tolist())
    industry_warnings_rows: list[dict[str, object]] = []
    panel = build_factor_panel(
        stocks,
        holding_days=config.holding_days,
        min_history_days=config.min_history_days,
        industry_sw=industry_cache,
        industry_warnings_rows=industry_warnings_rows,
        ic_summary_path=config.processed_dir / "ic_summary.csv",
        ic_summary_source_label="data/processed/ic_summary.csv",
    )
    pd.DataFrame(industry_warnings_rows).to_csv(
        config.processed_dir / "industry_join_warnings.csv",
        index=False,
        encoding="utf-8-sig",
    )
    results = evaluate_factor_panel(panel, group_count=config.group_count)
    fetch_summary = client.fetch_summary_frame()
    fetch_summary.to_csv(
        config.processed_dir / "fetch_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    price_row = (
        fetch_summary[fetch_summary["endpoint"] == "price"].iloc[0].to_dict()
        if "price" in set(fetch_summary["endpoint"])
        else {"success": 0, "failed": 0, "cache_fallback": 0, "skipped_required_price": 0}
    )
    price_attempts = int(price_row["success"]) + int(price_row["failed"])
    price_success_rate = int(price_row["success"]) / price_attempts if price_attempts else 0.0
    cache_fallbacks = int(fetch_summary["cache_fallback"].sum()) if not fetch_summary.empty else 0
    data_quality = {
        "universe_size": len(universe),
        "effective_stocks": len(stocks),
        "price_success_rate": price_success_rate,
        "price_usable_rate": len(stocks) / len(universe) if len(universe) else 0.0,
        "cache_fallbacks": cache_fallbacks,
        "fetch_failures": len(client.failures),
        "universe_survivorship_status": "current_universe_price_history_only",
        "financial_available_date_policy": "announce_date_else_report_date_plus_120d",
        "cashflow_statement_basis": "ttm_from_cumulative_quarterly_flows",
        "sell_side_execution_constraints": "same_day_untradable_forced_hold_minimal_model",
    }
    if args.cache_only:
        data_quality.update(db_cache_quality_metadata(config.root_dir))
    data_quality.update(factor_panel_quality_metadata(panel))
    report_path = save_outputs(panel, results, config.processed_dir, config.report_dir, data_quality=data_quality)
    if args.run_backtest:
        backtest_report_path = run_backtest_outputs(
            panel,
            config.processed_dir,
            config.report_dir,
            top_n=args.backtest_top_n,
            transaction_cost_rate=args.transaction_cost_rate,
        )
        print(f"Backtest report written: {backtest_report_path}")
        portfolio_report_path = run_portfolio_experiment_outputs(
            panel,
            config.processed_dir,
            config.report_dir,
            transaction_cost_rate=args.transaction_cost_rate,
        )
        print(f"Portfolio construction report written: {portfolio_report_path}")
        walk_forward_report_path = run_walk_forward_outputs(
            panel,
            config.processed_dir,
            config.report_dir,
            transaction_cost_rate=args.transaction_cost_rate,
        )
        print(f"Walk-forward report written: {walk_forward_report_path}")

    failures = pd.DataFrame(
        client.failures,
        columns=["code", "name", "endpoint", "error_type", "attempts", "cache_fallback", "error"],
    )
    failures.to_csv(
        config.processed_dir / "fetch_failures.csv",
        index=False,
        encoding="utf-8-sig",
    )
    if client.failures:
        print(f"Fetch failures: {len(client.failures)}; see data/processed/fetch_failures.csv")
    failed_symbols = client.failed_symbols_frame()
    failed_symbols.to_csv(
        config.processed_dir / "failed_symbols.csv",
        index=False,
        encoding="utf-8-sig",
    )
    if not failed_symbols.empty:
        print(f"Failed symbols: {len(failed_symbols)}; see data/processed/failed_symbols.csv")
    print(f"Effective stocks: {len(stocks)}/{len(universe)}")
    print(f"Price usable rate: {data_quality['price_usable_rate']:.1%}")
    print(f"Price request success rate: {price_success_rate:.1%}")
    print(f"Cache fallbacks: {cache_fallbacks}; see data/processed/fetch_summary.csv")
    print(f"Factor panel rows: {len(panel)}")
    print(f"Report written: {report_path}")


def run_backtest_outputs(
    panel: pd.DataFrame,
    processed_dir: Path,
    report_dir: Path,
    top_n: int,
    transaction_cost_rate: float,
) -> Path:
    try:
        backtest_config = BacktestConfig(top_n=top_n, transaction_cost_rate=transaction_cost_rate)
        result = MonthlyRebalanceBacktester(backtest_config).run(panel)
        return save_backtest_outputs(result, processed_dir, report_dir, backtest_config)
    except Exception as exc:
        processed_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        warning = pd.DataFrame(
            [
                {
                    "warning_type": "backtest_failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            ]
        )
        warning.to_csv(processed_dir / "backtest_warnings.csv", index=False, encoding="utf-8-sig")
        report_path = report_dir / "backtest_report.md"
        report_path.write_text(
            "\n".join(
                [
                    "# Monthly Rebalanced Backtest Report",
                    "",
                    "- status=failed",
                    f"- error_type={type(exc).__name__}",
                    f"- message={exc}",
                ]
            ),
            encoding="utf-8",
        )
        return report_path


def run_portfolio_experiment_outputs(
    panel: pd.DataFrame,
    processed_dir: Path,
    report_dir: Path,
    transaction_cost_rate: float,
) -> Path:
    try:
        metrics, nav = run_portfolio_experiments(
            panel,
            default_portfolio_experiments(),
            transaction_cost_rate=transaction_cost_rate,
        )
        return save_portfolio_experiment_outputs(metrics, nav, processed_dir, report_dir)
    except Exception as exc:
        processed_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        warning = pd.DataFrame(
            [
                {
                    "warning_type": "portfolio_experiments_failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            ]
        )
        warning.to_csv(processed_dir / "portfolio_experiment_warnings.csv", index=False, encoding="utf-8-sig")
        report_path = report_dir / "portfolio_construction_report.md"
        report_path.write_text(
            "\n".join(
                [
                    "# Portfolio Construction Experiment Report",
                    "",
                    "- status=failed",
                    f"- error_type={type(exc).__name__}",
                    f"- message={exc}",
                ]
            ),
            encoding="utf-8",
        )
        return report_path


def run_walk_forward_outputs(
    panel: pd.DataFrame,
    processed_dir: Path,
    report_dir: Path,
    transaction_cost_rate: float,
) -> Path:
    try:
        metrics, nav = run_walk_forward_validation(panel, transaction_cost_rate=transaction_cost_rate)
        report_path = save_walk_forward_outputs(metrics, nav, processed_dir, report_dir)
        portfolio_metrics_path = processed_dir / "portfolio_experiment_metrics.csv"
        portfolio_nav_path = processed_dir / "portfolio_experiment_nav.csv"
        if portfolio_metrics_path.exists() and portfolio_nav_path.exists():
            portfolio_metrics = read_cache_csv(portfolio_metrics_path)
            portfolio_nav = read_cache_csv(portfolio_nav_path)
            save_portfolio_experiment_outputs(
                portfolio_metrics,
                portfolio_nav,
                processed_dir,
                report_dir,
                walk_forward_metrics=metrics,
            )
        return report_path
    except Exception as exc:
        processed_dir.mkdir(parents=True, exist_ok=True)
        report_dir.mkdir(parents=True, exist_ok=True)
        warning = pd.DataFrame(
            [
                {
                    "warning_type": "walk_forward_failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            ]
        )
        warning.to_csv(processed_dir / "walk_forward_warnings.csv", index=False, encoding="utf-8-sig")
        report_path = report_dir / "walk_forward_report.md"
        report_path.write_text(
            "\n".join(
                [
                    "# Walk-Forward Validation Report",
                    "",
                    "- status=failed",
                    f"- error_type={type(exc).__name__}",
                    f"- message={exc}",
                ]
            ),
            encoding="utf-8",
        )
        return report_path

def db_cache_quality_metadata(root_dir: Path) -> dict[str, object]:
    metadata: dict[str, object] = {"data_source": "db_cache"}
    mapping_path = root_dir / "config" / "db_mapping.json"
    if mapping_path.exists():
        mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
        price = mapping.get("endpoints", {}).get("price", {})
        if price:
            optional_fields = price.get("optional_fields", {})
            if isinstance(optional_fields, dict) and "total_market_cap" in optional_fields:
                metadata["price_adjustment"] = "market_cap_proxy"
                metadata["return_source"] = "total_market_cap"
                metadata["methodology_note"] = (
                    "由于底层数据库缺乏复权因子，本次回测使用总市值变化率近似替代个股收益率，"
                    "成功排除了拆股带来的断崖式噪音，但微幅低估了实际的现金分红回报。"
                )
            else:
                metadata["price_adjustment"] = price.get("adjustment", "unknown")
            metadata["unit_summary"] = {
                key: f"{value.get('unit', 'unknown')} x{value.get('multiplier', 'unknown')}"
                for key, value in price.get("units", {}).items()
                if isinstance(value, dict)
            }
    summary_path = root_dir / "data" / "processed" / "db_sync_summary.csv"
    if summary_path.exists():
        try:
            summary = read_cache_csv(summary_path)
        except pd.errors.EmptyDataError:
            metadata["db_sync_summary_status"] = "empty"
        else:
            if "status" in summary:
                metadata["sync_counts"] = summary["status"].value_counts().to_dict()
                metadata["db_sync_summary_status"] = "loaded"
            else:
                # The sync summary is diagnostic metadata; an incomplete file should not abort research.
                metadata["db_sync_summary_status"] = "missing_status_column"
    metadata.update(sync_manifest_quality_metadata(root_dir))
    metadata.update(industry_neutralization_metadata(root_dir))
    moneyflow_dir = root_dir / "data" / "cache" / "moneyflow"
    if not moneyflow_dir.exists() or not any(moneyflow_dir.glob("*.csv")):
        metadata["moneyflow_status"] = "disabled_or_missing"
    price_ranges, missing_rate = price_cache_coverage(root_dir / "data" / "cache" / "price")
    metadata["price_date_ranges"] = price_ranges
    metadata["price_missing_rate"] = missing_rate
    return metadata


def factor_panel_quality_metadata(panel: pd.DataFrame) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if panel.empty:
        return metadata
    neutral_columns = [
        column
        for column in [
            "cashflow_quality_score_neutral",
            "cf_yield_neutral",
            "reversal_20d_neutral",
            "volatility_20d_neutral",
        ]
        if column in panel
    ]
    if neutral_columns:
        modes = panel["factor_neutralization_mode"].dropna().astype(str) if "factor_neutralization_mode" in panel else pd.Series(dtype=str)
        mode = modes.mode().iloc[0] if not modes.empty else "market_cap"
        if mode == "market_cap_industry":
            metadata["factor_processing"] = "mad_zscore_market_cap_industry_neutralized"
            metadata["factor_processing_ols_x"] = "ln_total_market_cap + sw_l1_code_dummies(drop_one)"
            metadata["factor_processing_min_regression_samples"] = 30
            metadata["industry_neutralization"] = "shenwan_l1"
            metadata["industry_neutralization_status"] = "applied"
            metadata["methodology_note"] = INDUSTRY_METHOD_NOTE
        else:
            metadata["factor_processing"] = "mad_zscore_market_cap_neutralized"
            metadata["factor_processing_ols_x"] = "ln_total_market_cap"
            metadata["factor_processing_min_regression_samples"] = 20
        metadata["factor_processing_mad_multiplier"] = 3.5
        metadata["neutral_factor_coverage"] = {
            column: f"{panel[column].notna().mean():.1%}" for column in neutral_columns
        }
    if "sw_l1_code" in panel:
        metadata["industry_coverage"] = float(panel["sw_l1_code"].notna().mean())
    if "cf_yield_neutral_status" in panel:
        statuses = panel["cf_yield_neutral_status"].dropna().astype(str)
        if not statuses.empty:
            fallback = statuses.str.startswith("fallback")
            metadata["industry_neutralization_fallback_rate"] = float(fallback.mean())
            metadata["industry_neutralization_fallback_reasons"] = statuses[fallback].value_counts().to_dict()
    exposure = factor_exposure_metadata(panel)
    if exposure:
        metadata.update(exposure)
    if "return_source" in panel:
        sources = panel["return_source"].dropna().astype(str)
        if not sources.empty:
            metadata["return_source"] = sources.mode().iloc[0]
    if "market_cap_unit_multiplier" in panel:
        multipliers = pd.to_numeric(panel["market_cap_unit_multiplier"], errors="coerce").dropna()
        if not multipliers.empty:
            metadata["market_cap_unit_multiplier"] = format_numeric_metadata(multipliers.mode().iloc[0])
    if "cf_yield_unit_guard_status" in panel:
        statuses = panel["cf_yield_unit_guard_status"].dropna().astype(str)
        if not statuses.empty:
            metadata["cf_yield_unit_guard_status"] = statuses.mode().iloc[0]
    ic_metadata = ic_weight_metadata(panel)
    if ic_metadata:
        metadata.update(ic_metadata)
    return metadata


def ic_weight_metadata(panel: pd.DataFrame) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if panel.empty or "ic_weight_source" not in panel:
        return metadata
    sources = panel["ic_weight_source"].dropna().astype(str)
    if sources.empty:
        return metadata
    metadata["ic_weight_source"] = sources.mode().iloc[0]
    details: dict[str, object] = {}
    for factor in IC_WEIGHT_FACTORS:
        for label, column in [
            ("rank_ic_mean", f"ic_rank_ic_mean_{factor}"),
            ("direction", f"ic_direction_{factor}"),
            ("weight", f"ic_weight_{factor}"),
        ]:
            if column not in panel:
                continue
            values = pd.to_numeric(panel[column], errors="coerce").dropna()
            if not values.empty:
                details[f"{factor}.{label}"] = format_numeric_metadata(float(values.iloc[0]))
    if details:
        metadata["ic_weight"] = details
    return metadata


def format_numeric_metadata(value: float) -> int | float:
    numeric = float(value)
    if numeric.is_integer():
        return int(numeric)
    return numeric


def industry_neutralization_metadata(root_dir: Path) -> dict[str, object]:
    schema_path = root_dir / "data" / "processed" / "db_schema.csv"
    if not schema_path.exists():
        return {"industry_neutralization_status": "not_checked"}
    schema = read_cache_csv(schema_path)
    if schema.empty or "table" not in schema:
        return {"industry_neutralization_status": "not_checked"}
    tables = set(schema["table"].astype(str))
    if {"map_company_industry_sw", "dim_industry_categories_sw"}.issubset(tables):
        return {"industry_neutralization_status": "sw_found_available"}
    return {"industry_neutralization_status": "not_found"}


def factor_exposure_metadata(panel: pd.DataFrame) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if panel.empty or "ln_total_market_cap" not in panel:
        return metadata
    raw_corr = mean_abs_corr_by_date(panel, "cf_yield", "ln_total_market_cap")
    neutral_corr = mean_abs_corr_by_date(panel, "cf_yield_neutral", "ln_total_market_cap")
    if raw_corr is not None:
        metadata["qa_raw_cf_yield_ln_cap_mean_abs_corr"] = f"{raw_corr:.6g}"
    if neutral_corr is not None:
        metadata["qa_neutral_cf_yield_ln_cap_mean_abs_corr"] = f"{neutral_corr:.6g}"
    if {"cf_yield_neutral", "sw_l1_code"}.issubset(panel.columns):
        rows = []
        for _date, group in panel.dropna(subset=["cf_yield_neutral", "sw_l1_code"]).groupby("date"):
            means = group.groupby("sw_l1_code")["cf_yield_neutral"].mean().abs()
            if not means.empty:
                rows.append(float(means.max()))
        if rows:
            metadata["qa_neutral_industry_dummy_max_abs_mean"] = f"{sum(rows) / len(rows):.6g}"
    return metadata


def mean_abs_corr_by_date(panel: pd.DataFrame, left: str, right: str) -> float | None:
    if left not in panel or right not in panel:
        return None
    correlations = []
    for _date, group in panel.groupby("date"):
        valid = group[[left, right]].dropna()
        if valid.shape[0] >= 3 and valid[left].nunique() > 1 and valid[right].nunique() > 1:
            value = valid[left].corr(valid[right])
            if pd.notna(value):
                correlations.append(abs(float(value)))
    if not correlations:
        return None
    return float(sum(correlations) / len(correlations))


def sync_manifest_quality_metadata(root_dir: Path) -> dict[str, object]:
    metadata: dict[str, object] = {}
    manifests = []
    runs_dir = root_dir / "data" / "processed" / "db_sync_runs"
    if runs_dir.exists():
        manifests.extend(sorted(runs_dir.glob("*/db_sync_manifest.json"), key=lambda path: path.stat().st_mtime))
    pipeline_manifest = root_dir / "data" / "processed" / "pipeline_manifest.json"
    if pipeline_manifest.exists():
        manifests.append(pipeline_manifest)
    for path in manifests:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if payload.get("price_adjustment_fields_found") is not None:
            metadata["price_adjustment_fields_found"] = payload.get("price_adjustment_fields_found", [])
        if payload.get("price_adjustment_warning"):
            metadata["price_adjustment_warning"] = payload["price_adjustment_warning"]
            metadata["price_return_warning_level"] = payload.get("price_return_warning_level", "mathematically_invalid")
    return metadata


def price_cache_coverage(price_dir: Path) -> tuple[dict[str, str], float]:
    ranges: dict[str, str] = {}
    missing_rates: list[float] = []
    for path in sorted(price_dir.glob("*.csv")):
        frame = read_cache_csv(path)
        if frame.empty or "date" not in frame:
            continue
        dates = parse_cache_date(frame["date"]).dropna().sort_values()
        if dates.empty:
            continue
        ranges[path.stem] = f"{dates.min().date().isoformat()}..{dates.max().date().isoformat()}"
        calendar_days = max((dates.max() - dates.min()).days + 1, 1)
        missing_rates.append(1.0 - (dates.nunique() / calendar_days))
    if not missing_rates:
        return ranges, 0.0
    return ranges, float(sum(missing_rates) / len(missing_rates))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise
