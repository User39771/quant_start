# Project Instructions

This is a Python quantitative research project for A-share stock data analysis.

## Environment

- Project root: D:\Python_Files\quant_start
- Do not modify files under C:\Users\Hangxi Yang\OneDrive\文档\量化初步
- Use the existing Python environment; do not recreate Python unless explicitly asked.
- Do not run npm install.
- Do not add proxy environment variables unless explicitly asked.

## Coding rules

- Prefer small, focused changes.
- Do not rewrite the whole project unless necessary.
- Preserve existing folder structure.
- Add comments for non-obvious finance/data logic.
- Keep data-fetching logic separate from factor calculation logic.
- Prefer robust error handling and clear logs.

## Network/data rules

- The user has confirmed that a minimal Python request to Eastmoney kline API works locally.
- If data fetching fails, check headers, session reuse, timeout, retry logic, secid mapping, and response validation first.
- Do not assume proxy variables are required.
- Do not silently skip failed symbols; record failures to a CSV or log file.

## Validation

After changes, run:

```powershell
python scripts/run_research.py --symbols 600519,000001,300750 --years 1