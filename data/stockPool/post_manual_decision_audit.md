# Post-Manual Decision Audit


## Counts After Manual Merge
- Total rows: 200
- Manual rows applied: 19
- Rows with changed status/materiality: 6

## review_status Distribution
- conditional: 93
- reject: 44
- watchlist: 42
- core: 20
- unknown: 1

## theme_revenue_materiality Distribution
- transition: 101
- immaterial: 42
- unknown: 38
- core: 19

## By Theme / Status
```
review_status  conditional  core  reject  unknown  watchlist
theme                                                       
AI                      77     8      36        1         30
商业航天                    16    12       8        0         12
```

## Changed Rows
```
  code name theme before_status after_status before_materiality after_materiality
  2602 世纪华通    AI   conditional       reject         transition        transition
300036 超图软件    AI   conditional       reject         transition        transition
300036 超图软件  商业航天     watchlist       reject         transition        transition
300098  高新兴  商业航天     watchlist       reject            unknown           unknown
300123 ST亚光  商业航天   conditional       reject         transition        transition
300342 天银机电  商业航天   conditional         core         transition        transition
```