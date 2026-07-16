from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from difflib import SequenceMatcher, get_close_matches
from pathlib import Path
from typing import Any, Callable

import pandas as pd

REQUIRED_MAPPING_COLUMNS = [
    "theme",
    "source_priority",
    "source_id",
    "source_title",
    "source_type",
    "source_org",
    "source_date",
    "source_url",
    "official_or_market_term",
    "industry_chain_layer",
    "possible_akshare_concept",
    "ring",
    "include_default",
    "evidence_summary",
    "risk_note",
    "input_reason",
    "akshare_next_step",
]
OVERRIDE_COLUMNS = [
    "theme",
    "possible_akshare_concept",
    "override_action",
    "matched_akshare_concept",
    "matched_akshare_code",
    "override_reason",
]
STOCK_OVERRIDE_COLUMNS = [
    "code",
    "name",
    "theme",
    "override_status",
    "reason",
    "reviewer",
    "review_date",
]
BUSINESS_PROFILE_COLUMNS = [
    "code",
    "name",
    "theme",
    "primary_business",
    "revenue_segments",
    "sw_industry",
    "theme_business_description",
    "theme_revenue_materiality",
    "theme_revenue_ratio",
    "theme_revenue_amount",
    "evidence_level",
    "evidence_source",
    "evidence_url",
    "evidence_date",
    "evidence_summary",
    "reviewer",
    "review_status",
]
VALID_STOCK_OVERRIDE_STATUS = {"accept", "conditional", "reject", "watchlist"}
VALID_BUSINESS_REVIEW_STATUS = {"core", "conditional", "watchlist", "reject", "unknown"}
VALID_EVIDENCE_LEVELS = {
    "official_report",
    "official_announcement",
    "investor_relations",
    "exchange_inquiry_reply",
    "company_website",
    "f10_summary",
    "media_report",
    "broker_report",
    "unknown",
}
VALID_RINGS = {"P0", "P1", "P2"}
VALID_INCLUDE_DEFAULT = {"yes", "conditional", "no"}
VALID_CONFIRMED_MATCH_STATUS = {"exact", "manual_confirmed"}
SOURCE_RELIABILITY_WEIGHTS = {
    "official_policy": 1.25,
    "official_standard": 1.25,
    "local_official_policy": 1.15,
    "industry_whitepaper": 1.0,
    "technical_whitepaper": 0.9,
    "annual_report": 0.85,
    "broker_industry_report": 0.75,
}
UNKNOWN_SOURCE_WEIGHT = 0.7
RING_WEIGHTS = {"P0": 3.0, "P1": 1.5, "P2": 0.5}
DEFAULT_VALIDATION_COLUMNS = [
    "mapping_row_id",
    "theme",
    "possible_akshare_concept",
    "match_status",
    "matched_akshare_concept",
    "matched_akshare_code",
    "match_score",
    "fuzzy_candidates",
    "ring",
    "include_default",
    "source_id",
    "source_url",
    "evidence_summary",
    "risk_note",
    "input_reason",
    "action_required",
    "generated_at",
    "input_file",
    "refresh",
    "akshare_cache_status",
]
CONSTITUENT_COLUMNS = [
    "raw_code",
    "code",
    "name",
    "theme",
    "matched_akshare_concept",
    "original_possible_concept",
    "ring",
    "include_default",
    "industry_chain_layer",
    "source_id",
    "source_url",
    "concept_source_weight",
    "evidence_summary",
    "risk_note",
]
UNIVERSE_COLUMNS = [
    "raw_code",
    "code",
    "name",
    "theme",
    "concept_exposure_score",
    "theme_relevance_score",
    "matched_concept_count",
    "p0_concept_count",
    "p1_concept_count",
    "p2_concept_count",
    "supporting_concepts",
    "supporting_source_ids",
    "supporting_industry_chain_layers",
    "strongest_evidence_summary",
    "main_risk_note",
    "universe_inclusion_status",
    "verification_status",
]
PURITY_DIAGNOSTIC_COLUMNS = [
    "raw_code",
    "code",
    "name",
    "theme",
    "concept_exposure_score",
    "theme_relevance_score",
    "matched_concept_count",
    "p0_concept_count",
    "p1_concept_count",
    "p2_concept_count",
    "supporting_concepts",
    "supporting_source_ids",
    "supporting_industry_chain_layers",
    "strongest_evidence_summary",
    "main_risk_note",
    "broad_concept_only",
    "multi_concept_support",
    "specific_concept_support",
    "concept_purity_bucket",
    "mojibake_flag",
    "mojibake_field_count",
    "encoding_warning",
    "override_status",
    "override_reason",
    "reviewer",
    "review_date",
    "amount_20d",
    "volatility_20d",
    "high",
    "low",
    "amount",
    "total_market_cap",
    "circulating_market_cap",
    "liquidity_pass",
    "tradability_pass",
    "overheat_flag",
    "st_flag",
    "midfreq_ready",
    "generated_at",
    "concept_constituents_asof",
    "price_cache_asof",
    "price_cache_staleness_days",
    "concept_cache_staleness_days",
]
REVIEW_QUEUE_COLUMNS = [
    "code",
    "name",
    "theme",
    "concept_purity_bucket",
    "review_priority",
    "reason_for_review",
    "supporting_concepts",
    "concept_exposure_score",
    "suggested_action",
]
BUSINESS_MATERIALITY_COLUMNS = [
    "raw_code",
    "code",
    "name",
    "theme",
    "concept_purity_bucket",
    "concept_exposure_score",
    "matched_concept_count",
    "supporting_concepts",
    "supporting_source_ids",
    "override_status",
    "override_reason",
    "business_profile_available",
    "primary_business",
    "revenue_segments",
    "sw_industry",
    "theme_business_description",
    "theme_revenue_materiality",
    "theme_revenue_materiality_bucket",
    "theme_revenue_ratio",
    "theme_revenue_amount",
    "evidence_level",
    "evidence_source",
    "evidence_url",
    "evidence_date",
    "evidence_summary",
    "reviewer",
    "review_status",
    "primary_business_match",
    "theme_business_disclosed",
    "business_mismatch_flag",
    "transition_story_flag",
    "concept_only_flag",
    "final_review_suggestion",
    "business_materiality_warning",
    "generated_at",
]
HIGH_CONFIDENCE_MISMATCH_COLUMNS = [
    "code",
    "name",
    "theme",
    "concept_purity_bucket",
    "concept_exposure_score",
    "matched_concept_count",
    "supporting_concepts",
    "business_mismatch_flag",
    "transition_story_flag",
    "concept_only_flag",
    "final_review_suggestion",
    "reason_for_review",
]
BUSINESS_PROFILE_TEMPLATE_COLUMNS = BUSINESS_PROFILE_COLUMNS + [
    "concept_purity_bucket",
    "supporting_concepts",
    "concept_exposure_score",
    "reason_for_review",
    "suggested_initial_review_status",
]
DEFAULT_PURITY_RULES: dict[str, Any] = {
    "broad_concepts": {
        "AI": ["人工智能", "AIGC概念", "AIGC", "浜哄伐鏅鸿兘", "AIGC����"],
        "商业航天": ["商业航天", "鍟嗕笟鑸ぉ"],
    },
    "specific_concepts": {
        "AI": [
            "AI智能体",
            "算力概念",
            "算力租赁",
            "数据中心",
            "大模型",
            "DeepSeek概念",
            "绠楀姏绉熻祦",
            "��������",
        ],
        "商业航天": ["卫星互联网", "北斗导航", "通用航空", "航天装备", "鍖楁枟瀵艰埅"],
    },
    "weak_concept_patterns": ["概念", "姒傚康"],
    "thresholds": {
        "low_exposure_score": 3.0,
        "liquidity_amount_20d": 50_000_000,
        "overheat_return_20d": 0.5,
        "fresh_price_max_days": 3,
    },
}
MOJIBAKE_PATTERN = re.compile(r"(�|锟|浜|绠|姒|鏅|熻|鑸|鍟|浠|鍚|璇|跺|垮|潡|伐|兘|纭|畻)")


