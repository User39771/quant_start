# Quant Start Research Project v1.0 Final Report

## Executive Summary

Quant Start 项目起始于一个朴素但真实的研究动机：从人工智能与商业航天等主题股票出发，把经验判断和市场观察转化为可以计算、比较和检验的量化问题。早期工作集中在动量、低波动、流动性与主题广度等常见想法上，研究方式也带有明显的探索色彩——先寻找一个看起来有经济含义的 pattern，再检查它在历史样本中是否稳定。随着实验推进，项目逐渐认识到，量化研究的困难并不只是写出因子公式，而是明确研究总体、时间信息集、measurement、比较基准、样本排除规则和结果的证据身份。

项目的 A 股主线使用最终冻结的 56 只主题股票研究池。这个研究池经历了从概念板块候选、业务相关性证据整理到有记录的人工判断和版本冻结的过程，但仍主要是基于当前概念归属构造的历史研究总体，而不是完整的历史 point-in-time 主题成分回测。因此，H1–H8 的大部分结果都属于 `historical_seen`：它们可以支持描述、诊断和方法比较，却不能被包装成独立样本外验证。调整价格谱系、ST/停牌/涨跌停状态、可成交性和容量等方面也仍有边界。

早期 H1–H4 给出了清楚但并不整齐的结果。正向 MOM60 假设未获支持，MOM40、MOM60 与 MOM80 的方向均为负，但这并不自动证明反转因子成立。LOWVOL20 显示出方向一致的排序和风险信息：低波动组合风险较低，但收益存在温和牺牲，历史区间也跨越零，因此只能称为有边界的方向性支持，而不是成功的 Alpha 策略。固定的流动性中位数过滤没有改善比较结果，反而伴随更高换手和更差累计收益表现；主题 Breadth60 则是 mixed 的市场状态诊断，没有进入后续择时或配置阶段。

H5–H8 标志着研究方式的实质变化。H5 从文献启发的交易活动状态出发，发现稳定的历史 pattern，但进一步 measurement 检查显示原始成交额混合了规模和其他暴露；固定 turnover-like 代理保留方向，却使幅度大幅衰减。H6 使用个股自身历史中的异常活动，得到较清楚的负向 HIGH_SHOCK−LOW_SHOCK 关联，尤其集中在过去赢家组，但机制仍不能由相关结构单独识别。H7 引入 point-in-time 总股本分母和动态收益—活动模型，发现较高相对换手通常削弱延续，却通常不足以造成直接反转，且规模方向并未干净支持来源论文机制。H8 进一步采用外部给定、可证伪的预测做 adapted replication：总体符号预测未复制，时间结构预测则方向一致，最终结论必须保持 mixed / partial replication。

Robinhood Chain 是独立的新市场研究分支，而不是 H9。其核心 RQ2 检查 Stock Token 在传统市场 20:00–04:00 ET 间隙中的价格变化，是否在 16:00–20:00 传统盘后变动之外，对随后股票开盘含有增量信息。设计状态为 `PILOT_INFORMED_PROSPECTIVE_EXTENSION`；已披露的 NVDA discovery 样本没有进入 Primary 推断。冻结的 43 行 prospective-extension 样本产生正向但不确定的 token 系数 0.304048，HC3 标准误 0.286911，95% 区间为 [-0.276773, 0.884869]。后续诊断显示结果不是由单个 session 驱动，但明显依赖资产构成与 NVDA；流动性不能干净解释该异质性；严格 premarket QA 又造成严重的资产偏斜流失，使原始跨资产 timing 问题无法识别。共同样本 5m/30m 比较保留了正方向，但幅度和增量拟合明显衰减。

项目最终没有形成经过充分验证、可以声称具有实际交易价值的策略成果。这一结论既不是把整个项目判为失败，也不等于已观察到的 empirical patterns 没有研究价值。更准确的评价是：项目留下了一组边界明确的历史事实、若干未解决的机制问题，以及一套逐步形成的研究纪律。对于一个从本科一年级开始的量化入门与科研训练项目，最重要的变化不是找到更多“好看的”结果，而是学会提出可检验问题、构造可审计数据、区分 measurement 与 mechanism、保存负面与 mixed 证据，并让结论的强度服从证据身份。

v1.0 的 evidence governance 立场因此是：冻结已完成问题的设计、样本、分类和解释边界；保留探索发现，但不让它们倒写既有 claim；把真正的新问题放进新的证据周期。详细事实分别保存在[早期 H1–H4 研究史](EARLY_RESEARCH_HISTORY_H1_H4.md)、[H5–H8 研究史](H5_H8_RESEARCH_HISTORY.md)和[研究方法论经验](RESEARCH_METHODOLOGY_LESSONS.md)中。本报告只做综合，不替代这些可追溯档案。

## 1. Project Origin and Scope

项目最初选择人工智能与商业航天主题作为研究入口，并围绕主题股票开展经验与观察驱动的因子实验。早期本地记录能够确认主题、股票池和实验顺序，却不足以重建当时选择这两个主题的完整经济论证；因此应明确保留一句边界说明：**原始主题选择的完整经济动机未在早期本地档案中被完整记录。** 本报告不以事后叙事填补这一缺口。

