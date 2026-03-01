from __future__ import annotations

import sys
import os
from pathlib import Path
import requests

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

st.set_page_config(page_title="Valoriza Pro - Oráculo", layout="wide", page_icon="⚽")

# ----------------------------
# CSS Minimalista e Focado
# ----------------------------
CSS = """
<style>
.stApp { background-color: #0d1117; color: #ffffff; }
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
# Camada de Integração de APIs
# ----------------------------
def get_secret_or_env(key: str) -> str | None:
    try:
        if key in st.secrets: return str(st.secrets[key])
    except Exception: pass
    return os.getenv(key)

@st.cache_data(ttl=300) # Cache de 5 minutos
def fetch_cartola():
    client = CartolaClient(base_url="https://api.cartolafc.globo.com")
    status = client.mercado_status()
    mercado = client.atletas_mercado()
    return status, mercado

@st.cache_data(ttl=3600) # Cache de 1 hora para economizar a cota da API
def fetch_brasileirao_tabela() -> pd.DataFrame | None:
    token = get_secret_or_env("FOOTBALL_DATA_TOKEN")
    if not token: return None
    
    url = "https://api.football-data.org/v4/competitions/BSA/standings"
    try:
        r = requests.get(url, headers={"X-Auth-Token": token}, timeout=15)
        r.raise_for_status()
        data = r.json()
        table = data.get("standings", [])[0].get("table", [])
        
        rows = []
        for row in table:
            rows.append({
                "Pos": row.get("position"),
                "Time": row.get("team", {}).get("name"),
                "Pts": row.get("points"),
                "PJ": row.get("playedGames"),
                "V": row.get("won"),
                "E": row.get("draw"),
                "D": row.get("lost"),
                "SG": row.get("goalDifference")
            })
        return pd.DataFrame(rows)
    except Exception:
        return None

# Helpers de UI
def format_foto_url(raw: str | None, size: str = "140x140") -> str | None:
    if not raw: return "https://s2.glbimg.com/a4E1AXX0iV9I9K_4v-d_XyUv-0I=/140x140/smart/https://s3.glbimg.com/v1/AUTH_58d78b787ec34892b5aaa0c7a14616a6/placeholder/perfil.png"
    url = raw.replace("{FORMATO}", size).replace("FORMATO", size)
    return "https:" + url if url.startswith("//") else url

# ----------------------------
# APP PRINCIPAL
# ----------------------------
def main():
    st.markdown("<h1 style='text-align: center;'>🪄 Valoriza Pro</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #94a3b8;'>Inteligência em dados. Cartola FC + Estatísticas Reais.</p>", unsafe_allow_html=True)
    
    tab_oraculo, tab_stats = st.tabs(["🚀 O Oráculo (Escalação)", "🏆 Contexto do Brasileirão"])
    
    # ==========================================
    # ABA 1: O ORÁCULO (Motor do Cartola)
    # ==========================================
    with tab_oraculo:
        col1, col2 = st.columns(2)
        with col1: orcamento = st.number_input("Seu Patrimônio (C$):", min_value=50.0, value=100.0, step=1.0)
        with col2: formacao = st.selectbox("Formação Tática:", ["4-3-3", "3-4-3", "4-4-2", "3-5-2"], index=0)

        st.write("")
        if st.button("🚀 Gerar Time Perfeito", type="primary", use_container_width=True):
            with st.spinner("Integrando APIs e calculando valorização..."):
                try:
                    status, mercado = fetch_cartola()
                    rodada = int(status.get("rodada_atual") or 0)
                    df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
                    
                    if df is None or df.empty:
                        st.warning("⚠️ O mercado do Cartola não retornou atletas ativos.")
                        st.stop()
                        
                    df = valuation_heuristic(df)
                    
                    # Preparando dados e fotos
                    athletes = mercado.get("atletas", [])
                    photo_map = {int(a.get("atleta_id", 0)): format_foto_url(a.get("foto")) for a in athletes}
                    df["foto_url"] = df["athlete_id"].map(photo_map)
                    
                    df_base = filter_probables(df, only_probable=True)
                    
                    if df_base.empty:
                        st.warning("⚠️ Não há jogadores prováveis no momento.")
                        st.stop()
                    
                    time_ideal, saldo_sobra = build_team_greedy(df_base, formation=formacao, budget=float(orcamento))
                    
                    if time_ideal is None or time_ideal.empty:
                        st.error("❌ A IA não conseguiu montar o time com esse orçamento.")
                        st.stop()
                        
                    st.success(f"✅ Time gerado! Custo: C$ {orcamento - saldo_sobra:.2f} | Sobrou: C$ {saldo_sobra:.2f}")
                    
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
                                        <div class="nome">{jog.get('apelido', 'Desc')}</div>
                                        <div class="clube">{jog.get('clube', '-')}</div>
                                        <div class="preco">C$ {jog.get('preco', 0.0):.2f}</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"Erro no processamento: {e}")

    # ==========================================
    # ABA 2: APIs EXTERNAS (Brasileirão Real)
    # ==========================================
    with tab_stats:
        st.subheader("📊 Classificação Atualizada")
        st.write("Dados puxados da API `football-data.org` para embasar as escolhas do algoritmo.")
        
        df_tabela = fetch_brasileirao_tabela()
        
        if df_tabela is not None and not df_tabela.empty:
            st.dataframe(df_tabela, use_container_width=True, hide_index=True)
        else:
            st.info("⚠️ Dados da tabela indisponíveis. Verifique se a variável `FOOTBALL_DATA_TOKEN` está configurada nos Secrets do Streamlit.")

if __name__ == "__main__":
    main()
