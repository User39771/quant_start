from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.utils import clean_code, exchange_prefix, is_hushen_a, read_cache_csv

A_SHARE_DB_SYMBOL_RE = re.compile(r"^(SH|SZ)_\d{6}$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run database cache sync and cache-only research.")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--endpoints", type=str, default="universe,price,cashflow,profit")
    parser.add_argument("--symbols", type=str, default="")
    parser.add_argument("--chunk-size", type=int, default=200)
    parser.add_argument("--years", type=int, default=5)
    parser.add_argument("--start-date", type=str, default="")
    parser.add_argument("--end-date", type=str, default="")
    parser.add_argument("--refresh-existing", action="store_true")
    parser.add_argument("--skip-research", action="store_true")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    root = args.root.resolve()
    endpoints = parse_csv(args.endpoints)
    start_date, end_date = date_range(args)
    if args.symbols.strip():
        symbols = parse_csv(args.symbols)
        universe_stats = {
            "raw_universe_count": len(symbols),
            "a_share_symbol_count": len(symbols),
            "excluded_symbol_count": 0,
        }
    else:
        symbols, universe_stats = load_universe_symbols(root)
    if args.chunk_size <= 0:
        raise SystemExit("--chunk-size must be positive")

    started_at = datetime.now().isoformat(timespec="seconds")
    sync_returncodes: list[int] = []
    sync_batches = 0
    existing_sync_runs = existing_run_dirs(root)

    if "universe" in endpoints and not args.symbols.strip():
        sync_returncodes.append(run_sync(root, ["universe"], [], start_date, end_date, args.refresh_existing))

    sync_endpoints = [endpoint for endpoint in endpoints if endpoint != "universe"]
    for chunk in chunked(symbols, args.chunk_size):
        if not sync_endpoints:
            break
        sync_batches += 1
        sync_returncodes.append(run_sync(root, sync_endpoints, chunk, start_date, end_date, args.refresh_existing))

    research_returncode = 0
    if not args.skip_research:
        research_symbols = symbols if args.symbols.strip() else []
        research_returncode = run_research(root, args.years, research_symbols)

    manifest = {
        "started_at": started_at,
        "ended_at": datetime.now().isoformat(timespec="seconds"),
        "root": str(root),
        "endpoints": endpoints,
        "symbols_count": len(symbols),
        **universe_stats,
        "sync_batches": sync_batches,
        "chunk_size": args.chunk_size,
        "start_date": start_date,
        "end_date": end_date,
        "refresh_existing": bool(args.refresh_existing),
        "sync_returncodes": sync_returncodes,
        "research_returncode": research_returncode,
    }
    manifest.update(collect_sync_run_metadata(root, existing_sync_runs))
    output = root / "data" / "processed" / "pipeline_manifest.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Pipeline manifest written: {output}")
    print(f"Symbols: {len(symbols)}; sync batches: {sync_batches}; research returncode: {research_returncode}")
    if any(code != 0 for code in sync_returncodes) or research_returncode != 0:
        raise SystemExit(1)


def parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def date_range(args: argparse.Namespace) -> tuple[str, str]:
    end = date.fromisoformat(args.end_date) if args.end_date else date.today()
    start = date.fromisoformat(args.start_date) if args.start_date else end - timedelta(days=365 * args.years + 90)
    return start.isoformat(), end.isoformat()


def load_universe_symbols(root: Path) -> tuple[list[str], dict[str, int]]:
    path = root / "data" / "cache" / "universe_spot.csv"
    if not path.exists():
        raise FileNotFoundError(f"Universe cache is required before batched sync: {path}")
    universe = read_cache_csv(path)
    if universe.empty or "code" not in universe:
        return [], {"raw_universe_count": int(universe.shape[0]), "a_share_symbol_count": 0, "excluded_symbol_count": 0}
    frame = universe.copy()
    raw_count = int(frame.shape[0])
    frame["code"] = frame["code"].map(clean_code)
    if "db_symbol" not in frame:
        frame["db_symbol"] = frame["code"].map(lambda code: f"{exchange_prefix(code)}_{code}")
    if "exchange" in frame:
        frame["exchange"] = frame["exchange"].astype(str).str.upper()
        frame = frame[frame["exchange"].isin(["SH", "SZ"])]
    frame["db_symbol"] = frame["db_symbol"].astype(str)
    frame = frame[frame["db_symbol"].str.match(A_SHARE_DB_SYMBOL_RE)]
    frame = frame[frame["code"].map(is_hushen_a)]
    frame = frame.drop_duplicates("code").sort_values("code")
    symbols = frame["db_symbol"].astype(str).tolist()
    stats = {
        "raw_universe_count": raw_count,
        "a_share_symbol_count": len(symbols),
        "excluded_symbol_count": raw_count - len(symbols),
    }
    return symbols, stats


def chunked(values: list[str], size: int) -> list[list[str]]:
    return [values[index : index + size] for index in range(0, len(values), size)]


def run_sync(root: Path, endpoints: list[str], symbols: list[str], start_date: str, end_date: str, refresh: bool) -> int:
    command = [
        sys.executable,
        str(root / "scripts" / "sync_database_cache.py"),
        "--endpoints",
        ",".join(endpoints),
        "--start-date",
        start_date,
        "--end-date",
        end_date,
    ]
    if symbols:
        command.extend(["--symbols", ",".join(symbols)])
    if refresh:
        command.append("--refresh-existing")
    print(f"Running sync: endpoints={','.join(endpoints)} symbols={len(symbols)}")
    return subprocess.run(command, cwd=root, check=False).returncode


def run_research(root: Path, years: int, symbols: list[str] | None = None) -> int:
    command = [
        sys.executable,
        str(root / "scripts" / "run_research.py"),
        "--cache-only",
        "--years",
        str(years),
        "--sleep",
        "0",
        "--root",
        str(root),
    ]
    if symbols:
        codes = [clean_code(symbol) for symbol in symbols]
        command.extend(["--symbols", ",".join(codes)])
    print("Running cache-only research")
    return subprocess.run(command, cwd=root, check=False).returncode


def existing_run_dirs(root: Path) -> set[str]:
    runs = root / "data" / "processed" / "db_sync_runs"
    if not runs.exists():
        return set()
    return {path.name for path in runs.iterdir() if path.is_dir()}


def collect_sync_run_metadata(root: Path, existing_runs: set[str]) -> dict[str, object]:
    runs = root / "data" / "processed" / "db_sync_runs"
    if not runs.exists():
        return {}
    status_counts: dict[str, int] = {}
    adjustment_fields: set[str] = set()
    adjustment_warning = ""
    run_count = 0
    for run_dir in sorted(path for path in runs.iterdir() if path.is_dir() and path.name not in existing_runs):
        manifest_path = run_dir / "db_sync_manifest.json"
        if not manifest_path.exists():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        run_count += 1
        for status, count in manifest.get("status_counts", {}).items():
            status_counts[status] = status_counts.get(status, 0) + int(count)
        adjustment_fields.update(str(field) for field in manifest.get("price_adjustment_fields_found", []))
        if manifest.get("price_adjustment_warning"):
            adjustment_warning = str(manifest["price_adjustment_warning"])
    payload: dict[str, object] = {
        "sync_run_count": run_count,
        "sync_status_counts": status_counts,
        "price_adjustment_fields_found": sorted(adjustment_fields),
    }
    if adjustment_warning:
        payload["price_adjustment_warning"] = adjustment_warning
        payload["price_return_warning_level"] = "mathematically_invalid"
    return payload


if __name__ == "__main__":
    main()
