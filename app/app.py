from __future__ import annotations

# ===== Path fix (Streamlit Cloud) =====
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # raiz do repo
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ===== Standard libs =====
import os
import requests
import pandas as pd
import streamlit as st

# ===== Project modules =====
from cartola.client import CartolaClient
from cartola import storage
from cartola.analytics import make_dataframe, valuation_heuristic, filter_probables, top_by_position
from cartola.team_builder import build_team_greedy, FORMATIONS

# Pitch visual (arquivo app/pitch.py)
from pitch import draw_pitch


# ----------------------------
# App Config
# ----------------------------
st.set_page_config(page_title="Valoriza Pro", layout="wide", page_icon="⚽")

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
    "Provável": "#16a34a",
    "Dúvida": "#f59e0b",
    "Suspenso": "#ef4444",
    "Contundido": "#ef4444",
    "Vetado": "#ef4444",
    "Nulo": "#64748b",
}

# ----------------------------
# Visual / CSS
# ----------------------------
FOOTBALL_CSS = """
<style>
/* Base */
.block-container { padding-top: 1.2rem; padding-bottom: 2.2rem; max-width: 1250px; }
h1, h2, h3 { letter-spacing: -0.02em; }
.small-muted { color: rgba(255,255,255,.65); font-size: 0.92rem; }
.hr { height: 1px; background: rgba(255,255,255,.12); margin: 0.75rem 0 1rem 0; }

/* Top header card */
.hero {
  border-radius: 18px;
  padding: 18px 18px;
  background: radial-gradient(1200px 600px at 10% 0%, rgba(34,197,94,.28), rgba(2,6,23,0) 60%),
              radial-gradient(1200px 600px at 80% 10%, rgba(59,130,246,.20), rgba(2,6,23,0) 55%),
              linear-gradient(180deg, rgba(15,23,42,.85), rgba(2,6,23,.85));
  border: 1px solid rgba(255,255,255,.10);
}
.hero-title {
  font-size: 1.55rem;
  font-weight: 800;
  margin: 0;
}
.hero-sub {
  margin-top: 4px;
  color: rgba(255,255,255,.70);
}

/* Cards */
.card {
  border-radius: 16px;
  padding: 14px 14px;
  border: 1px solid rgba(255,255,255,.10);
  background: rgba(15, 23, 42, .55);
}
.card h4 { margin: 0 0 6px 0; font-size: 1.02rem; }
.kpi {
  display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap;
}
.kpi .v { font-size: 1.35rem; font-weight: 800; }
.kpi .l { font-size: .92rem; color: rgba(255,255,255,.65); }

/* Badge */
.badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 3px 9px;
  border-radius: 999px;
  font-size: .82rem;
  font-weight: 700;
  border: 1px solid rgba(255,255,255,.12);
  background: rgba(255,255,255,.06);
}

/* Sidebar tweaks */
section[data-testid="stSidebar"] {
  border-right: 1px solid rgba(255,255,255,.10);
}
.sidebar-title {
  font-weight: 800;
  font-size: 1.05rem;
  margin-bottom: .4rem;
}

/* Player row */
.player-row {
  border-radius: 14px;
  padding: 10px 10px;
  border: 1px solid rgba(255,255,255,.10);
  background: rgba(2,6,23,.35);
  margin-bottom: 8px;
}
.player-name { font-weight: 800; margin: 0; }
.player-sub { color: rgba(255,255,255,.65); margin-top: 2px; font-size: .9rem; }
.player-metrics { color: rgba(255,255,255,.75); font-size: .92rem; }

/* Tab label slightly bigger */
button[data-baseweb="tab"] p { font-size: .95rem; font-weight: 700; }

</style>
"""
st.markdown(FOOTBALL_CSS, unsafe_allow_html=True)


# ----------------------------
# Helpers
# ----------------------------
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


def badge(text: str, color: str | None = None) -> str:
    c = color or "rgba(255,255,255,.85)"
    return f'<span class="badge"><span style="width:8px;height:8px;border-radius:999px;background:{c};display:inline-block"></span>{text}</span>'


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


