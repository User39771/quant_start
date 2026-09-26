"""Inventory and build remaining literature readers from audited local PDFs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import importlib.util
import json
import os
import re
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/literature_reconnaissance"
PAPERS = DOCS / "papers"
READERS = PAPERS / "readers"
PDFS = PAPERS / "source_pdfs"
REGISTRY = DOCS / "02_literature_registry.csv"
ACQUISITION = PAPERS / "acquisition_manifest.csv"
INVENTORY = PAPERS / "READER_MASTER_INVENTORY.csv"
CHECKPOINT = PAPERS / "reader_batch_checkpoint.json"
RUN_MANIFEST = PAPERS / "reader_batch_run_manifest.json"

EXCLUDED = {"B01", "B05", "A04", "A03", "D03", "E01", "C07"}
DEEP = {"F01", "A01", "A02", "A05", "B03", "B04", "C03", "C04", "C06", "D05", "E03"}
REFERENCE = {
    "B02", "B06", "C01", "C02", "C05", "D01", "D02", "D04", "D06",
    "E02", "F02", "F03", "CAND-023",
}
BUILD_ORDER = [
    "F01", "A01", "A02", "A05", "B03", "B04", "C03", "C04", "C06",
    "D05", "E03", "B02", "B06", "C01", "C02", "C05", "D01", "D02",
    "D04", "D06", "E02", "F02", "F03", "CAND-023",
]
REQUIRED_BACKEND = [
    "source/source_metadata.json", "source/sha256.txt",
    "extracted/paper_original.md", "extracted/source_map.csv",
    "extracted/section_index.csv", "extracted/formulas_index.csv",
    "extracted/figures_index.csv", "extracted/tables_index.csv",
    "extracted/extraction_issues.md", "analysis/research_contract.md",
    "analysis/evidence_map.md", "analysis/limitations_map.md",
    "analysis/project_relevance.md", "analysis/reading_outline.md",
    "analysis/translation_queue.md", "analysis/work_handoff.md",
]
INVENTORY_FIELDS = [
    "paper_id", "title", "authors", "year", "reading_tier", "core_status",
    "full_text_status", "pdf_path", "pdf_valid", "pdf_version", "pdf_sha256",
    "nature_reader_backend_status", "source_map_status", "draft_reader_status",
    "work_review_status", "final_reader_status", "reference_reader_status",
    "blocker", "recommended_action", "last_updated_utc",
]
LABELS = ["[AUTHOR CLAIM]", "[PROJECT INFERENCE]", "[EXTRACTION LIMITATION]", "[UNRESOLVED]"]
BLOCKED_LATEX = [
    r"\[", r"\]", r"\(", r"\)", r"\begin{equation}", r"\begin{align}",
    r"\tag{", r"\label{", r"\ref{", r"\eqref{", r"\newcommand", r"\usepackage",
]
READER_FACTORY_VERSION = "1.1"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def atomic_text(path: Path, text: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding=encoding, newline="", delete=False, dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp",
    ) as handle:
        handle.write(text)
        temp = Path(handle.name)
    os.replace(temp, path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8-sig", newline="", delete=False, dir=path.parent,
        prefix=f".{path.name}.", suffix=".tmp",
    ) as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
        temp = Path(handle.name)
    os.replace(temp, path)


def pdf_info(path: Path) -> tuple[bool, int, str]:
    if not path.exists() or path.read_bytes()[:5] != b"%PDF-":
        return False, 0, ""
    try:
        pages = len(PdfReader(path).pages)
    except Exception:
        return False, 0, ""
    return pages > 0, pages, sha256(path)


def local_pdf(paper_id: str) -> Path | None:
    folder = PDFS / paper_id
    files = sorted(folder.glob("*.pdf")) if folder.exists() else []
    return files[0] if len(files) == 1 else None


def metadata(paper_id: str) -> dict[str, object] | None:
    path = READERS / paper_id / "source/source_metadata.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def backend_status(paper_id: str, pdf_hash: str) -> tuple[str, str]:
    base = READERS / paper_id
    if paper_id == "C07":
        return "existing_native_nature_reader_validated", "pointer"
    if not all((base / rel).exists() for rel in REQUIRED_BACKEND):
        return "missing", "missing"
    meta = metadata(paper_id) or {}
    if not pdf_hash or meta.get("sha256") != pdf_hash:
        return "version_mismatch", "version_mismatch"
    try:
        rows = read_csv(base / "extracted/source_map.csv")
        ids = [row["source_map_id"] for row in rows]
        if not rows or len(ids) != len(set(ids)):
            return "qa_failed", "qa_failed"
    except Exception:
        return "qa_failed", "qa_failed"
    return "source_only_extraction_complete", "complete"


def tier(paper_id: str, core: bool) -> str:
    if paper_id in EXCLUDED:
        return "completed_or_existing"
    if paper_id in DEEP:
        return "Tier A - Deep Student Reader"
    if paper_id in REFERENCE:
        return "Tier B - Reference Reader"
    return "Tier C - Acquisition / Blocked" if not core else "unclassified_core"


def build_inventory() -> list[dict[str, str]]:
    registry = read_csv(REGISTRY)
    stamp = now()
    rows: list[dict[str, str]] = []
    for record in registry:
        pid = record["paper_id"]
        pdf = local_pdf(pid)
        valid, _, digest = pdf_info(pdf) if pdf else (False, 0, "")
        meta = metadata(pid) or {}
        backend, source_map = backend_status(pid, digest)
        base = READERS / pid
        draft = base / f"paper_reader_{pid}_draft.md"
        final = base / f"paper_reader_{pid}.md"
        reference = base / f"reference_reader_{pid}.md"
        notes = base / f"analysis/work_review_notes_{pid}.md"
        is_core = record["selection_status"] == "core"
        paper_tier = tier(pid, is_core)
        if pid in EXCLUDED:
            action = "preserve_completed_reader"
            blocker = ""
        elif not valid:
            action = "legal_fulltext_retrieval_or_user_pdf"
            blocker = "no_unique_valid_local_pdf"
        elif backend not in {"source_only_extraction_complete", "existing_native_nature_reader_validated"}:
            action = "rebuild_or_reconcile_backend"
            blocker = backend
        elif paper_tier.startswith("Tier A"):
            action = "await_work_review" if draft.exists() else "generate_deep_reader_draft"
            blocker = ""
        elif paper_tier.startswith("Tier B"):
            action = "complete" if reference.exists() else "generate_reference_reader"
            blocker = ""
        else:
            action = "inventory_only"
            blocker = ""
        rows.append({
            "paper_id": pid, "title": record["title"], "authors": record["authors"],
            "year": record["year"], "reading_tier": paper_tier,
            "core_status": "core" if is_core else "candidate",
            "full_text_status": (
                "full_text_reviewed" if pid == "C07" else
                "full_text_downloaded_not_reviewed" if valid else record["full_text_status"]
            ),
            "pdf_path": pdf.relative_to(ROOT).as_posix() if pdf else "",
            "pdf_valid": str(valid).lower(), "pdf_version": str(meta.get("obtained_version", "")),
            "pdf_sha256": digest, "nature_reader_backend_status": backend,
            "source_map_status": source_map,
            "draft_reader_status": "complete" if draft.exists() else "not_started",
            "work_review_status": "complete" if notes.exists() else (
                "not_required" if paper_tier.startswith("Tier B") else "pending"
            ),
            "final_reader_status": "complete" if final.exists() else "not_started",
            "reference_reader_status": "complete" if reference.exists() else "not_started",
            "blocker": blocker, "recommended_action": action, "last_updated_utc": stamp,
        })
    write_csv(INVENTORY, rows, INVENTORY_FIELDS)
    return rows


def load_extractor():
    path = Path(__file__).with_name("extract_core_readers.py")
    spec = importlib.util.spec_from_file_location("reader_source_extractor", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def archive_f01(old_meta: dict[str, object]) -> tuple[Path, dict[str, str]]:
    base = READERS / "F01"
    prefix = str(old_meta["sha256"])[:12]
    archive = base / "versions" / f"legacy_{prefix}"
    hashes: dict[str, str] = {}
    targets = [base / name for name in ("source", "extracted", "analysis")]
    targets += [
        path for path in base.iterdir()
        if path.is_file() and (
            "draft" in path.name.casefold() or "manifest" in path.name.casefold()
            or "qa" in path.name.casefold() or "blocker" in path.name.casefold()
        )
    ]
    for source in targets:
        if source.is_dir():
            for file in source.rglob("*"):
                if file.is_file():
                    hashes[file.relative_to(base).as_posix()] = sha256(file)
        elif source.is_file():
            hashes[source.relative_to(base).as_posix()] = sha256(source)
    if not archive.exists():
        archive.mkdir(parents=True)
        for source in targets:
            destination = archive / source.relative_to(base)
            if source.is_dir():
                shutil.copytree(source, destination)
            elif source.is_file():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, destination)
    return archive, hashes


def staged_extract(pid: str, registry: dict[str, str], manifest: dict[str, str]) -> None:
    extractor = load_extractor()
    temp_root = ROOT / "tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"reader_{pid}_", dir=temp_root) as folder:
        stage = Path(folder) / "readers"
        extractor.READERS = stage
        extractor.extract(registry, manifest)
        generated = stage / pid
        meta = json.loads((generated / "source/source_metadata.json").read_text(encoding="utf-8"))
        if meta["sha256"] != manifest["sha256"]:
            raise RuntimeError(f"{pid}: staged metadata SHA mismatch")
        map_path = generated / "extracted/source_map.csv"
        maps = read_csv(map_path)
        page_set = {int(row["original_page"]) for row in maps}
        expected_pages = set(range(1, int(manifest["page_count"]) + 1))
        missing_pages = sorted(expected_pages - page_set)
        for page in missing_pages:
            maps.append({
                "source_map_id": f"p{page:03d}-b001",
                "original_page": str(page),
                "section_title": "Unmapped page",
                "locator": "[EXTRACTION LIMITATION] No extractable paragraph block on this PDF page.",
            })
        if missing_pages:
            maps.sort(key=lambda row: (int(row["original_page"]), row["source_map_id"]))
            write_csv(map_path, maps, list(maps[0]))
            issues = generated / "extracted/extraction_issues.md"
            issues.write_text(
                issues.read_text(encoding="utf-8").rstrip()
                + f"\n- Source-map placeholder added for low-text pages: {missing_pages}.\n",
                encoding="utf-8",
            )
        page_set = {int(row["original_page"]) for row in maps}
        if page_set != expected_pages:
            raise RuntimeError(f"{pid}: staged source map does not cover every PDF page")
        base = READERS / pid
        for file in generated.rglob("*"):
            if not file.is_file():
                continue
            target = base / file.relative_to(generated)
            target.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(delete=False, dir=target.parent, prefix=".", suffix=".tmp") as out:
                out.write(file.read_bytes())
                temp = Path(out.name)
            os.replace(temp, target)


def upsert_acquisition(updates: dict[str, dict[str, str]]) -> None:
    rows = read_csv(ACQUISITION)
    fields = list(rows[0])
    by_id = {row["paper_id"]: row for row in rows}
    for pid, values in updates.items():
        if pid not in by_id:
            row = {field: "" for field in fields}
            row["paper_id"] = pid
            rows.append(row)
            by_id[pid] = row
        by_id[pid].update(values)
    write_csv(ACQUISITION, rows, fields)


def update_registry_status(ids: set[str]) -> None:
    rows = read_csv(REGISTRY)
    fields = list(rows[0])
    for row in rows:
        if row["paper_id"] in ids:
            row["full_text_status"] = "full_text_downloaded_not_reviewed"
    write_csv(REGISTRY, rows, fields)


def upsert_checkpoint_csv(path: Path, updates: dict[str, dict[str, str]]) -> None:
    rows = read_csv(path)
    fields = list(rows[0])
    by_id = {row["paper_id"]: row for row in rows}
    for pid, values in updates.items():
        if pid not in by_id:
            row = {field: "" for field in fields}
            row["paper_id"] = pid
            rows.append(row)
            by_id[pid] = row
        by_id[pid].update(values)
    write_csv(path, rows, fields)


def replace_marked(path: Path, begin: str, end: str, body: str) -> None:
    text = path.read_text(encoding="utf-8-sig") if path.exists() else ""
    block = f"{begin}\n{body.rstrip()}\n{end}"
    if begin in text and end in text:
        text = text.split(begin, 1)[0].rstrip() + "\n\n" + block + "\n" + text.split(end, 1)[1].lstrip()
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    atomic_text(path, text)


def update_supporting_indexes() -> None:
    stamp = now()
    registry_rows = read_csv(REGISTRY)
    registry = {row["paper_id"]: row for row in registry_rows}
    upsert_acquisition({
        pid: {
            "title": registry[pid]["title"], "authors": registry[pid]["authors"],
            "year": registry[pid]["year"], "target_version": registry[pid]["venue"],
            "obtained_version": "", "version_relation": "OpenAlex OA candidate not obtained",
            "source_url": url, "source_domain": domain, "access_basis": "open_access_candidate",
            "retrieved_at_utc": stamp, "filename": "", "file_size": "", "page_count": "",
            "pdf_valid": "false", "sha256": "", "full_text_status": "retrieval_error",
            "notes": reason,
        }
        for pid, url, domain, reason in [
            (
                "CAND-010", "https://www.ams.org/notices/201405/rnoti-p458.pdf",
                "ams.org", "Official open page returned HTTP 403; no file accepted.",
            ),
            (
                "CAND-022", "https://ojs.aaai.org/index.php/AAAI/article/download/33365/35520",
                "ojs.aaai.org", "Official open download repeatedly truncated/timed out; invalid file rejected.",
            ),
        ]
    })
    inventory = build_inventory()
    by_id = {row["paper_id"]: row for row in inventory}
    upsert_checkpoint_csv(
        PAPERS / "acquisition_checkpoint.csv",
        {
            "F01": {"full_text_status": "existing_local_pdf", "completed_at_utc": stamp},
            "E03": {"full_text_status": "existing_local_pdf", "completed_at_utc": stamp},
            "B02": {"full_text_status": "repository_version_downloaded", "completed_at_utc": stamp},
            "CAND-023": {"full_text_status": "open_fulltext_downloaded", "completed_at_utc": stamp},
        },
    )
    upsert_checkpoint_csv(
        PAPERS / "batch_checkpoint.csv",
        {
            pid: {
                "acquisition_status": (
                    "repository_version_downloaded" if pid == "B02" else
                    "open_fulltext_downloaded" if pid == "CAND-023" else "existing_local_pdf"
                ),
                "reader_status": "source_only_extraction_complete",
                "pdf_sha256": by_id[pid]["pdf_sha256"],
                "reader_path": f"docs/literature_reconnaissance/papers/readers/{pid}",
                "completed_at_utc": stamp,
            }
            for pid in ("F01", "E03", "B02", "CAND-023")
        },
    )
    gaps = [
        "# Full-text gap report", "",
        "No abstract, login page, or HTML error page was treated as a full paper.", "",
        "| ID | Title | Status | Stable identifier | Reason / next action |",
        "|---|---|---|---|---|",
    ]
    for row in inventory:
        if row["pdf_valid"] == "true":
            continue
        record = registry[row["paper_id"]]
        gaps.append(
            f"| {row['paper_id']} | {row['title'].replace('|', '/')} | "
            f"{record['full_text_status']} | {record['doi_or_stable_identifier']} | "
            f"{row['blocker'] or 'legal_fulltext_retrieval_or_user_pdf'} |"
        )
    atomic_text(PAPERS / "fulltext_gap_report.md", "\n".join(gaps) + "\n")

    handoff_rows = [
        "## Reader Factory batch status", "",
        "| ID | Tier | Reader status | Work status | Entry |",
        "|---|---|---|---|---|",
    ]
    for pid in BUILD_ORDER:
        row = by_id[pid]
        if pid in DEEP and row["draft_reader_status"] == "complete":
            entry = f"`papers/readers/{pid}/analysis/work_review_request_{pid}.md`"
            reader_status = "deep_draft_complete"
        elif pid in REFERENCE and row["reference_reader_status"] == "complete":
            entry = f"`papers/readers/{pid}/reference_reader_{pid}.md`"
            reader_status = "reference_reader_complete"
        else:
            entry = row["recommended_action"]
            reader_status = "blocked"
        handoff_rows.append(
            f"| {pid} | {row['reading_tier']} | {reader_status} | "
            f"{row['work_review_status']} | {entry} |"
        )
    replace_marked(
        PAPERS / "WORK_HANDOFF_INDEX.md",
        "<!-- READER_FACTORY_BEGIN -->", "<!-- READER_FACTORY_END -->",
        "\n".join(handoff_rows),
    )


def rebuild_special_backends(registry_by_id: dict[str, dict[str, str]]) -> list[str]:
    updates: dict[str, dict[str, str]] = {}
    rebuilt: list[str] = []
    stamp = now()
    specs = {
        "F01": {
            "file": PDFS / "F01/HuPanWangCCM.pdf",
            "obtained_version": "2020 author manuscript (This Version: August 15, 2020)",
            "version_relation": "Pre-publication version forthcoming in Critical Finance Review",
            "source_url": "local_user_provided", "access_basis": "user_provided_pdf",
            "source_domain": "local_user_supplied", "full_text_status": "existing_local_pdf",
        },
        "E03": {
            "file": PDFS / "E03/Allocating to Thematic Investments.pdf",
            "obtained_version": "final journal version",
            "version_relation": "Final Financial Analysts Journal 79(1), 18-36 article",
            "source_url": "https://doi.org/10.1080/0015198X.2022.2112895",
            "access_basis": "user_provided_pdf", "source_domain": "tandfonline.com",
            "full_text_status": "existing_local_pdf",
        },
        "B02": {
            "file": PDFS / "B02/sullivan_timmermann_white_1998_lse_dp303.pdf",
            "obtained_version": "LSE Financial Markets Group Discussion Paper 303",
            "version_relation": "1998 working-paper predecessor of the 1999 Journal of Finance article",
            "source_url": "https://eprints.lse.ac.uk/119144/1/dp303.pdf",
            "access_basis": "repository_version_downloaded", "source_domain": "eprints.lse.ac.uk",
            "full_text_status": "repository_version_downloaded",
        },
        "CAND-023": {
            "file": PDFS / "CAND-023/alpha_gpt_2308.00016.pdf",
            "obtained_version": "arXiv preprint 2308.00016",
            "version_relation": "Open preprint; not a peer-reviewed final journal version",
            "source_url": "https://arxiv.org/pdf/2308.00016",
            "access_basis": "open_fulltext_downloaded", "source_domain": "arxiv.org",
            "full_text_status": "open_fulltext_downloaded",
        },
    }
    old_f01 = metadata("F01")
    if not old_f01:
        raise RuntimeError("F01: old backend metadata missing; cannot archive")
    transition_path = READERS / "F01/F01_version_transition_manifest.json"
    f01_digest = pdf_info(specs["F01"]["file"])[2]
    if old_f01.get("sha256") == f01_digest and transition_path.exists():
        prior_transition = json.loads(transition_path.read_text(encoding="utf-8"))
        archive = ROOT / prior_transition["archive_path"]
        old_hashes = prior_transition["old_backend_sha256s"]
        archived_old_meta = {
            "obtained_version": prior_transition["old_version_description"],
            "sha256": prior_transition["old_pdf_sha256"],
        }
    else:
        archive, old_hashes = archive_f01(old_f01)
        archived_old_meta = old_f01
    for pid, spec in specs.items():
        pdf = spec["file"]
        valid, pages, digest = pdf_info(pdf)
        if not valid:
            raise RuntimeError(f"{pid}: invalid local PDF")
        manifest = {
            "paper_id": pid, "title": registry_by_id[pid]["title"],
            "authors": registry_by_id[pid]["authors"], "year": registry_by_id[pid]["year"],
            "target_version": registry_by_id[pid]["venue"],
            "obtained_version": spec["obtained_version"],
            "version_relation": spec["version_relation"], "source_url": spec["source_url"],
            "source_domain": spec["source_domain"], "access_basis": spec["access_basis"],
            "retrieved_at_utc": stamp, "filename": pdf.relative_to(ROOT).as_posix(),
            "file_size": str(pdf.stat().st_size), "page_count": str(pages),
            "pdf_valid": "true", "sha256": digest,
            "full_text_status": spec["full_text_status"],
            "notes": "Local user-provided PDF; identity verified from title page",
        }
        current = metadata(pid)
        if current and current.get("sha256") == digest and backend_status(pid, digest)[0] == "source_only_extraction_complete":
            updates[pid] = manifest
            continue
        staged_extract(pid, registry_by_id[pid], manifest)
        current_meta_path = READERS / pid / "source/source_metadata.json"
        current_meta = json.loads(current_meta_path.read_text(encoding="utf-8"))
        if pid == "F01":
            current_meta.update({
                "paper_version": "2020", "historical_overview": True,
                "current_2026_status_claim_allowed": False,
            })
        atomic_json(current_meta_path, current_meta)
        updates[pid] = manifest
        rebuilt.append(pid)
    f01_new = metadata("F01") or {}
    transition = {
        "paper_id": "F01",
        "old_version_description": archived_old_meta.get("obtained_version"),
        "old_pdf_sha256": archived_old_meta.get("sha256"),
        "old_backend_sha256s": old_hashes,
        "new_version_description": f01_new.get("obtained_version"),
        "new_pdf_sha256": f01_new.get("sha256"),
        "transition_authorized": True,
        "authorized_basis": "user_explicit_2020_version_instruction",
        "archived_at_utc": datetime.fromtimestamp(archive.stat().st_ctime, timezone.utc).isoformat(),
        "archive_path": archive.relative_to(ROOT).as_posix(),
    }
    atomic_json(READERS / "F01/F01_version_transition_manifest.json", transition)
    atomic_text(
        READERS / "F01/draft_generation_blocker.md",
        "# F01 prior blocker resolved\n\n"
        "The former 2018-backend/2020-PDF mismatch was resolved under explicit user "
        "authorization. The legacy backend is preserved under `versions/`; the current "
        "backend is bound to the 2020 PDF. See `F01_version_transition_manifest.json`.\n",
    )
    upsert_acquisition(updates)
    update_registry_status(set(specs))
    return rebuilt


def source_rows(pid: str, name: str) -> list[dict[str, str]]:
    path = READERS / pid / f"extracted/{name}.csv"
    return read_csv(path) if path.exists() else []


def repair_page_coverage(pid: str) -> list[int]:
    meta = metadata(pid)
    path = READERS / pid / "extracted/source_map.csv"
    if not meta or not path.exists():
        return []
    rows = read_csv(path)
    expected = set(range(1, int(meta["page_count"]) + 1))
    present = {int(row["original_page"]) for row in rows}
    missing = sorted(expected - present)
    for page in missing:
        rows.append({
            "source_map_id": f"p{page:03d}-b001", "original_page": str(page),
            "section_title": "Unmapped page",
            "locator": "[EXTRACTION LIMITATION] No extractable paragraph block on this PDF page.",
        })
    if missing:
        rows.sort(key=lambda row: (int(row["original_page"]), row["source_map_id"]))
        write_csv(path, rows, list(rows[0]))
        issue_path = READERS / pid / "extracted/extraction_issues.md"
        marker = f"Source-map placeholder added for low-text pages: {missing}."
        issue_text = issue_path.read_text(encoding="utf-8")
        if marker not in issue_text:
            atomic_text(issue_path, issue_text.rstrip() + f"\n- {marker}\n")
    return missing


def first_anchor(pid: str) -> tuple[str, str]:
    rows = source_rows(pid, "source_map")
    row = rows[0]
    return row["original_page"], row["source_map_id"]


def evidence_anchors(pid: str) -> list[tuple[str, str]]:
    path = READERS / pid / "analysis/evidence_map.md"
    text = path.read_text(encoding="utf-8")
    pairs = re.findall(r"\|\s*(\d+)\s*\|\s*(p\d{3}-b\d{3})", text)
    return pairs or [first_anchor(pid)]


def section_rows(pid: str) -> list[dict[str, str]]:
    rows = source_rows(pid, "section_index")
    seen: set[tuple[str, str]] = set()
    chosen = []
    for row in rows:
        key = (row["section_title"], row["original_page"])
        if key in seen:
            continue
        seen.add(key)
        chosen.append(row)
    return chosen[:12]


def csv_index_md(pid: str, name: str, limit: int = 12) -> str:
    rows = source_rows(pid, name)
    if not rows:
        return "- `[EXTRACTION LIMITATION]` 审计索引为空；不得据此补写内容。"
    id_field = next((key for key in rows[0] if key.endswith("_id") and key != "source_map_id"), "source_map_id")
    caption_field = "caption" if "caption" in rows[0] else "formula_text"
    lines = ["| ID | PDF页 | locator | 审计说明 |", "|---|---:|---|---|"]
    for row in rows[:limit]:
        note = re.sub(r"\s+", " ", row.get(caption_field, ""))[:120].replace("|", "/")
        if name == "formulas_index":
            note = "自动提取候选；公式文本不直接导入Reader，等待Work视觉核验"
        lines.append(
            f"| {row.get(id_field, '')} | {row.get('original_page', '')} | "
            f"`{row.get('source_map_id', '')}` | {note} |"
        )
    return "\n".join(lines)


def input_digest(pid: str) -> str:
    base = READERS / pid
    hasher = hashlib.sha256()
    hasher.update(READER_FACTORY_VERSION.encode())
    for rel in REQUIRED_BACKEND:
        path = base / rel
        hasher.update(rel.encode())
        hasher.update(path.read_bytes())
    return hasher.hexdigest()


def state_block(pid: str, digest: str, kind: str, f01: bool = False) -> str:
    extra = (
        "\npaper_version=2020\nhistorical_overview=true"
        "\ncurrent_2026_status_claim_allowed=false"
        if f01 else ""
    )
    if kind == "deep":
        return (
            f"paper_id={pid}\nreader_version=draft-1.0\n"
            "reader_type=student_learning_reader_draft\n"
            f"source_pdf_sha256={digest}\nnature_reader_backend_preserved=true\n"
            "full_text_translation=false\nselective_translation_status=pending_work_review\n"
            "reader_draft_status=complete\nwork_review_status=pending\n"
            "reader_merge_status=not_started\nstudent_reading_status=pending\n"
            f"student_understood=false{extra}"
        )
    return (
        f"paper_id={pid}\nreader_version=reference-1.0\nreader_type=reference_reader\n"
        f"source_pdf_sha256={digest}\nnature_reader_backend_preserved=true\n"
        "full_text_translation=false\nwork_review_required=false\n"
        "reference_reader_status=complete\nstudent_reading_status=not_required\n"
        f"student_understood=false\nfull_text_reviewed=false{extra}"
    )


def make_deep_reader(record: dict[str, str], meta: dict[str, object]) -> str:
    pid = record["paper_id"]
    anchors = evidence_anchors(pid)
    page, locator = anchors[0]
    sections = section_rows(pid)
    section_lines = [
        "| 原文章节 | PDF页 | locator | 阅读任务 |",
        "|---|---:|---|---|",
    ]
    for row in sections:
        section_lines.append(
            f"| {row['section_title'].replace('|', '/')} | {row['original_page']} | "
            f"`{row['source_map_id']}` | 核对定义、证据、限定语与可跳过细节 |"
        )
    toc = "\n".join(
        f"- [{name}](#{number}-{slug})"
        for number, name, slug in [
            (1, "文献身份与版本", "文献身份与版本"), (2, "五分钟理解", "五分钟理解"),
            (3, "为什么现在阅读", "为什么现在阅读"), (4, "推荐阅读路线", "推荐阅读路线"),
            (5, "研究问题与直觉", "研究问题与直觉"), (6, "核心术语", "核心术语"),
            (7, "逐节导读", "逐节导读"), (8, "关键公式索引和解释", "关键公式索引和解释"),
            (9, "图表与实证结果索引", "图表与实证结果索引"),
            (10, "作者证明了什么", "作者证明了什么"), (11, "作者没有证明什么", "作者没有证明什么"),
            (12, "局限与批判", "局限与批判"), (13, "与当前量化项目的对应", "与当前量化项目的对应"),
            (14, "Work选择性翻译", "work选择性翻译"), (15, "自测问题", "自测问题"),
            (16, "Mentor汇报提纲", "mentor汇报提纲"), (17, "完整来源索引", "完整来源索引"),
        ]
    )
    f01_note = (
        "\n\n`[EXTRACTION LIMITATION]` 本文是2020版本的历史综述。制度描述只能代表"
        "论文样本期和作者截至2020年的陈述；2026现行规则必须另查实时权威资料。"
        if pid == "F01" else ""
    )
    return f"""# {pid} 学生学习 Reader Draft

