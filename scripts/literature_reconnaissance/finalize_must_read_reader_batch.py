from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import re
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs/literature_reconnaissance"
PAPERS_ROOT = DOCS / "papers"
READERS = PAPERS_ROOT / "readers"
PACKETS = PAPERS_ROOT / "private_work_packets"
ORDER = ["B05", "A04", "A03", "E01", "F01", "D03"]
PROCESSABLE = {"B05", "A04", "A03", "E01", "D03"}
ALLOWED_REQUEST_TYPES = {
    "key_definition",
    "method",
    "formula",
    "empirical_result",
    "limitation",
    "difficult_paragraph",
    "project_mapping",
    "selective_translation",
}
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
PACKET_MEMBERS = [
    "paper_reader_{pid}_draft.md",
    "analysis/research_contract.md",
    "analysis/evidence_map.md",
    "analysis/limitations_map.md",
    "analysis/project_relevance.md",
    "analysis/reading_outline.md",
    "analysis/translation_queue.md",
    "extracted/source_map.csv",
    "extracted/section_index.csv",
    "extracted/formulas_index.csv",
    "extracted/figures_index.csv",
    "extracted/tables_index.csv",
    "extracted/extraction_issues.md",
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
PROTECTED = [
    READERS / "B01/paper_reader_B01.md",
    READERS / "B01/paper_reader_B01_draft.md",
    READERS / "B01/analysis/work_review_notes_B01.md",
    Path(r"C:\Users\Hangxi Yang\.codex\skills\nature-reader\SKILL.md"),
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_paper_specs() -> dict[str, dict[str, object]]:
    source = Path(__file__).with_name("build_must_read_drafts.py")
    spec = importlib.util.spec_from_file_location("must_read_specs", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load build_must_read_drafts.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return {str(item["id"]): item for item in module.PAPERS}


def load_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def source_locations(root: Path) -> list[dict[str, str]]:
    return load_csv(root / "extracted/source_map.csv")


def locate_term(rows: list[dict[str, str]], term: str, fallback: tuple[int, str]) -> tuple[int, str]:
    variants = [term.lower()]
    variants.extend(part.lower() for part in re.split(r"[/()]", term) if len(part.strip()) >= 4)
    for row in rows:
        text = row.get("locator", "").lower()
        if any(variant.strip() in text for variant in variants):
            return int(row["original_page"]), row["source_map_id"]
    return fallback


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        out.append("| " + " | ".join(str(cell).replace("|", r"\|").replace("\n", " ") for cell in row) + " |")
    return "\n".join(out)


def replace_section(text: str, heading: str, next_heading: str, body: str) -> str:
    pattern = re.compile(
        rf"(?ms)^## {re.escape(heading)}[ \t]*\r?\n.*?(?=^## )"
    )
    replacement = f"## {heading}\n\n{body.rstrip()}\n\n"
    updated, count = pattern.subn(lambda _: replacement, text)
    if count != 1:
        raise RuntimeError(f"section replacement failed: {heading} -> {next_heading}, count={count}")
    return updated


FORMULA_BLOCKS = {
    "B05": [
        {
            "id": "B05-R01",
            "latex": r"|t| > 2",
            "page": 2,
            "locator": "p002-b001",
            "status": "source_map_verified",
            "note": "传统单检验门槛；论文论证在大规模因子搜索下不足。",
        },
        {
            "id": "B05-R02",
            "latex": r"|t| > 3",
            "page": 32,
            "locator": "p032-b002",
            "status": "source_map_verified",
            "note": "作者给新因子的经验性更高门槛；不能机械移植到当前56只主题池。",
        },
    ],
    "A04": [
        {
            "id": "A04-R01",
            "latex": r"|t| \ge 3",
            "page": 2,
            "locator": "p002-b001",
            "status": "source_map_verified",
            "note": "更严格的复制判据之一；必须与当前 working-paper 版本的构造一起解释。",
        }
    ],
    "A03": [
        {
            "id": "A03-R01",
            "latex": r"\Delta P_t = c\Delta Q_t + \beta_m r_{m,t} + \varepsilon_t",
            "page": 7,
            "locator": "p007-b002",
            "status": "partially_verified",
            "note": "交易成本回归的文本层候选；符号、下标和估计细节待 Work 对照原版排版。",
        }
    ],
    "E01": [
        {
            "id": "E01-R01",
            "latex": r"\mathrm{AR}_{i,t}=R_{i,t}-E[R_{i,t}\mid X_t]",
            "page": 3,
            "locator": "p003-b005",
            "status": "pdf_verified",
            "note": "异常收益等于实际收益减去无事件条件下的正常收益。",
        },
        {
            "id": "E01-R02",
            "latex": r"\mathrm{CAR}_i(\tau_1,\tau_2)=\sum_{t=\tau_1}^{\tau_2}\mathrm{AR}_{i,t}",
            "page": 9,
            "locator": "p009-b009",
            "status": "pdf_verified",
            "note": "个体证券在事件窗内的累计异常收益；与复合超额收益不是同一定义。",
        },
        {
            "id": "E01-R03",
            "latex": r"R_{i,t}=\alpha_i+\beta_i R_{m,t}+\varepsilon_{i,t}",
            "page": 6,
            "locator": "p006-b003",
            "status": "source_map_verified",
            "note": "市场模型；参数应在估计窗中估计，事件窗通常不用于估计。",
        },
    ],
    "D03": [
        {
            "id": "D03-R01",
            "latex": r"r_i-r_f=\alpha_i+\beta_i(r_m-r_f)+s_i\mathrm{SMB}+h_i\mathrm{HML}+\varepsilon_i",
            "page": 16,
            "locator": "p016-b003",
            "status": "source_map_verified",
            "note": "论文用于风险调整的回归；不能把风险调整后结果直接迁移为A股结论。",
        },
        {
            "id": "D03-R02",
            "latex": r"r_{t+K,i}=\alpha_K+b_K r_{t,i}+u_{t+K,i}",
            "page": 31,
            "locator": "p031-b003",
            "status": "partially_verified",
            "note": "长期收益回归的文本层候选；K与估计细节待Work复核。",
        },
    ],
}


def formula_body(pid: str, paper: dict[str, object]) -> str:
    intro = {
        "B05": "本节以多重检验和阈值框架为主。FWER、FDR、依赖检验及隐藏试验的完整数学推导留给 Work；Draft 只写已能可靠定位的门槛。",
        "A04": "本文的核心是统一复制协议，公式服务于组合形成、收益聚合与显著性判据。当前 PDF 为 working paper，复杂定义应按具体异象逐项核对。",
        "A03": "本节区分毛收益、换手、交易成本与净收益。成本回归可定位，但广义 alpha/MVE 公式的自动提取残缺，不能照抄乱码。",
        "E01": "事件研究的制度框架是：确定事件与窗口，估计正常收益，再计算 AR、CAR 并处理跨证券聚合、聚类和模型误设。",
        "D03": "本文主要依赖横截面双排序、形成期/持有期与长期路径比较。成交量代理为平均日换手率，不是任意成交量指标。",
    }[pid]
    pieces = [f"[AUTHOR CLAIM] {intro}"]
    for item in FORMULA_BLOCKS[pid]:
        pieces.extend(
            [
                f"### {item['id']}",
                "",
                "$$",
                str(item["latex"]),
                "$$",
                "",
                f"- PDF p.{item['page']}；source locator `{item['locator']}`",
                f"- verification_status={item['status']}",
                f"- [AUTHOR CLAIM] {item['note']}",
            ]
        )
    pieces.extend(
        [
            "",
            "[EXTRACTION LIMITATION] `formulas_index.csv` 是文本候选索引，字体、上下标、求和、乘积或希腊字母可能残缺；未通过核验的 OCR 公式不进入 Draft。",
            "",
            "[UNRESOLVED] Work 需对照原 PDF 逐式复核剩余复杂公式、参数定义和推导；未复核部分不视为已解决。",
        ]
    )
    return "\n".join(pieces)


def patch_reader(pid: str, paper: dict[str, object], metadata: dict[str, object]) -> tuple[str, str]:
    root = READERS / pid
    path = root / f"paper_reader_{pid}_draft.md"
    original = path.read_text(encoding="utf-8")
    text = original
    if "## 8. 方法、公式或制度框架" in text and "[WORK EXPLANATION]" not in text:
        return original, text
    text = text.replace(
        "- `[WORK EXPLANATION]`：等待 Work 人工补充的教学解释；本 Draft 不伪造该内容。\n",
        "",
    )
    text = text.replace("[WORK EXPLANATION] [UNRESOLVED]", "[UNRESOLVED]")
    text = text.replace("[WORK EXPLANATION]", "[UNRESOLVED]")
    if "`[WORK EXPLANATION]`" in text:
        raise RuntimeError(f"{pid}: forbidden WORK_EXPLANATION remains")

    routes = list(paper["route"])
    route_extra = "\n".join(
        [
            "",
            "**推荐顺序：** 五分钟理解 → 必须精读页 → 方法/公式或制度框架 → 关键图表 → 局限与项目映射。",
            "",
            "**各阶段读后应回答：**",
            "",
            "1. 作者的研究对象、样本与主要比较基准是什么？",
            "2. 关键结果依赖哪些权重、窗口、显著性或成本设定？",
            "3. 哪些结论只能留在论文市场与样本，不能直接迁移到当前 A 股主题池？",
        ]
    )
    route_body = md_table(["层级", "PDF页码", "阅读目标"], [list(row) for row in routes]) + route_extra
    text = replace_section(text, "4. 推荐阅读路线", "5. 研究问题与直觉", route_body)

    rows = source_locations(root)
    fallback_page, fallback_locator = int(paper["sections"][0][1]), str(paper["sections"][0][2])
    term_rows: list[list[str]] = []
    for english, chinese, meaning, example in paper["terms"]:
        page, locator = locate_term(rows, str(english), (fallback_page, fallback_locator))
        term_rows.append([str(english), str(chinese), str(meaning), str(example), f"PDF p.{page} `{locator}`"])
    terms_body = md_table(
        ["English", "中文", "论文中的含义", "当前项目中的例子", "PDF页码与source locator"],
        term_rows,
    )
    text = replace_section(text, "6. 核心术语", "7. 逐节导读", terms_body)

    section_rows: list[list[str]] = []
    for name, page, locator, aim in paper["sections"]:
        section_rows.append(
            [
                str(name),
                str(aim),
                "沿作者原章节顺序识别定义、方法、证据与限定语。",
                str(aim),
                "长证明、完整变量目录或重复稳健性表可先按阅读路线略读。",
                f"PDF p.{page}",
                f"`{locator}`",
                f"[UNRESOLVED] 核对本节关键数字、公式/图表及作者限定语。",
            ]
        )
    section_body = md_table(
        [
            "原文章节",
            "本节解决什么",
            "论证结构",
            "必须理解",
            "可以暂时跳过",
            "PDF页码",
            "source locator",
            "待Work复核点",
        ],
        section_rows,
    )
    section_body += (
        "\n\n[EXTRACTION LIMITATION] `section_index.csv` 含页眉、脚注或表格文本误识别为章节的条目；"
        "上表只保留经正文结构核对的主线，原生索引仍完整保留。"
    )
    text = replace_section(text, "7. 逐节导读", "8. 关键公式索引和解释占位", section_body)
    text = text.replace("## 8. 关键公式索引和解释占位", "## 8. 方法、公式或制度框架")
    text = text.replace(
        "- [关键公式索引和解释占位](#8-关键公式索引和解释占位)",
        "- [方法、公式或制度框架](#8-方法公式或制度框架)",
    )
    text = replace_section(text, "8. 方法、公式或制度框架", "9. 图表与实证结果索引", formula_body(pid, paper))
    text = text.replace("## 9. 图表与实证结果索引", "## 9. 实证、图表或论证结果")
    text = text.replace(
        "- [图表与实证结果索引](#9-图表与实证结果索引)",
        "- [实证、图表或论证结果](#9-实证图表或论证结果)",
    )
    text = text.replace("## 14. 待 Work 补充的关键翻译", "## 14. Work选择性翻译队列")
    text = text.replace(
        "- [待 Work 补充的关键翻译](#14-待-work-补充的关键翻译)",
        "- [Work选择性翻译队列](#14-work选择性翻译队列)",
    )
    text = text.replace("## 16. Mentor 汇报提纲", "## 16. Mentor汇报提纲Draft")
    text = text.replace(
        "- [Mentor 汇报提纲](#16-mentor-汇报提纲)",
        "- [Mentor汇报提纲Draft](#16-mentor汇报提纲draft)",
    )
    text = text.replace("## 17. 完整来源索引", "## 17. 来源索引与提取问题")
    text = text.replace(
        "- [完整来源索引](#17-完整来源索引)",
        "- [来源索引与提取问题](#17-来源索引与提取问题)",
    )
    text = text.replace(
        "reader_content_rebuilt=false",
        "reader_content_rebuilt=false\nreader_contract_completed=true",
    )
    if text.count("[WORK EXPLANATION]") or text.count("[CODEX INFERENCE]"):
        raise RuntimeError(f"{pid}: forbidden evidence label remains")
    if text.count("[SELECTIVE TRANSLATION PENDING]") or text.count("[WORK REVIEW REQUIRED]"):
        raise RuntimeError(f"{pid}: legacy evidence label remains")
    return original, text


def formula_qa(pid: str, text: str) -> tuple[list[dict[str, object]], list[str]]:
    blocked = [pattern for pattern in BLOCKED_LATEX if pattern in text]
    rows: list[dict[str, object]] = []
    for item in FORMULA_BLOCKS[pid]:
        marker = f"### {item['id']}"
        line = text[: text.index(marker)].count("\n") + 1
        rows.append(
            {
                "paper_id": pid,
                "formula_id": item["id"],
                "reader_line": line,
                "formula_type": "block",
                "latex": item["latex"],
                "pdf_page": item["page"],
                "source_locator": item["locator"],
                "verification_status": item["status"],
                "notion_compatible": "true",
                "issue": "" if item["status"] != "partially_verified" else "Work must verify symbols/estimation details",
            }
        )
    return rows, blocked


def write_formula_qa(pid: str, rows: list[dict[str, object]]) -> Path:
    path = READERS / pid / f"analysis/notion_formula_qa_{pid}.csv"
    fields = [
        "paper_id",
        "formula_id",
        "reader_line",
        "formula_type",
        "latex",
        "pdf_page",
        "source_locator",
        "verification_status",
        "notion_compatible",
        "issue",
    ]
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return path


def work_items(pid: str, paper: dict[str, object]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    first_name, first_page, first_locator, first_aim = paper["sections"][0]
    items.append(
        {
            "type": "key_definition",
            "page": str(first_page),
            "locator": str(first_locator),
            "why": f"建立本文专属概念边界：{first_name}",
            "draft": str(first_aim),
            "action": "explain_in_chinese",
        }
    )
    for name, page, locator, aim in list(paper["sections"])[1:4]:
        items.append(
            {
                "type": "method",
                "page": str(page),
                "locator": str(locator),
                "why": f"主方法/论证段：{name}",
                "draft": str(aim),
                "action": "challenge_interpretation",
            }
        )
    for item in FORMULA_BLOCKS[pid]:
        items.append(
            {
                "type": "formula",
                "page": str(item["page"]),
                "locator": str(item["locator"]),
                "why": f"关键公式 {item['id']} 需要人工核验直觉与符号",
                "draft": str(item["note"]),
                "action": "derive_formula" if pid == "E01" else "verify_numeric_result",
            }
        )
    for name, page, locator, note in list(paper["visuals"])[:3]:
        items.append(
            {
                "type": "empirical_result",
                "page": str(page),
                "locator": str(locator),
                "why": f"{name} 承载关键证据",
                "draft": str(note),
                "action": "verify_numeric_result",
            }
        )
    last_name, last_page, last_locator, last_aim = paper["sections"][-1]
    items.append(
        {
            "type": "limitation",
            "page": str(last_page),
            "locator": str(last_locator),
            "why": f"结论与限制段：{last_name}",
            "draft": str(last_aim),
            "action": "challenge_interpretation",
        }
    )
    for translation in list(paper["translations"])[:2]:
        match = re.search(r"p\.(\d+)", str(translation))
        page = match.group(1) if match else str(first_page)
        loc = next(
            (
                row["source_map_id"]
                for row in source_locations(READERS / pid)
                if row["original_page"] == page
            ),
            str(first_locator),
        )
        items.append(
            {
                "type": "selective_translation",
                "page": page,
                "locator": loc,
                "why": "难段或限定语需要短小选择性翻译",
                "draft": str(translation),
                "action": "translate_key_passage",
            }
        )
    items.append(
        {
            "type": "project_mapping",
            "page": str(last_page),
            "locator": str(last_locator),
            "why": "防止把论文样本结论直接推广到当前A股主题池",
            "draft": "Draft已标记PROJECT INFERENCE及historical_seen/final test边界。",
            "action": "compare_with_project",
        }
    )
    return items[:15]


def build_work_request(pid: str, paper: dict[str, object], metadata: dict[str, object]) -> str:
    rows = []
    items = work_items(pid, paper)
    for index, item in enumerate(items, 1):
        if item["type"] not in ALLOWED_REQUEST_TYPES:
            raise RuntimeError(f"{pid}: invalid request type {item['type']}")
        rows.append(
            [
                str(index),
                item["type"],
                f"PDF p.{item['page']}",
                f"`{item['locator']}`",
                item["why"],
                item["draft"],
                item["action"],
            ]
        )
    priority_pages = "；".join(str(item) for item in paper["translations"])
    return f"""# {pid} Work Review Request

## A. 论文身份

paper_id={pid}  
title={paper['title']}  
authors={paper['authors']}  
year={paper['year']}  
source_pdf_sha256={metadata['sha256']}  
pdf_version={paper['version']}  
work_review_status=pending  
final_merge_waiting_for_work_review=true

## B. Draft路径

`docs/literature_reconnaissance/papers/readers/{pid}/paper_reader_{pid}_draft.md`

原 PDF 本地路径（不在 ZIP 中）：

`{metadata['source_pdf_path']}`

## C. 建议Work优先核验的章节

{priority_pages}

## D-E. 重点问题（最多15项）

{md_table(
    ['序号', 'type', 'PDF页码', 'source locator', '为什么重要', '当前Draft写了什么', '希望Work执行什么'],
    rows,
)}

type 仅使用：`key_definition`、`method`、`formula`、`empirical_result`、`limitation`、`difficult_paragraph`、`project_mapping`、`selective_translation`。

## F. 推荐Work产物路径

`docs/literature_reconnaissance/papers/readers/{pid}/analysis/work_review_notes_{pid}.md`

## 边界

- 以原 PDF 为事实权威；数值、公式、页码、图表标题、样本和限定语发生冲突时记录冲突。
- 只做选择性翻译，不生成全文翻译，不调用外部翻译 API。
- 不能把项目推断改写成作者结论，不能把论文结果写成 A 股已验证 Alpha。
- 不修改 `full_text_reviewed`、`student_understood` 或最终合并状态。
- Work Notes 完成后，另按 `reader_merge_contract_v1.md` 合并；本交接不生成最终 Reader。
"""


def validate_identity(pid: str) -> tuple[dict[str, object], Path]:
    root = READERS / pid
    missing = [name for name in REQUIRED if not (root / name).is_file()]
    if missing:
        raise RuntimeError(f"{pid}: missing audit inputs: {missing}")
    metadata = json.loads((root / "source/source_metadata.json").read_text(encoding="utf-8"))
    if metadata["paper_id"] != pid:
        raise RuntimeError(f"{pid}: metadata paper_id mismatch")
    pdf = ROOT / str(metadata["source_pdf_path"])
    if not pdf.is_file():
        raise RuntimeError(f"{pid}: metadata PDF missing: {pdf}")
    actual = sha256(pdf)
    recorded = str(metadata["sha256"]).lower()
    sha_txt = (root / "source/sha256.txt").read_text(encoding="utf-8").strip().split()[0].lower()
    if actual != recorded or actual != sha_txt:
        raise RuntimeError(f"{pid}: PDF/metadata/sha256.txt mismatch")
    pages = len(PdfReader(str(pdf)).pages)
    if pages <= 0 or pages != int(metadata["page_count"]):
        raise RuntimeError(f"{pid}: PDF page count mismatch")
    if not (root / "extracted/source_map.csv").stat().st_size:
        raise RuntimeError(f"{pid}: empty source map")
    return metadata, pdf


def write_reader_qa(
    pid: str,
    metadata: dict[str, object],
    pdf: Path,
    draft_text: str,
    blocked_latex: list[str],
    protected_before: dict[str, str],
) -> Path:
    locators = {row["source_map_id"] for row in source_locations(READERS / pid)}
    cited = set(re.findall(r"`(p\d{3}-b\d{3})`", draft_text))
    invalid = sorted(cited - locators)
    headings = re.findall(r"^## (\d+)\. ", draft_text, re.M)
    unresolved = draft_text.count("[UNRESOLVED]")
    final_path = READERS / pid / f"paper_reader_{pid}.md"
    checks = {
        "paper_id/title/authors/year metadata present": all(
            str(metadata[key]) in draft_text for key in ["paper_id", "title"]
        ),
        "PDF valid and page count > 0": len(PdfReader(str(pdf)).pages) > 0,
        "PDF SHA-256 matches metadata": sha256(pdf) == str(metadata["sha256"]).lower(),
        "17 numbered sections retained": headings == [str(i) for i in range(1, 18)],
        "source locators all resolve": not invalid and bool(cited),
        "Draft evidence tags allowed": not any(
            label in draft_text
            for label in [
                "[WORK EXPLANATION]",
                "[CODEX INFERENCE]",
                "[WORK REVIEW REQUIRED]",
                "[SELECTIVE TRANSLATION PENDING]",
            ]
        ),
        "Notion blocked LaTeX absent": not blocked_latex,
        "no final Reader generated": not final_path.exists(),
        "no full-text translation": "full_text_translation=false" in draft_text,
        "student state remains pending/false": (
            "student_reading_status=pending" in draft_text and "student_understood=false" in draft_text
        ),
    }
    if not all(checks.values()):
        failed = [name for name, ok in checks.items() if not ok]
        raise RuntimeError(f"{pid}: reader QA failed: {failed}; invalid locators={invalid}; blocked={blocked_latex}")
    report = [
        f"# {pid} Reader QA",
        "",
        f"checked_at_utc={datetime.now(timezone.utc).isoformat()}",
        f"source_pdf_sha256={sha256(pdf)}",
        f"source_pdf_pages={len(PdfReader(str(pdf)).pages)}",
        f"draft_sha256={sha256(READERS / pid / f'paper_reader_{pid}_draft.md')}",
        f"remaining_unresolved={unresolved}",
        "",
        "| 检查 | 结果 |",
        "|---|---|",
    ]
    report.extend(f"| {name} | {'PASS' if ok else 'FAIL'} |" for name, ok in checks.items())
    report.extend(
        [
            "",
            "## 输入保护基线",
            "",
            *[f"- `{path}`: `{digest}`" for path, digest in protected_before.items()],
            "",
            "## 边界",
            "",
            "- Draft只包含论文专属短摘要、定位、方法框架与Work队列，不包含全文翻译。",
            "- `[UNRESOLVED]` 全部保留给Work复核；Draft完成不等于全文已人工精读。",
            "- 未生成最终Reader，未修改B01/C07，未运行量化研究。",
        ]
    )
    path = READERS / pid / f"analysis/reader_qa_{pid}.md"
    path.write_text("\n".join(report) + "\n", encoding="utf-8", newline="\n")
    return path


def create_packet(pid: str) -> Path:
    PACKETS.mkdir(parents=True, exist_ok=True)
    packet = PACKETS / f"work_review_packet_{pid}.zip"
    temp = packet.with_suffix(".tmp.zip")
    if temp.exists():
        temp.unlink()
    root = READERS / pid
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for pattern in PACKET_MEMBERS:
            rel = pattern.format(pid=pid)
            source = root / rel
            if not source.is_file():
                raise RuntimeError(f"{pid}: packet input missing: {rel}")
            archive.write(source, arcname=rel)
    with zipfile.ZipFile(temp, "r") as archive:
        names = archive.namelist()
        if len(names) != len(PACKET_MEMBERS):
            raise RuntimeError(f"{pid}: packet member count mismatch")
        if any(name.lower().endswith(".pdf") for name in names):
            raise RuntimeError(f"{pid}: PDF leaked into work packet")
        if archive.testzip() is not None:
            raise RuntimeError(f"{pid}: corrupt work packet")
    temp.replace(packet)
    return packet


def input_hashes(pid: str) -> dict[str, str]:
    root = READERS / pid
    out = {name: sha256(root / name) for name in REQUIRED if (root / name).is_file()}
    metadata_path = root / "source/source_metadata.json"
    if metadata_path.is_file():
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        pdf = ROOT / str(metadata["source_pdf_path"])
        if pdf.is_file():
            out[str(metadata["source_pdf_path"])] = sha256(pdf)
    return out


def write_checkpoint(state: dict[str, object]) -> None:
    path = PAPERS_ROOT / "must_read_reader_batch_checkpoint.json"
    temp = path.with_suffix(".tmp.json")
    temp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(path)


def update_registry(statuses: dict[str, dict[str, str]]) -> None:
    path = DOCS / "02_literature_registry.csv"
    rows = load_csv(path)
    fields = list(rows[0].keys())
    for field in ["reader_draft_status", "work_review_status", "final_merge_status", "blocker", "handoff_path"]:
        if field not in fields:
            fields.append(field)
    for row in rows:
        pid = row["paper_id"]
        if pid in statuses:
            for key, value in statuses[pid].items():
                if key in {"full_text_status", "reader_draft_status", "work_review_status", "final_merge_status", "blocker", "handoff_path"}:
                    row[key] = value
    temp = path.with_suffix(".tmp.csv")
    with temp.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    temp.replace(path)


def update_handoff_index(statuses: dict[str, dict[str, str]], specs: dict[str, dict[str, object]]) -> None:
    path = PAPERS_ROOT / "WORK_HANDOFF_INDEX.md"
    text = path.read_text(encoding="utf-8").rstrip()
    marker = "\n## Must Read统一Draft与Work Review交接状态"
    if marker in text:
        text = text.split(marker, 1)[0].rstrip()
    rows = []
    for pid in ORDER:
        status = statuses[pid]
        rows.append(
            [
                pid,
                str(specs.get(pid, {}).get("title", "Chinese Capital Market: An Empirical Overview")),
                status["reader_draft_status"],
                status["work_review_status"],
                status["final_merge_status"],
                status["blocker"] or "none",
                status["handoff_path"] or "none",
            ]
        )
    appendix = (
        marker
        + "\n\n"
        + md_table(
            ["paper_id", "title", "reader_draft_status", "work_review_status", "final_merge_status", "blocker", "handoff_path"],
            rows,
        )
        + "\n"
    )
    path.write_text(text + appendix, encoding="utf-8", newline="\n")


def batch_status(statuses: dict[str, dict[str, str]], specs: dict[str, dict[str, object]], state: dict[str, object]) -> None:
    rows = []
    for pid in ORDER:
        item = state["papers"][pid]
        spec = specs.get(pid, {})
        rows.append(
            [
                pid,
                str(spec.get("title", "Chinese Capital Market: An Empirical Overview")),
                str(item.get("pdf_status", "")),
                str(item.get("pdf_version", "")),
                str(item.get("source_pdf_sha256", "")),
                str(item.get("nature_reader_status", "")),
                statuses[pid]["reader_draft_status"],
                str(item.get("notion_formula_qa", "")),
                str(item.get("work_packet_status", "")),
                statuses[pid]["work_review_status"],
                statuses[pid]["final_merge_status"],
                statuses[pid]["blocker"] or "none",
                str(item.get("recommended_next_action", "")),
            ]
        )
    content = """# Must Read Reader Batch Status

generated_at_utc={generated}

{table}

## 状态边界

- `full_text_downloaded_not_reviewed` 表示身份、source map、Draft与QA可追溯，不表示人工精读完成。
- 本批次没有生成任何最终 `paper_reader_<PAPER_ID>.md`。
- `student_reading_status=pending`、`student_understood=false` 保持不变。
""".format(
        generated=state["updated_at_utc"],
        table=md_table(
            [
                "paper_id",
                "title",
                "pdf_status",
                "pdf_version",
                "source_pdf_sha256",
                "nature_reader_status",
                "draft_reader_status",
                "notion_formula_qa",
                "work_packet_status",
                "work_review_status",
                "final_merge_status",
                "blocker",
                "recommended_next_action",
            ],
            rows,
        ),
    )
    (PAPERS_ROOT / "MUST_READ_READER_BATCH_STATUS.md").write_text(content, encoding="utf-8", newline="\n")


def work_index(statuses: dict[str, dict[str, str]], specs: dict[str, dict[str, object]]) -> None:
    rows = []
    for pid in ORDER:
        spec = specs.get(pid, {})
        if pid == "F01":
            rows.append(
                [
                    pid,
                    "blocked",
                    "none",
                    "none",
                    "none",
                    "恢复与2018 NBER审计包匹配的PDF，或授权重建2020版审计后端",
                    "PDF/source-map版本不一致",
                    "identity/version",
                ]
            )
            continue
        pages = "；".join(str(item) for item in spec["translations"])
        rows.append(
            [
                pid,
                f"`docs/literature_reconnaissance/papers/readers/{pid}/paper_reader_{pid}_draft.md`",
                f"`docs/literature_reconnaissance/papers/readers/{pid}/analysis/work_review_request_{pid}.md`",
                f"`docs/literature_reconnaissance/papers/private_work_packets/work_review_packet_{pid}.zip`",
                pages,
                str(spec["formulas"][-1][2]),
                str(spec["mentor"]),
                "pending",
            ]
        )
    content = f"""# Work Review Batch Index

复核顺序固定为：B05 → A04 → A03 → E01 → F01 → D03。F01虽阻断，仍保留在指定顺序位置；D03最后处理。

{md_table(
    ['paper_id', 'draft路径', 'Work request路径', 'Work packet路径', '建议先读页码', '最难部分', '预计Work复核重点', '状态'],
    rows,
)}

## 通用交接规则

- ZIP不含原PDF；需看图形或原版排版时，按Work request中的本地PDF路径和页码打开。
- Work生成 `analysis/work_review_notes_<PAPER_ID>.md` 后，另按 `reader_merge_contract_v1.md` 合并。
- Work Notes缺失前不得生成最终Reader，不得标记学生已理解。
"""
    (PAPERS_ROOT / "WORK_REVIEW_BATCH_INDEX.md").write_text(content, encoding="utf-8", newline="\n")


def main() -> None:
    specs = load_paper_specs()
    checkpoint_path = PAPERS_ROOT / "must_read_reader_batch_checkpoint.json"
    prior_state: dict[str, object] = {}
    if checkpoint_path.is_file():
        try:
            prior_state = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prior_state = {}
    protected_before = {str(path): sha256(path) for path in PROTECTED if path.is_file()}
    c07_files = sorted(path for path in (READERS / "C07").rglob("*") if path.is_file())
    protected_before.update({str(path): sha256(path) for path in c07_files})
    audit_before = {pid: input_hashes(pid) for pid in ORDER}
    state: dict[str, object] = {
        "schema_version": "must_read_reader_batch_checkpoint_v1",
        "order": ORDER,
        "created_at_utc": prior_state.get("created_at_utc", datetime.now(timezone.utc).isoformat()),
        "updated_at_utc": datetime.now(timezone.utc).isoformat(),
        "protected_input_hashes_before": protected_before,
        "papers": {},
    }
    statuses: dict[str, dict[str, str]] = {}
    write_checkpoint(state)

    for pid in ORDER:
        state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
        if pid == "F01":
            root = READERS / pid
            metadata = json.loads((root / "source/source_metadata.json").read_text(encoding="utf-8"))
            expected = ROOT / str(metadata["source_pdf_path"])
            available = sorted((PAPERS_ROOT / "source_pdfs/F01").glob("*.pdf"))
            blocker = "audit_pdf_missing_and_available_pdf_hash_page_count_do_not_match_source_map"
            statuses[pid] = {
                "full_text_status": "full_text_downloaded_not_reviewed",
                "reader_draft_status": "blocked",
                "work_review_status": "blocked",
                "final_merge_status": "not_started",
                "blocker": blocker,
                "handoff_path": "docs/literature_reconnaissance/papers/readers/F01/draft_generation_blocker.md",
            }
            state["papers"][pid] = {
                "status": "blocked",
                "pdf_status": "version_mismatch",
                "pdf_version": "available 2020 manuscript; audit backend expects 2018 NBER working paper",
                "source_pdf_sha256": sha256(available[0]) if available else "",
                "expected_source_pdf_sha256": metadata["sha256"],
                "expected_pdf_exists": expected.is_file(),
                "nature_reader_status": "blocked_identity_mismatch",
                "notion_formula_qa": "not_run",
                "work_packet_status": "not_generated",
                "recommended_next_action": "restore exact 2018 NBER PDF or authorize a new audit backend for the 2020 manuscript",
                "input_hashes": audit_before[pid],
            }
            write_checkpoint(state)
            continue

        current_inputs = input_hashes(pid)
        prior_paper = (prior_state.get("papers") or {}).get(pid, {})
        draft = READERS / pid / f"paper_reader_{pid}_draft.md"
        packet = PACKETS / f"work_review_packet_{pid}.zip"
        qa_csv = READERS / pid / f"analysis/notion_formula_qa_{pid}.csv"
        request = READERS / pid / f"analysis/work_review_request_{pid}.md"
        qa_report = READERS / pid / f"analysis/reader_qa_{pid}.md"
        can_resume_skip = (
            prior_paper.get("status") == "complete"
            and prior_paper.get("input_hashes") == current_inputs
            and draft.is_file()
            and packet.is_file()
            and qa_csv.is_file()
            and request.is_file()
            and qa_report.is_file()
            and prior_paper.get("draft_sha256") == sha256(draft)
            and prior_paper.get("work_packet_sha256") == sha256(packet)
        )
        if can_resume_skip:
            statuses[pid] = {
                "full_text_status": "full_text_downloaded_not_reviewed",
                "reader_draft_status": "complete",
                "work_review_status": "pending",
                "final_merge_status": "not_started",
                "blocker": "",
                "handoff_path": f"docs/literature_reconnaissance/papers/readers/{pid}/analysis/work_review_request_{pid}.md",
            }
            state["papers"][pid] = dict(prior_paper)
            state["papers"][pid]["resume_action"] = "skipped_unchanged_inputs_and_outputs"
            write_checkpoint(state)
            continue

        paper = specs[pid]
        metadata, pdf = validate_identity(pid)
        original, patched = patch_reader(pid, paper, metadata)
        rows, blocked = formula_qa(pid, patched)
        if blocked:
            raise RuntimeError(f"{pid}: blocked LaTeX in patched Draft: {blocked}")
        temp_draft = draft.with_suffix(".tmp.md")
        temp_draft.write_text(patched, encoding="utf-8", newline="\n")
        temp_draft.replace(draft)
        qa_csv = write_formula_qa(pid, rows)
        request.write_text(build_work_request(pid, paper, metadata), encoding="utf-8", newline="\n")
        qa_report = write_reader_qa(pid, metadata, pdf, patched, blocked, protected_before)
        packet = create_packet(pid)
        statuses[pid] = {
            "full_text_status": "full_text_downloaded_not_reviewed",
            "reader_draft_status": "complete",
            "work_review_status": "pending",
            "final_merge_status": "not_started",
            "blocker": "",
            "handoff_path": f"docs/literature_reconnaissance/papers/readers/{pid}/analysis/work_review_request_{pid}.md",
        }
        state["papers"][pid] = {
            "status": "complete",
            "pdf_status": "valid",
            "pdf_version": paper["version"],
            "source_pdf_sha256": metadata["sha256"],
            "source_pdf_pages": metadata["page_count"],
            "nature_reader_status": "source_only_backend_validated",
            "preexisting_draft_sha256": hashlib.sha256(original.encode("utf-8")).hexdigest(),
            "draft_sha256": sha256(draft),
            "notion_formula_qa": "pass",
            "notion_formula_qa_path": str(qa_csv.relative_to(ROOT)).replace("\\", "/"),
            "reader_qa_path": str(qa_report.relative_to(ROOT)).replace("\\", "/"),
            "work_request_path": str(request.relative_to(ROOT)).replace("\\", "/"),
            "work_packet_status": "complete_no_pdf",
            "work_packet_path": str(packet.relative_to(ROOT)).replace("\\", "/"),
            "work_packet_sha256": sha256(packet),
            "recommended_next_action": f"Work creates analysis/work_review_notes_{pid}.md",
            "input_hashes": audit_before[pid],
        }
        write_checkpoint(state)

    update_registry(statuses)
    update_handoff_index(statuses, specs)
    state["knowledge_base_updated"] = [
        "docs/literature_reconnaissance/02_literature_registry.csv",
        "docs/literature_reconnaissance/papers/WORK_HANDOFF_INDEX.md",
    ]
    state["updated_at_utc"] = datetime.now(timezone.utc).isoformat()
    protected_after = {path: sha256(Path(path)) for path in protected_before}
    state["protected_input_hashes_after"] = protected_after
    state["protected_inputs_unchanged"] = protected_before == protected_after
    audit_after = {pid: input_hashes(pid) for pid in ORDER}
    state["audit_inputs_unchanged"] = {
        pid: audit_before[pid] == audit_after[pid] for pid in ORDER
    }
    if not state["protected_inputs_unchanged"] or not all(state["audit_inputs_unchanged"].values()):
        raise RuntimeError("protected or audit inputs changed")
    batch_status(statuses, specs, state)
    work_index(statuses, specs)
    write_checkpoint(state)


if __name__ == "__main__":
    main()
