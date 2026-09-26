# 核心论文清单（30 篇）

完整解析合同见 `02_literature_registry.csv`。本文件说明为什么入选、阅读层级和主要用途。

## Cluster A — 因子评价基础（5）

| paper_id | 论文 | 层级 | 入选理由 |
|---|---|---|---|
| A01 | Fama & French (1992), *The Cross-Section of Expected Stock Returns* | Guided/Deep | 理解横截面回归、特征与收益关系的基础 |
| A02 | Jegadeesh & Titman (1993), *Returns to Buying Winners and Selling Losers* | Guided | MOM60/REV60 必须对照的原始中期动量证据 |
| A03 | Novy-Marx & Velikov (2016), *A Taxonomy of Anomalies and Their Trading Costs* | Must | 把统计信号、换手和可实现净收益分开 |
| A04 | Hou, Xue & Zhang (2020), *Replicating Anomalies* | Must | 统一口径复制、value weighting 与更高检验门槛 |
| A05 | Gu, Kelly & Xiu (2020), *Empirical Asset Pricing via Machine Learning* | Guided/Deep | 展示复杂模型为何需要大样本、时间切分和验证集 |

## Cluster B — 过拟合与研究偏差（6）

| paper_id | 论文 | 层级 | 入选理由 |
|---|---|---|---|
| B01 | White (2000), *A Reality Check for Data Snooping* | Must/Deep | 将“所有尝试过的模型”纳入共同推断 |
| B02 | Sullivan, Timmermann & White (1999), *Data-Snooping, Technical Trading Rule Performance, and the Bootstrap* | Guided | 7,846 条技术规则的具体警示 |
| B03 | Bailey et al. (2017), *The Probability of Backtest Overfitting* | Must/Deep | 用 CSCV 描述搜索赢家的样本外失败概率 |
| B04 | Bailey & López de Prado (2014), *The Deflated Sharpe Ratio* | Guided/Deep | 把试验次数和非正态性带入 Sharpe 证据 |
| B05 | Harvey, Liu & Zhu (2016), *… and the Cross-Section of Expected Returns* | Must/Deep | 因子动物园中的更高显著性门槛 |
| B06 | Brown et al. (1992), *Survivorship Bias in Performance Studies* | Guided | 说明股票池/基金池删掉失败者会制造可预测性 |

## Cluster C — 自动因子发现（7）

| paper_id | 论文 | 层级 | 入选理由 |
|---|---|---|---|
| C01 | Zhang et al. (2020), *AutoAlpha* | Reference | 遗传规划与层级搜索基线 |
| C02 | Cui et al. (2021), *AlphaEvolve* | Reference | 学习型变异和 seed library |
| C03 | Yu et al. (2023), *Generating Synergistic Formulaic Alpha Collections via Reinforcement Learning* | Guided/Deep | 直接优化因子集合的增量信息 |
| C04 | Ren et al. (2024), *RiskMiner* | Guided/Deep | 非 LLM 的风险偏好 MCTS 基线 |
| C05 | Li et al. (2024), *FAMA* | Guided | LLM 神经—符号组合及其异常高回测指标需要审计 |
| C06 | Tang et al. (2025), *AlphaAgent* | Guided | AST 相似度、语义一致性和复杂度约束 |
| C07 | Shi, Duan & Li (2025), *Navigating the Alpha Jungle* | Must/Deep | 用户已有全文；LLM+MCTS 的直接方法对象 |

## Cluster D — 量价与微观结构（6）

| paper_id | 论文 | 层级 | 入选理由 |
|---|---|---|---|
| D01 | Karpoff (1987), *The Relation Between Price Changes and Trading Volume: A Survey* | Must | 建立量价机制地图，避免因果故事化 |
| D02 | Campbell, Grossman & Wang (1993), *Trading Volume and Serial Correlation in Stock Returns* | Guided | 高量可对应流动性压力与条件反转 |
| D03 | Lee & Swaminathan (2000), *Price Momentum and Trading Volume* | Must/Deep | 量能状态改变动量持续与反转路径 |
| D04 | Gervais, Kaniel & Mingelgrin (2001), *The High-Volume Return Premium* | Guided | “异常量”应相对自身历史定义 |
| D05 | Llorente et al. (2002), *Dynamic Volume-Return Relation of Individual Stocks* | Guided/Deep | 信息交易与流动性交易可给出相反方向 |
| D06 | Barber & Odean (2008), *All That Glitters* | Guided | 异常量作为投资者注意力代理之一 |

