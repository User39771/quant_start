# MCTS Sandbox v1 Redundancy

| search_method   |   successful_proposals |   distinct_formulas |   canonical_formulas |   unique_rank_signals |   unique_q5_portfolios |   rank_information_redundancy |   canonical_cache_hits |   rank_cache_hits |
|:----------------|-----------------------:|--------------------:|---------------------:|----------------------:|-----------------------:|------------------------------:|-----------------------:|------------------:|
| mcts            |                  46299 |                7699 |                 4765 |                  1749 |                   1214 |                      0.962224 |                  33890 |              7409 |
| random          |                  15730 |                7729 |                 6976 |                  3678 |                   2924 |                      0.766179 |                   7437 |              3293 |

Cache hits are proposal-level search-mechanism evidence. Q5 equivalence is derived only from signal membership and never controls reward evaluation.