项目的预期角色是量化研究入门：从可获得的公开数据和有限股票池开始，练习把直觉变成变量，把变量变成冻结比较，再把结果写成可审查的结论。研究重点逐渐从“某个因子历史上是否表现不错”转向四个更基础的问题：研究总体究竟是谁，变量在当时是否可知，measurement 是否与经济概念一致，以及现有证据最多允许说到哪里。

这一范围同时决定了 v1.0 的边界。A 股部分大多是在反复查看过的历史数据上完成的 current-universe research，不是历史逐期可知的主题成分回测；`historical_seen` 不等于独立 OOS。多数结果属于描述性事实、measurement 检查或 mechanism diagnostic。执行成本只在部分比较中以简化方式处理，容量、冲击成本、涨跌停与停牌下的真实成交约束并未系统完成。由此，v1.0 不作最终交易价值判断，也不声称已经识别一组稳定的经济机制。

## 2. Building the Research Foundation

### 2.1 Thematic universe

研究总体最初来自 Eastmoney 七个概念板块，共形成 1,225 条候选概念归属记录。项目随后认识到，“数据库把公司放进某个概念板块”与“公司业务对该主题具有足够 materiality”不是同一个判断，于是把自动生成的候选归属、业务相关性证据和人工复核分开保存。v1、v1.1 与 v1.2 版本共保留了 113 条代码—主题记录；在 v1.2 中，1 条属于 default、56 条进入 expanded、56 条被排除，最终冻结为 56 只唯一股票的研究池。

人工判断在这里不是应当消除的“主观污染”，而是需要被约束和记录的研究环节。合理做法是：先保存候选来源，再整理业务证据，由人依据有记录的业务证据与 materiality 判断标准作出决定，并在接触相应结果前冻结版本。现有研究池做到了版本化与证据分层，但概念归属主要来自当前快照，因此不能把它描述为每一个历史日期都可知的主题总体。

### 2.2 Data layer and adjusted-return baseline

项目采用公开数据策略，建立了日频价格、成交额、基准和交易日历的基础层。价格处理中区分 raw 与前复权（qfq）：因子和持有期收益可使用与研究目标相符的 qfq 序列，而成交额、换手分母和公司行为相关变量不能因为方便就沿用同一种处理。研究使用 CSI 300 交易日历定义固定 20 交易日期间，不对缺失价格随意填充；常用比较基准包括 000300、000852 与 399006，并在需要时显式记录 0、10bp、20bp 等成本情景。

固定期间结构减少了不同实验间的日期漂移，也让 H1–H8 的顺序更可审查。更重要的是，缺失值被视为 measurement 状态，而非等待补齐的空格：无法满足所需观测长度、可靠性或时间可知性时，样本应被排除或标记，而不是用临近值、未来信息或任意插值制造完整面板。

### 2.3 What was already known to be imperfect

基础层仍有三类已知不完美。第一，股票池是当前主题快照的历史回填，存在 survivorship 与 membership timing 问题。第二，ST、停牌、涨跌停、退市与实际可买卖状态没有被完整地逐日 point-in-time 重建；在这些约束市场中，显示价格可能存在，但变量未必能按研究所需的经济含义被可靠解释。第三，qfq 数据依赖外部调整链路，虽适合部分历史收益比较，却不等同于完整、可独立审计的公司行为谱系。

因此，基础设施的作用不是让历史结果自动获得更高证据等级，而是让这些限制可见、可重复并尽量不随结果变化。详细形成过程见[早期研究史第 1–2 节](EARLY_RESEARCH_HISTORY_H1_H4.md)。

## 3. Early Factor Research: H1–H4

| Stage | Question | Main result | Evidence identity | Why the project moved on |
|---|---|---|---|---|
| H1 — MOM60 | 过去 60 日强势股是否继续领先 | MOM40/60/80 均呈负向；正向动量 `not_supported` | current-universe、`historical_seen` | 注册方向未获支持，不能把符号翻转直接当成新结论 |
| H2 — LOWVOL20 | 可靠测得的低波动是否含排序与风险信息 | 方向性排序与降风险证据，但伴随温和收益牺牲 | `historical_seen`；后有冻结原型与 append 协议 | 支持有限，需要新数据周期，不能视为已确认 Alpha |
| H3 — Liquidity Filter | 固定可实施性过滤能否改善组合比较 | 更高换手、较差累计收益表现；`not_supported` | 固定规则的历史诊断 | 不再搜索阈值，避免结果导向优化 |
| H4 — Breadth60 | 主题内部广度是否是稳定市场状态变量 | 核心相关关系较弱且 mixed | 描述性状态诊断 | 未满足进入 H4B 择时/配置阶段的冻结标准 |

### H1 — MOM60

