# Quant Start — Mentor Handoff Summary（精简版）

## 1. 项目背景与研究路径

这个项目从 2026 年 6 月开始，定位是本科阶段的量化研究入门与实践训练。开始时，我没有实际股票交易经验，对因子研究、量化研究流程和 AI agent 在量化中的应用也缺乏系统认识。最初先围绕 **AI 与商业航天** 两个主题建立股票池，再从一些较基础、可检验的 hypothesis 入手，熟悉数据、因子评价和研究流程。

在早期交流中，您建议我利用 Codex / Claude Code 等工具承担大量实现工作，把自己的角色更多放在需求设计、review、测试和结果解释上。随着项目推进，我逐渐认识到，AI 能否写出代码不是核心，真正重要的是能否用明确的研究合同、数据检查、QA、单元测试和冻结规则约束实现。

项目大致经历四个阶段：

1. **H1–H4：基础量化探索**  
   围绕 AI / 商业航天主题股票池，依次研究 MOM60、LOWVOL20、liquidity filter 和 Theme Breadth60。
2. **H5–H8：literature-driven research**  
   7 月 25 日沟通后，我开始系统阅读论文并学习研究方法，新的 hypothesis 更明确地对应文献、measurement contract、冻结比较和 stopping rule。
3. **Robinhood Chain RQ2**  
   将此前形成的 research workflow 迁移到美股 stock-token 这一独立新市场问题。
4. **Alpha Jungle C0 capstone**  
   回到您 7 月推荐的 *Navigating the Alpha Jungle*，用 baseline-controlled benchmark 比较 grammar-random、Direct LLM 和 LLM-guided MCTS。

项目最终没有形成可以声称具有实际交易价值的 Alpha 策略。更准确地说，它完成的是一次从“寻找历史 pattern”到“学习如何定义问题、控制 measurement、隔离样本、设置 baseline、冻结 Validation/Test，并接受负面或 mixed 结果”的研究训练。

---

## 2. 我完成了什么

### H1–H4：建立数据与基础研究流程

我逐步完成了公开数据获取、价格处理、交易日历、benchmark、股票池审核与冻结，以及基础因子评价流程。概念板块标签没有直接被当成研究总体，而是进一步区分 concept membership、business materiality 和人工审核。

H1–H4 的结果并不整齐：MOM60 和固定 liquidity filter 未获支持，LOWVOL20 留下有限的方向性 / 风险证据，Theme Breadth60 为 mixed。这个阶段让我第一次认识到：一个因子“算出来了”并不意味着研究成立；universe、point-in-time correctness、missingness 和 QA 本身都是研究设计的一部分。

### H5–H8：从因子测试转向文献驱动研究

7 月 25 日之后，我开始系统做 literature reconnaissance。后续 H5–H8 形成了一条较清楚的方法演进：

> **measurement → empirical phenomenon → economic mechanism → adapted replication**

H5 暴露出 absolute amount activity 与规模、波动等 exposure 混杂的问题；H6 转向相对自身历史的 abnormal activity；H7 引入 point-in-time share denominator 和 stock-level dynamic regression；H8 使用外部论文给出的 sign / timing prediction 做 adapted replication，并将不一致结果保留为 mixed / partial replication。

这一阶段让我开始把“现象是否存在”和“为什么存在”分开处理：更好的 measurement 可以让 empirical relation 更清楚，但不能自动证明经济机制。

### Robinhood Chain：迁移研究流程

我先用 NVDA 做 discovery，再把已查看的 discovery observations 与后续 prospective-extension sample 分开，冻结 eligibility 和 QA 后分析后续 outcome。Primary 最终使用 NVDA、GME、COST 的 43 行样本。

结果是正向但不确定的 incremental association，并且在 stricter 5-minute estimator 下明显衰减，因此没有被解释为 price discovery、Alpha 或套利机会。

### Alpha Jungle C0：完成方法比较

C0 在固定数据、formula grammar、evaluator 和预算下比较：

> **grammar-random vs Direct LLM vs LLM-guided MCTS**

Train、Validation 和 Final Test 被明确分离；Validation 后按冻结规则选择候选，并在访问 Final Test 前锁定。Final Test 只访问一次，禁止 Test-based reselection。

最终 MCTS 没有通过冻结的 Validation advantage rule，但 Direct 与 MCTS 都反复找到了一类 short-horizon price-volume interaction family，因此 C0 被保留为 **MIXED**，而不是包装成“MCTS 成功”。

---

## 3. 三个代表性结果

