# quant_start：A 股中频量化研究（H5–H8）

这是一个面向导师审阅的 A 股中频量化研究项目。项目重点不是发布实盘交易系统，而是展示从研究问题、数据合同、预注册、实现、诊断到停止决策的完整证据链。所有结果均为历史样本内的研究证据，不构成投资建议、稳定 Alpha、因果机制或样本外有效性声明。

## 当前研究阶段

H5–H8 已完成。当前工作是回到文献，选择和精读下一篇论文；是否形成 H9 尚未决定。选择下一问题前，会先检查相关文献与新颖性，再决定是否值得开展大规模数据和实证工作。

导师建议先阅读 [H5–H8 研究进展](docs/research_progress_h5_h8.md)，再进入各 hypothesis 的预注册、正式报告和脚本。

## H5–H8 概览

| Hypothesis | 文献启发 | 研究问题 | 主要结果 | 最终解释 |
| --- | --- | --- | --- | --- |
| H5 | Lee & Swaminathan (2000) | past return × trading activity 是否对应后续 continuation/reversal 路径？ | H5A 的 raw amount 排序产生 6/6 稳定主对比，但该 proxy 与规模等暴露显著相关；更接近 turnover 的 H5B VT20 与 H5A 仅 7/9 同方向，绝对幅度只保留约 4%–19%。 | paper-like pattern 可见，但 turnover mechanism 的 construct validity 不稳健，不能称为 Alpha 或因果效应。 |
| H6 | Gervais, Kaniel & Mingelgrin (2001) | 个股自身历史中的异常日成交额，是否对应后续 5/10/20 日收益路径？ | 20D HIGH_SHOCK−LOW_SHOCK 在 LOW/MID/HIGH_RETURN 均为负，市场归一化后方向保留；局部趋势与样本限制仍是重要替代解释。 | 历史样本中存在较稳定的负向 abnormal-activity association，但 mechanism unresolved。 |
| H7 | Llorente et al. (2002) | turnover 是否改变个股动态 return relation，并呈现规模异质性？ | Primary 4,470 只股票的 C2 中位数为负，2D/5D、替代 turnover 口径和长历史样本方向大体延续；规模分组与截面回归显示明显异质性。 | 这是历史样本内的现象诊断。后续文献复核显示增量新颖性不足，项目停止继续扩展，并形成“先做 novelty check”的流程教训。 |
| H8 | Yao & Yang (2026) | 在可行的数据边界内，T+1 sign-asymmetric return-reversal 机制能否作 stock-level adapted replication？ | 474 只 Primary 股票的全样本 close-to-close 差异方向不支持完整复现；intraday−overnight timing contrast 为负，大盘 quintiles 的差异也转为负。 | 只能表述为 partial / heterogeneous replication evidence：部分 timing 与大盘股结果与论文预测一致，不能包装为完整复现、因果机制或稳定 Alpha。 |

## 研究逻辑的演进

```text
H5  paper-like pattern -> proxy / construct-validity problem
H6  empirical association -> mechanism unresolved
H7  cross-sectional heterogeneity -> novelty problem
H8  mechanism-oriented replication -> partial large-cap evidence
```

研究标准因此从“是否出现显著或好看的结果”逐步转向：construct validity、confounding、literature novelty、mechanism identification、robustness，以及尚未打开的 OOS/prospective evidence。

## 当前研究边界

- **冻结股票池**：56 只股票，冻结日为 `2026-07-11`。
- **冻结文件**：`data/processed/research_universe_lowvol_freeze_20260711.csv`。
- **冻结文件 SHA-256**：`a8c2803802f1927176fdf7940aa187b551fdc6d03037876c1c5d9d297780e626`。
- **主题标签**：44 只仅 AI、11 只仅商业航天、1 只双主题（`002049` 紫光国微）；按 50/50 分数归属时，AI/商业航天主题权重分别为 44.5/11.5。
- **期间口径**：LOWVOL 与其可比研究使用 57 个锁定期间。Hypothesis 3 因首期 amount 窗口覆盖不足，使用 56 期共同样本。
- **重要限制**：股票池是被冻结的研究集合，而不是历史时点的成分股快照；不对缺失价格、停牌日或不完整窗口进行插补。

