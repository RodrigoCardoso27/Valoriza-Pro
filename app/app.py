from __future__ import annotations

import sys
import os
import requests
import pandas as pd
import streamlit as st
from pathlib import Path

# ===== Correção de Caminho (Streamlit Cloud) =====
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Imports do seu backend local
from cartola.client import CartolaClient
from cartola import storage
from cartola.analytics import make_dataframe, valuation_heuristic, filter_probables
from cartola.team_builder import build_team_greedy

st.set_page_config(page_title="Valoriza Pro | TabuadaRJ", layout="wide", page_icon="🪄")

# ==========================================
# 1. FRONTEND: CSS Premium
# ==========================================
CSS = """
<style>
/* Tema Geral Dark/Neon */
.stApp { background-color: #0b0f19; color: #e2e8f0; font-family: 'Inter', sans-serif; }

/* Header estilizado */
.hero-box {
    background: linear-gradient(90deg, #1e293b 0%, #0f172a 100%);
    padding: 2rem;
    border-radius: 16px;
    border-left: 5px solid #22c55e;
    margin-bottom: 2rem;
    box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.5);
}
.hero-title { margin: 0; font-size: 2.5rem; font-weight: 900; color: #ffffff; }
.hero-subtitle { margin: 5px 0 0 0; color: #94a3b8; font-size: 1.1rem; }

/* Botão Mágico (Oráculo) */
div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #16a34a 0%, #22c55e 100%);
    color: white;
    font-weight: 800;
    font-size: 1.2rem;
    padding: 1rem;
    border: none;
    border-radius: 12px;
    box-shadow: 0 4px 14px 0 rgba(34, 197, 94, 0.39);
    transition: all 0.3s ease;
}
div.stButton > button[kind="primary"]:hover {
    transform: translateY(-2px);
    box-shadow: 0 6px 20px 0 rgba(34, 197, 94, 0.5);
}

/* O Gramado */
.pitch-container {
    background: repeating-linear-gradient(0deg, #1b4322, #1b4322 40px, #16381c 40px, #16381c 80px);
    border: 2px solid rgba(255, 255, 255, 0.1);
    border-radius: 16px;
    padding: 30px 15px;
    box-shadow: inset 0px 0px 50px rgba(0,0,0,0.8);
}

/* Cards dos Jogadores - Estilo Cartola Moderno */
.cartola-card {
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-radius: 12px;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 15px 10px;
    margin-bottom: 15px;
    position: relative;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.5);
    transition: transform 0.2s;
}
.cartola-card:hover { transform: scale(1.05); border-color: #22c55e; }
.cartola-card img {
    border-radius: 50%;
    width: 65px;
    height: 65px;
    object-fit: cover;
    border: 2px solid #22c55e;
    background-color: #cbd5e1;
    margin-bottom: 8px;
}
.cartola-card .pos-badge {
    background-color: #22c55e;
    color: #020617;
    font-size: 0.75rem;
    font-weight: 900;
    padding: 3px 10px;
    border-radius: 20px;
    position: absolute;
    top: -10px;
    box-shadow: 0 2px 4px rgba(0,0,0,0.3);
}
.cartola-card .name { font-size: 0.85rem; font-weight: 800; text-align: center; color: #f8fafc; line-height: 1.2; }
.cartola-card .clube { font-size: 0.7rem; color: #94a3b8; text-transform: uppercase; margin-bottom: 5px; }
.cartola-card .price { font-size: 0.85rem; color: #4ade80; font-weight: 800; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ==========================================
# 2. MICROSERVIÇOS (APIs Independentes)
# ==========================================
def get_secret(key: str) -> str | None:
    try: return str(st.secrets[key]) if key in st.secrets else os.getenv(key)
    except: return os.getenv(key)

@st.cache_data(ttl=300)
def api_1_cartola():
    """Busca Preços e Status Oficial do Game"""
    client = CartolaClient(base_url="https://api.cartolafc.globo.com")
    return client.mercado_status(), client.atletas_mercado()

@st.cache_data(ttl=3600)
def api_2_tabela_redundante() -> pd.DataFrame | None:
    """Tenta a API oficial, se falhar, faz Web Scraping de failover"""
    token = get_secret("FOOTBALL_DATA_TOKEN")
    if token:
        try:
            url = "https://api.football-data.org/v4/competitions/BSA/standings"
            r = requests.get(url, headers={"X-Auth-Token": token}, timeout=10)
            if r.status_code == 200:
                table = r.json().get("standings", [])[0].get("table", [])
                rows = [{"Pos": row.get("position"), "Time": row.get("team", {}).get("name"), 
                         "Pts": row.get("points"), "V": row.get("won"), "SG": row.get("goalDifference")} for row in table]
                return pd.DataFrame(rows)
        except: pass
    
    # PLANO B (Failover): Scraping da Wikipedia
    try:
        url_fallback = "https://pt.wikipedia.org/wiki/Campeonato_Brasileiro_de_Futebol_de_2025_-_S%C3%A9rie_A"
        tabelas = pd.read_html(url_fallback, match="Classificação")
        if tabelas:
            df = tabelas[0]
            return pd.DataFrame({
                "Pos": df.iloc[:, 0], "Time": df.iloc[:, 1], "Pts": df.iloc[:, 2],
                "V": df.iloc[:, 4], "SG": df.iloc[:, 8]
            })
    except: return None

@st.cache_data(ttl=3600)
def api_3_artilheiros() -> list:
    """Busca os matadores. Retorna lista de nomes."""
    token = get_secret("FOOTBALL_DATA_TOKEN")
    if not token: return []
    try:
        url = "https://api.football-data.org/v4/competitions/BSA/scorers"
        r = requests.get(url, headers={"X-Auth-Token": token}, timeout=10)
        if r.status_code == 200:
            scorers = r.json().get("scorers", [])
            return [s.get("player", {}).get("name") for s in scorers]
    except: pass
    return []

def format_foto(raw: str | None) -> str:
    if not raw: return "https://s2.glbimg.com/a4E1AXX0iV9I9K_4v-d_XyUv-0I=/140x140/smart/https://s3.glbimg.com/v1/AUTH_58d78b787ec34892b5aaa0c7a14616a6/placeholder/perfil.png"
    return "https:" + raw.replace("FORMATO", "140x140") if raw.startswith("//") else raw.replace("FORMATO", "140x140")

# ==========================================
# 3. INTERFACE PRINCIPAL
# ==========================================
def main():
    st.markdown("""
    <div class="hero-box">
        <h1 class="hero-title">🪄 Valoriza Pro by TabuadaRJ</h1>
        <p class="hero-subtitle">Inteligência de Dados. Escalação automatizada cruzando estatísticas reais com o Cartola FC.</p>
    </div>
    """, unsafe_allow_html=True)
    
    tab_oraculo, tab_brasileirao = st.tabs(["🚀 O Oráculo", "📊 Base de Dados Real"])
    
    with tab_oraculo:
        c1, c2 = st.columns(2)
        orcamento = c1.number_input("💸 Seu Patrimônio (C$):", min_value=50.0, value=100.0, step=1.0)
        formacao = c2.selectbox("📐 Formação Tática:", ["4-3-3", "3-4-3", "4-4-2", "3-5-2"], index=0)

        st.write("")
        if st.button("🚀 Gerar Time Perfeito", type="primary", use_container_width=True):
            with st.spinner("Conectando aos microserviços e analisando dados..."):
                try:
                    # Consome as APIs
                    status, mercado = api_1_cartola()
                    artilheiros_reais = api_3_artilheiros()
                    
                    rodada = int(status.get("rodada_atual") or 0)
                    df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
                    
                    if df is None or df.empty:
                        st.warning("⚠️ O mercado do Cartola está fechado ou sem dados no momento.")
                        st.stop()
                    
                    # Motor matemático base
                    df = valuation_heuristic(df)
                    
                    # 🧠 INTELIGÊNCIA: Cruzamento de Dados (Bônus para Artilheiros)
                    if artilheiros_reais and 'score_final' in df.columns:
                        for artilheiro in artilheiros_reais:
                            # Se o nome do artilheiro bater com o apelido do Cartola, ganha 20% de bônus no score
                            df.loc[df['apelido'].str.contains(artilheiro, case=False, na=False), 'score_final'] *= 1.2
                    
                    # Prepara fotos e filtra prováveis
                    photo_map = {int(a.get("atleta_id", 0)): format_foto(a.get("foto")) for a in mercado.get("atletas", [])}
                    df["foto_url"] = df["athlete_id"].map(photo_map)
                    df_base = filter_probables(df, only_probable=True)
                    
                    if df_base.empty:
                        st.warning("⚠️ Não há jogadores prováveis no momento.")
                        st.stop()
                    
                    # Escalação IA
                    time_ideal, saldo_sobra = build_team_greedy(df_base, formation=formacao, budget=float(orcamento))
                    
                    if time_ideal is None or time_ideal.empty:
                        st.error("❌ Orçamento baixo demais para formar um time.")
                        st.stop()

                    # Renderização do Gramado
                    st.success(f"✅ Análise concluída! Custo Total: C$ {orcamento - saldo_sobra:.2f} | Saldo Restante: C$ {saldo_sobra:.2f}")
                    st.markdown('<div class="pitch-container">', unsafe_allow_html=True)
                    
                    ordem_campo = ["ATA", "MEI", "LAT", "ZAG", "GOL", "TEC"]
                    for pos in ordem_campo:
                        jogadores_pos = time_ideal[time_ideal["posicao"] == pos]
                        if not jogadores_pos.empty:
                            cols = st.columns(len(jogadores_pos))
                            for i, (_, jog) in enumerate(jogadores_pos.iterrows()):
                                with cols[i]:
                                    st.markdown(f"""
                                    <div class="cartola-card">
                                        <div class="pos-badge">{jog.get('posicao', pos)}</div>
                                        <img src="{jog.get('foto_url', '')}">
                                        <div class="name">{jog.get('apelido', 'Desc')}</div>
                                        <div class="clube">{jog.get('clube', '---')}</div>
                                        <div class="price">C$ {jog.get('preco', 0.0):.2f}</div>
                                    </div>
                                    """, unsafe_allow_html=True)
                            st.write("") # Espaço entre as linhas do campo
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                except Exception as e:
                    st.error(f"Erro na execução da análise: {e}")

    with tab_brasileirao:
        st.subheader("🏆 Integração: Tabela do Brasileirão")
        st.write("Dados puxados em tempo real (com sistema de failover ativo).")
        df_tabela = api_2_tabela_redundante()
        if df_tabela is not None and not df_tabela.empty:
            st.dataframe(df_tabela, use_container_width=True, hide_index=True)
        else:
            st.info("Aguardando início do campeonato ou atualização das fontes de dados.")

if __name__ == "__main__":
    main()