| 研究 | 关键结果 | 我认为可以支持的结论 |
|---|---|---|
| **H7** | Primary 覆盖 **4,470** 只股票；约 **61.7%** 的 `C2` 为负；两种 turnover measurement 的 `C2` 相关约 **0.984**、符号一致率约 **96.9%** | 较高 relative turnover 通常削弱短期 continuation，但一般不足以形成普遍 reversal；measurement 较稳定，但来源论文的机制解释没有被确认 |
| **Robinhood RQ2** | 冻结样本 **N=43**；30-minute beta = **0.304**，95% CI **[-0.277, 0.885]**；相同 43 行上的 strict 5-minute beta = **0.222**，约低 **27%** | 存在 positive but uncertain、且对 measurement 敏感的增量关联；不能支持 causal price discovery 或 trading alpha |
| **Alpha Jungle C0** | MCTS Validation advantage **FAILED**；Final Test RankIC：Direct **0.0389**、MCTS **0.0417**、ROC20 benchmark **0.0246** | historical benchmark 中保留了一类跨 Train / Validation / Test 为正的 price-volume interaction family，但没有证明 MCTS complexity 相比 Direct LLM 是必要的 |

这三个结果分别代表了我在项目中的三种变化：**measurement 变得更严格、研究流程能够迁移、复杂方法开始必须和简单 baseline 正面竞争。**

---

## 4. 我学到的主要方法论

这几个月对我最大的改变，不是掌握了某个具体因子或代码写法，而是逐渐改变了我对“一个量化结果为什么可信”的理解。

- **数据处理本身就是研究设计的一部分。**  
  Universe、point-in-time correctness、缺失值和 observability 都会改变最终回答的问题，而不只是工程细节。

- **AI 可以降低实现成本，但不能替代研究设计。**  
  我后来更多通过 unit tests、deterministic QA、reconciliation 和 frozen contracts 验证 AI 的实现，而不是试图逐行读完所有代码。一个很直接的经验是：  
  > **Valid computation ≠ valid identification.**

- **负面和 mixed 结果也应该被正式保存。**  
  H1、H3、H8、Robinhood 和 C0 都没有整齐地收敛到“成功策略”，但这些结果本身构成了研究记录的一部分。

- **学会停止强化同一个 claim。**  
  如果看到结果后不断更换窗口、阈值、sample 或 specification，再把更好的结果当作原来的 Primary evidence，研究结论的身份会变得模糊。项目最后采用的原则是：  
  > **Freeze the claim, not the curiosity.**

目前仍需保留明确边界：A 股主线大部分仍是 current-universe historical research；H1–H8 多数属于 historical-seen evidence；Robinhood 只有 43 行且存在 heterogeneity / measurement sensitivity；C0 是 historical benchmark 而非 live OOS；整个项目也没有系统解决 slippage、market impact、fill probability 和 capacity。

因此，我目前不能声称已经发现一套经过充分验证、具有实际交易价值的 Alpha 策略。

---

## 5. 交付物与推荐阅读顺序

如果只希望快速了解这次项目，我建议按以下顺序查看：

1. **`MENTOR_HANDOFF_SUMMARY.md`**  
   本次汇报总览。
2. **`reports/PROJECT_V1_0_FINAL_REPORT.md`**  
   H1–H8 与 Robinhood Chain 的完整项目总结。
3. **`reports/alpha_jungle_c0/C0_RESEARCH_CARD.md`**  
   Alpha Jungle / MCTS capstone 的简短结论。
4. **`reports/H5_H8_RESEARCH_HISTORY.md`**  
   文献驱动阶段的详细研究过程。
5. **`reports/RESEARCH_METHODOLOGY_LESSONS.md`**  
   整个项目最终形成的方法论总结。

补充材料包括 `reports/EARLY_RESEARCH_HISTORY_H1_H4.md`、C0 addendum、Robinhood Primary / sensitivity reports，以及仓库中的 frozen contracts、QA reports、audit artifacts 和中间输出，需要核查具体设计或数字时可以继续追溯。

---

总体上，这次项目没有得到一套可以直接用于实际交易的策略，但形成了一套可以复核的研究记录，也让我从几乎不了解量化研究，逐步走到能够参与问题定义、数据设计、AI-assisted implementation review、Validation/Test 设计和结果解释。现阶段 H1–H8、Robinhood Chain 和 Alpha Jungle C0 都已经收束到明确的停止点，因此我希望以这些材料作为这段项目经历的最终汇报和工作记录。