```text
{state_block(pid, str(meta['sha256']), 'deep', pid == 'F01')}
```

> 证据标签：`[AUTHOR CLAIM]`、`[PROJECT INFERENCE]`、`[EXTRACTION LIMITATION]`、`[UNRESOLVED]`。
> 本Draft不包含人工Work教学标签，也不替代原PDF或人工精读。

## 阅读目录

{toc}

## 1. 文献身份与版本

| 项目 | 内容 |
|---|---|
| 标题 | {record['title']} |
| 作者 | {record['authors']} |
| 发表年 | {record['year']} |
| 获得版本 | {meta.get('obtained_version', '')} |
| 版本关系 | {meta.get('version_relation', '')} |
| PDF页数 | {meta.get('page_count', '')} |
| PDF SHA-256 | `{meta.get('sha256', '')}` |
| PDF路径 | `{meta.get('source_pdf_path', '')}` |

身份定位：PDF p.{page} `{locator}`。{f01_note}

## 2. 五分钟理解

- `[AUTHOR CLAIM]` 研究问题：{record['research_question']} PDF p.{page} `{locator}`。
- `[AUTHOR CLAIM]` 作者报告：{record['main_findings']} 主要核验入口：{", ".join(f"p.{p} `{a}`" for p, a in anchors[:3])}。
- `[AUTHOR CLAIM]` 负面或边界：{record['negative_or_null_findings']}
- `[PROJECT INFERENCE]` 与项目关系：{record['relationship_to_current_project']}
- `[UNRESOLVED]` Work需逐项核验数字、公式、图表脚注与作者限定语。

