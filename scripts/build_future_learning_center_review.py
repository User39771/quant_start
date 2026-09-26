"""Build a page-grounded literature database for the Future Learning Center corpus."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import shutil
import subprocess
import tempfile
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from pypdf import PdfReader


logging.getLogger("pypdf").setLevel(logging.ERROR)


THEMES = {
    "T1": "Future Learning Center Concepts and Theories",
    "T2": "Library Space Transformation and Learning Commons",
    "T3": "Learning Support Services",
    "T4": "User Needs, Experience and Behaviour",
    "T5": "Digital Intelligence, AI and Smart Library Services",
    "T6": "Organizational Governance and Service Models",
    "T7": "International Comparison and Foreign Practices",
}

THEME_TERMS = {
    "T1": {
        "概念": 3,
        "内涵": 3,
        "理论": 3,
        "逻辑": 2,
        "要素": 2,
        "体系": 2,
        "构想": 2,
        "演化": 2,
        "研究进展": 2,
        "热点": 2,
        "趋势": 1,
        "价值意蕴": 2,
    },
    "T2": {
        "空间": 3,
        "学习共享空间": 4,
        "learning commons": 4,
        "场景": 2,
        "空间服务": 4,
        "空间再造": 4,
        "空间设计": 4,
        "空间建设": 3,
        "家具": 3,
        "沉浸式": 2,
    },
    "T3": {
        "学习支持": 5,
        "教学支持": 5,
        "科研服务": 4,
        "学业": 3,
        "育人": 2,
        "知识服务": 3,
        "文献资源": 3,
        "资源保障": 4,
        "阅读服务": 4,
        "信息服务": 2,
    },
    "T4": {
        "用户需求": 6,
        "读者需求": 6,
        "用户体验": 6,
        "用户行为": 6,
        "采纳意愿": 5,
        "用户": 2,
        "需求": 2,
        "体验": 2,
        "行为": 2,
        "满意": 3,
        "评价": 2,
        "kano": 5,
    },
    "T5": {
        "人工智能": 5,
        "ai": 3,
        "aigc": 5,
        "chatgpt": 5,
        "大语言模型": 5,
        "大模型": 4,
        "智能体": 5,
        "数智": 4,
        "数字化": 2,
        "智慧图书馆": 4,
        "智慧空间": 3,
        "元宇宙": 5,
        "机器人": 4,
        "知识图谱": 4,
        "数字孪生": 5,
        "多模态": 4,
        "空间计算": 4,
        "智能服务": 4,
    },
    "T6": {
        "治理": 5,
        "组织": 3,
        "服务模式": 4,
        "建设模式": 4,
        "机制": 3,
        "转型": 3,
        "路径": 1,
        "建设": 1,
        "角色": 3,
        "能力": 3,
        "人力资源": 4,
        "规划": 4,
        "功能定位": 4,
        "协同": 2,
        "生态": 3,
    },
    "T7": {
        "国外": 6,
        "国际": 5,
        "中外": 6,
        "海外": 6,
        "全球": 3,
        "哈佛": 6,
        "arl": 5,
        "外国": 5,
        "比较研究": 3,
    },
}

THEORY_TERMS = {
    "Activity Theory": ("活动理论",),
    "Affordance Theory": ("可供性理论", "可供性视角"),
    "Constructivist Learning Theory": ("建构主义学习理论", "建构主义理论"),
    "Meme Theory": ("模因论",),
    "TOE Framework": ("toe框架", "toe 模型"),
    "KANO Model": ("kano模型", "kano 模型"),
    "Supply-Demand Theory": ("供需理论",),
    "Technology Acceptance Model": ("技术接受模型", "technology acceptance model", "tam模型"),
    "UTAUT": ("utaut", "统一技术接受与使用理论"),
    "Service Design": ("服务设计理论", "服务设计理念"),
    "Lifecycle Perspective": ("全生命周期视角", "全生命周期理论"),
    "Ecological Perspective": ("生态理论", "生态系统理论", "生态视角"),
}

METHOD_TERMS = {
    "Questionnaire survey": ("问卷调查", "问卷法", "调查问卷"),
    "Interview": ("访谈法", "访谈调查", "深度访谈", "半结构式访谈"),
    "Case study": ("案例分析", "案例研究", "个案研究", "多案例分析", "以", "为例"),
    "Literature review": ("文献调研", "文献调查", "文献研究", "文献分析"),
    "Content analysis": ("内容分析法", "内容分析"),
    "Comparative study": ("比较研究", "对比研究", "中外比较"),
    "Web survey": ("网络调研", "网站调研", "网络调查"),
    "Bibliometric analysis": ("文献计量", "文献统计", "知识图谱", "citespace", "vosviewer"),
    "Grounded theory": ("扎根理论",),
    "KANO analysis": ("kano模型", "kano 模型", "better-worse"),
    "Structural equation modelling": ("结构方程", "sem模型"),
    "fsQCA": ("fsqca", "模糊集定性比较分析"),
    "TOE analysis": ("toe框架", "toe 模型"),
    "Expert consultation": ("德尔菲法", "专家咨询"),
    "Analytic hierarchy process": ("层次分析法", "ahp"),
}

METHOD_MARKERS = tuple(
    term
    for method, terms in METHOD_TERMS.items()
    for term in terms
    if term not in {"以", "为例"}
)

JOURNAL_PATTERNS = (
    "中国图书馆学报",
    "大学图书情报学刊",
    "图书情报工作",
    "图书与情报",
    "图书馆论坛",
    "图书馆建设",
    "图书馆学研究",
    "图书馆杂志",
    "图书馆工作与研究",
    "图书馆理论与实践",
    "图书馆学刊",
    "新世纪图书馆",
    "国家图书馆学刊",
    "农业图书情报学报",
    "信息资源管理学报",
    "现代情报",
    "情报理论与实践",
    "情报科学",
    "情报杂志",
    "情报探索",
    "江苏科技信息",
    "传播与版权",
)

ANALYSIS_FIELDS = (
    "research_object",
    "research_question",
    "theoretical_framework",
    "methodology",
    "research_site",
    "sample",
    "main_arguments",
    "findings",
    "limitations",
)


def clean_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\u00a0", " ")
    text = re.sub(r"(?<=[\u4e00-\u9fff])\s+(?=[\u4e00-\u9fff])", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def compact(text: str) -> str:
    return re.sub(r"[\W_]+", "", text, flags=re.UNICODE).casefold()


def clip(text: str, limit: int = 1600) -> str:
    text = clean_text(text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def find_tool(candidates: list[Path]) -> Path:
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    resolved = shutil.which(candidates[0].stem)
    if resolved:
        return Path(resolved)
    raise FileNotFoundError(f"Required tool not found: {candidates[0].stem}")


def page_count(pdf: Path) -> int:
    return len(PdfReader(str(pdf), strict=False).pages)


def run_pdftotext(pdf: Path, tool: Path, expected_pages: int) -> list[str]:
    result = subprocess.run(
        [str(tool), "-layout", str(pdf), "-"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    )
    pages = result.stdout.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    pages = [clean_text(page) for page in pages]
    if len(pages) < expected_pages:
        pages.extend([""] * (expected_pages - len(pages)))
    return pages[:expected_pages]


def run_ocr(pdf: Path, pdftoppm: Path, tesseract: Path) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="flc_ocr_") as folder:
        prefix = Path(folder) / "page"
        subprocess.run(
            [str(pdftoppm), "-r", "200", "-png", str(pdf), str(prefix)],
            capture_output=True,
            check=True,
        )
        pages = []
        for image in sorted(prefix.parent.glob("page-*.png")):
            result = subprocess.run(
                [str(tesseract), str(image), "stdout", "-l", "chi_sim+eng"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=True,
            )
            pages.append(clean_text(result.stdout))
        return pages


def normal_extraction_failed(pages: list[str]) -> bool:
    counts = [len(compact(page)) for page in pages]
    return not counts or sum(counts) < max(200, len(counts) * 40)


def title_from_filename(path: Path) -> tuple[str, str]:
    stem = path.stem.strip()
    author = ""
    match = re.search(r"_([\u4e00-\u9fff]{2,4})$", stem)
    if match:
        author = match.group(1)
        stem = stem[: match.start()]
    stem = re.sub(r"(?<!\d)_(?!\d)", "：", stem)
    return stem.strip(), author


def front_lines(pages: list[str], page_limit: int = 3) -> list[str]:
    return [
        clean_text(line)
        for page in pages[:page_limit]
        for line in page.splitlines()
        if clean_text(line)
    ]


def first_matching_page(pages: list[str], value: str) -> int | None:
    needle = compact(value)
    if not needle:
        return None
    for index, page in enumerate(pages, 1):
        if needle in compact(page):
            return index
    return None


def parse_author(lines: list[str], title: str, filename_author: str) -> tuple[str, int | None, str]:
    front = "\n".join(lines[:120])
    front_key = compact(front)
    title_key = compact(title)

    def split_names(raw_names: str) -> list[str]:
        if not 2 <= len(raw_names) <= 24:
            return []
        if any(marker in raw_names for marker in ("大学", "学院", "图书馆", "研究院")):
            return []
        if len(raw_names) <= 4:
            names = [raw_names]
        elif len(raw_names) % 3 == 0:
            names = [
                raw_names[index:index + 3]
                for index in range(0, len(raw_names), 3)
            ]
        elif filename_author and raw_names.startswith(filename_author):
            names = [filename_author]
            remainder = raw_names[len(filename_author):]
            if remainder and len(remainder) % 3 == 0:
                names.extend(
                    remainder[index:index + 3]
                    for index in range(0, len(remainder), 3)
                )
        else:
            names = []
        return names if names and all(2 <= len(name) <= 4 for name in names) else []

    for line in lines[:60]:
        line_key = compact(line)
        if title_key not in line_key:
            continue
        suffix = line_key.split(title_key, 1)[1].split("摘要", 1)[0]
        names = split_names(re.sub(r"[^\u4e00-\u9fff]", "", suffix))
        if names and (not filename_author or names[0] == filename_author):
            return "；".join(names), 1, "explicit"

    title_at = front_key.find(title_key)
    abstract_at = front_key.find("摘要", title_at + len(title_key)) if title_at >= 0 else -1
    if title_at >= 0 and abstract_at >= 0:
        raw_names = re.sub(
            r"[^\u4e00-\u9fff]",
            "",
            front_key[title_at + len(title_key):abstract_at],
        )
        names = split_names(raw_names)
        if names and (not filename_author or names[0] == filename_author):
            return "；".join(names), 1, "explicit"

    if filename_author:
        page = 1 if compact(filename_author) in front_key else None
        return filename_author, page, "explicit" if page else "inferred"

    title_index = 0
    for index, line in enumerate(lines[:80]):
        line_key = compact(line)
        if len(line_key) >= 5 and (line_key in title_key or title_key in line_key):
            title_index = index
    abstract_index = next(
        (index for index, line in enumerate(lines) if re.match(r"^摘要[:：]?", line)),
        min(len(lines), title_index + 12),
    )
    excluded = (
        "大学",
        "学院",
        "图书馆",
        "研究院",
        "研究",
        "学刊",
        "期刊",
        "年",
        "月",
        "摘要",
        "关键词",
        "基金",
        "项目",
        "doi",
        "issn",
        "中图",
        "作者简介",
    )
    candidates: list[tuple[int, str]] = []
    for index in range(title_index + 1, min(abstract_index, title_index + 10)):
        value = re.sub(r"[\d*＊¹²³⁴⁵⁶⁷⁸⁹（）()·•\s]", "", lines[index])
        if any(word in value.casefold() for word in excluded):
            continue
        if not re.fullmatch(r"[\u4e00-\u9fff,，、;；]+", value):
            continue
        names = [name for name in re.split(r"[,，、;；]", value) if name]
        if names and all(2 <= len(name) <= 5 for name in names) and len(names) <= 8:
            candidates.append((index, "；".join(names)))
    if candidates:
        _, value = candidates[-1]
        return value, 1, "explicit"
    return "", None, "not_reported"


def parse_year(lines: list[str]) -> tuple[int | None, int | None]:
    normalized = [unicodedata.normalize("NFKC", line) for line in lines[:120]]
    patterns = (
        r"(?<!\d)(20(?:1[3-9]|2[0-6]))\s*年\s*\d{1,2}\s*月",
        r"(?<!\d)(20(?:1[3-9]|2[0-6]))\s*年\s*第?\s*\d+\s*期",
        r"(?:收稿日期|出版日期)\s*[:：]?\s*(20(?:1[3-9]|2[0-6]))",
        r"(?:引用本文格式|本文引用格式).*?(20(?:1[3-9]|2[0-6]))\s*[（(]\s*\d+",
    )
    years = [
        int(match)
        for line in normalized
        for pattern in patterns
        for match in re.findall(pattern, line)
    ]
    front = " ".join(normalized)
    citation_match = re.search(
        r"(?:引用本文格式|本文引用格式).{0,300}?"
        r"(?<!\d)(20(?:1[3-9]|2[0-6]))(?!\d)",
        front,
    )
    if citation_match:
        years.append(int(citation_match.group(1)))
    if years:
        return max(years), 1
    return None, None


def parse_journal(lines: list[str]) -> tuple[str, int | None]:
    for line in lines[:40]:
        if "Journal of Library Science in China" in line:
            return "中国图书馆学报", 1
        for journal in JOURNAL_PATTERNS:
            if journal in line:
                if "专题" in line and ":" in line and journal == "图书馆理论与实践":
                    continue
                return journal, 1
    front = unicodedata.normalize("NFKC", "\n".join(lines[:120]))
    match = re.search(r"\[\s*J\s*\][.．]\s*([^，,。\n]{2,30})[，,]\s*20\d{2}", front, re.I)
    return (clean_text(match.group(1)), 1) if match else ("", None)


def parse_institution(lines: list[str]) -> tuple[str, int | None]:
    institution_pattern = re.compile(
        r"([\u4e00-\u9fff]{2,30}(?:大学|学院|研究院|职业技术学院)"
        r"(?:[\u4e00-\u9fff]{0,20}图书馆)?)"
    )
    for line in lines[:200]:
        if "作者简介" not in line:
            continue
        matches = institution_pattern.findall(line)
        if matches:
            return max(matches, key=len), 1

    markers = ("大学", "学院", "图书馆", "研究院", "职业技术学院", "学校")
    for line in lines[:100]:
        if not any(marker in line for marker in markers):
            continue
        if any(
            word in line
            for word in (
                "引用本文",
                "基金项目",
                "主办",
                "摘要",
                "关键词",
                "分类号",
                "专题",
                "journal",
            )
        ):
            continue
        if not (
            line.lstrip().startswith(("（", "("))
            or re.search(r"(?:作者单位|单位)\s*[:：]", line)
        ):
            continue
        if re.search(r"(?:作者单位|单位)\s*[:：]", line):
            line = re.split(r"(?:作者单位|单位)\s*[:：]", line, maxsplit=1)[1]
        value = re.sub(r"^[（(]\s*\d+[.．、]?\s*", "", line)
        value = re.sub(r"[）)]$", "", value)
        value = re.sub(r"\s*\d{6}\s*", "", value)
        value = clean_text(value).strip("（）() ")
        if 2 <= len(value) <= 120:
            return value, 1
    return "", None


def extract_labeled(text: str, start: str, ends: tuple[str, ...], limit: int = 3000) -> str:
    end_pattern = "|".join(ends)
    match = re.search(
        rf"{start}\s*[:：]\s*(.*?)(?={end_pattern})",
        text,
        re.I | re.S,
    )
    return clip(match.group(1), limit) if match else ""


def parse_abstract_keywords(pages: list[str]) -> tuple[str, list[str], int | None]:
    front = "\n".join(pages[:5])
    abstract_label = r"[［\[【]?\s*摘\s*要\s*[］\]】]?\s*[:：]?"
    keyword_label = r"[［\[【]?\s*关\s*键\s*词\s*[］\]】]?\s*[:：]?"
    abstract_match = re.search(
        rf"{abstract_label}\s*(.*?)(?={keyword_label})",
        front,
        re.I | re.S,
    )
    abstract = clip(abstract_match.group(1), 4000) if abstract_match else ""
    if not abstract:
        abstract_match = re.search(
            rf"{abstract_label}\s*(.*?)(?=\n\s*\n|$)",
            front,
            re.I | re.S,
        )
        abstract = clip(abstract_match.group(1), 4000) if abstract_match else ""
    keyword_match = re.search(
        rf"{keyword_label}\s*(.*?)(?="
        r"中图分类号|分类号|文献标志|引用本文格式|doi\s*[:：]|DOI\s*[:：]|"
        r"\n\s*Abstract\s*[:：]?|\n\s*0\s+引言|\n\s*1\s+引言|$)",
        front,
        re.I | re.S,
    )
    keyword_text = clip(keyword_match.group(1), 800) if keyword_match else ""
    keywords = [
        clean_text(item).strip("。.")
        for item in re.split(r"[;；,，]", keyword_text)
        if clean_text(item).strip("。.")
    ]
    if len(keywords) == 1 and len(keywords[0]) > 15:
        known = (
            "未来学习中心",
            "高校图书馆",
            "公共图书馆",
            "教学服务",
            "科研服务",
            "学习支持",
            "空间服务",
            "学习空间",
            "用户需求",
            "用户体验",
            "数智赋能",
            "教育数字化",
            "智慧图书馆",
            "人工智能",
            "服务创新",
        )
        segmented = [term for term in known if term in keywords[0]]
        if len(segmented) >= 2:
            keywords = segmented
    page = first_matching_page(pages, abstract[:80]) if abstract else None
    return abstract, keywords, page


def infer_language(pages: list[str]) -> str:
    body = "".join(pages)
    chinese = len(re.findall(r"[\u4e00-\u9fff]", body))
    latin = len(re.findall(r"[A-Za-z]", body))
    if chinese > latin:
        return "zh-CN"
    if latin > chinese:
        return "en"
    return "und"


def split_sentences(page: str) -> list[str]:
    return [
        clip(sentence, 700)
        for sentence in re.split(r"(?<=[。！？!?；;])|\n+", page)
        if len(compact(sentence)) >= 12
    ]


def sentence_hits(
    pages: list[str],
    markers: tuple[str, ...],
    *,
    page_scope: list[int] | None = None,
    require_number: bool = False,
    limit: int = 3,
) -> tuple[list[str], list[int]]:
    hits: list[str] = []
    hit_pages: list[int] = []
    indexes = page_scope or list(range(1, len(pages) + 1))
    for page_number in indexes:
        if not 1 <= page_number <= len(pages):
            continue
        for sentence in split_sentences(pages[page_number - 1]):
            low = sentence.casefold()
            if not any(marker.casefold() in low for marker in markers):
                continue
            if require_number and not re.search(r"\d", sentence):
                continue
            if sentence not in hits:
                hits.append(sentence)
                hit_pages.append(page_number)
            if len(hits) >= limit:
                return hits, sorted(set(hit_pages))
    return hits, sorted(set(hit_pages))


def field(value: str, status: str, pages: list[int] | None = None) -> dict[str, Any]:
    if not value:
        return {"value": "", "status": "not_reported", "evidence_pages": []}
    return {
        "value": clip(value),
        "status": status,
        "evidence_pages": sorted(set(pages or [])),
    }


def structured_abstract_segment(abstract: str, label: str, next_labels: tuple[str, ...]) -> str:
    next_pattern = "|".join(rf"[\[［【]\s*{item}.*?[\]］】]" for item in next_labels)
    match = re.search(
        rf"[\[［【]\s*{label}.*?[\]］】]\s*(.*?)(?={next_pattern}|$)",
        abstract,
        re.I | re.S,
    )
    return clip(match.group(1), 1400) if match else ""


def extract_theories(pages: list[str], title: str, abstract: str) -> tuple[list[str], list[int]]:
    scope = f"{title}\n{abstract}"
    low = scope.casefold()
    theories: list[str] = []
    evidence: list[int] = []
    for theory, terms in THEORY_TERMS.items():
        matched = next((term for term in terms if term.casefold() in low), None)
        if not matched:
            continue
        theories.append(theory)
        page = first_matching_page(pages[:4], matched)
        if page:
            evidence.append(page)
    return theories, sorted(set(evidence))


def extract_methods(
    pages: list[str], abstract: str, method_segment: str
) -> tuple[list[str], list[int]]:
    scope = f"{method_segment}\n{abstract}".casefold()
    methods: list[str] = []
    evidence: list[int] = []
    for method, terms in METHOD_TERMS.items():
        if method == "Case study":
            matched = (
                "案例分析"
                if "案例分析" in scope
                else "案例研究"
                if "案例研究" in scope
                else "多案例分析"
                if "多案例分析" in scope
                else None
            )
        else:
            matched = next((term for term in terms if term.casefold() in scope), None)
        if not matched:
            continue
        methods.append(method)
        page = first_matching_page(pages[:5], matched)
        if page:
            evidence.append(page)
    return methods, sorted(set(evidence))


def extract_research_site(title: str, abstract: str, pages: list[str]) -> dict[str, Any]:
    scope = f"{title}。{abstract}"
    patterns = (
        r"以([^。；;，,]{2,60}(?:大学|学院|图书馆|中心|成员馆))为例",
        r"基于([^。；;，,]{2,60}(?:大学|学院|图书馆|中心|成员馆))",
        r"选取([^。；;]{2,80})作为(?:案例|研究对象|调查对象)",
    )
    for pattern in patterns:
        match = re.search(pattern, scope)
        if match:
            value = match.group(1).strip("———-：: ")
            page = first_matching_page(pages[:5], value)
            return field(value, "explicit", [page] if page else [])
    return field("", "not_reported")


def extract_sample(pages: list[str], abstract: str) -> dict[str, Any]:
    sample_pattern = re.compile(
        r"(?:样本|调查对象|研究对象|发放问卷|回收问卷|有效问卷|受访者|"
        r"访谈对象|样本量|选取.{0,80}\d+\s*(?:所|家|个|名|份)|"
        r"\d+\s*(?:所高校|家图书馆|个案例|名受访者|份问卷))"
    )
    hits = [
        sentence
        for sentence in split_sentences(abstract)
        if sample_pattern.search(sentence)
    ][:2]
    evidence = [first_matching_page(pages[:5], hits[0])] if hits else []
    method_page_markers = (
        "研究设计",
        "研究方法",
        "调查设计",
        "问卷设计",
        "数据来源",
        "样本构成",
        "样本选择",
        "调查对象",
        "研究对象与方法",
    )
    if not hits:
        for page_number, page in enumerate(pages, 1):
            if not any(marker in page for marker in method_page_markers):
                continue
            for sentence in split_sentences(page):
                if not sample_pattern.search(sentence):
                    continue
                if sentence not in hits:
                    hits.append(sentence)
                    evidence.append(page_number)
                if len(hits) >= 2:
                    break
            if len(hits) >= 2:
                break
    return field(" ".join(hits), "explicit", [page for page in evidence if page])


def extract_analysis(metadata: dict[str, Any], pages: list[str]) -> dict[str, Any]:
    title = metadata["title"]
    abstract = metadata["abstract"]
    abstract_page = metadata["field_sources"].get("abstract_page")
    purpose = structured_abstract_segment(abstract, r"目的\s*/?\s*意义", ("方法", "结果"))
    method_segment = structured_abstract_segment(
        abstract, r"方法\s*/?\s*过程", ("结果", "结论")
    )
    result_segment = structured_abstract_segment(
        abstract, r"结果\s*/?\s*结论", ("创新", "关键词")
    )

    object_hits, object_pages = sentence_hits(
        pages[:8],
        ("研究对象为", "作为研究对象", "围绕", "面向"),
        limit=1,
    )
    if object_hits:
        research_object = field(object_hits[0], "explicit", object_pages)
    else:
        research_object = field(f"题名所指研究对象：{title}", "inferred", [1])

    question_hits, question_pages = sentence_hits(
        pages[:8],
        ("旨在", "目的在于", "目的/意义", "探讨", "研究问题", "考察"),
        limit=2,
    )
    if purpose:
        research_question = field(
            purpose,
            "explicit",
            [abstract_page] if abstract_page else question_pages,
        )
    elif question_hits:
        research_question = field(" ".join(question_hits), "explicit", question_pages)
    else:
        research_question = field(f"围绕“{title}”展开的核心问题", "inferred", [1])

    theories, theory_pages = extract_theories(pages, title, abstract)
    theoretical_framework = field("；".join(theories), "explicit", theory_pages)

    methods, method_pages = extract_methods(pages, abstract, method_segment)
    methodology = field("；".join(methods), "explicit", method_pages)

    research_site = extract_research_site(title, abstract, pages)
    sample = extract_sample(pages, abstract)

    argument_hits, argument_pages = sentence_hits(
        pages,
        ("提出", "构建", "认为", "指出", "阐释", "建议", "路径", "策略"),
        page_scope=list(range(1, min(len(pages), 6) + 1)),
        limit=3,
    )
    if not argument_hits:
        tail_scope = list(range(max(1, len(pages) - 3), len(pages) + 1))
        argument_hits, argument_pages = sentence_hits(
            pages, ("提出", "构建", "认为", "建议", "路径", "策略"),
            page_scope=tail_scope, limit=3
        )
    main_arguments = field(" ".join(argument_hits), "explicit", argument_pages)

    finding_hits, finding_pages = sentence_hits(
        pages,
        ("研究发现", "结果表明", "研究结果", "调查显示", "结果显示"),
        page_scope=list(range(1, min(len(pages), 10) + 1)),
        limit=3,
    )
    if result_segment:
        findings = field(
            result_segment,
            "explicit",
            [abstract_page] if abstract_page else finding_pages,
        )
    else:
        findings = field(" ".join(finding_hits), "explicit", finding_pages)

    tail_scope = list(range(max(1, len(pages) - 4), len(pages) + 1))
    limitation_hits, limitation_pages = sentence_hits(
        pages,
        ("研究局限", "局限性", "不足之处", "存在不足", "有待进一步", "未来研究"),
        page_scope=tail_scope,
        limit=3,
    )
    limitations = field(" ".join(limitation_hits), "explicit", limitation_pages)

    values = {
        "research_object": research_object,
        "research_question": research_question,
        "theoretical_framework": theoretical_framework,
        "methodology": methodology,
        "research_site": research_site,
        "sample": sample,
        "main_arguments": main_arguments,
        "findings": findings,
        "limitations": limitations,
    }
    evidence_pages = sorted(
        {
            page
            for item in values.values()
            for page in item["evidence_pages"]
        }
    )
    return {
        **values,
        "theories": theories,
        "methods": methods,
        "evidence_pages": evidence_pages,
    }


def classify_themes(metadata: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    title = metadata["title"]
    scope = (
        f"{title}\n{metadata['abstract']}\n{'；'.join(metadata['keywords'])}"
    ).casefold()
    relevance_terms = ("未来学习中心", "学习中心", "图书馆", "学习空间", "智慧空间")
    if not any(term in scope for term in relevance_terms):
        return {
            "scope_status": "out_of_scope",
            "primary_theme": "",
            "secondary_themes": [],
            "theme_scores": {},
        }
    if any(term in title for term in ("十五五", "规划")) and "未来学习中心" not in title:
        scope_status = "background_only"
    else:
        scope_status = "included"

    scores: dict[str, int] = {}
    title_low = title.casefold()
    for theme_id, terms in THEME_TERMS.items():
        score = 0
        for term, weight in terms.items():
            term_low = term.casefold()
            if term_low in scope:
                score += weight
            if term_low in title_low:
                score += weight
        scores[theme_id] = score
    ordered = sorted(scores, key=lambda theme_id: (-scores[theme_id], theme_id))
    title_overrides = (
        ("T7", ("国外", "国际", "中外", "海外", "哈佛", "ARL")),
        ("T4", ("用户需求", "用户体验", "用户行为", "采纳意愿", "需求研究", "效果评价")),
        ("T3", ("学习支持", "教学支持", "科研服务", "学业规划", "阅读服务")),
        ("T2", ("空间服务", "空间再造", "空间设计", "空间建设", "学习共享空间", "智慧空间")),
        ("T5", ("人工智能", "AIGC", "ChatGPT", "大语言模型", "大模型", "智能体", "元宇宙", "数字孪生")),
        ("T1", ("概念", "理论", "逻辑", "内涵", "思考")),
    )
    primary = next(
        (
            theme_id
            for theme_id, terms in title_overrides
            if any(term.casefold() in title_low for term in terms)
        ),
        ordered[0] if scores[ordered[0]] > 0 else "",
    )
    secondary = [
        theme_id
        for theme_id in ordered[1:]
        if scores[theme_id] >= 4 and scores[theme_id] >= scores[primary] * 0.45
    ][:3] if primary else []
    return {
        "scope_status": scope_status,
        "primary_theme": primary,
        "secondary_themes": secondary,
        "theme_scores": scores,
    }


def priority_scores(record: dict[str, Any]) -> dict[str, int]:
    title = record["metadata"]["title"]
    analysis = record["analysis"]
    theme = record["theme"]
    year = record["metadata"]["year"]
    theoretical = min(
        5,
        (3 if analysis["theories"] else 0)
        + (2 if any(term in title for term in ("理论", "概念", "内涵", "逻辑", "框架", "模型")) else 0),
    )
    rigor = min(
        5,
        (2 if analysis["methodology"]["status"] == "explicit" else 0)
        + (2 if analysis["sample"]["status"] == "explicit" else 0)
        + (1 if len(analysis["methods"]) >= 2 else 0),
    )
    relevance = min(
        5,
        (3 if "未来学习中心" in title else 1)
        + (1 if "图书馆" in title else 0)
        + (1 if theme["primary_theme"] in THEMES else 0),
    )
    value = min(
        5,
        (2 if any(term in title for term in ("研究进展", "热点", "趋势", "综述", "全球", "比较")) else 0)
        + (1 if year and year <= 2022 else 0)
        + (1 if any(term in title for term in ("概念", "内涵", "理论", "框架", "要素", "体系")) else 0)
        + (1 if analysis["findings"]["status"] == "explicit" else 0),
    )
    return {
        "theoretical_contribution": theoretical,
        "methodological_rigor": rigor,
        "relevance": relevance,
        "citation_value_potential": value,
        "total": theoretical + rigor + relevance + value,
    }


def write_extracted(path: Path, record: dict[str, Any], pages: list[str]) -> None:
    lines = [
        f"# {record['metadata']['title']}",
        "",
        f"stable_id: {record['stable_id']}",
        f"source_file: {record['relative_path']}",
        f"extraction_method: {record['extraction_method']}",
        f"extraction_status: {record['extraction_status']}",
        "",
    ]
    for number, page in enumerate(pages, 1):
        lines.extend([f"<!-- PAGE {number} -->", f"## PDF page {number}", "", page, ""])
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def build_metadata(pdf: Path, pages: list[str], relative_path: str) -> dict[str, Any]:
    title, filename_author = title_from_filename(pdf)
    lines = front_lines(pages)
    author, author_page, author_status = parse_author(lines, title, filename_author)
    year, year_page = parse_year(lines)
    journal, journal_page = parse_journal(lines)
    institution, institution_page = parse_institution(lines)
    abstract, keywords, abstract_page = parse_abstract_keywords(pages)
    title_page = first_matching_page(pages[:3], title) or 1
    return {
        "title": title,
        "author": author,
        "year": year,
        "journal": journal,
        "institution": institution,
        "keywords": keywords,
        "abstract": abstract,
        "language": infer_language(pages),
        "field_sources": {
            "title_page": title_page,
            "title_status": "explicit" if first_matching_page(pages[:3], title) else "inferred",
            "author_page": author_page,
            "author_status": author_status,
            "year_page": year_page,
            "journal_page": journal_page,
            "institution_page": institution_page,
            "abstract_page": abstract_page,
            "keywords_page": abstract_page,
            "relative_path": relative_path,
        },
    }


def failure_record(pdf: Path, relative_path: str, digest: str, error: Exception) -> dict[str, Any]:
    stable_id = f"FLC-{digest[:12].upper()}"
    metadata = {
        "title": title_from_filename(pdf)[0],
        "author": title_from_filename(pdf)[1],
        "year": None,
        "journal": "",
        "institution": "",
        "keywords": [],
        "abstract": "",
        "language": "und",
        "field_sources": {"relative_path": relative_path},
    }
    analysis = {
        **{name: field("", "not_reported") for name in ANALYSIS_FIELDS},
        "theories": [],
        "methods": [],
        "evidence_pages": [],
    }
    return {
        "stable_id": stable_id,
        "filename": pdf.name,
        "relative_path": relative_path,
        "sha256": digest,
        "page_count": 0,
        "extraction_method": "none",
        "extraction_status": "failed",
        "extraction_error": f"{type(error).__name__}: {error}",
        "metadata": metadata,
        "analysis": analysis,
        "theme": {
            "scope_status": "background_only",
            "primary_theme": "",
            "secondary_themes": [],
            "theme_scores": {},
        },
        "priority_scores": {
            "theoretical_contribution": 0,
            "methodological_rigor": 0,
            "relevance": 0,
            "citation_value_potential": 0,
            "total": 0,
        },
    }


def process_pdf(
    pdf: Path,
    corpus: Path,
    pdftotext: Path,
    pdftoppm: Path,
    tesseract: Path,
) -> tuple[dict[str, Any], list[str]]:
    relative_path = pdf.relative_to(corpus).as_posix()
    digest = sha256(pdf)
    stable_id = f"FLC-{digest[:12].upper()}"
    try:
        if pdf.stat().st_size == 0:
            raise ValueError("zero-byte PDF")
        pages_expected = page_count(pdf)
        pages = run_pdftotext(pdf, pdftotext, pages_expected)
        method = "pdftotext"
        if normal_extraction_failed(pages):
            pages = run_ocr(pdf, pdftoppm, tesseract)
            method = "ocr:chi_sim+eng"
        if normal_extraction_failed(pages):
            raise ValueError("text extraction remained insufficient after OCR")
        metadata = build_metadata(pdf, pages, relative_path)
        analysis = extract_analysis(metadata, pages)
        record = {
            "stable_id": stable_id,
            "filename": pdf.name,
            "relative_path": relative_path,
            "sha256": digest,
            "page_count": pages_expected,
            "extraction_method": method,
            "extraction_status": "success",
            "extraction_error": "",
            "metadata": metadata,
            "analysis": analysis,
        }
        record["theme"] = classify_themes(metadata, analysis)
        record["priority_scores"] = priority_scores(record)
        return record, pages
    except Exception as error:
        return failure_record(pdf, relative_path, digest, error), []


def workbook_payload(records: list[dict[str, Any]], qa: dict[str, Any]) -> dict[str, Any]:
    papers = []
    evidence = []
    for record in records:
        metadata = record["metadata"]
        analysis = record["analysis"]
        theme = record["theme"]
        scores = record["priority_scores"]
        papers.append(
            {
                "stable_id": record["stable_id"],
                "filename": record["filename"],
                "relative_path": record["relative_path"],
                "sha256": record["sha256"],
                "page_count": record["page_count"],
                "extraction_method": record["extraction_method"],
                "extraction_status": record["extraction_status"],
                "title": metadata["title"],
                "author": metadata["author"],
                "year": metadata["year"],
                "journal": metadata["journal"],
                "institution": metadata["institution"],
                "keywords": "；".join(metadata["keywords"]),
                "abstract": metadata["abstract"],
                "language": metadata["language"],
                "scope_status": theme["scope_status"],
                "primary_theme": THEMES.get(theme["primary_theme"], ""),
                "secondary_themes": "；".join(
                    THEMES[theme_id] for theme_id in theme["secondary_themes"]
                ),
                "theories": "；".join(analysis["theories"]),
                "methods": "；".join(analysis["methods"]),
                "priority_total": scores["total"],
                "extraction_error": record["extraction_error"],
            }
        )
        for name in ANALYSIS_FIELDS:
            item = analysis[name]
            evidence.append(
                {
                    "stable_id": record["stable_id"],
                    "field": name,
                    "status": item["status"],
                    "value": item["value"],
                    "evidence_pages": ",".join(map(str, item["evidence_pages"])),
                    "source_file": record["relative_path"],
                }
            )
    themes = []
    for theme_id, theme_name in THEMES.items():
        ids = [
            record["stable_id"]
            for record in records
            if record["theme"]["primary_theme"] == theme_id
            or theme_id in record["theme"]["secondary_themes"]
        ]
        primary_count = sum(
            record["theme"]["primary_theme"] == theme_id for record in records
        )
        themes.append(
            {
                "theme_id": theme_id,
                "theme": theme_name,
                "primary_count": primary_count,
                "all_coded_count": len(ids),
                "paper_ids": "；".join(ids),
            }
        )
    return {"papers": papers, "evidence": evidence, "themes": themes, "qa": qa}


def build_literature_map(records: list[dict[str, Any]]) -> dict[str, Any]:
    theme_map: dict[str, list[str]] = defaultdict(list)
    theory_map: dict[str, list[str]] = defaultdict(list)
    method_map: dict[str, list[str]] = defaultdict(list)
    relationships = []
    papers = []
    for record in records:
        stable_id = record["stable_id"]
        analysis = record["analysis"]
        theme = record["theme"]
        paper = {
            "stable_id": stable_id,
            "title": record["metadata"]["title"],
            "author": record["metadata"]["author"],
            "year": record["metadata"]["year"],
            "journal": record["metadata"]["journal"],
            "scope_status": theme["scope_status"],
            "primary_theme": theme["primary_theme"],
            "secondary_themes": theme["secondary_themes"],
            "theories": analysis["theories"],
            "methods": analysis["methods"],
            "evidence_locations": {
                name: analysis[name]["evidence_pages"] for name in ANALYSIS_FIELDS
            },
        }
        papers.append(paper)
        for role, theme_ids in (
            ("primary_theme", [theme["primary_theme"]] if theme["primary_theme"] else []),
            ("secondary_theme", theme["secondary_themes"]),
        ):
            for theme_id in theme_ids:
                theme_map[theme_id].append(stable_id)
                relationships.append(
                    {"source": stable_id, "target": theme_id, "type": role}
                )
        for theory in analysis["theories"]:
            theory_id = f"THEORY-{hashlib.sha1(theory.encode()).hexdigest()[:10].upper()}"
            theory_map[theory].append(stable_id)
            relationships.append(
                {"source": stable_id, "target": theory_id, "type": "uses_theory"}
            )
        for method in analysis["methods"]:
            method_id = f"METHOD-{hashlib.sha1(method.encode()).hexdigest()[:10].upper()}"
            method_map[method].append(stable_id)
            relationships.append(
                {"source": stable_id, "target": method_id, "type": "uses_method"}
            )
    return {
        "papers": papers,
        "themes": [
            {
                "id": theme_id,
                "name": THEMES[theme_id],
                "paper_ids": sorted(set(theme_map[theme_id])),
            }
            for theme_id in THEMES
        ],
        "theories": [
            {
                "id": f"THEORY-{hashlib.sha1(name.encode()).hexdigest()[:10].upper()}",
                "name": name,
                "paper_ids": sorted(set(ids)),
            }
            for name, ids in sorted(theory_map.items())
        ],
        "methods": [
            {
                "id": f"METHOD-{hashlib.sha1(name.encode()).hexdigest()[:10].upper()}",
                "name": name,
                "paper_ids": sorted(set(ids)),
            }
            for name, ids in sorted(method_map.items())
        ],
        "relationships": relationships,
    }


def representative_titles(
    records: list[dict[str, Any]], theme_id: str, limit: int = 3
) -> list[str]:
    choices = [
        record for record in records
        if record["theme"]["primary_theme"] == theme_id
        and record["extraction_status"] == "success"
    ]
    choices.sort(key=lambda record: (-record["priority_scores"]["total"], record["stable_id"]))
    return [
        f"{record['metadata']['title']}（{record['stable_id']}）"
        for record in choices[:limit]
    ]


def build_review(records: list[dict[str, Any]]) -> str:
    successful = [record for record in records if record["extraction_status"] == "success"]
    included = [record for record in successful if record["theme"]["scope_status"] == "included"]
    years = Counter(
        record["metadata"]["year"]
        for record in successful
        if record["metadata"]["year"]
    )
    themes = Counter(record["theme"]["primary_theme"] for record in included)
    methods = Counter(
        method for record in included for method in record["analysis"]["methods"]
    )
    theories = Counter(
        theory for record in included for theory in record["analysis"]["theories"]
    )
    status_counts = {
        name: Counter(record["analysis"][name]["status"] for record in successful)
        for name in ANALYSIS_FIELDS
    }
    recent_ai = sum(
        bool(
            record["theme"]["primary_theme"] == "T5"
            and record["metadata"]["year"] is not None
            and record["metadata"]["year"] >= 2024
        )
        for record in included
    )
    empirical = sum(
        any(
            method in record["analysis"]["methods"]
            for method in (
                "Questionnaire survey",
                "Interview",
                "Case study",
                "Grounded theory",
                "KANO analysis",
                "Structural equation modelling",
                "fsQCA",
            )
        )
        for record in included
    )

    year_rows = "\n".join(
        f"| {year} | {count} |" for year, count in sorted(years.items())
    ) or "| Unknown | 0 |"
    theme_rows = "\n".join(
        f"| {THEMES[theme_id]} | {themes[theme_id]} | "
        f"{'；'.join(representative_titles(included, theme_id)) or '—'} |"
        for theme_id in THEMES
    )
    method_rows = "\n".join(
        f"| {method} | {count} |" for method, count in methods.most_common()
    ) or "| Not explicitly reported | 0 |"
    theory_rows = "；".join(f"{name}（{count}）" for name, count in theories.most_common()) or "多数论文未明确报告理论框架"
    missing_method = status_counts["methodology"]["not_reported"]
    missing_sample = status_counts["sample"]["not_reported"]
    missing_limit = status_counts["limitations"]["not_reported"]

    return f"""# Research Landscape

