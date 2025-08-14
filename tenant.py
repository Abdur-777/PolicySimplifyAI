# tenant.py
from __future__ import annotations
import json, os, streamlit as st

_PATH = "assets/councils/councils.json"

def load_directory() -> dict:
    try:
        with open(_PATH, "r") as f:
            return json.load(f)
    except Exception:
        return {"version":1, "councils":[], "defaults":{"plan":"pro","retention_days":180}}

def current_council_key() -> str:
    qp = st.query_params.get("council")
    if isinstance(qp, list): qp = qp[0] if qp else None
    return (qp or os.getenv("COUNCIL_KEY") or os.getenv("BRAND_KEY") or "default").lower()

def resolve_council() -> dict:
    data = load_directory()
    key = current_council_key()
    defaults = data.get("defaults", {})
    match = next((c for c in data.get("councils", []) if c["key"].lower() == key), None)
    # base record
    rec = {
        "key": key,
        "name": (match or {}).get("name", "PolicySimplify"),
        "state": (match or {}).get("state", data.get("default_state", "VIC")),
        "plan": defaults.get("plan", "pro"),
        "retention_days": int(defaults.get("retention_days", 180)),
        "primary": defaults.get("primary", "#1555C0"),
        "secondary": defaults.get("secondary", "#0B2A5C"),
        "accent": defaults.get("accent", "#00B3A4"),
        "logo": defaults.get("logo", "assets/brands/default/logo.png")
    }
    # overrides
    ov = data.get("overrides", {}).get(key)
    if ov:
        rec.update(ov)
    # env hard overrides (for private pilots)
    if os.getenv("RETENTION_DAYS"):
        rec["retention_days"] = int(os.getenv("RETENTION_DAYS"))
    if os.getenv("PLAN"):
        rec["plan"] = os.getenv("PLAN")
    return rec
