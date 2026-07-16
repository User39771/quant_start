# Stock Pool v1 QA Report

Generated at: 2026-07-02T21:57:02

## Scope
- theme_stock_research_scorecard.csv rows: 113
- Output rows: 113
- Note: user requested full_119 naming; current input file contains 113 code/theme rows, so outputs cover 113 rows.

## Stock Pool Rules Applied
- 最低日均成交额: 1亿 (保证基本流动性)
- 最低市值: 30亿 (避免过小盘噪声)
- ST: 一律剔除 (降低退市/流动性风险)
- financial_quality_flag=fail: 剔除 (财务质量不支持)
- valuation=high: 不剔除 (但 manual题材股常高估需结合增长)
- conditional: 不进默认池 (只进扩展研究池)

## Label Distribution
- evidence_strength: {'strong': 113}
- business_evidence_decision: {'theme_confirmed': 113}
- trading_pool_decision: {'default': 1, 'excluded_by_rules': 58, 'expanded': 54}

## Manual Follow-up Needed
- Count: 58
- 000555 神州信息 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 000561 烽火电子 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 000818 航锦科技 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 000938 紫光股份 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 001270 铖昌科技 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 001339 智微智能 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 001388 信通电子 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002151 北斗星通 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002197 证通电子 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002229 鸿博股份 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002313 日海智能 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002354 天娱数科 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002413 雷科防务 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002413 雷科防务 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002421 达实智能 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002465 海格通信 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002583 海能达 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002649 博彦科技 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002657 中科金财 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002771 真视通 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002829 星网宇达 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002912 中新赛克 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300045 华力创通 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300053 航宇微 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300053 航宇微 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300075 数字政通 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300166 东方国信 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300188 国投智能 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300212 *ST易录 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300229 拓尔思 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300252 金信诺 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300253 卫宁健康 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300342 天银机电 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300364 中文在线 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300366 ST创意 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300366 ST创意 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300418 昆仑万维 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300447 全信股份 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300448 浩云科技 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300451 创业慧康 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300455 航天智装 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300474 景嘉微 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300479 神思电子 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300520 科大国创 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300608 思特奇 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300609 汇纳科技 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300624 万兴科技 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300762 上海瀚讯 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300768 迪普科技 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300781 因赛集团 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300825 阿尔特 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300830 金现代 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300846 首都在线 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300857 协创数据 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300872 天阳科技 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 300965 恒宇信通 商业航天: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 301129 瑞纳智能 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 301159 三维天地 AI: theme_confirmed / excluded_by_rules；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤

## 10 Important Judgment Cases
- 300627 华测导航 商业航天: business=theme_confirmed, trading=default, strength=strong；core 且主题证据确认，基础财务/流动性规则通过
- 000555 神州信息 AI: business=theme_confirmed, trading=excluded_by_rules, strength=strong；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 000561 烽火电子 商业航天: business=theme_confirmed, trading=excluded_by_rules, strength=strong；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 000818 航锦科技 AI: business=theme_confirmed, trading=excluded_by_rules, strength=strong；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 000938 紫光股份 AI: business=theme_confirmed, trading=excluded_by_rules, strength=strong；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 001270 铖昌科技 商业航天: business=theme_confirmed, trading=excluded_by_rules, strength=strong；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 001339 智微智能 AI: business=theme_confirmed, trading=excluded_by_rules, strength=strong；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 001388 信通电子 AI: business=theme_confirmed, trading=excluded_by_rules, strength=strong；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002151 北斗星通 商业航天: business=theme_confirmed, trading=excluded_by_rules, strength=strong；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤
- 002197 证通电子 AI: business=theme_confirmed, trading=excluded_by_rules, strength=strong；主题证据与交易池规则分开判断：主题业务可能成立，但未通过财务质量/流动性/ST/市值成交额过滤

## QA Checks
- Row coverage check: passed
- evidence_url non-empty: passed
- Illegal labels / duplicates / theme-mixing checks: passed
- Report fetch errors: 0
- PDF text extraction failures: 0

## Fetch / Extraction Caveats
- Fetch error examples: none
- Text extraction failure examples: none
- business_evidence_decision is based on official annual-report text extraction by theme-specific keywords.
- trading_pool_decision separately applies stock_pool_rules.csv plus scorecard risk flags; financial failure does not imply business mismatch.

## Validation Errors
- None
