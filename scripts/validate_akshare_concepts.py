from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.data_collection.io import write_frame
from aq_factor_lab.data_layer.akshare_client import AkSharePublicClient
from aq_factor_lab.theme_concepts import (
    apply_manual_overrides,
    clean_concept_mapping,
    load_concept_mapping,
    load_manual_overrides,
    validate_akshare_concepts,
)

CONCEPT_NAME_CACHE = ROOT / "data" / "cache" / "public" / "raw" / "akshare" / "concept_names" / "stock_board_concept_name_em.csv"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate reviewed theme concepts against Eastmoney AkShare concept boards.")
    parser.add_argument("--input", type=Path, default=ROOT / "data" / "manual" / "source_concept_mapping.csv")
    parser.add_argument("--overrides", type=Path, default=ROOT / "config" / "theme_concept_overrides.csv")
    parser.add_argument("--clean-output", type=Path, default=ROOT / "data" / "processed" / "theme_concept_mapping_clean.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "processed" / "akshare_concept_validation.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "akshare_concept_validation_report.md")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--top-n", type=int, default=5)
    parser.add_argument("--fuzzy-cutoff", type=float, default=0.65)
    return parser.parse_args(argv)


def load_or_fetch_concept_names(refresh: bool) -> tuple[pd.DataFrame | None, str, str]:
    if CONCEPT_NAME_CACHE.exists() and not refresh:
        return pd.read_csv(CONCEPT_NAME_CACHE, dtype=str, keep_default_na=False), "cache_hit", ""
    try:
        concepts = AkSharePublicClient().concept_names()
        CONCEPT_NAME_CACHE.parent.mkdir(parents=True, exist_ok=True)
        concepts.to_csv(CONCEPT_NAME_CACHE, index=False, encoding="utf-8-sig")
        return concepts, "refreshed" if refresh else "cache_miss_fetched", ""
    except Exception as exc:  # noqa: BLE001 - top-level data source failure is reported.
        if CONCEPT_NAME_CACHE.exists():
            return pd.read_csv(CONCEPT_NAME_CACHE, dtype=str, keep_default_na=False), "fetch_failed_cache_hit", str(exc)
        return None, "fetch_failed_no_cache", str(exc)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = datetime.now(UTC).isoformat()
    input_file = str(args.input)
    raw = load_concept_mapping(args.input)
    clean, warnings = clean_concept_mapping(raw, input_file=input_file, generated_at=generated_at)

    concept_names, cache_status, fetch_error = load_or_fetch_concept_names(args.refresh)
    clean["refresh"] = bool(args.refresh)
    clean["akshare_cache_status"] = cache_status
    clean["selected_themes"] = ""
    clean["selected_rings"] = ""
    clean["default_only"] = ""
    clean["include_conditional"] = ""
    clean["include_p2"] = ""
    clean["include_excluded_for_audit"] = ""
    write_frame(args.clean_output, clean)

    if concept_names is None:
        empty = pd.DataFrame()
        write_frame(args.output, empty)
        _write_validation_report(
            args.report,
            validation=empty,
            clean=clean,
            warnings=warnings,
            metadata=_metadata(args, generated_at, cache_status),
            fetch_error=fetch_error,
        )
        print(f"failed to fetch EM AkShare concept names; wrote {args.report}")
        return 1

    result = validate_akshare_concepts(
        clean,
        concept_names,
        generated_at=generated_at,
        input_file=input_file,
        refresh=args.refresh,
        akshare_cache_status=cache_status,
        top_n=args.top_n,
        fuzzy_cutoff=args.fuzzy_cutoff,
    )
    overrides = load_manual_overrides(args.overrides)
    validation = apply_manual_overrides(result.resolved, overrides)
    validation["selected_themes"] = ""
    validation["selected_rings"] = ""
    validation["default_only"] = ""
    validation["include_conditional"] = ""
    validation["include_p2"] = ""
    validation["include_excluded_for_audit"] = ""
    write_frame(args.output, validation)
    _write_validation_report(
        args.report,
        validation=validation,
        clean=clean,
        warnings=warnings,
        metadata=_metadata(args, generated_at, cache_status),
        fetch_error=fetch_error,
    )
    print(f"wrote {args.clean_output}")
    print(f"wrote {args.output}")
    print(f"wrote {args.report}")
    return 0


def _metadata(args: argparse.Namespace, generated_at: str, cache_status: str) -> dict[str, object]:
    return {
        "generated_at": generated_at,
        "input_file": str(args.input),
        "refresh": bool(args.refresh),
        "akshare_cache_status": cache_status,
        "selected_themes": "",
        "selected_rings": "",
        "default_only": "",
        "include_conditional": "",
        "include_p2": "",
        "include_excluded_for_audit": "",
    }


def _write_validation_report(
    path: Path,
    *,
    validation: pd.DataFrame,
    clean: pd.DataFrame,
    warnings: pd.DataFrame,
    metadata: dict[str, object],
    fetch_error: str,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# AkShare Concept Validation Report",
        "",
        "This worksheet is a reviewed concept taxonomy, not a stock recommendation list.",
        "AkShare concept names are validated only against Eastmoney concept boards in this phase.",
        "Fuzzy matches are candidate suggestions only and are not auto-confirmed.",
        "",
        "## Run Metadata",
    ]
    lines.extend(f"- {key}={value}" for key, value in metadata.items())
    if fetch_error:
        lines.append(f"- concept_name_fetch_error={fetch_error}")
    lines.extend(
        [
            "",
            "## Summary",
            f"- mapping_rows={len(clean)}",
            f"- validation_rows={len(validation)}",
            f"- mapping_warnings={len(warnings)}",
        ]
    )
    if not validation.empty and "match_status" in validation:
        lines.append("")
        lines.append("## Match Status Counts")
        for status, count in validation["match_status"].value_counts().sort_index().items():
            lines.append(f"- {status}={count}")
        review = validation[validation["match_status"].isin(["fuzzy_candidate", "not_found", "manual_rejected"])]
        if not review.empty:
            lines.extend(["", "## Action Required"])
            for _, row in review.iterrows():
                lines.append(
                    "- "
                    f"theme={row.get('theme', '')}; "
                    f"concept={row.get('possible_akshare_concept', '')}; "
                    f"status={row.get('match_status', '')}; "
                    f"action={row.get('action_required', '')}; "
                    f"fuzzy={row.get('fuzzy_candidates', '')}"
                )
    lines.extend(
        [
            "",
            "## Caveats",
            "- Concept constituents can be noisy current snapshots.",
            "- P0/P1/P2 and include_default control later universe construction.",
            "- All source claims remain evidence summaries unless separately verified.",
            "- The output is a research input for later testing, not alpha proof.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
