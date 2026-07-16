import pandas as pd
df = pd.read_csv("data/processed/adjusted_price_panel_v1_2.csv", dtype={"stock_code": str})
print(df["stock_code"].head())
print(df["stock_code"].str.fullmatch(r"\d{6}").all())
print(df["trade_date"].head())
print(df["adjusted_flag"].value_counts(dropna=False))