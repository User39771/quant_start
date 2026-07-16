from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DataLayerConfig:
    """Runtime configuration for conservative public-data access."""

    root_dir: Path
    source: str = "akshare"
    schema_version: str = "v1"
    sleep_seconds: float = 10.0
    max_requests_per_run: int = 20
    max_attempts: int = 3
    timeout_seconds: float = 20.0
    cache_only: bool = False
    dry_run: bool = False
    allow_stale_cache: bool = False

    @property
    def public_cache_dir(self) -> Path:
        return self.root_dir / "data" / "cache" / "public"

    @property
    def raw_cache_dir(self) -> Path:
        return self.public_cache_dir / "raw"

    @property
    def clean_cache_dir(self) -> Path:
        return self.public_cache_dir / "clean"

    @property
    def manifest_dir(self) -> Path:
        return self.public_cache_dir / "manifests"

    @property
    def log_dir(self) -> Path:
        return self.public_cache_dir / "logs"


def default_config() -> DataLayerConfig:
    return DataLayerConfig(root_dir=Path.cwd())
