# 量化研究文献侦察：执行摘要

## 核心结论

当前项目最缺的不是更多公式，而是**更小的假设家族、更完整的试验日志、point-in-time 数据和真正不回看的 final test**。量价文献支持“成交量会改变收益信号的含义”，但不支持“放量必涨、缩量必跌”或任何庄家因果故事。自动因子发现论文说明搜索可以更有结构，却没有消除反复回测带来的多重检验。

## 网络与全文访问

- `web_research_blocked=false`
- 可用：网页搜索、OpenAlex 学术元数据、DOI/出版社摘要、arXiv、ACL Anthology、SSRN/NBER/作者或机构公开页。
- 未绕过付费墙，也未批量下载版权 PDF。
- 本地可完整读取：arXiv:2505.11122v3 *Navigating the Alpha Jungle* 的 31 页读者、TeX 源与图表。
- 其余未逐页完整审阅的论文保守标为 `full_text_status=abstract_only`。

## 实际检索来源与数量

- 12 个 OpenAlex 宽检索查询，读取 294 条返回记录，去重后 264 条。
- 经题名精确解析、DOI/稳定标识核验和相关性筛选，注册表保留 88 条。
- 核心清单：30 篇。
- 深度解析：13 篇。
- Idea backlog：9 条。

## 六个主题簇的主要认识

### A — 因子评价

RankIC/RankIR、分位单调性和 long-short spread 只回答“排序信息是否存在”；当前项目真正关心的 long-only 结果还受持仓集中、换手、成本和容量影响。文献复制研究显示，统一实现、value weighting 和成本会显著缩小异常集合。

### B — 过拟合

所有窗口、方向、阈值和手工改动共同构成试验家族。White Reality Check、PBO 和 DSR 可用于诊断，但都不能替代 untouched final test。REV60 是 MOM60 的符号变换，不应算新发现。

### C — 自动因子发现

GP、RL、MCTS 和 LLM 的共同价值是更有效地分配搜索预算和组织候选；共同风险是更快地产生更多选择。公平比较必须锁定同一数据、语法、候选数、参数尝试数和回测预算，并包含随机搜索。

对本地 LLM+MCTS 论文：

- 人类固定数据、算子、种子、奖励、门槛、预算和下游模型；
- AI 选择搜索分支、提出经济语义修改并生成公式；
- 奖励等权结合 RankIC、RankIR、换手、多样性和 LLM 过拟合风险评分；
- FSA 避免高频子树，但不能消除经济近重复；
- 三组参数择优、最大值回传、反复 OOS 观察和同 bar 时序仍有过拟合/执行风险。

### D — 量价

低量、高量、异常量和量价交互都可以数学化。文献中的机制至少包括信息到达、注意力、意见分歧、流动性和价格压力；不同机制对未来延续/反转给出相反预测。最有文献基础的主问题是“过去收益 × 标准化过去换手状态”，而不是固定 K 线故事。

### E — 主题与事件

主题成员常混合行业、风格和公司规模暴露。主题 breadth 必须使用历史成员，并控制市场/行业共同成分。事件研究需冻结首次公开时点、估计窗、事件窗和正常收益模型；商业航天事件目前仍应保持描述性。

### F — A 股约束

T+1、涨跌停、停牌、ST/退市、板块差异和有限卖空会同时改变信号形成、成交可行性和收益分布。今天的股票池或主题名单不能回填到过去；复权收益与当时真实成交限制必须分开处理。

## 最高优先级阅读

1. Shi, Duan & Li (2025), *Navigating the Alpha Jungle*
2. White (2000), *A Reality Check for Data Snooping*
3. Harvey, Liu & Zhu (2016), *… and the Cross-Section of Expected Returns*
4. Hou, Xue & Zhang (2020), *Replicating Anomalies*
5. Novy-Marx & Velikov (2016), *A Taxonomy of Anomalies and Their Trading Costs*
6. Lee & Swaminathan (2000), *Price Momentum and Trading Volume*
7. MacKinlay (1997), *Event Studies in Economics and Finance*
8. Hu, Pan & Wang (2021), *Chinese Capital Market: An Empirical Overview*

## Idea backlog 的证据等级

| status | 数量 | 含义 |
|---|---:|---|
| literature_supported_candidate | 2 | 文献直接支持构造或机制；A 股方向仍未验证 |
| exploratory_candidate | 2 | 方法与机制可检验，但没有直接市场证据 |
| concept_translation_only | 3 | 只是把脑图变成无歧义变量 |
| reject_due_to_evidence_or_data | 2 | 当前负面证据、数据或授权不满足 |

没有任何条目被称为 guaranteed alpha、likely profitable 或 recommended strategy。

## 尚不能回答

- REV60 能否在真正新样本保持方向；
- 八个量价形态在 A 股宽基究竟对应延续还是反转；
- 历史主题成员、自由流通股本和逐日交易限制是否完整；
- 56 只主题池的有效独立横截面样本量；
- LLM+MCTS 论文的同 bar 成交时序与完整预算公平；
- 自动搜索论文的强回测结果能否独立复现。

## 学生下一步

先读 C07、B01、B05，完成阅读计划中的三个问题；再读 A04/A03 理解复制与成本，最后读 D03、E01、F01。读完前不写新因子代码。若之后要研究量价，只选择一个连续交互、一个方向、一个持有期，在宽基 point-in-time sandbox 预注册；主题池只做冻结规格的转移检查。

## 文件导航

- `00_scope_and_status.md`：边界、网络门和证据规则
- `01_search_queries.md`：检索词、结果计数和来源
- `02_literature_registry.csv`：88 条注册记录与 30 篇核心解析合同
- `03_core_papers_shortlist.md`：核心清单
- `04_deep_reading_notes.md`：13 篇深读
- `05_methodology_matrix.csv`：10 种方法对照
- `06_volume_price_translation.md`：八类量价概念数学化
- `07_idea_backlog.csv`：9 条可追溯 idea
- `08_student_reading_plan.md`：三层阅读计划
- `09_evidence_gaps_and_next_questions.md`：缺口与停止条件