H1 注册的是正向动量问题：按过去 60 日收益排序后，高动量股票是否在下一期继续领先。主样本包含 54 个期间，平均 RankIC 为 -0.09191，Q5−Q1 为 -0.02042；作为历史检查的 23 个期间同样为负，RankIC 为 -0.12645，Q5−Q1 为 -0.03689。MOM40、MOM60 和 MOM80 的方向一致为负，因此对注册的正向动量方向给出 `not_supported`。

符号为负并不自动建立 REV60。反转需要自己的经济问题、变量方向、比较家族与停止规则；在看见动量结果后把因子乘以 -1，只能说明同一信息被重新定向，不能制造独立证据。H1 的价值在于第一次把“假设未获支持”保留为正式结果。

### H2 — LOWVOL20

H2 对 measurement 的要求更严格：每个截面需要恰好 21 个 qfq 收盘价形成 20 个收益，`LOWVOL20 = -VOL20`；可靠性还要求至少 3 个不同收盘价、至少 5 个非零收益，且最长连续零收益不超过 5 日。最终冻结比较覆盖 57 个期间。锁定网格的平均 RankIC 为 0.08763，波动持续性为 0.43706；历史描述性检查的平均 RankIC 为 0.08274，Q5−Q1 为 0.01951，但区间跨越零。

结果更清楚地支持风险维度：低波动 Q5 的组合波动约 0.323，低于 Q1 的 0.465；端点回撤约 -0.326，也小于 Q1 的 -0.482。然而 Q5 平均收益 0.0172 略低于研究总体的 0.0197，零成本累计财富也低于总体。因而准确结论是“LOWVOL20 含有方向一致的风险排序信息，并可能以温和收益牺牲为代价”，而不是“低波策略获得成功 Alpha”。后续冻结的 long-only prototype、维护和 prospective append 协议只是把既有规则变成可继续观察的对象，不等于已经完成正式确认。

### H3 — Liquidity Filter

H3 首先是可实施性与过滤诊断，不是独立的流动性收益因子。冻结规则使用严格为正的过去 20 日成交额，在每个截面保留不低于中位数的股票，目标覆盖率为 90%，比较期间为 1–56，并在 0、10bp、20bp 成本下评估。

固定过滤后的等权组合累计收益在三种成本下约为 0.374、0.358、0.343，明显低于未过滤组合的 1.187、1.180、1.173；平均换手约 0.207，也高于未过滤的 0.059。该规则因此为 `not_supported`。项目没有在看到结果后继续搜索更有利的分位数或阈值，这一点比找到一个事后漂亮阈值更重要。

### H4 — Theme Breadth60

H4 把 Breadth60 定义为主题内高于自身 60 日均线的股票比例，并分别观察总体、AI 与商业航天主题，共有 51 个有效期间。冻结稳定性规则要求相关方向和强度达到预定门槛。核心结果中，Breadth 与下一期收益相关约 -0.163，与回撤幅度相关约 +0.160，整体较弱且含义不一致；因此分类为 `mixed`。

次要分析中 Breadth 与 LOWVOL 相对表现相关约 0.352，但 secondary pattern 不能反过来提升核心假设。H4 没有进入 H4B 的择时或配置阶段。它留下的是一个有边界的市场状态诊断，而不是主题仓位开关。

## 4. Transition to Literature-Driven Research

H1 不支持、H2 只有有限方向性支持、H3 不支持、H4 mixed，使项目无法再沿用“换一个常见因子继续看”的逻辑。与此同时，同一历史区间已经被多次查看；即使把日期切成所谓 validation 段，也不能消除研究者已经知道结果、变量和异常的事实。由此产生的关键术语是 `historical_seen`：它承认历史研究可以严谨，却不把反复使用过的数据称为 clean retrospective validation。

转型首先发生在程序上。文献 reconnaissance 不再只是寻找一个可复制的结论，而用于提出更具体的 measurement 问题；每一阶段冻结自己的变量、比较组、稳健性家族和停止条件。H5 后的 size/volatility 检查被标记为 post-outcome diagnostic，而不是悄悄并入 H5 Primary；H5B、H6、H7 和 H8 各自建立新的设计周期。measurement contract 规定数据怎样映射到经济概念，机制诊断则明确哪些模式仍可能有多种解释。

这种转型没有把旧历史数据变成 prospective 数据。它改善的是 researcher degrees of freedom 的管理和结论可审计性，而不是凭流程标签升级证据身份。真正的进步是能够区分：冻结问题的回答、看到结果后的解释性检查，以及需要未来数据或新设计的新问题。

## 5. H5–H8: Measurement, Phenomenon, Mechanism, Replication

| Stage | Methodological change | Main empirical result | What remained unresolved |
|---|---|---|---|
| H5 | 文献启发状态分组；随后冻结 turnover-like proxy | 原始成交额状态差异稳定，代理下方向多保留但幅度严重衰减 | 规模、波动与多重暴露污染；原解释不稳固 |
| H6 | 以个股自身历史定义异常活动 | HIGH_SHOCK−LOW_SHOCK 为负，过去赢家组更明显 | 形成期趋势与活动冲击难以完全分离，机制未识别 |
| H7 | point-in-time 总股本分母；动态收益—活动模型 | C2 多为负；高活动削弱延续但通常不造成反转 | 来源论文的机制，尤其规模含义，未获干净支持 |
| H8 | 外部给定的可证伪预测；stock-level adapted replication | P1 未复制，P2 时间结构方向一致 | 整体只能是 mixed / partial replication |

