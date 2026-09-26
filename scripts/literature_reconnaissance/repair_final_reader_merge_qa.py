from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PAPERS_ROOT = ROOT / "docs/literature_reconnaissance/papers"
READERS = PAPERS_ROOT / "readers"
STATUS_PATH = PAPERS_ROOT / "MUST_READ_FINAL_MERGE_STATUS.json"
ORDER = ["B05", "A04", "A03", "E01", "D03"]


def load_merge_module():
    path = Path(__file__).with_name("merge_must_read_work_notes.py")
    spec = importlib.util.spec_from_file_location("merge_module", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("unable to load merge module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


CONFLICTS = {
    "B05": [
        "B05-C01: Draft用p002-b001（期刊页眉）支持常规t门槛；最终改用摘要p001-b004及p002-b002。",
        "B05-C02: Draft对316个因子的定位过粗；最终改用p003-b003/p004-b002，并以结论p032-b003复核。",
        "B05-C03: Draft把p032-b002作为t>3主证据；最终改用p032-b003+p033-b002，并明确约3是依赖错误目标、相关性和隐藏试验的经验数量级。",
        "B05-C04: Work的V/R、FWER/FDR公式是教学重记号，不是PDF逐字符原式；最终保留为WORK EXPLANATION。",
    ],
    "A04": [
        "A04-C01: Draft的447/286/380等数字使用页眉或续文locator；最终改用p003-b002、p003-b009至p003-b013及p033-b011至p033-b019。",
        "A04-C02: Draft误述Table 1-6用途并合并页码；最终按tables_index分别修正至p48、p57、p58、p60、p62、p64。",
        "A04-C03: Work的H-L、t统计量和q-factor回归为教学表达，非PDF逐字符方程；最终标为WORK EXPLANATION且partially_verified。",
    ],
    "A03": [
        "A03-C01: Work把成本参数c写成也与price impact有关；PDF p6-7表明它对应Hasbrouck有效买卖价差，且price impact未被覆盖，最终据此修正。",
        "A03-C02: break-even cost是Work教学诊断式，不是论文原文术语或编号公式；最终删除虚假PDF来源并重分类。",
        "A03-C03: Draft漏列Figure 7；最终补充PDF p47 p047-b001，并保留未生成可靠裁剪资产的限制。",
    ],
    "E01": [
        "E01-C01: Draft把Figure 2a/2b都放在p13；最终拆为Figure 2a p13 p013-b005、Figure 2b p14 p014-b005。",
        "E01-C02: Draft把Figure 3a/3b都放在p18；最终拆为Figure 3a p18 p018-b006、Figure 3b p19 p019-b005，并把事件聚集主定位改为p15。",
    ],
    "D03": [
        "D03-C01: Work把第一年低量赢家优势概括过强；最终注明多数赢家cell差异小且不显著，第一年总体量价差主要由输家腿驱动，低量赢家相对优势从Year 2起更清楚。",
        "D03-C02: Work把12.49%放在Table VI语境；最终改为Table VII p27 p027-b005，Table VI只用于分腿长期路径。",
        "D03-C03: Work混合Table III/IV、value weighting与风险调整；最终分别定位Table III/IV、p015-b004与Table V p016-b002/p016-b003。",
        "D03-C04: microcap放大属于批判性教学推断，不是作者结论；最终改为WORK EXPLANATION。",
        "D03-C05: Turnover、W-L是教学重写，20日平均成交额是项目例子；最终分别标WORK EXPLANATION/PROJECT INFERENCE并补locator。",
    ],
}


SECTION_CLAIM_SOURCES = {
    "B05": "`p032-b003`, `p033-b002`",
    "A04": "`p003-b009`, `p003-b013`, `p004-b014`, `p033-b011`, `p033-b019`",
    "A03": "`p002-b001`, `p045-b002`, `p048-b001`",
    "E01": "`p003-b005`, `p009-b009`, `p015-b003`, `p024-b001`",
    "D03": "`p011-b004`, `p012-b002`, `p024-b004`, `p048-b004`, `p051-b003`",
}


def common_patch(text: str, pid: str) -> str:
    text = text.replace("|\\n|", "|\n|")
    text = text.replace("| source locator | 待Work复核点 |", "| source locator | Work复核结论 |")
    replacements = {
        "- [方法、公式或制度框架](#8-方法公式或制度框架)": "- [关键公式索引和解释](#8-关键公式索引和解释)",
        "## 8. 方法、公式或制度框架": "## 8. 关键公式索引和解释",
        "- [实证、图表或论证结果](#9-实证图表或论证结果)": "- [图表与实证结果索引](#9-图表与实证结果索引)",
        "## 9. 实证、图表或论证结果": "## 9. 图表与实证结果索引",
        "- [Work选择性翻译队列](#14-work选择性翻译队列)": "- [Work选择性翻译](#14-work选择性翻译)",
        "## 14. Work选择性翻译队列": "## 14. Work选择性翻译",
        "- [Mentor汇报提纲Draft](#16-mentor汇报提纲draft)": "- [Mentor汇报提纲](#16-mentor汇报提纲)",
        "## 16. Mentor汇报提纲Draft": "## 16. Mentor汇报提纲",
        "- [来源索引与提取问题](#17-来源索引与提取问题)": "- [完整来源索引](#17-完整来源索引)",
        "## 17. 来源索引与提取问题": "## 17. 完整来源索引",
        "### Work合并内容\n\n": "",
        "[UNRESOLVED] 核对本节关键数字、公式/图表及作者限定语。": "Work Review已完成；真实未解决项见§17。",
        "未通过核验的 OCR 公式不进入 Draft。": "未通过核验的OCR公式不进入最终Reader。",
        "[UNRESOLVED] Work 需对照原 PDF 逐式复核剩余复杂公式、参数定义和推导；未复核部分不视为已解决。": "[UNRESOLVED] Work未完成剩余复杂公式、参数定义和推导的逐式视觉核验；未复核部分不视为已解决。",
        "图形、列标题、脚注和数值须在 Work 中查看原 PDF。": "Work已复核主图表叙事；由于未生成可靠裁剪资产，完整列标题、脚注和精确数值仍须回到原PDF。",
        "文本候选，待 Work 核验": "核心公式已由Work复核；复杂OCR候选见§17",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"(?m)^### (\d+)\. (.+)$", r"### \2", text)
    text = re.sub(r"(?m)^#### \d+\.\d+ (.+)$", r"#### \1", text)
    text = text.replace("### 五分钟理解\n", "### Work精读解释\n")
    text = text.replace("### 五分钟理解：", "### Work精读解释：")
    source_line = (
        f"[AUTHOR CLAIM] 本节作者证据边界的主要定位：{SECTION_CLAIM_SOURCES[pid]}。"
    )
    for section in (10, 11):
        pattern = rf"(?m)^(## {section}\. .+)$"
        if source_line not in text:
            text, count = re.subn(pattern, rf"\1\n\n{source_line}", text, count=1)
            if count != 1:
                raise RuntimeError(f"{pid}: unable to add section {section} claim source")
        else:
            break
    if text.count(source_line) == 1:
        match = re.search(r"(?m)^## 11\. .+$", text)
        if match:
            text = text[: match.end()] + "\n\n" + source_line + text[match.end() :]
    return text


def patch_b05(text: str) -> str:
    text = text.replace(
        "作者汇集至少 316 个已提出因子，并把因子发现视为多重检验问题；传统 |t|>2 会低估错误发现风险。（PDF p.2–4；p002-b001，p003-b002，p004-b003）",
        "作者汇集至少316个已提出因子，并把因子发现视为多重检验问题；传统 $|t|>2$ 会低估错误发现风险。（PDF pp.1–4；`p001-b004`, `p002-b002`, `p003-b003`, `p004-b002`）",
    )
    text = text.replace(
        "作者比较 FWER 与 FDR 调整，并在相关检验模型下估计更高门槛；结论建议新因子的 t 统计量应超过 3.0，而不是机械沿用 2.0。（PDF p.29–33；p029-b003，p031-b002，p032-b002）",
        "作者比较FWER与FDR调整，并在相关检验模型下估计更高门槛；约3或更高是依赖错误控制目标、相关性和隐藏试验的经验数量级，不是固定常数。（PDF pp.29–33；`p029-b003`, `p031-b002`, `p032-b003`, `p033-b002`）",
    )
    text = text.replace(
        "3.0 也可能偏低，因为论文只能观察已发表或流通的因子，无法观察全部失败尝试。（PDF p.24，p.32；p024-b002，p032-b002）",
        "只按公开因子推导的门槛仍可能偏低，因为失败或未发表试验不可观察。（PDF p.24；`p024-b002`）",
    )
    replacements = {
        "| multiple testing | 多重检验 | 同一研究计划评估许多候选假设 | 候选越多，偶然显著越常见 | PDF p.3 `p003-b002` |":
            "| multiple testing | 多重检验 | 同一研究计划评估许多候选假设 | 候选越多，偶然显著越常见 | PDF p.7 `p007-b003` |",
        "| factor zoo | 因子动物园 | 文献中不断增长的收益预测因子集合 | 不能把项目里的每个公式当作独立发现 | PDF p.3 `p003-b002` |":
            "| factor zoo | 因子动物园 | 文献中不断增长的收益预测因子集合 | 不能把项目里的每个公式当作独立发现 | PDF p.32 `p032-b003` |",
        "| t-statistic hurdle | t统计量门槛 | 支持新发现所需的最低证据强度 | 不能把 2.0 当作自动通行证 | PDF p.3 `p003-b002` |":
            "| t-statistic hurdle | t统计量门槛 | 支持新发现所需的最低证据强度 | 不能把2.0当作自动通行证 | PDF p.32 `p032-b003` |",
        "| test dependence | 检验相关性 | 因子收益及其统计量并不独立 | 相邻窗口与等价公式会产生相关候选 | PDF p.3 `p003-b002` |":
            "| test dependence | 检验相关性 | 因子收益及其统计量并不独立 | 相邻窗口与等价公式会产生相关候选 | PDF p.25 `p025-b004` |",
        "| 搜索过程与因子清单 | 解释为什么已观察的 316 个因子仍低估真实试验总数。 |":
            "| 搜索过程与因子清单 | 解释为什么已观察的316个因子仍低估真实试验总数。 |",
        "| PDF p.3 | `p003-b002` |": "| PDF p.3 | `p003-b003` |",
        "- PDF p.2；source locator `p002-b001`": "- PDF p.1；source locator `p001-b004`",
        "- PDF p.32；source locator `p032-b002`": "- PDF pp.32–33；source locators `p032-b003`, `p033-b002`",
        "#### 摘要 — PDF p.1 `p001-b001`—2": "#### 摘要 — PDF pp.1–2；`p001-b004`, `p002-b002`",
        "#### Search process — PDF p.3 `p003-b001`—5": "#### Search process — PDF pp.3–5；`p003-b003`, `p004-b002`",
        "#### FWER与FDR — PDF p.9 `p009-b001`—13": "#### FWER与FDR — PDF pp.9–13；`p009-b002`, `p010-b004`, `p011-b004`",
        "#### Holm — PDF p.15 `p015-b001`": "#### Holm — PDF p.15；`p015-b002`, `p015-b003`",
        "#### 依赖问题 — PDF p.23 `p023-b001`—27": "#### 依赖问题 — PDF pp.24–27；`p024-b002`, `p025-b004`, `p026-b003`, `p027-b003`",
        "#### 结论 — PDF p.32 `p032-b001`—33": "#### 结论 — PDF pp.32–33；`p032-b003`, `p033-b002`",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    marker = "[AUTHOR CLAIM] 本节以多重检验和阈值框架为主。"
    note = (
        "[WORK EXPLANATION] Work中的$V/R$、FWER/FDR及调整程序公式是教学重记号，"
        "PDF原文在pp.10–18使用其自身记号；verification_status=partially_verified。"
    )
    text = text.replace(note + "\n\n" + note, note)
    if note not in text:
        text = text.replace(marker, note + "\n\n" + marker)
    return text


def patch_a04(text: str) -> str:
    replacements = {
        "当前 2017 NBER 稿复制 447 个异常变量，使用 NYSE breakpoints 和 value-weighted returns 作为共同程序。（PDF p.2–3、p.10–11；p002-b001，p003-b002，p010-b001，p011-b001）":
            "当前2017 NBER稿复制447个异常变量，并使用NYSE breakpoints和value-weighted returns等共同程序。（PDF pp.3, 10–11；`p003-b002`, `p010-b001`, `p011-b001`）",
        "286/447（64%）在 5% 水平不显著；若把门槛提高到 |t|≥3，380/447（85%）不显著。（PDF p.2、p.33；p002-b001，p033-b001）":
            "286/447（64%）在5%水平不显著；若要求$|t|\\ge3$，380/447（85%）不显著。（PDF pp.3, 33；`p003-b009`, `p003-b010`, `p003-b011`, `p033-b011`, `p033-b015`）",
        "交易摩擦类变量中 95/102（93%）不显著；对仍显著的 161 个异常，q-factor 模型使 115 个 alpha 不显著，150 个的 |t|<3。（PDF p.2、p.24–32；p002-b001，p024-b001，p032-b001）":
            "交易摩擦类变量中95/102（93%）不显著；对仍显著的161个异常，q-factor模型使115个alpha不显著，150个的$|t|<3$。（PDF pp.3–4, 24–33；`p003-b013`, `p004-b014`, `p004-b015`, `p033-b016`, `p033-b019`）",
        "| 摘要与研究动机 | 先核对 447、286、380、95/102、115 与 150。": "| 摘要与研究动机 | 先核对447、286、380、95/102、115与150。",
        "| PDF p.2 | `p002-b001` |": "| PDF p.3 | `p003-b009` |",
        "| 总结与报告建议 | 核对作者推荐的共同基准和适用边界。 | 沿作者原章节顺序识别定义、方法、证据与限定语。 | 核对作者推荐的共同基准和适用边界。 | 长证明、完整变量目录或重复稳健性表可先按阅读路线略读。 | PDF p.33 | `p033-b001` |":
            "| 总结与报告建议 | 核对作者推荐的共同基准和适用边界。 | 沿作者原章节顺序识别定义、方法、证据与限定语。 | 核对作者推荐的共同基准和适用边界。 | 长证明、完整变量目录或重复稳健性表可先按阅读路线略读。 | PDF p.33 | `p033-b011` |",
        "- PDF p.2；source locator `p002-b001`": "- PDF p.3；source locator `p003-b011`",
        "| Table 1 | PDF p.48 | p048-b001 | 六类 447 个异常的统一复制结果 |":
            "| Table 1 | PDF p.48 | `p048-b001` | 异象变量清单（List of Anomaly Variables） |",
        "| Table 2 | PDF p.57 | p057-b001 | 动量类异常 |":
            "| Table 2 | PDF p.57 | `p057-b001` | 市值加权/等权收益与选定变量统计 |",
        "| Table 3 | PDF p.58 | p058-b001 | 价值/投资等类别结果 |":
            "| Table 3 | PDF p.58 | `p058-b001` | 在5%水平未复制的异象 |",
        "| Table 4–6 | PDF p.60 | p060-b001 | 其他类别与 q-factor 检验 |":
            "| Table 4 | PDF p.60 | `p060-b001` | q-factor alpha |\\n| Table 5 | PDF p.62 | `p062-b001` | 因子载荷 |\\n| Table 6 | PDF p.64 | `p064-b001` | 46个q-anomalies的秩相关 |",
        "#### 总结 — PDF p.33 `p033-b001`": "#### 总结 — PDF p.33；`p033-b011`, `p033-b019`",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    marker = "[AUTHOR CLAIM] 本文的核心是统一复制协议"
    note = (
        "[WORK EXPLANATION] Work中的$H-L$、t统计量和q-factor回归是教学表达，"
        "并非PDF逐字符编号公式；verification_status=partially_verified。\n\n"
    )
    text = text.replace(note + note, note)
    if note.strip() not in text:
        text = text.replace(marker, note + marker)
    return text


def patch_a03(text: str) -> str:
    text = text.replace(
        "| break-even cost | 盈亏平衡成本 | 使净优势归零的最大成本 | 判断信号对成本误差的容忍度 | PDF p.6 `p006-b001` |",
        "| break-even cost（教学诊断） | 盈亏平衡成本 | [WORK EXPLANATION] 使简化净优势归零的成本敏感性诊断；不是论文原文术语或编号公式 | 判断信号对成本误差的容忍度 | 无论文方程；见本Reader §8 |",
    )
    text = text.replace(
        "- $c$：与有效价差或价格冲击有关的成本参数；",
        "- $c$：与Hasbrouck有效买卖价差有关的成本参数；论文明确指出该模型未覆盖price impact；",
    )
    text = text.replace(
        "#### Break-even cost直觉\n\n设策略gross超额收益",
        "#### Break-even cost直觉\n\n[WORK EXPLANATION] 以下是教学诊断式，非论文术语、编号公式或作者给出的PDF方程。\n\n设策略gross超额收益",
    )
    table_marker = "| Table 13 | PDF p.45 | p045-b003 | 不同规模组的 sS 策略毛/净收益 |"
    if table_marker in text and "| Figure 7 |" not in text:
        text = text.replace(
            table_marker,
            table_marker + "\n| Figure 7 | PDF p.47 | `p047-b001` | 不同规模组的gross与net Sharpe比较 |",
        )
    return text


def patch_e01(text: str) -> str:
    replacements = {
        "| Figure 2a/2b | PDF p.13 | p013-b005 | 不同正常收益模型下的累计异常收益 |":
            "| Figure 2a | PDF p.13 | `p013-b005` | 不同正常收益模型下的累计异常收益 |\\n| Figure 2b | PDF p.14 | `p014-b005` | 不同正常收益模型下的累计异常收益（续） |",
        "| Figure 3a/3b | PDF p.18 | p018-b006 | 事件研究检验功效 |":
            "| Figure 3a | PDF p.18 | `p018-b006` | 事件研究检验功效 |\\n| Figure 3b | PDF p.19 | `p019-b005` | 事件研究检验功效（续） |",
        "**PDF p.17 `p017-b001`—18；Table 2、Figure 3a/3b**":
            "**Table 2：PDF p.17 `p017-b002`；Figure 3a：p.18 `p018-b006`；Figure 3b：p.19 `p019-b005`**",
        "#### Clustering — PDF p.15 `p015-b001`": "#### Clustering — PDF p.15；`p015-b003`, `p015-b006`",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def patch_d03(text: str) -> str:
    replacements = {
        "低量赢家在第一年通常比高量赢家延续更久；":
            "第一年多数赢家cell的低量—高量差异较小且不显著；第一年总体动量在高量股更强，主要由输家腿驱动；低量赢家相对优势从Year 2起更清楚；",
        "低量赢家往往比高量赢家持续更久；":
            "低量赢家相对高量赢家的显著优势主要从Year 2起出现并延续；",
        "作者报告，在多数组合设定中：\n\n- 低量赢家优于高量赢家；\n- 示例差异约0.26%每月；\n- 结果主要对应组合形成后的第一年；":
            "作者报告的第一年结果具有赢家/输家不对称：\n\n- 多数赢家cell的低量—高量差异较小且不显著；\n- 示例0.26%每月只是一项组合差异，不能概括全部赢家cell；\n- 第一年的总体动量在高量股更强，主要由输家腿驱动；低量赢家的相对优势从Year 2起更清楚；",
        "**PDF p.15 `p015-b001`—17；Table III/IV**":
            "**Table III/IV为稳健性与特征结果；value-weighted说明见PDF p.15 `p015-b004`，风险调整见Table V p.16 `p016-b002`, `p016-b003`。**",
        "value weighting结果方向类似但通常更弱，提示microcaps和小股票可能放大结果。":
            "[WORK EXPLANATION] value weighting结果方向类似但通常更弱；“microcaps可能放大”是批判性教学推断，不是作者的直接因果结论。",
        "**PDF p.24 `p024-b001`—33；Table VI、Figure 1/2**":
            "**Table VI用于分腿长期路径；PDF p.24 `p024-b004`。Figure 1/2见p.29 `p029-b005`, `p029-b006`及p.30。**",
        "示例表中，简单动量策略第一年原始收益约12.49%，随后多年的收益转负。具体数字依赖组合口径，应以表格脚注为准。":
            "Table VII报告的简单动量策略第一年原始收益约12.49%（PDF p.27 `p027-b005`），随后多年收益转负；该数字不属于Table VI。",
        "在过去收益和成交量双排序中，低量赢家通常比高量赢家获得更高的后续收益。一个代表性差异约为每月0.26个百分点，但结果随形成期和持有期变化。":
            "双排序的第一年赢家腿差异多数较小且不显著；代表性的0.26个百分点不能概括所有cell。低量赢家相对高量赢家的显著优势主要从Year 2起出现，结果随形成期和持有期变化。",
        "作者样本中低量赢家通常延续更久，高量赢家较快反转。":
            "第一年赢家腿差异多不显著；低量赢家相对优势主要从Year 2起更清楚，高量赢家之后更快反转。",
        "作者发现低量赢家通常比高量赢家持续更久，输家侧则呈不同的不对称路径；":
            "作者发现成交量与赢家/输家路径存在不对称：第一年总体量价差主要由输家腿驱动，低量赢家相对优势从Year 2起更清楚；",
        "#### 摘要 — PDF p.2 `p002-b001`": "#### 摘要 — PDF p.2；`p002-b004`",
        "#### 样本方法 — PDF p.6 `p006-b001`—7": "#### 样本方法 — PDF pp.6–7；`p006-b004`, `p006-b005`, `p007-b002`",
        "#### Table II — PDF p.11 `p011-b001`—12": "#### Table II — PDF pp.11–12；`p011-b004`, `p012-b002`",
        "#### 长期反转 — PDF p.24 `p024-b001`—29": "#### 长期反转 — PDF pp.24–29；`p024-b004`, `p027-b005`, `p029-b005`, `p029-b006`",
        "#### MLC — PDF p.48 `p048-b001`—51": "#### MLC — PDF pp.48–51；`p048-b004`, `p048-b007`, `p051-b003`",
        "- [AUTHOR CLAIM] 长期收益回归的文本层候选；K与估计细节待Work复核。":
            "- [EXTRACTION LIMITATION] 长期收益回归为文本层候选；Work未完成K与符号的视觉逐式核验，保持partially_verified。",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.replace(
        "论文采用平均日换手率：",
        "[WORK EXPLANATION] 论文p.3 `p003-b003`把成交量定义为平均日换手率；下式是教学重排：",
    )
    text = text.replace(
        "当前项目曾使用20日平均成交额：",
        "[PROJECT INFERENCE] 当前项目曾使用20日平均成交额；它不是论文的volume定义：",
    )
    text = text.replace(
        "一个典型赢家减输家组合为：",
        "[WORK EXPLANATION] 下式$W-L$是教学记号，不是论文编号公式；相关组合见Table II，PDF pp.11–12 `p011-b004`, `p012-b002`：",
    )
    bh_marker = "[EXTRACTION LIMITATION] `formulas_index.csv` 是文本候选索引"
    bh_note = (
        "[EXTRACTION LIMITATION] BHAR公式在PDF p.29 `p029-b007`, `p029-b008`的文本提取已损坏，"
        "Work未可靠恢复，保持[UNRESOLVED]。\n\n"
    )
    text = text.replace(bh_note + bh_note, bh_note)
    if bh_note.strip() not in text:
        text = text.replace(bh_marker, bh_note + bh_marker)
    return text


PATCHERS = {
    "B05": patch_b05,
    "A04": patch_a04,
    "A03": patch_a03,
    "E01": patch_e01,
    "D03": patch_d03,
}


def main() -> None:
    module = load_merge_module()
    status = json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    for pid in ORDER:
        root = READERS / pid
        final = root / f"paper_reader_{pid}.md"
        report = root / f"paper_reader_{pid}_merge_report.md"
        manifest = root / f"paper_reader_{pid}_merge_manifest.json"
        expected = status["papers"][pid]["final_reader_sha256"]
        if module.sha256(final) != expected:
            raise RuntimeError(f"{pid}: final hash changed since initial merge; refusing repair")
        old_manifest = json.loads(manifest.read_text(encoding="utf-8"))
        inputs = {item["path"]: item["sha256"] for item in old_manifest["inputs"]}
        metadata = json.loads((root / "source/source_metadata.json").read_text(encoding="utf-8"))
        note_text = (root / f"analysis/work_review_notes_{pid}.md").read_text(encoding="utf-8")
        text = final.read_text(encoding="utf-8")
        text = common_patch(text, pid)
        text = PATCHERS[pid](text)
        qa = module.qa_final(pid, text, metadata)
        unresolved = module.unresolved_items(note_text)
        if pid == "D03":
            unresolved.extend(
                [
                    "R02的K与符号仍需视觉逐式核验。",
                    "BHAR公式提取损坏，尚未可靠恢复。",
                    "Figure 1/2的曲线、脚注与精确数值未逐项视觉核验。",
                    "fueling与diffusion的正式区别仍需回到原文细读。",
                ]
            )
        elif pid == "A03":
            unresolved.extend(["广义alpha完整数学证明未逐式完成。"])
        elif pid == "E01":
            unresolved.extend(["完整方差与检验统计量尚未逐式教学核验。"])
        elif pid == "B05":
            unresolved.extend(["附录相关/混合模型与复杂公式尚未逐式推导。"])
        elif pid == "A04":
            unresolved.extend(["与2020最终期刊版的逐项差异尚未核验。"])
        temp_final = root / f"paper_reader_{pid}.qa_repair.tmp.md"
        temp_report = root / f"paper_reader_{pid}_merge_report.qa_repair.tmp.md"
        temp_manifest = root / f"paper_reader_{pid}_merge_manifest.qa_repair.tmp.json"
        temp_final.write_text(text, encoding="utf-8", newline="\n")
        final_hash = module.sha256(temp_final)
        report_text = module.build_report(
            pid, metadata, inputs, final_hash, qa, unresolved, CONFLICTS[pid]
        )
        temp_report.write_text(report_text, encoding="utf-8", newline="\n")
        report_hash = module.sha256(temp_report)
        new_manifest = module.build_manifest(
            pid,
            metadata,
            inputs,
            final,
            final_hash,
            report,
            report_hash,
            qa,
            unresolved,
            CONFLICTS[pid],
            text,
        )
        temp_manifest.write_text(
            json.dumps(new_manifest, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        json.loads(temp_manifest.read_text(encoding="utf-8"))
        module.verify_inputs_unchanged(pid, inputs)
        temp_final.replace(final)
        temp_report.replace(report)
        temp_manifest.replace(manifest)
        status["papers"][pid].update(
            {
                "final_reader_sha256": module.sha256(final),
                "merge_report_sha256": module.sha256(report),
                "merge_manifest_sha256": module.sha256(manifest),
                "qa": "pass_after_pdf_authority_repairs",
                "conflict_count": len(CONFLICTS[pid]),
                "remaining_unresolved_count": qa["remaining_unresolved_count"],
            }
        )
    STATUS_PATH.write_text(
        json.dumps(status, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


if __name__ == "__main__":
    main()
