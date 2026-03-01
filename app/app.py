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
# Mapeamentos / Formações em Linhas (Grid Streamlit)
# ----------------------------
STATUS_MAP = {2: "Dúvida", 3: "Suspenso", 5: "Contundido", 6: "Nulo", 7: "Provável", 8: "Vetado"}
MERCADO_MAP = {1: "Aberto", 2: "Fechado"}

# Em vez de posições fixas de HTML, dividimos as formações por "Linhas" para usar st.columns
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
    "3-5-2": [
        ["ATA", "ATA"],
        ["MEI", "MEI", "MEI", "MEI", "MEI"],
        ["ZAG", "ZAG", "ZAG"],
        ["GOL", "TEC"]
    ],
    "5-3-2": [
        ["ATA", "ATA"],
        ["MEI", "MEI", "MEI"],
        ["LAT", "ZAG", "ZAG", "ZAG", "LAT"],
        ["GOL", "TEC"]
    ],
}

# ----------------------------
# CSS (Foco em replicar o visual dark do Cartola)
# ----------------------------
CSS = """
<style>
.stApp { background-color: #121418; color: #ffffff; }
.block-container { max-width: 1200px; }

/* Estilo do Campo de Futebol */
.pitch-container {
    background: linear-gradient(180deg, #2a6f37 0%, #1e5228 100%);
    border-radius: 12px;
    padding: 20px;
    border: 2px solid rgba(255,255,255,0.1);
    box-shadow: inset 0px 0px 50px rgba(0,0,0,0.5);
}

/* Card Estilo Cartola */
.cartola-card {
    background-color: #161b22;
    border: 1px solid #2d3748;
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 10px;
    margin-bottom: 5px;
    box-shadow: 0px 4px 6px rgba(0,0,0,0.3);
    height: 140px;
    justify-content: center;
}
.cartola-card img {
    border-radius: 50%;
    width: 60px;
    height: 60px;
    object-fit: cover;
    border: 2px solid #22c55e;
}
.cartola-card .pos-badge {
    background-color: #2d3748;
    font-size: 0.7rem;
    padding: 2px 8px;
    border-radius: 10px;
    margin-top: -10px;
    z-index: 2;
    font-weight: bold;
}
.cartola-card .name { font-size: 0.8rem; font-weight: bold; margin-top: 5px; text-align: center;}
.cartola-card .price { font-size: 0.75rem; color: #22c55e; font-weight: bold;}

/* Estilo do botão padrão do Streamlit para parecer card vazio */
div[data-testid="stButton"] button {
    width: 100%;
    border-radius: 8px;
    font-weight: bold;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ----------------------------
# Helpers & Fetch
# ----------------------------
def safe_get(d: dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur: return default
        cur = cur[k]
    return cur

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
def fetch_cartola(base_url: str):
    client = CartolaClient(base_url=base_url)
    status = client.mercado_status()
    rodada = int(status.get("rodada_atual") or status.get("rodada") or 0)
    mercado = client.atletas_mercado()
    partidas = client.partidas()
    try: parciais = client.parciais()
    except: parciais = None
    return rodada, status, mercado, partidas, parciais

# ----------------------------
# MODAL DE SELEÇÃO
# ----------------------------
@st.dialog("Mercado de Transferências")
def selecionar_jogador_modal(slot_key: str, pos_target: str, df_opcoes: pd.DataFrame):
    st.write(f"Escolhendo **{pos_target}**")
    
    # Filtra só a posição pedida
    df_filtrado = df_opcoes[df_opcoes["posicao"] == pos_target].copy()
    df_filtrado = df_filtrado.sort_values(by="preco", ascending=False)
    
    # Prepara lista pro Selectbox
    opcoes = []
    mapa_jogadores = {}
    for _, r in df_filtrado.iterrows():
        id_jog = int(r["athlete_id"])
        texto = f"{r['apelido']} ({r['clube']}) - C$ {float(r['preco']):.2f} - {r['status_nome']}"
        opcoes.append(texto)
        mapa_jogadores[texto] = id_jog
        
    escolha = st.selectbox("Selecione o atleta:", opcoes)
    
    if st.button("Confirmar Escalação", type="primary"):
        st.session_state["picked"][slot_key] = mapa_jogadores[escolha]
        st.rerun()

# ----------------------------
# APP PRINCIPAL
# ----------------------------
def main():
    st.title("⚽ Valoriza Pro - TabuadaRJ")
    
    # Estado inicial
    if "picked" not in st.session_state: st.session_state["picked"] = {}

    with st.sidebar:
        st.header("⚙️ Painel de Controle")
        formacao_escolhida = st.selectbox("Formação Tática", list(FORMATION_ROWS.keys()), index=0)
        orcamento = st.number_input("Orçamento (C$)", value=120.0, step=1.0)
        auto = st.button("⚡ Auto-escalar (IA)", use_container_width=True)
        if st.button("🗑️ Limpar Time", use_container_width=True):
            st.session_state["picked"] = {}
            st.rerun()

    # Fetch Data
    try:
        rodada, status, mercado, partidas, parciais = fetch_cartola("https://api.cartolafc.globo.com")
        df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
        df = valuation_heuristic(df)
        df_base = df_with_status_and_photo(filter_probables(df, only_probable=True), mercado)
    except Exception as e:
        st.error(f"Erro ao carregar Cartola: {e}")
        st.stop()

    # Auto-escalar Lógica
    if auto:
        team_auto, _ = build_team_greedy(df_base, formation=formacao_escolhida, budget=float(orcamento))
        st.session_state["picked"] = {}
        # Preencher os slots dinamicamente baseados na matriz da formação
        idx_tracker = {"ATA": 0, "MEI": 0, "ZAG": 0, "LAT": 0, "GOL": 0, "TEC": 0}
        for _, r in team_auto.iterrows():
            pos = r["posicao"]
            slot_key = f"{pos}-{idx_tracker[pos]}"
            st.session_state["picked"][slot_key] = int(r["athlete_id"])
            idx_tracker[pos] += 1

    tab_escalacao, tab_stats = st.tabs(["🧩 Campo", "📊 Mercado & Stats"])

    # ABA CAMPO (UI VISUAL)
    with tab_escalacao:
        col_campo, col_resumo = st.columns([2.5, 1])
        
        with col_campo:
            st.markdown('<div class="pitch-container">', unsafe_allow_html=True)
            
            # Renderiza as linhas do campo baseado na matriz FORMATION_ROWS
            layout = FORMATION_ROWS[formacao_escolhida]
            
            # Mapeia quantos de cada posição já foram renderizados
            count_tracker = {"ATA": 0, "MEI": 0, "ZAG": 0, "LAT": 0, "GOL": 0, "TEC": 0}
            
            for linha in layout:
                cols = st.columns(len(linha))
                for i, pos_alvo in enumerate(linha):
                    slot_key = f"{pos_alvo}-{count_tracker[pos_alvo]}"
                    count_tracker[pos_alvo] += 1
                    
                    with cols[i]:
                        id_selecionado = st.session_state["picked"].get(slot_key)
                        
                        if id_selecionado:
                            # Card Preenchido
                            jogador = df_base[df_base["athlete_id"] == id_selecionado].iloc[0]
                            st.markdown(f"""
                            <div class="cartola-card">
                                <img src="{jogador['foto_url']}">
                                <div class="pos-badge">{jogador['posicao']}</div>
                                <div class="name">{jogador['apelido']}</div>
                                <div class="price">C$ {jogador['preco']:.2f}</div>
                            </div>
                            """, unsafe_allow_html=True)
                            if st.button("Trocar", key=f"btn_{slot_key}"):
                                selecionar_jogador_modal(slot_key, pos_alvo, df_base)
                        else:
                            # Card Vazio
                            st.markdown(f"""
                            <div class="cartola-card" style="border-style: dashed;">
                                <div class="pos-badge" style="margin-top:0;">{pos_alvo}</div>
                                <div class="name" style="color:#64748b;">Slot Vazio</div>
                            </div>
                            """, unsafe_allow_html=True)
                            if st.button(f"+ Add {pos_alvo}", key=f"btn_{slot_key}"):
                                selecionar_jogador_modal(slot_key, pos_alvo, df_base)
                st.write("") # Espaçamento entre as linhas
            st.markdown('</div>', unsafe_allow_html=True)
            
        with col_resumo:
            st.subheader("Resumo do Time")
            ids_escolhidos = list(st.session_state["picked"].values())
            time_df = df_base[df_base["athlete_id"].isin(ids_escolhidos)]
            custo_total = time_df["preco"].sum() if not time_df.empty else 0.0
            
            st.metric("Custo do Time", f"C$ {custo_total:.2f}")
            st.metric("Saldo Restante", f"C$ {orcamento - custo_total:.2f}", delta_color="normal" if orcamento >= custo_total else "inverse")
            
            if orcamento < custo_total:
                st.error("Orçamento estourado!")

    # ABA STATS (Simplificada para manter foco no campo)
    with tab_stats:
        st.subheader("Atletas do Mercado")
        st.dataframe(df_base[["apelido", "clube", "posicao", "preco", "score_final", "status_nome"]], use_container_width=True, hide_index=True)

if __name__ == "__main__":
    main()
