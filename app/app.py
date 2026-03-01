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
                
                # TRAVA 1: Verifica se o Cartola retornou dados
                if df is None or df.empty:
                    st.warning("⚠️ O mercado do Cartola não retornou atletas. Ele pode estar fechado ou em manutenção.")
                    st.stop()
                    
                df = valuation_heuristic(df)
                
                # Para testar fora de temporada, você pode mudar only_probable para False temporariamente
                df_base = status_and_photo(filter_probables(df, only_probable=True), mercado)
                
                # TRAVA 2: Verifica se sobrou alguém após filtrar os prováveis
                if df_base.empty:
                    st.warning("⚠️ Não há nenhum jogador com status 'Provável' no momento (comum quando não há rodada próxima).")
                    st.stop()
                
                # 2. IA escala o time
                time_ideal, saldo_sobra = build_team_greedy(df_base, formation=formacao, budget=float(orcamento))
                
                # TRAVA 3: Verifica se a IA conseguiu montar o time
                if time_ideal is None or time_ideal.empty:
                    st.error("❌ A IA não conseguiu escalar ninguém. O orçamento pode estar muito baixo para os jogadores disponíveis.")
                    st.stop()
                
                # Fallback de segurança: se a coluna se chamar 'posicao_id' em vez de 'posicao'
                if "posicao" not in time_ideal.columns and "posicao_id" in time_ideal.columns:
                    mapa_pos = {1: "GOL", 2: "LAT", 3: "ZAG", 4: "MEI", 5: "ATA", 6: "TEC"}
                    time_ideal["posicao"] = time_ideal["posicao_id"].map(mapa_pos)

                # 3. Exibe o resultado de forma organizada
                st.success(f"Time montado! Custo total: C$ {orcamento - saldo_sobra:.2f} | Sobrou: C$ {saldo_sobra:.2f}")
                
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
                                    <img src="{jog.get('foto_url', '')}">
                                    <div class="pos">{jog.get('posicao', pos)}</div>
                                    <div class="nome">{jog.get('apelido', 'Desconhecido')}</div>
                                    <div class="clube">{jog.get('clube', '-')}</div>
                                    <div class="preco">C$ {jog.get('preco', 0.0):.2f}</div>
                                </div>
                                """, unsafe_allow_html=True)
                                
            except Exception as e:
                st.error(f"Ocorreu um erro interno ao processar os dados: {e}")

if __name__ == "__main__":
    main()
