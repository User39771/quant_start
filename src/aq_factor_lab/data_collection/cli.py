from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .config import ThematicCollectionConfig
from .thematic import collect_thematic_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Collect a bounded thematic research dataset.")
    parser.add_argument("--config", type=Path, default=Path("configs/thematic_data_sample.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--cache-only", action="store_true")
    parser.add_argument("--max-symbols", type=int)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--theme-name")
    return parser


def load_config(
    path: Path,
    *,
    dry_run: bool = False,
    cache_only: bool = False,
    max_symbols: int | None = None,
    start: str | None = None,
    end: str | None = None,
    theme_name: str | None = None,
) -> ThematicCollectionConfig:
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    if theme_name is not None:
        payload["theme_name"] = theme_name
    if start is not None:
        payload["start"] = start
    if end is not None:
        payload["end"] = end
    if max_symbols is not None:
        payload["max_symbols"] = max_symbols
    if dry_run:
        payload["dry_run"] = True
    if cache_only:
        payload["cache_only"] = True
    payload["output_root"] = Path(payload.get("output_root", "."))
    return ThematicCollectionConfig(**payload)


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    config = load_config(
        args.config,
        dry_run=args.dry_run,
        cache_only=args.cache_only,
        max_symbols=args.max_symbols,
        start=args.start,
        end=args.end,
        theme_name=args.theme_name,
    )
    result = collect_thematic_dataset(config)
    print(f"output_dir={result.output_dir}")
    print(f"run_id={result.run_id}")


if __name__ == "__main__":
    main()
