from __future__ import annotations
import sys
import os
import pandas as pd
import streamlit as st
from pathlib import Path

# ===== Ajuste de Caminhos =====
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cartola.client import CartolaClient
from cartola import storage
from cartola.analytics import make_dataframe, valuation_heuristic, filter_probables
from cartola.team_builder import FORMATIONS

st.set_page_config(page_title="Valoriza Pro | TabuadaRJ", layout="wide", page_icon="🪄")

# ==========================================
# 1. CSS DO CAMPO REALISTA (Estilo Aplicativo)
# ==========================================
CSS = """
<style>
.stApp { background-color: #0b111a; color: #ffffff; }

/* Gramado com Faixas e Perspectiva */
.pitch-container {
    background: #234f27;
    background-image: 
        linear-gradient(rgba(255, 255, 255, 0.1) 2px, transparent 2px),
        repeating-linear-gradient(0deg, #234f27, #234f27 50px, #1e4421 50px, #1e4421 100px);
    border: 4px solid rgba(255, 255, 255, 0.3);
    border-radius: 15px;
    height: 800px;
    width: 100%;
    position: relative;
    margin: 20px 0;
    box-shadow: inset 0px 0px 80px rgba(0,0,0,0.6);
}

/* Marcações do Campo */
.pitch-line-center { position: absolute; top: 50%; left: 0; right: 0; height: 2px; background: rgba(255, 255, 255, 0.2); }
.pitch-circle-center { 
    position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%);
    width: 140px; height: 140px; border: 2px solid rgba(255, 255, 255, 0.2); border-radius: 50%; 
}

/* Card do Atleta */
.player-slot {
    position: absolute;
    width: 100px;
    display: flex;
    flex-direction: column;
    align-items: center;
    transform: translate(-50%, -50%);
}

.card-visual {
    background: rgba(15, 23, 42, 0.95);
    border: 1px solid #334155;
    border-radius: 10px;
    width: 90px; padding: 10px 5px;
    display: flex; flex-direction: column;
    align-items: center;
    box-shadow: 0 10px 20px rgba(0,0,0,0.7);
}

.card-visual img { 
    width: 60px; height: 60px; border-radius: 50%; 
    border: 2px solid #22c55e; background: #334155; margin-bottom: 5px; 
}

.card-name { font-size: 0.75rem; font-weight: 800; text-align: center; color: #f8fafc; line-height: 1.1; }
.card-price { font-size: 0.75rem; color: #4ade80; font-weight: 800; margin-top: 3px; }

.pos-tag {
    background: #22c55e; color: #020617;
    font-size: 0.65rem; font-weight: 900;
    padding: 2px 8px; border-radius: 12px;
    position: absolute; top: -12px; z-index: 5;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# Coordenadas de Posicionamento (Top/Left %)
COORDS = {
    "3-4-3": {
        "ATA": [(25, 18), (50, 12), (75, 18)],
        "MEI": [(15, 42), (38, 48), (62, 48), (85, 42)],
        "ZAG": [(28, 72), (50, 78), (72, 72)],
        "GOL": [(50, 92)], "TEC": [(90, 92)]
    },
    "4-3-3": {
        "ATA": [(25, 18), (50, 12), (75, 18)],
        "MEI": [(30, 48), (50, 52), (70, 48)],
        "LAT": [(12, 68), (88, 68)],
        "ZAG": [(38, 75), (62, 75)],
        "GOL": [(50, 92)], "TEC": [(90, 92)]
    },
    "4-4-2": {
        "ATA": [(40, 18), (60, 18)],
        "MEI": [(15, 45), (40, 50), (60, 50), (85, 45)],
        "LAT": [(12, 68), (88, 68)],
        "ZAG": [(38, 75), (62, 75)],
        "GOL": [(50, 92)], "TEC": [(90, 92)]
    }
}

# ==========================================
# 2. BACKEND SEGURO
# ==========================================
@st.cache_data(ttl=300)
def get_cartola_data():
    client = CartolaClient(base_url="https://api.cartolafc.globo.com")
    return client.mercado_status(), client.atletas_mercado()

def escalar_time_seguro(df, formacao_nome, orcamento_maximo):
    vagas = FORMATIONS.get(formacao_nome, {}).copy()
    
    # Proteção contra DataFrame vazio (Erro que você teve)
    if df.empty or "preco" not in df.columns:
        return None, 0, "O mercado não retornou atletas. Tente ligar o 'Modo Pré-Temporada'."

    df_qualidade = df.sort_values(by=["score_final"], ascending=False)
    
    time_selecionado = []
    for pos, qtd in vagas.items():
        jogadores_pos = df_qualidade[df_qualidade["posicao"] == pos]
        if len(jogadores_pos) < qtd:
            return None, 0, f"Atletas insuficientes para a posição: {pos}"
        time_selecionado.extend(jogadores_pos.head(qtd).to_dict('records'))
    
    res_df = pd.DataFrame(time_selecionado)
    custo_total = res_df["preco"].sum()
    
    if custo_total > orcamento_maximo:
        return None, 0, f"Orçamento insuficiente (Custo: C$ {custo_total:.2f})"
        
    return res_df, orcamento_maximo - custo_total, ""

# ==========================================
# 3. INTERFACE
# ==========================================
def main():
    st.markdown("<h1 style='text-align: center;'>🪄 Oráculo Valoriza Pro</h1>", unsafe_allow_html=True)
    
    with st.sidebar:
        st.header("⚙️ Painel de Controle")
        orcamento = st.number_input("Meu Patrimônio (C$)", value=100.0, min_value=30.0)
        formacao = st.selectbox("Formação Tática", list(COORDS.keys()))
        modo_teste = st.toggle("Modo Pré-Temporada (Ignorar 'Prováveis')", value=True)

    if st.button("🚀 Gerar Escalação Perfeita", type="primary", use_container_width=True):
        with st.status("Analisando mercado...", expanded=False) as status:
            status_cartola, mercado = get_cartola_data()
            rodada = int(status_cartola.get("rodada_atual") or 0)
            
            df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
            df = valuation_heuristic(df)
            
            # Filtro Dinâmico
            df_base = filter_probables(df, only_probable=not modo_teste)
            
            time_ideal, saldo, erro = escalar_time_seguro(df_base, formacao, orcamento)
            
            if erro:
                status.update(label="Falha na Escalação", state="error")
                st.error(f"❌ {erro}")
            else:
                status.update(label="Time Escalado!", state="complete")
                
                # --- RENDERIZAÇÃO DO CAMPO ---
                html_cards = ""
                tracker = {p: 0 for p in COORDS[formacao].keys()}
                
                for _, jog in time_ideal.iterrows():
                    pos = jog['posicao']
                    if pos in COORDS[formacao]:
                        idx = tracker[pos]
                        if idx < len(COORDS[formacao][pos]):
                            left, top = COORDS[formacao][pos][idx]
                            tracker[pos] += 1
                            
                            # Tratar foto
                            foto_raw = jog.get('foto') or ""
                            foto = foto_raw.replace("FORMATO", "140x140")
                            if foto.startswith("//"): foto = "https:" + foto
                            if not foto: foto = "https://via.placeholder.com/140"
                            
                            html_cards += f"""
                            <div class="player-slot" style="left:{left}%; top:{top}%;">
                                <div class="pos-tag">{pos}</div>
                                <div class="card-visual">
                                    <img src="{foto}">
                                    <div class="card-name">{jog['apelido']}</div>
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
                st.components.v1.html(field_html, height=820)
                st.metric("Saldo Restante na Conta", f"C$ {saldo:.2f}", delta_color="normal")

if __name__ == "__main__":
    main()
