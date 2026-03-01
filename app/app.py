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
from cartola.team_builder import FORMATIONS

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

/* Cards dos Jogadores */
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
# 2. MICROSERVIÇOS & LOGICA (Backend)
# ==========================================
def get_secret(key: str) -> str | None:
    try: return str(st.secrets[key]) if key in st.secrets else os.getenv(key)
    except: return os.getenv(key)

@st.cache_data(ttl=300)
def api_1_cartola():
    client = CartolaClient(base_url="https://api.cartolafc.globo.com")
    return client.mercado_status(), client.atletas_mercado()

@st.cache_data(ttl=3600)
def api_2_tabela_redundante() -> pd.DataFrame | None:
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

def escalar_time_seguro(df, formacao_nome, orcamento_maximo):
    """Algoritmo de escalação com reserva de verba para garantir a montagem com orçamentos baixos."""
    vagas = FORMATIONS.get(formacao_nome, {}).copy()
    
    # Prepara as listas (uma focada na nota, outra focada no preço mínimo)
    df_qualidade = df.sort_values(by=["score_final"], ascending=False)
    df_preco = df.sort_values(by=["preco"], ascending=True)
    
    # 1. Reserva o dinheiro dos jogadores mais baratos do mercado para cada vaga
    custo_minimo_posicao = {}
    for pos, qtd in vagas.items():
        jogadores_pos = df_preco[df_preco["posicao"] == pos]
        if len(jogadores_pos) < qtd:
            return None, 0 # Faltou jogador no mercado pra essa posição
        custo_minimo_posicao[pos] = jogadores_pos.head(qtd)["preco"].tolist()
        
    custo_minimo_total = sum(sum(precos) for precos in custo_minimo_posicao.values())
    
    if custo_minimo_total > orcamento_maximo:
        return None, 0 # O orçamento é menor do que o time mais barato possível
        
    time_selecionado = []
    custo_atual = 0.0
    
    # 2. Escala o time substituindo a reserva pelo jogador bom, se couber no bolso
    for pos, qtd in vagas.items():
        selecionados_pos = 0
        for _, jog in df_qualidade[df_qualidade["posicao"] == pos].iterrows():
            if selecionados_pos >= qtd:
                break
                
            preco_jog = float(jog["preco"])
            id_jog = jog["athlete_id"]
            
            if any(j["athlete_id"] == id_jog for j in time_selecionado):
                continue
                
            preco_barato_reservado = custo_minimo_posicao[pos][selecionados_pos]
            custo_simulado = custo_atual + preco_jog + (custo_minimo_total - preco_barato_reservado)
            
            if custo_simulado <= orcamento_maximo:
                time_selecionado.append(jog)
                custo_atual += preco_jog
                custo_minimo_total -= preco_barato_reservado
                selecionados_pos += 1
                
    if len(time_selecionado) < sum(vagas.values()):
        return None, 0 # Falha de segurança
        
    time_df = pd.DataFrame(time_selecionado)
    saldo = orcamento_maximo - custo_atual
    return time_df, saldo

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
        orcamento = c1.number_input("💸 Seu Patrimônio (C$):", min_value=30.0, value=80.0, step=1.0, help="Insira suas cartoletas atuais. O algoritmo ajustará as contratações ao seu bolso.")
        formacao = c2.selectbox("📐 Formação Tática:", ["4-3-3", "3-4-3", "4-4-2", "3-5-2"], index=0, help="A formação impacta na distribuição do orçamento.")

        st.write("")
        if st.button("🚀 Gerar Time Perfeito", type="primary", use_container_width=True):
            
            # Novo visual de carregamento com etapas detalhadas
            with st.status("Iniciando a Inteligência do Oráculo...", expanded=True) as status_box:
                try:
                    st.write("📡 Conectando aos servidores da Globo...")
                    status_cartola, mercado = api_1_cartola()
                    
                    st.write("⚽ Buscando artilheiros do Brasileirão...")
                    artilheiros_reais = api_3_artilheiros()
                    
                    rodada = int(status_cartola.get("rodada_atual") or 0)
                    df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
                    
                    if df is None or df.empty:
                        status_box.update(label="Falha na leitura", state="error", expanded=False)
                        st.warning("⚠️ O mercado do Cartola está fechado ou sem dados no momento.")
                        st.stop()
                    
                    st.write("🧮 Calculando algoritmo de valorização de patrimônio...")
                    df = valuation_heuristic(df)
                    
                    if artilheiros_reais and 'score_final' in df.columns:
                        for artilheiro in artilheiros_reais:
                            df.loc[df['apelido'].str.contains(artilheiro, case=False, na=False), 'score_final'] *= 1.2
                    
                    photo_map = {int(a.get("atleta_id", 0)): format_foto(a.get("foto")) for a in mercado.get("atletas", [])}
                    df["foto_url"] = df["athlete_id"].map(photo_map)
                    df_base = filter_probables(df, only_probable=True)
                    
                    if df_base.empty:
                        status_box.update(label="Sem atletas", state="error", expanded=False)
                        st.warning("⚠️ Não há jogadores prováveis no momento.")
                        st.stop()
                    
                    st.write("🤖 Otimizando verba e fechando contratações...")
                    time_ideal, saldo_sobra = escalar_time_seguro(df_base, formacao_nome=formacao, orcamento_maximo=float(orcamento))
                    
                    if time_ideal is None or time_ideal.empty:
                        status_box.update(label="Orçamento insuficiente", state="error", expanded=False)
                        st.error("❌ O seu patrimônio atual é menor que o custo do time mais barato possível para esta formação.")
                        st.stop()

                    status_box.update(label="Time escalado com sucesso!", state="complete", expanded=False)
                    
                    # Exibe o resumo financeiro elegantemente
                    custo_time = orcamento - saldo_sobra
                    m1, m2 = st.columns(2)
                    m1.metric("💰 Custo do Time", f"C$ {custo_time:.2f}")
                    m2.metric("🏦 Saldo Restante", f"C$ {saldo_sobra:.2f}", delta=f"{saldo_sobra:.2f} livres", delta_color="normal")
                    st.write("---")

                    # Renderização do Gramado
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
                            st.write("") 
                    st.markdown('</div>', unsafe_allow_html=True)
                    
                except Exception as e:
                    status_box.update(label="Erro no servidor", state="error", expanded=True)
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
