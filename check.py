import os
import psycopg

conn = psycopg.connect(
    host=os.environ["DB_HOST"],
    port=os.environ["DB_PORT"],
    dbname=os.environ["DB_NAME"],
    user=os.environ["DB_USER"],
    password=os.environ["DB_PASSWORD"]
)

# 测试两张表：现金流表和利润表
queries = {
    "cash_flow_check": """
        SELECT company_id, report_date, notice_date, netcash_operate
        FROM public.cash_flow_sheets
        WHERE netcash_operate IS NOT NULL
        LIMIT 5;
    """,
    "profit_check": """
        SELECT company_id, report_date, notice_date, total_operate_income, parent_netprofit
        FROM public.profit_sheets
        WHERE parent_netprofit IS NOT NULL
        LIMIT 5;
    """
}

with conn, conn.cursor() as cur:
    for name, sql in queries.items():
        try:
            print(f"\n--- Running {name} ---")
            cur.execute(sql)
            rows = cur.fetchall()
            if not rows:
                print("表是空的或找不到非空字段！")
            for row in rows:
                print(row)
        except Exception as e:
            print(f"Error querying {name}: {e}")
            conn.rollback() # 出错回滚，防止挂起