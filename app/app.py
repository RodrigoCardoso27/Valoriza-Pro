from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # pasta raiz do projeto
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
    
import streamlit as st
import pandas as pd

from cartola.client import CartolaClient
from cartola import storage
from cartola.analytics import make_dataframe, valuation_heuristic, filter_probables, top_by_position
from cartola.team_builder import build_team_greedy, FORMATIONS

st.set_page_config(page_title="Cartola Scout", layout="wide")

@st.cache_data(ttl=30)
def fetch_all(base_url: str):
    client = CartolaClient(base_url=base_url)
    status = client.mercado_status()
    rodada = int(status.get("rodada_atual") or status.get("rodada") or 0)

    mercado = client.atletas_mercado()
    partidas = client.partidas()

    # Parciais podem falhar dependendo do estado da rodada/mercado
    parciais = None
    try:
        parciais = client.parciais()
    except Exception:
        parciais = None

    return rodada, status, mercado, partidas, parciais

def main():
    st.title("⚽ Cartola Scout (MVP)")
    st.caption("Sugestão de escalação por rodada, baseada em mercado + heurística de valorização.")

    with st.sidebar:
        st.subheader("Configurações")
        base_url = st.text_input("Base URL da API", value="https://api.cartolafc.globo.com")
        only_probable = st.toggle("Somente prováveis (status_id=7)", value=True)
        formation = st.selectbox("Formação", list(FORMATIONS.keys()), index=0)
        budget = st.number_input("Orçamento (C$)", min_value=0.0, value=120.0, step=1.0)
        st.divider()
        if st.button("🔄 Atualizar agora"):
            st.cache_data.clear()

    try:
        rodada, status, mercado, partidas, parciais = fetch_all(base_url)
    except Exception as e:
        st.error(f"Falha ao consultar API: {e}")
        st.stop()

    # salva snapshots
    storage.init_db()
    storage.save_snapshot(rodada, "status", status)
    storage.save_snapshot(rodada, "mercado", mercado)
    storage.save_snapshot(rodada, "partidas", partidas)
    if parciais is not None:
        storage.save_snapshot(rodada, "parciais", parciais)

    # normaliza atletas e guarda histórico de preço
    atletas = (mercado.get("atletas") or mercado.get("atleta") or [])
    storage.upsert_price_history(rodada, atletas)

    # pontos (parciais) quando disponíveis
    if isinstance(parciais, dict):
        points_map = parciais.get("atletas") or parciais.get("pontuados") or {}
        if isinstance(points_map, dict) and points_map:
            storage.upsert_points_history(rodada, points_map)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Rodada atual", rodada)
    with col2:
        st.metric("Mercado", "Aberto" if status.get("status_mercado") == 1 else "Fechado")
    with col3:
        st.metric("Parciais", "Disponíveis" if parciais is not None else "Indisponíveis")

    df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
    df = valuation_heuristic(df)
    df = filter_probables(df, only_probable=only_probable)

    st.subheader("📊 Ranking (por posição)")
    tabs = st.tabs(["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC", "Todos"])
    for i, pos in enumerate(["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"]):
        with tabs[i]:
            d = top_by_position(df, pos, n=30)
            st.dataframe(d[["apelido","clube","posicao","preco","media","delta_preco","score_final","bonus_valorizacao"]], use_container_width=True)

    with tabs[-1]:
        st.dataframe(df.sort_values("score_final", ascending=False).head(200), use_container_width=True)

    st.subheader("🧠 Time sugerido")
    team, left = build_team_greedy(df, formation=formation, budget=float(budget))
    if team.empty:
        st.warning("Não consegui montar um time com os filtros/orçamento atuais. Tente aumentar o orçamento ou desmarcar 'somente prováveis'.")
    else:
        st.success(f"Time montado na formação {formation}. Sobra: C$ {left:.2f}")
        st.dataframe(team[["apelido","clube","posicao","preco","media","delta_preco","score_final"]].sort_values(["posicao","score_final"], ascending=[True, False]), use_container_width=True)
        st.write(f"**Custo total:** C$ {(float(budget)-left):.2f}")

    with st.expander("🔎 Dados da rodada (partidas)"):
        st.json(partidas)

    with st.expander("🧾 Debug (status/mercado)"):
        st.json({"status": status, "keys_mercado": list(mercado.keys())})

if __name__ == "__main__":
    main()
