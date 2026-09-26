# 学生阅读计划

阅读目标不是记住结论，而是能复述研究问题、数据、方法、限制，并判断能否迁移到当前 A 股项目。Must Read 要做笔记和回答问题；Guided Read 只抓骨架；Reference Only 在具体问题出现时查。

## Must Read（8 篇）

| 优先级 | paper_id | 必读章节/页码 | 难度 | 阅读前术语 | 读后必须能回答的 3 个问题 |
|---:|---|---|---|---|---|
| 1 | C07 | 本地读者“方法”“实验”“批判性审计”；原文 p.1–7、Appendix G/H/J | 高 | RankIC、RankIR、UCT、AST、OOS | 1) 人类固定什么、AI做什么？ 2) 五维奖励怎样形成？ 3) 为什么 MCTS 仍会过拟合？ |
| 2 | B01 | Abstract、Sections 1–3、procedure/example、Conclusion | 高 | bootstrap、复合原假设、loss differential | 1) data snooping 的统计对象是什么？ 2) 为什么只检验冠军会错？ 3) trial ledger 为何是检验输入？ |
| 3 | B05 | Abstract、Introduction、multiple-testing framework、Conclusion | 高 | p-value、t-stat、FDR、factor zoo | 1) 为什么 1.96 不够？ 2) 隐藏试验数怎样影响门槛？ 3) REV60 为何不算独立发现？ |
| 4 | A04 | Abstract、replication protocol、value/equal weighting、transaction-cost discussion | 中高 | anomaly、value weighting、microcap、replication | 1) “未复制”怎样定义？ 2) 微盘股为何改变结论？ 3) 统一口径为何重要？ |
| 5 | A03 | Abstract、cost model、anomaly taxonomy、net-return tables | 中高 | turnover、break-even cost、long-short | 1) gross signal 与 net implementability 有何差别？ 2) 换手怎样吞噬收益？ 3) A 股还要增加哪些约束？ |
| 6 | D03 | Abstract、portfolio formation、volume–momentum results、long-horizon reversal | 中 | turnover、double sort、momentum lifecycle | 1) 过去成交量如何改变动量？ 2) 论文是否支持“放量必涨”？ 3) 可写成哪个连续交互？ |
| 7 | E01 | pp.13–39；事件定义、正常收益、aggregation/inference、design issues | 中 | estimation window、AR、CAR、market model | 1) 正常收益怎样估？ 2) 事件聚集为何破坏标准误？ 3) 描述性案例与推断性事件研究差在哪？ |
| 8 | F01 | Abstract/overview、market institutions、investor composition、summary | 中 | T+1、price limit、ST、free float | 1) A 股哪些制度随时间变化？ 2) 规则怎样影响可成交收益？ 3) 数据字典必须保存哪些历史字段？ |

### Must Read 的做法

每篇用一页纸写五栏：`问题 / 数据 / 方法 / 作者结论 / 我不相信的地方`。先不写公式代码。八篇读完后，学生应能口头讲清：

1. 为什么一个 RankIC 不等于可交易；
2. 为什么每次“再试一个阈值”都增加多重检验；
3. 为什么量价关系没有单一方向；
4. 自动搜索的价值与风险分别在哪里。

## Guided Read（10 篇）

| 优先级 | paper_id | 必读章节/页码 | 难度 | 阅读前术语 | 读后应能回答的 3 个问题 |
|---:|---|---|---|---|---|
| 9 | A01 | Abstract、变量构造、横截面回归、结论 | 中 | beta、size、book-to-market、Fama–MacBeth | 1) 回归与分组各回答什么？ 2) beta 的结果是什么？ 3) 1992 论文缺哪些现代验证？ |
| 10 | A02 | Abstract、formation/holding design、主要表、结论 | 中 | winner/loser、skip period、overlapping portfolio | 1) 中期动量怎样定义？ 2) 何时出现反转？ 3) 为什么不能替 MOM60 决定方向？ |
| 11 | A05 | Abstract、sample split、model comparison、variable importance | 高 | regularization、validation、OOS R²、nonlinearity | 1) 验证集做什么？ 2) 哪类非线性重要？ 3) 56 只股票为何不匹配？ |
| 12 | B03 | Abstract、CSCV algorithm、PBO definition、examples | 高 | cross-validation、rank、logit、selection | 1) PBO 衡量谁？ 2) 为什么普通 holdout 可能不稳？ 3) PBO 为何不能替 final test？ |
| 13 | B04 | DSR definition、trial-count correction、non-normality example | 高 | Sharpe、skewness、kurtosis、PSR | 1) DSR 修正哪三类膨胀？ 2) 有效试验数为何难估？ 3) 输入回测有前视时 DSR 能否修复？ |
| 14 | C03 | MDP/reward、collection objective、CSI experiments | 高 | policy gradient、synergy、correlation | 1) 单因子与集合目标有何差异？ 2) 奖励如何防重复？ 3) OOS 是否独立？ |
| 15 | C04 | Abstract、MDP/MCTS、risk-seeking objective、experiments | 高 | MDP、MCTS、risk-seeking、reward dense | 1) MCTS 利用什么结构？ 2) risk-seeking 有何选择偏差？ 3) 应与什么随机基线比较？ |
| 16 | C06 | Abstract、AST similarity、hypothesis alignment、complexity control | 高 | AST、semantic alignment、alpha decay | 1) 三种正则分别限制什么？ 2) LLM 评分能否当统计证据？ 3) decay 与过拟合有何区别？ |
| 17 | D05 | Abstract、model predictions、empirical design、conclusion | 高 | informed trading、liquidity trading、conditional autocorrelation | 1) 为什么同样的量可能对应延续或反转？ 2) 哪些代理变量区分机制？ 3) 日线数据不能识别什么？ |
| 18 | E03 | Abstract、theme definition、risk-factor controls、allocation framework | 中 | thematic exposure、style factor、robust optimization | 1) 主题与行业有何不同？ 2) 为什么要控制传统因子？ 3) 当前概念成员表缺少什么历史信息？ |