### H5 — 稳定 pattern 与不稳定解释

H5 受交易活动与收益状态文献启发，但不是来源论文的精确复制。H5A 用 RETURN60 与 AMOUNT_MEAN_20 构造状态，在 20、60、120 日路径上比较后续表现。六个 LOW/HIGH_RETURN 活动—期限对比均通过冻结稳定性规则；在 HIGH_RETURN 中，高活动减低活动的差异依次约为 -0.0206、-0.0560、-0.0967，看起来像一个随期限累积的稳定历史 pattern。

问题在于原始成交额并非纯粹交易活动。活动分位与对数市值的平均 Spearman 相关约 +0.664，与 VOL20 约 +0.436；按规模分层后，原差异仅保留约 47.4% 的幅度。H5B 因而单独冻结 `mean(amount/marketcap)` 的 20 日 proxy，不允许在看到结果后进行代理竞赛。方向在 9 个比较中有 7 个一致，但 HIGH_RETURN 的三段差异只剩 -0.00285、-0.00978、-0.01791，约为 H5A 幅度的 13.9%、17.5% 与 18.5%，且六个 90% 区间都包含零。与此同时，proxy 与规模相关转为 -0.267，与波动相关升至 +0.671。

H5 的结论不是原发现被“证明”或“推翻”，而是稳定的结果未必对应正确的解释。改用一个更接近 turnover 的固定代理后，方向大体存在，幅度却大幅缩小，而且新的 proxy 又带来其他暴露。

### H6 — 自身历史异常活动与机制边界

H6 不再按横截面绝对活动水平分组，而用 50 日个股自身历史的成交额 rank 定义异常活动，Primary 使用第 3–56 期共 54 个期间和 20 日后续收益。LOW、MID、HIGH 过去收益组的 HIGH_SHOCK−LOW_SHOCK 20 日差异分别约为 -0.00873、-0.00800、-0.02378，三个 90% 区间均低于零；负向关联在过去赢家组最强，市场标准化后方向仍保留。

这种 measurement 比 H5 更接近“相对自身常态的活动冲击”，但仍不能单独识别经济机制。形成日收益 Middle40 robustness 造成严重样本损失，而 local-trend diagnostic 又显示 HIGH_SHOCK 和 LOW_SHOCK 经常伴随明显的局部活动趋势；在高、低 shock 中达到较强局部相关的比例分别约为 31% 和 44%。因此 formation-day return 与 slow local trend 都仍是未排除的 alternative explanations。可支持的是一个历史经验关联：异常高活动与较弱的后续收益相关，尤其在过去赢家中。不能支持的是活动冲击必然代表某一种投资者行为或信息机制。

### H7 — point-in-time turnover 与动态模型

H7 同时升级分母和模型。turnover 使用 BaoStock 成交量除以 CNINFO 总股本，只有在 `max(change_date, announcement_date)` 之后才可用，不对首次事件前的缺失分母回填；相对 turnover 以过去 200 个活跃观测建立基线。Primary 是 stock-level 动态收益—活动模型，要求至少 750 条有效观测，最终包含 4,470 只股票。

核心交互系数 C2 的均值约 -0.01736，中位数 -0.01781，约 61.7% 为负。更直接的含义是，高相对活动通常削弱延续：在活动水平的低、中、高分位，有效斜率中位数仍分别为正的 0.0561、0.0439、0.0280，正斜率股票占比约为 74.8%、80.1%、71.5%。也就是说，活动上升更多表现为 continuation 变弱，而非普遍跨过零形成 outright reversal。

替代 turnover measurement 与 Primary 的 C2 高度一致：相关约 0.984，符号一致率约 96.9%。但来源论文式规模解释没有被干净支持，规模相关斜率反而为正约 +0.00947。H7 因此在 measurement robustness 上较强，在机制映射上较弱。

### H8 — 可证伪预测与 adapted replication

H8 使用外部提供的明确预测，将研究单位提升到股票层面的 adapted mechanism replication，Primary 有 474 只股票。P1 预测的总体符号没有复制：关键系数中位数为正，目标差异中位数约 +0.000439，只有约 40.9% 股票呈预期负方向。P2 的时间结构则方向一致：overnight 差异约 +0.000815，intraday 约 -0.000340，两者的 timing contrast 约 -0.001055，约 67.9% 股票为负。

P1 与 P2 指向不同，不能以其中一个替代另一个。最终状态必须保持 mixed / partial replication：总体机制符号未复制，但收益在 overnight 与 intraday 之间的相对分布与预测方向一致。H8 也不是精确 replication，因为市场、数据、变量和模型均经过适配。

### 从 measurement 到 replication

H5–H8 的连续性不在于不断追求更显著的结果，而在于问题层级依次提高：

> measurement → empirical phenomenon → economic mechanism → replication

