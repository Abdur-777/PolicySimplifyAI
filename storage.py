# storage.py — Day 4
# SQLite persistence for policy cards + simple event log with retention

from __future__ import annotations
import os, sqlite3, time
from typing import List, Dict, Any

DB_PATH = os.getenv("DB_PATH", "./policy.db")

SCHEMA = """
CREATE TABLE IF NOT EXISTS policy_cards (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_name TEXT NOT NULL,
  summary TEXT NOT NULL,
  checklist TEXT NOT NULL,
  risk TEXT NOT NULL,
  risk_explainer TEXT NOT NULL,
  created_at INTEGER NOT NULL
);
"""

EVENTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  kind TEXT NOT NULL,
  detail TEXT NOT NULL
);
"""

def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute(SCHEMA)
    con.execute(EVENTS_SCHEMA)
    return con

def save_card(card: Dict[str, Any]) -> None:
    con = _conn()
    with con:
        con.execute(
            "INSERT INTO policy_cards (source_name, summary, checklist, risk, risk_explainer, created_at) VALUES (?,?,?,?,?,?)",
            (
                card.get("policy") or card.get("source_name") or "Unknown",
                card.get("summary",""),
                card.get("checklist",""),
                card.get("risk","Medium"),
                card.get("risk_explainer",""),
                int(card.get("created_at") or time.time()),
            ),
        )
    con.close()

def load_cards(limit: int = 500) -> List[Dict[str, Any]]:
    con = _conn()
    cur = con.execute(
        "SELECT source_name, summary, checklist, risk, risk_explainer, created_at FROM policy_cards "
        "ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    con.close()
    out: List[Dict[str, Any]] = []
    for r in rows:
        out.append({
            "policy": r[0],
            "summary": r[1],
            "checklist": r[2],
            "risk": r[3],
            "risk_explainer": r[4],
            "created_at": r[5],
        })
    return out

def clear_all() -> None:
    con = _conn()
    with con:
        con.execute("DELETE FROM policy_cards")
        con.execute("DELETE FROM events")
    con.close()

def log_event(kind: str, detail: str) -> None:
    con = _conn()
    with con:
        con.execute("INSERT INTO events (ts, kind, detail) VALUES (?,?,?)", (int(time.time()), kind, detail))
    con.close()

def recent_events(limit: int = 5) -> List[Dict[str, Any]]:
    con = _conn()
    cur = con.execute("SELECT ts, kind, detail FROM events ORDER BY ts DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    con.close()
    return [{"ts": r[0], "kind": r[1], "detail": r[2]} for r in rows]

def purge_older_than(days: int) -> int:
    """Delete events and cards older than N days. Returns total rows removed."""
    cutoff = int(time.time()) - days * 86400
    con = _conn()
    with con:
        e = con.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
        c = con.execute("DELETE FROM policy_cards WHERE created_at < ?", (cutoff,))
        removed = (e.rowcount or 0) + (c.rowcount or 0)
    con.close()
    return removed
