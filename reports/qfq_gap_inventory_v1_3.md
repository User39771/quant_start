# QFQ Gap Inventory v1.3

## Stage Metadata
- status: completed_read_only_inventory
- inputs: `data/cache/qfq_enrichment_v1_2`, `data/processed/qfq_fetch_manifest_v1_2.csv`, `data/processed/adjusted_price_panel_v1_2.csv`, `reports/adjusted_stock_pool_baseline_periods_v1_2.csv`, `data/processed/mom60_factor_panel_v1_3.csv`
- outputs: `reports/qfq_gap_inventory_v1_3.csv`, `reports/qfq_gap_inventory_v1_3.md`
- changed_files: `reports/qfq_gap_inventory_v1_3.csv`, `reports/qfq_gap_inventory_v1_3.md`
- commands: `python - (fresh read-only QFQ cache, manifest, panel, baseline endpoint, and MOM60 endpoint inventory)`
- exit_codes: `0`
- QA: CSV schema exact=True; rows=133; codes_scanned=56; cache_files=54; baseline_endpoints=80; MOM60_rebalance_endpoints=57; MOM60_lookback_endpoints=57; SHA256_recorded=True
- blockers: none
- next-stage recommendation: defer repair in this sprint. A future versioned repair may address P0/P1 network gaps. P2 rows require raw-base lineage review: QFQ cache rows alone cannot create adjusted-panel dates absent from raw base.

## Result
- gap rows: 133
- complete failures: 2 (`full_failure`: no valid QFQ cache rows on adjusted-panel trading dates)
- partial stocks: 3 (`partial_cache_gap`: only a subset of adjusted-panel trading dates lacks QFQ)
- baseline endpoint gaps: 62 rows, using all 80 baseline report endpoints
- MOM60 factor endpoint gaps: 66 rows; rebalance endpoints and 60-trading-day lookback endpoints are reported separately
- normal non-trading dates: 26 rows; no fetch is proposed
- network-required rows: 12; cache/panel reconciliation rows: 95 (diagnostic only, not automatically cache-repairable)

## Classification
- `full_failure`: no legal positive `qfq_close` cache rows; P0 network repair.
- `partial_cache_gap`: a QFQ cache hole on an existing adjusted-panel stock trading date; P1 network repair.
- `baseline_endpoint_gap`, `factor_endpoint_gap`, and `factor_lookback_gap`: required endpoint exists in the adjusted panel but not the QFQ cache; P1 network repair.
- `*_cache_only_reconciliation_gap`: endpoint exists in cache but not in adjusted panel; P2 lineage reconciliation. Because the adjusted panel is a left join from raw base, these rows are repairable from cache only if the matching raw-base row also exists.
- `*_non_trading_day_difference`: endpoint is absent from both cache and adjusted panel for that stock; P3, normal stock calendar difference.