H5 说明原始活动变量测量了什么并不显然；H6 把现象改写为相对自身历史的异常活动；H7 用 point-in-time 分母和动态模型检查机制结构；H8 则要求一个外部理论预测在股票层面经受可证伪的 adapted replication。每一步都缩小了可辩护结论，而不是自动增强原有结论。完整档案见[H5–H8 Research History](H5_H8_RESEARCH_HISTORY.md)。

## 6. Robinhood Chain: Applying the Research Process to a New Market

Robinhood Chain 分支把此前形成的研究纪律应用到一个新的市场结构问题。它独立于 A 股 H1–H8 序列，不应编号为 H9。Primary RQ2 是：**Stock Token 在 20:00–04:00 ET 传统市场间隙中的变化，是否在 16:00–20:00 传统盘后股票变动之外，对随后美国股票开盘含有增量信息？**

### 设计、样本与 Primary

设计状态为 `PILOT_INFORMED_PROSPECTIVE_EXTENSION`。早期已查看的 20 条 NVDA discovery observations 被明确排除在 Primary prospective inference 之外；这使 extension 样本与 discovery 样本隔离，但由于 pilot 信息参与了后续设计，仍不能称为完全 outcome-naive 的 preregistration。Primary 资产为 NVDA、GME 与 COST。价格无关的 robust 候选为 80 行，其中 20 行是 NVDA discovery，60 行为 prospective candidates；股票 QA 后冻结 Primary 为 43 行：NVDA 11、GME 23、COST 9。

Model 1 为：

```text
stock_20_to_open_return
~ asset fixed effects
+ stock_post_return
+ token_deep_return_30m
```

`token_deep_return_30m` 的系数为 0.304048，HC3 标准误 0.286911，95% CI 为 [-0.276773, 0.884869]，p = 0.2960。相对基线模型，ΔR² = 0.0879916，Δ adjusted R² = 0.0748276，partial R² = 0.111195。点估计和增量拟合与“token 含有额外信息”的方向一致，但区间同时容纳实质负值和实质正值，N 也只有 43。冻结结果的准确表述是**正向但不确定的增量关联**；它不是因果 price discovery 证据，不是已证明 Alpha，也不是盈利性证据。设计与结果详见[RQ2 Design Contract](robinhood_chain_pilot/rq2_information_content_design/RQ2_INFORMATION_CONTENT_DESIGN_CONTRACT.md)和[Primary Prospective Results](robinhood_chain_pilot/rq2_information_content_design/RQ2_PRIMARY_PROSPECTIVE_RESULTS.md)。

### E1 — 稳定性与资产构成

E1 的 leave-one-session-out 结果在 43 次删除中全部保持正系数，范围为 0.1857–0.5472，说明 Primary 方向不是由单一 session 独自造成。预先识别的四行 influence stress 也得到正系数 0.2326，但不替代 Primary。

资产删除结果显示更重要的边界：剔除 NVDA 后，系数降至 0.0692，Δ adjusted R² 为 -0.0124，partial R² 为 0.0181；剔除 GME 后系数为 0.6898，剔除 COST 后为 0.3220。因而结果可以称为“不由单一日期驱动”，却明显依赖资产构成，尤其与 NVDA 有关。[E1 summary](robinhood_chain_pilot/rq2_information_content_design/e1_stability_map/e1_stability_summary.md)没有授权删除任何观测或替换 Primary。

### E2 — 流动性与 NVDA 异质性

E2 使用两个 token 边界中较小 quote notional 的对数标准化值检查流动性依赖。NVDA 平均处于较高流动性区间，但与非 NVDA 存在重叠；流动性 interaction 的点估计没有显示流动性越高、token slope 越强。相反，NVDA-specific interaction 较大，但区间宽且包括零；把 NVDA 与流动性 interaction 同时放入模型后，NVDA interaction 并未被流动性解释掉。

因此，[E2 summary](robinhood_chain_pilot/rq2_information_content_design/e2_nvda_identity_vs_liquidity/e2_mechanism_summary.md)的最终状态是 unresolved confounding，点估计更偏向残余 NVDA-specific heterogeneity，但小样本无法干净区分资产身份与市场质量。两种机制均未被证明。

### E3 — QA 后的识别失败

E3 试图把股票 20:00 至开盘的结果拆成 premarket 与最后开盘段，但冻结 QA 只保留 22/43 行。更关键的是，保留样本为 GME 22 行，NVDA 0 行，COST 0 行；21 个排除都源于冻结的 duplicate-trade-ID anomaly review 规则。规则没有在看到流失后被放宽。

这使原本针对 NVDA/GME/COST pooled population 的 temporal-localization 问题失去可比样本：E3 可以描述留下的几乎纯 GME 子样本，却不能解释原始、明显 NVDA-dependent 的 pooled association 在目标资产总体中的时间位置。准确的最终解释是**识别限制**，而不是“证明不存在 coherent mechanism”。没有通过 QA 的 session 仍可能具有任何 temporal pattern，共同隔夜公共信息过程也未被排除。详见[E3 summary](robinhood_chain_pilot/rq2_information_content_design/e3_temporal_localization/e3_temporal_summary.md)。

