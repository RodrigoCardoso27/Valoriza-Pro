from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

DB_PATH_DEFAULT = os.path.join("data", "cartola.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  rodada INTEGER NOT NULL,
  kind TEXT NOT NULL,          -- 'mercado', 'partidas', 'status', 'parciais'
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_rodada_kind ON snapshots(rodada, kind);

CREATE TABLE IF NOT EXISTS athlete_price_history (
  athlete_id INTEGER NOT NULL,
  rodada INTEGER NOT NULL,
  price REAL,
  PRIMARY KEY (athlete_id, rodada)
);

CREATE TABLE IF NOT EXISTS athlete_points_history (
  athlete_id INTEGER NOT NULL,
  rodada INTEGER NOT NULL,
  points REAL,
  PRIMARY KEY (athlete_id, rodada)
);
"""

@contextmanager
def connect(db_path: str = DB_PATH_DEFAULT):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        yield conn
    finally:
        conn.close()

def init_db(db_path: str = DB_PATH_DEFAULT) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
        conn.commit()

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def save_snapshot(rodada: int, kind: str, payload: dict, db_path: str = DB_PATH_DEFAULT) -> None:
    init_db(db_path)
    with connect(db_path) as conn:
        conn.execute(
            "INSERT INTO snapshots(rodada, kind, payload_json, created_at) VALUES (?,?,?,?)",
            (rodada, kind, json.dumps(payload, ensure_ascii=False), now_iso()),
        )
        conn.commit()

def load_latest_snapshot(rodada: int, kind: str, db_path: str = DB_PATH_DEFAULT) -> dict | None:
    init_db(db_path)
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT payload_json FROM snapshots WHERE rodada=? AND kind=? ORDER BY id DESC LIMIT 1",
            (rodada, kind),
        )
        row = cur.fetchone()
        if not row:
            return None
        return json.loads(row[0])

def upsert_price_history(rodada: int, athletes: list[dict], db_path: str = DB_PATH_DEFAULT) -> None:
    """
    athletes: lista do mercado; cada atleta deve ter id e preco_num.
    """
    init_db(db_path)
    with connect(db_path) as conn:
        for a in athletes:
            aid = a.get("atleta_id") or a.get("id")
            if aid is None:
                continue
            price = a.get("preco_num")
            conn.execute(
                "INSERT OR REPLACE INTO athlete_price_history(athlete_id, rodada, price) VALUES (?,?,?)",
                (int(aid), int(rodada), float(price) if price is not None else None),
            )
        conn.commit()

def upsert_points_history(rodada: int, points_map: dict, db_path: str = DB_PATH_DEFAULT) -> None:
    """
    points_map: dict athlete_id -> dict com pontuacao/scouts (formato típico do endpoint pontuados)
    """
    init_db(db_path)
    with connect(db_path) as conn:
        for aid_str, pdata in points_map.items():
            try:
                aid = int(aid_str)
            except Exception:
                continue
            pts = pdata.get("pontuacao")
            conn.execute(
                "INSERT OR REPLACE INTO athlete_points_history(athlete_id, rodada, points) VALUES (?,?,?)",
                (aid, int(rodada), float(pts) if pts is not None else None),
            )
        conn.commit()

def get_last_price(athlete_id: int, rodada: int, db_path: str = DB_PATH_DEFAULT) -> float | None:
    init_db(db_path)
    with connect(db_path) as conn:
        cur = conn.execute(
            "SELECT price FROM athlete_price_history WHERE athlete_id=? AND rodada<? ORDER BY rodada DESC LIMIT 1",
            (athlete_id, rodada),
        )
        row = cur.fetchone()
        return None if not row else row[0]