@dataclass(frozen=True)
class ConceptValidationResult:
    resolved: pd.DataFrame
    failures: pd.DataFrame


@dataclass(frozen=True)
class ThemeUniverseResult:
    constituents: pd.DataFrame
    universe: pd.DataFrame


def load_concept_mapping(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def validate_concept_mapping_schema(df: pd.DataFrame) -> list[dict[str, object]]:
    missing = sorted(set(REQUIRED_MAPPING_COLUMNS) - set(df.columns))
    return [
        {
            "row": "",
            "warning_type": "missing_required_columns",
            "details": ",".join(missing),
        }
    ] if missing else []


def clean_concept_mapping(
    df: pd.DataFrame,
    *,
    input_file: str,
    generated_at: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    schema_warnings = validate_concept_mapping_schema(df)
    if schema_warnings:
        raise ValueError(f"mapping missing required columns: {schema_warnings[0]['details']}")

    clean = df.copy()
    for column in REQUIRED_MAPPING_COLUMNS:
        clean[column] = clean[column].map(_clean_text)

    clean["mapping_row_id"] = range(1, len(clean) + 1)
    clean["theme"] = clean["theme"].map(_normalize_theme)
    clean["ring"] = clean["ring"].str.upper()
    clean["include_default"] = clean["include_default"].str.lower()
    clean["source_date"] = clean["source_date"].map(_normalize_date)
    clean["generated_at"] = generated_at
    clean["input_file"] = input_file

    row_warnings: list[dict[str, object]] = []
    validation_warning_values: list[str] = []
    for _, row in clean.iterrows():
        warnings: list[str] = []
        if row["ring"] not in VALID_RINGS:
            warnings.append("invalid_ring")
        if row["include_default"] not in VALID_INCLUDE_DEFAULT:
            warnings.append("invalid_include_default")
        validation_warning_values.append("|".join(warnings))
        for warning in warnings:
            row_warnings.append(
                {
                    "mapping_row_id": int(row["mapping_row_id"]),
                    "warning_type": warning,
                    "details": str(row["possible_akshare_concept"]),
                }
            )

    clean["validation_warning"] = validation_warning_values
    leading = ["mapping_row_id"]
    trailing = ["generated_at", "input_file", "validation_warning"]
    ordered = leading + REQUIRED_MAPPING_COLUMNS + trailing
    return clean[ordered], pd.DataFrame(row_warnings)


def validate_akshare_concepts(
    mapping: pd.DataFrame,
    concept_names: pd.DataFrame,
    *,
    generated_at: str,
    input_file: str,
    refresh: bool,
    akshare_cache_status: str,
    top_n: int = 5,
    fuzzy_cutoff: float = 0.65,
) -> ConceptValidationResult:
    records = _concept_records(concept_names)
    by_name = {record["concept_name"]: record for record in records}
    names = [record["concept_name"] for record in records]

    rows: list[dict[str, object]] = []
    for _, item in mapping.iterrows():
        output = item.to_dict()
        output.update(
            {
                "match_status": "",
                "matched_akshare_concept": "",
                "matched_akshare_code": "",
                "match_score": 0.0,
                "fuzzy_candidates": "",
                "action_required": "",
                "refresh": bool(refresh),
                "akshare_cache_status": akshare_cache_status,
                "generated_at": generated_at,
                "input_file": input_file,
            }
        )

        if _has_invalid_input(item):
            output.update(
                {
                    "match_status": "invalid_input",
                    "action_required": "fix_invalid_input",
                }
            )
            rows.append(output)
            continue

        requested = _clean_text(item.get("possible_akshare_concept", ""))
        exact = by_name.get(requested)
        if exact is not None:
            output.update(
                {
                    "match_status": "exact",
                    "matched_akshare_concept": exact["concept_name"],
                    "matched_akshare_code": exact["concept_code"],
                    "match_score": 1.0,
                    "action_required": "none",
                }
            )
            rows.append(output)
            continue

        candidates = fuzzy_concept_candidates(requested, names, top_n=top_n, fuzzy_cutoff=fuzzy_cutoff)
        if candidates:
            output.update(
                {
                    "match_status": "fuzzy_candidate",
                    "match_score": candidates[0][1],
                    "fuzzy_candidates": "|".join(f"{name}:{score:.4f}" for name, score in candidates),
                    "action_required": "review_fuzzy_candidates",
                }
            )
        else:
            output.update(
                {
                    "match_status": "not_found",
                    "action_required": "manual_research_required",
                }
            )
        rows.append(output)

    resolved = pd.DataFrame(rows)
    for column in DEFAULT_VALIDATION_COLUMNS:
        if column not in resolved.columns:
            resolved[column] = ""
    return ConceptValidationResult(
        resolved=resolved,
        failures=pd.DataFrame(columns=["stage", "concept_name", "error_type", "error"]),
    )


def fuzzy_concept_candidates(
    requested: str,
    concept_names: list[str],
    *,
    top_n: int,
    fuzzy_cutoff: float,
) -> list[tuple[str, float]]:
    requested_norm = _normalize_match_text(requested)
    scores: dict[str, float] = {}
    for name in concept_names:
        name_norm = _normalize_match_text(name)
        score = SequenceMatcher(None, requested_norm, name_norm).ratio()
        if requested_norm and requested_norm in name_norm:
            score = max(score, 0.8)
        if _strip_suffix(requested_norm) and _strip_suffix(requested_norm) in name_norm:
            score = max(score, 0.72)
        if score >= fuzzy_cutoff:
            scores[name] = max(scores.get(name, 0.0), score)

    for normalized in get_close_matches(
        requested_norm,
        [_normalize_match_text(name) for name in concept_names],
        n=top_n * 2,
        cutoff=fuzzy_cutoff,
    ):
        for name in concept_names:
            if _normalize_match_text(name) == normalized:
                scores[name] = max(scores.get(name, 0.0), SequenceMatcher(None, requested_norm, normalized).ratio())

    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))[:top_n]


def load_manual_overrides(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=OVERRIDE_COLUMNS)
    overrides = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = sorted(set(OVERRIDE_COLUMNS) - set(overrides.columns))
    if missing:
        raise ValueError(f"manual overrides missing required columns: {missing}")
    for column in OVERRIDE_COLUMNS:
        overrides[column] = overrides[column].map(_clean_text)
    overrides["theme"] = overrides["theme"].map(_normalize_theme)
    overrides["override_action"] = overrides["override_action"].str.lower()
    invalid = sorted(set(overrides["override_action"]) - {"confirm", "reject"})
    if invalid:
        raise ValueError(f"invalid override_action values: {invalid}")
    return overrides[OVERRIDE_COLUMNS]


