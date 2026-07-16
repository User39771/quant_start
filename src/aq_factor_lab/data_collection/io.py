from __future__ import annotations

import json
import re
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


def safe_slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "theme"


def make_run_id(dry_run: bool) -> str:
    if dry_run:
        return "dry_run"
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def collection_output_dir(output_root: Path, theme_name: str, run_id: str) -> Path:
    return output_root / "data" / "collected" / "thematic" / safe_slug(theme_name) / run_id


def write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8-sig")


def json_ready(value: Any) -> Any:
    if is_dataclass(value):
        return json_ready(asdict(value))
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): json_ready(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_ready(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    return value


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(json_ready(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
