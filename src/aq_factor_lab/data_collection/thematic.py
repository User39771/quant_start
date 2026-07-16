from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from typing import Any

import pandas as pd

import aq_factor_lab.data_layer as data_layer
from aq_factor_lab.data_layer import DataLayerConfig

from .config import CollectionResult, ThematicCollectionConfig
from .errors import DataCollectionError
from .io import collection_output_dir, make_run_id, write_frame, write_json

MEMBERSHIP_WARNING = (
    "concept and universe membership are current_snapshot in v1, not historical "
    "point-in-time truth"
)

FAILURE_COLUMNS = ["stage", "symbol", "concept_name", "index_code", "error_type", "error"]


def collect_thematic_dataset(config: ThematicCollectionConfig) -> CollectionResult:
    """Collect a bounded thematic dataset through the cache-first public data layer."""
    run_id = make_run_id(config.dry_run)
    output_dir = collection_output_dir(config.output_root, config.theme_name, run_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    data_layer.configure_data_layer(
        DataLayerConfig(
            root_dir=config.output_root,
            cache_only=config.cache_only,
            dry_run=config.dry_run,
            max_requests_per_run=config.max_requests_per_run,
            sleep_seconds=config.sleep_seconds,
        )
    )

    write_json(output_dir / "run_config.json", config)

    if config.dry_run:
        return _write_empty_dry_run(config, output_dir, run_id)

    failures: list[dict[str, object]] = []
    concept_members = _collect_concepts(config.concept_names, failures)
    selected_symbols = _selected_symbols(concept_members, config.max_symbols)
    if not selected_symbols:
        raise DataCollectionError("No symbols found from requested concept members")

    universe = _fetch_universe(config.end, failures)
    daily_prices = _collect_daily_prices(config, selected_symbols, failures)
    index_prices = _collect_indices(config, failures)

    write_frame(output_dir / "concept_members_snapshot.csv", concept_members)
    if universe is not None:
        write_frame(output_dir / "stock_universe_snapshot.csv", universe)
    write_frame(output_dir / "daily_prices.csv", daily_prices)
    if config.benchmark_indices:
        write_frame(output_dir / "index_prices.csv", index_prices)
    failures_frame = pd.DataFrame(failures, columns=FAILURE_COLUMNS)
    write_frame(output_dir / "failures.csv", failures_frame)

    succeeded = int(daily_prices["symbol"].nunique()) if not daily_prices.empty else 0
    failed_symbols = {
        str(row["symbol"]) for row in failures if row.get("stage") == "daily_price" and row.get("symbol")
    }
    manifest = _manifest(
        config,
        run_id,
        selected_symbols,
        {
            "concept_members_snapshot.csv": len(concept_members),
            "stock_universe_snapshot.csv": 0 if universe is None else len(universe),
            "daily_prices.csv": len(daily_prices),
            "index_prices.csv": len(index_prices),
            "failures.csv": len(failures_frame),
        },
        len(failures_frame),
    )
    write_json(output_dir / "collection_manifest.json", manifest)

    return CollectionResult(
        output_dir=output_dir,
        run_id=run_id,
        theme_name=config.theme_name,
        requested_concepts=list(config.concept_names),
        symbols_requested=len(selected_symbols),
        symbols_succeeded=succeeded,
        symbols_failed=len(failed_symbols),
        index_count=len(config.benchmark_indices or []),
        dry_run=config.dry_run,
        cache_only=config.cache_only,
    )


def _write_empty_dry_run(
    config: ThematicCollectionConfig,
    output_dir: Path,
    run_id: str,
) -> CollectionResult:
    selected_symbols: list[str] = []
    write_frame(output_dir / "concept_members_snapshot.csv", pd.DataFrame())
    write_frame(output_dir / "daily_prices.csv", pd.DataFrame())
    if config.benchmark_indices:
        write_frame(output_dir / "index_prices.csv", pd.DataFrame())
    write_frame(output_dir / "failures.csv", pd.DataFrame(columns=FAILURE_COLUMNS))
    write_json(
        output_dir / "collection_manifest.json",
        _manifest(
            config,
            run_id,
            selected_symbols,
            {
                "concept_members_snapshot.csv": 0,
                "daily_prices.csv": 0,
                "index_prices.csv": 0,
                "failures.csv": 0,
            },
            0,
        ),
    )
    return CollectionResult(
        output_dir=output_dir,
        run_id=run_id,
        theme_name=config.theme_name,
        requested_concepts=list(config.concept_names),
        symbols_requested=0,
        symbols_succeeded=0,
        symbols_failed=0,
        index_count=len(config.benchmark_indices or []),
        dry_run=True,
        cache_only=config.cache_only,
    )


def _collect_concepts(
    concept_names: list[str],
    failures: list[dict[str, object]],
) -> pd.DataFrame:
    frames = []
    for concept_name in concept_names:
        try:
            frames.append(data_layer.get_concept_members(concept_name, date=None))
        except Exception as exc:
            failures.append(_failure("concept_members", exc, concept_name=concept_name))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _selected_symbols(concept_members: pd.DataFrame, max_symbols: int) -> list[str]:
    if concept_members.empty or "symbol" not in concept_members.columns:
        return []
    symbols = sorted({str(symbol).zfill(6) for symbol in concept_members["symbol"].dropna()})
    return symbols[:max_symbols]


def _fetch_universe(
    end: str,
    failures: list[dict[str, object]],
) -> pd.DataFrame | None:
    try:
        return data_layer.get_stock_universe(end, filters=None)
    except Exception as exc:
        failures.append(_failure("stock_universe", exc))
        return None


def _collect_daily_prices(
    config: ThematicCollectionConfig,
    selected_symbols: list[str],
    failures: list[dict[str, object]],
) -> pd.DataFrame:
    frames = []
    for symbol in selected_symbols:
        try:
            frames.append(data_layer.get_daily_price(symbol, config.start, config.end, adjusted=config.adjusted))
        except Exception as exc:
            failures.append(_failure("daily_price", exc, symbol=symbol))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _collect_indices(
    config: ThematicCollectionConfig,
    failures: list[dict[str, object]],
) -> pd.DataFrame:
    frames = []
    for index_code in config.benchmark_indices or []:
        try:
            frames.append(data_layer.get_index_price(index_code, config.start, config.end))
        except Exception as exc:
            failures.append(_failure("index_price", exc, index_code=index_code))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _failure(
    stage: str,
    exc: Exception,
    *,
    symbol: str = "",
    concept_name: str = "",
    index_code: str = "",
) -> dict[str, object]:
    return {
        "stage": stage,
        "symbol": symbol,
        "concept_name": concept_name,
        "index_code": index_code,
        "error_type": type(exc).__name__,
        "error": str(exc),
    }


def _manifest(
    config: ThematicCollectionConfig,
    run_id: str,
    selected_symbols: list[str],
    row_counts: dict[str, int],
    failure_count: int,
) -> dict[str, Any]:
    payload = asdict(config)
    payload["output_root"] = str(config.output_root)
    payload.update(
        {
            "run_id": run_id,
            "selected_symbols": selected_symbols,
            "row_counts": row_counts,
            "failure_count": failure_count,
            "dry_run": config.dry_run,
            "cache_only": config.cache_only,
            "membership_warning": MEMBERSHIP_WARNING,
        }
    )
    return payload
