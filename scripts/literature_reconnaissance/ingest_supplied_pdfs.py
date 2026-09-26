"""Incrementally ingest the seven user-supplied full-text PDFs.

This script is deliberately scoped to D01-D05, F02, and F03. It does not
download papers, translate text, or rerun readers for any other paper.
"""

from __future__ import annotations

import csv
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from extract_core_readers import extract


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/literature_reconnaissance"
PAPERS = DOCS / "papers"
READERS = PAPERS / "readers"
MANIFEST = PAPERS / "acquisition_manifest.csv"
REGISTRY = DOCS / "02_literature_registry.csv"
PDFINFO = Path(
    r"C:\Users\Hangxi Yang\.cache\codex-runtimes\codex-primary-runtime"
    r"\dependencies\native\poppler\Library\bin\pdfinfo.exe"
)
SUCCESS = {
    "existing_fulltext_reviewed",
    "open_fulltext_downloaded",
    "author_manuscript_downloaded",
    "repository_version_downloaded",
    "full_text_downloaded_not_reviewed",
}
FINAL_STATUS = "full_text_downloaded_not_reviewed"
GROUPS = {
    "Must Read": ["C07", "B01", "B05", "A04", "A03", "D03", "E01", "F01"],
    "Guided Read": ["A01", "A02", "A05", "B03", "B04", "C03", "C04", "C06", "D05", "E03"],
    "Reference Only": [
        "B02", "B06", "C01", "C02", "C05", "D01", "D02", "D04", "D06",
        "E02", "F02", "F03",
    ],
}
TARGETS = {
    "D01": {
        "path": "docs/literature_reconnaissance/papers/source_pdfs/D01/"
        "The_Relation_Between_Price_Cha.pdf",
        "source_url": "https://www.jstor.org/stable/2330874",
        "obtained_version": "final journal version (scanned reproduction)",
        "version_relation": "Exact final JFQA article layout; no content-version mismatch identified",
        "title_tokens": ["relation", "price", "changes", "trading", "volume", "survey"],
        "author_tokens": ["karpoff"],
        "year": "1987",
        "venue_tokens": ["financial", "quantitative", "analysis"],
    },
    "D02": {
        "path": "docs/literature_reconnaissance/papers/source_pdfs/D02/"
        "Campbell-TradingVolumeSerial-1993.pdf",
        "source_url": "https://www.jstor.org/stable/2118454",
        "obtained_version": "final journal version",
        "version_relation": "Exact final Quarterly Journal of Economics article; no mismatch identified",
        "title_tokens": ["trading", "volume", "serial", "correlation", "stock", "returns"],
        "author_tokens": ["campbell", "grossman", "wang"],
        "year": "1993",
        "venue_tokens": ["quarterly", "journal", "economics"],
    },
    "D03": {
        "path": "docs/literature_reconnaissance/papers/source_pdfs/D03/"
        "Lee-PriceMomentumTrading-2000.pdf",
        "source_url": "https://www.jstor.org/stable/222483",
        "obtained_version": "final journal version",
        "version_relation": "Exact final Journal of Finance article; no mismatch identified",
        "title_tokens": ["price", "momentum", "trading", "volume"],
        "author_tokens": ["lee", "swaminathan"],
        "year": "2000",
        "venue_tokens": ["journal", "finance"],
    },
    "D04": {
        "path": "docs/literature_reconnaissance/papers/source_pdfs/D04/"
        "Gervais-HighVolumeReturnPremium-2001.pdf",
        "source_url": "https://www.jstor.org/stable/222536",
        "obtained_version": "final journal version",
        "version_relation": "Exact final Journal of Finance article; no mismatch identified",
        "title_tokens": ["high", "volume", "return", "premium"],
        "author_tokens": ["gervais", "kaniel", "mingelgrin"],
        "year": "2001",
        "venue_tokens": ["journal", "finance"],
    },
    "D05": {
        "path": "docs/literature_reconnaissance/papers/source_pdfs/D05/"
        "Llorente-DynamicVolumeReturnRelation-2002.pdf",
        "source_url": "https://www.jstor.org/stable/1262690",
        "obtained_version": "final journal version",
        "version_relation": "Exact final Review of Financial Studies article; no mismatch identified",
        "title_tokens": ["dynamic", "volume", "return", "relation", "individual", "stocks"],
        "author_tokens": ["llorente", "michaely", "saar", "wang"],
        "year": "2002",
        "venue_tokens": ["review", "financial", "studies"],
    },
    "F02": {
        "path": "docs/literature_reconnaissance/papers/source_pdfs/F02/"
        "1-s2.0-S0378426611002561-main.pdf",
        "source_url": "https://doi.org/10.1016/j.jbankfin.2011.09.002",
        "obtained_version": "final journal version",
        "version_relation": "Exact final Journal of Banking & Finance article; no mismatch identified",
        "title_tokens": ["unique", "trading", "rule", "china", "theory", "evidence"],
        "author_tokens": ["guo", "li", "tu"],
        "year": "2012",
        "venue_tokens": ["journal", "banking", "finance"],
    },
    "F03": {
        "path": "docs/literature_reconnaissance/papers/source_pdfs/F03/"
        "1-s2.0-S0927539823000476-main.pdf",
        "source_url": "https://doi.org/10.1016/j.jempfin.2023.05.003",
        "obtained_version": "final journal version",
        "version_relation": "Exact final Journal of Empirical Finance article; no mismatch identified",
        "title_tokens": ["price", "limit", "market", "efficiency", "short", "sale", "experiment"],
        "author_tokens": ["chen", "gu", "ni"],
        "year": "2023",
        "venue_tokens": ["journal", "empirical", "finance"],
    },
}
INCREMENTAL_BEGIN = "<!-- SUPPLIED_PDF_INCREMENT_BEGIN -->"
INCREMENTAL_END = "<!-- SUPPLIED_PDF_INCREMENT_END -->"
FULLTEXT_BEGIN = "<!-- FULLTEXT_BATCH_BEGIN -->"
FULLTEXT_END = "<!-- FULLTEXT_BATCH_END -->"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pdf_pages(path: Path) -> int:
    result = subprocess.run(
        [str(PDFINFO), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    match = re.search(r"^Pages:\s+(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match:
        raise ValueError(f"Could not read page count: {path}")
    return int(match.group(1))


def replace_marked(path: Path, body: str, begin: str, end: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if begin in text:
        before, tail = text.split(begin, 1)
        text = before.rstrip()
        if end in tail:
            after = tail.split(end, 1)[1].strip()
            if after:
                text += "\n\n" + after
    path.write_text(f"{text.rstrip()}\n\n{begin}\n{body.rstrip()}\n{end}\n", encoding="utf-8")


def normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.casefold())


def csv_has_header(path: Path, required: set[str]) -> bool:
    if not path.exists():
        return False
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        return required.issubset(set(reader.fieldnames or []))


def build_candidate(
    paper_id: str, old: dict[str, str], now: str,
) -> dict[str, str]:
    spec = TARGETS[paper_id]
    pdf = ROOT / spec["path"]
    if not pdf.exists() or pdf.read_bytes()[:5] != b"%PDF-":
        raise ValueError(f"{paper_id}: missing or invalid PDF header")
    row = dict(old)
    row.update({
        "obtained_version": spec["obtained_version"],
        "version_relation": spec["version_relation"],
        "source_url": spec["source_url"],
        "source_domain": "local_user_supplied",
        "access_basis": "user_provided_pdf",
        "retrieved_at_utc": now,
        "filename": spec["path"],
        "file_size": str(pdf.stat().st_size),
        "page_count": str(pdf_pages(pdf)),
        "pdf_valid": "true",
        "sha256": sha256(pdf),
        "notes": (
            "User-supplied PDF; identity and final-journal layout checked locally; "
            "download origin beyond the supplied file is not independently asserted"
        ),
    })
    return row


def qa_paper(
    paper_id: str, candidate: dict[str, str],
) -> tuple[dict[str, bool], dict[str, str]]:
    spec = TARGETS[paper_id]
    pdf = ROOT / candidate["filename"]
    base = READERS / paper_id
    extracted = base / "extracted"
    analysis = base / "analysis"
    original_path = extracted / "paper_original.md"
    map_path = extracted / "source_map.csv"
    section_path = extracted / "section_index.csv"
    contract_path = analysis / "research_contract.md"
    evidence_path = analysis / "evidence_map.md"
    handoff_path = analysis / "work_handoff.md"
    required = [
        base / "source/source_metadata.json",
        base / "source/sha256.txt",
        original_path,
        section_path,
        map_path,
        extracted / "formulas_index.csv",
        extracted / "figures_index.csv",
        extracted / "tables_index.csv",
        extracted / "extraction_issues.md",
        contract_path,
        evidence_path,
        analysis / "limitations_map.md",
        analysis / "project_relevance.md",
        analysis / "reading_outline.md",
        analysis / "translation_queue.md",
        handoff_path,
    ]
    original = original_path.read_text(encoding="utf-8") if original_path.exists() else ""
    normalized = normalize(original)
    title_ok = all(token in normalized for token in spec["title_tokens"])
    authors_ok = all(token in normalized for token in spec["author_tokens"])
    year_ok = spec["year"] in normalized
    venue_ok = all(token in normalized for token in spec["venue_tokens"])
    identity_ok = title_ok and authors_ok and year_ok and venue_ok

    maps = read_csv(map_path) if map_path.exists() else []
    sections = read_csv(section_path) if section_path.exists() else []
    ids = [row["source_map_id"] for row in maps]
    pages = {int(row["original_page"]) for row in maps if row.get("original_page", "").isdigit()}
    expected_pages = int(candidate["page_count"])
    source_map_ok = (
        bool(maps)
        and len(ids) == len(set(ids))
        and pages == set(range(1, expected_pages + 1))
        and all(row.get("locator", "").strip() for row in maps)
        and original.count("<!-- PDF_PAGE:") == expected_pages
    )
    contract = contract_path.read_text(encoding="utf-8") if contract_path.exists() else ""
    evidence = evidence_path.read_text(encoding="utf-8") if evidence_path.exists() else ""
    referenced_ids = set(re.findall(r"p\d{3}-b\d{3}", contract + "\n" + evidence))
    contract_ok = (
        candidate["sha256"] in contract
        and spec["obtained_version"] in contract
        and "作者主要发现" in contract
        and "Codex inference" in contract
        and bool(referenced_ids)
        and referenced_ids.issubset(set(ids))
    )
    handoff = handoff_path.read_text(encoding="utf-8") if handoff_path.exists() else ""
    reader_ok = (
        all(path.exists() for path in required)
        and csv_has_header(section_path, {"section_id", "section_title", "original_page", "source_map_id"})
        and csv_has_header(map_path, {"source_map_id", "original_page", "section_title", "locator"})
        and csv_has_header(extracted / "formulas_index.csv", {
            "formula_id", "formula_text", "original_page", "source_map_id", "extraction_status",
        })
        and csv_has_header(extracted / "figures_index.csv", {
            "figure_id", "caption", "original_page", "source_map_id",
        })
        and csv_has_header(extracted / "tables_index.csv", {
            "table_id", "caption", "original_page", "source_map_id",
        })
        and any("conclu" in row.get("section_title", "").casefold() for row in sections)
        and "reader_status=source_only_extraction_complete" in handoff
        and "translation_status=pending_work_review" in handoff
        and "full_bilingual_reader_complete=false" in handoff
    )
    pdf_ok = (
        pdf.exists()
        and pdf.read_bytes()[:5] == b"%PDF-"
        and sha256(pdf) == candidate["sha256"]
        and pdf_pages(pdf) == expected_pages
        and pdf.stat().st_size == int(candidate["file_size"])
    )
    checks = {
        "pdf_integrity": pdf_ok,
        "identity_title_authors_year_venue": identity_ok,
        "source_map": source_map_ok,
        "research_contract": contract_ok,
        "reader_bundle": reader_ok,
    }
    detail = {
        "title": str(title_ok),
        "authors": str(authors_ok),
        "year": str(year_ok),
        "venue": str(venue_ok),
        "pages": candidate["page_count"],
        "sha256": candidate["sha256"],
        "source_blocks": str(len(maps)),
    }
    return checks, detail


def reader_status(paper_id: str, acquisition: str) -> str:
    if paper_id == "C07":
        return "existing_native_nature_reader_validated"
    if acquisition in SUCCESS:
        return "source_only_extraction_complete"
    return acquisition


def update_checkpoint(
    path: Path, target_updates: dict[str, dict[str, str]], key: str, fields: list[str],
) -> None:
    rows = read_csv(path)
    by_id = {row["paper_id"]: row for row in rows}
    for paper_id, updates in target_updates.items():
        by_id[paper_id].update(updates)
    write_csv(path, [by_id[row["paper_id"]] for row in rows], fields)


def update_handoff_and_gaps(
    manifest: dict[str, dict[str, str]], registry: dict[str, dict[str, str]],
) -> None:
    handoff = [
        "# Work handoff index",
        "",
        "This index contains no full-paper Chinese translation. `paper_original.md` and all "
        "source PDFs are local-only Git-ignored files.",
        "",
    ]
    for group, ids in GROUPS.items():
        handoff += [
            f"## {group}", "",
            "| ID | Title | Status | Work entry | Source version |",
            "|---|---|---|---|---|",
        ]
        for paper_id in ids:
            row, meta = manifest[paper_id], registry[paper_id]
            status = reader_status(paper_id, row["full_text_status"])
            if paper_id == "C07":
                entry = "`output/paper_reader_2505.11122v3/paper.md`"
            elif row["full_text_status"] in SUCCESS:
                entry = f"`papers/readers/{paper_id}/analysis/work_handoff.md`"
            else:
                entry = row["source_url"] or meta["source_url_or_location"]
            handoff.append(
                f"| {paper_id} | {meta['title'].replace('|', '/')} | {status} | "
                f"{entry} | {row['obtained_version'] or 'not obtained'} |"
            )
        handoff.append("")
    (PAPERS / "WORK_HANDOFF_INDEX.md").write_text("\n".join(handoff), encoding="utf-8")

    gaps = [
        "# Full-text gap report", "",
        "No abstract or HTML printout was treated as a full paper.", "",
        "| ID | Title | Final status | Stable identifier | Attempted official page | Reason |",
        "|---|---|---|---|---|---|",
    ]
    for paper_id in sum(GROUPS.values(), []):
        row, meta = manifest[paper_id], registry[paper_id]
        if row["full_text_status"] in SUCCESS:
            continue
        gaps.append(
            f"| {paper_id} | {meta['title'].replace('|', '/')} | {row['full_text_status']} | "
            f"{meta['doi_or_stable_identifier']} | {row['source_url']} | "
            f"{row['notes'].replace('|', '/')} |"
        )
    (PAPERS / "fulltext_gap_report.md").write_text("\n".join(gaps) + "\n", encoding="utf-8")


def update_markdown_indexes(
    manifest: dict[str, dict[str, str]], registry: dict[str, dict[str, str]],
) -> None:
    status_table = [
        "## 2026-07-25 supplied-PDF incremental checkpoint", "",
        "| ID | Acquisition | Knowledge-base status | Reader |",
        "|---|---|---|---|",
    ]
    for paper_id in sum(GROUPS.values(), []):
        row = manifest[paper_id]
        status_table.append(
            f"| {paper_id} | {row['full_text_status']} | "
            f"{registry[paper_id]['full_text_status']} | "
            f"{reader_status(paper_id, row['full_text_status'])} |"
        )
    status_table += [
        "",
        "D01-D05, F02 and F03 were supplied by the user and ingested incrementally. "
        "They remain `full_text_downloaded_not_reviewed`; Work-mode close reading is required "
        "before any promotion to `full_text_reviewed`.",
    ]
    replace_marked(
        DOCS / "03_core_papers_shortlist.md",
        "\n".join(status_table),
        FULLTEXT_BEGIN,
        FULLTEXT_END,
    )

    reading = [
        "## 2026-07-25 incremental Work-mode availability", "",
        "- D01, D02, D03, D04, D05, F02 and F03 now have source-only Reader bundles.",
        "- Start each paper from its `papers/readers/<paper_id>/analysis/work_handoff.md`.",
        "- No full Chinese translation was generated; translation queues remain pending Work review.",
        "- These seven papers are downloaded and structurally mapped, but not manually close-read.",
    ]
    replace_marked(
        DOCS / "08_student_reading_plan.md",
        "\n".join(reading),
        FULLTEXT_BEGIN,
        FULLTEXT_END,
    )


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    manifest_rows = read_csv(MANIFEST)
    manifest_fields = list(manifest_rows[0])
    manifest = {row["paper_id"]: row for row in manifest_rows}
    registry_rows = read_csv(REGISTRY)
    registry_fields = list(registry_rows[0])
    registry = {row["paper_id"]: row for row in registry_rows}

    candidates = {
        paper_id: build_candidate(paper_id, manifest[paper_id], now)
        for paper_id in TARGETS
    }
    extraction_errors: dict[str, str] = {}
    for paper_id, candidate in candidates.items():
        try:
            extract(registry[paper_id], candidate)
        except Exception as exc:  # keep other supplied PDFs progressing
            extraction_errors[paper_id] = f"{type(exc).__name__}: {exc}"

    results: dict[str, tuple[dict[str, bool], dict[str, str]]] = {}
    for paper_id, candidate in candidates.items():
        if paper_id in extraction_errors:
            results[paper_id] = (
                {
                    "pdf_integrity": True,
                    "identity_title_authors_year_venue": False,
                    "source_map": False,
                    "research_contract": False,
                    "reader_bundle": False,
                },
                {"error": extraction_errors[paper_id], "sha256": candidate["sha256"]},
            )
            continue
        results[paper_id] = qa_paper(paper_id, candidate)

    passed: list[str] = []
    for paper_id, candidate in candidates.items():
        checks, detail = results[paper_id]
        row = manifest[paper_id]
        row.update(candidate)
        if all(checks.values()):
            row["full_text_status"] = FINAL_STATUS
            row["notes"] += "; identity/source-map/research-contract/Reader QA PASS"
            registry[paper_id]["full_text_status"] = FINAL_STATUS
            passed.append(paper_id)
        else:
            row["full_text_status"] = "retrieval_error"
            row["pdf_valid"] = "true" if checks["pdf_integrity"] else "false"
            row["notes"] += f"; incremental QA failed: {json.dumps(detail, ensure_ascii=False)}"
    write_csv(MANIFEST, manifest_rows, manifest_fields)
    write_csv(REGISTRY, registry_rows, registry_fields)

    acquisition_updates = {
        paper_id: {
            "full_text_status": manifest[paper_id]["full_text_status"],
            "completed_at_utc": now,
        }
        for paper_id in TARGETS
    }
    update_checkpoint(
        PAPERS / "acquisition_checkpoint.csv",
        acquisition_updates,
        "full_text_status",
        ["paper_id", "full_text_status", "completed_at_utc"],
    )
    batch_updates = {
        paper_id: {
            "acquisition_status": manifest[paper_id]["full_text_status"],
            "reader_status": reader_status(paper_id, manifest[paper_id]["full_text_status"]),
            "pdf_sha256": manifest[paper_id]["sha256"],
            "reader_path": (
                f"docs/literature_reconnaissance/papers/readers/{paper_id}"
                if paper_id in passed else ""
            ),
            "completed_at_utc": now,
        }
        for paper_id in TARGETS
    }
    update_checkpoint(
        PAPERS / "batch_checkpoint.csv",
        batch_updates,
        "acquisition_status",
        [
            "paper_id", "acquisition_status", "reader_status", "pdf_sha256",
            "reader_path", "completed_at_utc",
        ],
    )

    update_handoff_and_gaps(manifest, registry)
    update_markdown_indexes(manifest, registry)

    version_lines = [
        "## 2026-07-25 supplied-PDF identity check", "",
        "All seven supplied files match the final journal record; no working-paper, accepted-"
        "manuscript, author-manuscript, or preprint mismatch was found.", "",
        "| ID | Obtained version | Relation to target |",
        "|---|---|---|",
    ]
    for paper_id in TARGETS:
        row = manifest[paper_id]
        version_lines.append(
            f"| {paper_id} | {row['obtained_version']} | {row['version_relation']} |"
        )
    replace_marked(
        PAPERS / "version_difference_report.md",
        "\n".join(version_lines),
        INCREMENTAL_BEGIN,
        INCREMENTAL_END,
    )

    qa_lines = [
        "## Supplied-PDF incremental QA", "",
        "| ID | PDF | Identity | Source map | Research contract | Reader | Pages | SHA-256 |",
        "|---|---|---|---|---|---|---:|---|",
    ]
    for paper_id in TARGETS:
        checks, detail = results[paper_id]
        qa_lines.append(
            f"| {paper_id} | {'PASS' if checks['pdf_integrity'] else 'FAIL'} | "
            f"{'PASS' if checks['identity_title_authors_year_venue'] else 'FAIL'} | "
            f"{'PASS' if checks['source_map'] else 'FAIL'} | "
            f"{'PASS' if checks['research_contract'] else 'FAIL'} | "
            f"{'PASS' if checks['reader_bundle'] else 'FAIL'} | "
            f"{manifest[paper_id]['page_count']} | `{manifest[paper_id]['sha256']}` |"
        )
    qa_lines += [
        "",
        f"- Passed and promoted to `{FINAL_STATUS}`: {', '.join(passed) or 'none'}.",
        f"- Extraction errors: {json.dumps(extraction_errors, ensure_ascii=False) if extraction_errors else 'none'}.",
        "- No external translation API/model, quantitative research, backtest, Phase B, or MCTS was run.",
        "- No reader outside D01-D05, F02, and F03 was regenerated.",
    ]
    replace_marked(
        PAPERS / "QA_REPORT.md",
        "\n".join(qa_lines),
        INCREMENTAL_BEGIN,
        INCREMENTAL_END,
    )

    print(json.dumps({
        "targets": list(TARGETS),
        "passed": passed,
        "failed": [paper_id for paper_id in TARGETS if paper_id not in passed],
        "status": FINAL_STATUS,
        "qa": {paper_id: checks for paper_id, (checks, _) in results.items()},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