def formation_needs(formation: str) -> dict:
    return FORMATIONS.get(formation, {}).copy()


def calc_min_budget(df: pd.DataFrame, formation: str) -> tuple[float | None, dict]:
    """
    Calcula orçamento mínimo aproximado pegando os mais baratos por posição.
    Retorna (min_budget, missing_positions)
    """
    need = formation_needs(formation)
    if not need:
        return None, {}

    missing = {}
    total = 0.0

    for pos, qty in need.items():
        dpos = df[df["posicao"] == pos].copy()
        dpos = dpos[dpos["preco"].notna()]
        dpos = dpos.sort_values("preco", ascending=True).head(qty)
        if len(dpos) < qty:
            missing[pos] = qty - len(dpos)
            continue
        total += float(dpos["preco"].sum())

    if missing:
        return None, missing
    return total, {}


def explain_team_failure(df: pd.DataFrame, formation: str, budget: float) -> str:
    min_budget, missing = calc_min_budget(df, formation)
    if missing:
        parts = []
        for pos, q in missing.items():
            parts.append(f"{pos} ({q} faltando)")
        return (
            "Não consegui montar porque faltam atletas suficientes em: "
            + ", ".join(parts)
            + ". Tente desmarcar 'somente prováveis' ou aguardar atualizações do mercado."
        )

    if min_budget is not None and budget < min_budget:
        return f"Seu orçamento (C$ {budget:.2f}) está abaixo do mínimo estimado para essa formação (≈ C$ {min_budget:.2f})."

    return "Não consegui montar o time com os filtros atuais. Tente aumentar o orçamento ou desmarcar 'somente prováveis'."


