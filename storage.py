# storage.py
# SQLite-based persistence for cards (per-tenant) and lightweight event logging.

from __future__ import annotations
import os
import time
import json
import sqlite3
from typing import List, Dict, Any, Optional

_DB_PATH = os.getenv("DB_PATH", "./policy.db")


# ---------------------------
# Low-level helpers
# ---------------------------

def _connect() -> sqlite3.Connection:
    # check_same_thread=False to play nicely with Streamlit reruns
    con = sqlite3.connect(_DB_PATH, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL;")   # better concurrency
    con.execute("PRAGMA synchronous=NORMAL;") # perf tradeoff OK for demo
    return con


def _init():
    with _connect() as con:
        con.execute("""
        CREATE TABLE IF NOT EXISTS cards(
            id INTEGER PRIMARY KEY,
            tenant TEXT,
            policy TEXT,
            summary TEXT,
            checklist TEXT,
            risk TEXT,
            risk_explainer TEXT,
            structured_tasks TEXT,
            created_at INTEGER
        );
        """)
        # Backfill 'tenant' column if DB created before multi-tenant
        try:
            con.execute("ALTER TABLE cards ADD COLUMN tenant TEXT;")
        except Exception:
            pass

        con.execute("""
        CREATE TABLE IF NOT EXISTS events(
            ts INTEGER,
            tenant TEXT,
            kind TEXT,
            detail TEXT
        );
        """)


# ---------------------------
# Card CRUD
# ---------------------------

def save_card(card: Dict[str, Any]) -> None:
    """
    Persist a generated policy 'card'.
    Required keys: policy, summary, checklist
    Optional: risk, risk_explainer, structured_tasks (list), created_at, tenant
    """
    _init()
    tenant = card.get("tenant", "default")
    structured_tasks = json.dumps(card.get("structured_tasks", []))
    created_at = int(card.get("created_at", time.time()))
    with _connect() as con:
        con.execute(
            """
            INSERT INTO cards(
                tenant, policy, summary, checklist, risk, risk_explainer, structured_tasks, created_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                tenant,
                card.get("policy", ""),
                card.get("summary", ""),
                card.get("checklist", ""),
                card.get("risk", ""),
                card.get("risk_explainer", ""),
                structured_tasks,
                created_at,
            ),
        )


def load_cards(tenant: str, limit: int = 500) -> List[Dict[str, Any]]:
    """
    Load most recent cards for a tenant.
    """
    _init()
    with _connect() as con:
        rows = con.execute(
            """
            SELECT policy, summary, checklist, risk, risk_explainer, structured_tasks, created_at, tenant
            FROM cards
            WHERE tenant=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (tenant, int(limit)),
        ).fetchall()

    out: List[Dict[str, Any]] = []
    for policy, summary, checklist, risk, rexpl, tasks_json, ts, t in rows:
        try:
            tasks = json.loads(tasks_json) if tasks_json else []
        except Exception:
            tasks = []
        out.append(
            {
                "policy": policy,
                "summary": summary,
                "checklist": checklist,
                "risk": risk,
                "risk_explainer": rexpl,
                "structured_tasks": tasks,
                "created_at": int(ts or 0),
                "tenant": t or tenant,
            }
        )
    return out


def purge_older_than(tenant: str, days: int) -> int:
    """
    Delete card/event rows older than 'days' for a tenant.
    Returns number of card rows removed.
    """
    _init()
    cutoff = int(time.time() - days * 86400)
    with _connect() as con:
        cur = con.execute(
            "DELETE FROM cards WHERE tenant=? AND created_at < ?",
            (tenant, cutoff),
        )
        con.execute(
            "DELETE FROM events WHERE tenant=? AND ts < ?",
            (tenant, cutoff),
        )
        removed = cur.rowcount or 0
    return removed


def delete_all_for_tenant(tenant: str) -> None:
    """
    Hard-delete ALL data for the tenant (cards + events).
    """
    _init()
    with _connect() as con:
        con.execute("DELETE FROM cards WHERE tenant=?", (tenant,))
        con.execute("DELETE FROM events WHERE tenant=?", (tenant,))


# ---------------------------
# Event log (light analytics / audit)
# ---------------------------

def log_event(kind: str, detail: str, tenant: str = "default") -> None:
    _init()
    with _connect() as con:
        con.execute(
            "INSERT INTO events(ts, tenant, kind, detail) VALUES(?,?,?,?)",
            (int(time.time()), tenant, kind, detail),
        )


def recent_events(limit: int = 10, tenant: str = "default") -> List[Dict[str, Any]]:
    _init()
    with _connect() as con:
        rows = con.execute(
            "SELECT ts, kind, detail FROM events WHERE tenant=? ORDER BY ts DESC LIMIT ?",
            (tenant, int(limit)),
        ).fetchall()
    return [{"ts": int(ts), "kind": k, "detail": d} for (ts, k, d) in rows]