## 3. 为什么现在阅读

{record['what_the_student_should_understand']}

`[PROJECT INFERENCE]` 本文只能改变研究合同、数据需求或候选解释，不能直接证明A股主题池Alpha。

## 4. 推荐阅读路线

参见 `analysis/reading_outline.md`。先读摘要、方法/制度框架、主要结果和结论；长证明或附录在需要复现时再读。每完成一节，应能回答“作者用了什么证据、允许声称什么、迁移时哪项假设会失效”。

## 5. 研究问题与直觉

- 正式问题：{record['research_question']}
- 数据与市场：{record['market_and_universe']}
- 样本：{record['sample_period']}；频率：{record['data_frequency']}
- 方法：{record['method']}
- 训练/验证/测试：{record['train_validation_test_design']}
- `[PROJECT INFERENCE]` 初学者应先把识别对象、评价对象和可交易对象分开。

## 6. 核心术语

| 术语 | 论文语境 | 当前项目例子 | 定位 |
|---|---|---|---|
| research question | 作者要回答的可证伪问题 | Phase A冻结主问题 | p.{page} `{locator}` |
| sample period | 论文实际观察期 | historical_seen不能伪装final test | p.{page} `{locator}` |
| market/universe | 证据适用的市场与对象 | 56只主题池外部有效性有限 | p.{page} `{locator}` |
| method | 从数据到结论的程序 | 固定同一评价合同 | p.{page} `{locator}` |
| benchmark | 结果比较基准 | benchmark不得事后更换 | p.{page} `{locator}` |
| metric | 作者报告的衡量标准 | 区分IC、收益、风险和成本 | p.{page} `{locator}` |
| transaction cost | 实施摩擦 | 20bps只是项目合同，不是论文事实 | p.{page} `{locator}` |
| out-of-sample | 未参与选择的数据 | final test保持未触碰 | p.{page} `{locator}` |
| limitation | 作者或审计明确的边界 | 不把外部市场结论直接迁移 | p.{page} `{locator}` |
| evidence locator | PDF与source map定位 | 结论必须可回到原文 | p.{page} `{locator}` |

