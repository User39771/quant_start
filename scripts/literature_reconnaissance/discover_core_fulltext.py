"""Discover lawful full-text candidates for the 30 core papers via OpenAlex.

This script only records metadata. It never downloads a paper PDF.
"""

from __future__ import annotations

import csv
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "docs/literature_reconnaissance/02_literature_registry.csv"
OUTPUT = ROOT / "docs/literature_reconnaissance/papers/discovery"
RAW = OUTPUT / "openalex"
CSV_PATH = OUTPUT / "open_source_candidates.csv"
USER_AGENT = "quant-start-literature-reconnaissance/1.0"


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError) as error:
            last_error = error
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"OpenAlex request failed: {last_error}")


def work_url(row: dict[str, str]) -> str:
    identifier = row["doi_or_stable_identifier"].strip()
    if identifier.lower().startswith("10."):
        doi_url = f"https://doi.org/{identifier}"
        return "https://api.openalex.org/works/" + urllib.parse.quote(
            doi_url, safe=":/"
        )
    query = urllib.parse.urlencode({"search": row["title"], "per-page": 1})
    return f"https://api.openalex.org/works?{query}"


def normalize_work(payload: dict) -> dict:
    if "results" in payload:
        results = payload.get("results") or []
        if not results:
            raise RuntimeError("OpenAlex title search returned no results")
        return results[0]
    return payload


def location_rows(paper_id: str, work: dict) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()
    locations = []
    best = work.get("best_oa_location")
    if best:
        locations.append(("best_oa_location", best))
    for location in work.get("locations") or []:
        locations.append(("location", location))

    for location_type, location in locations:
        pdf_url = (location.get("pdf_url") or "").strip()
        landing_url = (location.get("landing_page_url") or "").strip()
        key = (pdf_url, landing_url)
        if not any(key) or key in seen:
            continue
        seen.add(key)
        source = location.get("source") or {}
        rows.append(
            {
                "paper_id": paper_id,
                "openalex_id": work.get("id") or "",
                "location_type": location_type,
                "is_oa": str(bool(location.get("is_oa"))).lower(),
                "version": location.get("version") or "",
                "license": location.get("license") or "",
                "source_name": source.get("display_name") or "",
                "source_type": source.get("type") or "",
                "landing_page_url": landing_url,
                "pdf_url": pdf_url,
            }
        )
    if not rows:
        rows.append(
            {
                "paper_id": paper_id,
                "openalex_id": work.get("id") or "",
                "location_type": "none",
                "is_oa": str(bool((work.get("open_access") or {}).get("is_oa"))).lower(),
                "version": "",
                "license": "",
                "source_name": "",
                "source_type": "",
                "landing_page_url": "",
                "pdf_url": "",
            }
        )
    return rows


def write_csv(rows: list[dict[str, str]]) -> None:
    fieldnames = [
        "paper_id",
        "openalex_id",
        "location_type",
        "is_oa",
        "version",
        "license",
        "source_name",
        "source_type",
        "landing_page_url",
        "pdf_url",
    ]
    with CSV_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    with REGISTRY.open(encoding="utf-8-sig", newline="") as handle:
        core = [
            row for row in csv.DictReader(handle) if row["selection_status"] == "core"
        ]

    discovered: list[dict[str, str]] = []
    for row in core:
        paper_id = row["paper_id"]
        raw_path = RAW / f"{paper_id}.json"
        try:
            cached = json.loads(raw_path.read_text(encoding="utf-8")) if raw_path.exists() else None
            work = cached if cached and "error" not in cached else normalize_work(fetch_json(work_url(row)))
            if cached is None or "error" in cached:
                raw_path.write_text(
                    json.dumps(work, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            locations = location_rows(paper_id, work)
            discovered.extend(locations)
            print(f"{paper_id}: {len(locations)} locations")
        except Exception as error:  # keep the 30-paper batch recoverable
            raw_path.write_text(
                json.dumps({"paper_id": paper_id, "error": str(error)}, indent=2),
                encoding="utf-8",
            )
            discovered.append(
                {
                    "paper_id": paper_id,
                    "openalex_id": "",
                    "location_type": "error",
                    "is_oa": "",
                    "version": "",
                    "license": "",
                    "source_name": "",
                    "source_type": "",
                    "landing_page_url": "",
                    "pdf_url": "",
                }
            )
            print(f"{paper_id}: ERROR {error}")
        write_csv(discovered)
        time.sleep(0.25)

    print(f"papers={len(core)} candidate_rows={len(discovered)} output={CSV_PATH}")


if __name__ == "__main__":
    main()
