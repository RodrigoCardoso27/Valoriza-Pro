from __future__ import annotations

import sys
from pathlib import Path

# ===== Path fix (Streamlit Cloud) =====
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
import requests
import pandas as pd
import streamlit as st

from cartola.client import CartolaClient
from cartola import storage
from cartola.analytics import make_dataframe, valuation_heuristic, filter_probables, top_by_position
from cartola.team_builder import build_team_greedy, FORMATIONS

st.set_page_config(page_title="Valoriza Pro", layout="wide", page_icon="⚽")

# ----------------------------
# Formações em Linhas (Grid)
# ----------------------------
STATUS_MAP = {2: "Dúvida", 3: "Suspenso", 5: "Contundido", 6: "Nulo", 7: "Provável", 8: "Vetado"}

FORMATION_ROWS = {
    "3-4-3": [
        ["ATA", "ATA", "ATA"],
        ["MEI", "MEI", "MEI", "MEI"],
        ["ZAG", "ZAG", "ZAG"],
        ["GOL", "TEC"]
    ],
    "4-3-3": [
        ["ATA", "ATA", "ATA"],
        ["MEI", "MEI", "MEI"],
        ["LAT", "ZAG", "ZAG", "LAT"],
        ["GOL", "TEC"]
    ],
    "4-4-2": [
        ["ATA", "ATA"],
        ["MEI", "MEI", "MEI", "MEI"],
        ["LAT", "ZAG", "ZAG", "LAT"],
        ["GOL", "TEC"]
    ],
}

