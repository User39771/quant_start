"""Build source-only, page-grounded reader handoffs for acquired core PDFs."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/literature_reconnaissance"
PAPERS = DOCS / "papers"
MANIFEST = PAPERS / "acquisition_manifest.csv"
REGISTRY = DOCS / "02_literature_registry.csv"
READERS = PAPERS / "readers"
PDFTOTEXT = Path(r"C:\texlive\2026\bin\windows\pdftotext.exe")
PDFTOPPM = Path(r"C:\texlive\2026\bin\windows\pdftoppm.exe")
TESSERACT = Path(r"D:\Tesseract-OCR\tesseract.exe")
SUCCESS = {
    "existing_fulltext_reviewed", "open_fulltext_downloaded",
    "author_manuscript_downloaded", "repository_version_downloaded",
    "full_text_downloaded_not_reviewed",
}
MUST = {"C07", "B01", "B05", "A04", "A03", "D03", "E01", "F01"}
ANALYSIS_ANCHORS = {
    # PDF-page anchors verified from the supplied final journal layouts.
    "D01": (1, 13),
    "D02": (2, 32),
    "D03": (2, 50),
    "D04": (2, 40),
    "D05": (2, 39),
    "F02": (1, 7),
    "F03": (1, 17),
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, str]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def run_pdftotext(pdf: Path, force_ocr: bool = False) -> list[str]:
    result = subprocess.run(
        [str(PDFTOTEXT), "-layout", str(pdf), "-"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=True,
    )
    pages = result.stdout.split("\f")
    if force_ocr or (
        pages and sum(len(clean(page)) < 80 for page in pages) / len(pages) > 0.3
    ):
        pages = run_ocr(pdf)
    return pages


def run_ocr(pdf: Path) -> list[str]:
    """OCR image-heavy PDFs with already-installed local tools."""
    with tempfile.TemporaryDirectory(prefix="literature_ocr_") as folder:
        prefix = Path(folder) / "page"
        subprocess.run(
            [str(PDFTOPPM), "-r", "200", "-png", str(pdf), str(prefix)],
            capture_output=True, check=True,
        )
        pages = []
        for image in sorted(Path(folder).glob("page-*.png")):
            result = subprocess.run(
                [str(TESSERACT), str(image), "stdout", "-l", "eng"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                check=True,
            )
            pages.append(result.stdout)
        return pages


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def heading(line: str) -> bool:
    value = clean(line)
    if not 2 < len(value) < 120:
        return False
    if re.match(r"^(?:\d+(?:\.\d+)*|[IVX]+|V[lI]|\|)\.?\s+[A-Z]", value):
        return True
    if value.casefold() in {
        "abstract", "introduction", "conclusion", "conclusions",
        "references", "appendix", "data", "method", "methods",
        "empirical results", "results",
    }:
        return True
    letters = re.sub(r"[^A-Za-z]", "", value)
    return len(letters) >= 5 and letters.isupper()


def heading_text(line: str) -> str:
    value = clean(line)
    if heading(value):
        return value
    mixed_case = re.search(
        r"(?:^|\s{2,})(\d+(?:\.\d+)*\.?\s+[A-Z][A-Za-z][A-Za-z &:/-]{2,60})"
        r"(?=\s{2,}|$)",
        line,
    )
    if mixed_case:
        return clean(mixed_case.group(1))
    match = re.search(
        r"(?:^|\s)(\d+(?:\.\d+)*\s+[A-Z][A-Z0-9 &:/-]{3,})(?=\s{2,}|$)",
        line,
    )
    return clean(match.group(1)) if match else ""


def paragraph_blocks(page: str) -> list[str]:
    return [
        clean(block) for block in re.split(r"\n\s*\n", page)
        if len(clean(block)) >= 20
    ]


def find_anchor(sections: list[dict[str, str]], names: tuple[str, ...], fallback: int) -> int:
    for row in sections:
        if any(name in row["section_title"].casefold() for name in names):
            return int(row["original_page"])
    return fallback


def page_source_anchor(maps: list[dict[str, str]], page: int) -> str:
    return next(
        (row["source_map_id"] for row in maps if int(row["original_page"]) == page),
        f"p{page:03d}-b001",
    )


def md_table(items: list[tuple[str, str]]) -> str:
    lines = ["| Field | Value |", "|---|---|"]
    lines.extend(f"| {key} | {value.replace('|', '/')} |" for key, value in items)
    return "\n".join(lines)


def cluster_terms(cluster: str) -> list[tuple[str, str]]:
    pools = {
        "A": [("cross-sectional return", "横截面收益"), ("characteristic", "公司特征"),
              ("portfolio sort", "组合排序"), ("factor premium", "因子溢价"),
              ("value weighting", "市值加权"), ("equal weighting", "等权"),
              ("turnover", "换手率"), ("transaction cost", "交易成本"),
              ("out-of-sample", "样本外"), ("replication", "复制检验")],
        "B": [("data snooping", "数据窥探"), ("multiple testing", "多重检验"),
              ("bootstrap", "自助法"), ("false discovery", "伪发现"),
              ("selection bias", "选择偏差"), ("backtest overfitting", "回测过拟合"),
              ("Sharpe ratio", "夏普比率"), ("survivorship bias", "生存者偏差"),
              ("final test", "最终测试集"), ("experiment registry", "实验注册表")],
        "C": [("formulaic alpha", "公式型因子"), ("search space", "搜索空间"),
              ("reward", "奖励函数"), ("Monte Carlo tree search", "蒙特卡洛树搜索"),
              ("reinforcement learning", "强化学习"), ("symbolic regression", "符号回归"),
              ("candidate diversity", "候选多样性"), ("canonicalization", "规范化"),
              ("random-search baseline", "随机搜索基线"), ("alpha decay", "因子衰减")],
        "D": [("trading volume", "成交量"), ("turnover", "换手率"),
              ("return autocorrelation", "收益自相关"), ("liquidity trading", "流动性交易"),
              ("informed trading", "知情交易"), ("price pressure", "价格压力"),
              ("reversal", "反转"), ("continuation", "延续"),
              ("abnormal volume", "异常成交量"), ("investor attention", "投资者注意力")],
        "E": [("event date", "事件日"), ("estimation window", "估计窗口"),
              ("event window", "事件窗口"), ("abnormal return", "异常收益"),
              ("cumulative abnormal return", "累计异常收益"), ("market model", "市场模型"),
              ("test statistic", "检验统计量"), ("cross-sectional dependence", "横截面相关"),
              ("theme exposure", "主题暴露"), ("confounding event", "混杂事件")],
        "F": [("T+1 rule", "T+1交易规则"), ("price limit", "涨跌停"),
              ("suspension", "停牌"), ("point-in-time universe", "时点股票池"),
              ("delisting", "退市"), ("survivorship bias", "生存者偏差"),
              ("liquidity", "流动性"), ("capacity", "容量"),
              ("price adjustment", "复权"), ("implementation constraint", "实施约束")],
    }
    return pools[cluster]


def make_analysis(
    meta: dict[str, str], manifest: dict[str, str], sections: list[dict[str, str]],
    maps: list[dict[str, str]], formulas: list[dict[str, str]],
    figures: list[dict[str, str]], tables: list[dict[str, str]],
    analysis: Path,
) -> None:
    paper_id = meta["paper_id"]
    if paper_id in ANALYSIS_ANCHORS:
        abstract_page, conclusion_page = ANALYSIS_ANCHORS[paper_id]
    else:
        abstract_page = find_anchor(sections, ("abstract",), 1)
        conclusion_page = find_anchor(
            sections, ("conclu", "discussion"), int(manifest["page_count"])
        )
    abstract_anchor = page_source_anchor(maps, abstract_page)
    conclusion_anchor = page_source_anchor(maps, conclusion_page)
    contract = [
        ("PDF身份", f"{meta['title']} / {meta['authors']} / {meta['year']}"),
        ("来源版本", manifest["obtained_version"]),
        ("PDF SHA-256", manifest["sha256"]),
        ("研究问题", meta["research_question"]), ("数据市场与股票池", meta["market_and_universe"]),
        ("样本期间", meta["sample_period"]), ("数据频率", meta["data_frequency"]),
        ("输入变量", meta["input_variables"]), ("预测目标", meta["target_variable"]),
        ("方法", meta["method"]), ("train/validation/test设计", meta["train_validation_test_design"]),
        ("point-in-time状态", meta["point_in_time_status"]),
        ("交易成本", meta["transaction_cost_treatment"]), ("评价指标", meta["main_metrics"]),
        ("作者主要发现",
         f"{meta['main_findings']}（全文锚点：PDF p.{abstract_page} {abstract_anchor}; "
         f"p.{conclusion_page} {conclusion_anchor}）"),
        ("作者报告的失败或负面结果", meta["negative_or_null_findings"]),
        ("作者自己承认的限制", meta["limitations_reported_by_authors"]),
        ("Codex inference", meta["additional_limitations_identified"]),
    ]
    (analysis / "research_contract.md").write_text(
        f"# {paper_id} research contract\n\n"
        "下表保留 Author claim 与 Codex inference 的标签边界；摘要级旧字段未自动升级为作者全文主张。\n\n"
        + md_table(contract) + "\n", encoding="utf-8",
    )

    evidence = [
        ("Author claim", meta["main_findings"], abstract_page, abstract_anchor),
        ("Negative/null boundary (registry synthesis; Work verification pending)",
         meta["negative_or_null_findings"], conclusion_page, conclusion_anchor),
        ("Author limitation status", meta["limitations_reported_by_authors"], conclusion_page,
         f"{conclusion_anchor} (verify during Work review)"),
        ("Codex inference", meta["additional_limitations_identified"], conclusion_page,
         f"{conclusion_anchor} (project-level inference)"),
    ]
    lines = ["# Evidence map", "", "| Type | Claim or result | PDF page | Source-map locator |",
             "|---|---|---:|---|"]
    for kind, claim, page, locator in evidence:
        lines.append(f"| {kind} | {claim.replace('|', '/')} | {page} | {locator} |")
    (analysis / "evidence_map.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    (analysis / "limitations_map.md").write_text(
        "# Limitations map\n\n"
        f"- Author-reported limitation: {meta['limitations_reported_by_authors']}\n"
        f"- Codex inference: {meta['additional_limitations_identified']}\n"
        "- Transfer to A-shares: institutional rules, point-in-time membership, suspensions, "
        "price limits, liquidity and sample size must be re-evaluated; the paper does not "
        "establish an A-share alpha.\n", encoding="utf-8",
    )
    (analysis / "project_relevance.md").write_text(
        "# Project relevance\n\n"
        f"- Direct relationship: {meta['relationship_to_current_project']}\n"
        "- Phase A unified contract: use the paper's measurement choices only as auditable "
        "design inputs, not as validated project results.\n"
        "- historical_seen vs final test: any paper-inspired choice made now belongs to "
        "historical_seen; preserve the untouched final test.\n"
        "- REV60: treat relevance as a hypothesis about orientation/conditioning, not evidence "
        "that REV60 works in the current A-share pool.\n"
        "- Turnover and costs: keep gross predictability separate from implementable net results.\n"
        "- Future MCTS/automated search: log the search space, budget, duplicates and all trials; "
        "this task does not authorize search.\n", encoding="utf-8",
    )

    important_words = ("abstract", "introduction", "data", "method", "model",
                       "result", "evidence", "conclu", "discussion", "limitation")
    section_choices = [
        row for row in sections
        if any(word in row["section_title"].casefold() for word in important_words)
    ][:8] or sections[:8]
    outline = [
        f"# {paper_id} reading outline", "",
        "## 为什么现在读", "", meta["what_the_student_should_understand"], "",
        "## 必须精读", "",
    ]
    if section_choices:
        outline.extend(f"- PDF p.{row['original_page']}: {row['section_title']}" for row in section_choices[:4])
    else:
        outline.append(f"- PDF p.{abstract_page} 与 p.{conclusion_page}: 摘要、方法与结论")
    outline += ["", "## 可以略读", ""]
    outline.extend(
        f"- PDF p.{row['original_page']}: {row['section_title']}"
        for row in section_choices[4:7]
    )
    outline += ["", "## 暂时跳过", "", "- 纯证明细节或长篇附录；需要复现方法时再回看。"]
    if paper_id in MUST:
        outline += ["", "## 十个术语", ""]
        for en, zh in cluster_terms(meta["cluster"]):
            outline.append(f"- **{en} / {zh}**：先按论文语境解释，再与本项目数据合同对照。")
        outline += [
            "", "## 五个自测问题", "",
            "1. 论文的识别或评价对象是什么，为什么该对象能回答研究问题？",
            "2. 样本划分与多重检验安排允许作者声称什么，又不允许声称什么？",
            "3. 哪个结果最依赖市场、样本期或实现假设？",
            "4. 若迁移到A股，哪一项数据或制度差异最可能改变结论？",
            "5. 如何把本文方法纳入Phase A而不污染最终测试集？",
            "", "## 与当前项目的对应", "",
            "- 对应统一评价合同、historical_seen/final test、REV60方向、换手成本与未来搜索审计；"
            "只形成方法约束，不形成交易规则。",
            "", "## 最容易误读的三点", "",
            "- 统计显著不等于扣除成本后可交易。",
            "- 论文市场和样本期的结果不等于A股主题池结果。",
            "- 作者报告的最佳设定不等于未计入全部尝试后的无偏证据。",
        ]
    (analysis / "reading_outline.md").write_text("\n".join(outline) + "\n", encoding="utf-8")

    queue = []
    for row in section_choices[:10]:
        title = row["section_title"]
        low = title.casefold()
        kind = "method" if any(x in low for x in ("method", "model", "data")) else (
            "empirical_result" if any(x in low for x in ("result", "evidence", "test")) else
            "difficult_paragraph"
        )
        action = "explain_in_chinese" if kind != "method" else "compare_with_project"
        queue.append((title, row["original_page"], row["source_map_id"], kind, action))
    if formulas and len(queue) < 15:
        row = formulas[0]
        queue.append(("First formula candidate", row["original_page"], row["source_map_id"], "formula", "derive_formula"))
    qlines = [
        "# Translation queue", "",
        "translation_status=pending_work_review", "",
        "| Section title | Original page | Source-map | Why important | Type | Suggested handling |",
        "|---|---:|---|---|---|---|",
    ]
    for title, page, source_id, kind, action in queue[:15]:
        qlines.append(
            f"| {title.replace('|', '/')} | {page} | {source_id} | "
            f"定位论文结构与证据边界 | {kind} | {action} |"
        )
    (analysis / "translation_queue.md").write_text("\n".join(qlines) + "\n", encoding="utf-8")

    base = READERS / paper_id
    (analysis / "work_handoff.md").write_text(
        f"paper_id={paper_id}\n"
        "reader_status=source_only_extraction_complete\n"
        f"source_pdf_path={manifest['filename']}\n"
        f"original_markdown_path={base.relative_to(ROOT).as_posix()}/extracted/paper_original.md\n"
        f"source_map_path={base.relative_to(ROOT).as_posix()}/extracted/source_map.csv\n"
        f"research_contract_path={base.relative_to(ROOT).as_posix()}/analysis/research_contract.md\n"
        f"translation_queue_path={base.relative_to(ROOT).as_posix()}/analysis/translation_queue.md\n"
        f"recommended_first_section=PDF p.{abstract_page}\n"
        "known_extraction_issues=See extracted/extraction_issues.md\n"
        f"full_text_version={manifest['obtained_version']}\n"
        "nature_reader_extraction_complete=true\n"
        "translation_status=pending_work_review\n"
        "full_bilingual_reader_complete=false\n"
        "artifact_producer=auxiliary_poppler_extractor_under_nature_reader_protocol\n",
        encoding="utf-8",
    )


def extract(meta: dict[str, str], manifest: dict[str, str]) -> None:
    paper_id = meta["paper_id"]
    pdf = ROOT / manifest["filename"]
    base = READERS / paper_id
    source, extracted, analysis = base / "source", base / "extracted", base / "analysis"
    for folder in (source, extracted, analysis):
        folder.mkdir(parents=True, exist_ok=True)

    sha = hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert sha == manifest["sha256"]
    source_meta = {
        "paper_id": paper_id, "title": meta["title"], "authors": meta["authors"],
        "year": meta["year"], "source_pdf_path": manifest["filename"],
        "source_url": manifest["source_url"], "access_basis": manifest["access_basis"],
        "obtained_version": manifest["obtained_version"],
        "version_relation": manifest["version_relation"], "page_count": int(manifest["page_count"]),
        "sha256": sha, "pdf_valid": True,
        "artifact_producer": "auxiliary_poppler_extractor_under_nature_reader_protocol",
        "translation_status": "pending_work_review",
    }
    (source / "source_metadata.json").write_text(
        json.dumps(source_meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (source / "sha256.txt").write_text(f"{sha}  {pdf.name}\n", encoding="ascii")

    force_ocr = paper_id == "D01"
    pages = run_pdftotext(pdf, force_ocr=force_ocr)
    pages = pages[: int(manifest["page_count"])]
    md = [f"# {meta['title']}", "", "> Source-only Poppler extraction; no translation.", ""]
    maps: list[dict[str, str]] = []
    sections: list[dict[str, str]] = []
    formulas: list[dict[str, str]] = []
    figures: list[dict[str, str]] = []
    tables: list[dict[str, str]] = []
    seen_figure_labels: set[str] = set()
    seen_table_labels: set[str] = set()
    low_text_pages = []
    current_section = "Front matter"

    for page_no, page in enumerate(pages, 1):
        md += [f"<!-- PDF_PAGE:{page_no} -->", f"## PDF page {page_no}", "", page.rstrip(), ""]
        if len(clean(page)) < 80:
            low_text_pages.append(page_no)
        blocks = paragraph_blocks(page)
        source_id_for_page = f"p{page_no:03d}-b001"
        seen_page_headings: set[str] = set()
        for line in page.splitlines():
            candidate = heading_text(line)
            if candidate and candidate not in seen_page_headings:
                seen_page_headings.add(candidate)
                current_section = candidate[:110]
                sections.append({
                    "section_id": f"s{len(sections)+1:03d}", "section_title": current_section,
                    "original_page": str(page_no), "source_map_id": source_id_for_page,
                })
        for block_no, block in enumerate(blocks, 1):
            source_id = f"p{page_no:03d}-b{block_no:03d}"
            heading_line = next((heading_text(line) for line in block.splitlines()
                                 if heading_text(line)), "")
            if heading_line and heading_line not in seen_page_headings:
                seen_page_headings.add(heading_line)
                current_section = heading_line[:110]
                sections.append({
                    "section_id": f"s{len(sections)+1:03d}", "section_title": current_section,
                    "original_page": str(page_no), "source_map_id": source_id,
                })
            maps.append({
                "source_map_id": source_id, "original_page": str(page_no),
                "section_title": current_section, "locator": block[:160],
            })
            figure_match = re.search(r"\b(?:figure|fig\.)\s+([0-9ivx]+)\b", block, re.I)
            if figure_match and figure_match.group(1).casefold() not in seen_figure_labels:
                seen_figure_labels.add(figure_match.group(1).casefold())
                figures.append({"figure_id": f"fig{len(figures)+1:03d}", "caption": block[:220],
                                "original_page": str(page_no), "source_map_id": source_id})
            table_match = re.search(r"\btable\s+([a-z0-9ivx]+)\b", block, re.I)
            if table_match and table_match.group(1).casefold() not in seen_table_labels:
                seen_table_labels.add(table_match.group(1).casefold())
                tables.append({"table_id": f"tab{len(tables)+1:03d}", "caption": block[:220],
                               "original_page": str(page_no), "source_map_id": source_id})
            for line in block.splitlines():
                value = clean(line)
                if len(value) < 180 and "=" in value and re.search(r"[A-Za-zα-ωΑ-Ω]", value):
                    formulas.append({
                        "formula_id": f"eq{len(formulas)+1:03d}", "formula_text": value,
                        "original_page": str(page_no), "source_map_id": source_id,
                        "extraction_status": "text_candidate_unverified",
                    })
                    break

    (extracted / "paper_original.md").write_text("\n".join(md), encoding="utf-8")
    write_csv(extracted / "source_map.csv", maps,
              ["source_map_id", "original_page", "section_title", "locator"])
    write_csv(extracted / "section_index.csv", sections,
              ["section_id", "section_title", "original_page", "source_map_id"])
    write_csv(extracted / "formulas_index.csv", formulas,
              ["formula_id", "formula_text", "original_page", "source_map_id", "extraction_status"])
    write_csv(extracted / "figures_index.csv", figures,
              ["figure_id", "caption", "original_page", "source_map_id"])
    write_csv(extracted / "tables_index.csv", tables,
              ["table_id", "caption", "original_page", "source_map_id"])
    issues = [
        "# Extraction issues", "",
        "- Producer: auxiliary Poppler extraction under the Nature Reader source-grounding protocol.",
        "- No translation was generated.",
        f"- Extraction mode: {'full-document OCR (image-only journal scan)' if force_ocr else 'selectable PDF text layer'}.",
        f"- PDF pages expected/extracted: {manifest['page_count']}/{len(pages)}.",
        f"- Low-text or image-heavy pages: {', '.join(map(str, low_text_pages)) or 'none detected'}.",
        "- Formula rows are text candidates and must be checked against rendered pages in Work.",
        "- Figure/table indexes record the first detected labeled mention for each object; "
        "caption boundaries and visual crops must be verified in Work.",
    ]
    if paper_id in {"D02", "D03", "D04", "D05"}:
        issues.append(
            "- PDF p.1 is a JSTOR bibliographic wrapper; the journal article begins on PDF p.2. "
            "All source-map page numbers are PDF pages, not printed journal pages."
        )
    (extracted / "extraction_issues.md").write_text("\n".join(issues) + "\n", encoding="utf-8")
    make_analysis(meta, manifest, sections, maps, formulas, figures, tables, analysis)
    print(f"{paper_id}: pages={len(pages)} sections={len(sections)} maps={len(maps)}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--paper-ids", nargs="*",
        help="Optional paper IDs to extract; omitted means all successful non-C07 PDFs.",
    )
    args = parser.parse_args()
    selected = set(args.paper_ids or [])
    registry = {row["paper_id"]: row for row in read_csv(REGISTRY)}
    manifest = read_csv(MANIFEST)
    for row in manifest:
        if row["paper_id"] == "C07" or row["full_text_status"] not in SUCCESS:
            continue
        if selected and row["paper_id"] not in selected:
            continue
        extract(registry[row["paper_id"]], row)


if __name__ == "__main__":
    main()