## Pre-Repair SHA256
| stock_code | cache_present | valid_qfq_rows | manifest_status | sha256 |
|---|---:|---:|---|---|
| 000063 | true | 1561 | cached_ok | b007f693f212ddc363127a264a882bd709db786579d882af47cbd8ac75a81d01 |
| 000681 | true | 1562 | cached_ok | fd60d5deee5662d4656ac6b6e6e1358598a4b49473330aba34e13a3695bb889c |
| 000901 | true | 1556 | cached_ok | 0aacc1efecb5045841a2bfe2660d44cbd30501720ff712abde889b36d28fc644 |
| 000938 | true | 1562 | cached_ok | 839835872bb0c7b077d0cac9414b7fcd68901be670053ae8267320e8dee0ae28 |
| 000977 | true | 1556 | cached_ok | 6151b627fcebb1ad189e927fb3d68ab253892cfb488beaeb22666a743a920fd0 |
| 001208 | true | 1206 | ok | 0f31b323ab1f616f4051a53211f59f2c574db64e709e62cba7bbcf450d98b717 |
| 002015 | true | 1562 | ok | 1b634e7af1d7fb57aad11ab7cb6ee623ea84beab65f56ebbb6d030c97ab95e71 |
| 002044 | true | 1562 | ok | fd2300423a5301d037599e0fc924e12d22d80972a8d679723594f5ce3a9cd15d |
| 002049 | true | 1551 | partial_ok | e78945b29c1f5095bcd23c067981bc97ee2f3cc8491d896cd10c81b2c42d22b8 |
| 002065 | true | 1562 | ok | 91278bd58fab7398dd77cf0658f4e77a907610392b04f0e19aa7ceec7cae610e |
| 002131 | true | 1559 | partial_ok | 6406de3ee1e249a51bbcfad68d573397f49dfbe1425231759fd4b895b737032f |
| 002212 | true | 1562 | ok | 19c0a6a7a3e8d8bf7ac2e0b8e06a5dbf50496d0ad775ebbf58cb726381577614 |
| 002230 | true | 1562 | ok | 3f0a76993ee6b72504e204375211a70c9427cee968bd5a525288d45beebc229c |
| 002236 | true | 1562 | ok | 19471ac2b7ba18ed03260e548fc98976d59da368e0f92bf76429d825f545e520 |
| 002279 | true | 1562 | ok | d55f8331528397e9aee410acfb53666a85e288d0ec4aeef61ab758bd8cf8b3ef |
| 002315 | true | 1562 | ok | f311450bd9361785419750f57d49807a5adcd76197c2003a14109c9a93a1fb94 |
| 002361 | true | 1562 | ok | 369680cf933837856b34ae4faa47f38f3bfbe9795bde1b104676009a9eb6e1b5 |
| 002373 | true | 1562 | ok | 1146eb5659bf4474cff77b12ac7e65cc185002e3306c431c6d0e6e6f239be46f |
| 002396 | true | 1562 | ok | c71a764da43adf9a62b7003b69612457b41c9174c1dd679a8078f3dcef67a4fe |
| 002410 | true | 1562 | ok | 51d5cb94e1610dd58f3889202d44dbad5b143e05aa4f6d6c7b577b2e01c099a0 |
| 002446 | true | 1562 | ok | e6698eff12c71fb285e57b7e7234a29253567607fcb07876a98787485945cb61 |
| 002544 | false | 0 | error | absent |
| 002558 | true | 1562 | ok | 412a44072d596d5aba1b68d3cd49908e8dab7aa6c0d64f584abcfd12bf715a0b |
| 002757 | true | 1562 | ok | 876b69bc69616d5563ab6dcd476d4e5eda2a83bc013e2fdaf02d70d8aab1115d |
| 002792 | true | 1562 | ok | 3ac260df248831f7404a99988b5b356a1831f184cbf4c9e81f53c18eff030655 |
| 002881 | true | 1562 | ok | ac9cdfe780d06154171a3d297a5011e5d47e218d080ceaef37512d0e08532437 |
| 002929 | true | 1562 | ok | 9becd6e2aab287b7bf8ba4f8f1483a9111a38415a5f041840ae6d283ce66c95e |
| 002935 | true | 1562 | ok | 971235bc05cf36e5c485f477d8ef878cec9a6bddeeaa58453706b5fc5a777e54 |
| 002987 | true | 1482 | ok | b1210133d3c4595f3e1dba2c1bcdd0636451f9c80a009070f826ae4c3337f85d |
| 300002 | true | 1562 | ok | 4f2607ef57c6e1327a0e7750b6986c071d85ff57e7a204cc8b0beb31bee0e4a2 |
| 300017 | true | 1562 | ok | 4000d16248635c1cbe10b9aabf9e9583e704cb0d14b7d57f37a87675ce676205 |
| 300033 | true | 1562 | ok | 63dbd21ab63800917a7403d552e06039ca9bd96e7880c2771e396a7d5f15ce2a |
| 300047 | true | 1562 | ok | 4a192e1d0e45ffe9a612b60fa3a7800352d698e902d66c81e2991769912b35fa |
| 300058 | true | 1562 | ok | bfb09e002947411656039b19c163266322202ddb28cd4bce9d3fcf08a964df10 |
| 300101 | true | 1562 | ok | 3fbd4143750033df78665414274144149ec0f39acdb3f74e73d2074fdece5f77 |
| 300113 | true | 1562 | ok | b686ce095d81b3ab1d5f3b7ee7b7b46b9e516af4487e7beb8d4f5e2cabfbb6c8 |
| 300133 | false | 0 | error | absent |
| 300170 | true | 1562 | ok | 4b6f3382dc90102a7c48edb17b0d8efc1e32552abe4fc50e7282f0fcddd90ba4 |
| 300182 | true | 1557 | ok | bdb45757fac389f081032329223a951093509fc3167541931a5ff86bab8085a6 |
| 300339 | true | 1557 | ok | e8d81b3cf0dd5b2b351fa012bc3905cb8a695bdd2b77d2585e75013e80ad46c9 |
| 300348 | true | 1562 | ok | c1de5ee9848bd9add83d45e970d2e55ab8dc9bbc315ca3fa39ea2c7cc50a5a86 |
| 300378 | true | 1562 | cached_ok | 42ee4c09edf6b84c77fc762f9658cc760350e4cf598cd531bc8781d5930383ff |
| 300413 | true | 1562 | ok | 9ee947d88bbfd82ab28658093d37a8ec53f632a26a63e09b868e8f452586a8af |
| 300454 | true | 1562 | ok | 15b128c364839f3bb6574d194ba2433d7a72817ffb0dc23fa3c78276bfd4ff76 |
| 300458 | true | 1562 | ok | 659b184d6ada6950f9fa67e16f25d9218aad8df5665ce774d408a11b6b05e0b4 |
| 300496 | true | 1562 | ok | c704ed4da765934850380720638d5b37a8e3c13854b367060666d0dba0f1e16a |
| 300627 | true | 1562 | ok | 7a6a4ef1bcfabcfd0f67eb0c093bb4d89fad45e2230c784d08226037f020de50 |
| 300629 | true | 1562 | ok | 7d504dcb3740a086607dd62083e782e360ed0432af4828b0ef2da8e648269813 |
| 300634 | true | 1562 | ok | 166a9efc832564ce5876332665485599fbd6560d48f488b1c23e458592a04456 |
| 300674 | true | 1562 | ok | 6e934647bdcea46e3393d8f0ce060da720631b23d70708672610942744b07f38 |
| 300857 | true | 1427 | cached_ok | b3f7917b93305c4d03424636cd45c7e638f5cd2b36763c17942188d4682b41e1 |
| 300996 | true | 1220 | ok | 3d41496335b3ba7313c6f9d3fd1e5e137c4fa041eab931a40f675f0f4a959e40 |
| 301050 | true | 1163 | ok | 862b137384abbebd7fc35a00f9ad871b9d2d3f13f74590dba554c9b32b4f1628 |
| 301110 | true | 1033 | ok | b7d8b00070abc265ea872ea83fa00a65b90ba6a149ff195b5c7aaa2ee0cecc9e |
| 301165 | true | 864 | ok | 4f400b2ebe947d6a7b0eba6fe70c87fc5dd44d54baafb08f1af06a5907ae9637 |
| 301171 | true | 921 | partial_ok | e156a50da9c6a2256fba4bcbb0390cd0294ead22191314b3dc3a71b54c89ad4a |

## Category Counts
- `baseline_endpoint_cache_only_reconciliation_gap`=48
- `baseline_endpoint_gap`=3
- `baseline_endpoint_non_trading_day_difference`=11
- `factor_endpoint_gap`=2
- `factor_endpoint_non_trading_day_difference`=7
- `factor_lookback_cache_only_reconciliation_gap`=47
- `factor_lookback_gap`=2
- `factor_lookback_non_trading_day_difference`=8
- `full_failure`=2
- `partial_cache_gap`=3
