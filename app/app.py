import requests
import pandas as pd
import streamlit as st

# ==========================================
# API 1: CARTOLA (Preços e Status)
# ==========================================
@st.cache_data(ttl=300)
def api_cartola_mercado():
    url = "https://api.cartolafc.globo.com/atletas/mercado"
    # Faz o GET na Globo e retorna os preços
    return requests.get(url).json()

# ==========================================
# API 2: TABELA DO BRASILEIRÃO
# ==========================================
@st.cache_data(ttl=3600)
def api_tabela_classificacao(token):
    url = "https://api.football-data.org/v4/competitions/BSA/standings"
    headers = {"X-Auth-Token": token}
    # Faz o GET no football-data e retorna quem é o líder
    return requests.get(url, headers=headers).json()

# ==========================================
# API 3: ARTILHEIROS DO CAMPEONATO
# ==========================================
@st.cache_data(ttl=3600)
def api_artilheiros(token):
    # Endpoint específico para pegar os goleadores
    url = "https://api.football-data.org/v4/competitions/BSA/scorers"
    headers = {"X-Auth-Token": token}
    return requests.get(url, headers=headers).json()