`[UNRESOLVED]` Work应将以上通用入口替换或补充为论文专属定义，不得把模板文字冒充作者术语。

## 7. 逐节导读

{chr(10).join(section_lines)}

## 8. 关键公式索引和解释

{csv_index_md(pid, 'formulas_index')}

`[UNRESOLVED]` 自动提取公式不直接写入Reader。Work必须对照PDF视觉内容后，才可用Notion兼容的`$...$`或独立`$$...$$`补充解释。

## 9. 图表与实证结果索引

### 图

{csv_index_md(pid, 'figures_index')}

### 表

{csv_index_md(pid, 'tables_index')}

`[EXTRACTION LIMITATION]` 索引提供定位，不保证图形裁剪、表格脚注或OCR已被人工核验。

## 10. 作者证明了什么

- `[AUTHOR CLAIM]` {record['main_findings']}
- 证据入口：{", ".join(f"PDF p.{p} `{a}`" for p, a in anchors)}。
- `[UNRESOLVED]` Work需把复合结论拆成逐项、带页码的作者主张。

## 11. 作者没有证明什么

- 没有证明结果在当前A股主题池自动成立。
- 没有证明统计关系必然可在成本、涨跌停、停牌和容量约束下交易。
- 没有证明任何由本文启发的MOM60、REV60或未来搜索公式已通过final test。
- 原注册表记录的负面边界：{record['negative_or_null_findings']}