## 项目全流程

| 阶段 | 工作内容 | 主要输入/输出 |
| --- | --- | --- |
| 1. 主题候选与业务核验 | 汇总主题候选股，结合人工业务证据、规则例外和风险标记，形成可审计的研究池。 | `data/stockPool/`、`data/manual/`、主题业务复核 CSV |
| 2. 冻结股票池 | 将通过复核的股票、主题、证据字段和来源哈希固定；双主题股票按唯一代码合并。 | `research_universe_lowvol_freeze_20260711.csv`、`reports/lowvol20_freeze_manifest_v1_5.csv` |
| 3. 价格与基准数据 | 校验 qfq 复权价格、市场日历、端点可用性和价格主键；使用沪深 300 等基准的有效市场日。 | `adjusted_price_panel_v1_5.csv`、`hybrid_benchmark_panel_v1_5.csv`、QA 报告 |
| 4. 基准组合 | 在锁定调仓边界上构建冻结股票池等权基准，记录收益、换手、风险和缺失处理。 | `reports/adjusted_stock_pool_baseline_*`、`reports/baseline_attribution_*` |
| 5. 因子研究 | 以冻结 factor panel 检验 MOM60 与 LOWVOL20；保留每期分组、收益、风险、稳定性和 QA 证据。 | `data/processed/*factor_panel*`、`reports/factor_*` |
| 6. LOWVOL20 冻结与维护 | LOWVOL20 锁定后进行身份、结构和复现检查；匹配冻结身份时走 no-op 维护路径，不重建或替换产物。 | `reports/lowvol_locked_grid_prototype_*`、freeze/maintenance/prospective 文档 |
| 7. Hypothesis 3：流动性过滤 | 以流动性过滤本身为主比较：未过滤等权 vs 流动性过滤等权；LOWVOL Q5 的过滤交互仅为次级分析。 | `reports/liquidity_filter_*`、`scripts/test_liquidity_filter_hypothesis_v1_6.py` |
| 8. Hypothesis 4A：主题广度诊断 | 用信号日 Breadth60 对随后锁定期间的基准收益和回撤风险做描述性市场状态诊断，不生成交易规则。 | `scripts/run_theme_breadth_diagnostic_v1_7.py`、`reports/theme_breadth_*` |
| 9. 商业航天事件研究 | 对长征十号乙海上回收事件做固定窗口的日频描述性事件研究；T+5 不可用时停止，不扩展为新闻、预测或策略模块。 | `scripts/run_changzheng10_event_study.py`、`reports/event_study/changzheng10_recovery/` |
| 10. H5：交易活动与反转路径 | 在 broader-A 历史样本中固定 RETURN60、activity state 与 20/60/120D 路径；随后审计 raw amount 的规模/波动暴露，并以 VT20 作最小 construct check。 | `reports/hypothesis_5a/`、`reports/hypothesis_5b/` |
| 11. H6：异常交易活动 | 用个股自身 50 日 amount 历史定义 shock，继承 H5 RETURN_STATE，比较后续 5/10/20D 路径。 | `reports/hypothesis_6/` |
| 12. H7：动态量价关系 | 构建并审计 turnover 数据，以个股回归检验动态 volume-return relation、期限稳健性和规模异质性。 | `reports/hypothesis_7/` |
| 13. H8：T+1 机制适配复现 | 先解决样本、公司行动、收益分解和 GARCH 合同，再执行 stock-level adapted replication。 | `reports/hypothesis_8/` |

## MCTS 的位置