### 强制共同样本 5m/30m sensitivity

预先要求的共同样本 sensitivity 最终在全部 43 行上完成；30m 与严格 5m 均有效，因此差异不来自样本构成。两个 predictor 的 Pearson 相关为 0.958357，Spearman 为 0.912111，符号一致 39/43。30m beta 为 0.304048，5m beta 为 0.221986；partial R² 分别为 0.111195 和 0.084218。

冻结分类为 **same direction, material attenuation**：严格 estimator 改变后方向保留，但 beta 约下降 27%，增量拟合也下降约四分之一。它既没有推翻 30m Primary，也限制了对关系幅度的信心。历史关闭审计在 2026-09-21 00:41 尚把该项列为唯一未完成的 mandatory sensitivity；[共同样本 sensitivity](robinhood_chain_pilot/rq2_information_content_design/common_5m_vs_30m/common_5m_vs_30m_summary.md)于随后完成并记录 `MANDATORY_COMMON_SESSION_SENSITIVITY_COMPLETED`，因此两份记录反映的是先后状态，而非矛盾。

### RQ2 最终位置

RQ2 留下的是有边界的正向方向性证据，同时伴随四个不可省略的限制：样本小、资产异质性明显、估计幅度对 measurement 敏感、机制未解决。它完成了冻结 Primary 和唯一 mandatory sensitivity；E1–E3 是有标签的 post-outcome diagnostics，不能改写 Primary 身份。该分支不支持任何交易价值结论。

## 7. Main Empirical Findings

### 7.1 Bounded supported / directionally supported patterns

LOWVOL20 在历史样本中提供了方向一致的排序与风险信息，最有力的部分是较低组合波动与较浅回撤，而不是更高累计收益。H5A 的活动状态差异在多个期限上稳定，但 H5B 显示其幅度高度依赖 measurement，因此“pattern 稳定”只能在原变量定义内成立。H6 的 own-history abnormal activity 与较弱后续收益呈稳定负向关联，过去赢家组更明显；这是历史关联，不是行为机制确认。H7 则较稳健地显示，高相对 turnover 会削弱收益延续，但通常不会使有效斜率转为全面反转。

这些结果的共同点是：每一项只支持被实际测量的方向或结构。它们没有共同构成一个可直接组合的策略，也没有经过统一 prospective 交易验证。

### 7.2 Mixed evidence

H4 的 Breadth60 核心结果较弱且方向含义不一致，属于 mixed 的状态诊断。H8 中 P1 总体符号未复制，而 P2 timing structure 方向一致，属于 mixed / partial replication。Robinhood RQ2 的 Primary 点估计为正、共同样本 estimator 改变后方向仍正，但区间宽、资产组成敏感、幅度衰减且机制未识别，同样是 mixed evidence，而非简单的“成功”或“失败”。

### 7.3 Unsupported hypotheses

H1 的正向 MOM60 注册方向没有得到支持；负结果也没有自动授权 REV60。H3 的固定 20 日成交额中位数过滤没有改善既定组合比较，并产生更高换手与更差累计收益表现，因此该具体规则为 `not_supported`。`not_supported` 指向被检验的方向或规则，不代表数据“失败”，也不排除未来完全不同设计下的其他问题。

### 7.4 Identification failures / unresolved mechanisms

current-universe 历史回填无法识别逐期真实主题成员；H6 无法在现有设计中把异常活动与所有形成期趋势解释分离；H7 的规模结果没有干净映射到来源机制；Robinhood E3 的严重、资产偏斜 QA 流失使 pooled temporal-localization 问题无法识别。执行与容量资料不完整，也阻止了从历史 pattern 到可交易收益的推断。

因此，“unsupported”“mixed”和“unidentified”是三种不同科学结果。前者回答一个冻结方向未获支持；第二种要求同时保留正反证据；第三种说明有效样本或设计无法回答原问题。把三者都写成“效果不好”会丢失最重要的信息。

## 8. Methodological Lessons

### 8.1 Universe construction is part of the hypothesis

研究总体不是回测之前的行政准备，而是假设的一部分。概念标签、业务 materiality 和历史可知性应分别处理。项目采用生成候选、整理证据、记录人工判断和冻结版本的分层方式；其中人工判断可以是合法且必要的，只要它 evidence-informed、有记录，并在相应结果之前完成。

### 8.2 Point-in-time correctness is part of measurement design

变量不仅要说明“怎样计算”，还要说明“何时可知”。H7 的总股本分母只有在变更与公告信息可用后才能进入计算；首次有效记录之前的缺失保留为空，比无依据回填更诚实。价格也不存在对所有问题通用的 raw/qfq 选择：收益连续性、实际交易价格和公司行为问题需要不同基础。

### 8.3 Liquidity, market constraints, and observability

缺失、低成交与市场约束不仅是清洗麻烦，也可能说明经济变量无法按研究所需含义可靠解释。涨跌停情形下屏幕价格并非“不可观察”，但可成交性、价格发现和收益实现可能与普通 session 不同。项目采用明确过滤、保留失败原因和不作临时修补的原则，同时承认严格过滤会改变研究总体。

