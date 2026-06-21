from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.config import DEFAULT_SLEEP_SECONDS, ResearchConfig, default_dates
from aq_factor_lab.data import AkShareClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Slowly pre-cache A-share daily price data only.")
    parser.add_argument("--years", type=int, default=3, help="Lookback years, default: 3.")
    parser.add_argument("--max-symbols", type=int, default=None, help="Limit universe size for staged runs.")
    parser.add_argument("--symbols", type=str, default="", help="Comma-separated stock codes, bypassing universe.")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP_SECONDS, help="Sleep seconds between symbols.")
    parser.add_argument("--refresh-existing", action="store_true", help="Fetch again even when price cache exists.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Project root directory.")
    return parser


def build_symbol_frame(args: argparse.Namespace, client: AkShareClient) -> pd.DataFrame:
    if args.symbols.strip():
        symbols = [item.strip().zfill(6) for item in args.symbols.split(",") if item.strip()]
        return pd.DataFrame({"code": symbols, "name": symbols})
    return client.universe()[["code", "name"]]


def main() -> None:
    args = build_parser().parse_args()
    start, end = default_dates(args.years)
    config = ResearchConfig(
        root_dir=args.root,
        start_date=start,
        end_date=end,
        max_symbols=args.max_symbols,
        sleep_seconds=args.sleep,
        use_cache=not args.refresh_existing,
        price_cache_only=False,
        cache_only=False,
    )
    client = AkShareClient(config)
    universe = build_symbol_frame(args, client)
    rows: list[dict[str, str]] = []
    print(f"[{datetime.now():%H:%M:%S}] Pre-caching price for {len(universe)} symbols...")

    for idx, row in universe.iterrows():
        code = str(row["code"]).zfill(6)
        name = str(row.get("name", code))
        cache_path = config.cache_dir / "price" / f"{code}.csv"
        if config.use_cache and cache_path.exists():
            print(f"[{idx + 1}/{len(universe)}] cached {code} {name}")
            rows.append({"code": code, "name": name, "status": "cached", "error": ""})
        else:
            print(f"[{idx + 1}/{len(universe)}] fetching price {code} {name}")
            ok = client.precache_price(code, name)
            error = "" if ok else str(client.failed_symbols[-1]["error"])
            rows.append({"code": code, "name": name, "status": "success" if ok else "failed", "error": error})
        if idx + 1 < len(universe):
            client.sleep_between_symbols()

    config.processed_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows, columns=["code", "name", "status", "error"]).to_csv(
        config.processed_dir / "price_precache_summary.csv",
        index=False,
        encoding="utf-8-sig",
    )
    pd.DataFrame(
        client.failures,
        columns=["code", "name", "endpoint", "error_type", "attempts", "cache_fallback", "error"],
    ).to_csv(config.processed_dir / "fetch_failures.csv", index=False, encoding="utf-8-sig")
    client.failed_symbols_frame().to_csv(
        config.processed_dir / "failed_symbols.csv",
        index=False,
        encoding="utf-8-sig",
    )

    summary = pd.Series([row["status"] for row in rows]).value_counts().to_dict()
    print(f"Price pre-cache summary: {summary}")
    print(f"Summary written: {config.processed_dir / 'price_precache_summary.csv'}")


if __name__ == "__main__":
    main()
