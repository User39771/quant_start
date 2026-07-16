import time
import pandas as pd
import akshare as ak
from difflib import get_close_matches

concept_df = ak.stock_board_concept_name_em()
concept_names = concept_df["板块名称"].astype(str).tolist()

def resolve_concept(name: str):
    if name in concept_names:
        row = concept_df[concept_df["板块名称"] == name].iloc[0]
        return row["板块名称"], row.get("板块代码", None), "matched"

    matches = get_close_matches(name, concept_names, n=5, cutoff=0.65)
    if not matches:
        return None, None, "no_match"

    # 第一版不要自动接受模糊匹配，只记录候选，人工确认
    return "|".join(matches), None, "fuzzy_candidates"

def fetch_rows(matched_name: str):
    if matched_name is None or "|" in matched_name:
        return None
    try:
        df = ak.stock_board_concept_cons_em(symbol=matched_name)
        time.sleep(1.0)
        return len(df)
    except Exception:
        return None