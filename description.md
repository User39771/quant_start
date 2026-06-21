# A-share Factor Research Workflow

## Design

The preferred workflow is database-to-local-cache, then cache-only research.

- `scripts/inspect_database.py` reads PostgreSQL `information_schema` and creates `data/processed/db_schema.csv` plus `config/db_mapping_template.json`.
- `config/db_mapping.json` is the formal, human-confirmed mapping. Sync never uses automatic table guessing as authority.
- `scripts/sync_database_cache.py` reads enabled endpoints from the mapping and writes local CSV cache. Phase 1 supports `universe` and `price`.
- `scripts/run_research.py --cache-only` uses local CSV files and should not call AkShare.
- AkShare pre-cache scripts remain as fallback tools, not the main data path.

Database credentials must be provided through environment variables:

```powershell
$env:DB_HOST='...'
$env:DB_PORT='15432'
$env:DB_NAME='deeppivot'
$env:DB_USER='...'
$env:DB_PASSWORD='...'
```

Do not write credentials into code, mapping files, or documentation.

## Operating Flow

1. Inspect the database schema:

   ```powershell
   python scripts/inspect_database.py
   ```

2. Review `data/processed/db_schema.csv`, then manually confirm `config/db_mapping.json`.

3. Dry-run the sync:

   ```powershell
   python scripts/sync_database_cache.py --dry-run --max-symbols 200 --years 1 --endpoints universe,price
   ```

4. Sync local cache:

   ```powershell
   python scripts/sync_database_cache.py --max-symbols 200 --years 1 --endpoints universe,price
   ```

5. Generate a cache-only report:

   ```powershell
   python scripts/run_research.py --cache-only --years 1 --sleep 0
   ```

## Safety Rules

- Database connections are read-only and use statement/idle timeout settings.
- SQL identifiers are validated against `information_schema` before query construction.
- SQL values such as symbols and dates are parameterized.
- Cache writes are atomic: write `.tmp`, validate required columns and row count, then replace.
- Price cache is sorted by `code/date`, deduplicated, and never forward-filled.
- `price_adjustment=unknown` is allowed, but reports are marked `exploratory / not for decision`.

## Outputs

- `data/cache/universe_spot.csv`: local universe cache.
- `data/cache/price/*.csv`: local daily price cache.
- `data/processed/db_schema.csv`: database schema snapshot.
- `data/processed/db_sync_summary.csv`: sync status by symbol/endpoint.
- `data/processed/db_sync_warnings.csv`: duplicate-resolution warnings.
- `data/processed/factor_panel.csv`: generated factor panel.
- `reports/factor_reliability_report.md`: research report.
