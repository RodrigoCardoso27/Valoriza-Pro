from __future__ import annotations

import pandas as pd

FORMATIONS = {
    "4-3-3": {"GOL": 1, "LAT": 2, "ZAG": 2, "MEI": 3, "ATA": 3, "TEC": 1},
    "4-4-2": {"GOL": 1, "LAT": 2, "ZAG": 2, "MEI": 4, "ATA": 2, "TEC": 1},
    "3-4-3": {"GOL": 1, "ZAG": 3, "MEI": 4, "ATA": 3, "TEC": 1},
    "3-5-2": {"GOL": 1, "ZAG": 3, "MEI": 5, "ATA": 2, "TEC": 1},
    "5-3-2": {"GOL": 1, "LAT": 2, "ZAG": 3, "MEI": 3, "ATA": 2, "TEC": 1},
}

def build_team_greedy(df: pd.DataFrame, formation: str, budget: float) -> tuple[pd.DataFrame, float]:
    """
    Monta time guloso por score_final, respeitando formação e orçamento.
    Retorna (team_df, budget_left).
    """
    if df.empty:
        return df, budget

    if formation not in FORMATIONS:
        raise ValueError(f"Formação inválida: {formation}")

    need = FORMATIONS[formation].copy()
    picked = []

    # Ordena por score_final/price ratio para favorecer custo-benefício
    d = df.copy()
    d["preco"] = d["preco"].fillna(0.0)
    d["score_final"] = d["score_final"].fillna(0.0)
    d["value_ratio"] = d.apply(lambda r: r["score_final"] / (r["preco"] + 1e-6), axis=1)
    d = d.sort_values(["value_ratio", "score_final"], ascending=False)

    remaining = float(budget)

    for _, row in d.iterrows():
        pos = row["posicao"]
        if pos not in need or need[pos] <= 0:
            continue
        price = float(row["preco"] or 0.0)
        if price <= remaining:
            picked.append(row)
            remaining -= price
            need[pos] -= 1
        if all(v <= 0 for v in need.values()):
            break

    team = pd.DataFrame(picked)
    return team, remaining