本数据库系统整理了 {len(records)} 份 PDF，其中 {len(successful)} 份完成页面级文本提取，{len(records) - len(successful)} 份因文件完整性问题保留失败状态。纳入主题分析的论文共 {len(included)} 篇。语料明显集中在 2024—2025 年，因此本报告首先刻画的是未来学习中心概念在中国高校图书馆领域的快速扩散，而不是一个时间分布均衡的长期样本。

| 出版年 | 论文数 |
|---:|---:|
{year_rows}

# Concept Evolution

早期文献主要把未来学习中心视为学习空间、资源整合与教学支持的延伸；2021 年以后，研究逐渐把高校图书馆定位为未来学习中心的组织载体，并将空间再造、服务育人和教育数字化连接起来。2024 年后，概念进一步吸收生成式人工智能、数智治理、智能体、数字孪生与沉浸式场景等术语。这个演化并非简单的技术升级：语料同时保留了“学习组织”“服务模式”“空间场景”和“育人范式”等多条概念线索。

明确识别到的理论或模型包括：{theory_rows}。理论框架总体呈现“少数论文明确采用、更多论文隐含借用”的格局；未明确报告者在数据库中标记为 `not_reported`，不以主题词替代理论声明。

# Major Research Themes

| 主题 | 主主题论文数 | 代表论文 |
|---|---:|---|
{theme_rows}