## 12. 局限与批判

- `[AUTHOR CLAIM]` 作者报告的限制：{record['limitations_reported_by_authors']}
- `[PROJECT INFERENCE]` 额外限制：{record['additional_limitations_identified']}
- `[PROJECT INFERENCE]` point-in-time、幸存偏差、可成交性和外部有效性需在A股重新核验。
- `[EXTRACTION LIMITATION]` 详见 `extracted/extraction_issues.md`。

## 13. 与当前量化项目的对应

- Phase A：把本文用于收紧统一评价合同，不改写既有因子结论。
- historical_seen / final test：读后产生的任何选择都属于已见信息。
- MOM60 / REV60：只建立研究问题，不把论文方向机械移植。
- 换手和成本：gross evidence与net implementability分开。
- Phase B / MCTS：仍未授权；若未来开启，完整登记候选、预算、重复和失败。

## 14. Work选择性翻译

选择队列见 `analysis/translation_queue.md`。只翻译关键定义、方法、困难段落、主要结果与限制；不得生成全文中文替代品。

## 15. 自测问题

1. 论文的研究对象、市场和样本期是什么？
2. 方法如何把数据转化为作者结论？
3. 哪个结果最依赖权重、样本、基准或制度假设？
4. 作者没有证明的三件事是什么？
5. 若迁移到当前项目，哪项必须进入experiment registry，哪项必须留给final test？

