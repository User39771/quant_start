# 深度解析（13 篇）

说明：除 C07 外，本次多数论文只核验了正式摘要、元数据和可公开定位的关键内容，故注册表标记为 `abstract_only`。以下严格区分作者主张、Codex 推断和项目借鉴。

## A01 — Fama & French (1992): The Cross-Section of Expected Stock Returns

**研究问题。** 市场 beta、规模、账面市值比等特征，哪些能够解释美国股票平均收益的横截面差异？

**作者明确报告。** 在其样本和检验框架下，规模与账面市值比能够概括相当部分横截面收益差异，而单独的市场 beta 未呈现预期的解释力。

**负面与限制。** 论文不包含现代意义上的训练、验证、最终测试隔离，也不处理今天因子搜索面对的多重检验；本次没有获得可合法使用的全文，细节结论仍需回到正式版本逐项核验。

**Codex 推断。** 该文最适合作为“预测关系不等于可交易策略”的基础读物；它不能直接支持在 56 只主题股中加入某个价值或规模暴露。

**项目可借鉴。** 把横截面排序、回归解释力与成本后多头组合绩效分开记录，并在中国样本中明确市值、账面值和可交易性字段的时点口径。

## A05 — Gu, Kelly & Xiu (2020): Empirical Asset Pricing via Machine Learning

**研究问题。** 非线性和高维机器学习能否改善美国股票横截面收益的样本外预测？

**作者明确报告。** 论文使用长时间、大横截面的美国股票特征，采用按时间推进的训练、验证和测试设计；树模型与神经网络捕捉非线性和交互后，样本外预测与组合表现优于若干线性基线。

**Codex 推断。** 论文的正面结果依赖“数十年 × 数千股票”的样本规模、严格的时间分割和强正则化。当前 56 只主题池无法提供相同的自由度；把同类模型直接移植到主题池，会让模型容量远超有效样本。

**项目可借鉴。** 先把复杂模型放在独立宽基 sandbox；主题池只保留预注册的少数、可解释交互。验证集只用于模型选择，最终测试一旦开启不得回看调参。

## B01 — White (2000): A Reality Check for Data Snooping

**研究问题。** 当研究者在同一数据上比较许多模型，如何检验“最优模型”是否真的优于基准？

**作者明确报告。** Reality Check 以候选模型相对基准的损失差为对象，用 bootstrap 检验“整个搜索家族中不存在优于基准的模型”这一复合原假设。

**负面与限制。** 加入大量明显差的候选会降低检验功效；未记录的人工试验不会自动进入校正。

**Codex 推断。** 项目的 `factor_experiment_log` 不是行政日志，而是统计量的组成部分。MOM40/60/80、正负方向、所有阈值和失败尝试都属于同一搜索家族。

**项目可借鉴。** 在任何新回测前冻结候选家族和基准；没有完整 trial ledger 时，不计算“校正后显著性”的漂亮数字。

## B03 — Bailey et al. (2017): The Probability of Backtest Overfitting

**研究问题。** 被样本内选为冠军的策略，在样本外落到中位数以下的概率有多大？

**作者明确报告。** CSCV 对时间块做组合对称划分，反复比较样本内冠军在对应样本外的相对排名，汇总为 PBO。

**负面与限制。** 它需要明确的策略收益矩阵和足够长度；对依赖性很强、生成过程不断适应历史结果的公式，试验家族如何定义并不自动解决。

**Codex 推断。** PBO 是搜索过程诊断，不是单个因子的“过拟合分”。如果只保存最后十个好因子，PBO 会低估研究者自由度。

**项目可借鉴。** 当前先建立候选矩阵和失败记录；Phase B 仍必须保留真正未触碰的最终样本，不能用 CSCV 替代。

## B04 — Bailey & López de Prado (2014): The Deflated Sharpe Ratio

**研究问题。** 一个看起来很高的 Sharpe，在考虑样本长度、偏度、峰度和试验次数后是否仍异常？

**作者明确报告。** DSR 结合 Probabilistic Sharpe Ratio 与多重选择调整，把“研究者看过多个策略后留下最佳者”纳入显著性判断。

**负面与限制。** 有效试验数及试验间相关性难以估计；若输入收益本身有成交、前视或幸存偏差，DSR 无法修复。

**Codex 推断。** 主题池样本小、收益非正态、涨跌停和停牌造成离散分布，原始 Sharpe 的不确定性会更大。

**项目可借鉴。** DSR 可作为未来二级审计指标；优先级低于 point-in-time 数据、成本合同和独立 final test。

## B05 — Harvey, Liu & Zhu (2016): … and the Cross-Section of Expected Returns

**研究问题。** 因子发现数量巨大时，传统 `t > 1.96` 是否仍是合理门槛？

**作者明确报告。** 作者整理大量已发表因子，提出多重检验框架，并认为新因子需要显著高于传统门槛的统计证据，文中给出约 `t > 3` 的经验性要求。

**负面与限制。** 未发表试验数量不可见；因子间相关性使“独立试验数”不确定。