主题分布说明，国内研究的核心问题已经从“是否建设未来学习中心”转向“如何以空间、技术、服务和治理共同支撑学习方式变革”。空间与数智技术是最常见的实现抓手，用户需求与学习支持则构成评价这些建设是否真正有效的关键维度。国际比较研究数量较少，更多用于提供案例启示，而不是形成可直接比较的跨国证据。

# Methods Used

共 {empirical} 篇论文在摘要或正文中明确出现问卷、访谈、案例、扎根理论、KANO、结构方程或 fsQCA 等经验方法。其余研究较多采用文献调研、网络调查、案例归纳、文献计量或概念分析，但只有作者明确说明的方法才进入下表。

| 明确报告的方法 | 论文数 |
|---|---:|
{method_rows}

方法信息缺失是一个重要结果：{missing_method} 篇未明确报告 methodology，{missing_sample} 篇未明确报告 sample。数据库没有把一般性论述自动写成“文献研究法”，也没有为概念论文虚构样本。

# Current Research Trends

第一，数智化研究快速增长。2024 年以来以数字智能、AI 或智慧服务为主主题的论文有 {recent_ai} 篇，关注点从 ChatGPT/AIGC 的能力讨论扩展到大模型、智能体、数字孪生、多模态知识组织及其风险治理。