### 8.4 Label blindness and sample isolation

predictor 的生成、QA 和 eligibility 应尽可能与 outcome 隔离。Robinhood 分支将 discovery NVDA 与 prospective extension 分开，用价格无关 manifest 冻结候选行，再获取股票 outcome。隔离降低了 outcome-driven sample selection 风险，但 pilot 已参与设计，因此证据身份仍是 `PILOT_INFORMED_PROSPECTIVE_EXTENSION`，不是完全 preregistered confirmation。

### 8.5 QA as research design

QA 规则通过“规则 → 保留样本 → estimand”链条改变研究问题。E3 严格执行 duplicate-ID anomaly rule 后只剩 GME，说明 QA 并非中性的技术门槛：正确执行规则可能让问题变成 unidentified。面对这种情况，科学做法不是放宽规则换取答案，而是保留流失结构并缩小结论。

### 8.6 Research governance: separating frozen claims, exploration, and new questions

冻结或 precommitted claim、post-outcome diagnostic 与新研究周期必须分层。H5A 后的污染检查属于诊断，H5B 才是新的冻结 measurement；Robinhood Primary 完成后，E1–E3 也不能替代 Primary。历史数据已见时，宜使用“frozen / precommitted claim”，避免用“confirmatory”夸大证据身份。

研究纪律不是禁止好奇，而是防止好奇在事后改变同一个 claim。项目最终采用的原则是：**“Freeze the claim, not the curiosity.”** 完整方法论及案例矩阵见[Research Methodology Lessons](RESEARCH_METHODOLOGY_LESSONS.md)。

## 9. What Failed, and Why It Matters

项目的若干早期简化没有经受住后续检查。概念板块标签不能代替业务 materiality；即使经过人工复核，当前股票池也不等于历史 point-in-time membership。原始 amount activity 混合规模、波动和其他 exposures；换成更接近 turnover 的代理后，H5 幅度显著衰减。H6 和 H7 都说明，measurement 更贴近概念并不会自动识别机制。

经验假设也没有整齐地朝“有效策略”收敛。H1 正向动量未获支持；H3 的固定流动性过滤没有改善比较；H4 breadth mixed；H8 两个可证伪预测互相不完全一致。Robinhood E3 在严格 QA 下失去跨资产识别能力，Primary 则在 N=43 中表现出大区间和资产构成敏感性。这些结果如果被删除，项目叙事会更顺滑，但研究记录会更不真实。

保留失败与限制的意义在于，它们直接改变了后续方法。概念标签问题促成 universe 分层；H1 阻止了符号翻转式“发现”；H3 固定阈值的负结果强化了停止规则；H5 的污染促成更严格 measurement；E3 的流失让 QA 与 estimand 的关系变得具体。负面结果没有让原假设成功，却减少了下一轮中可重复犯的错误。

这也说明为什么“没有找到充分验证的策略”不等于“项目没有产出”。v1.0 的主要产出不是一条可交易信号，而是对哪些说法不成立、哪些只能有限成立、哪些根本没有被现有设计识别的清楚划分。

## 10. Reproducibility and Research Artifacts

项目为关键研究对象保留了版本化 universe、冻结数据或 manifest、设计合同、变量字典、确定性 QA 和归档报告。自动生成的数据与人工业务证据分开；在适用环节，冻结文件采用 append-only 或明确 supersede 的方式，避免未来更新静默改写历史。Robinhood 分支进一步把 price-free eligibility、stock-data QA、分析面板和结果阶段分离，使 outcome 获取与样本资格之间存在可审查边界。

本报告不是脚本清单。复现和审计应从三份主档案进入：[H1–H4 与前期基础](EARLY_RESEARCH_HISTORY_H1_H4.md)、[H5–H8](H5_H8_RESEARCH_HISTORY.md)、[方法论经验](RESEARCH_METHODOLOGY_LESSONS.md)。Robinhood 的主要入口是[设计合同](robinhood_chain_pilot/rq2_information_content_design/RQ2_INFORMATION_CONTENT_DESIGN_CONTRACT.md)、[Primary 结果](robinhood_chain_pilot/rq2_information_content_design/RQ2_PRIMARY_PROSPECTIVE_RESULTS.md)、[E1](robinhood_chain_pilot/rq2_information_content_design/e1_stability_map/e1_stability_summary.md)、[E2](robinhood_chain_pilot/rq2_information_content_design/e2_nvda_identity_vs_liquidity/e2_mechanism_summary.md)、[E3](robinhood_chain_pilot/rq2_information_content_design/e3_temporal_localization/e3_temporal_summary.md)与[共同样本 sensitivity](robinhood_chain_pilot/rq2_information_content_design/common_5m_vs_30m/common_5m_vs_30m_summary.md)。

可复现性在这里意味着：给定同一冻结输入、规则和环境，可以追踪得到同一输出，并知道哪些人工决定参与其中。它不意味着数据源永远不变，也不把复现成功等同于经济结论正确。

