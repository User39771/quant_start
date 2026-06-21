from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from aq_factor_lab.db_source import DatabaseConfig, connect_database

KEYWORDS = (
    "industry",
    "sector",
    "segment",
    "shenwan",
    "citic",
    "gics",
    "classification",
    "category",
    "_sw",
)


def discover_industry_tables(schema_frame: pd.DataFrame) -> list[dict[str, Any]]:
    required = {"schema", "table", "column", "data_type"}
    missing = required - set(schema_frame.columns)
    if missing:
        raise ValueError(f"db_schema.csv missing columns: {', '.join(sorted(missing))}")
    frame = schema_frame.copy()
    for column in required:
        frame[column] = frame[column].astype(str)
    matches: list[dict[str, Any]] = []
    for (schema, table), group in frame.groupby(["schema", "table"], sort=True):
        table_text = str(table).lower()
        columns = group["column"].astype(str).tolist()
        column_text = " ".join(columns).lower()
        if not any(keyword in table_text or keyword in column_text for keyword in KEYWORDS):
            continue
        matches.append(
            {
                "schema": str(schema),
                "table": str(table),
                "source": classify_industry_source(str(table), columns),
                "matched_columns": ",".join(columns),
                "column_count": int(group.shape[0]),
            }
        )
    return sorted(matches, key=lambda row: (source_rank(str(row["source"])), str(row["schema"]), str(row["table"])))


def classify_industry_source(table: str, columns: list[str]) -> str:
    text = f"{table} {' '.join(columns)}".lower()
    if "shenwan" in text or "_sw" in text or table.endswith("_sw"):
        return "申万/Shenwan"
    if "citic" in text:
        return "中信/Citic"
    if "gics" in text:
        return "GICS"
    if "industry" in text:
        return "generic_industry"
    if "sector" in text:
        return "generic_sector"
    if "segment" in text:
        return "generic_segment"
    return "candidate"


def source_rank(source: str) -> int:
    if "申万" in source:
        return 0
    if "中信" in source:
        return 1
    if "GICS" in source:
        return 2
    return 3


def render_discovery_log(matches: list[dict[str, Any]], db_samples: list[dict[str, Any]] | None) -> str:
    sw_found = any("申万" in str(match.get("source", "")) for match in matches)
    status = "sw_found_applied" if sw_found else "industry_not_found"
    lines = [
        "# Industry Classification Discovery Log",
        "",
        f"- status={status}",
        f"- candidate_tables={len(matches)}",
        "- implementation_scope=shenwan_l1_market_cap_industry_neutralization",
        "",
        "## Schema Candidates",
        "",
    ]
    if not matches:
        lines.append("No industry classification candidates found.")
    else:
        rows = pd.DataFrame(matches)
        lines += rows[["schema", "table", "source", "column_count", "matched_columns"]].to_markdown(index=False).splitlines()
    if db_samples:
        lines += ["", "## DB Coverage Samples", ""]
        rows = pd.DataFrame(db_samples)
        lines += rows.to_markdown(index=False).splitlines()
    if sw_found:
        lines += [
            "",
            "## Verified Shenwan Field Contract",
            "",
            "| item | value |",
            "|:--|:--|",
            "| industry_mapping_table | public.map_company_industry_sw |",
            "| industry_category_dimension_table | public.dim_industry_categories_sw |",
            "| stock_code_field | map_company_industry_sw.company_id |",
            "| sw_l1_code_field | map_company_industry_sw.l1_index_code |",
            "| sw_l2_code_field | map_company_industry_sw.l2_index_code |",
            "| sw_l3_code_field | map_company_industry_sw.l3_index_code |",
            "| sw_l1_name_field | dim_industry_categories_sw.industry_name joined on l1_index_code=index_code |",
            "| sw_l2_name_field | dim_industry_categories_sw.industry_name joined on l2_index_code=index_code |",
            "| sw_l3_name_field | dim_industry_categories_sw.industry_name joined on l3_index_code=index_code |",
            "| effective_date_field | map_company_industry_sw.in_date |",
            "| expiry_date_field | map_company_industry_sw.out_date |",
        ]
    lines.append("")
    return "\n".join(lines)


def fetch_db_samples(matches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not all(os.environ.get(key) for key in ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"]):
        return []
    samples: list[dict[str, Any]] = []
    config = DatabaseConfig.from_env()
    with connect_database(config) as conn:
        for match in matches:
            schema = str(match["schema"])
            table = str(match["table"])
            samples.append(fetch_table_sample(conn, schema, table))
    return samples


def fetch_table_sample(conn, schema: str, table: str) -> dict[str, Any]:
    from psycopg import sql

    with conn.cursor() as cur:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM {}").format(sql.Identifier(schema, table)))
        rows = cur.fetchone()[0]
    sample: dict[str, Any] = {"table": f"{schema}.{table}", "rows": int(rows)}
    if table == "companies":
        with conn.cursor() as cur:
            cur.execute(sql.SQL("SELECT COUNT(industry) FROM {}").format(sql.Identifier(schema, table)))
            sample["industry_non_null"] = int(cur.fetchone()[0])
    elif table == "map_company_industry_sw":
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL(
                    "SELECT COUNT(DISTINCT company_id), COUNT(DISTINCT l1_index_code), "
                    "COUNT(DISTINCT l2_index_code), COUNT(DISTINCT l3_index_code) FROM {}"
                ).format(sql.Identifier(schema, table))
            )
            companies, l1, l2, l3 = cur.fetchone()
            sample.update({"companies": int(companies), "l1": int(l1), "l2": int(l2), "l3": int(l3)})
    elif table == "dim_industry_categories_sw":
        with conn.cursor() as cur:
            cur.execute(
                sql.SQL("SELECT COUNT(DISTINCT industry_code), COUNT(DISTINCT level) FROM {}").format(
                    sql.Identifier(schema, table)
                )
            )
            codes, levels = cur.fetchone()
            sample.update({"industry_codes": int(codes), "levels": int(levels)})
    return sample


def main() -> None:
    schema_path = ROOT / "data" / "processed" / "db_schema.csv"
    if not schema_path.exists():
        raise FileNotFoundError(f"Missing schema snapshot: {schema_path}")
    schema = pd.read_csv(schema_path)
    matches = discover_industry_tables(schema)
    samples = fetch_db_samples(matches)
    log = render_discovery_log(matches, samples)
    output = ROOT / "data" / "processed" / "industry_discovery_log.md"
    output.write_text(log, encoding="utf-8")
    print(log)
    print(f"Industry discovery log written: {output}")


if __name__ == "__main__":
    main()