第二，空间研究从面积和设施配置转向场景化、沉浸式和复合共享，强调物理空间、数字平台和学习活动的一体化。

第三，服务研究逐步从资源供给转向学习支持、教学科研协同、学业规划和服务育人。用户需求、采纳意愿、体验评价及行为数据开始进入建设决策。

第四，治理研究开始讨论跨部门协同、敏捷治理、馆员能力、资源整合和组织机制，说明未来学习中心正在被视为制度与服务系统，而不只是空间项目。

# Research Gaps

- **经验评价不足。** 建设路径和规范性论述多，投入使用后的学习效果、持续使用、服务质量和成本效益证据相对有限。
- **样本与方法透明度不足。** {missing_sample} 篇未明确报告样本，限制了结论的可复核性和可迁移性。
- **理论累积较弱。** 明确理论框架集中在少数论文，概念、机制、结果变量之间尚未形成稳定的可检验模型。
- **用户结果弱于建设叙事。** 用户需求研究已经出现，但学习成效、行为改变、不同群体差异和长期体验仍未成为多数研究的主线。
- **局限报告不足。** {missing_limit} 篇未明确报告限制或未来研究边界，容易把案例启示扩大为普遍结论。
- **国际可比性有限。** 国外实践多以案例启示形式进入中文文献，缺少统一指标、同口径样本和制度差异控制。

