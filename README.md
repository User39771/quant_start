# Quant Start

> **Mentor / project handoff:** see [`mentor_handoff/README.md`](mentor_handoff/README.md)

Quant Start 是一个从本科一年级开始的量化研究训练项目。项目以人工智能与商业航天主题股票为起点，从基础的主题因子实验，逐步转向更明确的 universe definition、point-in-time 数据、measurement、文献驱动假设、样本隔离、QA 与 evidence governance。项目没有建立经过充分验证的可交易 Alpha 策略，但留下了边界清楚的 empirical findings、如实保存的负面与 mixed 结果，以及一套逐渐严格的研究流程。

## Project status

- **当前状态：** v1.0 research freeze。
- **结论边界：** 没有经过充分验证的可交易 Alpha claim，也没有盈利性或因果机制结论。
- **档案原则：** v1.0 是冻结的历史研究记录；既有设计、证据身份、支持分类和解释边界不应被事后静默改写。
- **后续治理：** 真正的新问题应进入新的 study、evidence cycle 或项目版本，而不是回写 v1.0。

**Freeze the claim, not the curiosity.**

## What the project studied

### A-share thematic research

项目先从 Eastmoney 概念板块生成 AI / 商业航天候选股票，再将概念标签与业务 materiality 分开，通过有记录的业务证据和人工判断形成并冻结 56 只股票的研究总体。这里的人工判断是合法的研究输入，前提是 evidence-informed、有记录，并在接触相应结果前冻结。该总体主要是 current-universe historical research，不是完整的历史 point-in-time 主题成分回测。

早期研究依次考察：

- H1：MOM60 正向动量；
- H2：可靠性约束下的 LOWVOL20；
- H3：固定成交额中位数 liquidity filter，主要作为 implementability/filter diagnostic；
- H4：主题 Breadth60 市场状态诊断。

H5–H8 随后把研究重点从简单因子表现推进到交易活动与收益关系的 measurement、empirical phenomenon、economic mechanism 和 adapted replication。研究逐步引入 literature reconnaissance、假设专属设计、冻结比较家族、point-in-time turnover 分母、stock-level 模型和明确停止规则。

### Robinhood Chain

Robinhood Chain 是独立的新市场研究分支，**不是 H9**。其 Primary RQ2 是：Stock Token 在传统市场 20:00–04:00 ET 间隙中的价格变化，是否在 16:00–20:00 股票盘后变动之外，对随后美国股票开盘含有增量信息？

该分支的设计身份为 `PILOT_INFORMED_PROSPECTIVE_EXTENSION`。已披露的 NVDA discovery observations 被排除在 Primary prospective inference 之外；Primary 使用 NVDA、GME 与 COST 的冻结 extension 样本。结果为正向但不确定的增量关联，且存在明显资产异质性和 estimator sensitivity。它不构成 price discovery、Alpha 或盈利性证据。E3 在严格 QA 后发生严重、资产偏斜的样本流失，使原 pooled temporal-localization 问题无法识别；这是一项 identification limitation，不是不存在机制的证明。

## Post-v1.0 capstone: Alpha Jungle / MCTS C0

C0 是 v1.0 冻结后的独立 capstone evidence cycle，在冻结的 Qlib 公式搜索基准下比较 grammar-random、Direct LLM 与 LLM-guided MCTS。MCTS 未通过事先冻结的 Validation advantage rule；但 Direct 与 MCTS 都发现了一个在 Final Test 中继续保持正 RankIC 的 price-volume interaction family。最终分类为 `MIXED`，该结果是历史 benchmark 中的有限经验发现，不是交易价值或 live-OOS claim。

## Main findings