MCTS 不是当前项目的核心研究结论。已有 v0/v1 仅是 `historical_seen` 搜索机制 sandbox，用来检查表达式重复、信息等价与 MCTS/Random Search 的搜索效率；两轮均未观察到合同要求下的稳定 MCTS search-efficiency advantage，也不允许 Alpha 或 OOS claim。当前更合理的顺序是先从论文提取 economically meaningful primitives，完成数据与实证验证，再决定是否有必要搜索这些 primitives 的组合。

## 主要文献

- Lee, C. M. C. & Swaminathan, B. (2000). “Price Momentum and Trading Volume.” *The Journal of Finance*, 55(5), 2017–2069. [DOI](https://doi.org/10.1111/0022-1082.00280)
- Gervais, S., Kaniel, R. & Mingelgrin, D. H. (2001). “The High-Volume Return Premium.” *The Journal of Finance*, 56(3), 877–919. [DOI](https://doi.org/10.1111/0022-1082.00349)
- Llorente, G., Michaely, R., Saar, G. & Wang, J. (2002). “Dynamic Volume-Return Relation of Individual Stocks.” *Review of Financial Studies*, 15(4), 1005–1047. [DOI](https://doi.org/10.1093/rfs/15.4.1005)
- Yao, J. & Yang, Y. (2026). “Positive feedback trading, the T+1 rule, and asymmetric return reversals in China.” *Economic Modelling*, 164, 107783.

## 研究原则与复核规则

1. **先冻结、后比较**：股票池、期间键、成本情景和已冻结的 LOWVOL 产物不得由后续研究回写。
2. **无前视与无填补**：信号只使用信号日及之前的精确市场日；端点或窗口缺失会显式标记为无效。
3. **等权、可重算**：正式组合遵循固定成员、等权归一化、漂移后换手和既定缺价处理；端点收益与正式产物对账。
4. **区分描述与因果**：行业、主题构成、事件窗口和组合交互只作为暴露或机制证据，不作严格因果收益归因。
5. **结论有边界**：Hypothesis 3 使用 `supported_for_implementability`、`mixed`、`not_supported`；4A 使用 `diagnostically_supported`、`mixed`、`not_supported`；事件研究仅使用描述性解释类别。

## 目录导览

```text
data/
  processed/     冻结股票池、复权价格、基准与因子面板
  manual/        人工业务证据和概念映射
  stockPool/     股票池构建规则、审计表与候选记录
reports/         研究报告、期间表、汇总表、QA 与冻结清单
scripts/         可复现研究与诊断脚本
src/aq_factor_lab/
  data_layer/    AkShare 数据读取、缓存、规范化和质量检查
  data_collection/  有边界的主题数据采集工具
tests/           脚本与数据契约的单元测试
```

`data_layer` 和 `data_collection` 只提供数据基础设施，不实现因子排序、策略或回测。所有主题研究都应优先复用冻结面板和已有报告，而不是静默刷新历史数据。

## 复现与检查

在项目根目录使用现有 Python 环境：

```powershell
python -m unittest discover -s tests
python -m ruff check scripts tests src
```

仅在需要复核相应模块时运行其专用脚本；不要把通用数据抓取或 `run_research.py` 当作冻结研究的重建命令。以下文件必须保持只读：冻结 universe、调整后价格面板、LOWVOL 正式 periods/summary，以及 MOM60、LOWVOL20、Hypothesis 3 的既有结论产物。

## 冻结的 56 只股票

下表直接来自冻结股票池。`AI|商业航天` 表示同一股票同时属于两个主题；在主题加权诊断中按 50/50 处理，但在任何单个组合中只保留一次。

| 代码 | 名称 | 冻结主题 |
| --- | --- | --- |
| 000063 | 中兴通讯 | AI |
| 000681 | 视觉中国 | AI |
| 000901 | 航天科技 | 商业航天 |
| 000938 | 紫光股份 | AI |
| 000977 | 浪潮信息 | AI |
| 001208 | 华菱线缆 | 商业航天 |
| 002015 | 协鑫能科 | AI |
| 002044 | 美年健康 | AI |
| 002049 | 紫光国微 | AI\|商业航天 |
| 002065 | 东华软件 | AI |
| 002131 | 利欧股份 | AI |
| 002212 | 天融信 | AI |
| 002230 | 科大讯飞 | AI |
| 002236 | 大华股份 | AI |
| 002279 | 久其软件 | AI |
| 002315 | 焦点科技 | AI |
| 002361 | 神剑股份 | 商业航天 |
| 002373 | 千方科技 | AI |
| 002396 | 星网锐捷 | AI |
| 002410 | 广联达 | AI |
| 002446 | 盛路通信 | 商业航天 |
| 002544 | 普天科技 | 商业航天 |
| 002558 | 巨人网络 | AI |
| 002757 | 南兴股份 | AI |
| 002792 | 通宇通讯 | 商业航天 |
| 002881 | 美格智能 | AI |
| 002929 | 润建股份 | AI |
| 002935 | 天奥电子 | 商业航天 |
| 002987 | 京北方 | AI |
| 300002 | 神州泰岳 | AI |
| 300017 | 网宿科技 | AI |
| 300033 | 同花顺 | AI |
| 300047 | 天源迪科 | AI |
| 300058 | 蓝色光标 | AI |
| 300101 | 振芯科技 | 商业航天 |
| 300113 | 顺网科技 | AI |
| 300133 | 华策影视 | AI |
| 300170 | 汉得信息 | AI |
| 300182 | 捷成股份 | AI |
| 300339 | 润和软件 | AI |
| 300348 | 长亮科技 | AI |
| 300378 | 鼎捷数智 | AI |
| 300413 | 芒果超媒 | AI |
| 300454 | 深信服 | AI |
| 300458 | 全志科技 | AI |
| 300496 | 中科创达 | AI |
| 300627 | 华测导航 | 商业航天 |
| 300629 | 新劲刚 | 商业航天 |
| 300634 | 彩讯股份 | AI |
| 300674 | 宇信科技 | AI |
| 300857 | 协创数据 | AI |
| 300996 | 普联软件 | AI |
| 301050 | 雷电微力 | 商业航天 |
| 301110 | 青木科技 | AI |
| 301165 | 锐捷网络 | AI |
| 301171 | 易点天下 | AI |

## 面向导师审阅的入口

- H5–H8 总览与研究演进：`docs/research_progress_h5_h8.md`。
- H5：`reports/hypothesis_5a/h5a_preregistration_and_implementation_plan.md`、`reports/hypothesis_5a/h5a_diagnostic_report.md`、`reports/hypothesis_5b/h5b_diagnostic_report.md`。
- H6：`reports/hypothesis_6/h6_daily_amount_preregistration.md`、`reports/hypothesis_6/h6_diagnostic_report.md`。
- H7：`reports/hypothesis_7/h7_dynamic_volume_return_preregistration_v1.md`、`reports/hypothesis_7/h7_dynamic_volume_return_report_v1.md`。
- H8：`reports/hypothesis_8/h8_preregistration_v1.md`、`reports/hypothesis_8/h8_report_v1.md`。
- 研究范围与库存：`reports/project_inventory_for_backtest.md`、`reports/project_structure_for_v1_3.md`。
- LOWVOL20 冻结与维护：`reports/lowvol20_freeze_manifest_v1_5.csv`、`reports/lowvol20_maintenance_mode_v1_5_1.md`。
- 股票池来源与业务证据：`data/stockPool/`、`theme_business_review_completed_001_200.csv`。
- 事件研究数据状态：`reports/event_study/changzheng10_recovery/event_data_manifest.csv`。

任何新增研究应新建版本化脚本与报告，不修改冻结输入或既有结论；需要重新选择股票、改变阈值、变更窗口或启动新的治理流程时，应先单独审批。
