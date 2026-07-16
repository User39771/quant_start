from __future__ import annotations

import argparse
import re
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
    build_business_materiality_diagnostics,
    build_constituent_table,
    build_high_confidence_business_mismatch_queue,
    build_stock_business_profile_template,
    build_theme_stock_purity_diagnostics,
    build_theme_stock_review_queue,
    build_theme_stock_universe,
    load_manual_overrides,
    load_purity_rules,
    load_stock_business_profiles,
    load_stock_overrides,
    select_validated_concepts,
)

CONSTITUENT_CACHE_DIR = ROOT / "data" / "cache" / "public" / "raw" / "akshare" / "theme_concept_constituents"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build a concept-weighted theme research universe.")
    parser.add_argument("--validation", type=Path, default=ROOT / "data" / "processed" / "akshare_concept_validation.csv")
    parser.add_argument("--overrides", type=Path, default=ROOT / "config" / "theme_concept_overrides.csv")
    parser.add_argument(
        "--output-constituents",
        type=Path,
        default=ROOT / "data" / "processed" / "theme_concept_constituents.csv",
    )
    parser.add_argument("--output-universe", type=Path, default=ROOT / "data" / "processed" / "theme_stock_universe.csv")
    parser.add_argument("--report", type=Path, default=ROOT / "reports" / "theme_stock_universe_report.md")
    parser.add_argument("--purity-rules", type=Path, default=ROOT / "config" / "theme_concept_purity_rules.json")
    parser.add_argument("--stock-overrides", type=Path, default=ROOT / "config" / "theme_stock_overrides.csv")
    parser.add_argument("--output-purity-diagnostics", type=Path, default=None)
    parser.add_argument("--output-review-queue", type=Path, default=None)
    parser.add_argument("--purity-report", type=Path, default=None)
    parser.add_argument("--price-cache-dir", type=Path, default=ROOT / "data" / "cache" / "price")
    parser.add_argument("--business-profile", type=Path, default=ROOT / "data" / "manual" / "stock_business_profile.csv")
    parser.add_argument("--output-business-materiality", type=Path, default=None)
    parser.add_argument("--output-high-confidence-mismatch", type=Path, default=None)
    parser.add_argument("--output-business-profile-template", type=Path, default=None)
    parser.add_argument("--business-materiality-report", type=Path, default=None)
    parser.add_argument("--themes", type=str, default="")
    parser.add_argument("--rings", type=str, default="")
    parser.add_argument("--default-only", action="store_true", default=True)
    parser.add_argument("--include-conditional", action="store_true")
    parser.add_argument("--include-p2", action="store_true")
    parser.add_argument("--include-excluded-for-audit", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-concepts", type=int, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    generated_at = datetime.now(UTC).isoformat()
    purity_output = args.output_purity_diagnostics or args.output_universe.parent / "theme_stock_purity_diagnostics.csv"
    review_queue_output = args.output_review_queue or args.output_universe.parent / "theme_stock_review_queue.csv"
    purity_report = args.purity_report or args.report.parent / "theme_stock_purity_report.md"
    materiality_output = args.output_business_materiality or args.output_universe.parent / "theme_business_materiality_diagnostics.csv"
    mismatch_output = args.output_high_confidence_mismatch or args.output_universe.parent / "high_confidence_business_mismatch_queue.csv"
    profile_template_output = args.output_business_profile_template or _default_profile_template_output(args.output_universe)
    materiality_report = args.business_materiality_report or args.report.parent / "theme_business_materiality_report.md"
    validation = pd.read_csv(args.validation, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    overrides = load_manual_overrides(args.overrides)
    validation = apply_manual_overrides(validation, overrides)
    purity_rules = load_purity_rules(args.purity_rules)
    stock_overrides = load_stock_overrides(args.stock_overrides)
    business_profiles = load_stock_business_profiles(args.business_profile)

    themes = _parse_csv_arg(args.themes)
    rings = _parse_csv_arg(args.rings)
    metadata = _metadata(args, generated_at, themes, rings)
    selected = select_validated_concepts(
        validation,
        themes=themes or None,
        rings=rings or None,
        default_only=args.default_only,
        include_conditional=args.include_conditional,
        include_p2=args.include_p2,
        include_excluded_for_audit=args.include_excluded_for_audit,
        max_concepts=args.max_concepts,
    )
    cache_status: dict[str, str] = {}

    def fetch_members(concept_name: str) -> pd.DataFrame:
        return _load_or_fetch_members(concept_name, refresh=args.refresh, cache_status=cache_status)

    constituents, failures = build_constituent_table(
        selected,
        fetch_members=fetch_members,
        generated_at=generated_at,
        run_metadata=metadata,
        dry_run=args.dry_run,
    )
    universe = build_theme_stock_universe(
        constituents,
        generated_at=generated_at,
        run_metadata=metadata,
    )
    diagnostics = build_theme_stock_purity_diagnostics(
        universe,
        constituents,
        purity_rules=purity_rules,
        stock_overrides=stock_overrides,
        generated_at=generated_at,
        run_metadata=metadata,
        price_cache_dir=args.price_cache_dir,
    )
    review_queue = build_theme_stock_review_queue(diagnostics)
    materiality = build_business_materiality_diagnostics(
        diagnostics,
        business_profiles,
        stock_overrides=stock_overrides,
        generated_at=generated_at,
        run_metadata=metadata,
    )
    mismatch_queue = build_high_confidence_business_mismatch_queue(materiality)
    profile_template = build_stock_business_profile_template(materiality, mismatch_queue)
    write_frame(args.output_constituents, constituents)
    write_frame(args.output_universe, universe)
    write_frame(purity_output, diagnostics)
    write_frame(review_queue_output, review_queue)
    write_frame(materiality_output, materiality)
    write_frame(mismatch_output, mismatch_queue)
    write_frame(profile_template_output, profile_template)
    _write_universe_report(
        args.report,
        selected=selected,
        constituents=constituents,
        universe=universe,
        failures=failures,
        metadata=metadata,
        cache_status=cache_status,
    )
    _write_purity_report(
        purity_report,
        diagnostics=diagnostics,
        review_queue=review_queue,
        metadata=metadata,
        purity_rules_path=args.purity_rules,
        stock_overrides_path=args.stock_overrides,
        price_cache_dir=args.price_cache_dir,
    )
    _write_business_materiality_report(
        materiality_report,
        materiality=materiality,
        mismatch_queue=mismatch_queue,
        profile_template=profile_template,
        metadata=metadata,
        business_profile_path=args.business_profile,
        materiality_output=materiality_output,
        mismatch_output=mismatch_output,
        profile_template_output=profile_template_output,
    )
    print(f"wrote {args.output_constituents}")
    print(f"wrote {args.output_universe}")
    print(f"wrote {purity_output}")
    print(f"wrote {review_queue_output}")
    print(f"wrote {materiality_output}")
    print(f"wrote {mismatch_output}")
    print(f"wrote {profile_template_output}")
    print(f"wrote {args.report}")
    print(f"wrote {purity_report}")
    print(f"wrote {materiality_report}")
    return 0 if failures.empty else 1


def _load_or_fetch_members(concept_name: str, *, refresh: bool, cache_status: dict[str, str]) -> pd.DataFrame:
    path = CONSTITUENT_CACHE_DIR / f"{_safe_name(concept_name)}.csv"
    if path.exists() and not refresh:
        cache_status[concept_name] = "cache_hit"
        return pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    members = AkSharePublicClient().concept_members(concept_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    members.to_csv(path, index=False, encoding="utf-8-sig")
    cache_status[concept_name] = "refreshed" if refresh else "cache_miss_fetched"
    return members


def _metadata(args: argparse.Namespace, generated_at: str, themes: list[str], rings: list[str]) -> dict[str, object]:
    return {
        "generated_at": generated_at,
        "input_file": str(args.validation),
        "refresh": bool(args.refresh),
        "akshare_cache_status": "per_concept",
        "selected_themes": "|".join(themes) if themes else "all",
        "selected_rings": "|".join(rings) if rings else "default",
        "default_only": bool(args.default_only),
        "include_conditional": bool(args.include_conditional),
        "include_p2": bool(args.include_p2),
        "include_excluded_for_audit": bool(args.include_excluded_for_audit),
        "dry_run": bool(args.dry_run),
        "max_concepts": "" if args.max_concepts is None else int(args.max_concepts),
        "purity_rules": str(args.purity_rules),
        "stock_overrides": str(args.stock_overrides),
        "price_cache_dir": str(args.price_cache_dir),
        "business_profile": str(args.business_profile),
    }


def _write_universe_report(
    path: Path,
    *,
    selected: pd.DataFrame,
    constituents: pd.DataFrame,
    universe: pd.DataFrame,
    failures: pd.DataFrame,
    metadata: dict[str, object],
    cache_status: dict[str, str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Theme Stock Universe Report",
        "",
        "This worksheet is a reviewed concept taxonomy, not a stock recommendation list.",
        "Concept constituents are noisy current snapshots and are not pure AI or commercial-space stocks.",
        "concept_exposure_score measures concept-board exposure, not confirmed stock relevance.",
        "theme_relevance_score is currently an alias for concept_exposure_score and remains a future field.",
        "",
        "## Run Metadata",
    ]
    lines.extend(f"- {key}={value}" for key, value in metadata.items())
    lines.extend(
        [
            "",
            "## Summary",
            f"- selected_concepts={len(selected)}",
            f"- constituent_rows={len(constituents)}",
            f"- universe_rows={len(universe)}",
            f"- failures={len(failures)}",
        ]
    )
    if not universe.empty:
        lines.append("")
        lines.append("## Universe Inclusion Counts")
        for status, count in universe["universe_inclusion_status"].value_counts().sort_index().items():
            lines.append(f"- {status}={count}")
    if cache_status:
        lines.append("")
        lines.append("## Constituent Cache Status")
        for concept, status in sorted(cache_status.items()):
            lines.append(f"- {concept}={status}")
    if not failures.empty:
        lines.append("")
        lines.append("## Fetch Failures")
        for _, row in failures.iterrows():
            lines.append(
                "- "
                f"concept={row.get('matched_akshare_concept', '')}; "
                f"error_type={row.get('error_type', '')}; "
                f"error={row.get('error', '')}"
            )
    lines.extend(
        [
            "",
            "## TradingAgents-Inspired Workflow Boundary",
            "- Theme Curator: validates concept taxonomy and stock-theme exposure.",
            "- Event Analyst: future news and announcement extraction.",
            "- Technical Analyst: future mid-frequency price and volume factors.",
            "- Fundamental Analyst: future financial quality checks.",
            "- Bear Researcher: future impurity, hype, liquidity, and overheat flags.",
            "- Risk Manager: future liquidity, concentration, suspension, limit, and drawdown constraints.",
            "",
            "## Caveats",
            "- P0/P1/P2 and include_default control universe construction.",
            "- Outputs are research universe inputs for later testing, not alpha proof.",
            "- No buy/sell recommendations are generated by this report.",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_purity_report(
    path: Path,
    *,
    diagnostics: pd.DataFrame,
    review_queue: pd.DataFrame,
    metadata: dict[str, object],
    purity_rules_path: Path,
    stock_overrides_path: Path,
    price_cache_dir: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    freshness = _freshness_summary(diagnostics)
    lines = [
        "# Theme Stock Purity Report",
        "",
        "theme_concept_constituents.csv is a noisy concept-board snapshot.",
        "Generated constituent rows should not be manually deleted.",
        "Concept exposure is not confirmed business purity.",
        "Broad concepts naturally include loose or surprising constituents.",
        "Manual stock decisions belong in config/theme_stock_overrides.csv.",
        "Review should prioritize high-impact uncertain names, not every constituent.",
        "11-day-old concept data is acceptable for pipeline testing and review queue construction.",
        "11-day-old price data is not acceptable for final mid-frequency trading readiness or live candidate selection.",
        "Before any theme factor, backtest, or live-screening step, refresh concept constituents and price cache.",
        "Outputs remain research-universe inputs, not buy/sell recommendations or alpha proof.",
        "",
        "## Run Metadata",
    ]
    lines.extend(f"- {key}={value}" for key, value in metadata.items())
    if "purity_rules" not in metadata:
        lines.append(f"- purity_rules={purity_rules_path}")
    if "stock_overrides" not in metadata:
        lines.append(f"- stock_overrides={stock_overrides_path}")
    if "price_cache_dir" not in metadata:
        lines.append(f"- price_cache_dir={price_cache_dir}")
    for key, value in freshness.items():
        lines.append(f"- {key}={value}")
    lines.extend(
        [
            "",
            "## Summary",
            f"- diagnostics_rows={len(diagnostics)}",
            f"- review_queue_rows={len(review_queue)}",
        ]
    )
    if not diagnostics.empty:
        lines.append("")
        lines.append("## Purity Buckets")
        for bucket, count in diagnostics["concept_purity_bucket"].value_counts().sort_index().items():
            lines.append(f"- {bucket}={count}")
        lines.append("")
        lines.append("## Encoding Diagnostics")
        lines.append(f"- mojibake_rows={int(diagnostics['mojibake_flag'].astype(bool).sum())}")
    if not review_queue.empty:
        lines.append("")
        lines.append("## Top Review Queue")
        for _, row in review_queue.head(20).iterrows():
            lines.append(
                "- "
                f"code={row.get('code', '')}; "
                f"name={row.get('name', '')}; "
                f"theme={row.get('theme', '')}; "
                f"bucket={row.get('concept_purity_bucket', '')}; "
                f"priority={row.get('review_priority', '')}; "
                f"reason={row.get('reason_for_review', '')}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _write_business_materiality_report(
    path: Path,
    *,
    materiality: pd.DataFrame,
    mismatch_queue: pd.DataFrame,
    profile_template: pd.DataFrame,
    metadata: dict[str, object],
    business_profile_path: Path,
    materiality_output: Path,
    mismatch_output: Path,
    profile_template_output: Path,
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Theme Business Materiality Report",
        "",
        "Concept board support is not business materiality.",
        "High-confidence concept support can still be a false positive.",
        "Transition stories are not core exposure unless revenue, order, or product evidence is available.",
        "Manual profile evidence should preferably come from annual reports, interim reports, announcements, exchange replies, or investor relations records.",
        "Cases such as 亿田智能 should be handled through stock_business_profile.csv or theme_stock_overrides.csv.",
        "Outputs are review aids, not recommendations or trading signals.",
        "",
        "## Run Metadata",
    ]
    lines.extend(f"- {key}={value}" for key, value in metadata.items())
    if "business_profile" not in metadata:
        lines.append(f"- business_profile={business_profile_path}")
    lines.extend(
        [
            f"- business_materiality_output={materiality_output}",
            f"- high_confidence_mismatch_output={mismatch_output}",
            f"- business_profile_template={profile_template_output}",
            "",
            "## Summary",
            f"- materiality_rows={len(materiality)}",
            f"- high_confidence_mismatch_rows={len(mismatch_queue)}",
            f"- profile_template_rows={len(profile_template)}",
        ]
    )
    if not materiality.empty:
        lines.append("")
        lines.append("## Final Review Suggestions")
        for suggestion, count in materiality["final_review_suggestion"].value_counts().sort_index().items():
            lines.append(f"- {suggestion}={count}")
        lines.append("")
        lines.append("## Review Status Counts")
        for status, count in materiality["review_status"].value_counts().sort_index().items():
            lines.append(f"- {status}={count}")
        lines.append("")
        lines.append("## Theme Revenue Materiality Buckets")
        for bucket, count in materiality["theme_revenue_materiality_bucket"].value_counts().sort_index().items():
            lines.append(f"- {bucket}={count}")
    if not mismatch_queue.empty:
        lines.append("")
        lines.append("## High-Confidence Business Mismatch Queue")
        for _, row in mismatch_queue.head(20).iterrows():
            lines.append(
                "- "
                f"code={row.get('code', '')}; "
                f"name={row.get('name', '')}; "
                f"theme={row.get('theme', '')}; "
                f"suggestion={row.get('final_review_suggestion', '')}; "
                f"reason={row.get('reason_for_review', '')}"
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _freshness_summary(diagnostics: pd.DataFrame) -> dict[str, object]:
    if diagnostics.empty:
        return {
            "concept_constituents_asof": "",
            "price_cache_asof": "",
            "price_cache_staleness_days": "",
            "concept_cache_staleness_days": "",
        }
    first = diagnostics.iloc[0]
    return {
        "concept_constituents_asof": first.get("concept_constituents_asof", ""),
        "price_cache_asof": first.get("price_cache_asof", ""),
        "price_cache_staleness_days": first.get("price_cache_staleness_days", ""),
        "concept_cache_staleness_days": first.get("concept_cache_staleness_days", ""),
    }


def _default_profile_template_output(output_universe: Path) -> Path:
    default_universe = ROOT / "data" / "processed" / "theme_stock_universe.csv"
    try:
        if output_universe.resolve() == default_universe.resolve():
            return ROOT / "data" / "manual" / "stock_business_profile_template.csv"
    except OSError:
        pass
    return output_universe.parent / "stock_business_profile_template.csv"


def _parse_csv_arg(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _safe_name(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9_\-\u4e00-\u9fff]+", "_", value.strip())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "concept"


if __name__ == "__main__":
    raise SystemExit(main())
