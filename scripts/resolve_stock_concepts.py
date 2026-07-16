from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
import akshare as ak

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.data_collection.concept_resolution import resolve_stock_concepts
from aq_factor_lab.data_collection.io import write_frame
from aq_factor_lab.data_layer import DataLayerConfig, configure_data_layer, get_concept_members
from aq_factor_lab.data_layer.akshare_client import AkSharePublicClient


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Resolve stocks.csv candidate concept names against AkShare concept boards."
    )
    parser.add_argument("--input", type=Path, default=ROOT / "stocks.csv")
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "data" / "processed" / "stocks_concept_resolution.csv",
    )
    parser.add_argument(
        "--failures",
        type=Path,
        default=ROOT / "data" / "processed" / "stocks_concept_failures.csv",
    )
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--fuzzy-cutoff", type=float, default=0.55)
    parser.add_argument("--concept-source", choices=["auto", "em", "ths"], default="auto")
    parser.add_argument("--sleep-seconds", type=float, default=1.0)
    parser.add_argument("--max-requests-per-run", type=int, default=200)
    parser.add_argument(
        "--skip-member-counts",
        action="store_true",
        help="Only validate concept-name existence; do not query concept constituent counts.",
    )
    return parser.parse_args(argv)


def load_concept_names(source: str) -> tuple[pd.DataFrame | None, str, pd.DataFrame]:
    failures: list[dict[str, str]] = []
    if source in {"auto", "em"}:
        try:
            return (
                AkSharePublicClient().concept_names(),
                "akshare.stock_board_concept_name_em",
                pd.DataFrame(failures),
            )
        except Exception as exc:  # noqa: BLE001 - data-source failures are reported to CSV.
            failures.append(
                {
                    "stage": "concept_names_em" if source == "auto" else "concept_names",
                    "concept_name": "",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            if source == "em":
                return None, "", pd.DataFrame(failures)

    if source in {"auto", "ths"}:
        try:
            ths = ak.stock_board_concept_name_ths()
            ths = ths.rename(columns={"code": "板块代码", "name": "板块名称"})
            return (
                ths[["板块代码", "板块名称"]],
                "akshare.stock_board_concept_name_ths",
                pd.DataFrame(failures),
            )
        except Exception as exc:  # noqa: BLE001 - data-source failures are reported to CSV.
            failures.append(
                {
                    "stage": "concept_names_ths" if source == "auto" else "concept_names",
                    "concept_name": "",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )

    return None, "", pd.DataFrame(failures)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    candidates = pd.read_csv(args.input, encoding="utf-8-sig")

    configure_data_layer(
        DataLayerConfig(
            root_dir=ROOT,
            sleep_seconds=args.sleep_seconds,
            max_requests_per_run=args.max_requests_per_run,
        )
    )
    concept_names, resolved_source, source_failures = load_concept_names(args.concept_source)
    if concept_names is None:
        write_frame(args.failures, source_failures)
        print(f"failed to fetch AkShare concept names; wrote {args.failures}")
        return 1
    fetch_members = (
        None
        if args.skip_member_counts or resolved_source == "akshare.stock_board_concept_name_ths"
        else get_concept_members
    )

    result = resolve_stock_concepts(
        candidates,
        concept_names,
        fetch_members=fetch_members,
        top_n=args.top_n,
        fuzzy_cutoff=args.fuzzy_cutoff,
    )
    result.resolved["resolved_source"] = resolved_source
    failures = pd.concat([source_failures, result.failures], ignore_index=True)
    write_frame(args.output, result.resolved)
    write_frame(args.failures, failures)

    status_counts = result.resolved["status"].value_counts().to_dict()
    print(f"wrote {args.output}")
    print(f"wrote {args.failures}")
    print(f"status_counts={status_counts}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
