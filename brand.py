# brand.py
import json, os, streamlit as st

_BRAND_ROOT = "assets/brands"

def _safe_read(path: str) -> dict:
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return {
            "name": "PolicySimplify AI",
            "primary": "#1f6feb",
            "secondary": "#0a3069",
            "accent": "#06b6d4",
            "text_on_primary": "#ffffff",
            "logo_alt": "PolicySimplify AI"
        }

def resolve_brand_key() -> str:
    qp = st.query_params.get("brand")
    if isinstance(qp, list):
        qp = qp[0] if qp else None
    return (qp or os.getenv("BRAND_KEY") or "default").lower()

def get_brand():
    key = resolve_brand_key()
    cfg = _safe_read(f"{_BRAND_ROOT}/{key}/brand.json")
    logo_path = f"{_BRAND_ROOT}/{key}/logo.png"
    if not os.path.exists(logo_path):
        logo_path = f"{_BRAND_ROOT}/default/logo.png"
    return key, cfg, logo_path

def inject_theme(cfg: dict):
    primary = cfg.get("primary", "#1f6feb")
    secondary = cfg.get("secondary", "#0a3069")
    accent = cfg.get("accent", "#06b6d4")
    st.markdown(f"""
    <style>
      :root {{
        --brand-primary: {primary};
        --brand-secondary: {secondary};
        --brand-accent: {accent};
      }}
      .stApp button[kind="primary"],
      .stApp [data-testid="baseButton-primary"] {{
        background: var(--brand-primary) !important;
        color: {cfg.get("text_on_primary", "#ffffff")} !important;
        border: none !important;
      }}
      .stApp a {{ color: var(--brand-primary) !important; }}
      .stApp [data-testid="stHeader"] {{
        background: linear-gradient(90deg, var(--brand-secondary), var(--brand-primary));
      }}
    </style>
    """, unsafe_allow_html=True)