# ----------------------------
# CSS (Campo de Futebol Real)
# ----------------------------
CSS = """
<style>
.stApp { background-color: #0d1117; color: #ffffff; }

/* Desenhando o Gramado com CSS */
.pitch-container {
    background: repeating-linear-gradient(
        0deg,
        #2e7d32,
        #2e7d32 50px,
        #276b2a 50px,
        #276b2a 100px
    );
    border: 3px solid rgba(255, 255, 255, 0.4);
    border-radius: 8px;
    padding: 30px 10px;
    position: relative;
    box-shadow: inset 0px 0px 40px rgba(0,0,0,0.6);
    overflow: hidden;
}

/* Linha de meio de campo e círculo central */
.pitch-container::before {
    content: "";
    position: absolute;
    top: 50%;
    left: 0;
    right: 0;
    height: 2px;
    background: rgba(255, 255, 255, 0.4);
    z-index: 0;
}
.pitch-container::after {
    content: "";
    position: absolute;
    top: 50%;
    left: 50%;
    transform: translate(-50%, -50%);
    width: 100px;
    height: 100px;
    border: 2px solid rgba(255, 255, 255, 0.4);
    border-radius: 50%;
    z-index: 0;
}

/* Ocultar elementos do Streamlit para colar o card no botão */
div[data-testid="column"] { z-index: 1; }
div.stButton > button {
    width: 100%;
    border-radius: 0 0 10px 10px; /* Arredonda só embaixo */
    background-color: #1f2937;
    border: 1px solid #374151;
    border-top: none;
    color: white;
    font-size: 0.8rem;
    padding: 2px 0;
}
div.stButton > button:hover { border-color: #22c55e; color: #22c55e; }

/* Cards Escuros Estilo Cartola */
.cartola-card {
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #374151;
    border-bottom: none;
    border-radius: 10px 10px 0 0; /* Arredonda só em cima */
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 10px 5px 5px 5px;
    height: 110px;
    justify-content: center;
}
.cartola-card img {
    border-radius: 50%;
    width: 50px;
    height: 50px;
    object-fit: cover;
    border: 2px solid #22c55e;
    background-color: #cbd5e1;
}
.cartola-card .pos-badge {
    background-color: #0f172a;
    color: #e2e8f0;
    font-size: 0.65rem;
    padding: 1px 6px;
    border-radius: 10px;
    margin-top: -10px;
    z-index: 2;
    border: 1px solid #374151;
}
.cartola-card .name { font-size: 0.75rem; font-weight: bold; margin-top: 4px; text-align: center; line-height: 1.1;}
.cartola-card .price { font-size: 0.7rem; color: #22c55e; font-weight: bold;}

.card-empty { border-style: dashed; background: rgba(15, 23, 42, 0.7); }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ----------------------------
# Helpers
# ----------------------------
def format_foto_url(raw: str | None, size: str = "140x140") -> str | None:
    if not raw: return "https://s2.glbimg.com/a4E1AXX0iV9I9K_4v-d_XyUv-0I=/140x140/smart/https://s3.glbimg.com/v1/AUTH_58d78b787ec34892b5aaa0c7a14616a6/placeholder/perfil.png"
    url = raw.replace("{FORMATO}", size).replace("FORMATO", size)
    if url.startswith("//"): url = "https:" + url
    return url

def df_with_status_and_photo(df: pd.DataFrame, mercado_payload: dict) -> pd.DataFrame:
    athletes = mercado_payload.get("atletas") or mercado_payload.get("atleta") or []
    photo_map = {int(a.get("atleta_id") or a.get("id")): format_foto_url(a.get("foto")) for a in athletes if (a.get("atleta_id") or a.get("id"))}
    out = df.copy()
    if not out.empty:
        out["status_nome"] = out["status_id"].map(STATUS_MAP).fillna(out["status_id"].astype(str))
        out["foto_url"] = out["athlete_id"].map(photo_map)
    return out

@st.cache_data(ttl=30)
def fetch_cartola():
    client = CartolaClient(base_url="https://api.cartolafc.globo.com")
    status = client.mercado_status()
    rodada = int(status.get("rodada_atual") or status.get("rodada") or 0)
    mercado = client.atletas_mercado()
    return rodada, status, mercado

# ----------------------------
# MODAL DE SELEÇÃO (Filtra Posição, Prováveis e Custo)
# ----------------------------
@st.dialog("Mercado de Transferências")
def selecionar_jogador_modal(slot_key: str, pos_target: str, df_opcoes: pd.DataFrame, orcamento_livre: float):
    st.markdown(f"### Buscando: **{pos_target}**")
    
    # Filtra apenas a posição desejada (já são apenas prováveis da df_base)
    df_filtrado = df_opcoes[df_opcoes["posicao"] == pos_target].copy()
    
    # Filtra jogadores que cabem no saldo atual (opcional, ajuda a não estourar)
    df_filtrado = df_filtrado[df_filtrado["preco"] <= (orcamento_livre + 20)] # Dá uma margem caso ele queira trocar depois
    df_filtrado = df_filtrado.sort_values(by="score_final", ascending=False)
    
    opcoes = []
    mapa_jogadores = {}
    for _, r in df_filtrado.iterrows():
        id_jog = int(r["athlete_id"])
        texto = f"{r['apelido']} ({r['clube']}) | C$ {float(r['preco']):.2f} | Potencial: {float(r['score_final']):.1f}"
        opcoes.append(texto)
        mapa_jogadores[texto] = id_jog
        
    escolha = st.selectbox("Selecione o atleta (ordenado por melhor custo/benefício):", opcoes)
    
    if st.button("✅ Confirmar", type="primary"):
        st.session_state["picked"][slot_key] = mapa_jogadores[escolha]
        st.rerun()

# ----------------------------
# APP PRINCIPAL
# ----------------------------
def main():
    if "picked" not in st.session_state: st.session_state["picked"] = {}

    with st.sidebar:
        st.header("⚙️ Painel de Controle")
        formacao_escolhida = st.selectbox("Formação Tática", list(FORMATION_ROWS.keys()), index=0)
        orcamento = st.number_input("Meu Saldo (C$)", value=120.0, step=1.0)
        
        st.markdown("---")
        auto = st.button("⚡ Auto-escalar (IA)", use_container_width=True)
        if st.button("🗑️ Limpar Time", use_container_width=True):
            st.session_state["picked"] = {}
            st.rerun()

    # Fetch Data
    try:
        rodada, status, mercado = fetch_cartola()
        df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
        df = valuation_heuristic(df) # Lógica matemática de valorização
        df_base = df_with_status_and_photo(filter_probables(df, only_probable=True), mercado)
    except Exception as e:
        st.error(f"Erro ao carregar Cartola: {e}")
        st.stop()

    # Lógica de Orçamento Atual
    ids_escolhidos = list(st.session_state["picked"].values())
    time_df = df_base[df_base["athlete_id"].isin(ids_escolhidos)]
    custo_total = time_df["preco"].sum() if not time_df.empty else 0.0
    saldo_restante = orcamento - custo_total

    # Lógica do Auto-escalar (Pega os melhores pro saldo)
    if auto:
        team_auto, _ = build_team_greedy(df_base, formation=formacao_escolhida, budget=float(orcamento))
        st.session_state["picked"] = {}
        idx_tracker = {"ATA": 0, "MEI": 0, "ZAG": 0, "LAT": 0, "GOL": 0, "TEC": 0}
        for _, r in team_auto.iterrows():
            pos = r["posicao"]
            slot_key = f"{pos}-{idx_tracker[pos]}"
            st.session_state["picked"][slot_key] = int(r["athlete_id"])
            idx_tracker[pos] += 1
        st.rerun()

    # Interface Visual
    col_campo, col_resumo = st.columns([2.5, 1])
    
    with col_resumo:
        st.markdown(f"### 💰 Saldo: C$ {saldo_restante:.2f}")
        st.markdown(f"**Gasto:** C$ {custo_total:.2f}")
        if saldo_restante < 0:
            st.error("⚠️ Orçamento estourado!")
        st.dataframe(time_df[["apelido", "posicao", "preco"]], hide_index=True, use_container_width=True)

    with col_campo:
        st.markdown('<div class="pitch-container">', unsafe_allow_html=True)
        layout = FORMATION_ROWS[formacao_escolhida]
        count_tracker = {"ATA": 0, "MEI": 0, "ZAG": 0, "LAT": 0, "GOL": 0, "TEC": 0}
        
        for linha in layout:
            cols = st.columns(len(linha))
            for i, pos_alvo in enumerate(linha):
                slot_key = f"{pos_alvo}-{count_tracker[pos_alvo]}"
                count_tracker[pos_alvo] += 1
                
                with cols[i]:
                    id_selecionado = st.session_state["picked"].get(slot_key)
                    
                    if id_selecionado:
                        jogador = df_base[df_base["athlete_id"] == id_selecionado].iloc[0]
                        # Parte de cima do Card (Visual HTML)
                        st.markdown(f"""
                        <div class="cartola-card">
                            <img src="{jogador['foto_url']}">
                            <div class="pos-badge">{jogador['posicao']}</div>
                            <div class="name">{jogador['apelido']}</div>
                            <div class="price">C$ {jogador['preco']:.2f}</div>
                        </div>
                        """, unsafe_allow_html=True)
                        # Parte de baixo (Botão Streamlit colado)
                        if st.button("🔄 Trocar", key=f"btn_{slot_key}"):
                            selecionar_jogador_modal(slot_key, pos_alvo, df_base, saldo_restante)
                    else:
                        st.markdown(f"""
                        <div class="cartola-card card-empty">
                            <div class="pos-badge">{pos_alvo}</div>
                            <div class="name" style="color:#94a3b8;">Vazio</div>
                        </div>
                        """, unsafe_allow_html=True)
                        if st.button(f"➕ Add", key=f"btn_{slot_key}"):
                            selecionar_jogador_modal(slot_key, pos_alvo, df_base, saldo_restante)
            st.write("") # Quebra de linha
        st.markdown('</div>', unsafe_allow_html=True)

if __name__ == "__main__":
    main()