## 11. Limitations

### 11.1 Data limitations

项目主要依赖公开和第三方市场数据。qfq 调整链路、总股本事件、交易 condition、extended-hours executions 等变量的质量取决于来源覆盖和字段含义。部分环节虽有确定性 QA，却无法证明所有上游修订、取消记录或公司行为都被完整恢复。数据完整不等于经济 measurement 无误。

### 11.2 Point-in-time / survivorship limitations

A 股 56 股票研究池主要反映当前主题认定后对历史数据的回填，不是逐期冻结的历史主题成员。公司存续、数据库覆盖和当前可见性可能影响样本。H7 对总股本执行了更严格的 point-in-time 规则，但这种改进不能 retroactively 修复所有早期研究。

### 11.3 Statistical limitations

H1–H8 在同一历史总体上经历多轮研究，存在 repeated inspection、multiple comparisons 和小截面问题；`historical_seen` 结果不能视为独立验证。若干区间跨零，分组结果可能受极端值与样本构成影响。Robinhood Primary 只有 43 行，HC3 区间宽，资产层面仅三组，interaction 和 leave-one-asset 结果都具有较大不确定性。

### 11.4 Identification limitations

相关与排序不能自动识别因果。H5 的活动变量包含多重暴露，H6 的异常活动与形成期趋势仍可能纠缠，H7 的动态系数不能单独证明来源论文的投资者行为机制，H8 只是 adapted replication。Robinhood E2 无法区分 NVDA identity 与 liquidity，E3 又因 asset-skewed attrition 无法回答原 pooled timing 问题。共同公共信息也可能同时驱动 token 与股票价格。

### 11.5 External-validity limitations

结论来自特定中国主题股票池、特定历史区间和一个短期的 Robinhood Chain 资产样本。主题、监管、交易机制、流动性和参与者结构变化后，方向与幅度都可能不同。H5–H8 对来源文献的应用经过市场与变量适配，不能代表原论文在其他市场被精确重复。

### 11.6 Execution / trading limitations

项目没有完成系统的容量、冲击成本、涨跌停成交概率、延迟、滑点和真实订单执行研究。H3 仅是固定过滤与简化成本比较，Robinhood RQ2 也研究信息关联而非可执行套利。LOWVOL20 prototype 与维护状态不等于 live trading validation。最终状态是：实践交易价值**尚未被充分建立**；不能进一步说所有 pattern 都“没有交易价值”，因为项目并未完成足以支持那一否定结论的执行研究。

## 12. Final Assessment

Quant Start v1.0 没有建立一套经过充分验证、可声称具有可交易 Alpha 的策略。它也没有证明低波动、活动冲击、相对 turnover 或 Stock Token 信息对应唯一经济机制。若以“是否产出可交易策略”为唯一标准，项目没有达到该目标；但这种单一标准会忽略项目实际完成的研究工作。

项目确实形成了一组有限且边界明确的 empirical findings：LOWVOL20 的风险导向排序信息，H5 在 measurement 改变下显著衰减的活动状态 pattern，H6 的异常活动负向关联，H7 的高 turnover 弱化延续结构，H8 的 mixed replication，以及 Robinhood RQ2 正向但不确定、异质且 measurement-sensitive 的增量关联。这些发现不能被简单相加，也不能直接转化为交易建议，但它们可被追踪、质疑和继续检验。

更持久的成果是一套逐步严谨的量化研究流程：把 universe 当作假设，把 point-in-time 当作 measurement 条件，把 QA 当作 estimand 的组成部分，把 discovery 与 prospective extension 分开，并用 evidence governance 约束事后解释。项目最大的改变，是从“哪一个历史 pattern 看起来不错？”转向“究竟测量了什么、当时能够知道什么、证据属于什么身份、现有结果实际允许什么结论？”

作为研究者本科一年级开始的量化入门与科研训练，项目提供了实质性的学习过程，但不意味着已经达到专业研究 mastery。它训练的核心能力是：在结果为负、mixed 或 unidentified 时仍保存结论，承认设计边界，并把下一步好奇心与既有 claim 分开。这比用同一历史数据不断寻找更好看的 specification 更接近可持续的研究实践。

## 13. Freeze Status and Reopening Rules

本报告将 v1.0 视为一次历史研究冻结。H1–H8 的支持分类、Robinhood Primary 与 mandatory 5m/30m sensitivity，以及相应证据身份和解释边界，应按现有档案保存，不因未来出现新想法而被静默改写。

冻结的 v1.0 claim 只在以下情况重新打开：

1. 发现可复现性或实现 bug，且足以改变既有结果；
2. 发现事实性归档错误，例如样本数、变量定义、时间顺序或数值记录错误；
3. Mentor 提出需要实质修正的反馈。

文字清晰度、链接和不改变含义的舍入修订可以形成勘误记录。若问题本身、样本、measurement 或解释目标发生实质变化，则应建立新研究、开启新的 evidence cycle，或发布后续项目版本，而不是回写 v1.0 的历史。

**Freeze the claim, not the curiosity.**
