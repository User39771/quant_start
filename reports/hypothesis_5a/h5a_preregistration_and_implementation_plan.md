# Hypothesis 5A — Trading-Activity State and Reversal-Timing Diagnostic

## 1. Research identity and question

H5A检验：在过去60日收益状态相近的股票中，signal-time amount-based trading-activity state是否对应不同的20D、60D和120D continuation/reversal路径。

本研究来自return × trading-activity文献范式的启发，但不是原论文replication，也不识别因果关系。研究身份固定为：

```text
sample_role=historical_seen
research_type=mechanism_diagnostic
descriptive_only=true
alpha_claim_allowed=false
oos_claim_allowed=false
strategy_claim_allowed=false
universe_point_in_time=false
survivorship_bias_possible=true
```

Primary目标是比较相同past-return state内不同activity state的future-return path，而不是寻找收益最高的cell、投资组合或交易信号。

## 2. Primary universe and periods

Primary使用当前5,195只broader-A current-universe historical backfill。预计5,180只具备canonical Sina QFQ与amount联合数据。不得依据future return、后续ST/退市状态或历史表现事后改变universe。

保留57个locked signal periods。Primary仅纳入 `signal_ready_count >= 1,000` 的56期，即 `period_index=1–56`。

`period_index=0` 只有约68只signal-ready股票，预先标记为 `low_coverage_diagnostic`：保留原始输出，但不进入Primary inference。该排除来自事前横截面数据质量，不依赖future outcome。

## 3. Signal-state contract

### Past-return state

固定使用现有 `RETURN_60`：信号日QFQ close相对沪深300日历上此前第60个市场日QFQ close的收益。不测试其他return窗口。

每期仅在signal-ready broader-A横截面中，先按以下键建立确定性ordinal ordering：

```text
RETURN_60 ascending
stock_code ascending
```

再按人数近似等分为：

```text
LOW_RETURN
MID_RETURN
HIGH_RETURN
```

`stock_code` 是固定tie-breaker。ties不得改变group count，也不得依据future outcome处理。

### Trading-activity state

Primary proxy固定为 `AMOUNT_MEAN_20`，即截至signal date的20个精确沪深300市场日中，正、有限amount观测的算术平均；不允许填充。

`ACTIVITY_PCT` 是当期signal-ready横截面内 `AMOUNT_MEAN_20` 的average percentile rank，只用于报告和解释。Primary state membership不直接按percentile cut point划分，而是先按：

```text
AMOUNT_MEAN_20 ascending
stock_code ascending
```

建立确定性ordinal ordering，再按人数近似等分为：

```text
LOW_ACTIVITY
MID_ACTIVITY
HIGH_ACTIVITY
```

因此，percentile value用于描述，deterministic ordinal assignment用于state membership。该变量必须称为 **amount-based trading-activity proxy**，不得称为turnover或true turnover。它仍混合交易活跃度、股票规模和价格水平；横截面rank不能消除这些经济暴露。

### Primary grid

Primary固定为RETURN state × ACTIVITY state的3×3 grid。不得测试quartile、quintile、decile、自定义threshold或替代Primary的2×2。

## 4. Future-return timing contract

时间顺序固定为：

```text
signal_as_of_date close
    < rebalance_date close = return_start_date
    < endpoint_20d / endpoint_60d / endpoint_120d
```

- state只使用signal date及以前的信息；
- return起点为现有locked `rebalance_date` 的QFQ close；
- endpoint为沪深300市场日历上rebalance date之后第20、60或120个市场日；
- `future_return_h = QFQ_close(endpoint_h) / QFQ_close(rebalance_date) - 1`；
- 起点或端点缺失、非正或非有限时，该stock-horizon outcome无效；
- 不forward fill、backfill或替换价格，也不因outcome缺失改变signal membership。

20D、60D和120D都是从同一rebalance close起算的嵌套累计future returns。

## 5. Outcome aggregation

每个 `period × return_state × activity_state × horizon` 至少输出：

- signal membership count；
- valid outcome count与coverage；
- mean future return；
- median future return；
- IQR。

cell-horizon只有在signal成员不少于25且有效outcome coverage不少于80%时有效。跨期Primary统计采用period-level equal weighting，不将所有股票跨期pooling，也不让横截面较大的period获得更高权重。