## Reference Only（12 篇）

| 优先级 | paper_id | 查阅章节/页码 | 难度 | 阅读前术语 | 需要时回答的 3 个问题 |
|---:|---|---|---|---|---|
| 19 | B02 | rule universe、bootstrap results、later subsample | 中高 | technical rule、bootstrap | 1) 测了多少规则？ 2) 校正后什么变化？ 3) 后期样本是否持续？ |
| 20 | B06 | truncation model、numerical examples、conclusion | 中高 | survivorship、truncation | 1) 删除失败者怎样制造持续性？ 2) 股票池中对应什么？ 3) 什么 point-in-time 数据可修复？ |
| 21 | C01 | hierarchy/root genes、evolution loop、experiments | 高 | GP、expression tree | 1) 层级搜索省在哪里？ 2) 搜索空间谁固定？ 3) 预算如何计？ |
| 22 | C02 | Abstract、architecture、mutation/search policy、experiments | 高 | genetic programming、mutation、seed alpha | 1) 学习策略改变了哪一步？ 2) 新公式如何判重？ 3) 基线预算是否公平？ |
| 23 | C05 | pp.3891–3902；CSS、CoE、Table 2 | 高 | in-context sample、neural-symbolic | 1) CSS/CoE 各做什么？ 2) 667.2% 的 Sharpe 表达如何审计？ 3) 交易时序是否清楚？ |
| 24 | D01 | empirical regularities、theory survey、future directions | 中 | signed/absolute return、volume | 1) 哪些关系较稳？ 2) 因果机制有几类？ 3) 为什么不能直接造阈值？ |
| 25 | D02 | model intuition、conditional autocorrelation、empirical tables | 高 | market maker、price pressure | 1) 高量为何改变自相关？ 2) 下跌后预期收益怎样变化？ 3) 这是横截面还是时间序列结论？ |
| 26 | D04 | abnormal-volume definition、event portfolios、horizon | 中 | abnormal volume、visibility | 1) 为什么相对自身历史？ 2) 效应持续多久？ 3) A 股涨停怎样干扰？ |
| 27 | D06 | attention proxies、individual/institution comparison、results | 中 | attention、buy-sell imbalance | 1) 三个 attention proxy 是什么？ 2) 个人与机构有何差别？ 3) 买入偏好是否等于未来收益？ |
| 28 | E02 | simulation setup、test size/power、daily-return findings | 中高 | size、power、event-induced variance | 1) 模拟如何知道原假设为真？ 2) 哪些简单方法表现尚可？ 3) 主题相关残差会怎样改变 size？ |
| 29 | F02 | model、B-share empirical test、welfare/volume results | 中高 | T+0/T+1、trend chaser | 1) T+1 限制什么？ 2) 作者的实证对象为何不是整个 A 股？ 3) 对执行时点有何含义？ |
| 30 | F03 | policy reform、DID、event study、shortable heterogeneity | 高 | price discovery、DID、short-sale constraint | 1) 价格限制与卖空如何交互？ 2) 哪些股票改善更多？ 3) 涨停收盘为何不一定可交易？ |

## 建议顺序

第一周读 C07、B01、B05；第二周读 A04、A03；第三周读 D03、E01、F01。先完成每篇的三个问题，再进入 Guided Read。若任何答案只能重复摘要原句而不能用自己的例子解释，暂缓编码。

<!-- FULLTEXT_BATCH_BEGIN -->
## 2026-07-25 incremental Work-mode availability

- D01, D02, D03, D04, D05, F02 and F03 now have source-only Reader bundles.
- Start each paper from its `papers/readers/<paper_id>/analysis/work_handoff.md`.
- No full Chinese translation was generated; translation queues remain pending Work review.
- These seven papers are downloaded and structurally mapped, but not manually close-read.
<!-- FULLTEXT_BATCH_END -->
