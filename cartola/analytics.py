from __future__ import annotations

import math
import pandas as pd
from .utils import POS_MAP, coalesce
from .storage import get_last_price

DEFAULT_PROVAVEL_STATUS_ID = 7

def normalize_athletes_payload(payload: dict) -> tuple[list[dict], dict, dict]:
    """
    Retorna (athletes, clubes_map, posicoes_map)
    - Alguns payloads vêm com chaves 'atletas' e 'clubes' (dict) e 'posicoes' (dict)
    """
    athletes = payload.get("atletas") or payload.get("atleta") or []
    clubes = payload.get("clubes") or {}
    posicoes = payload.get("posicoes") or {}
    return athletes, clubes, posicoes

def make_dataframe(rodada: int, mercado_payload: dict, db_path: str) -> pd.DataFrame:
    athletes, clubes, posicoes = normalize_athletes_payload(mercado_payload)

    rows = []
    for a in athletes:
        aid = a.get("atleta_id") or a.get("id")
        if aid is None:
            continue
        pos_id = a.get("posicao_id")
        club_id = a.get("clube_id")
        price = a.get("preco_num")
        media = a.get("media_num")
        pontos = a.get("pontos_num")
        status_id = a.get("status_id")

        # nome do clube pode estar em dict por id (às vezes string-key)
        club = clubes.get(str(club_id)) or clubes.get(int(club_id)) if club_id is not None else None
        club_name = None
        if isinstance(club, dict):
            club_name = club.get("nome") or club.get("abreviacao")
        elif club is not None:
            club_name = str(club)

        pos_name = None
        pos = posicoes.get(str(pos_id)) or posicoes.get(int(pos_id)) if pos_id is not None else None
        if isinstance(pos, dict):
            pos_name = pos.get("nome")
        pos_name = coalesce(pos_name, POS_MAP.get(pos_id), str(pos_id) if pos_id is not None else None)

        last_price = get_last_price(int(aid), int(rodada), db_path=db_path)

        rows.append({
            "athlete_id": int(aid),
            "apelido": a.get("apelido") or a.get("nome") or "",
            "posicao_id": pos_id,
            "posicao": pos_name,
            "clube_id": club_id,
            "clube": club_name or "",
            "status_id": status_id,
            "preco": float(price) if price is not None else None,
            "media": float(media) if media is not None else None,
            "pontos_ultima": float(pontos) if pontos is not None else None,
            "preco_anterior": float(last_price) if last_price is not None else None,
        })

    df = pd.DataFrame(rows)

    # delta preço (quando existir)
    if not df.empty:
        df["delta_preco"] = df["preco"] - df["preco_anterior"]
    return df

def valuation_heuristic(df: pd.DataFrame) -> pd.DataFrame:
    """
    Heurística simples:
    - Jogador barato que tem média boa tende a valorizar (principalmente começo).
    - Se preço caiu na rodada anterior (delta_preco negativo), tende a buscar recuperação.
    Retorna df com colunas: alvo_pontos_1rod, bonus_valorizacao, score_base, score_final
    """
    if df.empty:
        return df

    # alvo de pontos na rodada 1 (~46% do preço). Usamos 0.46 por padrão.
    df["alvo_pontos_1rod"] = df["preco"] * 0.46

    # bônus: preço baixo + média alta + recuperação
    # normalizações robustas
    preco = df["preco"].fillna(0)
    media = df["media"].fillna(0)
    delta = df["delta_preco"].fillna(0)

    # quanto menor o preço, maior o bônus (log para não explodir)
    bonus_preco = (1 / (1 + preco)).clip(lower=0)
    bonus_media = (media / (media.max() if media.max() > 0 else 1)).clip(0, 1)
    bonus_recuperacao = (-delta).clip(lower=0)  # se caiu, positivo

    df["bonus_valorizacao"] = (0.6 * bonus_preco + 0.3 * bonus_media + 0.1 * bonus_recuperacao)

    # score base: média + (pequeno ajuste pela última pontuação se disponível)
    df["score_base"] = df["media"].fillna(0) + 0.15 * df["pontos_ultima"].fillna(0)
    df["score_final"] = df["score_base"] + 2.0 * df["bonus_valorizacao"]

    return df

def filter_probables(df: pd.DataFrame, only_probable: bool = True) -> pd.DataFrame:
    if df.empty:
        return df
    if only_probable:
        return df[df["status_id"] == DEFAULT_PROVAVEL_STATUS_ID].copy()
    return df.copy()

def top_by_position(df: pd.DataFrame, pos: str, n: int = 20) -> pd.DataFrame:
    d = df[df["posicao"] == pos].sort_values("score_final", ascending=False)
    return d.head(n)