Primary horizon contrast至少需要 `45/56` 个有效periods，即不少于80%的Primary periods。

## 6. Continuation-aligned paths and activity contrasts

对LOW_RETURN和HIGH_RETURN定义：

\[
C_h =
\begin{cases}
future\_return_h,& HIGH\_RETURN\\
-future\_return_h,& LOW\_RETURN
\end{cases}
\]

`C_h > 0` 表示过去趋势方向仍在延续；`C_h < 0` 表示相对过去趋势方向已经发生反转。MID_RETURN不使用方向化C，保留原始future return作为activity main-effect diagnostic。

在LOW_RETURN和HIGH_RETURN内分别计算每期activity contrast：

\[
G_{R,h}=C_{R,HIGH\_ACTIVITY,h}-C_{R,LOW\_ACTIVITY,h}
\]

MID_ACTIVITY用于判断LOW/MID/HIGH三档是否有序。

另报告非阻断、非acceptance的描述性interaction contrast：

\[
I_h=G_{HIGH\_RETURN,h}-G_{LOW\_RETURN,h}
\]

`I_h` 只帮助解释activity main effect与return-state dependence，不进入 `H5A_DIAGNOSTICALLY_SUPPORTED` 硬门槛，不产生独立hypothesis，也不触发任何新搜索。

## 7. Coarse reversal-horizon classification

对每个LOW/HIGH return × activity state，以跨期等权cell mean形成的 `C20/C60/C120` 为主，跨期median为补充，按以下顺序分类：

1. `REVERSAL_OBSERVED`：首次出现负C之前均非负，之后均非正；报告first observed reversal horizon。
2. `ATTENUATES`：三个C均非负，随horizon非递增，且至少一次严格下降。
3. `CONTINUATION_PERSISTS`：三个C均为正，但不满足attenuation。
4. `NO_CLEAR_PATH`：重复变号、数据不足、全零或不符合上述有序结构。

这些类别仅是 **coarse state-level path classification**。嵌套累计收益的符号变化只能识别coarse reversal horizon或first observed reversal horizon，不能识别实际反转发生的精确交易日。

例如，若 `C20 > 0, C60 < 0, C120 < 0`，只能表述为：“截至20D仍表现为continuation-aligned positive，截至60D首次观察到累计aligned return转负。”不得称反转发生于20D到60D之间的某个确定时点。

## 8. Statistical and stability evidence

跨期只使用以下描述统计：

- across-period mean和median；
- direction consistency；
- 90% moving-block bootstrap interval；
- leave-one-period-out；
- 固定early/late split；
- cell-size concentration。

### Moving-block bootstrap

block length只由locked calendar和最长预注册horizon决定：

```text
primary_signal_periods=56
adjacent_primary_signal_spacings=55
median_market_day_spacing=20
maximum_horizon_market_days=120
moving_block_length=ceil(120 / 20)=6
bootstrap_repetitions=10000
bootstrap_seed=20260721
```

20D、60D和120D Primary analyses统一使用 `moving_block_length=6`，不按horizon搜索不同block length，也不得依据outcome修改。

90% moving-block bootstrap interval仅作为 **descriptive uncertainty / stability evidence**。它不代表family-wise-error-controlled significance、Alpha significance或OOS significance。本研究不增加Holm、FDR或其他multiple-testing框架，因为Primary states、horizons和contrasts已预注册固定。

### Stability rules

固定early/late split为：

```text
early: period_index=1–28
late:  period_index=29–56
```

某horizon的activity差异仅在以下条件全部满足时称为稳定：

- 至少45/56个有效period contrasts；
- LOW/MID/HIGH activity的跨期mean C按同一方向有序；
- HIGH−LOW的90% moving-block bootstrap interval不含0；
- direction consistency `>=60%`；
- leave-one-period-out至少80%保持全样本方向；
- cell-size QA通过。

同时报告cell count的median、minimum及低于25的period比例，避免把小cell结果解释为稳定机制。

## 9. Final classification

按以下优先顺序判定：

### `H5A_INCONCLUSIVE`

时间合同、state membership冻结或必要QA失败，或任一核心侧无法在至少45/56期形成有效比较。

