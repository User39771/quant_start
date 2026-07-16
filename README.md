# A股现金流与主力资金因子拆解

这个项目把截图里的两个诊股信号拆成可检验的量化因子：

- `cashflow_quality_score`：现金流造血质量，分数越高越好。
- `main_moneyflow_score`：主力资金流强度，分数越高代表主力净流入越强。

第一版默认使用 AkShare，不依赖 Tushare。目标是做因子可靠性检验，而不是直接生成交易策略。

## 快速开始

先跑离线单元测试：

```powershell
python -m unittest discover -s tests
```

再跑一个小样本真实数据烟测：

```powershell
python scripts/run_research.py --max-symbols 10 --years 1
```

如果全市场列表接口网络不稳定，可以直接指定股票：

```powershell
python scripts/run_research.py --symbols 600519,000001,300750 --years 1
```

正式跑近 3 年沪深 A 股：

```powershell
python scripts/run_research.py --years 3
```

输出文件会写入：

- `data/cache/`：AkShare 原始数据缓存。
- `data/processed/`：因子面板与检验表。
- `reports/`：Markdown 报告和图片。

## 重要说明

- AkShare 的个股主力资金流接口通常只能取到较短历史。代码会如实报告覆盖率，不会把短历史伪装成 3 年长期结果。
- 个股财报接口不一定提供精确公告日。若缺少公告日，代码保守使用“报告期后 120 天”作为可用日期，避免未来函数。
- 全市场运行会请求大量网页接口，建议先用 `--max-symbols 10` 确认环境可跑，再放大全样本。

## Public Data Layer

The standalone public-data layer lives under `aq_factor_lab.data_layer`. It is infrastructure only: it does not implement factors, rankings, strategies, or backtests.

Public functions:

```python
from aq_factor_lab.data_layer import (
    get_concept_members,
    get_daily_price,
    get_index_price,
    get_stock_universe,
)
```

Daily stock prices use deterministic exact-query cache files. If an exact cleaned cache exists, it is returned without silently refreshing qfq data. For A-share daily prices, `adjusted=True` means qfq / 前复权 and calls AkShare `stock_zh_a_hist(..., adjust="qfq")`; `adjusted=False` calls the same endpoint with `adjust=""`.
V1 does not implement TTL refresh, forced refresh, stale fallback, or partial-range cache merging; `allow_stale_cache` is reserved for future behavior.

Normalized price outputs use primary downstream columns `open`, `high`, `low`, and `close`. AkShare daily stock `成交量` is reported in 手/lots; the data layer converts `volume` to shares by multiplying by `100`. `amount` remains CNY/yuan. Index prices follow the same OHLCV convention and always use `adjusted=False`.

Universe and concept membership are marked with `asof_quality="current_snapshot"` in v1. AkShare does not provide point-in-time historical membership through these snapshot endpoints, so downstream research must not treat a requested historical date as true historical universe or concept membership.

Minimal live smoke test:

```powershell
$env:PYTHONPATH='src'; python scripts/smoke_test_data_layer.py
```

The smoke test requests only one small stock daily-price query, then repeats the same query to show exact clean-cache reuse. It does not download broad market data.

## Thematic Data Collection

`aq_factor_lab.data_collection` orchestrates bounded thematic research datasets on top of the
cache-first `data_layer`. It is still infrastructure only: it does not calculate factors, rankings,
signals, strategies, or backtests.

The collector accepts a small config with theme name, concept names, date range, optional benchmark
indices, and a `max_symbols` cap. It collects concept snapshots, optional current universe metadata,
daily OHLCV prices, index OHLCV prices, a manifest, and failures under:

```text
data/collected/thematic/<theme_name>/<run_id>/
```

Concept and universe membership remain `current_snapshot` in v1. A requested historical date is not
point-in-time historical membership, and the manifest records this caveat.

Small manual dry run:

```powershell
$env:PYTHONPATH='src'; python scripts/collect_thematic_data.py --config configs/thematic_data_sample.json --dry-run --max-symbols 2
```

# Files

- `codex_handoff_prompt.md`
  - Main prompt to paste into Codex.
  - It instructs Codex to use subagents, merge outputs, validate labels, and create the final review files.

- `theme_business_review_remaining_rows_061_200.csv`
  - The 140 rows still needing review.
  - Codex should fill these rows.

- `theme_business_review_seed_rows_001_060.csv`
  - The already-reviewed first 60 rows.
  - Codex should use this as labeling reference and preserve it in the final 200-row output.

## Suggested Codex Usage

1. Start a new Codex task in the same project/workspace.
2. Attach the three files above.
3. Paste the full contents of `codex_handoff_prompt.md`.
4. Ask Codex to execute the task end-to-end.
5. Check the final `manual_decision_required.csv` first.

## Important

Do not ask Codex to directly modify your original manual profile file.
It should create new output files first, then you can decide whether to replace or merge them into your project.

