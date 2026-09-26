# 文献搜索查询与来源记录

搜索日期：2026-07-25

## 检索策略

先用 OpenAlex 做宽检索，再用 DOI、arXiv、ACL Anthology、出版社页面、SSRN/NBER/机构页面核验核心记录。宽检索的 12 个查询各读取前 25 条，共取得 264 条去重元数据；这不是“命中 264 篇即全部保留”，而是用于建立可审计候选池。

## OpenAlex 宽检索

| query_id | exact_query | database_or_search_source | result_count_seen | records_retrieved | notes |
|---|---|---:|---:|---:|---|
| Q_A01 | cross-sectional stock return factor evaluation information coefficient portfolio sorts | OpenAlex | 6706 | 25 | 结果宽泛，人工保留原始资产定价与评价论文 |
| Q_A02 | factor zoo anomalies transaction costs out of sample stock returns | OpenAlex | 184 | 25 | 优先 replication、cost、OOS |
| Q_B01 | backtest overfitting data snooping multiple testing finance | OpenAlex | 122 | 25 | 去除泛 ML 和博客式论文 |
| Q_B02 | false discoveries deflated Sharpe ratio probability of backtest overfitting | OpenAlex | 26 | 25 | 核验 PBO、DSR、false discovery |
| Q_C01 | formulaic alpha mining genetic programming reinforcement learning symbolic regression | OpenAlex | 28 | 25 | 重点保留可解释公式与搜索协议 |
| Q_C02 | LLM alpha factor mining MCTS formula discovery | OpenAlex | 19 | 19 | 包含 RiskMiner、AlphaAgent、Alpha Jungle |
| Q_D01 | trading volume price momentum reversal stock returns | OpenAlex | 5677 | 25 | 结果很宽，回到经典原始论文 |
| Q_D02 | abnormal volume investor attention disagreement liquidity price pressure | OpenAlex | 745 | 25 | 用机制而非“庄家”叙事筛选 |
| Q_E01 | thematic investing stock classification event study abnormal returns | OpenAlex | 869 | 25 | 主题投资学术文献较少，方法与事件文献并行 |
| Q_E02 | news announcement response industry spillover theme stock returns | OpenAlex | 788 | 25 | 关注共同事件、行业污染和注意力扩散 |
| Q_F01 | China A-share price limits suspension ST delisting transaction costs | OpenAlex | 62 | 25 | 保留规则直接相关论文 |
| Q_F02 | China stock market T+1 survivorship point in time constituents liquidity | OpenAlex | 139 | 25 | 宽检索较噪，核心条目另用出版页核验 |

原始响应位于 `raw_metadata/Q_*.json`，去重汇总为 `raw_metadata/openalex_candidates.csv`。

## 精确核验查询

| query_id | exact_query | database_or_search_source | result_count_seen | notes |
|---|---|---|---:|---|
| V_B01 | site:academic.oup.com rfs cross section expected returns factor zoo multiple testing Harvey Liu Zhu 2016 | Web search + OUP | 10 | 核验 RFS 卷期、作者、DOI 与摘要 |
| V_B02 | "The Probability of Backtest Overfitting" journal DOI | Web search + eScholarship/Risk.net | 8 | 核验 DOI 10.21314/JCF.2016.322 |
| V_B03 | "The Deflated Sharpe Ratio" journal DOI | Web search + author version/SSRN | 6 | 正式期刊标识采用 10.3905/jpm.2014.40.5.094 |
| V_C01 | site:aclanthology.org "Can Large Language Models Mine Interpretable Financial Factors More Effectively" | ACL Anthology | 8 | 核验作者、页码和 DOI |
| V_C02 | site:arxiv.org LLM formulaic alpha mining MCTS AlphaAgent Alpha-GPT Navigating the Alpha Jungle | arXiv/web search | 6 | 核验版本与摘要主张 |
| V_D01 | "Price Momentum and Trading Volume" | Wiley | 1 primary | 核验 DOI、样本与摘要结论 |
| V_D02 | "Trading Volume and Serial Correlation in Stock Returns" | OUP/author repository | 3 primary/author copies | 核验 DOI、机制与摘要 |
| V_E01 | MacKinlay 1997 Event Studies in Economics and Finance | AEA/JSTOR/BU author copy | 3 | 核验页码 13–39 与方法角色 |
| V_F01 | "A unique T + 1 trading rule in China" authors DOI | Elsevier | 1 primary | 核验 10.1016/j.jbankfin.2011.09.002 |
| V_F02 | "Does the T + 1 rule really reduce speculation" DOI authors | Wiley | 1 primary | 核验 10.1111/acfi.12330 |
| V_F03 | "How price limit affects the market efficiency" authors DOI | Elsevier/RePEc/SSRN | 2 versions | 核验正式版 10.1016/j.jempfin.2023.05.003 |
| V_F04 | "Statistical Properties and Pre-hit Dynamics of Price Limit Hits" | PLOS/arXiv | 2 versions | 核验 DOI 10.1371/journal.pone.0120312 |

## 中英文后续检索词

### Cluster A

- `cross-sectional factor evaluation RankIC RankIR quantile monotonicity turnover factor decay`
- `横截面 因子评价 RankIC 分位数组合 单调性 换手率 因子衰减`
- `long-only versus long-short factor evaluation transaction costs`
- `多空因子 与 多头组合 评价差异 交易成本`

### Cluster B

- `data snooping multiple testing backtest overfitting deflated Sharpe prospective test`
- `数据窥探 多重检验 回测过拟合 去膨胀夏普 前瞻测试`
- `point-in-time universe survivorship look-ahead bias experiment registry finance`
- `时点股票池 生存者偏差 前视偏差 实验注册`

### Cluster C

- `formulaic alpha mining random search baseline search budget canonicalization`
- `公式因子 挖掘 随机搜索 基线 搜索预算 公式规范化`
- `symbolic regression genetic programming reinforcement learning MCTS LLM alpha`
- `符号回归 遗传规划 强化学习 蒙特卡洛树搜索 大模型 因子`

### Cluster D

- `abnormal volume return continuation reversal information arrival price pressure`
- `异常成交量 收益延续 反转 信息到达 价格压力`
- `volume contraction breakout investor attention disagreement liquidity`
- `缩量 突破 投资者注意力 意见分歧 流动性`

### Cluster E

- `thematic investing point-in-time theme membership industry contamination`
- `主题投资 历史成分 行业污染 主题暴露`
- `event study clustered events event-induced variance industry-adjusted abnormal returns`
- `事件研究 事件聚集 事件诱导方差 行业调整异常收益`

### Cluster F

- `China A-share T+1 price limit suspension ST delisting adjusted prices`
- `A股 T+1 涨跌停 停牌 ST 退市 前复权 后复权`
- `Chinese stock point-in-time index constituents theme concept membership history`
- `中国股票 历史指数成分 主题概念历史成员`

## 筛选与去重规则

1. DOI 优先作为去重键；无 DOI 时用 arXiv/SSRN/ACL Anthology 稳定标识。
2. 同一论文的工作稿与正式版只保留正式版，除非工作稿是唯一开放版本。
3. 标题近似但研究对象不同的不合并。
4. 只给漂亮回测、没有时间切分和成本说明的论文可登记，但不进入核心清单。
5. 元数据冲突时以出版者正式页为准；OpenAlex 的 early-online 年份已对核心条目按卷期修正。