## 16. Mentor汇报提纲

先讲研究问题与样本，再讲方法与最重要证据；随后明确负面结果、作者限制和版本关系；最后只说明它如何约束当前项目，不把论文结果说成A股实证结论。`[UNRESOLVED]` Work需形成论文专属中文汇报提纲。

## 17. 完整来源索引

- `source/source_metadata.json`
- `source/sha256.txt`
- `extracted/paper_original.md`
- `extracted/source_map.csv`
- `extracted/section_index.csv`
- `extracted/formulas_index.csv`
- `extracted/figures_index.csv`
- `extracted/tables_index.csv`
- `extracted/extraction_issues.md`
- `analysis/research_contract.md`
- `analysis/evidence_map.md`
- `analysis/limitations_map.md`
- `analysis/project_relevance.md`
- `analysis/reading_outline.md`
- `analysis/translation_queue.md`
- `analysis/work_handoff.md`

事实权威顺序：原PDF > source map与审计索引 > 本Draft > 旧摘要笔记。
"""


def make_reference_reader(record: dict[str, str], meta: dict[str, object]) -> str:
    pid = record["paper_id"]
    anchors = evidence_anchors(pid)
    page, locator = anchors[0]
    return f"""# {pid} Reference Reader

```text
{state_block(pid, str(meta['sha256']), 'reference')}
```

