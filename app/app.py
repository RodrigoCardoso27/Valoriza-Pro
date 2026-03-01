from __future__ import annotations

import sys
from pathlib import Path

# ===== Correção de Caminho (Streamlit Cloud) =====
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st
import pandas as pd

# Imports do seu backend
from cartola.client import CartolaClient
from cartola import storage
from cartola.analytics import make_dataframe, valuation_heuristic, filter_probables
from cartola.team_builder import build_team_greedy

st.set_page_config(page_title="Valoriza Pro - Oráculo", layout="centered", page_icon="⚽")

# ----------------------------
# CSS Minimalista e Focado
# ----------------------------
CSS = """
<style>
.stApp { background-color: #0d1117; color: #ffffff; }

/* Estilo dos Cards Gerados */
.jogador-card {
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #374151;
    border-radius: 10px;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 15px 10px;
    margin-bottom: 15px;
    box-shadow: 0 4px 6px rgba(0,0,0,0.3);
}
.jogador-card img {
    border-radius: 50%;
    width: 60px;
    height: 60px;
    object-fit: cover;
    border: 2px solid #22c55e;
    margin-bottom: 5px;
}
.jogador-card .pos {
    background-color: #22c55e;
    color: #000;
    font-size: 0.7rem;
    font-weight: bold;
    padding: 2px 8px;
    border-radius: 10px;
    margin-top: -15px;
}
.jogador-card .nome { font-size: 0.85rem; font-weight: bold; margin-top: 8px; text-align: center; }
.jogador-card .clube { font-size: 0.7rem; color: #94a3b8; }
.jogador-card .preco { font-size: 0.8rem; color: #22c55e; font-weight: bold; margin-top: 5px; }
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

def status_and_photo(df: pd.DataFrame, mercado_payload: dict) -> pd.DataFrame:
    athletes = mercado_payload.get("atletas") or mercado_payload.get("atleta") or []
    photo_map = {int(a.get("atleta_id") or a.get("id")): format_foto_url(a.get("foto")) for a in athletes if (a.get("atleta_id") or a.get("id"))}
    out = df.copy()
    if not out.empty:
        out["foto_url"] = out["athlete_id"].map(photo_map)
    return out

@st.cache_data(ttl=60)
def fetch_data():
    client = CartolaClient(base_url="https://api.cartolafc.globo.com")
    status = client.mercado_status()
    rodada = int(status.get("rodada_atual") or status.get("rodada") or 0)
    mercado = client.atletas_mercado()
    return rodada, status, mercado

# ----------------------------
# APP PRINCIPAL (O ORÁCULO)
# ----------------------------
def main():
    st.markdown("<h1 style='text-align: center;'>🪄 Valoriza Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #94a3b8;'>A inteligência artificial que escala seu time focando em pontuação e ganho de cartoletas.</p>", unsafe_allow_html=True)
    
    st.write("---")
    
    # Configurações do usuário
    col1, col2 = st.columns(2)
    with col1:
        orcamento = st.number_input("Seu Patrimônio (C$):", min_value=50.0, value=100.0, step=1.0)
    with col2:
        formacao = st.selectbox("Formação Tática:", ["4-3-3", "3-4-3", "4-4-2", "3-5-2"], index=0)

    st.write("")
    
    # O Grande Botão
    if st.button("🚀 Gerar Time Perfeito", type="primary", use_container_width=True):
        with st.spinner("Analisando rodada, calculando valorização e escalando..."):
            try:
                # 1. Coleta e prepara os dados
                rodada, status, mercado = fetch_data()
                df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
                df = valuation_heuristic(df) # Aplica a matemática de valorização
                df_base = status_and_photo(filter_probables(df, only_probable=True), mercado)
                
                # 2. IA escala o time (Greedy)
                time_ideal, saldo_sobra = build_team_greedy(df_base, formation=formacao, budget=float(orcamento))
                
                # 3. Exibe o resultado de forma organizada
                st.success(f"Time montado! Custo total: C$ {orcamento - saldo_sobra:.2f} | Sobrou: C$ {saldo_sobra:.2f}")
                
                # Renderiza os jogadores agrupados por posição
                posicoes_ordem = ["ATA", "MEI", "LAT", "ZAG", "GOL", "TEC"]
                
                for pos in posicoes_ordem:
                    jogadores_pos = time_ideal[time_ideal["posicao"] == pos]
                    if not jogadores_pos.empty:
                        st.markdown(f"### {pos}")
                        cols = st.columns(len(jogadores_pos))
                        for i, (_, jog) in enumerate(jogadores_pos.iterrows()):
                            with cols[i]:
                                st.markdown(f"""
                                <div class="jogador-card">
                                    <img src="{jog['foto_url']}">
                                    <div class="pos">{jog['posicao']}</div>
                                    <div class="nome">{jog['apelido']}</div>
                                    <div class="clube">{jog['clube']}</div>
                                    <div class="preco">C$ {jog['preco']:.2f}</div>
                                </div>
                                """, unsafe_allow_html=True)
                                
            except Exception as e:
                st.error(f"Ocorreu um erro ao processar os dados do Cartola: {e}")

if __name__ == "__main__":
    main()
