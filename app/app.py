from __future__ import annotations
import sys
import os
import requests
import pandas as pd
import streamlit as st
from pathlib import Path

# ===== Path Fix (Streamlit Cloud) =====
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cartola.client import CartolaClient
from cartola import storage
from cartola.analytics import make_dataframe, valuation_heuristic, filter_probables
from cartola.team_builder import FORMATIONS

st.set_page_config(page_title="Valoriza Pro | TabuadaRJ", layout="wide", page_icon="🪄")

# ==========================================
# 1. CSS PREMIUM: CAMPO EM PERSPECTIVA
# ==========================================
CSS = """
<style>
.stApp { background-color: #0b0f19; color: #ffffff; }

/* Gramado com Perspectiva Estilo Cartola */
.pitch-container {
    background: #2e7d32;
    background-image: 
        linear-gradient(rgba(255, 255, 255, 0.1) 2px, transparent 2px),
        repeating-linear-gradient(0deg, #2e7d32, #2e7d32 40px, #276b2a 40px, #276b2a 80px);
    border: 3px solid rgba(255, 255, 255, 0.4);
    border-radius: 12px;
    height: 750px;
    width: 100%;
    position: relative;
    margin: 20px 0;
    overflow: hidden;
    box-shadow: inset 0px 0px 100px rgba(0,0,0,0.5);
}

/* Linhas do Campo */
.pitch-line-center { position: absolute; top: 50%; left: 0; right: 0; height: 2px; background: rgba(255, 255, 255, 0.3); }
.pitch-circle-center { 
    position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: 120px; height: 120px; border: 2px solid rgba(255, 255, 255, 0.3); border-radius: 50%; 
}

/* Card do Jogador (Slot) */
.player-slot {
    position: absolute;
    width: 90px;
    display: flex;
    flex-direction: column;
    align-items: center;
    transform: translate(-50%, -50%);
    transition: all 0.3s ease;
}

.card-box {
    background: linear-gradient(180deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-radius: 8px;
    width: 85px; padding: 8px 4px;
    display: flex; flex-direction: column;
    align-items: center;
    box-shadow: 0 8px 16px rgba(0,0,0,0.6);
}

.card-box img { width: 55px; height: 55px; border-radius: 50%; border: 2px solid #22c55e; background: #475569; margin-bottom: 4px; }
.card-name { font-size: 0.75rem; font-weight: 800; text-align: center; color: #f8fafc; line-height: 1; margin-bottom: 2px; }
.card-info { font-size: 0.6rem; color: #94a3b8; text-transform: uppercase; }
.card-price { font-size: 0.75rem; color: #4ade80; font-weight: 800; margin-top: 2px; }

.pos-label {
    background: #22c55e; color: #020617;
    font-size: 0.65rem; font-weight: 900;
    padding: 1px 6px; border-radius: 10px;
    position: absolute; top: -10px; z-index: 10;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Coordenadas Visuais (Ajustadas para 3-4-3 do print)
FORMATION_COORDS = {
    "3-4-3": {
        "ATA": [(20, 15), (50, 12), (80, 15)],
        "MEI": [(15, 38), (38, 42), (62, 42), (85, 38)],
        "ZAG": [(25, 68), (50, 72), (75, 68)],
        "GOL": [(50, 90)],
        "TEC": [(85, 90)]
    },
    "4-3-3": {
        "ATA": [(20, 15), (50, 12), (80, 15)],
        "MEI": [(25, 42), (50, 45), (75, 42)],
        "LAT": [(12, 65), (88, 65)],
        "ZAG": [(38, 70), (62, 70)],
        "GOL": [(50, 90)],
        "TEC": [(85, 90)]
    }
}

# ==========================================
# 2. LÓGICA DE BACKEND (Blindada contra Erros)
# ==========================================
@st.cache_data(ttl=300)
def fetch_api_data():
    try:
        client = CartolaClient(base_url="https://api.cartolafc.globo.com")
        return client.mercado_status(), client.atletas_mercado()
    except:
        return {}, {}

def escalar_time_seguro(df, formacao_nome, orcamento_maximo):
    """Garante a montagem do time sem KeyError e respeitando o saldo."""
    vagas = FORMATIONS.get(formacao_nome, {}).copy()
    
    # Se o DF estiver vazio ou sem a coluna preco, aborta com erro amigável
    if df.empty or "preco" not in df.columns:
        return None, 0, "Nenhum jogador disponível no mercado com os filtros atuais."

    df_qualidade = df.sort_values(by=["score_final"], ascending=False)
    df_preco = df.sort_values(by=["preco"], ascending=True)
    
    # Validação financeira básica
    custo_min = 0
    for pos, qtd in vagas.items():
        subset = df_preco[df_preco["posicao"] == pos]
        if len(subset) < qtd:
            return None, 0, f"Não há jogadores suficientes para a posição {pos}."
        custo_min += subset.head(qtd)["preco"].sum()
    
    if custo_min > orcamento_maximo:
        return None, 0, f"Saldo insuficiente para o time mais barato (Mínimo: C$ {custo_min:.2f})."

    # Montagem do Time
    time_selecionado = []
    for pos, qtd in vagas.items():
        time_selecionado.extend(df_qualidade[df_qualidade["posicao"] == pos].head(qtd).to_dict('records'))
    
    res_df = pd.DataFrame(time_selecionado)
    saldo_final = orcamento_maximo - res_df["preco"].sum()
    return res_df, saldo_final, ""

# ==========================================
# 3. INTERFACE PRINCIPAL
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center;'>🪄 Oráculo Valoriza Pro</h1>", unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("⚙️ Painel do Técnico")
        orcamento = st.number_input("Meu Patrimônio (C$)", value=100.0, min_value=30.0)
        formacao = st.selectbox("Formação Tática", list(FORMATION_COORDS.keys()))
        # Importante: Como é março, o padrão deve ser False para aparecerem jogadores
        modo_teste = st.toggle("Modo Pré-Temporada (Ver todos os atletas)", value=True)

    if st.button("🚀 Gerar Escalação Perfeita", type="primary", use_container_width=True):
        with st.status("Processando dados...", expanded=False) as status:
            status.write("📡 Conectando à API da Globo...")
            status_cartola, mercado = fetch_api_data()
            
            rodada = int(status_cartola.get("rodada_atual") or 0)
            df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
            df = valuation_heuristic(df)
            
            status.write("🤖 Filtrando melhores opções...")
            # only_probable=not modo_teste (Se modo_teste on, mostra tudo)
            df_base = filter_probables(df, only_probable=not modo_teste)
            
            time_ideal, saldo, erro = escalar_time_seguro(df_base, formacao, orcamento)
            
            if erro:
                status.update(label="Falha na Escalação", state="error")
                st.error(f"❌ {erro}")
                st.info("Dica: Ative o 'Modo Pré-Temporada' na lateral para testar fora de época de jogos.")
            else:
                status.update(label="Escalação Concluída!", state="complete")
                
                # --- RENDERIZAÇÃO DO CAMPO (Visual Print) ---
                html_cards = ""
                count_tracker = {p: 0 for p in FORMATION_COORDS[formacao].keys()}
                
                for _, jog in time_ideal.iterrows():
                    pos = jog['posicao']
                    if pos in FORMATION_COORDS[formacao]:
                        idx = count_tracker[pos]
                        if idx < len(FORMATION_COORDS[formacao][pos]):
                            left, top = FORMATION_COORDS[formacao][pos][idx]
                            count_tracker[pos] += 1
                            
                            # URL da foto tratada
                            foto_raw = jog.get('foto')
                            foto = foto_raw.replace("FORMATO", "140x140") if foto_raw else "https://via.placeholder.com/140"
                            if foto.startswith("//"): foto = "https:" + foto
                            
                            html_cards += f"""
                            <div class="player-slot" style="left:{left}%; top:{top}%;">
                                <div class="pos-label">{pos}</div>
                                <div class="card-box">
                                    <img src="{foto}">
                                    <div class="card-name">{jog['apelido']}</div>
                                    <div class="card-info">{jog.get('clube', '---')}</div>
                                    <div class="card-price">C$ {jog['preco']:.2f}</div>
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
                st.components.v1.html(field_html, height=760)
                st.metric("Saldo Restante", f"C$ {saldo:.2f}")

if __name__ == "__main__":
    main()
