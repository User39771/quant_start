# 量化研究文献侦察：范围与状态

生成日期：2026-07-25（Asia/Shanghai）

## 结论先行

- `web_research_blocked=false`：网页检索、学术元数据接口、开放摘要与部分开放全文均可访问。
- 本次通过 12 个 OpenAlex 查询取得 264 条去重候选元数据，再按项目相关性、来源等级和可核验性缩减为 88 条注册记录。
- 核心清单 30 篇；深读 13 篇。只有本地 `output/paper_reader_2505.11122v3/paper.md` 对应的 LLM+MCTS 论文按完整文本审阅；其余未完整逐页读取者均标为 `abstract_only`。
- 本任务只建立知识库与 idea backlog。未实施信号、未运行回测、未选择“最佳因子”、未开启 Phase B 或 MCTS。

## 项目边界

研究对象是大学生 A 股中频研究，现有主题池约 56 只，主题为 AI 与商业航天。当前历史证据包括：

- MOM60 的正向方向未获支持；REV60 只是符号翻转，尚无新样本验证。
- LOWVOL20 降低风险，同时降低收益。
- 20 日平均成交额中位数过滤未获支持。
- Theme Breadth60 核心结果未获支持，LOWVOL 交互为 mixed。
- 商业航天事件研究保留为描述性案例。
- Phase A 已有统一评价合同；Phase B prospective 验证、MCTS 和自动公式搜索均未授权。

这些既有结论只用于限定文献问题，不在本任务中重估或改写。

## 六个主题簇

| Cluster | 任务角色 | 本次关键问题 |
|---|---|---|
| A | 因子评价基础 | RankIC/RankIR、分位组合、单调性、衰减、换手、成本、long-only 与 long-short 的差异 |
| B | 过拟合与研究偏差 | data snooping、多重检验、PBO、DSR、样本选择、prospective final test、实验注册 |
| C | 自动因子发现 | GP、symbolic regression、RL、MCTS、LLM、去重、搜索预算、公平基线 |
| D | 量价与微观结构 | 信息到达、注意力、意见分歧、流动性压力、延续与反转的条件性 |
| E | 主题与事件 | 主题暴露、行业污染、事件时点、异常收益、相关事件与 regime dependence |
| F | A 股约束 | T+1、涨跌停、停牌、ST/退市、复权、流动性容量、历史成分与主题成员 |

## 证据使用规则

1. Tier 1 的正式期刊、会议和原始方法论文优先。
2. Tier 2 的 arXiv/SSRN 只支持“论文报告了什么”，不等同于已独立复现。
3. Tier 3 用于术语、制度和实现背景。
4. 量价脑图属于 Tier 4，仅作为构造种子；“庄家吸筹、洗盘、控盘”不作为机制证据。
5. `author claim` 表示作者明确报告；`Codex inference` 表示依据方法做出的审慎推断；`project use` 表示当前项目可借鉴的研究动作。

## 全文访问状态

| 文献/来源 | 状态 | 用法 |
|---|---|---|
| Shi, Duan & Li, *Navigating the Alpha Jungle*, arXiv:2505.11122v3 | `full_text_local` | 31 页本地读者、TeX 源文件和图表均已纳入深读 |
| ACL Anthology、arXiv、作者/机构公开页 | 页面或 PDF 可定位，但本次未逐页完整审阅 | 注册表仍保守标 `abstract_only` |
| OUP/Wiley/Elsevier/ACM 等出版页 | 元数据与正式摘要可访问；部分全文受限 | 只提炼摘要支持的主张，需深读处明确留缺口 |
| 项目 annual-report PDF 缓存 | 可读取但与方法侦察无关 | 未纳入，避免把公司年报误当方法证据 |

## 停止门

知识库完成后停止。后续任何 idea 若进入研究，必须另行授权并先完成预注册；本目录中的候选不构成交易建议或已经验证的 Alpha。
