from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.db_source import (
    DatabaseConfig,
    connect_database,
    fetch_information_schema,
    make_mapping_template,
    write_json,
)


def main() -> None:
    config = DatabaseConfig.from_env()
    processed_dir = ROOT / "data" / "processed"
    processed_dir.mkdir(parents=True, exist_ok=True)
    with connect_database(config) as conn:
        schema = fetch_information_schema(conn)
    schema.to_csv(processed_dir / "db_schema.csv", index=False, encoding="utf-8-sig")
    write_json(ROOT / "config" / "db_mapping_template.json", make_mapping_template(schema))
    print(f"Schema written: {processed_dir / 'db_schema.csv'}")
    print(f"Mapping template written: {ROOT / 'config' / 'db_mapping_template.json'}")


if __name__ == "__main__":
    main()
