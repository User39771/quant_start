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
