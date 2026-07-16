# Theme Stock Purity Report

theme_concept_constituents.csv is a noisy concept-board snapshot.
Generated constituent rows should not be manually deleted.
Concept exposure is not confirmed business purity.
Broad concepts naturally include loose or surprising constituents.
Manual stock decisions belong in config/theme_stock_overrides.csv.
Review should prioritize high-impact uncertain names, not every constituent.
11-day-old concept data is acceptable for pipeline testing and review queue construction.
11-day-old price data is not acceptable for final mid-frequency trading readiness or live candidate selection.
Before any theme factor, backtest, or live-screening step, refresh concept constituents and price cache.
Outputs remain research-universe inputs, not buy/sell recommendations or alpha proof.

## Run Metadata
- generated_at=2026-06-28T14:39:16.859173+00:00
- input_file=D:\Python_Files\quant_start\data\processed\akshare_concept_validation.csv
- refresh=False
- akshare_cache_status=per_concept
- selected_themes=AI|商业航天
- selected_rings=P0
- default_only=True
- include_conditional=False
- include_p2=False
- include_excluded_for_audit=False
- dry_run=False
- max_concepts=
- purity_rules=D:\Python_Files\quant_start\config\theme_concept_purity_rules.json
- stock_overrides=D:\Python_Files\quant_start\config\theme_stock_overrides.csv
- price_cache_dir=D:\Python_Files\quant_start\data\cache\price
- business_profile=D:\Python_Files\quant_start\data\manual\stock_business_profile.csv
- concept_constituents_asof=2026-06-28
- price_cache_asof=2026-06-16
- price_cache_staleness_days=12
- concept_cache_staleness_days=0

## Summary
- diagnostics_rows=1225
- review_queue_rows=1225

## Purity Buckets
- broad_concept_only=771
- high_confidence=230
- medium_confidence=224

## Encoding Diagnostics
- mojibake_rows=0

## Top Review Queue
- code=000909; name=*ST数源; theme=AI; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=002122; name=ST汇洲; theme=AI; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=002689; name=ST远智; theme=AI; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=002932; name=*ST明德; theme=AI; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=002977; name=*ST天箭; theme=商业航天; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=300096; name=ST易联众; theme=AI; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=300205; name=*ST天喻; theme=AI; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=300211; name=*ST亿通; theme=AI; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=300419; name=ST浩丰; theme=AI; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=300555; name=ST路通; theme=AI; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=600169; name=ST太重; theme=商业航天; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=600476; name=*ST湘邮; theme=AI; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=688053; name=ST思科瑞; theme=商业航天; bucket=broad_concept_only; priority=4; reason=broad_concept_only|single_concept_support|st_name|weak_liquidity
- code=300800; name=力合科技; theme=AI; bucket=broad_concept_only; priority=6; reason=broad_concept_only|single_concept_support|weak_liquidity
- code=301558; name=三态股份; theme=AI; bucket=broad_concept_only; priority=6; reason=broad_concept_only|single_concept_support|weak_liquidity
- code=603258; name=电魂网络; theme=AI; bucket=broad_concept_only; priority=6; reason=broad_concept_only|single_concept_support|weak_liquidity
- code=000821; name=ST京机; theme=AI; bucket=broad_concept_only; priority=6; reason=broad_concept_only|single_concept_support|st_name
- code=000826; name=*ST启环; theme=AI; bucket=broad_concept_only; priority=6; reason=broad_concept_only|single_concept_support|st_name
- code=001368; name=通达创智; theme=AI; bucket=broad_concept_only; priority=6; reason=broad_concept_only|single_concept_support|weak_liquidity
- code=001379; name=腾达科技; theme=商业航天; bucket=broad_concept_only; priority=6; reason=broad_concept_only|single_concept_support|weak_liquidity
