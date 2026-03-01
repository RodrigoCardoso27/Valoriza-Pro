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
# IMPORTANTE: pitch.py deve estar na mesma pasta deste app.py (app/)
from pitch import draw_pitch


# ----------------------------
# Config
# ----------------------------
st.set_page_config(page_title="Valoriza Pro", layout="wide")

STATUS_MAP = {
    2: "Dúvida",
    3: "Suspenso",
    5: "Contundido",
    6: "Nulo",
    7: "Provável",
    8: "Vetado",
}
# Alguns ambientes usam status_mercado 1=aberto, 2=fechado etc. Mantemos simples:
MERCADO_MAP = {1: "Aberto", 2: "Fechado"}


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
    """
    A API do Cartola costuma retornar foto com placeholder tipo:
      ".../FORMATO.png"  ou ".../{FORMATO}.png"
    Aqui tentamos normalizar.
    """
    if not raw:
        return None
    url = raw
    url = url.replace("{FORMATO}", size).replace("FORMATO", size)
    # às vezes vem // sem esquema
    if url.startswith("//"):
        url = "https:" + url
    return url


def df_with_status_and_photo(df: pd.DataFrame, mercado_payload: dict) -> pd.DataFrame:
    """
    Enriquecemos o df com:
    - status_nome
    - foto_url (quando disponível no payload original)
    """
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


# ----------------------------
# External (Brasileirão stats)
# ----------------------------
@st.cache_data(ttl=6 * 60 * 60)  # 6h
def football_data_get_standings() -> pd.DataFrame | None:
    """
    football-data.org (requere token) - Série A costuma ser "BSA" (Brazilian Serie A)
    Docs: https://www.football-data.org/
    """
    token = os.getenv("FOOTBALL_DATA_TOKEN")
    if not token:
        return None

    url = "https://api.football-data.org/v4/competitions/BSA/standings"
    r = requests.get(url, headers={"X-Auth-Token": token}, timeout=20)
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
    return pd.DataFrame(rows)


@st.cache_data(ttl=6 * 60 * 60)  # 6h
def football_data_get_scorers(top: int = 20) -> pd.DataFrame | None:
    token = os.getenv("FOOTBALL_DATA_TOKEN")
    if not token:
        return None

    url = f"https://api.football-data.org/v4/competitions/BSA/scorers?limit={top}"
    r = requests.get(url, headers={"X-Auth-Token": token}, timeout=20)
    r.raise_for_status()
    data = r.json()

    rows = []
    for s in data.get("scorers", []):
        player = safe_get(s, "player", "name")
        team = safe_get(s, "team", "name")
        rows.append(
            {
                "Jogador": player,
                "Time": team,
                "Gols": s.get("goals"),
                "Assist": s.get("assists"),
                "Penaltis": s.get("penalties"),
            }
        )
    return pd.DataFrame(rows)


