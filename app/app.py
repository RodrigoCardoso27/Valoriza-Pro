from __future__ import annotations

# ===== Path fix (Streamlit Cloud) =====
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # raiz do repo
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import os
import math
import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from cartola.client import CartolaClient
from cartola import storage
from cartola.analytics import make_dataframe, valuation_heuristic, filter_probables, top_by_position
from cartola.team_builder import build_team_greedy, FORMATIONS

st.set_page_config(page_title="Valoriza Pro", layout="wide", page_icon="⚽")

# ----------------------------
# Mapeamentos / Visual
# ----------------------------
STATUS_MAP = {
    2: "Dúvida",
    3: "Suspenso",
    5: "Contundido",
    6: "Nulo",
    7: "Provável",
    8: "Vetado",
}
MERCADO_MAP = {1: "Aberto", 2: "Fechado"}

BADGE_COLORS = {
    "Provável": "#22c55e",
    "Dúvida": "#f59e0b",
    "Suspenso": "#ef4444",
    "Contundido": "#ef4444",
    "Vetado": "#ef4444",
    "Nulo": "#64748b",
}

# Coordenadas (top/left em %) para desenhar slots no campo
# Ajuste fino se quiser (fica bem estilo Cartola)
FORMATION_SLOTS = {
    "4-3-3": {
        "ATA": [(18, 15), (42, 12), (66, 15)],
        "MEI": [(22, 40), (42, 36), (62, 40)],
        "LAT": [(8, 62), (78, 62)],
        "ZAG": [(28, 62), (52, 62)],
        "GOL": [(42, 82)],
        "TEC": [(78, 82)],
    },
    "4-4-2": {
        "ATA": [(30, 15), (54, 15)],
        "MEI": [(14, 40), (34, 36), (54, 36), (74, 40)],
        "LAT": [(8, 62), (78, 62)],
        "ZAG": [(28, 62), (52, 62)],
        "GOL": [(42, 82)],
        "TEC": [(78, 82)],
    },
    "3-4-3": {
        "ATA": [(18, 15), (42, 12), (66, 15)],
        "MEI": [(14, 40), (34, 36), (54, 36), (74, 40)],
        "ZAG": [(22, 62), (42, 64), (62, 62)],
        "GOL": [(42, 82)],
        "TEC": [(78, 82)],
    },
    "3-5-2": {
        "ATA": [(30, 15), (54, 15)],
        "MEI": [(10, 40), (28, 36), (42, 34), (56, 36), (74, 40)],
        "ZAG": [(22, 62), (42, 64), (62, 62)],
        "GOL": [(42, 82)],
        "TEC": [(78, 82)],
    },
    "5-3-2": {
        "ATA": [(30, 15), (54, 15)],
        "MEI": [(22, 40), (42, 36), (62, 40)],
        "LAT": [(6, 62), (82, 62)],
        "ZAG": [(22, 64), (42, 66), (62, 64)],
        "GOL": [(42, 82)],
        "TEC": [(78, 82)],
    },
}

