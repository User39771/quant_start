from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from .config import DataLayerConfig


@dataclass(frozen=True)
class CachePaths:
    raw: Path
    clean: Path
    manifest: Path


def normalized_filters(filters: dict | None) -> str:
    if not filters:
        return "{}"
    return json.dumps(filters, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def build_query_payload(
    *,
    endpoint: str,
    config: DataLayerConfig,
    symbol: str | None = None,
    index_code: str | None = None,
    concept_name: str | None = None,
    start: str | None = None,
    end: str | None = None,
    adjusted: bool | None = None,
    requested_date: str | None = None,
    filters: dict | None = None,
) -> dict[str, Any]:
    return {
        "endpoint": endpoint,
        "source": config.source,
        "schema_version": config.schema_version,
        "symbol": symbol or "",
        "index_code": index_code or "",
        "concept_name": concept_name or "",
        "start": start or "",
        "end": end or "",
        "adjusted": adjusted,
        "requested_date": requested_date or "",
        "filters": json.loads(normalized_filters(filters)),
    }


def query_key(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:24]
    endpoint = str(payload["endpoint"])
    identifier = (
        str(payload.get("symbol") or payload.get("index_code") or payload.get("concept_name") or "query")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )
    return f"{endpoint}_{identifier}_{digest}"


def cache_paths(config: DataLayerConfig, endpoint: str, key: str) -> CachePaths:
    return CachePaths(
        raw=config.raw_cache_dir / config.source / endpoint / f"{key}.csv",
        clean=config.clean_cache_dir / config.source / endpoint / f"{key}.csv",
        manifest=config.manifest_dir / config.source / endpoint / f"{key}.json",
    )


def read_clean_cache(path: Path, date_columns: list[str] | None = None) -> pd.DataFrame:
    df = pd.read_csv(path, dtype={"symbol": str, "index_code": str})
    for column in date_columns or []:
        if column in df.columns:
            df[column] = pd.to_datetime(df[column], errors="coerce")
    if "adjusted" in df.columns:
        df["adjusted"] = df["adjusted"].astype(bool)
    return df


def write_csv(path: Path, df: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def write_manifest(
    *,
    path: Path,
    akshare_version: str,
    endpoint: str,
    source: str,
    schema_version: str,
    query_key_value: str,
    adjust_mode: str,
    raw_row_count: int,
    clean_row_count: int,
    raw_path: Path,
    clean_path: Path,
) -> None:
    payload = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "akshare_version": akshare_version,
        "endpoint": endpoint,
        "source": source,
        "schema_version": schema_version,
        "query_key": query_key_value,
        "adjust_mode": adjust_mode,
        "raw_row_count": raw_row_count,
        "clean_row_count": clean_row_count,
        "raw_path": str(raw_path),
        "clean_path": str(clean_path),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