def load_stock_overrides(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=STOCK_OVERRIDE_COLUMNS)
    overrides = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = sorted(set(STOCK_OVERRIDE_COLUMNS) - set(overrides.columns))
    if missing:
        raise ValueError(f"stock overrides missing required columns: {missing}")
    for column in STOCK_OVERRIDE_COLUMNS:
        overrides[column] = overrides[column].map(_clean_text)
    overrides["code"] = overrides["code"].map(normalize_stock_code)
    overrides["theme"] = overrides["theme"].map(_normalize_theme)
    overrides["override_status"] = overrides["override_status"].str.lower()
    invalid = sorted(set(overrides["override_status"]) - VALID_STOCK_OVERRIDE_STATUS)
    if invalid:
        raise ValueError(f"invalid override_status values: {invalid}")
    return overrides[STOCK_OVERRIDE_COLUMNS]


def load_stock_business_profiles(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame(columns=BUSINESS_PROFILE_COLUMNS)
    profiles = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    missing = sorted(set(BUSINESS_PROFILE_COLUMNS) - set(profiles.columns))
    if missing:
        raise ValueError(f"stock business profiles missing required columns: {missing}")
    for column in BUSINESS_PROFILE_COLUMNS:
        profiles[column] = profiles[column].map(_clean_text)
    profiles["code"] = profiles["code"].map(normalize_stock_code)
    profiles["theme"] = profiles["theme"].map(_normalize_theme)
    profiles["review_status"] = profiles["review_status"].str.lower().replace("", "unknown")
    profiles["evidence_level"] = profiles["evidence_level"].str.lower().replace("", "unknown")
    invalid_status = sorted(set(profiles["review_status"]) - VALID_BUSINESS_REVIEW_STATUS)
    if invalid_status:
        raise ValueError(f"invalid review_status values: {invalid_status}")
    invalid_evidence = sorted(set(profiles["evidence_level"]) - VALID_EVIDENCE_LEVELS)
    if invalid_evidence:
        raise ValueError(f"invalid evidence_level values: {invalid_evidence}")
    return profiles[BUSINESS_PROFILE_COLUMNS]


def load_purity_rules(path: Path) -> dict[str, Any]:
    rules = _deep_copy_rules(DEFAULT_PURITY_RULES)
    if not path.exists():
        return rules
    with path.open("r", encoding="utf-8-sig") as handle:
        configured = json.load(handle)
    return _merge_purity_rules(rules, configured)


def apply_manual_overrides(validation: pd.DataFrame, overrides: pd.DataFrame) -> pd.DataFrame:
    if overrides.empty:
        result = validation.copy()
        if "manual_override_reason" not in result.columns:
            result["manual_override_reason"] = ""
        return result

    result = validation.copy()
    result["manual_override_reason"] = ""
    lookup = {
        (_normalize_theme(row["theme"]), _clean_text(row["possible_akshare_concept"])): row
        for _, row in overrides.iterrows()
    }
    for idx, row in result.iterrows():
        key = (_normalize_theme(row["theme"]), _clean_text(row["possible_akshare_concept"]))
        override = lookup.get(key)
        if override is None:
            continue
        if override["override_action"] == "confirm":
            result.loc[idx, "match_status"] = "manual_confirmed"
            result.loc[idx, "matched_akshare_concept"] = override["matched_akshare_concept"]
            result.loc[idx, "matched_akshare_code"] = override["matched_akshare_code"]
            result.loc[idx, "match_score"] = 1.0
            result.loc[idx, "action_required"] = "manual_override_confirmed"
        else:
            result.loc[idx, "match_status"] = "manual_rejected"
            result.loc[idx, "matched_akshare_concept"] = ""
            result.loc[idx, "matched_akshare_code"] = ""
            result.loc[idx, "match_score"] = 0.0
            result.loc[idx, "action_required"] = "manual_override_rejected"
        result.loc[idx, "manual_override_reason"] = override["override_reason"]
    return result


def select_validated_concepts(
    validation: pd.DataFrame,
    *,
    themes: list[str] | None = None,
    rings: list[str] | None = None,
    default_only: bool = True,
    include_conditional: bool = False,
    include_p2: bool = False,
    include_excluded_for_audit: bool = False,
    max_concepts: int | None = None,
) -> pd.DataFrame:
    if validation.empty:
        return validation.copy()
    selected = validation.copy()
    selected = selected[selected["match_status"].isin(VALID_CONFIRMED_MATCH_STATUS)].copy()
    if themes:
        normalized_themes = {_normalize_theme(theme) for theme in themes}
        selected = selected[selected["theme"].map(_normalize_theme).isin(normalized_themes)]
    if rings:
        allowed_rings = {ring.upper() for ring in rings}
        selected = selected[selected["ring"].astype(str).str.upper().isin(allowed_rings)]
    elif not include_p2:
        selected = selected[selected["ring"] != "P2"]

    include_values = {"yes"}
    if include_conditional:
        include_values.add("conditional")
    if include_excluded_for_audit:
        include_values.add("no")
    selected = selected[selected["include_default"].isin(include_values)]

    if default_only:
        selected = selected[(selected["ring"] == "P0") & (selected["include_default"].isin(include_values))]

    selected = selected.sort_values(
        ["theme", "ring", "include_default", "matched_akshare_concept", "source_id"],
        kind="mergesort",
    ).reset_index(drop=True)
    if max_concepts is not None:
        selected = selected.head(max_concepts).copy()
    return selected


def build_constituent_table(
    selected_concepts: pd.DataFrame,
    *,
    fetch_members: Callable[[str], pd.DataFrame],
    generated_at: str,
    run_metadata: dict[str, object],
    dry_run: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metadata = _metadata_columns(run_metadata, generated_at)
    if dry_run or selected_concepts.empty:
        return (
            pd.DataFrame(columns=CONSTITUENT_COLUMNS + list(metadata)),
            pd.DataFrame(columns=["stage", "matched_akshare_concept", "error_type", "error"]),
        )

    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for _, concept in selected_concepts.iterrows():
        concept_name = str(concept["matched_akshare_concept"])
        try:
            members = fetch_members(concept_name)
        except Exception as exc:  # noqa: BLE001 - row-level data failures are reported.
            failures.append(
                {
                    "stage": "concept_constituents",
                    "matched_akshare_concept": concept_name,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            continue

        code_col = _first_existing_column(members, ["raw_code", "code", "symbol", "代码", "证券代码"])
        name_col = _first_existing_column(members, ["name", "名称", "证券简称"])
        if code_col is None:
            failures.append(
                {
                    "stage": "concept_constituents",
                    "matched_akshare_concept": concept_name,
                    "error_type": "DataQualityError",
                    "error": f"Cannot identify stock code column: {list(members.columns)}",
                }
            )
            continue
        for _, member in members.iterrows():
            raw_code = _clean_text(member.get(code_col, ""))
            row = {
                "raw_code": raw_code,
                "code": normalize_stock_code(raw_code),
                "name": _clean_text(member.get(name_col, "")) if name_col else "",
                "theme": concept.get("theme", ""),
                "matched_akshare_concept": concept_name,
                "original_possible_concept": concept.get("possible_akshare_concept", ""),
                "ring": concept.get("ring", ""),
                "include_default": concept.get("include_default", ""),
                "industry_chain_layer": concept.get("industry_chain_layer", ""),
                "source_id": concept.get("source_id", ""),
                "source_url": concept.get("source_url", ""),
                "concept_source_weight": concept_source_weight(concept),
                "evidence_summary": concept.get("evidence_summary", ""),
                "risk_note": concept.get("risk_note", ""),
            }
            row.update(metadata)
            rows.append(row)
    constituents = pd.DataFrame(rows)
    for column in CONSTITUENT_COLUMNS + list(metadata):
        if column not in constituents.columns:
            constituents[column] = ""
    return constituents[CONSTITUENT_COLUMNS + list(metadata)], pd.DataFrame(failures)


def build_theme_stock_universe(
    constituents: pd.DataFrame,
    *,
    generated_at: str,
    run_metadata: dict[str, object],
) -> pd.DataFrame:
    metadata = _metadata_columns(run_metadata, generated_at)
    if constituents.empty:
        return pd.DataFrame(columns=UNIVERSE_COLUMNS + list(metadata))

    deduped = constituents.drop_duplicates(
        ["theme", "code", "source_id", "matched_akshare_concept"],
        keep="first",
    ).copy()
    rows: list[dict[str, object]] = []
    for (theme, code), group in deduped.groupby(["theme", "code"], sort=True):
        concepts = sorted(group["matched_akshare_concept"].dropna().astype(str).unique())
        source_ids = sorted(group["source_id"].dropna().astype(str).unique())
        layers = sorted(layer for layer in group["industry_chain_layer"].dropna().astype(str).unique() if layer)
        weight_sum = float(pd.to_numeric(group["concept_source_weight"], errors="coerce").fillna(0.0).sum())
        breadth_bonus = min(1.0, 0.25 * max(len(source_ids) - 1, 0))
        score = round(weight_sum + breadth_bonus, 4)
        p0_count = _concept_count_by_ring(group, "P0")
        p1_count = _concept_count_by_ring(group, "P1")
        p2_count = _concept_count_by_ring(group, "P2")
        has_default = ((group["ring"] == "P0") & (group["include_default"] == "yes")).any()
        has_excluded_only = (group["include_default"] == "no").all()
        status = "default" if has_default else "excluded" if has_excluded_only else "conditional"
        verification = "concept_matched" if status == "default" else "needs_review" if status == "conditional" else "rejected"
        strongest = group.sort_values(["concept_source_weight", "source_id"], ascending=[False, True]).iloc[0]
        row = {
            "raw_code": "|".join(sorted(group["raw_code"].dropna().astype(str).unique())),
            "code": code,
            "name": str(strongest.get("name", "")),
            "theme": theme,
            "concept_exposure_score": score,
            "theme_relevance_score": score,
            "matched_concept_count": len(concepts),
            "p0_concept_count": p0_count,
            "p1_concept_count": p1_count,
            "p2_concept_count": p2_count,
            "supporting_concepts": "|".join(concepts),
            "supporting_source_ids": "|".join(source_ids),
            "supporting_industry_chain_layers": "|".join(layers),
            "strongest_evidence_summary": str(strongest.get("evidence_summary", "")),
            "main_risk_note": str(strongest.get("risk_note", "")),
            "universe_inclusion_status": status,
            "verification_status": verification,
        }
        row.update(metadata)
        rows.append(row)

    universe = pd.DataFrame(rows)
    return universe[UNIVERSE_COLUMNS + list(metadata)]


def build_theme_stock_purity_diagnostics(
    universe: pd.DataFrame,
    constituents: pd.DataFrame,
    *,
    purity_rules: dict[str, Any],
    stock_overrides: pd.DataFrame,
    generated_at: str,
    run_metadata: dict[str, object],
    price_cache_dir: Path | None = None,
) -> pd.DataFrame:
    metadata = _freshness_metadata(
        constituents,
        generated_at=generated_at,
        price_cache_dir=price_cache_dir,
        codes=universe["code"].tolist() if "code" in universe else [],
    )
    if universe.empty:
        return pd.DataFrame(columns=PURITY_DIAGNOSTIC_COLUMNS + _extra_metadata_columns(run_metadata))

    deduped = constituents.drop_duplicates(
        ["theme", "code", "source_id", "matched_akshare_concept"],
        keep="first",
    ).copy()
    override_lookup = _stock_override_lookup(stock_overrides)
    rows: list[dict[str, object]] = []
    for _, stock in universe.iterrows():
        theme = _normalize_theme(stock.get("theme", ""))
        code = normalize_stock_code(stock.get("code", ""))
        group = deduped[(deduped["theme"].map(_normalize_theme) == theme) & (deduped["code"].map(normalize_stock_code) == code)]
        concepts = _split_pipe(stock.get("supporting_concepts", ""))
        source_ids = _split_pipe(stock.get("supporting_source_ids", ""))
        if not concepts and not group.empty:
            concepts = sorted(group["matched_akshare_concept"].dropna().astype(str).unique())
        if not source_ids and not group.empty:
            source_ids = sorted(group["source_id"].dropna().astype(str).unique())

        broad_support = [_concept for _concept in concepts if _matches_configured_concept(_concept, theme, purity_rules, "broad_concepts")]
        specific_support = [
            _concept for _concept in concepts if _matches_configured_concept(_concept, theme, purity_rules, "specific_concepts")
        ]
        broad_only = bool(concepts) and bool(broad_support) and not specific_support and len(broad_support) == len(concepts)
        multi_concept = len(set(concepts)) > 1
        score = float(pd.to_numeric(pd.Series([stock.get("concept_exposure_score", 0)]), errors="coerce").fillna(0.0).iloc[0])
        include_default_no_only = (not group.empty) and group["include_default"].astype(str).str.lower().eq("no").all()
        impossible_code_name = not code.isdigit() or len(code) != 6 or not _clean_text(stock.get("name", ""))
        mojibake_count = _mojibake_field_count(stock)
        mojibake_flag = mojibake_count > 0
        override = override_lookup.get((theme, code), {})
        override_status = _clean_text(override.get("override_status", ""))
        p0_count = int(pd.to_numeric(pd.Series([stock.get("p0_concept_count", 0)]), errors="coerce").fillna(0).iloc[0])
        low_exposure = score < float(purity_rules.get("thresholds", {}).get("low_exposure_score", 3.0))
        risk_conflict = _has_conflicting_risk_note(stock.get("main_risk_note", ""))
        bucket = _concept_purity_bucket(
            broad_only=broad_only,
            specific_support=bool(specific_support),
            multi_concept=multi_concept,
            distinct_sources=len(set(source_ids)),
            p0_count=p0_count,
            low_exposure=low_exposure,
            include_default_no_only=include_default_no_only,
            impossible_code_name=impossible_code_name,
            mojibake_flag=mojibake_flag,
            risk_conflict=risk_conflict,
            override_status=override_status,
        )
        price_fields = _price_cache_diagnostics(
            code,
            stock.get("name", ""),
            generated_at=generated_at,
            price_cache_dir=price_cache_dir,
            rules=purity_rules,
        )
        row = stock.to_dict()
        row.update(
            {
                "broad_concept_only": broad_only,
                "multi_concept_support": multi_concept,
                "specific_concept_support": bool(specific_support),
                "concept_purity_bucket": bucket,
                "mojibake_flag": mojibake_flag,
                "mojibake_field_count": mojibake_count,
                "encoding_warning": "possible_mojibake_review_required" if mojibake_flag else "",
                "override_status": override_status,
                "override_reason": _clean_text(override.get("reason", "")),
                "reviewer": _clean_text(override.get("reviewer", "")),
                "review_date": _clean_text(override.get("review_date", "")),
            }
        )
        row.update(price_fields)
        row.update(metadata)
        row.update({key: value for key, value in run_metadata.items() if key not in row})
        rows.append(row)

    diagnostics = pd.DataFrame(rows)
    for column in PURITY_DIAGNOSTIC_COLUMNS + _extra_metadata_columns(run_metadata):
        if column not in diagnostics.columns:
            diagnostics[column] = ""
    return diagnostics[PURITY_DIAGNOSTIC_COLUMNS + _extra_metadata_columns(run_metadata)]


def build_theme_stock_review_queue(diagnostics: pd.DataFrame) -> pd.DataFrame:
    if diagnostics.empty:
        return pd.DataFrame(columns=REVIEW_QUEUE_COLUMNS)
    rows: list[dict[str, object]] = []
    for _, row in diagnostics.iterrows():
        reasons = _review_reasons(row)
        suggested = _suggested_review_action(row)
        priority = _review_priority(row, reasons)
        rows.append(
            {
                "code": row.get("code", ""),
                "name": row.get("name", ""),
                "theme": row.get("theme", ""),
                "concept_purity_bucket": row.get("concept_purity_bucket", ""),
                "review_priority": priority,
                "reason_for_review": "|".join(reasons) if reasons else "no_immediate_review_flag",
                "supporting_concepts": row.get("supporting_concepts", ""),
                "concept_exposure_score": row.get("concept_exposure_score", ""),
                "suggested_action": suggested,
            }
        )
    queue = pd.DataFrame(rows)
    return queue.sort_values(["review_priority", "concept_exposure_score", "code"], ascending=[True, True, True]).reset_index(
        drop=True
    )[REVIEW_QUEUE_COLUMNS]


def build_business_materiality_diagnostics(
    purity_diagnostics: pd.DataFrame,
    business_profiles: pd.DataFrame,
    *,
    stock_overrides: pd.DataFrame,
    generated_at: str,
    run_metadata: dict[str, object],
) -> pd.DataFrame:
    if purity_diagnostics.empty:
        return pd.DataFrame(columns=BUSINESS_MATERIALITY_COLUMNS + _extra_business_metadata_columns(run_metadata))

    profile_lookup = _business_profile_lookup(business_profiles)
    override_lookup = _stock_override_lookup(stock_overrides)
    rows: list[dict[str, object]] = []
    for _, purity in purity_diagnostics.iterrows():
        code = normalize_stock_code(purity.get("code", ""))
        theme = _normalize_theme(purity.get("theme", ""))
        profile = profile_lookup.get((theme, code), {})
        override = override_lookup.get((theme, code), {})
        profile_available = bool(profile)
        review_status = _clean_text(profile.get("review_status", "unknown")).lower() or "unknown"
        materiality_bucket = _materiality_bucket(profile.get("theme_revenue_materiality", ""))
        theme_disclosed = bool(
            _clean_text(profile.get("theme_business_description", ""))
            or _clean_text(profile.get("evidence_summary", ""))
        )
        primary_match = _primary_business_match(theme, profile) if profile_available else False
        transition_story = _transition_story_flag(materiality_bucket, profile)
        impossible = not code.isdigit() or len(code) != 6 or not _clean_text(purity.get("name", ""))
        mismatch = bool(profile_available and not primary_match and materiality_bucket in {"unknown", "immaterial"})
        concept_support = bool(_clean_text(purity.get("supporting_concepts", "")))
        concept_only = bool(concept_support and (not profile_available or not theme_disclosed or mismatch))
        warning = _business_materiality_warning(profile, materiality_bucket)
        final_suggestion = _final_review_suggestion(
            override_status=_clean_text(override.get("override_status", "")),
            review_status=review_status,
            materiality_bucket=materiality_bucket,
            theme_business_disclosed=theme_disclosed,
            transition_story=transition_story,
            business_mismatch=mismatch,
            profile_available=profile_available,
            impossible_code_name=impossible,
        )
        row = {
            "raw_code": purity.get("raw_code", ""),
            "code": code,
            "name": purity.get("name", ""),
            "theme": theme,
            "concept_purity_bucket": purity.get("concept_purity_bucket", ""),
            "concept_exposure_score": purity.get("concept_exposure_score", ""),
            "matched_concept_count": purity.get("matched_concept_count", ""),
            "supporting_concepts": purity.get("supporting_concepts", ""),
            "supporting_source_ids": purity.get("supporting_source_ids", ""),
            "override_status": _clean_text(override.get("override_status", purity.get("override_status", ""))),
            "override_reason": _clean_text(override.get("reason", purity.get("override_reason", ""))),
            "business_profile_available": profile_available,
            "primary_business": profile.get("primary_business", ""),
            "revenue_segments": profile.get("revenue_segments", ""),
            "sw_industry": profile.get("sw_industry", ""),
            "theme_business_description": profile.get("theme_business_description", ""),
            "theme_revenue_materiality": profile.get("theme_revenue_materiality", ""),
            "theme_revenue_materiality_bucket": materiality_bucket,
            "theme_revenue_ratio": _numeric_or_blank(profile.get("theme_revenue_ratio", "")),
            "theme_revenue_amount": _numeric_or_blank(profile.get("theme_revenue_amount", "")),
            "evidence_level": profile.get("evidence_level", "unknown") if profile_available else "unknown",
            "evidence_source": profile.get("evidence_source", ""),
            "evidence_url": profile.get("evidence_url", ""),
            "evidence_date": _normalize_date(profile.get("evidence_date", "")),
            "evidence_summary": profile.get("evidence_summary", ""),
            "reviewer": profile.get("reviewer", ""),
            "review_status": review_status,
            "primary_business_match": primary_match,
            "theme_business_disclosed": theme_disclosed,
            "business_mismatch_flag": mismatch,
            "transition_story_flag": transition_story,
            "concept_only_flag": concept_only,
            "final_review_suggestion": final_suggestion,
            "business_materiality_warning": warning,
            "generated_at": generated_at,
        }
        row.update({key: value for key, value in run_metadata.items() if key not in row})
        rows.append(row)

    diagnostics = pd.DataFrame(rows)
    for column in BUSINESS_MATERIALITY_COLUMNS + _extra_business_metadata_columns(run_metadata):
        if column not in diagnostics.columns:
            diagnostics[column] = ""
    return diagnostics[BUSINESS_MATERIALITY_COLUMNS + _extra_business_metadata_columns(run_metadata)]


def build_high_confidence_business_mismatch_queue(materiality_diagnostics: pd.DataFrame) -> pd.DataFrame:
    if materiality_diagnostics.empty:
        return pd.DataFrame(columns=HIGH_CONFIDENCE_MISMATCH_COLUMNS)
    rows: list[dict[str, object]] = []
    for _, row in materiality_diagnostics.iterrows():
        reasons = _business_mismatch_reasons(row)
        if not reasons:
            continue
        rows.append(
            {
                "code": row.get("code", ""),
                "name": row.get("name", ""),
                "theme": row.get("theme", ""),
                "concept_purity_bucket": row.get("concept_purity_bucket", ""),
                "concept_exposure_score": row.get("concept_exposure_score", ""),
                "matched_concept_count": row.get("matched_concept_count", ""),
                "supporting_concepts": row.get("supporting_concepts", ""),
                "business_mismatch_flag": row.get("business_mismatch_flag", False),
                "transition_story_flag": row.get("transition_story_flag", False),
                "concept_only_flag": row.get("concept_only_flag", False),
                "final_review_suggestion": row.get("final_review_suggestion", ""),
                "reason_for_review": "|".join(reasons),
            }
        )
    if not rows:
        return pd.DataFrame(columns=HIGH_CONFIDENCE_MISMATCH_COLUMNS)
    queue = pd.DataFrame(rows)
    queue["_priority"] = queue["reason_for_review"].map(_business_queue_priority)
    return queue.sort_values(["_priority", "code"], kind="mergesort").drop(columns=["_priority"]).reset_index(drop=True)[
        HIGH_CONFIDENCE_MISMATCH_COLUMNS
    ]


def build_stock_business_profile_template(
    materiality_diagnostics: pd.DataFrame,
    mismatch_queue: pd.DataFrame,
    *,
    max_rows: int | None = 200,
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    queue_keys = [(row.get("theme", ""), normalize_stock_code(row.get("code", ""))) for _, row in mismatch_queue.iterrows()]
    materiality_lookup = {
        (_normalize_theme(row.get("theme", "")), normalize_stock_code(row.get("code", ""))): row
        for _, row in materiality_diagnostics.iterrows()
    }
    ordered_keys = queue_keys + [
        (_normalize_theme(row.get("theme", "")), normalize_stock_code(row.get("code", "")))
        for _, row in materiality_diagnostics.iterrows()
        if str(row.get("final_review_suggestion", "")) in {"review", "conditional", "watchlist", "reject_candidate"}
    ]
    for theme, code in ordered_keys:
        key = (_normalize_theme(theme), normalize_stock_code(code))
        if key in seen or key not in materiality_lookup:
            continue
        source = materiality_lookup[key]
        seen.add(key)
        rows.append(_business_profile_template_row(source))
        if max_rows is not None and len(rows) >= max_rows:
            break
    template = pd.DataFrame(rows)
    for column in BUSINESS_PROFILE_TEMPLATE_COLUMNS:
        if column not in template.columns:
            template[column] = ""
    return template[BUSINESS_PROFILE_TEMPLATE_COLUMNS]


def normalize_stock_code(value: object) -> str:
    text = _clean_text(value)
    digits = "".join(char for char in text if char.isdigit())
    if not digits:
        return ""
    return digits[-6:].zfill(6)


def concept_source_weight(row: pd.Series | dict[str, object]) -> float:
    include_default = str(row.get("include_default", "")).lower()
    if include_default == "no":
        return 0.0
    ring_weight = RING_WEIGHTS.get(str(row.get("ring", "")).upper(), 0.0)
    source_weight = SOURCE_RELIABILITY_WEIGHTS.get(
        str(row.get("source_type", "")).strip().lower(),
        UNKNOWN_SOURCE_WEIGHT,
    )
    return round(ring_weight * source_weight, 4)


def metadata_for_report(metadata: dict[str, object]) -> list[str]:
    return [f"- {key}={value}" for key, value in metadata.items()]


def _deep_copy_rules(rules: dict[str, Any]) -> dict[str, Any]:
    return json.loads(json.dumps(rules, ensure_ascii=False))


def _merge_purity_rules(defaults: dict[str, Any], configured: dict[str, Any]) -> dict[str, Any]:
    for key, value in configured.items():
        if isinstance(value, dict) and isinstance(defaults.get(key), dict):
            merged = dict(defaults[key])
            merged.update(value)
            defaults[key] = merged
        else:
            defaults[key] = value
    return defaults


def _stock_override_lookup(overrides: pd.DataFrame) -> dict[tuple[str, str], dict[str, object]]:
    if overrides.empty:
        return {}
    return {
        (_normalize_theme(row.get("theme", "")), normalize_stock_code(row.get("code", ""))): row.to_dict()
        for _, row in overrides.iterrows()
    }


def _matches_configured_concept(concept: object, theme: str, rules: dict[str, Any], key: str) -> bool:
    concept_text = _normalize_match_text(concept)
    candidates = list(rules.get(key, {}).get(theme, []))
    if theme != _normalize_theme(theme):
        candidates.extend(rules.get(key, {}).get(_normalize_theme(theme), []))
    for candidate in candidates:
        candidate_text = _normalize_match_text(candidate)
        if candidate_text and (candidate_text == concept_text or candidate_text in concept_text or concept_text in candidate_text):
            return True
    return False


def _split_pipe(value: object) -> list[str]:
    return sorted({item.strip() for item in _clean_text(value).split("|") if item.strip()})


def _mojibake_field_count(row: pd.Series | dict[str, object]) -> int:
    fields = [
        "name",
        "supporting_concepts",
        "supporting_source_ids",
        "supporting_industry_chain_layers",
        "strongest_evidence_summary",
        "main_risk_note",
    ]
    return sum(1 for field in fields if MOJIBAKE_PATTERN.search(_clean_text(row.get(field, ""))))


def _has_conflicting_risk_note(value: object) -> bool:
    text = _clean_text(value).lower()
    return any(token in text for token in ["conflict", "contradict", "不一致", "冲突", "矛盾"])


def _concept_purity_bucket(
    *,
    broad_only: bool,
    specific_support: bool,
    multi_concept: bool,
    distinct_sources: int,
    p0_count: int,
    low_exposure: bool,
    include_default_no_only: bool,
    impossible_code_name: bool,
    mojibake_flag: bool,
    risk_conflict: bool,
    override_status: str,
) -> str:
    if override_status == "reject" or include_default_no_only or impossible_code_name:
        return "exclude_candidate"
    if override_status in {"conditional", "watchlist"} or mojibake_flag or risk_conflict:
        return "needs_manual_review"
    if specific_support and multi_concept and distinct_sources > 1:
        return "high_confidence"
    if broad_only:
        return "broad_concept_only"
    if low_exposure:
        return "needs_manual_review"
    if p0_count >= 1:
        return "medium_confidence"
    return "needs_manual_review"


def _freshness_metadata(
    constituents: pd.DataFrame,
    *,
    generated_at: str,
    price_cache_dir: Path | None,
    codes: list[object],
) -> dict[str, object]:
    run_dt = _parse_datetime(generated_at) or datetime.now(UTC)
    concept_asof = _latest_datetime(constituents["generated_at"]) if "generated_at" in constituents else None
    if concept_asof is None:
        concept_asof = run_dt
    price_asof = _latest_price_cache_datetime(price_cache_dir, codes)
    return {
        "generated_at": generated_at,
        "concept_constituents_asof": _date_string(concept_asof),
        "price_cache_asof": _date_string(price_asof),
        "price_cache_staleness_days": _staleness_days(run_dt, price_asof),
        "concept_cache_staleness_days": _staleness_days(run_dt, concept_asof),
    }


def _price_cache_diagnostics(
    code: str,
    name: object,
    *,
    generated_at: str,
    price_cache_dir: Path | None,
    rules: dict[str, Any],
) -> dict[str, object]:
    empty = {
        "amount_20d": "",
        "volatility_20d": "",
        "high": "",
        "low": "",
        "amount": "",
        "total_market_cap": "",
        "circulating_market_cap": "",
        "liquidity_pass": "",
        "tradability_pass": "",
        "overheat_flag": "",
        "st_flag": _is_st_name(name),
        "midfreq_ready": "",
    }
    if price_cache_dir is None:
        return empty
    path = price_cache_dir / f"{code}.csv"
    if not path.exists():
        return empty
    try:
        price = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except Exception:  # noqa: BLE001 - corrupted local runtime cache should not break concept diagnostics.
        return empty
    if price.empty or "date" not in price:
        return empty
    frame = price.copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date")
    if frame.empty:
        return empty
    for column in ["close", "amount", "high", "low", "total_market_cap", "circulating_market_cap"]:
        if column in frame:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")
    latest = frame.iloc[-1]
    amount_20d = frame["amount"].tail(20).mean() if "amount" in frame else pd.NA
    close = frame["close"] if "close" in frame else pd.Series(dtype=float)
    volatility_20d = close.pct_change(fill_method=None).tail(20).std() if not close.empty else pd.NA
    return_20d = (close.iloc[-1] / close.iloc[-20] - 1.0) if len(close.dropna()) >= 20 and close.iloc[-20] else pd.NA
    liquidity_threshold = float(rules.get("thresholds", {}).get("liquidity_amount_20d", 50_000_000))
    overheat_threshold = float(rules.get("thresholds", {}).get("overheat_return_20d", 0.5))
    liquidity_pass = bool(pd.notna(amount_20d) and float(amount_20d) >= liquidity_threshold)
    high = latest.get("high", pd.NA)
    low = latest.get("low", pd.NA)
    amount = latest.get("amount", pd.NA)
    tradability_pass = bool(pd.notna(amount) and float(amount) > 0 and pd.notna(high) and pd.notna(low) and float(high) != float(low))
    overheat_flag = bool(pd.notna(return_20d) and float(return_20d) > overheat_threshold)
    st_flag = _is_st_name(name)
    return {
        "amount_20d": round(float(amount_20d), 4) if pd.notna(amount_20d) else "",
        "volatility_20d": round(float(volatility_20d), 6) if pd.notna(volatility_20d) else "",
        "high": float(high) if pd.notna(high) else "",
        "low": float(low) if pd.notna(low) else "",
        "amount": float(amount) if pd.notna(amount) else "",
        "total_market_cap": float(latest.get("total_market_cap")) if pd.notna(latest.get("total_market_cap", pd.NA)) else "",
        "circulating_market_cap": float(latest.get("circulating_market_cap"))
        if pd.notna(latest.get("circulating_market_cap", pd.NA))
        else "",
        "liquidity_pass": liquidity_pass,
        "tradability_pass": tradability_pass,
        "overheat_flag": overheat_flag,
        "st_flag": st_flag,
        "midfreq_ready": bool(liquidity_pass and tradability_pass and not overheat_flag and not st_flag),
    }


def _latest_price_cache_datetime(price_cache_dir: Path | None, codes: list[object]) -> datetime | None:
    if price_cache_dir is None or not price_cache_dir.exists():
        return None
    dates: list[datetime] = []
    for raw_code in codes:
        path = price_cache_dir / f"{normalize_stock_code(raw_code)}.csv"
        if not path.exists():
            continue
        try:
            frame = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig", usecols=lambda col: col in {"date", "updated_at"})
        except Exception:  # noqa: BLE001 - unreadable local cache files are reported as missing freshness.
            continue
        for column in ["date", "updated_at"]:
            if column in frame:
                parsed = _latest_datetime(frame[column])
                if parsed is not None:
                    dates.append(parsed)
    return max(dates) if dates else None


def _latest_datetime(values: pd.Series) -> datetime | None:
    parsed = _to_datetime(values).dropna()
    if parsed.empty:
        return None
    return parsed.max().to_pydatetime()


def _parse_datetime(value: object) -> datetime | None:
    parsed = _to_datetime(pd.Series([_clean_text(value)])).iloc[0]
    if pd.isna(parsed):
        return None
    return parsed.to_pydatetime()


def _to_datetime(values: pd.Series) -> pd.Series:
    try:
        return pd.to_datetime(values, errors="coerce", utc=True, format="mixed")
    except TypeError:
        return pd.to_datetime(values, errors="coerce", utc=True)


def _date_string(value: datetime | None) -> str:
    return "" if value is None else value.date().isoformat()


def _staleness_days(run_dt: datetime, asof: datetime | None) -> int | str:
    if asof is None:
        return ""
    return max(0, (run_dt.date() - asof.date()).days)


def _is_st_name(value: object) -> bool:
    text = _clean_text(value).upper()
    return text.startswith("ST") or text.startswith("*ST") or " ST" in text


def _review_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    if str(row.get("concept_purity_bucket", "")) in {"broad_concept_only", "needs_manual_review", "exclude_candidate"}:
        reasons.append(str(row.get("concept_purity_bucket", "")))
    if bool(row.get("broad_concept_only", False)):
        reasons.append("broad_concept_only")
    if int(pd.to_numeric(pd.Series([row.get("matched_concept_count", 0)]), errors="coerce").fillna(0).iloc[0]) <= 1:
        reasons.append("single_concept_support")
    if bool(row.get("mojibake_flag", False)):
        reasons.append("mojibake_warning")
    if row.get("liquidity_pass", "") is False:
        reasons.append("weak_liquidity")
    if bool(row.get("st_flag", False)):
        reasons.append("st_name")
    return sorted(set(reasons))


def _review_priority(row: pd.Series, reasons: list[str]) -> int:
    bucket_weight = {
        "exclude_candidate": 0,
        "broad_concept_only": 10,
        "needs_manual_review": 20,
        "medium_confidence": 60,
        "high_confidence": 90,
    }.get(str(row.get("concept_purity_bucket", "")), 50)
    penalty = 0
    for reason in reasons:
        if reason in {"mojibake_warning", "single_concept_support", "weak_liquidity", "st_name"}:
            penalty -= 2
    return max(0, bucket_weight + penalty)


def _suggested_review_action(row: pd.Series) -> str:
    bucket = str(row.get("concept_purity_bucket", ""))
    override_status = str(row.get("override_status", ""))
    if bucket == "exclude_candidate":
        return "reject_candidate"
    if override_status == "conditional":
        return "conditional"
    if bucket in {"broad_concept_only", "needs_manual_review"}:
        return "review"
    if bucket == "medium_confidence":
        return "conditional"
    return "keep"


def _business_profile_lookup(profiles: pd.DataFrame) -> dict[tuple[str, str], dict[str, object]]:
    if profiles.empty:
        return {}
    return {
        (_normalize_theme(row.get("theme", "")), normalize_stock_code(row.get("code", ""))): row.to_dict()
        for _, row in profiles.iterrows()
    }


def _materiality_bucket(value: object) -> str:
    text = _normalize_match_text(value)
    aliases = {
        "core": ["core", "material", "main", "primary", "核心", "主营", "主要收入"],
        "transition": ["transition", "emerging", "pilot", "newbusiness", "转型", "培育", "试点"],
        "immaterial": ["immaterial", "minor", "small", "noncore", "边缘", "占比低", "非主营"],
        "unknown": ["", "unknown", "unclear", "notdisclosed", "未知", "不明", "未披露"],
    }
    for bucket, candidates in aliases.items():
        if text in {_normalize_match_text(candidate) for candidate in candidates}:
            return bucket
    return "unknown"


def _primary_business_match(theme: str, profile: dict[str, object]) -> bool:
    text = _normalize_match_text(
        " ".join(
            [
                _clean_text(profile.get("primary_business", "")),
                _clean_text(profile.get("revenue_segments", "")),
                _clean_text(profile.get("sw_industry", "")),
                _clean_text(profile.get("theme_business_description", "")),
            ]
        )
    )
    keywords = _theme_business_keywords(theme)
    return any(_normalize_match_text(keyword) in text for keyword in keywords)


def _theme_business_keywords(theme: str) -> list[str]:
    theme_text = _normalize_match_text(theme)
    if "ai" in theme_text or "人工智能" in theme_text:
        return [
            "AI",
            "artificial intelligence",
            "computing",
            "算力",
            "人工智能",
            "大模型",
            "模型",
            "software",
            "platform",
            "data center",
            "cloud",
            "algorithm",
        ]
    if "space" in theme_text or "航天" in theme_text or "鑸" in theme_text:
        return ["space", "satellite", "rocket", "aerospace", "航天", "卫星", "火箭", "北斗", "商业航天"]
    return [theme]


def _transition_story_flag(materiality_bucket: str, profile: dict[str, object]) -> bool:
    if materiality_bucket == "transition":
        return True
    text = _normalize_match_text(
        " ".join(
            [
                _clean_text(profile.get("theme_business_description", "")),
                _clean_text(profile.get("evidence_summary", "")),
            ]
        )
    )
    transition_terms = ["transition", "emerging", "pilot", "newbusiness", "incubat", "转型", "培育", "试点", "布局"]
    return any(_normalize_match_text(term) in text for term in transition_terms)


def _business_materiality_warning(profile: dict[str, object], materiality_bucket: str) -> str:
    warnings: list[str] = []
    if profile and materiality_bucket == "unknown" and _clean_text(profile.get("theme_revenue_materiality", "")):
        warnings.append("unrecognized_materiality_value")
    for column in ["theme_revenue_ratio", "theme_revenue_amount"]:
        value = _clean_text(profile.get(column, ""))
        if value and _numeric_or_blank(value) == "":
            warnings.append(f"invalid_{column}")
    return "|".join(warnings)


def _numeric_or_blank(value: object) -> float | str:
    text = _clean_text(value)
    if not text:
        return ""
    numeric = pd.to_numeric(pd.Series([text]), errors="coerce").iloc[0]
    return "" if pd.isna(numeric) else float(numeric)


def _final_review_suggestion(
    *,
    override_status: str,
    review_status: str,
    materiality_bucket: str,
    theme_business_disclosed: bool,
    transition_story: bool,
    business_mismatch: bool,
    profile_available: bool,
    impossible_code_name: bool,
) -> str:
    if override_status == "reject":
        return "reject_candidate"
    if review_status == "reject":
        return "reject_candidate"
    if impossible_code_name:
        return "reject_candidate"
    if review_status == "core":
        return "core"
    if materiality_bucket == "core" and theme_business_disclosed:
        return "core"
    if transition_story:
        return "conditional"
    if review_status == "watchlist":
        return "watchlist"
    if review_status == "conditional":
        return "conditional"
    if business_mismatch:
        return "review"
    if not profile_available:
        return "review"
    return "review"


def _business_mismatch_reasons(row: pd.Series) -> list[str]:
    reasons: list[str] = []
    high_confidence = str(row.get("concept_purity_bucket", "")) == "high_confidence"
    mismatch = _truthy(row.get("business_mismatch_flag", False))
    transition = _truthy(row.get("transition_story_flag", False))
    concept_only = _truthy(row.get("concept_only_flag", False))
    matched_count = int(pd.to_numeric(pd.Series([row.get("matched_concept_count", 0)]), errors="coerce").fillna(0).iloc[0])
    override_status = str(row.get("override_status", ""))
    if high_confidence and mismatch:
        reasons.append("high_confidence_business_mismatch")
    if matched_count > 1 and concept_only:
        reasons.append("multi_concept_concept_only")
    if high_confidence and mismatch:
        reasons.append("unrelated_business_unknown_materiality")
    if transition:
        reasons.append("transition_story")
    if override_status in {"reject", "watchlist", "conditional"}:
        reasons.append(f"manual_override_{override_status}")
    return reasons


def _business_queue_priority(reason_for_review: str) -> int:
    if "high_confidence_business_mismatch" in reason_for_review:
        return 0
    if "multi_concept_concept_only" in reason_for_review:
        return 1
    if "transition_story" in reason_for_review:
        return 2
    return 5


def _business_profile_template_row(source: pd.Series) -> dict[str, object]:
    suggestion = str(source.get("final_review_suggestion", "review"))
    initial_status = {
        "core": "core",
        "conditional": "conditional",
        "watchlist": "watchlist",
        "reject_candidate": "reject",
    }.get(suggestion, "unknown")
    return {
        "code": source.get("code", ""),
        "name": source.get("name", ""),
        "theme": source.get("theme", ""),
        "primary_business": source.get("primary_business", ""),
        "revenue_segments": source.get("revenue_segments", ""),
        "sw_industry": source.get("sw_industry", ""),
        "theme_business_description": source.get("theme_business_description", ""),
        "theme_revenue_materiality": source.get("theme_revenue_materiality", ""),
        "theme_revenue_ratio": source.get("theme_revenue_ratio", ""),
        "theme_revenue_amount": source.get("theme_revenue_amount", ""),
        "evidence_level": source.get("evidence_level", "unknown"),
        "evidence_source": source.get("evidence_source", ""),
        "evidence_url": source.get("evidence_url", ""),
        "evidence_date": source.get("evidence_date", ""),
        "evidence_summary": source.get("evidence_summary", ""),
        "reviewer": source.get("reviewer", ""),
        "review_status": source.get("review_status", "unknown"),
        "concept_purity_bucket": source.get("concept_purity_bucket", ""),
        "supporting_concepts": source.get("supporting_concepts", ""),
        "concept_exposure_score": source.get("concept_exposure_score", ""),
        "reason_for_review": "|".join(_business_mismatch_reasons(source)),
        "suggested_initial_review_status": initial_status,
    }


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes"}


def _extra_business_metadata_columns(metadata: dict[str, object]) -> list[str]:
    return [key for key in metadata if key not in BUSINESS_MATERIALITY_COLUMNS]


def _extra_metadata_columns(metadata: dict[str, object]) -> list[str]:
    return [key for key in metadata if key not in PURITY_DIAGNOSTIC_COLUMNS]


def _concept_records(concept_names: pd.DataFrame) -> list[dict[str, str]]:
    code_col = _first_existing_column(concept_names, ["concept_code", "code", "板块代码", "f12"])
    name_col = _first_existing_column(concept_names, ["concept_name", "name", "板块名称", "f14"])
    if name_col is None:
        raise ValueError(f"Cannot identify concept name column: {list(concept_names.columns)}")
    records: list[dict[str, str]] = []
    for _, row in concept_names.iterrows():
        name = _clean_text(row.get(name_col, ""))
        if not name:
            continue
        records.append(
            {
                "concept_name": name,
                "concept_code": _clean_text(row.get(code_col, "")) if code_col else "",
            }
        )
    return records


def _has_invalid_input(row: pd.Series) -> bool:
    return str(row.get("ring", "")) not in VALID_RINGS or str(row.get("include_default", "")) not in VALID_INCLUDE_DEFAULT


def _concept_count_by_ring(group: pd.DataFrame, ring: str) -> int:
    subset = group[group["ring"] == ring]
    return int(subset["matched_akshare_concept"].nunique())


def _metadata_columns(run_metadata: dict[str, object], generated_at: str) -> dict[str, object]:
    metadata = {"generated_at": generated_at}
    metadata.update(run_metadata)
    return metadata


def _first_existing_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((column for column in candidates if column in frame.columns), None)


def _clean_text(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def _normalize_theme(value: object) -> str:
    return _clean_text(value)


def _normalize_date(value: object) -> str:
    text = _clean_text(value)
    if not text:
        return ""
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return text
    return parsed.strftime("%Y-%m-%d")


def _normalize_match_text(value: object) -> str:
    return _clean_text(value).replace(" ", "").replace("\u3000", "").lower()


def _strip_suffix(value: str) -> str:
    for suffix in ["概念", "板块", "产业", "行业"]:
        if value.endswith(suffix) and len(value) > len(suffix):
            return value[: -len(suffix)]
    return value