| Stage | Main result | Evidence status |
|---|---|---|
| H1 — MOM60 | 注册的正向动量方向未获支持；负号不等于反转已被证明 | `not_supported`；`historical_seen` |
| H2 — LOWVOL20 | 显示方向一致的排序与降风险信息，但伴随温和收益牺牲 | bounded directional / risk evidence；不是已验证 Alpha |
| H3 — Liquidity Filter | 固定过滤没有改善比较，并带来更高换手与较差累计收益表现 | `not_supported`；implementability/filter diagnostic |
| H4 — Breadth60 | 核心关系较弱且含义不一致，未进入择时或配置阶段 | `mixed`；描述性状态诊断 |
| H5 — Activity states | 原始活动 pattern 稳定，但改用固定 turnover-like proxy 后幅度严重衰减 | measurement-sensitive historical pattern |
| H6 — Abnormal activity | own-history 异常高活动与较弱后续收益相关，过去赢家组更明显 | historical association；mechanism unresolved |
| H7 — Relative turnover | 较高相对 turnover 通常削弱 continuation，但一般不足以造成 reversal | measurement 较稳健；来源机制未被干净支持 |
| H8 — Adapted replication | 总体符号预测未复制，timing structure 方向一致 | `mixed / partial replication` |
| Robinhood RQ2 | Primary 方向为正但不确定；结果具有资产异质性且对 estimator 敏感 | bounded prospective-extension evidence；mechanism unresolved |

这些结果不能合并为一条交易策略。`not_supported`、`mixed` 与 `unidentified` 是不同研究结果：前者表示冻结方向或规则未获支持；第二种要求同时保留支持与反对证据；第三种表示有效样本或设计无法回答原问题。

## What changed methodologically

1. **Universe construction is part of the hypothesis.** 概念归属、业务 materiality 和历史可知性必须分开；有记录、evidence-informed 且在结果前冻结的人工判断是合法研究输入。
2. **Point-in-time correctness is part of measurement design.** 变量不仅要说明如何计算，也要说明信息何时可知；缺失谱系优于无依据回填。
3. **Liquidity and market constraints affect observability.** 低成交、停牌或涨跌停等约束会影响变量能否按研究所需的经济含义被可靠解释。
4. **Leakage can enter through samples and rules.** outcome 不只会通过变量泄漏，也可能通过样本选择、阈值、排除规则和事后改写进入研究。
5. **QA is part of research design.** QA 规则决定保留样本并改变 estimand；严格 QA 有时会使问题变成 unidentified。
6. **Separate frozen claims, exploration, and new hypotheses.** 冻结或 precommitted claim、post-outcome diagnostic 与新证据周期必须保持不同身份。

## Important limitations

- A 股主线主要是 current-universe historical research，主题 membership 并非完整历史 point-in-time 快照。
- H1–H8 的大部分证据属于 `historical_seen`，不能升级为独立 OOS validation。
- qfq 数据谱系、ST/停牌/涨跌停状态及部分公司行为信息仍不完整。
- 执行、容量、冲击成本、滑点和真实成交概率没有得到系统验证。
- 历史排序、相关与回归结果不识别唯一因果机制。
- Robinhood RQ2 的 Primary 样本较小，存在资产异质性、宽不确定区间和 measurement sensitivity。
- 因此，项目只报告有边界的研究发现；实际交易价值尚未被充分建立。

## Repository guide

- **项目总览与最终解释：** [PROJECT_V1_0_FINAL_REPORT.md](reports/PROJECT_V1_0_FINAL_REPORT.md)
- **早期基础与 H1–H4：** [EARLY_RESEARCH_HISTORY_H1_H4.md](reports/EARLY_RESEARCH_HISTORY_H1_H4.md)
- **H5–H8 研究史：** [H5_H8_RESEARCH_HISTORY.md](reports/H5_H8_RESEARCH_HISTORY.md)
- **跨阶段方法论经验：** [RESEARCH_METHODOLOGY_LESSONS.md](reports/RESEARCH_METHODOLOGY_LESSONS.md)
- **Robinhood RQ2 设计、结果与诊断目录：** [rq2_information_content_design](reports/robinhood_chain_pilot/rq2_information_content_design/)
- **C0 capstone addendum：** [PROJECT_V1_0_CAPSTONE_C0_ADDENDUM.md](reports/PROJECT_V1_0_CAPSTONE_C0_ADDENDUM.md)
- **C0 research card：** [C0_RESEARCH_CARD.md](reports/alpha_jungle_c0/C0_RESEARCH_CARD.md)
- **C0 final test report：** [FINAL_TEST_REPORT.md](reports/alpha_jungle_c0/FINAL_TEST_REPORT.md)

建议首次阅读从最终报告开始；需要核对具体设计、数值、证据身份或停止原因时，再进入相应历史档案与 Robinhood RQ2 目录。README 只提供入口，不替代冻结报告。
