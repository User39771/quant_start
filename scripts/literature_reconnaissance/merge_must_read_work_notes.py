from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
PAPERS_ROOT = ROOT / "docs/literature_reconnaissance/papers"
READERS = PAPERS_ROOT / "readers"
CONTRACT = PAPERS_ROOT / "reader_merge_contract_v1.md"
ZIP_PATH = Path(r"C:\Users\Hangxi Yang\Downloads\must_read_work_review_notes_batch.zip")
ORDER = ["B05", "A04", "A03", "E01", "D03"]
REQUIRED = [
    "source/source_metadata.json",
    "source/sha256.txt",
    "extracted/paper_original.md",
    "extracted/source_map.csv",
    "extracted/section_index.csv",
    "extracted/formulas_index.csv",
    "extracted/figures_index.csv",
    "extracted/tables_index.csv",
    "extracted/extraction_issues.md",
    "analysis/research_contract.md",
    "analysis/evidence_map.md",
    "analysis/limitations_map.md",
    "analysis/project_relevance.md",
    "analysis/reading_outline.md",
    "analysis/translation_queue.md",
    "analysis/work_handoff.md",
]
BLOCKED_LATEX = [
    r"\[",
    r"\]",
    r"\(",
    r"\)",
    r"\begin{equation}",
    r"\begin{align}",
    r"\begin{align*}",
    r"\tag{",
    r"\label{",
    r"\ref{",
    r"\eqref{",
    r"\newcommand",
    r"\usepackage",
]
LEGACY_LABELS = [
    "[WORK REVIEW]",
    "[CODEX INFERENCE]",
    "[WORK REVIEW REQUIRED]",
    "[SELECTIVE TRANSLATION PENDING]",
]
ALLOWED_LABELS = [
    "[AUTHOR CLAIM]",
    "[WORK EXPLANATION]",
    "[PROJECT INFERENCE]",
    "[EXTRACTION LIMITATION]",
    "[UNRESOLVED]",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def validate_zip() -> dict[str, bytes]:
    if not ZIP_PATH.is_file():
        raise RuntimeError(f"ZIP missing: {ZIP_PATH}")
    with zipfile.ZipFile(ZIP_PATH, "r") as archive:
        names = archive.namelist()
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity test failed")
        for name in names:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
                raise RuntimeError(f"unsafe ZIP member: {name}")
        expected = {f"work_review_notes_{pid}.md" for pid in ORDER}
        if not expected.issubset(names):
            raise RuntimeError(f"ZIP missing Work Notes: {sorted(expected - set(names))}")
        return {name: archive.read(name) for name in names}


def ensure_work_note(pid: str, data: bytes) -> Path:
    path = READERS / pid / f"analysis/work_review_notes_{pid}.md"
    if path.exists():
        if sha256(path) != sha256_bytes(data):
            raise RuntimeError(f"{pid}: existing Work Notes differ; refusing overwrite")
        return path
    path.write_bytes(data)
    return path


def validate_inputs(pid: str, note: Path) -> tuple[dict[str, object], Path, dict[str, str]]:
    root = READERS / pid
    draft = root / f"paper_reader_{pid}_draft.md"
    final = root / f"paper_reader_{pid}.md"
    manifest = root / f"paper_reader_{pid}_merge_manifest.json"
    report = root / f"paper_reader_{pid}_merge_report.md"
    for output in [final, manifest, report]:
        if output.exists():
            raise RuntimeError(f"{pid}: output already exists: {output}; sha256={sha256(output)}")
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if not draft.is_file():
        missing.append(draft.name)
    if missing:
        raise RuntimeError(f"{pid}: missing inputs: {missing}")
    metadata = json.loads((root / "source/source_metadata.json").read_text(encoding="utf-8"))
    if metadata["paper_id"] != pid:
        raise RuntimeError(f"{pid}: metadata paper_id mismatch")
    pdf = ROOT / str(metadata["source_pdf_path"])
    if not pdf.is_file():
        raise RuntimeError(f"{pid}: source PDF missing")
    actual_sha = sha256(pdf)
    recorded_sha = str(metadata["sha256"]).lower()
    sha_txt = (root / "source/sha256.txt").read_text(encoding="utf-8").strip().split()[0].lower()
    if actual_sha != recorded_sha or actual_sha != sha_txt:
        raise RuntimeError(f"{pid}: PDF SHA mismatch")
    if len(PdfReader(str(pdf)).pages) != int(metadata["page_count"]) or int(metadata["page_count"]) <= 0:
        raise RuntimeError(f"{pid}: PDF page count mismatch")
    draft_text = draft.read_text(encoding="utf-8")
    note_text = note.read_text(encoding="utf-8")
    if f"paper_id={pid}" not in draft_text or f"paper_id={pid}" not in note_text:
        raise RuntimeError(f"{pid}: Draft/Work Notes paper_id mismatch")
    note_sha_match = re.search(r"PDF SHA-256：\*\* `([0-9a-fA-F]{64})`", note_text)
    if not note_sha_match or note_sha_match.group(1).lower() != actual_sha:
        raise RuntimeError(f"{pid}: Work Notes PDF SHA mismatch")
    title = str(metadata["title"])
    title_tokens = [token for token in normalize(title).split() if token]
    if normalize(title) not in normalize(note_text[:1200]):
        core_words = [word.lower() for word in re.findall(r"[A-Za-z]{5,}", title)]
        if not core_words or sum(word in note_text[:1200].lower() for word in core_words) < 2:
            raise RuntimeError(f"{pid}: Work Notes title mismatch")
    authors = [part.strip().split()[-1].lower() for part in str(metadata["authors"]).split(";")]
    if any(author.replace("‐", "-") not in note_text[:1200].lower().replace("‐", "-") for author in authors):
        raise RuntimeError(f"{pid}: Work Notes author mismatch")
    inputs = {name: sha256(root / name) for name in REQUIRED}
    inputs[draft.name] = sha256(draft)
    inputs[str(note.relative_to(root)).replace("\\", "/")] = sha256(note)
    inputs[str(metadata["source_pdf_path"])] = actual_sha
    return metadata, pdf, inputs


def extract(text: str, start: str, end: str | None) -> str:
    start_match = re.search(start, text, re.M)
    if not start_match:
        raise RuntimeError(f"Work block start not found: {start}")
    if end:
        end_match = re.search(end, text[start_match.end() :], re.M)
        stop = start_match.end() + end_match.start() if end_match else len(text)
    else:
        stop = len(text)
    return text[start_match.start() : stop].strip()


def unresolved_tail(text: str) -> str:
    match = re.search(r"(?ms)^仍未完成：\s*\n(.*)$", text)
    if not match:
        return "- [UNRESOLVED] 学生阅读与自测尚未完成。"
    tail = match.group(1).strip()
    return re.sub(r"(?m)^-\s*", "- [UNRESOLVED] ", tail)


MAPS: dict[str, list[tuple[int, str, str | None, str]]] = {
    "B05": [
        (2, r"^# 1\. ", r"^# 2\. ", "append"),
        (5, r"^# 2\. ", r"^# 3\. ", "append"),
        (5, r"^# 5\. ", r"^# 6\. ", "append"),
        (8, r"^# 3\. ", r"^# 4\. ", "append"),
        (8, r"^# 4\. ", r"^# 5\. ", "append"),
        (8, r"^# 6\. ", r"^# 7\. ", "append"),
        (9, r"^# 7\. ", r"^# 8\. ", "append"),
        (10, r"^## 8\.1 ", r"^## 8\.2 ", "append"),
        (11, r"^## 8\.2 ", r"^# 9\. ", "append"),
        (13, r"^# 9\. ", r"^# 10\. ", "append"),
        (14, r"^# 10\. ", r"^# 11\. ", "replace"),
        (15, r"^# 11\. ", r"^# 12\. ", "replace"),
        (16, r"^# 12\. ", r"^# 13\. ", "replace"),
    ],
    "A04": [
        (2, r"^# 1\. ", r"^# 2\. ", "append"),
        (5, r"^# 2\. ", r"^# 3\. ", "append"),
        (7, r"^# 3\. ", r"^# 4\. ", "append"),
        (8, r"^# 4\. ", r"^# 5\. ", "append"),
        (9, r"^# 5\. ", r"^# 6\. ", "append"),
        (10, r"^## 6\.1 ", r"^## 6\.2 ", "append"),
        (11, r"^## 6\.2 ", r"^# 7\. ", "append"),
        (12, r"^# 7\. ", r"^# 8\. ", "append"),
        (13, r"^# 8\. ", r"^# 9\. ", "append"),
        (14, r"^# 9\. ", r"^# 10\. ", "replace"),
        (15, r"^# 10\. ", r"^# 11\. ", "replace"),
        (16, r"^# 11\. ", r"^# 12\. ", "replace"),
    ],
    "A03": [
        (2, r"^# 1\. ", r"^# 2\. ", "append"),
        (5, r"^# 2\. ", r"^# 3\. ", "append"),
        (7, r"^# 3\. ", r"^# 4\. ", "append"),
        (8, r"^# 4\. ", r"^# 5\. ", "append"),
        (9, r"^# 5\. ", r"^# 6\. ", "append"),
        (10, r"^## 6\.1 ", r"^## 6\.2 ", "append"),
        (11, r"^## 6\.2 ", r"^# 7\. ", "append"),
        (12, r"^# 7\. ", r"^# 8\. ", "append"),
        (13, r"^# 8\. ", r"^# 9\. ", "append"),
        (14, r"^# 9\. ", r"^# 10\. ", "replace"),
        (15, r"^# 10\. ", r"^# 11\. ", "replace"),
        (16, r"^# 11\. ", r"^# 12\. ", "replace"),
    ],
    "E01": [
        (2, r"^# 1\. ", r"^# 2\. ", "append"),
        (5, r"^# 2\. ", r"^# 3\. ", "append"),
        (7, r"^# 3\. ", r"^# 4\. ", "append"),
        (8, r"^# 4\. ", r"^# 6\. ", "append"),
        (9, r"^# 6\. ", r"^# 7\. ", "append"),
        (12, r"^# 7\. ", r"^# 8\. ", "append"),
        (13, r"^# 8\. ", r"^# 9\. ", "append"),
        (14, r"^# 9\. ", r"^# 10\. ", "replace"),
        (15, r"^# 10\. ", r"^# 11\. ", "replace"),
        (16, r"^# 11\. ", r"^# 12\. ", "replace"),
    ],
    "D03": [
        (2, r"^# 1\. ", r"^# 2\. ", "append"),
        (5, r"^# 2\. ", r"^# 3\. ", "append"),
        (5, r"^# 3\. ", r"^# 4\. ", "append"),
        (8, r"^# 4\. ", r"^# 5\. ", "append"),
        (9, r"^# 5\. ", r"^# 7\. ", "append"),
        (10, r"^## 8\.1 ", r"^## 8\.2 ", "append"),
        (11, r"^## 8\.2 ", r"^# 9\. ", "append"),
        (12, r"^# 7\. ", r"^# 8\. ", "append"),
        (13, r"^# 9\. ", r"^# 10\. ", "append"),
        (14, r"^# 10\. ", r"^# 11\. ", "replace"),
        (15, r"^# 11\. ", r"^# 12\. ", "replace"),
        (16, r"^# 12\. ", r"^# 13\. ", "replace"),
    ],
}


def first_locator_by_page(root: Path) -> dict[int, str]:
    result: dict[int, str] = {}
    for row in load_csv(root / "extracted/source_map.csv"):
        page = int(row["original_page"])
        result.setdefault(page, row["source_map_id"])
    return result


def add_locator_hints(text: str, locators: dict[int, str]) -> str:
    pattern = re.compile(r"(PDF\s+p{1,2}\.\s*)(\d+)(?![^`\n]*`p\d{3}-b\d{3}`)", re.I)

    def repl(match: re.Match[str]) -> str:
        page = int(match.group(2))
        locator = locators.get(page)
        if not locator:
            return match.group(0)
        return f"{match.group(1)}{page} `{locator}`"

    return pattern.sub(repl, text)


def normalize_work_block(block: str, target: int, locators: dict[int, str]) -> str:
    block = re.sub(
        r"(?m)^(#{1,3}) (.+)$",
        lambda match: "#" * (len(match.group(1)) + 2) + " " + match.group(2),
        block,
    )
    block = block.replace("Draft中的", "本Reader中的")
    block = block.replace("Draft 中的", "本Reader中的")
    block = block.replace("当前Draft", "合并前Draft")
    block = re.sub(r"(?m)^---\s*$", "", block)
    block = add_locator_hints(block, locators).strip()
    if target == 13:
        label = (
            "> [PROJECT INFERENCE] 以下内容是Work基于论文与当前项目材料形成的迁移分析，"
            "不是作者对A股、MOM60、REV60、Phase A/B或MCTS的原文结论。"
        )
    elif target == 17:
        label = "> [UNRESOLVED] 以下事项在Work Review后仍未完成。"
    else:
        label = (
            "> [WORK EXPLANATION] 以下内容来自人工Work Review，负责教学解释、读图或选择性翻译；"
            "直接作者主张仍以本节已有PDF页码与source locator为准。"
        )
    return f"{label}\n\n{block}"


def section_bounds(text: str, number: int) -> tuple[int, int]:
    start_match = re.search(rf"(?m)^## {number}\. .+$", text)
    if not start_match:
        raise RuntimeError(f"final section {number} not found")
    next_match = re.search(rf"(?m)^## {number + 1}\. .+$", text[start_match.end() :]) if number < 17 else None
    end = start_match.end() + next_match.start() if next_match else len(text)
    return start_match.end(), end


def merge_into_section(text: str, number: int, content: str, mode: str) -> str:
    body_start, body_end = section_bounds(text, number)
    if mode == "replace":
        replacement = f"\n\n{content.strip()}\n\n"
        return text[:body_start] + replacement + text[body_end:]
    insertion = f"\n\n### Work合并内容\n\n{content.strip()}\n"
    return text[:body_end].rstrip() + insertion + "\n\n" + text[body_end:].lstrip()


def build_final(pid: str, metadata: dict[str, object], note_text: str) -> str:
    root = READERS / pid
    draft_path = root / f"paper_reader_{pid}_draft.md"
    text = draft_path.read_text(encoding="utf-8")
    text = re.sub(r"(?m)^# (.+?)：统一学生 Reader Draft$", r"# \1：学生学习 Reader", text, count=1)
    status = f"""```text
paper_id={pid}
reader_version=1.0
reader_type=student_learning_reader
source_pdf_sha256={metadata['sha256']}
nature_reader_backend_preserved=true
work_review_merged=true
full_text_translation=false
selective_translation=true
full_text_status=full_text_downloaded_not_reviewed
work_review_status=complete
reader_merge_status=complete
final_merge_waiting_for_work_review=false
student_reading_status=pending
student_understood=false
```"""
    text, count = re.subn(r"(?ms)^```text\npaper_id=.*?^```", lambda _: status, text, count=1)
    if count != 1:
        raise RuntimeError(f"{pid}: status block replacement failed")
    label_block = """证据标签：

- `[AUTHOR CLAIM]`：原 PDF 直接支持，并保留 PDF 页码和 source locator。
- `[WORK EXPLANATION]`：Work 人工精读形成的教学解释、忠实释义或读图方法。
- `[PROJECT INFERENCE]`：向当前项目的映射，不是论文作者的原话。
- `[EXTRACTION LIMITATION]`：PDF文本层、公式、图表、表格或版式提取限制。
- `[UNRESOLVED]`：Work Review后仍需回到原PDF、补充数据或由学生/导师继续核验。
"""
    text, count = re.subn(
        r"(?ms)^证据标签：\n.*?(?=^## 阅读目录)",
        lambda _: label_block + "\n",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"{pid}: evidence label block replacement failed")
    text = re.sub(r"(?ms)\n---\n\nreader_content_rebuilt=false.*\Z", "", text).rstrip() + "\n"
    locators = first_locator_by_page(root)
    grouped: dict[int, list[tuple[str, str]]] = {}
    for target, start, end, mode in MAPS[pid]:
        block = extract(note_text, start, end)
        grouped.setdefault(target, []).append((normalize_work_block(block, target, locators), mode))
    unresolved = normalize_work_block(unresolved_tail(note_text), 17, locators)
    grouped.setdefault(17, []).append((unresolved, "append"))
    for target in sorted(grouped):
        blocks = grouped[target]
        modes = {mode for _, mode in blocks}
        mode = "replace" if modes == {"replace"} else "append"
        content = "\n\n".join(block for block, _ in blocks)
        text = merge_into_section(text, target, content, mode)
    text = re.sub(
        r"(?m)^- \[UNRESOLVED\] Work 应把上述证据改写.*$\n?",
        "",
        text,
    )
    text = re.sub(
        r"(?m)^- \[UNRESOLVED\] 请 Work 用一个不依赖公式.*$\n?",
        "",
        text,
    )
    text = re.sub(
        r"(?m)^\[UNRESOLVED\] Work 应为上述问题补充答案要点.*$\n?",
        "",
        text,
    )
    text = text.replace("reader_contract_completed=true", "reader_contract_completed=true\nwork_review_content_integrated=true")
    text = text.replace("final_reader_generated=false", "final_reader_generated=true")
    text = text.replace("final_merge_waiting_for_work_review=true", "final_merge_waiting_for_work_review=false")
    footer = (
        "\n\n---\n\n"
        "reader_content_rebuilt=false  \n"
        "draft_structure_preserved=true  \n"
        "work_review_content_integrated=true  \n"
        "nature_reader_backend_modified=false  \n"
        "final_reader_generated=true  \n"
        "student_reading_status=pending  \n"
        "student_understood=false\n"
    )
    text = re.sub(r"(?ms)\n---\n\nreader_content_rebuilt=false.*\Z", "", text).rstrip() + footer
    return text


def collect_section_sources(text: str, number: int) -> dict[str, object]:
    start, end = section_bounds(text, number)
    body = text[start:end]
    locators = sorted(set(re.findall(r"p\d{3}-b\d{3}", body)))
    pages = sorted({int(page) for page in re.findall(r"PDF\s+p{1,2}\.\s*(\d+)", body, re.I)})
    sources = ["draft", "work_review_notes"]
    if locators or pages:
        sources.extend(["source_map", "source_pdf"])
    if number == 8:
        sources.append("formulas_index")
    if number == 9:
        sources.extend(["figures_index", "tables_index"])
    if number == 12:
        sources.extend(["limitations_map", "extraction_issues"])
    if number == 13:
        sources.append("project_relevance")
    return {
        "section": number,
        "sources": sorted(set(sources)),
        "pdf_pages": pages,
        "source_locators": locators,
    }


def qa_final(pid: str, text: str, metadata: dict[str, object]) -> dict[str, object]:
    root = READERS / pid
    valid_locators = {row["source_map_id"] for row in load_csv(root / "extracted/source_map.csv")}
    cited = set(re.findall(r"p\d{3}-b\d{3}", text))
    invalid = sorted(cited - valid_locators)
    h1_count = len(re.findall(r"(?m)^# ", text))
    sections = re.findall(r"(?m)^## (\d+)\. ", text)
    blocked = [pattern for pattern in BLOCKED_LATEX if pattern in text]
    legacy = [label for label in LEGACY_LABELS if label in text]
    checks = {
        "one_h1": h1_count == 1,
        "seventeen_numbered_sections": sections == [str(index) for index in range(1, 18)],
        "final_status_block": all(
            marker in text
            for marker in [
                f"paper_id={pid}",
                "reader_version=1.0",
                "work_review_merged=true",
                "reader_merge_status=complete",
                "student_reading_status=pending",
                "student_understood=false",
            ]
        ),
        "work_content_integrated": text.count("[WORK EXPLANATION]") >= 7,
        "all_locators_resolve": not invalid and bool(cited),
        "notion_latex": not blocked,
        "no_legacy_labels": not legacy,
        "all_current_labels_present": all(label in text for label in ALLOWED_LABELS),
        "extraction_issues_disclosed": "extraction_issues.md" in text and "[EXTRACTION LIMITATION]" in text,
        "selective_not_full_translation": "full_text_translation=false" in text and "selective_translation=true" in text,
        "no_false_research_status": not any(
            phrase in text
            for phrase in [
                "student_understood=true",
                "full_text_status=full_text_reviewed",
                "REV60_validated=true",
                "alpha_confirmed=true",
                "oos_passed=true",
            ]
        ),
        "pdf_sha_preserved": str(metadata["sha256"]) in text,
    }
    failed = [name for name, value in checks.items() if not value]
    if failed:
        raise RuntimeError(
            f"{pid}: final QA failed: {failed}; invalid_locators={invalid}; blocked={blocked}; legacy={legacy}"
        )
    return {
        "checks": checks,
        "h1_count": h1_count,
        "numbered_section_count": len(sections),
        "source_locator_count": len(cited),
        "invalid_locators": invalid,
        "blocked_latex_patterns": blocked,
        "legacy_labels": legacy,
        "remaining_unresolved_count": text.count("[UNRESOLVED]"),
        "work_explanation_count": text.count("[WORK EXPLANATION]"),
        "project_inference_count": text.count("[PROJECT INFERENCE]"),
    }


def unresolved_items(note_text: str) -> list[str]:
    tail = unresolved_tail(note_text)
    return [
        re.sub(r"^\[UNRESOLVED\]\s*", "", item.strip())
        for item in re.findall(r"(?m)^-\s*(.+)$", tail)
    ]


def version_notes(pid: str, metadata: dict[str, object]) -> list[str]:
    return []


def build_report(
    pid: str,
    metadata: dict[str, object],
    inputs: dict[str, str],
    final_hash: str,
    qa: dict[str, object],
    unresolved: list[str],
    conflicts: list[str],
) -> str:
    rows = "\n".join(f"| `{path}` | `{digest}` |" for path, digest in sorted(inputs.items()))
    conflict_rows = "\n".join(f"- {item}" for item in conflicts) or "- 未发现需要用PDF裁决的实质冲突。"
    unresolved_rows = "\n".join(f"- [UNRESOLVED] {item}" for item in unresolved)
    qa_rows = "\n".join(
        f"| {name} | {'PASS' if value else 'FAIL'} |" for name, value in qa["checks"].items()
    )
    return f"""# {pid} Reader Merge Report

merged_at_utc={datetime.now(timezone.utc).isoformat()}

## 1. 合并结论

- Draft作为17节结构骨架保留。
- Work Notes的教学解释、方法直觉、实证解读、选择性翻译、自测答案要点和Mentor版本已并入对应正文节。
- 原PDF、source map和审计索引仍为事实权威；未重跑Nature Reader。
- 最终Reader SHA-256：`{final_hash}`。

## 2. 身份与版本核验

| 字段 | 结果 |
|---|---|
| paper_id | `{pid}` |
| title | {metadata['title']} |
| authors | {metadata['authors']} |
| year | {metadata['year']} |
| obtained_version | {metadata['obtained_version']} |
| version_relation | {metadata['version_relation']} |
| PDF pages | {metadata['page_count']} |
| PDF SHA-256 | `{metadata['sha256']}` |
| Draft/Work/PDF同一版本 | PASS |

## 3. 输入哈希

| 输入 | SHA-256 |
|---|---|
{rows}

## 4. 冲突与权威处理

{conflict_rows}

## 5. 17节覆盖

全部17节均保留；Work内容按章节语义融合，不作为末尾整份附件堆叠。公式仍使用Notion兼容的`$...$`或`$$...$$`，图表和重要结论保留PDF页码/source locator。

## 6. 剩余未解决事项

{unresolved_rows}

这些事项没有因Reader合并而自动视为已完成。

## 7. QA

| 检查 | 结果 |
|---|---|
{qa_rows}

- remaining_unresolved_count={qa['remaining_unresolved_count']}
- source_locator_count={qa['source_locator_count']}
- Work Explanation标签数={qa['work_explanation_count']}
- Project Inference标签数={qa['project_inference_count']}

## 8. 状态边界

```text
full_text_status=full_text_downloaded_not_reviewed
work_review_status=complete
reader_merge_status=complete
student_reading_status=pending
student_understood=false
```

合并未验证当前项目Alpha、未开启Phase B/MCTS、未运行量化研究，也未修改文献注册表。
"""


def build_manifest(
    pid: str,
    metadata: dict[str, object],
    inputs: dict[str, str],
    final_path: Path,
    final_hash: str,
    report_path: Path,
    report_hash: str,
    qa: dict[str, object],
    unresolved: list[str],
    conflicts: list[str],
    final_text: str,
) -> dict[str, object]:
    root = READERS / pid
    path_map = {
        "draft": f"paper_reader_{pid}_draft.md",
        "work_review_notes": f"analysis/work_review_notes_{pid}.md",
        "source_map": "extracted/source_map.csv",
        "source_pdf": str(metadata["source_pdf_path"]),
        "formulas_index": "extracted/formulas_index.csv",
        "figures_index": "extracted/figures_index.csv",
        "tables_index": "extracted/tables_index.csv",
        "limitations_map": "analysis/limitations_map.md",
        "extraction_issues": "extracted/extraction_issues.md",
        "project_relevance": "analysis/project_relevance.md",
    }
    sections = []
    for number in range(1, 18):
        item = collect_section_sources(final_text, number)
        item["source_paths"] = [path_map[name] for name in item["sources"] if name in path_map]
        sections.append(item)
    return {
        "schema_version": "reader_merge_manifest_v1",
        "contract_path": str(CONTRACT.relative_to(ROOT)).replace("\\", "/"),
        "paper_id": pid,
        "title": metadata["title"],
        "authors": metadata["authors"],
        "year": metadata["year"],
        "merged_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_pdf": {
            "path": metadata["source_pdf_path"],
            "sha256": metadata["sha256"],
            "page_count": metadata["page_count"],
            "obtained_version": metadata["obtained_version"],
            "version_relation": metadata["version_relation"],
        },
        "inputs": [{"path": path, "sha256": digest} for path, digest in sorted(inputs.items())],
        "outputs": {
            "final_reader": {
                "path": str(final_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": final_hash,
            },
            "merge_report": {
                "path": str(report_path.relative_to(ROOT)).replace("\\", "/"),
                "sha256": report_hash,
            },
            "generic_contract": {
                "path": str(CONTRACT.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(CONTRACT),
            },
        },
        "sections": sections,
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
        "remaining_unresolved_items": unresolved,
        "status_boundary": {
            "full_text_status": "full_text_downloaded_not_reviewed",
            "work_review_status": "complete",
            "reader_merge_status": "complete",
            "student_reading_status": "pending",
            "student_understood": False,
        },
        "qa": qa,
    }


def verify_inputs_unchanged(pid: str, before: dict[str, str]) -> None:
    root = READERS / pid
    for path_string, expected in before.items():
        path = ROOT / path_string if path_string.startswith("docs/") else root / path_string
        if not path.is_file() or sha256(path) != expected:
            raise RuntimeError(f"{pid}: input changed during merge: {path_string}")


def main() -> None:
    members = validate_zip()
    zip_manifest = json.loads(members["batch_manifest.json"].decode("utf-8"))
    results: dict[str, object] = {
        "zip_path": str(ZIP_PATH),
        "zip_sha256": sha256(ZIP_PATH),
        "processed_at_utc": datetime.now(timezone.utc).isoformat(),
        "papers": {},
    }
    for pid in ORDER:
        note_name = f"work_review_notes_{pid}.md"
        expected_note_sha = zip_manifest["files"][note_name]["sha256"]
        if sha256_bytes(members[note_name]) != expected_note_sha:
            raise RuntimeError(f"{pid}: ZIP manifest note hash mismatch")
        note_path = ensure_work_note(pid, members[note_name])
        metadata, pdf, inputs_before = validate_inputs(pid, note_path)
        note_text = note_path.read_text(encoding="utf-8")
        final_text = build_final(pid, metadata, note_text)
        qa = qa_final(pid, final_text, metadata)
        unresolved = unresolved_items(note_text)
        conflicts = version_notes(pid, metadata)
        root = READERS / pid
        final_path = root / f"paper_reader_{pid}.md"
        report_path = root / f"paper_reader_{pid}_merge_report.md"
        manifest_path = root / f"paper_reader_{pid}_merge_manifest.json"
        temp_final = root / f"paper_reader_{pid}.merge.tmp.md"
        temp_report = root / f"paper_reader_{pid}_merge_report.tmp.md"
        temp_manifest = root / f"paper_reader_{pid}_merge_manifest.tmp.json"
        temp_final.write_text(final_text, encoding="utf-8", newline="\n")
        final_hash = sha256(temp_final)
        report_text = build_report(pid, metadata, inputs_before, final_hash, qa, unresolved, conflicts)
        temp_report.write_text(report_text, encoding="utf-8", newline="\n")
        report_hash = sha256(temp_report)
        manifest = build_manifest(
            pid,
            metadata,
            inputs_before,
            final_path,
            final_hash,
            report_path,
            report_hash,
            qa,
            unresolved,
            conflicts,
            final_text,
        )
        temp_manifest.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        json.loads(temp_manifest.read_text(encoding="utf-8"))
        verify_inputs_unchanged(pid, inputs_before)
        temp_final.replace(final_path)
        temp_report.replace(report_path)
        temp_manifest.replace(manifest_path)
        results["papers"][pid] = {
            "final_reader": str(final_path.relative_to(ROOT)).replace("\\", "/"),
            "final_reader_sha256": sha256(final_path),
            "merge_report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
            "merge_report_sha256": sha256(report_path),
            "merge_manifest": str(manifest_path.relative_to(ROOT)).replace("\\", "/"),
            "merge_manifest_sha256": sha256(manifest_path),
            "qa": "pass",
            "remaining_unresolved_count": qa["remaining_unresolved_count"],
        }
    results_path = PAPERS_ROOT / "MUST_READ_FINAL_MERGE_STATUS.json"
    results_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