# ----------------------------
# CSS (tema futebol)
# ----------------------------
CSS = """
<style>
.block-container { max-width: 1250px; padding-top: 1.1rem; padding-bottom: 2rem; }
h1,h2,h3 { letter-spacing: -0.02em; }
.small { color: rgba(255,255,255,.70); font-size: .92rem; }

.hero {
  border-radius: 18px;
  padding: 18px 18px;
  background: radial-gradient(1200px 600px at 10% 0%, rgba(34,197,94,.28), rgba(2,6,23,0) 60%),
              radial-gradient(1200px 600px at 80% 10%, rgba(59,130,246,.20), rgba(2,6,23,0) 55%),
              linear-gradient(180deg, rgba(15,23,42,.85), rgba(2,6,23,.85));
  border: 1px solid rgba(255,255,255,.10);
}
.hero-title { font-size: 1.55rem; font-weight: 900; margin:0; }
.hero-sub { margin-top: 4px; color: rgba(255,255,255,.72); }

.card {
  border-radius: 16px;
  padding: 14px 14px;
  border: 1px solid rgba(255,255,255,.10);
  background: rgba(15, 23, 42, .55);
}

.kpi { display:flex; gap:12px; align-items:baseline; flex-wrap:wrap; }
.kpi .v { font-size: 1.35rem; font-weight: 900; }
.kpi .l { font-size: .92rem; color: rgba(255,255,255,.65); }

.badge {
  display:inline-flex; align-items:center; gap:6px;
  padding: 3px 9px; border-radius: 999px;
  font-size: .82rem; font-weight: 800;
  border: 1px solid rgba(255,255,255,.12);
  background: rgba(255,255,255,.06);
}
.dot { width:8px; height:8px; border-radius:999px; display:inline-block; }

.pitch-wrap{
  border-radius: 18px;
  border: 1px solid rgba(255,255,255,.10);
  overflow:hidden;
  background: linear-gradient(180deg, rgba(2,6,23,.55), rgba(2,6,23,.30));
}

.pitch{
  position: relative;
  width: 100%;
  height: 560px;
  background:
    linear-gradient(180deg, rgba(0,0,0,.25), rgba(0,0,0,.05)),
    repeating-linear-gradient(
      90deg,
      rgba(34,197,94,.14) 0px,
      rgba(34,197,94,.14) 85px,
      rgba(34,197,94,.08) 85px,
      rgba(34,197,94,.08) 170px
    );
}

.pitch:before{
  content:"";
  position:absolute; inset: 18px;
  border: 2px solid rgba(255,255,255,.18);
  border-radius: 14px;
}

.line-mid{
  position:absolute; left: 18px; right:18px;
  top: 50%;
  height: 2px;
  background: rgba(255,255,255,.14);
}

.circle-mid{
  position:absolute;
  width: 120px; height: 120px;
  left: 50%; top: 50%;
  transform: translate(-50%,-50%);
  border: 2px solid rgba(255,255,255,.14);
  border-radius: 999px;
}

.slot{
  position:absolute;
  width: 110px; height: 138px;
  transform: translate(-50%,-50%);
  border-radius: 16px;
  border: 1px solid rgba(148,163,184,.25);
  background: rgba(2,6,23,.55);
  box-shadow: 0 10px 26px rgba(0,0,0,.35);
  display:flex; flex-direction:column;
  align-items:center; justify-content:center;
  gap:8px;
}

.slot .plus{
  width: 28px; height: 28px;
  border-radius: 999px;
  border: 1px solid rgba(255,255,255,.18);
  display:flex; align-items:center; justify-content:center;
  font-weight: 900;
  color: rgba(255,255,255,.85);
  background: rgba(255,255,255,.06);
}

.slot .pos{
  font-weight: 900;
  letter-spacing: .12em;
  color: rgba(255,255,255,.88);
}

.slot .name{
  font-size: .86rem;
  font-weight: 800;
  text-align:center;
  padding: 0 8px;
  color: rgba(255,255,255,.92);
}

.slot .sub{
  font-size: .78rem;
  color: rgba(255,255,255,.65);
  text-align:center;
  padding: 0 8px;
}

.avatar{
  width: 62px; height: 62px;
  border-radius: 16px;
  overflow:hidden;
  border: 1px solid rgba(255,255,255,.16);
  background: rgba(255,255,255,.06);
}
.avatar img{ width:100%; height:100%; object-fit:cover; }

.pillbar{
  display:flex; gap:10px; align-items:center; justify-content:flex-end;
}
.pill{
  border-radius: 999px;
  padding: 7px 12px;
  border: 1px solid rgba(255,255,255,.12);
  background: rgba(15,23,42,.55);
  font-weight: 900;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

# ----------------------------
# Helpers
# ----------------------------
def badge(text: str, color: str):
    return f'<span class="badge"><span class="dot" style="background:{color}"></span>{text}</span>'

def safe_get(d: dict, *keys, default=None):
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def format_foto_url(raw: str | None, size: str = "140x140") -> str | None:
    if not raw:
        return None
    url = raw.replace("{FORMATO}", size).replace("FORMATO", size)
    if url.startswith("//"):
        url = "https:" + url
    return url

def df_with_status_and_photo(df: pd.DataFrame, mercado_payload: dict) -> pd.DataFrame:
    athletes = mercado_payload.get("atletas") or mercado_payload.get("atleta") or []
    photo_map = {}
    for a in athletes:
        aid = a.get("atleta_id") or a.get("id")
        if aid is None:
            continue
        photo_map[int(aid)] = format_foto_url(a.get("foto"))
    out = df.copy()
    if not out.empty:
        out["status_nome"] = out["status_id"].map(STATUS_MAP).fillna(out["status_id"].astype(str))
        out["foto_url"] = out["athlete_id"].map(photo_map)
    return out

def get_secret_or_env(key: str) -> str | None:
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key)

# ----------------------------
# External APIs (Brasileirão)
# ----------------------------
@st.cache_data(ttl=6 * 60 * 60)
def football_data_get_standings() -> pd.DataFrame | None:
    token = get_secret_or_env("FOOTBALL_DATA_TOKEN")
    if not token:
        return None
    url = "https://api.football-data.org/v4/competitions/BSA/standings"
    r = requests.get(url, headers={"X-Auth-Token": token}, timeout=25)
    r.raise_for_status()
    data = r.json()

    table = None
    for s in data.get("standings", []):
        if s.get("type") == "TOTAL":
            table = s.get("table", [])
            break
    if table is None:
        return None

    rows = []
    for row in table:
        rows.append({
            "Pos": row.get("position"),
            "Time": safe_get(row, "team", "name"),
            "PJ": row.get("playedGames"),
            "V": row.get("won"),
            "E": row.get("draw"),
            "D": row.get("lost"),
            "GP": row.get("goalsFor"),
            "GC": row.get("goalsAgainst"),
            "SG": row.get("goalDifference"),
            "Pts": row.get("points"),
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=6 * 60 * 60)
def football_data_get_scorers(top: int = 20) -> pd.DataFrame | None:
    token = get_secret_or_env("FOOTBALL_DATA_TOKEN")
    if not token:
        return None
    url = f"https://api.football-data.org/v4/competitions/BSA/scorers?limit={top}"
    r = requests.get(url, headers={"X-Auth-Token": token}, timeout=25)
    r.raise_for_status()
    data = r.json()

    rows = []
    for s in data.get("scorers", []):
        rows.append({
            "Jogador": safe_get(s, "player", "name"),
            "Time": safe_get(s, "team", "name"),
            "Gols": s.get("goals"),
            "Assist": s.get("assists"),
            "Pênaltis": s.get("penalties"),
        })
    return pd.DataFrame(rows)

@st.cache_data(ttl=6 * 60 * 60)
def api_football_get_cards_table() -> pd.DataFrame | None:
    key = get_secret_or_env("API_FOOTBALL_KEY")
    if not key:
        return None
    league = get_secret_or_env("API_FOOTBALL_LEAGUE")
    season = get_secret_or_env("API_FOOTBALL_SEASON")
    if not league or not season:
        return pd.DataFrame([{
            "Como habilitar": "Defina API_FOOTBALL_LEAGUE e API_FOOTBALL_SEASON no Streamlit Secrets.",
            "Exemplo": "API_FOOTBALL_LEAGUE=... | API_FOOTBALL_SEASON=2026"
        }])

    url = "https://v3.football.api-sports.io/players/topredcards"
    headers = {"x-apisports-key": key}
    params = {"league": league, "season": season}
    r = requests.get(url, headers=headers, params=params, timeout=25)
    r.raise_for_status()
    data = r.json()

    rows = []
    for item in data.get("response", []):
        player = safe_get(item, "player", "name")
        team = safe_get(item, "statistics", 0, "team", "name")
        cards = safe_get(item, "statistics", 0, "cards", default={}) or {}
        rows.append({
            "Jogador": player,
            "Time": team,
            "Amarelos": cards.get("yellow"),
            "Vermelhos": cards.get("red"),
        })
    if not rows:
        return pd.DataFrame([{"Info": "Sem dados retornados. Verifique LEAGUE/SEASON/endpoint do seu plano."}])
    return pd.DataFrame(rows)

# ----------------------------
# Cartola fetch
# ----------------------------
@st.cache_data(ttl=30)
def fetch_cartola(base_url: str):
    client = CartolaClient(base_url=base_url)
    status = client.mercado_status()
    rodada = int(status.get("rodada_atual") or status.get("rodada") or 0)
    mercado = client.atletas_mercado()
    partidas = client.partidas()

    parciais = None
    try:
        parciais = client.parciais()
    except Exception:
        parciais = None
    return rodada, status, mercado, partidas, parciais

# ----------------------------
# Time manual (slots)
# ----------------------------
def formation_needed(formation: str) -> dict:
    return FORMATIONS.get(formation, {})

def build_empty_slots(formation: str) -> list[dict]:
    # cria lista ordenada de slots com pos + index
    need = formation_needed(formation)
    order = []
    # ordem visual aproximada
    for pos in ["ATA", "MEI", "LAT", "ZAG", "GOL", "TEC"]:
        if pos in need:
            for i in range(int(need[pos])):
                order.append({"pos": pos, "i": i})
    return order

def pick_options_for_pos(df: pd.DataFrame, pos: str) -> pd.DataFrame:
    d = df[df["posicao"] == pos].copy()
    d = d.sort_values(["score_final", "preco"], ascending=[False, True])
    return d

def render_pitch_html(formation: str, slot_players: list[dict]) -> str:
    # slot_players: lista com {pos, i, player(dict or None)}
    coords = FORMATION_SLOTS.get(formation, {})
    # fallback se não tiver coords
    if not coords:
        return "<div class='pitch-wrap'><div class='pitch'></div></div>"

    # construir slots
    slot_divs = []
    for sp in slot_players:
        pos = sp["pos"]
        i = sp["i"]
        player = sp.get("player")

        # coordenada
        if pos not in coords or i >= len(coords[pos]):
            continue
        left, top = coords[pos][i]

        if player:
            foto = player.get("foto_url") or ""
            nome = player.get("apelido") or ""
            clube = player.get("clube") or ""
            slot_divs.append(f"""
              <div class="slot" style="left:{left}%; top:{top}%;">
                <div class="avatar">{f"<img src='{foto}'/>" if foto else ""}</div>
                <div class="name">{nome}</div>
                <div class="sub">{clube} • {pos}</div>
              </div>
            """)
        else:
            slot_divs.append(f"""
              <div class="slot" style="left:{left}%; top:{top}%;">
                <div class="plus">+</div>
                <div class="pos">{pos}</div>
              </div>
            """)

    return f"""
    <div class="pitch-wrap">
      <div class="pitch">
        <div class="line-mid"></div>
        <div class="circle-mid"></div>
        {''.join(slot_divs)}
      </div>
    </div>
    """

# ----------------------------
# Jogos da rodada (bonito)
# ----------------------------
def normalize_partidas(partidas_payload: dict) -> pd.DataFrame:
    jogos = partidas_payload.get("partidas") or partidas_payload.get("partida") or partidas_payload.get("jogos") or []
    rows = []
    for j in jogos:
        mand = safe_get(j, "clube_casa", "nome") or safe_get(j, "clube_casa", "abreviacao") or j.get("clube_casa_id")
        vis = safe_get(j, "clube_visitante", "nome") or safe_get(j, "clube_visitante", "abreviacao") or j.get("clube_visitante_id")
        data = j.get("partida_data") or j.get("data_realizacao") or j.get("data")
        hora = j.get("hora_realizacao") or j.get("hora")
        local = j.get("local") or j.get("estadio")
        rows.append({
            "Mandante": mand,
            "Visitante": vis,
            "Data": data,
            "Hora": hora,
            "Local": local,
        })
    return pd.DataFrame(rows)

# ----------------------------
# App
# ----------------------------
def main():
    st.markdown(
        """
        <div class="hero">
          <div class="hero-title">⚽ Valoriza Pro</div>
          <div class="hero-sub">Escalação estilo Cartola • Abas do Brasileirão • Rankings • Atletas • Jogos</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.write("")

    # Sidebar config
    with st.sidebar:
        st.markdown("<div class='card'><div class='kpi'><div class='v'>⚙️</div><div class='l'>Configurações</div></div></div>", unsafe_allow_html=True)
        base_url = st.text_input("Base URL (Cartola)", value="https://api.cartolafc.globo.com")
        only_probable = st.toggle("Somente prováveis", value=True)
        formation = st.selectbox("Formação", list(FORMATIONS.keys()), index=0)
        budget = st.number_input("Orçamento (C$)", min_value=0.0, value=120.0, step=1.0)
        modo_dev = st.toggle("Modo dev (mostrar detalhes)", value=False)

        colA, colB = st.columns(2)
        with colA:
            if st.button("🔄 Atualizar"):
                st.cache_data.clear()
        with colB:
            st.caption("cache 30s")

    # Fetch
    try:
        rodada, status, mercado, partidas, parciais = fetch_cartola(base_url)
    except Exception as e:
        st.error(f"Falha ao consultar API do Cartola: {e}")
        st.stop()

    # Save snapshots
    storage.init_db()
    storage.save_snapshot(rodada, "status", status)
    storage.save_snapshot(rodada, "mercado", mercado)
    storage.save_snapshot(rodada, "partidas", partidas)
    if parciais is not None:
        storage.save_snapshot(rodada, "parciais", parciais)

    atletas_raw = (mercado.get("atletas") or mercado.get("atleta") or [])
    storage.upsert_price_history(rodada, atletas_raw)

    # métricas topo
    mercado_txt = MERCADO_MAP.get(status.get("status_mercado"), str(status.get("status_mercado")))
    parciais_txt = "Disponíveis" if parciais is not None else "Indisponíveis"

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"<div class='card'><h4>Rodada</h4><div class='kpi'><div class='v'>{rodada}</div><div class='l'>atual</div></div></div>", unsafe_allow_html=True)
    with c2:
        st.markdown(f"<div class='card'><h4>Mercado</h4><div class='kpi'><div class='v'>{mercado_txt}</div><div class='l'>status</div></div></div>", unsafe_allow_html=True)
    with c3:
        st.markdown(f"<div class='card'><h4>Parciais</h4><div class='kpi'><div class='v'>{parciais_txt}</div><div class='l'>ao vivo</div></div></div>", unsafe_allow_html=True)
    with c4:
        st.markdown(f"<div class='card'><h4>Atletas</h4><div class='kpi'><div class='v'>{len(atletas_raw)}</div><div class='l'>no mercado</div></div></div>", unsafe_allow_html=True)

    st.write("")

    # Dataframes
    df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
    df = valuation_heuristic(df)
    df = df_with_status_and_photo(df, mercado)

    df_base = filter_probables(df, only_probable=only_probable)

    # NAV TABS (como você pediu)
    tab_escalacao, tab_brasileirao, tab_rankings, tab_atletas, tab_jogos = st.tabs(
        ["🧩 Escalação", "🏆 Brasileirão", "📊 Rankings", "🧑‍🤝‍🧑 Atletas", "📅 Jogos"]
    )

    # ----------------------------
    # ESCALAÇÃO (estilo Cartola)
    # ----------------------------
    with tab_escalacao:
        left, right = st.columns([1.35, 1])

        # Botão auto-escalar (usa greedy)
        with right:
            st.markdown("<div class='card'><h4>Escalação</h4><div class='small'>Auto-escalar ou escolher manualmente.</div></div>", unsafe_allow_html=True)
            st.write("")

            auto = st.button("⚡ Auto-escalar (sugestão)")

            # Build slots list
            slots = build_empty_slots(formation)

            # Estado de seleção
            if "picked" not in st.session_state:
                st.session_state["picked"] = {}  # key: f"{pos}-{i}" -> athlete_id

            # se apertar auto, preenche session_state com time sugerido
            if auto:
                team_auto, left_budget = build_team_greedy(df_base, formation=formation, budget=float(budget))
                st.session_state["picked"] = {}
                for _, r in team_auto.iterrows():
                    # preencher na ordem do slot (primeiro vazio daquela posição)
                    pos = r["posicao"]
                    # achar primeiro índice livre
                    idx = 0
                    while f"{pos}-{idx}" in st.session_state["picked"]:
                        idx += 1
                    st.session_state["picked"][f"{pos}-{idx}"] = int(r["athlete_id"])

            # Montagem manual por slot
            used_ids = set(st.session_state["picked"].values())

            st.subheader("📌 Escolha manual")
            for sp in slots:
                pos = sp["pos"]
                i = sp["i"]
                key = f"{pos}-{i}"

                options_df = pick_options_for_pos(df_base, pos)
                # remove já usados
                options_df = options_df[~options_df["athlete_id"].isin(list(used_ids - {st.session_state["picked"].get(key)}))]

                # label
                st.caption(f"{pos} #{i+1}")

                # select
                # cria lista (id, label)
                items = [("", f"➕ {pos} (vazio)")]
                for _, r in options_df.head(80).iterrows():
                    status_nome = r.get("status_nome", "")
                    items.append((
                        str(int(r["athlete_id"])),
                        f"{r['apelido']} • {r['clube']} • C$ {float(r['preco'] or 0):.2f} • {status_nome}"
                    ))

                current = st.session_state["picked"].get(key)
                current_str = "" if current is None else str(current)

                selected = st.selectbox(
                    label="",
                    options=[x[0] for x in items],
                    format_func=lambda v: dict(items).get(v, v),
                    index=([x[0] for x in items].index(current_str) if current_str in [x[0] for x in items] else 0),
                    key=f"select-{key}",
                    label_visibility="collapsed",
                )

                if selected == "":
                    if key in st.session_state["picked"]:
                        del st.session_state["picked"][key]
                else:
                    st.session_state["picked"][key] = int(selected)

                used_ids = set(st.session_state["picked"].values())

            st.write("")
            st.markdown("<div class='card'><h4>Orçamento</h4></div>", unsafe_allow_html=True)

            # calcular custo
            picked_ids = list(st.session_state["picked"].values())
            team_manual = df_base[df_base["athlete_id"].isin(picked_ids)].copy()
            cost = float(team_manual["preco"].fillna(0).sum()) if not team_manual.empty else 0.0
            st.markdown(
                f"""
                <div class="pillbar">
                  <div class="pill">💰 Gasto: C$ {cost:.2f}</div>
                  <div class="pill">🧾 Saldo: C$ {max(0.0, float(budget)-cost):.2f}</div>
                </div>
                """,
                unsafe_allow_html=True
            )

        # Campo (render HTML)
        with left:
            # construir slot_players para o campo
            slot_players = []
            for sp in slots:
                pos = sp["pos"]
                i = sp["i"]
                key = f"{pos}-{i}"
                aid = st.session_state["picked"].get(key)
                player = None
                if aid is not None:
                    row = df_base[df_base["athlete_id"] == aid]
                    if not row.empty:
                        player = row.iloc[0].to_dict()
                slot_players.append({"pos": pos, "i": i, "player": player})

            html = render_pitch_html(formation, slot_players)
            components.html(html, height=590, scrolling=False)

            # Mensagem se faltar posições ou exceder orçamento
            need = formation_needed(formation)
            filled_count = {p: 0 for p in need.keys()}
            for sp in slots:
                key = f"{sp['pos']}-{sp['i']}"
                if key in st.session_state["picked"]:
                    filled_count[sp["pos"]] += 1

            missing = []
            for pos, qty in need.items():
                if filled_count.get(pos, 0) < qty:
                    missing.append(f"{pos} ({qty-filled_count.get(pos,0)} faltando)")
            if missing:
                st.warning("Faltando: " + ", ".join(missing))

            if float(cost) > float(budget):
                st.error("Seu time passou do orçamento. Troque alguns jogadores para caber no saldo.")

    # ----------------------------
    # BRASILEIRÃO (abas reais)
    # ----------------------------
    with tab_brasileirao:
        st.subheader("🏆 Brasileirão Série A")
        st.caption("Aqui são abas reais. Clique e troca o conteúdo.")

        t1, t2, t3 = st.tabs(["📌 Classificação", "🥇 Artilheiros", "🟨🟥 Cartões"])

        with t1:
            df_st = football_data_get_standings()
            if df_st is None:
                st.info("Configure **FOOTBALL_DATA_TOKEN** no Streamlit Secrets (football-data.org).")
            else:
                st.dataframe(df_st, use_container_width=True, hide_index=True)

        with t2:
            df_sc = football_data_get_scorers(20)
            if df_sc is None:
                st.info("Configure **FOOTBALL_DATA_TOKEN** no Streamlit Secrets (football-data.org).")
            else:
                st.dataframe(df_sc, use_container_width=True, hide_index=True)

        with t3:
            df_cards = api_football_get_cards_table()
            if df_cards is None:
                st.info("Configure **API_FOOTBALL_KEY** (e opcionalmente LEAGUE/SEASON) no Secrets.")
            else:
                st.dataframe(df_cards, use_container_width=True, hide_index=True)

    # ----------------------------
    # RANKINGS
    # ----------------------------
    with tab_rankings:
        st.subheader("📊 Rankings (por posição)")
        pos_tabs = st.tabs(["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC", "Top Geral"])

        for i, pos in enumerate(["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"]):
            with pos_tabs[i]:
                d = top_by_position(df_base, pos, n=40)
                cols = ["apelido", "clube", "posicao", "status_nome", "preco", "media", "delta_preco", "score_final", "bonus_valorizacao"]
                cols = [c for c in cols if c in d.columns]
                st.dataframe(d[cols], use_container_width=True, hide_index=True)

        with pos_tabs[-1]:
            d = df_base.sort_values("score_final", ascending=False).head(200)
            cols = ["apelido", "clube", "posicao", "status_nome", "preco", "media", "delta_preco", "score_final", "bonus_valorizacao"]
            cols = [c for c in cols if c in d.columns]
            st.dataframe(d[cols], use_container_width=True, hide_index=True)

    # ----------------------------
    # ATLETAS
    # ----------------------------
    with tab_atletas:
        st.subheader("🧑‍🤝‍🧑 Atletas do mercado")
        f1, f2, f3, f4 = st.columns([2.2, 1.4, 1.4, 1.1])
        with f1:
            search = st.text_input("Buscar jogador", value="")
        with f2:
            pos_options = ["(todas)"] + sorted([p for p in df_base["posicao"].dropna().unique().tolist()])
            pos_filter = st.selectbox("Posição", options=pos_options)
        with f3:
            status_options = ["(todos)"] + sorted([s for s in df_base["status_nome"].dropna().unique().tolist()])
            status_filter = st.selectbox("Status", options=status_options)
        with f4:
            limit = st.selectbox("Mostrar", options=[50, 100, 200, 300], index=1)

        d = df_base.copy()
        if search.strip():
            d = d[d["apelido"].str.contains(search.strip(), case=False, na=False)]
        if pos_filter != "(todas)":
            d = d[d["posicao"] == pos_filter]
        if status_filter != "(todos)":
            d = d[d["status_nome"] == status_filter]

        d = d.sort_values(["status_nome", "posicao", "score_final"], ascending=[True, True, False]).head(int(limit))

        show_cols = ["apelido", "clube", "posicao", "status_nome", "preco", "media", "delta_preco", "score_final"]
        st.dataframe(d[show_cols], use_container_width=True, hide_index=True)

    # ----------------------------
    # JOGOS (sem JSON)
    # ----------------------------
    with tab_jogos:
        st.subheader("📅 Jogos da rodada")
        try:
            dfj = normalize_partidas(partidas)
            if dfj.empty:
                st.info("Sem jogos para mostrar neste momento.")
            else:
                st.dataframe(dfj, use_container_width=True, hide_index=True)
        except Exception:
            st.info("Não consegui normalizar os jogos (payload pode ter mudado).")

        if modo_dev:
            st.write("### Modo Dev")
            st.json({"status": status, "keys_mercado": list(mercado.keys())})


if __name__ == "__main__":
    main()