**Codex 推断。** 当前项目的本地多重性与学术因子动物园叠加。把 MOM60 改成 REV60 不增加独立信息，只是同一排序的符号变换。

**项目可借鉴。** 证据等级应依据预注册、样本外、成本和稳定性共同决定，不能只靠单个 t 值。

## C03 — Yu et al. (2023): Generating Synergistic Formulaic Alpha Collections via Reinforcement Learning

**研究问题。** 自动搜索能否直接优化“因子集合的协同”，而非逐个追逐高 IC 因子？

**作者明确报告。** 论文将公式生成表述为强化学习问题，并以集合层面的预测效果/相关性为目标，报告在 CSI 300/500 上相对基线的改善。

**负面与限制。** 集合的历史 RankIC 改善不等于长期净收益；搜索过程中反复评价候选仍会产生选择偏差。

**Codex 推断。** 这篇论文支持保存“加入后边际贡献”和“与 Zoo 的最大相关性”，但不支持立即上 RL。

**项目可借鉴。** 在 Phase A 的统一合同中先增加候选规范化、相关性和失败原因字段；等人工迭代成为真实瓶颈再讨论搜索器。

## C04 — Ren et al. (2024): RiskMiner

**研究问题。** 风险偏好的 MCTS 是否能利用离散公式树结构，并优化因子集合？

**作者明确报告。** 论文把公式挖掘构造成 reward-dense MDP，使用 risk-seeking MCTS，报告在两个股票数据集和多个指标上优于当时基线。

**负面与限制。** 摘要未提供失败结果、完整预算公平或独立 final test 细节。

**Codex 推断。** risk-seeking 的“追逐尾部最好结果”与量化搜索中的赢家诅咒方向一致；若没有家族级校正，反而可能放大过拟合。

**项目可借鉴。** 若未来授权 MCTS，必须与同等候选数的随机搜索、普通 GP 和贪心搜索比较；报告每单位回测预算的有效候选数。

## C07 — Shi, Duan & Li (2025): Navigating the Alpha Jungle

**全文状态。** 本地 31 页论文、TeX 源和图表已审阅，版本为 arXiv:2505.11122v3。

### 人类预先固定了什么

- 股票市场与数据字段：OHLC、VWAP、成交量等。
- 算子库、公式语法和回测器。
- 初始 seed/root genes。
- 搜索预算、UCT 参数、温度与最多三组参数试验。
- 五维奖励：Effectiveness、Stability、Turnover、Diversity、Overfitting Risk。
- 有效 Alpha 门槛与 Zoo 选择规则。
- LightGBM/MLP 下游组合模型及评价指标。

### AI 自动完成了什么

- MCTS 用 UCT 在既有公式节点间分配扩展预算。
- 依据当前公式最弱评价维度选择 refinement 方向。
- LLM 先写 alpha portrait/经济直觉，再生成合法公式与参数。
- 回测结果回传树；FSA 根据 Alpha Zoo 中的高频子树要求 LLM 回避重复结构。

### 搜索奖励

作者把 RankIC、RankIR、日换手率、与 Zoo 最大相关性、LLM 对过拟合风险的定性评分映射为五个 0–10 分维度并等权平均。树的回传使用观察到的最大子节点分数，而非均值。

### 如何避免重复公式

FSA 抽象公式语法树，统计 Zoo 中高频子树，并在后续提示词中禁止这些结构。它减少结构同质化，但不能保证经济含义不重复；不同语法仍可能产生高度相关的暴露。

### 训练与测试隔离

论文设置历史 IS/OOS 区间，并报告不同搜索代数的 OOS RankIC、下游模型和回测结果。但搜索、三组参数择优和方法消融反复使用训练段；如果研究者观察 OOS 曲线后调整框架，名义 OOS 会逐渐成为验证集。

### 作者明确报告

- MCTS、多维反馈和 FSA 的消融方向大体支持增量作用。
- 最完整方法在多项预测与交易指标上优于所列基线，但不是每个单项都第一。
- 随搜索深度增加，IS 与 OOS RankIC 上升，同时 IS–OOS 差距扩大。
- 作者承认新颖性/复杂度仍不及人类专家，搜索空间受 LLM 内部知识限制，大规模搜索成本高。

### 额外过拟合与实现风险

1. 每个公式最多三组参数择优，增加隐含试验数。
2. 最大值回传会让偶然高分分支长期占优。
3. LLM 自评的“过拟合风险”不是统计校正。
4. 摘要和主文没有充分证明所有基线获得相同回测预算。
5. 使用当日字段并写按收盘价成交，若未至少滞后一日，可能存在同 bar 前视/执行偏差。
6. A 股涨跌停、停牌、T+1、容量与真实冲击成本没有达到当前项目的实现合同。

### 项目结论

先借鉴 Alpha Zoo、候选 canonicalization、搜索日志、预算公平和多维评价；不借鉴自动搜索执行本身。当前 `MCTS_status=not_authorized` 保持不变。