# ----------------------------
# External (Brasileirão stats)
# ----------------------------
def get_secret_or_env(key: str) -> str | None:
    # Streamlit Cloud: st.secrets
    try:
        if key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.getenv(key)


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
        team = safe_get(row, "team", "name")
        rows.append(
            {
                "Pos": row.get("position"),
                "Time": team,
                "PJ": row.get("playedGames"),
                "V": row.get("won"),
                "E": row.get("draw"),
                "D": row.get("lost"),
                "GP": row.get("goalsFor"),
                "GC": row.get("goalsAgainst"),
                "SG": row.get("goalDifference"),
                "Pts": row.get("points"),
            }
        )
    df = pd.DataFrame(rows)
    return df


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
        rows.append(
            {
                "Jogador": safe_get(s, "player", "name"),
                "Time": safe_get(s, "team", "name"),
                "Gols": s.get("goals"),
                "Assist": s.get("assists"),
                "Penaltis": s.get("penalties"),
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=6 * 60 * 60)
def api_football_get_cards_table() -> pd.DataFrame | None:
    key = get_secret_or_env("API_FOOTBALL_KEY")
    if not key:
        return None

    league = get_secret_or_env("API_FOOTBALL_LEAGUE")
    season = get_secret_or_env("API_FOOTBALL_SEASON")

    if not league or not season:
        return pd.DataFrame(
            [
                {
                    "Como habilitar": "Defina API_FOOTBALL_LEAGUE e API_FOOTBALL_SEASON (no Streamlit Secrets).",
                    "Exemplo": "API_FOOTBALL_LEAGUE=...  API_FOOTBALL_SEASON=2026",
                }
            ]
        )

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
        rows.append(
            {
                "Jogador": player,
                "Time": team,
                "Amarelos": cards.get("yellow"),
                "Vermelhos": cards.get("red"),
            }
        )
    if not rows:
        return pd.DataFrame([{"Info": "Sem dados retornados. Verifique LEAGUE/SEASON/endpoint no seu plano."}])
    return pd.DataFrame(rows)


# ----------------------------
# Fetch Cartola
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
# Sidebar: Brasileirão (visual)
# ----------------------------
def sidebar_brasileirao():
    st.sidebar.markdown('<div class="sidebar-title">📌 Brasileirão (Série A)</div>', unsafe_allow_html=True)
    menu = st.sidebar.radio(
        "Painéis",
        ["Classificação", "Artilheiros", "Cartões"],
        index=0,
        label_visibility="collapsed",
    )

    # Status cards
    token_ok = bool(get_secret_or_env("FOOTBALL_DATA_TOKEN"))
    cards_ok = bool(get_secret_or_env("API_FOOTBALL_KEY"))

    st.sidebar.markdown(
        f"""
        <div class="card">
          <h4>APIs (opcionais)</h4>
          <div class="small-muted">Para mostrar dados do Brasileirão, configure tokens no Streamlit Secrets.</div>
          <div class="hr"></div>
          <div style="display:flex; gap:8px; flex-wrap:wrap;">
            {badge("Classificação/Artilharia", "#16a34a" if token_ok else "#ef4444")}
            {badge("Cartões", "#16a34a" if cards_ok else "#ef4444")}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.sidebar.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # Content
    if menu == "Classificação":
        df = football_data_get_standings()
        if df is None:
            st.sidebar.info("Configure **FOOTBALL_DATA_TOKEN** (football-data.org) no Secrets.")
        else:
            st.sidebar.dataframe(df, use_container_width=True, hide_index=True)

    elif menu == "Artilheiros":
        df = football_data_get_scorers(20)
        if df is None:
            st.sidebar.info("Configure **FOOTBALL_DATA_TOKEN** (football-data.org) no Secrets.")
        else:
            st.sidebar.dataframe(df, use_container_width=True, hide_index=True)

    else:  # Cartões
        df = api_football_get_cards_table()
        if df is None:
            st.sidebar.info("Configure **API_FOOTBALL_KEY** (API-Football) no Secrets.")
        else:
            st.sidebar.dataframe(df, use_container_width=True, hide_index=True)


# ----------------------------
# Main UI
# ----------------------------
def main():
    # HERO header
    st.markdown(
        """
        <div class="hero">
          <div class="hero-title">⚽ Valoriza Pro</div>
          <div class="hero-sub">Escalação inteligente por rodada (Cartola) • Campo visual • Rankings • Lista de atletas</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)

    # Sidebar (Config + Brasileirão)
    with st.sidebar:
        st.markdown('<div class="sidebar-title">⚙️ Configurações</div>', unsafe_allow_html=True)
        base_url = st.text_input("Base URL (Cartola)", value="https://api.cartolafc.globo.com")
        only_probable = st.toggle("Somente prováveis (status_id=7)", value=True)
        formation = st.selectbox("Formação", list(FORMATIONS.keys()), index=0)
        budget = st.number_input("Orçamento (C$)", min_value=0.0, value=120.0, step=1.0)

        cA, cB = st.columns(2)
        with cA:
            if st.button("🔄 Atualizar"):
                st.cache_data.clear()
        with cB:
            st.caption("Cache 30s")

        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    sidebar_brasileirao()

    # Fetch Cartola
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

    # Save partials
    if isinstance(parciais, dict):
        points_map = parciais.get("atletas") or parciais.get("pontuados") or {}
        if isinstance(points_map, dict) and points_map:
            storage.upsert_points_history(rodada, points_map)

    mercado_txt = MERCADO_MAP.get(status.get("status_mercado"), str(status.get("status_mercado")))
    parciais_txt = "Disponíveis" if parciais is not None else "Indisponíveis"

    # KPI row
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(
            f"""
            <div class="card">
              <h4>Rodada</h4>
              <div class="kpi"><div class="v">{rodada}</div><div class="l">atual</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with k2:
        st.markdown(
            f"""
            <div class="card">
              <h4>Mercado</h4>
              <div class="kpi"><div class="v">{mercado_txt}</div><div class="l">status</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with k3:
        st.markdown(
            f"""
            <div class="card">
              <h4>Parciais</h4>
              <div class="kpi"><div class="v">{parciais_txt}</div><div class="l">durante jogos</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with k4:
        st.markdown(
            f"""
            <div class="card">
              <h4>Atletas</h4>
              <div class="kpi"><div class="v">{len(atletas_raw)}</div><div class="l">no mercado</div></div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

    # Dataframe base
    df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
    df = valuation_heuristic(df)
    df = df_with_status_and_photo(df, mercado)

    # Filter base
    df_filtered = filter_probables(df, only_probable=only_probable)

    # Main tabs
    tab1, tab2, tab3 = st.tabs(["🧠 Montar time", "📊 Rankings", "🗒️ Atletas da rodada"])

    # ----------------------------
    # Tab 1: Montar time (bonito + explicação)
    # ----------------------------
    with tab1:
        leftA, rightA = st.columns([1.35, 1])

        # Monta time
        team, left_budget = build_team_greedy(df_filtered, formation=formation, budget=float(budget))

        with leftA:
            st.subheader("🏟️ Campo")
            st.caption("Troque a formação e o campo reposiciona automaticamente os jogadores do time sugerido.")

            # Campo visual: desenha mesmo vazio (draw_pitch pode retornar None)
            fig = None
            try:
                fig = draw_pitch(team, formation)
            except Exception as e:
                st.warning(f"Erro ao desenhar campo: {e}")

            if fig is not None:
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Campo indisponível (verifique `app/pitch.py`).")

            # Se vazio, explica motivo
            if team.empty:
                msg = explain_team_failure(df_filtered, formation, float(budget))
                st.warning(msg)

                # Dica extra: orçamento mínimo (se der)
                min_budget, missing = calc_min_budget(df_filtered, formation)
                if min_budget is not None:
                    st.info(f"💡 Orçamento mínimo estimado para {formation}: **C$ {min_budget:.2f}**")

        with rightA:
            st.subheader("🧾 Sua escalação")
            st.caption("Lista do time sugerido com foto, status e custo.")

            if team.empty:
                st.markdown(
                    """
                    <div class="card">
                      <h4>Sem time ainda</h4>
                      <div class="small-muted">
                        Ajuste orçamento ou filtros. Se o mercado estiver instável, tente atualizar.
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div class="card">
                      <h4>Resumo</h4>
                      <div class="kpi">
                        <div class="v">C$ {(float(budget)-left_budget):.2f}</div>
                        <div class="l">gasto • sobra C$ {left_budget:.2f}</div>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

                # Render players
                team_sorted = team.sort_values(["posicao", "score_final"], ascending=[True, False]).copy()
                for _, row in team_sorted.iterrows():
                    status_nome = row.get("status_nome") or ""
                    color = BADGE_COLORS.get(status_nome, "#94a3b8")
                    st.markdown(
                        f"""
                        <div class="player-row">
                          <div style="display:flex; gap:10px; align-items:center;">
                            <div style="width:56px; height:56px; border-radius:14px; overflow:hidden; border:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.04); display:flex; align-items:center; justify-content:center;">
                              {"<img src='"+str(row.get("foto_url"))+"' style='width:56px;height:56px;object-fit:cover;'/>" if row.get("foto_url") else "—"}
                            </div>
                            <div style="flex:1;">
                              <div class="player-name">{row.get("apelido","")}</div>
                              <div class="player-sub">{row.get("clube","")} • {row.get("posicao","")}</div>
                              <div style="margin-top:6px;">{badge(status_nome or "—", color)}</div>
                            </div>
                            <div style="text-align:right;">
                              <div class="player-metrics"><b>C$ {float(row.get("preco") or 0):.2f}</b></div>
                              <div class="small-muted">Score {float(row.get("score_final") or 0):.2f}</div>
                            </div>
                          </div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        with st.expander("📅 Jogos da rodada (partidas)"):
            st.json(partidas)

        with st.expander("🧾 Debug (status/mercado)"):
            st.json({"status": status, "keys_mercado": list(mercado.keys())})

    # ----------------------------
    # Tab 2: Rankings (mais clean)
    # ----------------------------
    with tab2:
        st.subheader("📊 Rankings por posição")
        st.caption("Ordenado pelo score final (média + bônus de valorização).")

        pos_tabs = st.tabs(["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC", "Top Geral"])
        for i, pos in enumerate(["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"]):
            with pos_tabs[i]:
                d = top_by_position(df_filtered, pos, n=40)
                cols = ["apelido", "clube", "posicao", "status_nome", "preco", "media", "delta_preco", "score_final", "bonus_valorizacao"]
                cols = [c for c in cols if c in d.columns]
                st.dataframe(d[cols], use_container_width=True, hide_index=True)

        with pos_tabs[-1]:
            d = df_filtered.sort_values("score_final", ascending=False).head(200)
            cols = ["apelido", "clube", "posicao", "status_nome", "preco", "media", "delta_preco", "score_final", "bonus_valorizacao"]
            cols = [c for c in cols if c in d.columns]
            st.dataframe(d[cols], use_container_width=True, hide_index=True)

    # ----------------------------
    # Tab 3: Atletas da rodada (mais bonito)
    # ----------------------------
    with tab3:
        st.subheader("🗒️ Atletas do mercado (rodada)")
        st.caption("Busca + filtros. Mostra foto quando disponível e status do Cartola.")

        f1, f2, f3, f4 = st.columns([2.2, 1.5, 1.5, 1.2])
        with f1:
            search = st.text_input("Buscar jogador", value="")
        with f2:
            pos_options = ["(todas)"] + sorted([p for p in df["posicao"].dropna().unique().tolist()])
            pos_filter = st.selectbox("Posição", options=pos_options)
        with f3:
            status_options = ["(todos)"] + sorted([s for s in df["status_nome"].dropna().unique().tolist()])
            status_filter = st.selectbox("Status", options=status_options)
        with f4:
            limit = st.selectbox("Mostrar", options=[50, 100, 200, 300], index=1)

        d = df.copy()

        if search.strip():
            d = d[d["apelido"].str.contains(search.strip(), case=False, na=False)]

        if pos_filter != "(todas)":
            d = d[d["posicao"] == pos_filter]

        if status_filter != "(todos)":
            d = d[d["status_nome"] == status_filter]

        # ordenação
        d = d.sort_values(["status_nome", "posicao", "score_final"], ascending=[True, True, False])

        st.markdown(
            f"""
            <div class="card">
              <h4>Resultado</h4>
              <div class="small-muted">Total filtrado: <b>{len(d)}</b> atletas</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)

        # Render list (cards)
        shown = 0
        for _, row in d.iterrows():
            if shown >= int(limit):
                break
            shown += 1

            status_nome = row.get("status_nome") or ""
            color = BADGE_COLORS.get(status_nome, "#94a3b8")

            preco = row.get("preco")
            media = row.get("media")
            delta = row.get("delta_preco")

            preco_txt = f"C$ {float(preco):.2f}" if pd.notna(preco) else "—"
            media_txt = f"{float(media):.2f}" if pd.notna(media) else "—"
            delta_txt = f"{float(delta):+.2f}" if pd.notna(delta) else "—"

            st.markdown(
                f"""
                <div class="player-row">
                  <div style="display:flex; gap:10px; align-items:center;">
                    <div style="width:56px; height:56px; border-radius:14px; overflow:hidden; border:1px solid rgba(255,255,255,.12); background:rgba(255,255,255,.04); display:flex; align-items:center; justify-content:center;">
                      {"<img src='"+str(row.get("foto_url"))+"' style='width:56px;height:56px;object-fit:cover;'/>" if row.get("foto_url") else "—"}
                    </div>
                    <div style="flex:1;">
                      <div class="player-name">{row.get("apelido","")}</div>
                      <div class="player-sub">{row.get("clube","")} • {row.get("posicao","")}</div>
                      <div style="margin-top:6px;">{badge(status_nome or "—", color)}</div>
                    </div>
                    <div style="text-align:right;">
                      <div class="player-metrics"><b>{preco_txt}</b></div>
                      <div class="small-muted">Média {media_txt} • Δ {delta_txt}</div>
                    </div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        if len(d) > int(limit):
            st.info(f"Mostrando {limit} de {len(d)}. Use busca/filtros para refinar.")


if __name__ == "__main__":
    main()
