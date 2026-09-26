from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
PAPERS_ROOT = ROOT / "docs/literature_reconnaissance/papers"
READERS_ROOT = PAPERS_ROOT / "readers"


PAPERS = [
    {
        "id": "B05",
        "title": "… and the Cross-Section of Expected Returns",
        "authors": "Campbell R. Harvey；Yan Liu；Heqing Zhu",
        "year": "2016",
        "venue": "Review of Financial Studies 29(1)",
        "identifier": "DOI: 10.1093/rfs/hhv059",
        "version": "Published journal layout（目标正式期刊论文）",
        "pages": "64",
        "question": "在研究者已经检验大量候选因子的环境里，传统的 |t|>2 门槛是否仍足以支持“新因子有效”？",
        "five": [
            "作者汇集至少 316 个已提出因子，并把因子发现视为多重检验问题；传统 |t|>2 会低估错误发现风险。（PDF p.2–4；p002-b001，p003-b002，p004-b003）",
            "作者比较 FWER 与 FDR 调整，并在相关检验模型下估计更高门槛；结论建议新因子的 t 统计量应超过 3.0，而不是机械沿用 2.0。（PDF p.29–33；p029-b003，p031-b002，p032-b002）",
            "3.0 也可能偏低，因为论文只能观察已发表或流通的因子，无法观察全部失败尝试。（PDF p.24，p.32；p024-b002，p032-b002）",
        ],
        "why": "当前 MOM60、REV60 及未来 MCTS 候选都属于同一研究项目内的试验家族。本文要求把“看过多少设定”纳入解释，而不是只报告最后留下的一个 t 值。",
        "route": [
            ("必须精读", "PDF p.2–4、p.9–16、p.23–24、p.29–33", "因子清单、复合检验、FWER/FDR、隐藏试验、阈值与结论"),
            ("可以略读", "PDF p.18–22、p.25–28", "图形描述、相关结构与模型设定"),
            ("暂时跳过", "PDF p.34–64", "长附录和完整因子目录；复核具体因子时再查"),
        ],
        "terms": [
            ("multiple testing", "多重检验", "同时检验许多因子时，偶然显著的概率累积", "MOM60/REV60/搜索树中的全部候选共同构成试验家族"),
            ("factor zoo", "因子动物园", "文献中不断增长的收益预测因子集合", "不能把项目里的每个公式当作独立发现"),
            ("family-wise error rate", "族错误率", "至少一个假阳性的概率", "对强结论采用保守门槛"),
            ("false discovery rate", "错误发现率", "被拒绝假设中假阳性的期望比例", "对候选发现集合进行整体控制"),
            ("Bonferroni", "邦费罗尼校正", "用检验数量调整单项显著性", "试验越多，单个候选门槛越高"),
            ("Holm", "Holm逐步校正", "按排序后的 p 值控制 FWER", "审计全部候选而非只看最优项"),
            ("BHY", "BHY程序", "在依赖结构下控制 FDR", "候选公式高度相关时仍需多重检验控制"),
            ("hidden tests", "隐藏试验", "未发表、未登记或未报告的尝试", "临时阈值、窗口和方向都应进入 experiment registry"),
            ("t-statistic hurdle", "t统计量门槛", "支持新发现所需的最低证据强度", "不能把 2.0 当作自动通行证"),
            ("test dependence", "检验相关性", "因子收益及其统计量并不独立", "相邻窗口与等价公式会产生相关候选"),
        ],
        "sections": [
            ("搜索过程与因子清单", 3, "p003-b002", "解释为什么已观察的 316 个因子仍低估真实试验总数。"),
            ("多重检验框架", 5, "p005-b001", "把单因子检验改写为一组相互关联的假设。"),
            ("FWER、FDR 与调整程序", 10, "p010-b002", "比较不同错误控制目标及其门槛。"),
            ("相关性、隐藏试验与结构模型", 23, "p023-b002", "说明相关检验和不可见尝试如何改变阈值。"),
            ("实证阈值与结论", 29, "p029-b003", "核对 t>3.0、t=3.9 等结果的适用条件。"),
        ],
        "formulas": [
            ("多重检验原假设族", "PDF p.6–10；formulas_index.csv", "逐式解释 FWER/FDR 定义与拒绝规则。"),
            ("相关检验结构模型", "PDF p.26–31；formulas_index.csv", "核对 M、ρ、真实因子比例及阈值之间的关系。"),
        ],
        "visuals": [
            ("Figure 1", 18, "p018-b004", "多重检验门槛随因子数量变化"),
            ("Figure 2", 19, "p019-b002", "因子与发表数量的时间分布"),
            ("Figure 3", 21, "p021-b002", "调整后 t 统计门槛的时间路径"),
            ("Table 5", 30, "p030-b002", "相关检验结构模型的估计与阈值"),
        ],
        "proved": [
            "在作者收集的因子文献和设定下，传统 |t|>2 无法维持通常理解的错误率。",
            "不同的 FWER/FDR 目标与因子相关结构会给出不同但普遍高于 2 的证据门槛。",
            "未观察到的失败试验会使仅基于已发表因子数量的门槛偏低。",
        ],
        "not_proved": [
            "没有证明所有已发表因子都是假的，也没有给每个因子作最终真假判决。",
            "没有证明 t>3 的因子一定可交易、样本外有效或扣除成本后盈利。",
            "没有在当前 A 股主题池检验 MOM60、REV60 或任何 MCTS 公式。",
        ],
        "limitations": [
            "因子清单无法包含全部私人、失败或未发表试验，真实搜索规模不可见。",
            "阈值依赖错误控制目标、相关结构和模型假设，不是跨情境常数。",
            "经济理论可改变先验可信度，但论文没有给出可机械套用的“理论折扣”。",
        ],
        "project": [
            ("Phase A", "把所有窗口、方向、过滤器和交互项纳入统一试验族与审计日志。"),
            ("historical_seen / final test", "本文启发的阈值和规则都属于 historical_seen；final test 必须保持未触碰。"),
            ("MOM60 / REV60", "负向 orientation 也是一次研究选择；不得只报告留下的 REV60。"),
            ("Phase B", "只有预先冻结候选、指标和停止规则后才能进入 prospective 验证。"),
            ("MCTS / experiment registry", "记录搜索预算、重复公式、失败候选和选择路径；不能只对最终节点计算 p 值。"),
        ],
        "translations": [
            "PDF p.2–4：摘要、因子清单与隐藏试验的论证。",
            "PDF p.9–16：FWER/FDR及 Bonferroni、Holm、BHY 的选择性解释。",
            "PDF p.29–33：Table 5、阈值结果和结论中的限定语。",
        ],
        "mentor": "先说明为什么 |t|>2 在大量搜索后失效；再区分 FWER 与 FDR；最后把全部研究选择登记到当前项目，而不是声称 Reality Check 或多重检验已经在项目中完成。",
    },
    {
        "id": "A04",
        "title": "Replicating Anomalies",
        "authors": "Kewei Hou；Chen Xue；Lu Zhang",
        "year": "2020（当前 PDF 为 2017 NBER working paper）",
        "venue": "目标版本：Review of Financial Studies；当前版本：NBER Working Paper 23394",
        "identifier": "DOI: 10.1093/rfs/hhy131；NBER w23394",
        "version": "Working paper（正式期刊版之前的版本；不得视为最终期刊排版）",
        "pages": "130",
        "question": "用统一且更可实现的组合构造重新检验已发表异常后，有多少仍达到常规或更高的显著性门槛？",
        "five": [
            "当前 2017 NBER 稿复制 447 个异常变量，使用 NYSE breakpoints 和 value-weighted returns 作为共同程序。（PDF p.2–3、p.10–11；p002-b001，p003-b002，p010-b001，p011-b001）",
            "286/447（64%）在 5% 水平不显著；若把门槛提高到 |t|≥3，380/447（85%）不显著。（PDF p.2、p.33；p002-b001，p033-b001）",
            "交易摩擦类变量中 95/102（93%）不显著；对仍显著的 161 个异常，q-factor 模型使 115 个 alpha 不显著，150 个的 |t|<3。（PDF p.2、p.24–32；p002-b001，p024-b001，p032-b001）",
        ],
        "why": "它把“复制成功”落实到统一断点、权重和显著性门槛，直接约束当前项目如何比较 MOM60、REV60 与后续候选，而不是挑选最有利的组合构造。",
        "route": [
            ("必须精读", "PDF p.2–5、p.10–24、p.33–35", "447 个异常、共同程序、失败分类、q-factor 与总结"),
            ("可以略读", "PDF p.48–78", "Table 1–6 的完整结果；按问题查表"),
            ("暂时跳过", "PDF p.79–130", "信号定义与长附录；准备复现特定异常时再读"),
        ],
        "terms": [
            ("replication", "复制检验", "在统一程序下重建已发表异常", "用同一 Phase A 合同比较全部候选"),
            ("NYSE breakpoints", "NYSE断点", "用 NYSE 股票确定组合分位点", "避免微盘股数量支配分组"),
            ("value-weighted return", "市值加权收益", "按市值聚合组合收益", "与等权结果并列，辨认微盘驱动"),
            ("equal-weighted return", "等权收益", "每只股票权重相同", "小股票对主题池统计可能过强"),
            ("microcap", "微盘股", "数量多但总市值占比很低的股票", "容量、涨跌停和成本约束更强"),
            ("anomaly variable", "异常变量", "文献提出的横截面预测特征", "MOM60/REV60 是候选信号，不是已验证异常"),
            ("replication rate", "复制率", "按预设判据仍显著的比例", "必须提前固定成功标准"),
            ("q-factor model", "q因子模型", "用于解释异常收益的资产定价模型", "作为基准思想，不直接移植为 A 股结论"),
            ("alpha", "异常收益截距", "相对因子基准未解释的平均收益", "需要同时报告估计值、误差和成本"),
            ("t-statistic", "t统计量", "估计值相对标准误的比例", "不能脱离多重检验单独解释"),
        ],
        "sections": [
            ("摘要与研究动机", 2, "p002-b001", "先核对 447、286、380、95/102、115 与 150。"),
            ("复制设计与共同程序", 10, "p010-b001", "理解 NYSE 断点、市值加权及微盘股影响。"),
            ("未复制异常的分类", 13, "p013-b001", "区分显著性失败与经济含义。"),
            ("q-factor 解释检验", 24, "p024-b001", "只对复制成功的异常进一步检验 alpha。"),
            ("总结与报告建议", 33, "p033-b001", "核对作者推荐的共同基准和适用边界。"),
        ],
        "formulas": [
            ("异常组合与 t 统计量", "PDF p.10–24；formulas_index.csv", "核对分组、持有期重叠和标准误。"),
            ("q-factor 回归 alpha", "PDF p.24–32；formulas_index.csv", "核对因变量、基准因子和显著性判据。"),
            ("附录信号定义", "PDF p.79–130；formulas_index.csv", "只在复现指定变量时逐式核验。"),
        ],
        "visuals": [
            ("Table 1", 48, "p048-b001", "六类 447 个异常的统一复制结果"),
            ("Table 2", 57, "p057-b001", "动量类异常"),
            ("Table 3", 58, "p058-b001", "价值/投资等类别结果"),
            ("Table 4–6", 60, "p060-b001", "其他类别与 q-factor 检验"),
        ],
        "proved": [
            "在当前 working-paper 版本规定的统一构造下，多数已发表异常没有达到其复制标准。",
            "使用更高 |t| 门槛时，失败比例进一步上升。",
            "微盘股、断点和权重选择会显著影响异常是否看起来可复制。",
        ],
        "not_proved": [
            "没有证明 447 个异常在所有市场、版本和构造下都无效。",
            "没有证明 q-factor 是唯一正确的定价模型。",
            "没有验证当前 A 股主题池的 MOM60、REV60 或任何未来公式。",
        ],
        "limitations": [
            "当前 PDF 是 2017 NBER 稿；目标 2020 期刊版的样本、变量数量或表述可能有修订。",
            "复制结论依赖作者选定的共同程序；替代构造不是自动错误，但必须同时报告共同基准。",
            "美国微盘股与 A 股小市值股票在交易制度、停牌和涨跌停方面不同。",
        ],
        "project": [
            ("Phase A", "固定断点、权重、持有期、标准误和成功判据，所有候选使用同一合同。"),
            ("historical_seen / final test", "读完本文后采用的构造已被研究者看见，应登记为 historical_seen。"),
            ("MOM60 / REV60", "同时报告等权/市值加权、微盘敏感性和方向选择，不挑最有利结果。"),
            ("Phase B", "只把冻结后的少量候选带入 prospective 阶段。"),
            ("MCTS / experiment registry", "搜索出的每个可执行公式都要按同一复制合同评估并保留失败记录。"),
        ],
        "translations": [
            "PDF p.2–5：关键比例与研究动机。",
            "PDF p.10–13：共同程序、NYSE breakpoints 和 value weighting。",
            "PDF p.33–35：总结、微盘股解释及作者的报告建议。",
        ],
        "mentor": "先交代当前使用的是 2017 working paper；再说明统一程序为何改变复制率；最后强调“不复制”是相对于特定判据，而不是宣布所有异常永远无效。",
    },
    {
        "id": "A03",
        "title": "A Taxonomy of Anomalies and Their Trading Costs",
        "authors": "Robert Novy-Marx；Mihail Velikov",
        "year": "2016（当前 PDF 为 2014 NBER working paper）",
        "venue": "目标版本：Review of Financial Studies；当前版本：NBER Working Paper 20721",
        "identifier": "DOI: 10.1093/rfs/hhv063；NBER w20721",
        "version": "Working paper（正式期刊版之前的版本）",
        "pages": "61",
        "question": "常见异常在计入交易成本后还剩多少净表现，简单的降成本规则能否保留信号暴露？",
        "five": [
            "论文统一研究 23 个策略，按换手分层并估计毛收益、交易成本和净收益；交易成本在所有案例中都会降低盈利性及显著性。（PDF p.2–5、p.17–23；p002-b001，p005-b001，p017-b001）",
            "单边月换手低于 50% 的多数异常在成本缓解后仍有显著净价差；高换手策略很少能做到。（PDF p.2、p.5、p.45；p002-b001，p005-b001，p045-b001）",
            "三种简单方法中，buy/hold spread（sS 不行动区间）通常是最有效的单一方法；极高换手策略可能需要组合方法。（PDF p.24–39；p024-b001，p031-b001，p035-b001）",
        ],
        "why": "当前项目已把换手和成本列入 Phase A 合同。本文帮助学生理解：信号的毛统计量与可实现净表现是两个问题，减少换手也会改变暴露。",
        "route": [
            ("必须精读", "PDF p.2–8、p.11–16、p.17–24、p.29–39、p.45", "成本模型、净表现指标、23个策略、三类缓解法与结论"),
            ("可以略读", "PDF p.25–28、p.40–44", "低成本股票池、边际交易和规模分层"),
            ("暂时跳过", "PDF p.48–61", "信号定义、稳健性表和参考文献"),
        ],
        "terms": [
            ("gross return", "毛收益", "扣除交易成本前的策略收益", "Phase A 先保留毛预测力"),
            ("net return", "净收益", "扣除估计交易成本后的收益", "不能把毛收益写成可交易结果"),
            ("one-sided turnover", "单边换手", "一侧组合每期更换的比例", "MOM60/REV60 调仓造成的实际交易量"),
            ("effective spread", "有效价差", "基于成交与报价信息的成本代理", "A 股需另建符合制度的数据口径"),
            ("price impact", "价格冲击", "交易规模对成交价格的影响", "56只主题池容量有限时尤其重要"),
            ("buy/hold spread", "买入/持有区间", "进入阈值比继续持有阈值更严格", "用滞回减少边界附近反复调仓"),
            ("trading hysteresis", "交易滞回", "信号反转一小段时不立即换仓", "减少 REV60 排名抖动换手"),
            ("staggered rebalancing", "错峰再平衡", "只在部分日期更新一部分组合", "降低月度全量换仓"),
            ("generalized alpha", "广义alpha", "摩擦下衡量资产改善投资机会集的指标", "需 Work 核对公式和解释"),
            ("break-even cost", "盈亏平衡成本", "使净优势归零的最大成本", "判断信号对成本误差的容忍度"),
        ],
        "sections": [
            ("成本模型", 6, "p006-b001", "理解有效价差估计及其未覆盖的价格冲击。"),
            ("表现评价与广义 alpha", 11, "p011-b001", "区分毛 alpha、净 alpha 与机会集改善。"),
            ("23 个简单策略", 17, "p017-b001", "按低、中、高换手比较毛/净结果。"),
            ("三种成本缓解", 24, "p024-b001", "低成本股票池、错峰再平衡、buy/hold spread。"),
            ("规模分层与结论", 41, "p041-b001", "微盘驱动、净表现和外推边界。"),
        ],
        "formulas": [
            ("交易成本回归", "PDF p.7；p007-b002", "原索引式 `∆Pt = c∆Qt + βm rmt + εt`；字体与上下标需 Work 对照 PDF。"),
            ("广义 alpha / MVE 分解", "PDF p.15–16；p015-b004–p016-b005", "必须在 Work 中逐式核对符号与经济含义。"),
            ("信号定义附录", "PDF p.49–52；formulas_index.csv", "仅在复现具体异常时核验。"),
        ],
        "visuals": [
            ("Figure 1", 8, "p008-b001", "不同市值排名的中位有效价差"),
            ("Figure 3", 15, "p015-b001", "SMB、HML、UMD 成本的时间变化"),
            ("Figure 5", 32, "p032-b001", "sS momentum 随不行动区间变化"),
            ("Table 3", 20, "p020-b002", "23 个策略的市值加权毛/净结果"),
            ("Table 5", 26, "p026-b001", "三类缓解后的 momentum 净表现"),
            ("Table 13", 45, "p045-b003", "不同规模组的 sS 策略毛/净收益"),
        ],
        "proved": [
            "在作者的美国股票样本、成本模型和 23 个策略中，成本显著压低异常的净收益与显著性。",
            "换手是区分成本后存活概率的重要维度，50% 单边月换手是本文分类中的关键界线。",
            "buy/hold spread 通常是最有效的单一简单缓解方法，但并非对所有高换手策略都足够。",
        ],
        "not_proved": [
            "没有证明成本模型包含所有价格冲击、融资约束和卖空成本。",
            "没有证明 sS 规则在 A 股或当前主题池具有最优阈值。",
            "没有证明降低换手后保留的统计显著性等于可部署 Alpha。",
        ],
        "limitations": [
            "当前 PDF 为 2014 working paper，与 2016 期刊版可能存在表述或数值差异。",
            "直接成本估计不完整覆盖价格冲击，净结果依赖投资者规模。",
            "卖空、T+1、涨跌停、停牌与 A 股容量约束不同。",
        ],
        "project": [
            ("Phase A", "并列报告毛收益、换手、成本假设、净收益和成本敏感性。"),
            ("historical_seen / final test", "成本缓解规则一经从本文选择就进入 historical_seen。"),
            ("MOM60 / REV60", "可把滞回作为预注册候选，但它改变策略，不是免费优化。"),
            ("Phase B", "冻结成本模型和调仓规则后才检验 prospective 净表现。"),
            ("MCTS / experiment registry", "奖励函数若包含净收益，必须固定成本假设并记录所有阈值尝试。"),
        ],
        "translations": [
            "PDF p.2–5：毛表现、成本与 50% 换手界线。",
            "PDF p.11–16：广义 alpha 的公式与直觉。",
            "PDF p.24、p.29–39：三种成本缓解及 sS 规则。",
        ],
        "mentor": "把文章讲成“毛异常—换手—成本—净表现—缓解规则”的链条；明确当前是 working paper，且 A 股成本结构必须重新估计。",
    },
    {
        "id": "E01",
        "title": "Event Studies in Economics and Finance",
        "authors": "A. Craig MacKinlay",
        "year": "1997",
        "venue": "Journal of Economic Literature 35(1), pp. 13–39",
        "identifier": "JSTOR stable identifier: 2729691",
        "version": "Published journal layout（大学托管副本；目标正式论文）",
        "pages": "30",
        "question": "如何用证券价格在短窗口内衡量一个明确事件对公司价值的影响，并进行聚合与统计推断？",
        "five": [
            "事件研究先定义事件与事件窗，再用事件未发生时的正常收益模型计算异常收益；估计窗通常位于事件窗之前且不包含事件期。（PDF p.2–3；p002-b001，p003-b005）",
            "核心量是 AR=实际收益−正常收益，随后在时间和事件样本间聚合为 CAR 并检验。（PDF p.3、p.7–12；p003-b005，p007-b008，p009-b009，p012-b008）",
            "方法有效性依赖事件日期、正常收益模型、事件聚集、横截面依赖、检验功效和混杂事件；事件图本身不是因果识别。（PDF p.15–24；p015-b001，p021-b001，p022-b001，p024-b001）",
        ],
        "why": "当前商业航天事件工作只能在明确日期、对照收益和混杂事件规则下解释。本文提供描述性事件研究的最低合同，而不是给主题上涨赋予单一因果原因。",
        "route": [
            ("必须精读", "PDF p.1–3、p.5–12、p.15–24", "流程、正常收益、AR/CAR、功效、非参数检验、横截面模型和其他问题"),
            ("可以略读", "PDF p.4、p.13–14", "600个盈利公告示例及图形"),
            ("暂时跳过", "PDF p.26–30", "参考文献与链接页"),
        ],
        "terms": [
            ("event date", "事件日", "事件信息首次可被市场观察的日期", "公告日需按发布时间映射到交易日"),
            ("event window", "事件窗", "观察事件附近收益的区间", "例如 [-1,+1]，须事前固定"),
            ("estimation window", "估计窗", "估计正常收益参数且不含事件期的样本", "放在事件窗之前避免污染"),
            ("normal return", "正常收益", "没有事件条件下的期望收益", "市场模型给出反事实基准"),
            ("abnormal return", "异常收益", "实际收益减正常收益", "个股或主题对基准的当日偏离"),
            ("CAR", "累计异常收益", "事件窗内异常收益之和", "报告多个预注册窗口而非挑最好窗口"),
            ("market model", "市场模型", "个股收益与市场收益的稳定线性关系", "需要合适的 A 股宽基基准"),
            ("confounding event", "混杂事件", "同窗内可能影响价格的其他信息", "商业航天公告与业绩/政策新闻重叠"),
            ("test power", "检验功效", "真实效应存在时拒绝原假设的能力", "事件少或噪声高时不能把不显著当无效"),
            ("cross-sectional dependence", "横截面相关", "多个事件收益共享市场或行业冲击", "主题成分股同日反应不能视为独立样本"),
        ],
        "sections": [
            ("事件研究流程", 2, "p002-b001", "事件定义、样本选择、事件窗、估计窗与诊断。"),
            ("正常收益模型", 5, "p005-b004", "常数均值模型、市场模型及模型选择。"),
            ("AR、CAR 与聚合推断", 7, "p007-b008", "从单个事件到样本总体的统计量。"),
            ("功效、非参数与横截面模型", 16, "p016-b001", "理解小样本、分布假设和特征解释。"),
            ("其他问题与结论", 22, "p022-b001", "事件聚集、非同步交易、长窗口与边界。"),
        ],
        "formulas": [
            ("异常收益", "PDF p.3；p003-b005", "`AR_it = R_it - E(R_it | X_t)`；Work 核对原式下标。"),
            ("市场模型", "PDF p.6；p006-b003", "`R_it = α_i + β_i R_mt + ε_it`；参数由估计窗获得。"),
            ("累计异常收益", "PDF p.9；p009-b009", "`CAR_i(τ1,τ2) = Σ AR_iτ`；聚合方差需按论文假设计算。"),
        ],
        "visuals": [
            ("Figure 1", 8, "p008-b004", "估计窗与事件窗时间线"),
            ("Table 1", 10, "p010-b002", "盈利公告示例的 AR/CAR"),
            ("Figure 2a/2b", 13, "p013-b005", "不同正常收益模型下的累计异常收益"),
            ("Figure 3a/3b", 18, "p018-b006", "事件研究检验功效"),
            ("Figure 4", 22, "p022-b005", "不同采样间隔下的功效"),
        ],
        "proved": [
            "论文给出一套可审计的事件研究流程，并推导在明确假设下的 AR、CAR 与检验统计量。",
            "正常收益模型降低噪声的程度影响检测事件效应的能力。",
            "事件窗、事件聚集和样本依赖结构是推断的一部分，不是绘图后的附注。",
        ],
        "not_proved": [
            "没有证明观察到 CAR 就由该事件单独造成。",
            "没有证明长窗口事件研究自动可靠，或市场始终即时且完全理性。",
            "没有证明当前商业航天事件在 A 股产生可交易 Alpha。",
        ],
        "limitations": [
            "经典推断依赖正态、独立或稳定参数等假设；实际数据可能违背。",
            "事件日期不确定、事件重叠和横截面依赖会扭曲显著性。",
            "短窗反应适合测量市场重估，不等同于长期基本面因果效应。",
        ],
        "project": [
            ("Phase A", "为事件模块冻结事件定义、基准、估计窗、事件窗和排除规则。"),
            ("historical_seen / final test", "已看过的事件窗口与公告都属于 historical_seen。"),
            ("MOM60 / REV60", "事件 CAR 与横截面因子收益是不同研究对象，不混为一个 Alpha 证据。"),
            ("Phase B", "只有预注册新事件和时间戳规则才能形成 prospective 检验。"),
            ("MCTS / experiment registry", "不得让搜索算法事后挑事件窗；所有窗口必须进入试验登记。"),
        ],
        "translations": [
            "PDF p.2–3：完整事件研究流程。",
            "PDF p.5–12：正常收益、AR/CAR 与聚合推断。",
            "PDF p.20–24：非参数、横截面模型、事件聚集和结论边界。",
        ],
        "mentor": "用“事件—估计窗—正常收益—AR—CAR—推断—混杂”七步讲清楚，并明确主题图不是因果结论。",
    },
    {
        "id": "D03",
        "title": "Price Momentum and Trading Volume",
        "authors": "Charles M. C. Lee；Bhaskaran Swaminathan",
        "year": "2000",
        "venue": "The Journal of Finance 55(5)",
        "identifier": "DOI: 10.1111/0022-1082.00280；JSTOR stable 222483",
        "version": "Final journal version（用户提供；PDF p.1 为 JSTOR 书目信息页）",
        "pages": "54",
        "question": "过去换手率能否区分价格动量的强度、持续期和长期反转，并揭示不同的动量生命周期？",
        "five": [
            "样本为 1965–1995 年 NYSE/AMEX 股票，以过去收益和平均日换手率双排序；作者另用 Nasdaq-NMS holdout 样本复核。（PDF p.6–7；p006-b001，p006-b005，p007-b001）",
            "低成交量股票一般优于高成交量股票；成交量与动量的关系具有赢家/输家不对称性，不能简单概括为“放量给动量加油”。（PDF p.2、p.11–28、p.50；p002-b001，p011-b004，p050-b001）",
            "作者提出 Momentum Life Cycle 作为整合证据的解释框架，同时明确它是组合层面的倾向、并非个股确定路径。（PDF p.48–51；p048-b004，p049-b001，p050-b001）",
        ],
        "why": "它是把价格方向与成交量状态组合成可检验交互的直接文献。对 REV60 的启发只能登记为新假设，不能把美国历史结果写成 A 股已验证信号。",
        "route": [
            ("必须精读", "PDF p.2–16、p.27–34、p.40–50", "样本、双排序、短中长期结果、信息含量、MLC 与结论"),
            ("可以略读", "PDF p.17–26、p.35–47", "完整表格、盈利与估值特征、变化量检验"),
            ("暂时跳过", "PDF p.51–54", "补充说明、行业表与参考文献"),
        ],
        "terms": [
            ("turnover ratio", "换手率", "成交股数相对流通股数的尺度化交易量", "A 股需使用时点可得流通股本"),
            ("price momentum", "价格动量", "按过去收益排序后的延续现象", "MOM60 只是当前项目的一个窗口版本"),
            ("double sort", "双重排序", "同时按过去收益与成交量分组", "预注册 return×volume 交互"),
            ("holding period", "持有期", "形成组合后观察收益的期限", "短期延续和长期反转需分开"),
            ("holdout sample", "留出样本", "用 Nasdaq-NMS 做额外复核", "不等同于当前项目未触碰 final test"),
            ("volume effect", "成交量效应", "低换手组合相对高换手组合的收益差异", "不能解释成单纯流动性溢价"),
            ("momentum life cycle", "动量生命周期", "用成交量定位受追捧/被忽视阶段的框架", "只能作为候选机制"),
            ("value/glamour", "价值/成长型", "低量/高量股票呈现的估值特征差异", "需控制规模、估值和行业"),
            ("earnings surprise", "盈利意外", "实际盈利相对预期的偏离", "检验成交量是否含基本面预期信息"),
            ("long-run reversal", "长期反转", "形成后多年收益方向逆转", "与 REV60 的 60 日定义不可直接等同"),
        ],
        "sections": [
            ("相关文献与假设", 4, "p004-b001", "区分 fueling、diffusion 与作者后续证据。"),
            ("样本与方法", 6, "p006-b001", "1965–1995、NYSE/AMEX、换手率与 holdout 样本。"),
            ("量价双排序结果", 7, "p007-b001", "短期动量、赢家/输家不对称与稳健性。"),
            ("长期路径与信息含量", 27, "p027-b002", "持有多年后的延续/反转、估值和盈利特征。"),
            ("MLC 与结论", 48, "p048-b004", "框架、组合层面限制和未解释现象。"),
        ],
        "formulas": [
            ("四因子回归", "PDF p.16；p016-b003", "`(r_i-r_f)=α_i+β_i(r_m-r_f)+s_i SMB+h_i HML+ε_i`；OCR 下标待 Work 核对。"),
            ("BHAR", "PDF p.29；p029-b008", "formulas_index 的乘积符号提取不完整，必须对照 PDF。"),
            ("长期收益回归", "PDF p.31；p031-b003", "`r_{t+K,i}=α_K+b_K r_{t,i}+u_{t+K,i}`；Work 核对 K 与估计方式。"),
        ],
        "visuals": [
            ("Table I", 8, "p008-b003", "基础价格动量策略"),
            ("Table II", 11, "p011-b004", "价格动量×过去成交量双排序"),
            ("Figure 1/2", 29, "p029-b005", "行业/规模调整的长期买入持有收益"),
            ("Table IX", 34, "p034-b004", "盈利、估值与关注特征"),
            ("Figure 4", 48, "p048-b004", "Momentum Life Cycle 概念图"),
        ],
        "proved": [
            "在作者样本和组合构造中，过去换手率包含与未来横截面收益及动量路径相关的信息。",
            "成交量与动量的关系对赢家和输家并不对称，简单 fueling 或 diffusion 解释不足。",
            "低量/高量组合在估值、分析师关注和未来经营表现上呈系统差异。",
        ],
        "not_proved": [
            "没有证明 MLC 是个股必然经过的确定周期；作者明确称其为组合层面的倾向。",
            "没有证明成交量只是流动性或能单独识别投资者情绪因果机制。",
            "没有证明 A 股 REV60、低量或放量突破已经有效。",
        ],
        "limitations": [
            "MLC 是解释性框架，不能解释第一年成交量效应的不对称，也缺少完整理论模型。",
            "结果来自 1965–1995 年美国股票；市场结构、投资者和交易制度与 A 股不同。",
            "长期结果与微盘、权重、行业和风险调整相关，交易成本不是论文中心。",
        ],
        "project": [
            ("Phase A", "把收益窗口、成交量窗口、分组顺序、权重和持有期写入统一合同。"),
            ("historical_seen / final test", "从本文产生的 return×volume 候选立即登记为 historical_seen。"),
            ("MOM60 / REV60", "成交量条件会定义新因子，不是对原 REV60 的事后解释。"),
            ("Phase B", "只允许冻结一个小规模交互候选集后做 prospective 验证。"),
            ("MCTS / experiment registry", "成交量变换、窗口、方向和交互都计入搜索预算并保留失败项。"),
        ],
        "translations": [
            "PDF p.2、p.6–12：研究设计和关键短期结果。",
            "PDF p.27–34：长期收益与信息含量。",
            "PDF p.48–50：MLC、作者限定语与结论。",
        ],
        "mentor": "强调成交量不是一个万能确认信号；讲清双排序、不对称结果与 MLC 的组合层面限制，再说明迁移到 A 股必须形成新注册假设。",
    },
]


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


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def table(rows: list[tuple[str, ...]], headers: tuple[str, ...]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines.extend("| " + " | ".join(str(cell).replace("|", "\\|") for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def bullets(items: list[str], label: str) -> str:
    return "\n\n".join(f"- [{label}] {item}" for item in items)


def build_reader(paper: dict[str, object], metadata: dict[str, object]) -> str:
    pid = str(paper["id"])
    source_sha = str(metadata["sha256"])
    toc = [
        "文献身份与版本", "五分钟理解", "为什么现在阅读", "推荐阅读路线", "研究问题与直觉",
        "核心术语", "逐节导读", "关键公式索引和解释占位", "图表与实证结果索引",
        "作者证明了什么", "作者没有证明什么", "局限与批判", "与当前量化项目的对应",
        "待 Work 补充的关键翻译", "自测问题", "Mentor 汇报提纲", "完整来源索引",
    ]
    anchors = [
        "1-文献身份与版本", "2-五分钟理解", "3-为什么现在阅读", "4-推荐阅读路线", "5-研究问题与直觉",
        "6-核心术语", "7-逐节导读", "8-关键公式索引和解释占位", "9-图表与实证结果索引",
        "10-作者证明了什么", "11-作者没有证明什么", "12-局限与批判", "13-与当前量化项目的对应",
        "14-待-work-补充的关键翻译", "15-自测问题", "16-mentor-汇报提纲", "17-完整来源索引",
    ]
    return f"""# {paper['title']}：统一学生 Reader Draft

```text
paper_id={pid}
reader_version=draft-1.0
reader_type=student_learning_reader_draft
source_pdf_sha256={source_sha}
nature_reader_backend_preserved=true
full_text_translation=false
selective_translation_status=pending_work_review
reader_draft_status=complete
work_review_status=pending
reader_merge_status=not_started
student_reading_status=pending
student_understood=false
final_merge_waiting_for_work_review=true
```

证据标签：

- `[AUTHOR CLAIM]`：原 PDF 直接支持的作者主张或实证结果。
- `[WORK EXPLANATION]`：等待 Work 人工补充的教学解释；本 Draft 不伪造该内容。
- `[PROJECT INFERENCE]`：把论文方法映射到当前项目的推断。
- `[EXTRACTION LIMITATION]`：PDF、公式、图表或 OCR 提取限制。
- `[UNRESOLVED]`：需要 Work 对照原 PDF 才能完成的数学或教学问题。

## 阅读目录

{chr(10).join(f'- [{name}](#{anchor})' for name, anchor in zip(toc, anchors))}

## 1. 文献身份与版本

{table([
    ('paper_id', pid),
    ('标题', str(paper['title'])),
    ('作者', str(paper['authors'])),
    ('年份', str(paper['year'])),
    ('期刊/工作论文', str(paper['venue'])),
    ('DOI或稳定标识', str(paper['identifier'])),
    ('当前版本', str(paper['version'])),
    ('PDF页数', str(paper['pages'])),
    ('PDF SHA-256', source_sha),
    ('审计后端', 'source map、章节、公式、图、表索引均存在；原审计包未修改'),
], ('字段', '值'))}

## 2. 五分钟理解

{bullets(list(paper['five']), 'AUTHOR CLAIM')}

- [WORK EXPLANATION] [UNRESOLVED] Work 应把上述证据改写为初学者可复述的中文直觉，并逐项核对限定语；本 Draft 不把占位内容冒充人工复核。

## 3. 为什么现在阅读

- [PROJECT INFERENCE] {paper['why']}
- [PROJECT INFERENCE] 本文只提供研究约束与候选机制，不构成 `REV60 validated`、`Alpha confirmed`、`OOS passed`，也不表示相关方法已经在当前项目实施。

## 4. 推荐阅读路线

{table(list(paper['route']), ('层级', 'PDF页码', '阅读目标'))}

## 5. 研究问题与直觉

- [AUTHOR CLAIM] **研究问题：** {paper['question']}
- [WORK EXPLANATION] [UNRESOLVED] 请 Work 用一个不依赖公式的例子解释作者为何采用该识别或评价设计，并指出例子不能代替证据。

## 6. 核心术语

{table(list(paper['terms']), ('English', '中文', '论文中的含义', '当前项目中的例子'))}

## 7. 逐节导读

{table([(name, f'PDF p.{page}', locator, aim) for name, page, locator, aim in paper['sections']], ('章节', '页码', 'source-map locator', '阅读任务'))}

[EXTRACTION LIMITATION] `section_index.csv` 含页眉、脚注或表格文本误识别为章节的条目；上表仅列经正文结构核对的主线，完整原生索引仍保留。

## 8. 关键公式索引和解释占位

{table(list(paper['formulas']), ('公式/对象', 'PDF页码与定位', '当前解释状态'))}

[EXTRACTION LIMITATION] `formulas_index.csv` 为文本候选索引，字体、上下标、求和与乘积符号可能残缺。

[UNRESOLVED] Work 必须对照对应 PDF 页逐式核对；在此之前不得把 OCR 字符串当作权威公式，也不得声称数学附录已完成教学核验。

## 9. 图表与实证结果索引

{table([(name, f'PDF p.{page}', locator, note) for name, page, locator, note in paper['visuals']], ('图/表', 'PDF页码', 'source-map locator', '阅读重点'))}

[EXTRACTION LIMITATION] 审计包只保留检测到的图表标题和 locator，未生成可靠裁剪资产；图形、列标题、脚注和数值须在 Work 中查看原 PDF。

## 10. 作者证明了什么

{bullets(list(paper['proved']), 'AUTHOR CLAIM')}

## 11. 作者没有证明什么

{bullets(list(paper['not_proved']), 'AUTHOR CLAIM')}

## 12. 局限与批判

{bullets(list(paper['limitations']), 'AUTHOR CLAIM')}

- [PROJECT INFERENCE] 迁移到 A 股还需重新处理 point-in-time 股票池、退市与生存者偏差、停牌、ST、涨跌停、复权、流动性、容量和交易成本。
- [EXTRACTION LIMITATION] Nature Reader 后端未生成全文翻译；本文件只列选择性翻译任务。

## 13. 与当前量化项目的对应

{table([(area, f'[PROJECT INFERENCE] {mapping}') for area, mapping in paper['project']], ('项目部分', '对应关系'))}

## 14. 待 Work 补充的关键翻译

selective_translation_status=pending_work_review

{bullets(list(paper['translations']), 'UNRESOLVED')}

只允许选择性翻译难段、公式和图表说明；不得生成或粘贴全文中文翻译。

## 15. 自测问题

1. 不看原句，用自己的话说明论文的研究对象、识别设计和最关键的证据边界。
2. 哪一个结果最依赖样本、版本、权重、基准或成本假设？为什么？
3. 选择一项图表，解释它支持什么、不能支持什么，并给出 PDF 页码。
4. 如果迁移到 A 股，哪三项制度或数据差异最可能改变结果？
5. 如何把本文启发登记为 `historical_seen`，同时保护独立 `final test`？

[WORK EXPLANATION] [UNRESOLVED] Work 应为上述问题补充答案要点，但保留开放推理空间，不能写成背诵稿。

## 16. Mentor 汇报提纲

- [WORK EXPLANATION] [UNRESOLVED] {paper['mentor']}
- [PROJECT INFERENCE] 汇报结尾必须区分作者证据、项目推断和仍待验证事项。

## 17. 完整来源索引

{table([
    ('原 PDF', str(metadata['source_pdf_path']), f"SHA-256: {source_sha}"),
    ('身份元数据', 'source/source_metadata.json', '标题、作者、年份、版本、页数与 hash'),
    ('hash 记录', 'source/sha256.txt', source_sha),
    ('全文提取', 'extracted/paper_original.md', '仅作定位，不在本 Reader 全量复制'),
    ('source map', 'extracted/source_map.csv', 'PDF 页码与 block locator'),
    ('章节索引', 'extracted/section_index.csv', '原生审计输出'),
    ('公式索引', 'extracted/formulas_index.csv', '文本候选，待 Work 核验'),
    ('图索引', 'extracted/figures_index.csv', '标题与页码'),
    ('表索引', 'extracted/tables_index.csv', '标题与页码'),
    ('提取问题', 'extracted/extraction_issues.md', '不得隐藏'),
    ('研究合同', 'analysis/research_contract.md', '审计后端'),
    ('证据图', 'analysis/evidence_map.md', '审计后端'),
    ('限制图', 'analysis/limitations_map.md', '审计后端'),
    ('项目映射', 'analysis/project_relevance.md', '项目层面推断'),
    ('阅读路线', 'analysis/reading_outline.md', '审计后端'),
    ('翻译队列', 'analysis/translation_queue.md', '选择性翻译任务'),
    ('交接说明', 'analysis/work_handoff.md', 'Work 入口'),
], ('来源', '路径', '用途'))}

---

reader_content_rebuilt=false  
nature_reader_backend_modified=false  
final_reader_generated=false  
final_merge_waiting_for_work_review=true
"""


def build_request(paper: dict[str, object], metadata: dict[str, object]) -> str:
    pid = str(paper["id"])
    return f"""# {pid} Work Review Request

paper_id={pid}  
source_pdf_sha256={metadata['sha256']}  
draft_status=complete  
work_review_status=pending  
final_merge_waiting_for_work_review=true

## 复核目标

请以原 PDF 为事实权威，在不修改 Draft、原 PDF 或 Nature Reader 审计包的前提下，生成：

`analysis/work_review_notes_{pid}.md`

## 必读输入

- `paper_reader_{pid}_draft.md`
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

原 PDF 本地路径（不在 ZIP 中）：`{metadata['source_pdf_path']}`

## 本文专属复核任务

{bullets(list(paper['translations']), 'WORK TASK')}

- [WORK TASK] 对照 PDF 核对 Draft 中的关键数值、样本、页码、图表标题和作者限定语。
- [WORK TASK] 给关键公式补充中文直觉；OCR 不可靠处保留 `[UNRESOLVED]`。
- [WORK TASK] 补充选择性翻译、常见误读、自测答案要点和 Mentor 汇报提纲。
- [WORK TASK] 明确区分 `[AUTHOR CLAIM]`、`[WORK EXPLANATION]`、`[PROJECT INFERENCE]`、`[EXTRACTION LIMITATION]`、`[UNRESOLVED]`。

## 边界

- 不生成全文翻译，不调用外部翻译 API。
- 不把项目推断写成作者结论，不把论文结果写成 A 股已验证 Alpha。
- 不修改 `full_text_reviewed`、`student_understood` 或最终合并状态。
- 完成 Notes 后，另按 `reader_merge_contract_v1.md` 合并；本交接不生成最终 Reader。
"""


def verify_and_build() -> None:
    for paper in PAPERS:
        pid = str(paper["id"])
        reader_root = READERS_ROOT / pid
        missing = [item for item in REQUIRED if not (reader_root / item).is_file()]
        if missing:
            raise RuntimeError(f"{pid}: missing inputs: {missing}")
        metadata = json.loads((reader_root / "source/source_metadata.json").read_text(encoding="utf-8"))
        if metadata["paper_id"] != pid or metadata["title"] != paper["title"]:
            raise RuntimeError(f"{pid}: metadata identity mismatch")
        pdf = ROOT / metadata["source_pdf_path"]
        if not pdf.is_file():
            raise RuntimeError(f"{pid}: source PDF missing: {pdf}")
        actual_sha = sha256(pdf)
        if actual_sha != metadata["sha256"]:
            raise RuntimeError(f"{pid}: PDF hash mismatch")
        if len(PdfReader(str(pdf)).pages) != metadata["page_count"]:
            raise RuntimeError(f"{pid}: PDF page-count mismatch")
        if (reader_root / f"paper_reader_{pid}_draft.md").exists():
            raise RuntimeError(f"{pid}: draft already exists; refusing overwrite")
        if (reader_root / f"analysis/work_review_request_{pid}.md").exists():
            raise RuntimeError(f"{pid}: work request already exists; refusing overwrite")
        (reader_root / f"paper_reader_{pid}_draft.md").write_text(
            build_reader(paper, metadata), encoding="utf-8", newline="\n"
        )
        (reader_root / f"analysis/work_review_request_{pid}.md").write_text(
            build_request(paper, metadata), encoding="utf-8", newline="\n"
        )


if __name__ == "__main__":
    verify_and_build()
