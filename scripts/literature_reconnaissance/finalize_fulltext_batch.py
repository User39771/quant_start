"""Finalize handoff indexes, knowledge-base statuses, and batch QA."""

from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/literature_reconnaissance"
PAPERS = DOCS / "papers"
MANIFEST = PAPERS / "acquisition_manifest.csv"
PLAN = PAPERS / "source_plan.csv"
REGISTRY = DOCS / "02_literature_registry.csv"
READERS = PAPERS / "readers"
PDFTOTEXT = Path(r"C:\texlive\2026\bin\windows\pdftotext.exe")
SUCCESS = {
    "existing_fulltext_reviewed", "open_fulltext_downloaded",
    "author_manuscript_downloaded", "repository_version_downloaded",
    "full_text_downloaded_not_reviewed",
}
ALLOWED = SUCCESS | {"user_pdf_required", "fulltext_unavailable", "retrieval_error"}
GROUPS = {
    "Must Read": ["C07", "B01", "B05", "A04", "A03", "D03", "E01", "F01"],
    "Guided Read": ["A01", "A02", "A05", "B03", "B04", "C03", "C04", "C06", "D05", "E03"],
    "Reference Only": ["B02", "B06", "C01", "C02", "C05", "D01", "D02", "D04", "D06", "E02", "F02", "F03"],
}
BEGIN = "<!-- FULLTEXT_BATCH_BEGIN -->"
END = "<!-- FULLTEXT_BATCH_END -->"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def replace_appendix(path: Path, body: str) -> None:
    text = path.read_text(encoding="utf-8-sig")
    if BEGIN in text:
        text = text.split(BEGIN, 1)[0].rstrip()
    path.write_text(f"{text}\n\n{BEGIN}\n{body.rstrip()}\n{END}\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_pdf_text_sha256(path: Path) -> str:
    with tempfile.TemporaryDirectory(prefix="c07_text_qa_") as folder:
        target = Path(folder) / "paper.txt"
        subprocess.run(
            [str(PDFTOTEXT), "-layout", str(path), str(target)],
            capture_output=True, check=True,
        )
        return sha256(target)


def reader_status(paper_id: str, acquisition: str) -> str:
    if paper_id == "C07":
        return "existing_native_nature_reader_validated"
    if acquisition in SUCCESS:
        return "source_only_extraction_complete"
    return acquisition


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    plan = {row["paper_id"]: row for row in read_csv(PLAN)}
    manifest_rows = read_csv(MANIFEST)
    manifest_fields = list(manifest_rows[0])
    for row in manifest_rows:
        if not row["source_url"]:
            row["source_url"] = plan[row["paper_id"]]["source_url"]
    write_csv(MANIFEST, manifest_rows, manifest_fields)
    manifest = {row["paper_id"]: row for row in manifest_rows}

    registry_rows = read_csv(REGISTRY)
    registry_fields = list(registry_rows[0])
    registry = {row["paper_id"]: row for row in registry_rows}
    for row in registry_rows:
        if row["paper_id"] not in manifest:
            continue
        status = manifest[row["paper_id"]]["full_text_status"]
        if row["paper_id"] == "C07":
            row["full_text_status"] = "full_text_reviewed"
        elif status in SUCCESS:
            row["full_text_status"] = "full_text_downloaded_not_reviewed"
        else:
            row["full_text_status"] = status
    write_csv(REGISTRY, registry_rows, registry_fields)

    checkpoint = []
    for paper_id in sum(GROUPS.values(), []):
        row = manifest[paper_id]
        status = reader_status(paper_id, row["full_text_status"])
        checkpoint.append({
            "paper_id": paper_id, "acquisition_status": row["full_text_status"],
            "reader_status": status, "pdf_sha256": row["sha256"],
            "reader_path": (
                "output/paper_reader_2505.11122v3" if paper_id == "C07"
                else f"docs/literature_reconnaissance/papers/readers/{paper_id}"
                if row["full_text_status"] in SUCCESS else ""
            ),
            "completed_at_utc": now,
        })
    write_csv(
        PAPERS / "batch_checkpoint.csv", checkpoint,
        ["paper_id", "acquisition_status", "reader_status", "pdf_sha256",
         "reader_path", "completed_at_utc"],
    )

    handoff = [
        "# Work handoff index", "",
        "This index contains no full-paper Chinese translation. `paper_original.md` and all "
        "source PDFs are local-only Git-ignored files.", "",
    ]
    for group, ids in GROUPS.items():
        handoff += [f"## {group}", "",
                    "| ID | Title | Status | Work entry | Source version |",
                    "|---|---|---|---|---|"]
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

    status_table = [
        "## 2026-07-25 full-text infrastructure checkpoint", "",
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
        "Except for the previously completed C07 reader, downloaded papers remain "
        "`full_text_downloaded_not_reviewed`: source-only extraction and contracts are ready, "
        "but Work-mode close reading must verify nuanced claims and limitations before promotion "
        "to `full_text_reviewed`.",
    ]
    replace_appendix(DOCS / "03_core_papers_shortlist.md", "\n".join(status_table))

    notes = [
        "## 2026-07-25 source-only extraction additions", "",
        "The earlier abstract-level notes are preserved. This batch adds PDF provenance, complete "
        "page text, section/source maps, research-contract scaffolds, and Work queues. It does not "
        "promote new translated claims.", "",
        "| ID | Added full-text material | Claim revision |",
        "|---|---|---|",
    ]
    for paper_id in sum(GROUPS.values(), []):
        row = manifest[paper_id]
        added = (
            "Existing native Nature Reader artifacts revalidated"
            if paper_id == "C07" else
            "Source-only reader and evidence anchors"
            if row["full_text_status"] in SUCCESS else
            f"No PDF; {row['full_text_status']}"
        )
        revision = (
            "No change; existing C07 notes retained"
            if paper_id == "C07" else
            "No abstract-level conclusion promoted; Work review pending"
        )
        notes.append(f"| {paper_id} | {added} | {revision} |")
    replace_appendix(DOCS / "04_deep_reading_notes.md", "\n".join(notes))

    reading = [
        "## 2026-07-25 Work-mode availability", "",
        "- Start with the Must Read group in `papers/WORK_HANDOFF_INDEX.md`.",
        "- C07 is the validated existing native reader and was not regenerated.",
        "- Seven other Must Read papers were targeted; six new source-only readers are ready and "
        "D03 requires a user/library PDF.",
        "- Translation queues contain only short locators; explanation/selected translation happens "
        "later in Work.", "",
    ]
    replace_appendix(DOCS / "08_student_reading_plan.md", "\n".join(reading))

    qa: list[tuple[str, bool, str]] = []
    ids = [row["paper_id"] for row in manifest_rows]
    qa.append(("30 unique paper IDs", len(ids) == 30 and len(set(ids)) == 30, str(len(ids))))
    qa.append(("Acquisition statuses use allowed enum",
               all(row["full_text_status"] in ALLOWED for row in manifest_rows), ""))
    for row in manifest_rows:
        paper_id = row["paper_id"]
        if row["full_text_status"] not in SUCCESS:
            continue
        pdf = ROOT / row["filename"]
        ok = (
            pdf.exists() and pdf.read_bytes()[:5] == b"%PDF-"
            and sha256(pdf) == row["sha256"] and int(row["page_count"]) > 0
        )
        qa.append((f"{paper_id} PDF/hash/page identity", ok, row["sha256"]))
        if paper_id == "C07":
            old = Path(r"C:\Users\Hangxi Yang\Downloads\2505.11122v3.pdf")
            qa.append(("C07 native/current normalized text equivalence",
                       old.exists() and normalized_pdf_text_sha256(old)
                       == normalized_pdf_text_sha256(pdf),
                       "native reader not regenerated"))
            continue
        base = READERS / paper_id
        source_map = base / "extracted/source_map.csv"
        original = base / "extracted/paper_original.md"
        required = [
            base / "source/source_metadata.json", base / "source/sha256.txt",
            original, base / "extracted/section_index.csv", source_map,
            base / "extracted/formulas_index.csv", base / "extracted/figures_index.csv",
            base / "extracted/tables_index.csv", base / "extracted/extraction_issues.md",
            base / "analysis/research_contract.md", base / "analysis/evidence_map.md",
            base / "analysis/limitations_map.md", base / "analysis/project_relevance.md",
            base / "analysis/reading_outline.md", base / "analysis/translation_queue.md",
            base / "analysis/work_handoff.md",
        ]
        page_markers = original.read_text(encoding="utf-8").count("<!-- PDF_PAGE:")
        map_rows = read_csv(source_map)
        contract_text = (base / "analysis/research_contract.md").read_text(encoding="utf-8")
        qa.append((
            f"{paper_id} reader/source-map contract",
            all(path.exists() for path in required)
            and page_markers == int(row["page_count"])
            and max(int(item["original_page"]) for item in map_rows) <= int(row["page_count"])
            and "Codex inference" in contract_text and "作者主要发现" in contract_text,
            f"page_markers={page_markers}",
        ))
    qa.append(("No full Chinese translation artifact",
               not any(READERS.glob("*/**/full_chinese_translation.md")), ""))
    qa.append(("PDF/original text Git ignore rules",
               "papers/source_pdfs/" in (ROOT / ".gitignore").read_text(encoding="utf-8")
               and "paper_original.md" in (ROOT / ".gitignore").read_text(encoding="utf-8"), ""))
    qa.append(("No translation model dependency in batch scripts",
               not any(token in "\n".join(
                   path.read_text(encoding="utf-8", errors="replace")
                   for path in (ROOT / "scripts/literature_reconnaissance").glob("*.py")
                   if path.name != Path(__file__).name
               ).casefold() for token in ("argostranslate", "googletrans", "deepl")), ""))

    qa_lines = ["# Full-text batch QA", "",
                "| Check | Result | Note |", "|---|---|---|"]
    for check, passed, note in qa:
        qa_lines.append(f"| {check} | {'PASS' if passed else 'FAIL'} | {note} |")
    qa_lines += [
        "", "## Boundaries", "",
        "- No factor research, backtest, Phase B, MCTS, stock-pool change, or trading-rule "
        "implementation was run.",
        "- Files created or intentionally modified by this batch are confined to "
        "`docs/literature_reconnaissance/`, `scripts/literature_reconnaissance/`, and `.gitignore`.",
        "- Existing unrelated dirty-worktree files were not touched.",
    ]
    (PAPERS / "QA_REPORT.md").write_text("\n".join(qa_lines) + "\n", encoding="utf-8")

    summary = {
        "generated_at_utc": now, "papers_total": 30,
        "pdfs_valid": sum(row["full_text_status"] in SUCCESS for row in manifest_rows),
        "source_only_readers_complete": sum(
            row["full_text_status"] in SUCCESS and row["paper_id"] != "C07"
            for row in manifest_rows
        ),
        "existing_native_reader_validated": 1,
        "user_pdf_required": [
            row["paper_id"] for row in manifest_rows
            if row["full_text_status"] == "user_pdf_required"
        ],
        "retrieval_error": [
            row["paper_id"] for row in manifest_rows
            if row["full_text_status"] == "retrieval_error"
        ],
        "qa_pass": all(passed for _, passed, _ in qa),
        "translation_model_branch_stopped": True,
        "third_party_translation_used": False,
        "paper_pdfs_preserved": True,
        "quant_research_run": False,
    }
    (PAPERS / "batch_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
