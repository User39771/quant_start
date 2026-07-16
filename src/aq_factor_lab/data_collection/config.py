from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ThematicCollectionConfig:
    theme_name: str
    concept_names: list[str]
    start: str
    end: str
    output_root: Path
    benchmark_indices: list[str] | None = None
    max_symbols: int = 30
    adjusted: bool = True
    cache_only: bool = False
    dry_run: bool = False
    max_requests_per_run: int = 50
    sleep_seconds: float = 10.0


@dataclass(frozen=True)
class CollectionResult:
    output_dir: Path
    run_id: str
    theme_name: str
    requested_concepts: list[str]
    symbols_requested: int
    symbols_succeeded: int
    symbols_failed: int
    index_count: int
    dry_run: bool
    cache_only: bool
