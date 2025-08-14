# brand.py
from __future__ import annotations
import json, os, streamlit as st

_BRAND_ROOT = "assets/brands"

def _safe_read(path: str) -> dict:
    try:
        with open(path, "r") as f: 
            return json.load(f)
    except Exception:
        return {}

def get_brand_for_key(brand_key: str, fallback_name: str, primary: str, secondary: str, accent: str):
    cfg = _safe_read(f"{_BRAND_ROOT}/{brand_key}/brand.json")
    logo_path = f"{_BRAND_ROOT}/{brand_key}/logo.png"
    if not os.path.exists(logo_path):
        logo_path = f"{_BRAND_ROOT}/default/logo.png"
    # Merge colours from council directory if brand.json missing
    cfg = {
        "name": cfg.get("name", fallback_name),
        "primary": cfg.get("primary", primary),
        "secondary": cfg.get("secondary", secondary),
        "accent": cfg.get("accent", accent),
        "text_on_primary": cfg.get("text_on_primary", "#ffffff"),
        "logo_alt": cfg.get("logo_alt", fallback_name)
    }
    return cfg, logo_path

def inject_theme(cfg: dict):
    primary = cfg.get("primary", "#1555C0")
    secondary = cfg.get("secondary", "#0B2A5C")
    accent = cfg.get("accent", "#00B3A4")
    st.markdown(f"""
    <style>
      :root {{
        --brand-primary: {primary};
        --brand-secondary: {secondary};
        --brand-accent: {accent};
      }}
      .stApp [data-testid="stHeader"] {{
        background: linear-gradient(90deg, var(--brand-secondary), var(--brand-primary));
      }}
      .stApp a {{ color: var(--brand-primary) !important; }}
      .stApp .stButton>button[kind="primary"] {{
        background: var(--brand-primary) !important;
        color: {cfg.get("text_on_primary", "#fff")} !important;
        border: 0 !important;
      }}
    </style>
    """, unsafe_allow_html=True)