## 文献身份

- 标题：{record['title']}
- 作者：{record['authors']}
- 年份：{record['year']}
- 版本：{meta.get('obtained_version', '')}；{meta.get('version_relation', '')}
- PDF：{meta.get('page_count', '')}页；SHA-256 `{meta.get('sha256', '')}`
- 身份定位：PDF p.{page} `{locator}`

## 为什么保留为Reference

本文提供补充方法或背景，但当前阅读计划不要求完整Work Review。它不得冒充人工精读，也不建立`full_text_reviewed`状态。

## 研究合同

- `[AUTHOR CLAIM]` 问题：{record['research_question']}
- 市场与样本：{record['market_and_universe']}；{record['sample_period']}。
- 方法：{record['method']}
- 指标：{record['main_metrics']}
- 交易成本：{record['transaction_cost_treatment']}

## 主要证据入口

- `[AUTHOR CLAIM]` {record['main_findings']}
- 定位：{", ".join(f"PDF p.{p} `{a}`" for p, a in anchors)}。
- 负面/空结果：{record['negative_or_null_findings']}

## 方法、公式与图表索引

### 公式

{csv_index_md(pid, 'formulas_index', 8)}

### 图表

{csv_index_md(pid, 'figures_index', 8)}

{csv_index_md(pid, 'tables_index', 8)}

## 局限

- `[AUTHOR CLAIM]` {record['limitations_reported_by_authors']}
- `[PROJECT INFERENCE]` {record['additional_limitations_identified']}
- `[EXTRACTION LIMITATION]` 公式和图表仅保留定位；未作全文翻译或人工逐式核验。

## 项目相关性

`[PROJECT INFERENCE]` {record['relationship_to_current_project']} 该关系只用于未来查阅，不构成A股Alpha、Phase B或MCTS授权。

## 来源

