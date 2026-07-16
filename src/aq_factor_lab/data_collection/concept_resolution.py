from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher, get_close_matches
from typing import Callable

import pandas as pd


CONCEPT_NAME_COLUMNS = ["板块名称", "concept_name", "name"]
CONCEPT_CODE_COLUMNS = ["板块代码", "concept_code", "code"]
SUFFIXES = ("概念", "板块", "产业", "行业")
GENERIC_TOKENS = {"概念", "板块", "产业", "行业", "服务", "设备", "材料", "中心"}


@dataclass(frozen=True)
class ConceptResolutionResult:
    resolved: pd.DataFrame
    failures: pd.DataFrame


def resolve_stock_concepts(
    stock_candidates: pd.DataFrame,
    concept_names: pd.DataFrame,
    *,
    fetch_members: Callable[[str], pd.DataFrame] | None = None,
    top_n: int = 5,
    fuzzy_cutoff: float = 0.55,
) -> ConceptResolutionResult:
    """Resolve stock-pool concept candidates against the live AkShare concept list."""

    _require_columns(stock_candidates, ["candidate_concept_name"], "stock candidates")
    name_col = _first_existing_column(concept_names, CONCEPT_NAME_COLUMNS, "concept names")
    code_col = _optional_column(concept_names, CONCEPT_CODE_COLUMNS)

    concepts = _concept_records(concept_names, name_col, code_col)
    by_name = {record["name"]: record for record in concepts}
    all_names = [record["name"] for record in concepts]

    rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []
    for _, candidate_row in stock_candidates.iterrows():
        output = candidate_row.to_dict()
        requested = str(candidate_row["candidate_concept_name"]).strip()
        output.update(
            {
                "matched_concept_name": "",
                "matched_concept_code": "",
                "fuzzy_candidates": "",
                "fuzzy_query_direction": "",
                "error_type": "",
                "error": "",
            }
        )

        if not requested:
            output["status"] = "missing_name"
            output["rows"] = ""
            rows.append(output)
            continue

        exact = by_name.get(requested)
        if exact is not None:
            output["status"] = "matched"
            output["matched_concept_name"] = exact["name"]
            output["matched_concept_code"] = exact["code"]
            try:
                # AkShare accepts BK concept codes directly and avoids an extra name-to-code lookup.
                output["rows"] = _fetch_row_count(fetch_members, exact["code"] or exact["name"])
            except Exception as exc:  # noqa: BLE001 - row-level failures must be recorded.
                output["status"] = "matched_rows_failed"
                output["rows"] = ""
                output["error_type"] = type(exc).__name__
                output["error"] = str(exc)
                failures.append(
                    {
                        "stage": "concept_members",
                        "concept_name": exact["name"],
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
            rows.append(output)
            continue

        candidates, direction = fuzzy_concept_candidates(requested, all_names, top_n, fuzzy_cutoff)
        output["status"] = "fuzzy_candidates" if candidates else "no_match"
        output["rows"] = ""
        output["fuzzy_candidates"] = "|".join(candidates)
        output["fuzzy_query_direction"] = direction
        rows.append(output)

    return ConceptResolutionResult(
        resolved=pd.DataFrame(rows),
        failures=pd.DataFrame(failures, columns=["stage", "concept_name", "error_type", "error"]),
    )


def fuzzy_concept_candidates(
    requested: str,
    concept_names: list[str],
    top_n: int,
    fuzzy_cutoff: float,
) -> tuple[list[str], str]:
    requested_norm = _normalize_name(requested)
    normalized_lookup = {_normalize_name(name): name for name in concept_names}
    scores: dict[str, float] = {}
    directions: list[str] = []

    stripped = _strip_suffix(requested_norm)
    directions.append(f"remove_suffix:{stripped}")
    if stripped and stripped != requested_norm:
        for normalized, original in normalized_lookup.items():
            if _strip_suffix(normalized) == stripped:
                scores[original] = max(scores.get(original, 0), 1.0)

    close_matches = get_close_matches(
        requested_norm,
        list(normalized_lookup),
        n=max(top_n * 2, top_n),
        cutoff=fuzzy_cutoff,
    )
    if close_matches:
        directions.append("similar_text")
    for normalized in close_matches:
        original = normalized_lookup[normalized]
        score = SequenceMatcher(None, requested_norm, normalized).ratio()
        scores[original] = max(scores.get(original, 0), score)

    token_matches = _keyword_matches(stripped or requested_norm, concept_names)
    if token_matches:
        directions.append("keyword_contains")
    for name, score in token_matches.items():
        scores[name] = max(scores.get(name, 0), score)

    ordered = sorted(scores, key=lambda name: (-scores[name], name))[:top_n]
    return ordered, ";".join(directions)


def _fetch_row_count(fetch_members: Callable[[str], pd.DataFrame] | None, concept_name: str) -> int | str:
    if fetch_members is None:
        return ""
    members = fetch_members(concept_name)
    return len(members)


def _concept_records(
    concept_names: pd.DataFrame,
    name_col: str,
    code_col: str | None,
) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for _, row in concept_names.iterrows():
        name = str(row[name_col]).strip()
        if not name or name == "nan":
            continue
        code = "" if code_col is None or pd.isna(row.get(code_col)) else str(row[code_col]).strip()
        records.append({"name": name, "code": code})
    return records


def _keyword_matches(requested: str, concept_names: list[str]) -> dict[str, float]:
    matches: dict[str, float] = {}
    for token in _tokens(requested):
        for name in concept_names:
            if token in _normalize_name(name):
                matches[name] = max(matches.get(name, 0), 0.7 + min(len(token), 6) / 20)
    return matches


def _tokens(value: str) -> list[str]:
    clean = _strip_suffix(_normalize_name(value))
    tokens: list[str] = []
    for length in range(min(4, len(clean)), 1, -1):
        for start in range(0, len(clean) - length + 1):
            token = clean[start : start + length]
            if token not in GENERIC_TOKENS and token not in tokens:
                tokens.append(token)
    return tokens


def _normalize_name(value: str) -> str:
    return str(value).strip().replace(" ", "").replace("\u3000", "")


def _strip_suffix(value: str) -> str:
    clean = _normalize_name(value)
    for suffix in SUFFIXES:
        if clean.endswith(suffix) and len(clean) > len(suffix):
            return clean[: -len(suffix)]
    return clean


def _require_columns(frame: pd.DataFrame, columns: list[str], label: str) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"{label} missing required columns: {missing}")


def _first_existing_column(frame: pd.DataFrame, candidates: list[str], label: str) -> str:
    column = _optional_column(frame, candidates)
    if column is None:
        raise ValueError(f"Cannot identify name column in {label}: {list(frame.columns)}")
    return column


def _optional_column(frame: pd.DataFrame, candidates: list[str]) -> str | None:
    return next((column for column in candidates if column in frame.columns), None)
