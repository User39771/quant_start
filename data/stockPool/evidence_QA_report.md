# Annual Report Evidence QA Report

Generated at: 2026-07-02T18:23:54

## Scope
- Processed rows: 29
- Core rows: 20
- Manual rows: 9

## Stock Pool Rules Applied
- 最低日均成交额: 1亿 (保证基本流动性)
- 最低市值: 30亿 (避免过小盘噪声)
- ST: 一律剔除 (降低退市/流动性风险)
- financial_quality_flag=fail: 剔除 (财务质量不支持)
- valuation=high: 不剔除 (但 manual题材股常高估需结合增长)
- conditional: 不进默认池 (只进扩展研究池)

## Evidence Strength Distribution
- {'strong': 29}

## Suggested Pool Decision Distribution
- {'default': 1, 'expanded': 7, 'reject': 21}

## Core Stocks Needing Downgrade Or Follow-up
- 000063 中兴通讯 AI: expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 000818 航锦科技 AI: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 000938 紫光股份 AI: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 000977 浪潮信息 AI: expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 001270 铖昌科技 商业航天: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 002151 北斗星通 商业航天: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 002230 科大讯飞 AI: expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 002236 大华股份 AI: expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 002465 海格通信 商业航天: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 002829 星网宇达 商业航天: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 002935 天奥电子 商业航天: expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 300045 华力创通 商业航天: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300053 航宇微 商业航天: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300101 振芯科技 商业航天: expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 300229 拓尔思 AI: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300342 天银机电 商业航天: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300455 航天智装 商业航天: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300474 景嘉微 AI: reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 301050 雷电微力 商业航天: expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional

## Manual Stocks That Can Upgrade To Expanded/Default
- None

## Evidence Insufficient
- None

## Not For Default Pool Under Current Rules
- 000063 中兴通讯 AI: decision=expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 000818 航锦科技 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 000938 紫光股份 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 000977 浪潮信息 AI: decision=expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 001270 铖昌科技 商业航天: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 001388 信通电子 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 002151 北斗星通 商业航天: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 002230 科大讯飞 AI: decision=expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 002236 大华股份 AI: decision=expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 002465 海格通信 商业航天: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 002649 博彦科技 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 002829 星网宇达 商业航天: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 002912 中新赛克 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 002935 天奥电子 商业航天: decision=expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 300045 华力创通 商业航天: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300053 航宇微 商业航天: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300101 振芯科技 商业航天: decision=expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 300229 拓尔思 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300342 天银机电 商业航天: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300447 全信股份 商业航天: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300455 航天智装 商业航天: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300474 景嘉微 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300479 神思电子 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300768 迪普科技 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 300965 恒宇信通 商业航天: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 301050 雷电微力 商业航天: decision=expanded；有年报业务证据但不满足默认池全部严格条件，或当前为 conditional
- 301129 瑞纳智能 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high
- 301159 三维天地 AI: decision=reject；不通过 stock_pool_rules 的 ST/财务质量/流动性/市值成交额基础过滤，或财务风险为 high

## Fetch And Parsing Caveats
- Report fetch errors: 0
- PDF text extraction failures: 0
- Strong/medium/weak/missing are evidence ratings only, not trading opinions.
- If only a title/detail link exists but no extractable PDF text, evidence is treated as missing.
- If annual report text lacks revenue/order/customer/product evidence, evidence_strength is capped by rule.

## Validation
- Validation errors: 0
- None
