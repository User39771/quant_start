"""Fetch bounded academic metadata for the literature reconnaissance."""

from __future__ import annotations

import csv
import json
import time
import urllib.parse
import urllib.request
from pathlib import Path


QUERIES = [
    ("Q_A01", "cross-sectional stock return factor evaluation information coefficient portfolio sorts"),
    ("Q_A02", "factor zoo anomalies transaction costs out of sample stock returns"),
    ("Q_B01", "backtest overfitting data snooping multiple testing finance"),
    ("Q_B02", "false discoveries deflated Sharpe ratio probability of backtest overfitting"),
    ("Q_C01", "formulaic alpha mining genetic programming reinforcement learning symbolic regression"),
    ("Q_C02", "LLM alpha factor mining MCTS formula discovery"),
    ("Q_D01", "trading volume price momentum reversal stock returns"),
    ("Q_D02", "abnormal volume investor attention disagreement liquidity price pressure"),
    ("Q_E01", "thematic investing stock classification event study abnormal returns"),
    ("Q_E02", "news announcement response industry spillover theme stock returns"),
    ("Q_F01", "China A-share price limits suspension ST delisting transaction costs"),
    ("Q_F02", "China stock market T+1 survivorship point in time constituents liquidity"),
]

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs" / "literature_reconnaissance" / "raw_metadata"
FIELDS = [
    "query_id",
    "openalex_id",
    "doi",
    "title",
    "authors",
    "year",
    "venue",
    "type",
    "cited_by_count",
    "is_oa",
    "landing_page_url",
]


def get_json(url: str) -> dict:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "quant-start-literature-recon/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        value = json.loads(response.read().decode("utf-8"))
    return json.loads(value) if isinstance(value, str) else value


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rows: list[dict] = []
    counts: list[dict] = []
    seen: set[str] = set()

    for query_id, query in QUERIES:
        params = urllib.parse.urlencode(
            {
                "search": query,
                "per-page": 25,
            }
        )
        payload = get_json(f"https://api.openalex.org/works?{params}")
        (OUT / f"{query_id}.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        counts.append(
            {
                "query_id": query_id,
                "exact_query": query,
                "result_count_seen": payload["meta"]["count"],
                "records_retrieved": len(payload["results"]),
            }
        )
        for work in payload["results"]:
            key = work.get("doi") or work["id"]
            if key in seen:
                continue
            seen.add(key)
            location = work.get("primary_location") or {}
            source = location.get("source") or {}
            rows.append(
                {
                    "query_id": query_id,
                    "openalex_id": work["id"],
                    "doi": work.get("doi") or "",
                    "title": work["title"],
                    "authors": "; ".join(
                        item["author"]["display_name"]
                        for item in work.get("authorships", [])
                    ),
                    "year": work.get("publication_year") or "",
                    "venue": source.get("display_name") or "",
                    "type": work.get("type") or "",
                    "cited_by_count": work.get("cited_by_count") or 0,
                    "is_oa": (work.get("open_access") or {}).get("is_oa", False),
                    "landing_page_url": location.get("landing_page_url") or "",
                }
            )
        time.sleep(0.15)

    with (OUT / "openalex_candidates.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    with (OUT / "openalex_query_counts.csv").open(
        "w", encoding="utf-8-sig", newline=""
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=counts[0])
        writer.writeheader()
        writer.writerows(counts)

    print(f"queries={len(QUERIES)} unique_candidates={len(rows)}")


if __name__ == "__main__":
    main()