# Future Directions

1. 建立以学习成效、服务使用、用户体验和公平性为核心的结果评价框架，避免只以设施或技术部署衡量建设完成度。
2. 推进纵向研究、准实验、跨校比较和多源行为数据研究，同时公开样本、工具、变量定义和分析步骤。
3. 将 AI 与智能体研究从功能设想推进到可验证的服务流程，评估准确性、隐私、偏差、可解释性和馆员责任边界。
4. 研究物理空间、数字平台、资源组织、课程支持与治理机制之间的耦合，而不是把各要素分散为独立建设清单。
5. 建立国际比较的共同维度，明确制度环境、经费模式、用户结构与服务目标，区分可迁移机制和情境依赖做法。
6. 加强特殊用户群体、无障碍学习、职业院校与非高校场景研究，检验未来学习中心是否真正扩大了学习支持的覆盖面。
"""


def priority_reason(record: dict[str, Any]) -> str:
    parts = []
    analysis = record["analysis"]
    if analysis["theories"]:
        parts.append(f"明确采用{'、'.join(analysis['theories'][:2])}")
    if analysis["methods"]:
        parts.append(f"方法包含{'、'.join(analysis['methods'][:2])}")
    if analysis["sample"]["status"] == "explicit":
        parts.append("报告了样本或调查范围")
    if any(term in record["metadata"]["title"] for term in ("研究进展", "热点", "趋势", "全球", "比较")):
        parts.append("具有综述或比较价值")
    if not parts:
        parts.append("与未来学习中心核心议题高度相关")
    return "；".join(parts) + "。"


def build_priority_list(records: list[dict[str, Any]], limit: int = 25) -> str:
    candidates = [
        record for record in records
        if record["extraction_status"] == "success"
        and record["theme"]["scope_status"] == "included"
    ]
    candidates.sort(
        key=lambda record: (
            -record["priority_scores"]["total"],
            -record["priority_scores"]["methodological_rigor"],
            -record["priority_scores"]["theoretical_contribution"],
            record["stable_id"],
        )
    )
    lines = [
        "# Priority Reading List",
        "",
        "本排序是语料内部的研究价值排序，不代表真实引用次数。总分由理论贡献、方法严谨性、主题相关性和潜在引用/综述价值四项组成，每项 0—5 分。",
        "",
        "| Rank | ID | Title | Year | Theme | Theory | Method | Relevance | Value | Total | Why it matters |",
        "|---:|---|---|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for rank, record in enumerate(candidates[:limit], 1):
        metadata = record["metadata"]
        scores = record["priority_scores"]
        lines.append(
            f"| {rank} | {record['stable_id']} | {metadata['title'].replace('|', '/')} | "
            f"{metadata['year'] or '—'} | {THEMES[record['theme']['primary_theme']]} | "
            f"{scores['theoretical_contribution']} | {scores['methodological_rigor']} | "
            f"{scores['relevance']} | {scores['citation_value_potential']} | "
            f"{scores['total']} | {priority_reason(record).replace('|', '/')} |"
        )
    lines += [
        "",
        "## Reading strategy",
        "",
        "- 先读理论贡献和综述价值较高的论文，建立概念与演化框架。",
        "- 再读方法得分较高的调查、案例、KANO、扎根理论或组态研究，核对证据强度。",
        "- 最后按空间、学习支持、用户需求、AI 与治理主题补足专题阅读。",
        "- 每篇论文的字段证据页见 `future_learning_center_database.xlsx` 的 Evidence sheet 和 `literature_map.json`。",
    ]
    return "\n".join(lines) + "\n"


def qa_summary(records: list[dict[str, Any]], expected: int) -> dict[str, Any]:
    ids = [record["stable_id"] for record in records]
    extraction = Counter(record["extraction_status"] for record in records)
    scope = Counter(record["theme"]["scope_status"] for record in records)
    theme_counts = Counter(record["theme"]["primary_theme"] for record in records)
    metadata_fields = ("title", "author", "year", "journal", "institution", "keywords", "abstract", "language")
    metadata_missing = {
        name: sum(not record["metadata"].get(name) for record in records)
        for name in metadata_fields
    }
    analysis_status = {
        name: dict(Counter(record["analysis"][name]["status"] for record in records))
        for name in ANALYSIS_FIELDS
    }
    checks = {
        "all_inputs_accounted_for": len(records) == expected,
        "stable_ids_unique": len(ids) == len(set(ids)),
        "all_records_have_extraction_status": all(record["extraction_status"] for record in records),
        "all_analysis_items_have_valid_status": all(
            record["analysis"][name]["status"] in {"explicit", "inferred", "not_reported"}
            for record in records
            for name in ANALYSIS_FIELDS
        ),
        "all_evidence_pages_valid": all(
            1 <= page <= record["page_count"]
            for record in records
            for name in ANALYSIS_FIELDS
            for page in record["analysis"][name]["evidence_pages"]
        ),
    }
    return {
        "expected_pdf_count": expected,
        "record_count": len(records),
        "extraction_status": dict(extraction),
        "scope_status": dict(scope),
        "primary_theme_counts": {
            THEMES.get(theme_id, "Unclassified"): count
            for theme_id, count in theme_counts.items()
        },
        "metadata_missing": metadata_missing,
        "analysis_status": analysis_status,
        "checks": checks,
        "failed_records": [
            {
                "stable_id": record["stable_id"],
                "filename": record["filename"],
                "error": record["extraction_error"],
            }
            for record in records
            if record["extraction_status"] != "success"
        ],
    }


def qa_markdown(qa: dict[str, Any]) -> str:
    checks = "\n".join(
        f"- [{'x' if passed else ' '}] {name}"
        for name, passed in qa["checks"].items()
    )
    failures = "\n".join(
        f"- {item['stable_id']} — {item['filename']}: {item['error']}"
        for item in qa["failed_records"]
    ) or "- None"
    missing = "\n".join(
        f"| {name} | {count} |" for name, count in qa["metadata_missing"].items()
    )
    return f"""# Corpus QA Report

