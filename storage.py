# storage.py — tiny SQLite persistence for policy cards
import os, sqlite3, json, time
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

def _conn():
    os.makedirs(os.path.dirname(DB_PATH) or ".", exist_ok=True)
    con = sqlite3.connect(DB_PATH, check_same_thread=False)
    con.execute(SCHEMA)
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
                int(time.time()),
            ),
        )
    con.close()

def load_cards(limit: int = 500) -> List[Dict[str, Any]]:
    con = _conn()
    cur = con.execute(
        "SELECT source_name, summary, checklist, risk, risk_explainer, created_at FROM policy_cards ORDER BY created_at DESC LIMIT ?",
        (limit,),
    )
    rows = cur.fetchall()
    con.close()
    out = []
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
    con.close()