@st.cache_data(ttl=6 * 60 * 60)
def api_football_get_cards_table() -> pd.DataFrame | None:
    """
    API-Football (requere API key) - cartões por jogador depende do endpoint/plano.
    Aqui deixo um "placeholder" seguro: se você tiver a key e souber o season/league_id,
    você ajusta os parâmetros.

    Env vars:
      API_FOOTBALL_KEY
      API_FOOTBALL_LEAGUE (opcional)
      API_FOOTBALL_SEASON (opcional)
    """
    key = os.getenv("API_FOOTBALL_KEY")
    if not key:
        return None

    # ⚠️ Ajuste conforme sua conta/plano e ids corretos do Brasileirão na API-Football
    league = os.getenv("API_FOOTBALL_LEAGUE")  # ex: "71" (exemplo genérico, pode não ser BSA)
    season = os.getenv("API_FOOTBALL_SEASON")  # ex: "2026"

    if not league or not season:
        # Sem parâmetros, não tentamos bater no endpoint pra não dar confusão
        return pd.DataFrame(
            [
                {
                    "Info": "Configure API_FOOTBALL_LEAGUE e API_FOOTBALL_SEASON nas variáveis de ambiente.",
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

    # Estrutura pode variar. Tentamos interpretar.
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
        return pd.DataFrame([{"Info": "Sem dados de cartões retornados. Verifique league/season e endpoint."}])

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

    # Parciais podem falhar
    parciais = None
    try:
        parciais = client.parciais()
    except Exception:
        parciais = None

    return rodada, status, mercado, partidas, parciais


# ----------------------------
# UI
# ----------------------------
def main():
    st.title("⚽ Valoriza Pro — Cartola Scout")
    st.caption("MVP com time sugerido + campo visual + lista da rodada + painel do Brasileirão (opcional via APIs externas).")

    # Sidebar controls
    with st.sidebar:
        st.subheader("Configurações")
        base_url = st.text_input("Base URL (Cartola)", value="https://api.cartolafc.globo.com")
        only_probable = st.toggle("Somente prováveis (status_id=7)", value=True)
        formation = st.selectbox("Formação", list(FORMATIONS.keys()), index=0)
        budget = st.number_input("Orçamento (C$)", min_value=0.0, value=120.0, step=1.0)

        st.divider()
        if st.button("🔄 Atualizar agora"):
            st.cache_data.clear()

        # Lateral: abas de stats do Brasileirão
        st.divider()
        st.subheader("📌 Brasileirão (Série A)")
        tabA, tabB, tabC = st.tabs(["Classificação", "Artilheiros", "Cartões"])

        with tabA:
            df_st = football_data_get_standings()
            if df_st is None:
                st.info(
                    "Para mostrar a classificação, configure a variável de ambiente **FOOTBALL_DATA_TOKEN** "
                    "(football-data.org)."
                )
            else:
                st.dataframe(df_st, use_container_width=True, hide_index=True)

        with tabB:
            df_sc = football_data_get_scorers(20)
            if df_sc is None:
                st.info(
                    "Para mostrar artilheiros, configure **FOOTBALL_DATA_TOKEN** "
                    "(football-data.org)."
                )
            else:
                st.dataframe(df_sc, use_container_width=True, hide_index=True)

        with tabC:
            df_cards = api_football_get_cards_table()
            if df_cards is None:
                st.info(
                    "Para cartões (amarelo/vermelho), configure **API_FOOTBALL_KEY**. "
                    "Se quiser dados por temporada/liga, configure também **API_FOOTBALL_LEAGUE** e **API_FOOTBALL_SEASON**."
                )
            else:
                st.dataframe(df_cards, use_container_width=True, hide_index=True)

    # Fetch data
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

    # Save price history
    atletas_raw = (mercado.get("atletas") or mercado.get("atleta") or [])
    storage.upsert_price_history(rodada, atletas_raw)

    # Save partial points if exists
    if isinstance(parciais, dict):
        points_map = parciais.get("atletas") or parciais.get("pontuados") or {}
        if isinstance(points_map, dict) and points_map:
            storage.upsert_points_history(rodada, points_map)

    # Header metrics
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric("Rodada", rodada)
    with c2:
        mercado_txt = MERCADO_MAP.get(status.get("status_mercado"), str(status.get("status_mercado")))
        st.metric("Mercado", mercado_txt)
    with c3:
        st.metric("Parciais", "Disponíveis" if parciais is not None else "Indisponíveis")
    with c4:
        st.metric("Atletas no mercado", len(atletas_raw))

    # Build main df
    df = make_dataframe(rodada, mercado, db_path=storage.DB_PATH_DEFAULT)
    df = valuation_heuristic(df)
    df = df_with_status_and_photo(df, mercado)

    # Filter
    df_filtered = filter_probables(df, only_probable=only_probable)

    # Tabs: rankings / lista rodada / time
    st.divider()
    tab1, tab2, tab3 = st.tabs(["📊 Rankings", "🗒️ Lista da rodada", "🧠 Montar time"])

    # ---- Rankings
    with tab1:
        st.subheader("📊 Ranking (por posição)")
        pos_tabs = st.tabs(["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC", "Todos"])
        for i, pos in enumerate(["GOL", "LAT", "ZAG", "MEI", "ATA", "TEC"]):
            with pos_tabs[i]:
                d = top_by_position(df_filtered, pos, n=30)
                cols = ["apelido", "clube", "posicao", "status_nome", "preco", "media", "delta_preco", "score_final", "bonus_valorizacao"]
                existing = [c for c in cols if c in d.columns]
                st.dataframe(d[existing], use_container_width=True, hide_index=True)

        with pos_tabs[-1]:
            cols = ["apelido", "clube", "posicao", "status_nome", "preco", "media", "delta_preco", "score_final", "bonus_valorizacao"]
            existing = [c for c in cols if c in df_filtered.columns]
            st.dataframe(
                df_filtered.sort_values("score_final", ascending=False).head(200)[existing],
                use_container_width=True,
                hide_index=True,
            )

    # ---- Lista da rodada (todos do mercado)
    with tab2:
        st.subheader("🗒️ Todos os jogadores do mercado (rodada)")
        st.caption("Mostra status (provável/dúvida/suspenso/contundido etc.) e foto quando disponível no payload.")

        # Filtros locais
        colA, colB, colC = st.columns([2, 2, 2])
        with colA:
            search = st.text_input("Buscar jogador", value="")
        with colB:
            pos_filter = st.selectbox("Filtrar posição", options=["(todas)"] + sorted(df["posicao"].dropna().unique().tolist()))
        with colC:
            status_filter = st.selectbox("Filtrar status", options=["(todos)"] + sorted(df["status_nome"].dropna().unique().tolist()))

        d = df.copy()

        if search.strip():
            d = d[d["apelido"].str.contains(search.strip(), case=False, na=False)]

        if pos_filter != "(todas)":
            d = d[d["posicao"] == pos_filter]

        if status_filter != "(todos)":
            d = d[d["status_nome"] == status_filter]

        # Colunas que fazem sentido
        show_cols = ["foto_url", "apelido", "clube", "posicao", "status_nome", "preco", "media", "delta_preco", "score_final"]
        show_cols = [c for c in show_cols if c in d.columns]
        d = d.sort_values(["status_nome", "posicao", "score_final"], ascending=[True, True, False])

        # Render com imagem por linha (Streamlit dataframe não renderiza imagem nativamente)
        # Então fazemos um "cards list" simples:
        st.write(f"**Total:** {len(d)}")
        for _, row in d.head(250).iterrows():
            cimg, cinfo, cstats = st.columns([1, 3, 2])
            with cimg:
                if row.get("foto_url"):
                    st.image(row["foto_url"], width=56)
                else:
                    st.write("—")
            with cinfo:
                st.markdown(f"**{row.get('apelido','')}**  \n{row.get('clube','')} • {row.get('posicao','')} • **{row.get('status_nome','')}**")
            with cstats:
                st.write(
                    f"C$ {row.get('preco', 0):.2f} | Média: {row.get('media', 0):.2f} | Δ: {row.get('delta_preco', 0) if pd.notna(row.get('delta_preco')) else '—'}"
                )

        if len(d) > 250:
            st.info("Mostrando apenas os 250 primeiros (use busca/filtros para refinar).")

    # ---- Montar time (campo visual)
    with tab3:
        st.subheader("🧠 Montar time")
        st.caption("Muda a formação e o campo reposiciona automaticamente o time sugerido.")

        team, left = build_team_greedy(df_filtered, formation=formation, budget=float(budget))

        # Campo visual
        fig = None
        try:
            fig = draw_pitch(team, formation)
        except Exception as e:
            st.warning(f"Não consegui desenhar o campo (verifique pitch.py): {e}")

        if fig is not None:
            st.plotly_chart(fig, use_container_width=True)

        # Lista do time sugerido
        if team.empty:
            st.warning(
                "Não consegui montar um time com os filtros/orçamento atuais. "
                "Tente aumentar o orçamento ou desmarcar 'somente prováveis'."
            )
        else:
            st.success(f"Time montado na formação {formation}. Sobra: C$ {left:.2f}")
            cols = ["foto_url", "apelido", "clube", "posicao", "status_nome", "preco", "media", "delta_preco", "score_final"]
            cols = [c for c in cols if c in team.columns]

            # Mostrar em cards com foto
            for _, row in team.sort_values(["posicao", "score_final"], ascending=[True, False]).iterrows():
                a, b, c = st.columns([1, 3, 2])
                with a:
                    if row.get("foto_url"):
                        st.image(row["foto_url"], width=64)
                    else:
                        st.write("—")
                with b:
                    st.markdown(f"**{row.get('apelido','')}**  \n{row.get('clube','')} • {row.get('posicao','')}")
                with c:
                    st.write(f"C$ {row.get('preco', 0):.2f} | Score: {row.get('score_final', 0):.2f}")

            st.write(f"**Custo total:** C$ {(float(budget) - left):.2f}")

        with st.expander("🔎 Jogos da rodada (partidas)"):
            st.json(partidas)

        with st.expander("🧾 Debug (status/mercado)"):
            st.json({"status": status, "keys_mercado": list(mercado.keys())})


if __name__ == "__main__":
    main()