### `H5A_DIAGNOSTICALLY_SUPPORTED`

LOW_RETURN或HIGH_RETURN至少一侧满足：

- 不少于两个horizons具有同方向的稳定activity差异；
- 三档activity呈有序关系；
- 至少两个activity states的coarse reversal-horizon classification不同。

不要求复制原文献的特定方向，不得因为某个state收益最高而判定supported。

### `H5A_MIXED`

未达到supported，但至少存在一个稳定horizon；或两个以上horizons呈相同有序方向但bootstrap/LOO条件不完整；或主要证据表现为MID_RETURN activity main effect。

### `H5A_NOT_SUPPORTED`

数据和QA充分，但LOW_RETURN与HIGH_RETURN均无稳定horizon、无重复出现的有序path差异，或方向主要由少数period驱动。

MID_RETURN不能单独产生supported。若MID_RETURN中的activity差异也很强，报告必须提示观察结果可能包含activity main effect，而不只是return × activity interaction。

## 10. Secondary theme transfer

AI和商业航天都直接继承每只股票在broader-A Primary中、当期signal-time已经确定的 `RETURN_STATE` 与 `ACTIVITY_STATE`。不得在主题内部重新计算RETURN或activity quantiles。

### AI

对冻结的45只AI股票仅作descriptive transfer，报告：

- period/state成员数；
- state occupancy；
- 20D/60D/120D路径；
- broader-A观察方向在AI样本中是否大致可见。

不构造theme-local 2×2或3×3，不独立进行显著性筛选，也不产生独立classification。

### 商业航天

约12只商业航天股票同样直接映射broader-A state，仅报告：

- 个股state；
- state occupancy；
- 个股及主题描述性路径。

不构造theme-local 2×2或3×3，不进行正式推断。Theme结果不得改变broader-A Primary classification。

## 11. QA and implementation

未来获批后，实施仅新增一个独立runner和一个测试文件：

- `scripts/run_h5a_trading_activity_reversal_timing_v1.py`
- `tests/test_h5a_trading_activity_reversal_timing_v1.py`

计划输出：

- `reports/hypothesis_5a/h5a_period_state_returns.csv`
- `reports/hypothesis_5a/h5a_state_path_summary.csv`
- `reports/hypothesis_5a/h5a_stability_summary.csv`
- `reports/hypothesis_5a/h5a_diagnostic_report.md`

测试必须覆盖：

- stock_code、period keys和locked calendar唯一性；
- period 0固定为low-coverage diagnostic；
- RETURN60与AMOUNT20无look-ahead；
- ordinal tercile assignment、tie-break和人数守恒；
- membership在future outcome读取前冻结；
- rebalance起点及20D/60D/120D endpoint无off-by-one；
- missing endpoint不改变state membership且不填充；
- period-level equal weighting不与stock-level pooling混淆；
- continuation-aligned符号与四类coarse path规则；
- block length 6、10,000 repetitions和fixed seed可复现；
- 45/56、60% direction consistency和80% LOO门槛；
- 四种final categories的合成样本；
- Theme transfer只继承broader-A states且不能改变Primary classification。

## 12. Interpretation limits and human gate

H5A只能称为literature-inspired、D03-informed或conceptual adaptation；不得称为replication、Momentum Life Cycle确认或turnover导致反转的因果证据。

主要限制包括：current-universe survivorship bias、非point-in-time eligibility、historical_seen样本已被其他研究查看、amount proxy混合规模和价格暴露、停牌与端点缺失不插补，以及主题样本统计功效有限。

禁止修改RETURN60、AMOUNT20、3×3 states或三个horizons，禁止搜索threshold、state数量或最好cell，也不运行portfolio/cost optimization、MCTS、Phase B、prospective或final test。

H5A不得自动进入H5B。只有最终为 `H5A_DIAGNOSTICALLY_SUPPORTED`，或出现非常明确、稳定且可解释的 `H5A_MIXED`，并经学生人工审核后，才可另行制定H5B计划。Codex只负责计算、QA和事实报告，不自动生成交易策略。

本计划阶段状态：

```text
code_modified=false
H5A_run=false
state_conditioned_future_performance_viewed=false
MCTS_run=false
Phase_B_run=false
```