## D03 — Lee & Swaminathan (2000): Price Momentum and Trading Volume

**研究问题。** 过去换手率能否区分不同的动量生命周期？

**作者明确报告。** 高/低过去换手股票具有不同特征和未来收益；成交量预测动量幅度与持续性，高量 winners/losers 的长期反转更快。

**负面与限制。** 月频美国证据不等同于 A 股中频阈值；长期反转可能受微盘、权重和退市处理影响。

**Codex 推断。** 论文不支持“放量必涨”或“缩量必跌”，而支持 `past_return × normalized_turnover` 的条件性问题。

**项目可借鉴。** 只允许一个预注册交互方向与窗口；宽基 sandbox 先检验，再决定主题池是否只做复现。

## D05 — Llorente et al. (2002): Dynamic Volume-Return Relation

**研究问题。** 成交量能否帮助区分信息交易造成的延续与流动性交易造成的反转？

**作者明确报告。** 论文模型和实证表明，个股的动态量价关系随信息不对称与流动性交易而变化。

**Codex 推断。** 同一个“放量”观测无法识别 informed trading、attention、disagreement 或 price pressure；机制需要额外代理变量或互斥预测。

**项目可借鉴。** 每个量价 idea 同时写出 continuation 与 reversal 的 falsification；禁止用庄家叙事解释任何结果。

## E01 — MacKinlay (1997): Event Studies in Economics and Finance

**研究问题。** 如何用证券价格衡量事件对企业价值的影响？

**作者明确报告。** 标准流程包括事件定义、样本选择、估计窗、正常收益模型、异常收益、跨证券/时间聚合和统计推断；同时讨论检验力、非参数方法和设计问题。

**负面与限制。** 事件聚集、事件时点不确定、事件诱导方差和正常收益模型错误都会破坏推断。

**Codex 推断。** 商业航天政策或发射事件常同时影响整个主题/行业，56 只股票的残差高度相关；简单平均 CAR 的标准误可能过小。

**项目可借鉴。** 当前案例维持 descriptive；若未来推断，需预注册事件源、时点、估计窗、市场+行业模型和 clustered inference。

## F01 — Hu, Pan & Wang (2021): Chinese Capital Market: An Empirical Overview

**研究问题。** 中国资本市场的制度、参与者和资产价格事实与成熟市场有何不同？

**作者明确报告。** 综述中国市场的快速发展、所有制与投资者结构、制度变化、交易特征及相关资产定价事实。

**Codex 推断。** “A 股”不是固定制度：板块规则、涨跌停幅度、ST/退市和互联互通会随日期变化。任何长期面板都必须把规则版本化。

**项目可借鉴。** 数据字典至少包含交易状态、ST、上市/退市、板块、当日价格限制、复权口径和历史成分。

## 深读共同结论

1. 初始变量应来自可区分的机制，不来自无约束公式组合。
2. 评价必须同时看横截面预测、分位单调性、long-only 可实现性、换手、成本和稳定性。
3. 自动搜索的公平比较单位是“总候选回测数/总预算”，不是最终挑出的公式数。
4. 搜索方法不会自动解决多重检验；搜索越高效，越需要独立 final test。
5. 对当前 56 只主题池，最重要的下一步是读懂并冻结研究合同，而不是扩大模型容量。

<!-- FULLTEXT_BATCH_BEGIN -->
## 2026-07-25 source-only extraction additions

The earlier abstract-level notes are preserved. This batch adds PDF provenance, complete page text, section/source maps, research-contract scaffolds, and Work queues. It does not promote new translated claims.

| ID | Added full-text material | Claim revision |
|---|---|---|
| C07 | Existing native Nature Reader artifacts revalidated | No change; existing C07 notes retained |
| B01 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| B05 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| A04 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| A03 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| D03 | No PDF; user_pdf_required | No abstract-level conclusion promoted; Work review pending |
| E01 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| F01 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| A01 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| A02 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| A05 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| B03 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| B04 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| C03 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| C04 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| C06 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| D05 | No PDF; retrieval_error | No abstract-level conclusion promoted; Work review pending |
| E03 | No PDF; user_pdf_required | No abstract-level conclusion promoted; Work review pending |
| B02 | No PDF; user_pdf_required | No abstract-level conclusion promoted; Work review pending |
| B06 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| C01 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| C02 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| C05 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| D01 | No PDF; user_pdf_required | No abstract-level conclusion promoted; Work review pending |
| D02 | No PDF; retrieval_error | No abstract-level conclusion promoted; Work review pending |
| D04 | No PDF; user_pdf_required | No abstract-level conclusion promoted; Work review pending |
| D06 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| E02 | Source-only reader and evidence anchors | No abstract-level conclusion promoted; Work review pending |
| F02 | No PDF; user_pdf_required | No abstract-level conclusion promoted; Work review pending |
| F03 | No PDF; user_pdf_required | No abstract-level conclusion promoted; Work review pending |
<!-- FULLTEXT_BATCH_END -->