## Cluster E — 主题与事件（3）

| paper_id | 论文 | 层级 | 入选理由 |
|---|---|---|---|
| E01 | MacKinlay (1997), *Event Studies in Economics and Finance* | Must/Deep | 事件时点、正常收益模型、AR/CAR 与推断基础 |
| E02 | Brown & Warner (1985), *Using Daily Stock Returns: The Case of Event Studies* | Guided | 用模拟检查日频事件检验的 size/power |
| E03 | Somefun et al. (2022), *Allocating to Thematic Investments* | Guided | 主题应与行业、风格、区域暴露同时处理 |

## Cluster F — A 股约束（3）

| paper_id | 论文 | 层级 | 入选理由 |
|---|---|---|---|
| F01 | Hu, Pan & Wang (2021), *Chinese Capital Market: An Empirical Overview* | Must/Deep | A 股制度与投资者结构总览 |
| F02 | Guo, Li & Tu (2012), *A Unique T+1 Trading Rule in China* | Guided | 同日买卖不可行会改变信号与收益实现 |
| F03 | Chen, Gu & Ni (2023), *How Price Limit Affects Market Efficiency…* | Guided | 涨跌停既是信息事件也是成交约束 |

## 筛选判断

- 核心不是“最看多”清单，而是对当前项目最能改变研究质量的 30 篇。
- 自动挖掘论文保留其积极结果，也同时保留搜索复用、预算公平、同 bar 时序和交易可实现性问题。
- 主题投资正式学术文献少于因子与事件研究；因此不把机构主题说明冒充资产定价证据。
- 88 条完整候选的元数据和非核心状态均在注册表，低相关结果已删除而不是为数量补齐。

<!-- FULLTEXT_BATCH_BEGIN -->
## 2026-07-25 supplied-PDF incremental checkpoint

| ID | Acquisition | Knowledge-base status | Reader |
|---|---|---|---|
| C07 | existing_fulltext_reviewed | full_text_reviewed | existing_native_nature_reader_validated |
| B01 | repository_version_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| B05 | author_manuscript_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| A04 | open_fulltext_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| A03 | open_fulltext_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| D03 | full_text_downloaded_not_reviewed | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| E01 | repository_version_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| F01 | open_fulltext_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| A01 | repository_version_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| A02 | repository_version_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| A05 | open_fulltext_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| B03 | author_manuscript_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| B04 | author_manuscript_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| C03 | open_fulltext_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| C04 | open_fulltext_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| C06 | open_fulltext_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| D05 | full_text_downloaded_not_reviewed | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| E03 | user_pdf_required | user_pdf_required | user_pdf_required |
| B02 | user_pdf_required | user_pdf_required | user_pdf_required |
| B06 | repository_version_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| C01 | open_fulltext_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| C02 | open_fulltext_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| C05 | open_fulltext_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| D01 | full_text_downloaded_not_reviewed | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| D02 | full_text_downloaded_not_reviewed | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| D04 | full_text_downloaded_not_reviewed | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| D06 | author_manuscript_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| E02 | repository_version_downloaded | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| F02 | full_text_downloaded_not_reviewed | full_text_downloaded_not_reviewed | source_only_extraction_complete |
| F03 | full_text_downloaded_not_reviewed | full_text_downloaded_not_reviewed | source_only_extraction_complete |

D01-D05, F02 and F03 were supplied by the user and ingested incrementally. They remain `full_text_downloaded_not_reviewed`; Work-mode close reading is required before any promotion to `full_text_reviewed`.
<!-- FULLTEXT_BATCH_END -->
