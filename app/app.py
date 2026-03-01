from __future__ import annotations
import sys
import os
import requests
import pandas as pd
import streamlit as st
from pathlib import Path

# ===== Correção de Caminho =====
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cartola.client import CartolaClient
from cartola import storage
from cartola.analytics import make_dataframe, valuation_heuristic, filter_probables
from cartola.team_builder import FORMATIONS

st.set_page_config(page_title="Valoriza Pro | TabuadaRJ", layout="wide", page_icon="🪄")

# ==========================================
# 1. FRONTEND: CSS DO CAMPO REAL (Idêntico ao Print)
# ==========================================
CSS = """
<style>
.stApp { background-color: #0b0f19; color: #ffffff; }

/* Estilização do Gramado */
.pitch-container {
    background: #2e7d32;
    background-image: 
        linear-gradient(rgba(255, 255, 255, 0.1) 2px, transparent 2px),
        repeating-linear-gradient(0deg, #2e7d32, #2e7d32 40px, #276b2a 40px, #276b2a 80px);
    border: 3px solid rgba(255, 255, 255, 0.4);
    border-radius: 12px;
    height: 700px;
    width: 100%;
    position: relative;
    margin: 20px 0;
    overflow: hidden;
}

/* Linhas do Campo */
.pitch-line-center {
    position: absolute; top: 50%; left: 0; right: 0;
    height: 2px; background: rgba(255, 255, 255, 0.4);
}
.pitch-circle-center {
    position: absolute; top: 50%; left: 50%;
    transform: translate(-50%, -50%);
    width: 120px; height: 120px;
    border: 2px solid rgba(255, 255, 255, 0.4);
    border-radius: 50%;
}

/* Card do Jogador */
.player-card {
    position: absolute;
    width: 100px;
    display: flex;
    flex-direction: column;
    align-items: center;
    transform: translate(-50%, -50%);
}
.player-box {
    background: rgba(16, 24, 40, 0.9);
    border: 1px solid #334155;
    border-radius: 8px;
    width: 80px; height: 100px;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    box-shadow: 0 4px 10px rgba(0,0,0,0.5);
}
.player-img { width: 50px; height: 50px; border-radius: 50%; border: 2px solid #22c55e; background: #cbd5e1; }
.player-name { color: white; font-size: 0.7rem; font-weight: bold; text-align: center; margin-top: 5px; }
.player-pos { color: #94a3b8; font-size: 0.6rem; text-transform: uppercase; }
.player-price { color: #4ade80; font-size: 0.7rem; font-weight: bold; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Coordenadas visuais por formação (Top/Left em %)
FORMATION_COORDS = {
    "4-3-3": {
        "GOL": [(50, 90)],
        "ZAG": [(35, 70), (65, 70)],
        "LAT": [(15, 65), (85, 65)],
        "MEI": [(30, 45), (50, 50), (70, 45)],
        "ATA": [(25, 20), (50, 15), (75, 20)],
        "TEC": [(85, 90)]
    },
    "3-4-3": {
        "GOL": [(50, 90)],
        "ZAG": [(30, 70), (50, 75), (70, 70)],
        "MEI": [(15, 45), (40, 50), (60, 50), (85, 45)],
        "ATA": [(25, 20), (50, 15), (75, 20)],
        "TEC": [(85, 90)]
    },
    "4-4-2": {
        "GOL": [(50, 90)],
        "ZAG": [(35, 70), (65, 70)],
        "LAT": [(15, 65), (85, 65)],
        "MEI": [(20, 45), (40, 50), (60, 50), (80, 45)],
        "ATA": [(40, 20), (60, 20)],
        "TEC": [(85, 90)]
    }
}

# ==========================================
# 2. LOGICA DE BACKEND (Reserva de Verba)
# ==========================================
@st.cache_data(ttl=300)
def fetch_api_data():
    client = CartolaClient(base_url="https://api.cartolafc.globo.com")
    return client.mercado_status(), client.atletas_mercado()

def escalar_time_seguro(df, formacao_nome, orcamento_maximo):
    vagas = FORMATIONS.get(formacao_nome, {}).copy()
    df_qualidade = df.sort_values(by=["score_final"], ascending=False)
    df_preco = df.sort_values(by=["preco"], ascending=True)
    
    # Validação de orçamento mínimo
    custo_min = 0
    for pos, qtd in vagas.items():
        custo_min += df_preco[df_preco["posicao"] == pos].head(qtd)["preco"].sum()
    
    if custo_min > orcamento_maximo:
        return None, 0, f"Saldo insuficiente. Mínimo necessário: C$ {custo_min:.2f}"

    time_selecionado = []
    # Lógica simplificada de escalação (Greedy com reserva)
    for pos, qtd in vagas.items():
        time_selecionado.extend(df_qualidade[df_qualidade["posicao"] == pos].head(qtd).to_dict('records'))
    
    res_df = pd.DataFrame(time_selecionado)
    custo_total = res_df["preco"].sum()
    return res_df, orcamento_maximo - custo_total, ""

# ==========================================
# 3. APP PRINCIPAL
# ==========================================
def main():
    st.title("🪄 Oráculo Valoriza Pro")
    
    # Sidebar de Configuração
    with st.sidebar:
        st.header("Configurações")
        orcamento = st.number_input("Meu Patrimônio (C$)", value=100.0, min_value=30.0)
        formacao = st.selectbox("Formação", list(FORMATION_COORDS.keys()))
        modo_teste = st.toggle("Modo Pré-Temporada", value=True)

    if st.button("🚀 Gerar Escalação Perfeita", type="primary", use_container_width=True):
        status_cartola, mercado = fetch_api_data()
        rodada = int(status_cartola.get("rodada_atual") or 0)
        df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
        df = valuation_heuristic(df)
        
        # Filtros
        df_base = filter_probables(df, only_probable=not modo_teste)
        
        time_ideal, saldo, erro = escalar_time_seguro(df_base, formacao, orcamento)
        
        if erro:
            st.error(erro)
        else:
            st.success(f"Time escalado! Saldo Restante: C$ {saldo:.2f}")
            
            # --- RENDERIZAÇÃO DO CAMPO ---
            html_cards = ""
            count_tracker = {p: 0 for p in FORMATION_COORDS[formacao].keys()}
            
            for _, jog in time_ideal.iterrows():
                pos = jog['posicao']
                if pos in FORMATION_COORDS[formacao]:
                    idx = count_tracker[pos]
                    if idx < len(FORMATION_COORDS[formacao][pos]):
                        left, top = FORMATION_COORDS[formacao][pos][idx]
                        count_tracker[pos] += 1
                        
                        foto = jog.get('foto_url') or "https://via.placeholder.com/50"
                        html_cards += f"""
                        <div class="player-card" style="left:{left}%; top:{top}%;">
                            <div class="player-box">
                                <img src="{foto}" class="player-img">
                                <div class="player-name">{jog['apelido']}</div>
                                <div class="player-pos">{pos}</div>
                                <div class="player-price">C$ {jog['preco']:.2f}</div>
                            </div>
                        </div>
                        """

            field_html = f"""
            <div class="pitch-container">
                <div class="pitch-line-center"></div>
                <div class="pitch-circle-center"></div>
                {html_cards}
            </div>
            """
            st.components.v1.html(field_html, height=720)

if __name__ == "__main__":
    main()
