# Theme Business Materiality Report

Concept board support is not business materiality.
High-confidence concept support can still be a false positive.
Transition stories are not core exposure unless revenue, order, or product evidence is available.
Manual profile evidence should preferably come from annual reports, interim reports, announcements, exchange replies, or investor relations records.
Cases such as 亿田智能 should be handled through stock_business_profile.csv or theme_stock_overrides.csv.
Outputs are review aids, not recommendations or trading signals.

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
- business_materiality_output=D:\Python_Files\quant_start\data\processed\theme_business_materiality_diagnostics.csv
- high_confidence_mismatch_output=D:\Python_Files\quant_start\data\processed\high_confidence_business_mismatch_queue.csv
- business_profile_template=D:\Python_Files\quant_start\data\manual\stock_business_profile_template.csv

## Summary
- materiality_rows=1225
- high_confidence_mismatch_rows=318
- profile_template_rows=200

## Final Review Suggestions
- review=1225

## Review Status Counts
- unknown=1225

## Theme Revenue Materiality Buckets
- unknown=1225

## High-Confidence Business Mismatch Queue
- code=000063; name=中兴通讯; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=000066; name=中国长城; theme=商业航天; suggestion=review; reason=multi_concept_concept_only
- code=000157; name=中联重科; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=000547; name=航天发展; theme=商业航天; suggestion=review; reason=multi_concept_concept_only
- code=000555; name=神州信息; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=000560; name=我爱我家; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=000561; name=烽火电子; theme=商业航天; suggestion=review; reason=multi_concept_concept_only
- code=000681; name=视觉中国; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=000810; name=创维数字; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=000818; name=航锦科技; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=000818; name=航锦科技; theme=商业航天; suggestion=review; reason=multi_concept_concept_only
- code=000892; name=欢瑞世纪; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=000901; name=航天科技; theme=商业航天; suggestion=review; reason=multi_concept_concept_only
- code=000925; name=众合科技; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=000938; name=紫光股份; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=000977; name=浪潮信息; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=001208; name=华菱线缆; theme=商业航天; suggestion=review; reason=multi_concept_concept_only
- code=001270; name=铖昌科技; theme=商业航天; suggestion=review; reason=multi_concept_concept_only
- code=001339; name=智微智能; theme=AI; suggestion=review; reason=multi_concept_concept_only
- code=001388; name=信通电子; theme=AI; suggestion=review; reason=multi_concept_concept_only
