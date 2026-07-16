# A股现金流与主力资金因子可靠性报告

没有生成可检验的因子面板。请先用较小股票池检查 AkShare 数据是否可访问。

## 数据质量提示

- 初始股票池数量：3
- 最终有效股票数：3
- 价格可用率：100.0%
- 价格请求成功率：0.0%
- 资金流最新截面覆盖率：未知
- 最小月度有效股票数：0
- IC 有效期数：0
- 缓存兜底次数：0
- 端点失败记录数：0
- universe_survivorship_status=current_universe_price_history_only
- survivorship_bias_caveat=current universe membership may omit delisted historical stocks; per-date rows require historical price observations but do not fully prove point-in-time listing membership.
- financial_available_date_policy=announce_date_else_report_date_plus_120d
- cashflow_statement_basis=ttm_from_cumulative_quarterly_flows
- sell_side_execution_constraints=same_day_untradable_forced_hold_minimal_model

**样本不足，IC/分组结果不可解释。** 请优先查看 `data/processed/fetch_summary.csv` 和 `fetch_failures.csv`。
