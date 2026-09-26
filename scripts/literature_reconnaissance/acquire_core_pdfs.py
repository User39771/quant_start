"""Sequentially acquire and validate planned core-paper PDFs.

Only URLs explicitly reviewed in source_plan.csv are used. The manifest is
rewritten after each paper so the batch can resume safely.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/literature_reconnaissance"
PAPERS = DOCS / "papers"
PDF_ROOT = PAPERS / "source_pdfs"
PLAN = PAPERS / "source_plan.csv"
REGISTRY = DOCS / "02_literature_registry.csv"
MANIFEST = PAPERS / "acquisition_manifest.csv"
CHECKPOINT = PAPERS / "acquisition_checkpoint.csv"
PDFINFO = Path(r"C:\texlive\2026\bin\windows\pdfinfo.exe")
PDFTOTEXT = Path(r"C:\texlive\2026\bin\windows\pdftotext.exe")
USER_AGENT = "quant-start-literature-reconnaissance/1.0"

FIELDS = [
    "paper_id", "title", "authors", "year", "target_version",
    "obtained_version", "version_relation", "source_url", "source_domain",
    "access_basis", "retrieved_at_utc", "filename", "file_size", "page_count",
    "pdf_valid", "sha256", "full_text_status", "notes",
]


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def pdf_info(path: Path) -> tuple[int, str]:
    result = subprocess.run(
        [str(PDFINFO), str(path)], capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=False,
    )
    match = re.search(r"^Pages:\s+(\d+)", result.stdout, re.MULTILINE)
    return (int(match.group(1)) if match else 0, result.stdout + result.stderr)


def first_pages(path: Path) -> str:
    result = subprocess.run(
        [str(PDFTOTEXT), "-f", "1", "-l", "3", str(path), "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False,
    )
    return result.stdout


def identity_ok(meta: dict[str, str], path: Path) -> tuple[bool, str]:
    pages, info = pdf_info(path)
    if path.read_bytes()[:5] != b"%PDF-" or pages < 1:
        return False, f"invalid PDF header/page count; {info[-300:]}"
    text = re.sub(r"\s+", " ", first_pages(path)).casefold()
    title_words = [
        word.casefold() for word in re.findall(r"[A-Za-z]{5,}", meta["title"])
        if word.casefold() not in {"using", "between", "returns", "stock", "stocks"}
    ]
    author_tokens = [
        token.casefold() for token in re.findall(r"[A-Za-z]{4,}", meta["authors"])
    ]
    title_hits = sum(word in text for word in title_words[:8])
    author_hit = any(token in text for token in author_tokens)
    ok = title_hits >= min(2, len(title_words)) and author_hit
    return ok, f"title_word_hits={title_hits}; author_hit={author_hit}; pages={pages}"


def download(url: str, target: Path) -> None:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/pdf,text/html;q=0.5,*/*;q=0.1",
        },
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(request, timeout=60) as response:
        payload = response.read()
    target.write_bytes(payload)


def status_for(plan: dict[str, str]) -> str:
    basis = plan["access_basis"]
    if basis in {"author_homepage"}:
        return "author_manuscript_downloaded"
    if basis in {"institutional_repository", "university_hosted_copy", "university_course_copy"}:
        return "repository_version_downloaded"
    return "open_fulltext_downloaded"


def main() -> None:
    registry = {
        row["paper_id"]: row for row in read_csv(REGISTRY)
        if row["selection_status"] == "core"
    }
    plan_rows = read_csv(PLAN)
    existing = {
        row["paper_id"]: row for row in read_csv(MANIFEST)
    } if MANIFEST.exists() else {}

    for plan in plan_rows:
        paper_id = plan["paper_id"]
        meta = registry[paper_id]
        target = PDF_ROOT / paper_id / plan["filename"]
        retrieved = datetime.now(timezone.utc).isoformat()
        note_parts = [plan["notes"]] if plan["notes"] else []
        url = plan["source_url"]

        try:
            if not target.exists():
                if plan["access_basis"] == "publisher_landing_only":
                    raise PermissionError("publisher landing page only; no open PDF URL")
                download(url, target)
            valid, identity_note = identity_ok(meta, target)
            note_parts.append(identity_note)
            if not valid and plan.get("identity_override") != "visual":
                target.unlink(missing_ok=True)
                raise ValueError("downloaded object failed PDF identity validation")
            if not valid:
                note_parts.append("identity accepted after visual first-page verification")
            pages, _ = pdf_info(target)
            sha = hashlib.sha256(target.read_bytes()).hexdigest()
            final_status = (
                "existing_fulltext_reviewed" if paper_id == "C07"
                else status_for(plan)
            )
            row = {
                "paper_id": paper_id,
                "title": meta["title"],
                "authors": meta["authors"],
                "year": meta["year"],
                "target_version": meta["venue"],
                "obtained_version": plan["obtained_version"],
                "version_relation": plan["version_relation"],
                "source_url": url,
                "source_domain": plan["source_domain"],
                "access_basis": plan["access_basis"],
                "retrieved_at_utc": retrieved,
                "filename": str(target.relative_to(ROOT)).replace("\\", "/"),
                "file_size": str(target.stat().st_size),
                "page_count": str(pages),
                "pdf_valid": "true",
                "sha256": sha,
                "full_text_status": final_status,
                "notes": "; ".join(note_parts),
            }
        except (OSError, ValueError, PermissionError, urllib.error.URLError) as error:
            target.unlink(missing_ok=True)
            row = {
                "paper_id": paper_id,
                "title": meta["title"],
                "authors": meta["authors"],
                "year": meta["year"],
                "target_version": meta["venue"],
                "obtained_version": "",
                "version_relation": plan["version_relation"],
                "source_url": url,
                "source_domain": plan["source_domain"],
                "access_basis": plan["access_basis"],
                "retrieved_at_utc": retrieved,
                "filename": "",
                "file_size": "",
                "page_count": "",
                "pdf_valid": "false",
                "sha256": "",
                "full_text_status": plan["on_failure_status"],
                "notes": "; ".join(note_parts + [f"{type(error).__name__}: {error}"]),
            }

        existing[paper_id] = row
        ordered = [existing[item["paper_id"]] for item in plan_rows if item["paper_id"] in existing]
        write_csv(MANIFEST, ordered, FIELDS)
        write_csv(
            CHECKPOINT,
            [{"paper_id": item["paper_id"], "full_text_status": item["full_text_status"],
              "completed_at_utc": item["retrieved_at_utc"]} for item in ordered],
            ["paper_id", "full_text_status", "completed_at_utc"],
        )
        print(f"{paper_id}: {row['full_text_status']}")

    assert len(existing) == 30
    print(json.dumps({"papers": 30, "manifest": str(MANIFEST)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