## Reconciliation

- Expected PDFs: {qa['expected_pdf_count']}
- Records created: {qa['record_count']}
- Extraction status: {json.dumps(qa['extraction_status'], ensure_ascii=False)}
- Scope status: {json.dumps(qa['scope_status'], ensure_ascii=False)}

## Integrity checks

{checks}

## Metadata completeness

| Field | Missing records |
|---|---:|
{missing}

## Extraction failures

{failures}

## Interpretation

An extraction failure remains in the database and QA outputs; it is never silently excluded. `not_reported` means the field was not explicitly supported by the extracted document evidence, not that the concept is necessarily absent from the underlying research.
"""


def validate_outputs(output: Path, expected_count: int) -> dict[str, Any]:
    manifest_path = output / "processed/manifest.jsonl"
    records = [
        json.loads(line)
        for line in manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if len(records) != expected_count:
        raise RuntimeError(f"Manifest has {len(records)} records; expected {expected_count}")
    ids = {record["stable_id"] for record in records}
    if len(ids) != expected_count:
        raise RuntimeError("Stable IDs are not unique")
    literature_map = json.loads((output / "literature_map.json").read_text(encoding="utf-8"))
    map_ids = {paper["stable_id"] for paper in literature_map["papers"]}
    if map_ids != ids:
        raise RuntimeError("literature_map.json paper IDs do not match manifest")
    relationship_sources = {
        relationship["source"] for relationship in literature_map["relationships"]
    }
    if not relationship_sources.issubset(ids):
        raise RuntimeError("literature_map.json contains invalid relationship sources")
    for record in records:
        stable_id = record["stable_id"]
        for folder in ("extracted_text", "metadata", "analysis"):
            suffix = ".md" if folder == "extracted_text" else ".json"
            path = output / "processed" / folder / f"{stable_id}{suffix}"
            if not path.is_file():
                raise RuntimeError(f"Missing processed artifact: {path}")
    for filename in ("thematic_review.md", "priority_reading_list.md", "literature_map.json"):
        if not (output / filename).is_file():
            raise RuntimeError(f"Missing final artifact: {filename}")
    qa = qa_summary(records, expected_count)
    if not all(qa["checks"].values()):
        raise RuntimeError(f"QA checks failed: {qa['checks']}")
    return qa


def build(corpus: Path, output: Path, limit: int | None = None) -> None:
    if output.exists():
        raise FileExistsError(f"Output path already exists: {output}")
    pdfs = sorted(corpus.rglob("*.pdf"), key=lambda path: path.relative_to(corpus).as_posix().casefold())
    if limit:
        pdfs = pdfs[:limit]
    if not pdfs:
        raise FileNotFoundError(f"No PDFs found under {corpus}")

    pdftotext = find_tool(
        [
            Path(r"C:\texlive\2026\bin\windows\pdftotext.exe"),
            Path("pdftotext.exe"),
        ]
    )
    pdftoppm = find_tool(
        [
            Path(r"C:\texlive\2026\bin\windows\pdftoppm.exe"),
            Path("pdftoppm.exe"),
        ]
    )
    tesseract = find_tool(
        [
            Path(r"D:\Tesseract-OCR\tesseract.exe"),
            Path("tesseract.exe"),
        ]
    )

    processed = output / "processed"
    extracted_dir = processed / "extracted_text"
    metadata_dir = processed / "metadata"
    analysis_dir = processed / "analysis"
    for path in (extracted_dir, metadata_dir, analysis_dir):
        path.mkdir(parents=True, exist_ok=False)

    records = []
    for index, pdf in enumerate(pdfs, 1):
        record, pages = process_pdf(pdf, corpus, pdftotext, pdftoppm, tesseract)
        stable_id = record["stable_id"]
        write_extracted(extracted_dir / f"{stable_id}.md", record, pages)
        (metadata_dir / f"{stable_id}.json").write_text(
            json.dumps(
                {
                    "stable_id": stable_id,
                    "filename": record["filename"],
                    "relative_path": record["relative_path"],
                    "sha256": record["sha256"],
                    "page_count": record["page_count"],
                    "extraction_method": record["extraction_method"],
                    "extraction_status": record["extraction_status"],
                    **record["metadata"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
            newline="\n",
        )
        (analysis_dir / f"{stable_id}.json").write_text(
            json.dumps(
                {
                    "stable_id": stable_id,
                    **record["analysis"],
                    **record["theme"],
                    "priority_scores": record["priority_scores"],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
            newline="\n",
        )
        records.append(record)
        print(
            f"[{index:03d}/{len(pdfs):03d}] {stable_id} "
            f"{record['extraction_status']} {record['filename']}"
        )

    qa = qa_summary(records, len(pdfs))
    (processed / "manifest.jsonl").write_text(
        "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (processed / "qa_report.md").write_text(
        qa_markdown(qa), encoding="utf-8", newline="\n"
    )
    (processed / "workbook_data.json").write_text(
        json.dumps(workbook_payload(records, qa), ensure_ascii=False),
        encoding="utf-8",
    )
    (output / "literature_map.json").write_text(
        json.dumps(build_literature_map(records), ensure_ascii=False, indent=2),
        encoding="utf-8",
        newline="\n",
    )
    (output / "thematic_review.md").write_text(
        build_review(records), encoding="utf-8", newline="\n"
    )
    (output / "priority_reading_list.md").write_text(
        build_priority_list(records), encoding="utf-8", newline="\n"
    )
    validate_outputs(output, len(pdfs))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--corpus", type=Path, default=Path("otherneeds"))
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    corpus = args.corpus.resolve()
    output = (args.output or corpus).resolve()
    if args.validate_only:
        expected = args.limit or len(list(corpus.rglob("*.pdf")))
        qa = validate_outputs(output, expected)
        print(json.dumps(qa["checks"], ensure_ascii=False))
        return
    build(corpus, output, args.limit)


if __name__ == "__main__":
    main()
