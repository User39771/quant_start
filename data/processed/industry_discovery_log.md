# Industry Classification Discovery Log

- status=sw_found_applied
- candidate_tables=10
- implementation_scope=shenwan_l1_market_cap_industry_neutralization

## Schema Candidates

| schema   | table                      | source           |   column_count | matched_columns                                                                                                                                                                                                                                                        |
|:---------|:---------------------------|:-----------------|---------------:|:-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| public   | dim_industry_categories_sw | 申万/Shenwan     |              8 | id,index_code,industry_code,level,industry_name,parent_code,created_at,updated_at                                                                                                                                                                                      |
| public   | map_company_industry_sw    | 申万/Shenwan     |             10 | id,company_id,l1_index_code,l2_index_code,l3_index_code,in_date,out_date,is_new,created_at,updated_at                                                                                                                                                                  |
| public   | companies                  | generic_industry |             18 | company_id,name,name_en,short_name,market_type,ticker,exchange,industry,founded_date,headquarters,website,description,employee_count,is_active,created_at,updated_at,name_embedding,embedding_model                                                                    |
| public   | company_segment_map        | generic_segment  |             10 | id,company_id,segment_id,core_business_ratio,is_primary,start_date,created_at,updated_at,ratio_source,ratio_evidence                                                                                                                                                   |
| public   | graph_build_jobs           | generic_industry |             19 | job_id,job_name,industry_id,status,start_time,end_time,document_count,documents_processed,entities_recognized,relations_extracted,segments_mapped,segments_pending_review,is_incremental,auto_map_segments,start_date,end_date,error_message,created_at,updated_at     |
| public   | industries                 | generic_industry |              5 | industry_id,name,description,created_at,updated_at                                                                                                                                                                                                                     |
| public   | industry_segments          | generic_industry |             11 | segment_id,industry_id,name,position_type,description,sort_order,created_at,updated_at,name_embedding,description_embedding,embedding_model                                                                                                                            |
| public   | segment_reviews            | generic_industry |             18 | review_id,industry_id,company_id,suggested_segment_name,suggested_position_type,company_name,company_description,source_job_id,status,created_by,reviewed_by,reviewed_at,created_at,updated_at,suggested_description,is_new_segment,existing_segment_id,review_comment |
| public   | v_chain_completeness       | generic_industry |             10 | industry_id,industry_name,total_segments,upstream_count,midstream_count,downstream_count,total_companies,upstream_companies,midstream_companies,downstream_companies                                                                                                   |
| public   | v_quality_metrics          | generic_segment  |              7 | total_companies,total_relations,total_industries,total_segments,isolated_companies,outdated_relations,pending_reviews                                                                                                                                                  |

## Verified Shenwan Field Contract

| item | value |
|:--|:--|
| industry_mapping_table | public.map_company_industry_sw |
| industry_category_dimension_table | public.dim_industry_categories_sw |
| stock_code_field | map_company_industry_sw.company_id |
| sw_l1_code_field | map_company_industry_sw.l1_index_code |
| sw_l2_code_field | map_company_industry_sw.l2_index_code |
| sw_l3_code_field | map_company_industry_sw.l3_index_code |
| sw_l1_name_field | dim_industry_categories_sw.industry_name joined on l1_index_code=index_code |
| sw_l2_name_field | dim_industry_categories_sw.industry_name joined on l2_index_code=index_code |
| sw_l3_name_field | dim_industry_categories_sw.industry_name joined on l3_index_code=index_code |
| effective_date_field | map_company_industry_sw.in_date |
| expiry_date_field | map_company_industry_sw.out_date |