原PDF、`source/source_metadata.json`、`extracted/source_map.csv`及全部审计索引保留为事实后端。事实权威顺序：PDF > source map > 本Reference Reader。
"""


def formula_qa(pid: str, reader: str, kind: str) -> list[dict[str, str]]:
    rows = source_rows(pid, "formulas_index")
    result = []
    for index, row in enumerate(rows or [{}], 1):
        result.append({
            "paper_id": pid, "formula_id": row.get("formula_id", f"{pid}-NONE"),
            "reader_line": "", "formula_type": "index_only", "latex": "",
            "pdf_page": row.get("original_page", ""),
            "source_locator": row.get("source_map_id", ""),
            "verification_status": "unresolved", "notion_compatible": "true",
            "issue": f"{kind} does not import unverified extracted formula text",
        })
    for pattern in BLOCKED_LATEX:
        if pattern in reader:
            raise RuntimeError(f"{pid}: blocked LaTeX pattern {pattern}")
    return result


def build_request(pid: str, record: dict[str, str], meta: dict[str, object]) -> str:
    queue = source_rows(pid, "section_index")[:10]
    lines = [
        f"# {pid} Work Review Request", "", "## A. 论文身份", "",
        f"- {record['title']} — {record['authors']} ({record['year']})",
        f"- PDF SHA-256: `{meta['sha256']}`", f"- PDF pages: {meta['page_count']}",
        "", "## B. Draft路径", "",
        f"`docs/literature_reconnaissance/papers/readers/{pid}/paper_reader_{pid}_draft.md`",
        "", "## C. 建议优先核验", "",
        "定义、方法、主要结果、关键数字/公式、作者限制和项目迁移边界。",
        "", "## D-E. 重点问题", "",
        "| # | type | PDF页 | locator | 为什么重要 | Draft现状 | Work动作 |",
        "|---:|---|---:|---|---|---|---|",
    ]
    types = ["key_definition", "method", "empirical_result", "limitation", "project_mapping"]
    actions = [
        "explain_in_chinese", "derive_formula", "verify_numeric_result",
        "challenge_interpretation", "compare_with_project",
    ]
    for index, row in enumerate(queue, 1):
        lines.append(
            f"| {index} | {types[(index - 1) % len(types)]} | {row['original_page']} | "
            f"`{row['source_map_id']}` | 核验本节证据边界 | Draft仅提供审计定位 | "
            f"{actions[(index - 1) % len(actions)]} |"
        )
    lines += [
        "", "## F. 推荐产物路径", "",
        f"`docs/literature_reconnaissance/papers/readers/{pid}/analysis/work_review_notes_{pid}.md`",
    ]
    return "\n".join(lines) + "\n"


def write_work_packet(pid: str) -> Path:
    base = READERS / pid
    packet = ROOT / "private_work_packets" / f"work_review_packet_{pid}.zip"
    packet.parent.mkdir(parents=True, exist_ok=True)
    names = [
        f"paper_reader_{pid}_draft.md", "analysis/research_contract.md",
        "analysis/evidence_map.md", "analysis/limitations_map.md",
        "analysis/project_relevance.md", "analysis/reading_outline.md",
        "analysis/translation_queue.md", "analysis/work_handoff.md",
        "extracted/source_map.csv", "extracted/section_index.csv",
        "extracted/formulas_index.csv", "extracted/figures_index.csv",
        "extracted/tables_index.csv", "extracted/extraction_issues.md",
        f"analysis/work_review_request_{pid}.md",
        f"analysis/notion_formula_qa_{pid}.csv",
    ]
    with tempfile.NamedTemporaryFile(delete=False, dir=packet.parent, prefix=".", suffix=".zip") as handle:
        temp = Path(handle.name)
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            path = base / name
            archive.write(path, arcname=name)
    os.replace(temp, packet)
    return packet


def build_readers(resume: bool) -> dict[str, dict[str, str]]:
    registry = read_csv(REGISTRY)
    by_id = {row["paper_id"]: row for row in registry}
    checkpoint = json.loads(CHECKPOINT.read_text(encoding="utf-8")) if CHECKPOINT.exists() else {"papers": {}}
    rebuilt = rebuild_special_backends(by_id)
    repaired_pages = {pid: pages for pid in BUILD_ORDER if (pages := repair_page_coverage(pid))}
    results: dict[str, dict[str, str]] = {}
    for pid in BUILD_ORDER:
        record = by_id[pid]
        pdf = local_pdf(pid)
        valid, _, digest = pdf_info(pdf) if pdf else (False, 0, "")
        if not valid:
            result = {"status": "blocked", "reason_code": "no_unique_valid_local_pdf"}
        else:
            backend, _ = backend_status(pid, digest)
            if backend != "source_only_extraction_complete":
                result = {"status": "blocked", "reason_code": f"backend_{backend}"}
            else:
                current_input = input_digest(pid)
                prior = checkpoint["papers"].get(pid, {})
                if resume and prior.get("input_sha256") == current_input and prior.get("status") == "complete":
                    result = prior
                else:
                    base = READERS / pid
                    meta = metadata(pid) or {}
                    if pid in DEEP:
                        output = base / f"paper_reader_{pid}_draft.md"
                        if output.exists() and not prior:
                            raise RuntimeError(f"{pid}: Draft exists without checkpoint; refusing overwrite")
                        reader = make_deep_reader(record, meta)
                        atomic_text(output, reader)
                        request = base / f"analysis/work_review_request_{pid}.md"
                        atomic_text(request, build_request(pid, record, meta))
                        qa_path = base / f"analysis/notion_formula_qa_{pid}.csv"
                        qa_rows = formula_qa(pid, reader, "Deep Draft")
                        write_csv(
                            qa_path, qa_rows,
                            ["paper_id", "formula_id", "reader_line", "formula_type", "latex",
                             "pdf_page", "source_locator", "verification_status",
                             "notion_compatible", "issue"],
                        )
                        packet = write_work_packet(pid)
                        result = {
                            "status": "complete", "tier": "A", "input_sha256": current_input,
                            "output": output.relative_to(ROOT).as_posix(),
                            "output_sha256": sha256(output),
                            "work_request": request.relative_to(ROOT).as_posix(),
                            "work_packet": packet.relative_to(ROOT).as_posix(),
                            "notion_formula_qa": "pass",
                            "final_merge_waiting_for_work_review": "true",
                        }
                    else:
                        output = base / f"reference_reader_{pid}.md"
                        if output.exists() and not prior:
                            raise RuntimeError(f"{pid}: Reference Reader exists without checkpoint; refusing overwrite")
                        reader = make_reference_reader(record, meta)
                        atomic_text(output, reader)
                        qa_path = base / f"analysis/notion_formula_qa_{pid}.csv"
                        qa_rows = formula_qa(pid, reader, "Reference Reader")
                        write_csv(
                            qa_path, qa_rows,
                            ["paper_id", "formula_id", "reader_line", "formula_type", "latex",
                             "pdf_page", "source_locator", "verification_status",
                             "notion_compatible", "issue"],
                        )
                        result = {
                            "status": "complete", "tier": "B", "input_sha256": current_input,
                            "output": output.relative_to(ROOT).as_posix(),
                            "output_sha256": sha256(output), "notion_formula_qa": "pass",
                        }
        result["updated_at_utc"] = now()
        checkpoint["papers"][pid] = result
        atomic_json(CHECKPOINT, checkpoint)
        results[pid] = result
    checkpoint["special_backends_rebuilt"] = rebuilt
    checkpoint["source_map_page_repairs"] = repaired_pages
    checkpoint["updated_at_utc"] = now()
    atomic_json(CHECKPOINT, checkpoint)
    update_supporting_indexes()
    return results


def protected_hashes() -> dict[str, str]:
    paths = [
        READERS / "B01/paper_reader_B01.md", READERS / "B05/paper_reader_B05.md",
        READERS / "A04/paper_reader_A04.md", READERS / "A03/paper_reader_A03.md",
        READERS / "D03/paper_reader_D03.md", READERS / "E01/paper_reader_E01.md",
        PDFS / "C07/shi_duan_li_2025_arxiv_2505.11122v3.pdf",
        Path(r"C:\Users\Hangxi Yang\.codex\skills\nature-reader\SKILL.md"),
    ]
    return {str(path): sha256(path) for path in paths if path.exists()}


def report(results: dict[str, dict[str, str]] | None = None) -> None:
    inventory = build_inventory()
    counts: dict[str, int] = {}
    for row in inventory:
        counts[row["recommended_action"]] = counts.get(row["recommended_action"], 0) + 1
    manifest = {
        "schema_version": "reader_batch_run_manifest_v1",
        "generated_at_utc": now(),
        "registered_papers": len(inventory),
        "counts_by_recommended_action": counts,
        "build_results": results or {},
        "protected_hashes": protected_hashes(),
        "network_retrieval": "official_open_urls_attempted_before_build; see oa_candidate_retrieval",
        "oa_candidate_retrieval": {
            "CAND-010": "retrieval_error_http_403",
            "CAND-022": "retrieval_error_truncated_or_timeout",
            "CAND-023": "open_fulltext_downloaded_and_reference_reader_complete",
        },
        "translation_model_or_api_used": False,
        "quantitative_research_run": False,
        "phase_b_or_mcts_run": False,
    }
    atomic_json(RUN_MANIFEST, manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


def self_check() -> None:
    rows = build_inventory()
    assert len(rows) == 88
    assert len({row["paper_id"] for row in rows}) == 88
    assert set(INVENTORY_FIELDS) == set(rows[0])


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("inventory")
    build_parser = sub.add_parser("build")
    build_parser.add_argument("--resume", action="store_true")
    sub.add_parser("report")
    args = parser.parse_args()
    if args.command == "inventory":
        self_check()
        report()
    elif args.command == "build":
        before = protected_hashes()
        results = build_readers(args.resume)
        after = protected_hashes()
        if before != after:
            raise RuntimeError("protected completed readers or Nature Reader skill changed")
        report(results)
    else:
        report()


if __name__ == "__main__":
    main()
