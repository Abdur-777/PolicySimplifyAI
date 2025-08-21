# app.py — PolicySimplify AI (streamlined, no-FAISS version)
from __future__ import annotations

import os, io, json, time, requests
from typing import List, Dict, Any
from pathlib import Path

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# --- Local modules (make sure these files exist) ---
# pdf_loader.py must define: load_pdf(file_bytes: bytes) -> str
from pdf_loader import load_pdf
# checklist_generator.py must define the following (from my previous message):
#   generate_summary, generate_checklist, assess_risk, compose_policy_card, qa_answer
from checklist_generator import (
    generate_summary, generate_checklist, assess_risk, compose_policy_card, qa_answer
)
# storage.py must define: save_policy(council_key, dict), load_policies(council_key), clear_policies(council_key)
from storage import save_policy, load_policies, clear_policies

# =========================
# Setup
# =========================
load_dotenv()

APP_NAME    = os.getenv("APP_NAME", "PolicySimplify AI")
APP_TAGLINE = os.getenv("APP_TAGLINE", "Turn any government policy into an instant compliance checklist.")
SALES_MODE_DEFAULT = os.getenv("SALES_MODE_DEFAULT", "true").lower() == "true"

# IMPORTANT: Your assets folder is spelled "assetssss"
PRELOAD_SHARED_BASE = "assetssss/preloads/_shared"

st.set_page_config(page_title=APP_NAME, page_icon="✅", layout="wide")

# =========================
# Branding helpers
# =========================
def _load_brand_map() -> Dict[str, Dict[str, Any]]:
    """
    Optionally load council brand config from council_brands.json at repo root.
    Example entry:
      "wyndham-city": {
        "name": "Wyndham City Council",
        "primary": "#0051A5",
        "secondary": "#012B55",
        "accent": "#00B3A4",
        "logo": "assets/brands/wyndham.png"
      }
    """
    cfg = {}
    f = Path("council_brands.json")
    if f.exists():
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
        except Exception as e:
            st.warning(f"Could not read council_brands.json: {e}")
    return cfg

BRANDS = _load_brand_map()

def apply_brand_header(council_key: str, council_label: str):
    cfg = BRANDS.get(council_key, {})
    primary   = cfg.get("primary", "#0B2A5C")
    secondary = cfg.get("secondary", "#1555C0")
    accent    = cfg.get("accent", "#00B3A4")

    st.markdown(
        f"""
        <style>
          :root {{ --ps-primary:{primary}; --ps-secondary:{secondary}; --ps-accent:{accent}; }}
          .ps-header h2 {{ color: var(--ps-secondary); margin: 0; }}
          .ps-sub {{ opacity:.85; }}
          .stButton>button {{
             background: var(--ps-primary);
             color: #fff; border-radius: .5rem; border: 0; padding: .5rem .9rem;
          }}
          .stButton>button:hover {{
             filter: brightness(.95);
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

    c1, c2 = st.columns([0.82, 0.18])
    with c1:
        st.markdown(
            f"<div class='ps-header'><h2>{APP_NAME}</h2>"
            f"<div class='ps-sub'><em>{APP_TAGLINE}</em></div></div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Tenant: **{council_label}** • Key: `{council_key}`")
    with c2:
        logo = cfg.get("logo")
        if logo and Path(logo).exists():
            st.image(logo, use_column_width=True)
    st.divider()

# =========================
# Preloads & councils
# =========================
def list_council_keys() -> List[str]:
    base = Path(PRELOAD_SHARED_BASE)
    if not base.exists():
        return []
    return sorted([p.name for p in base.iterdir() if p.is_dir()])

def load_demo_list_for(council_key: str) -> List[Dict[str, Any]]:
    """
    Loads _shared/<council>/demo_policies.json (list of {"name": "...","url": "https://...pdf"})
    """
    fp = Path(PRELOAD_SHARED_BASE) / council_key / "demo_policies.json"
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        out = []
        for item in data if isinstance(data, list) else []:
            url = item.get("url")
            nm  = item.get("name") or (os.path.basename(url) if url else "Policy.pdf")
            if url and url.lower().endswith(".pdf"):
                out.append({"name": nm, "url": url})
        return out
    except Exception as e:
        st.warning(f"Invalid JSON in {fp}: {e}")
        return []

def council_label_for(key: str) -> str:
    return BRANDS.get(key, {}).get("name", key.replace("-", " ").title())

# =========================
# Policy processing
# =========================
def process_text_to_card(source_name: str, council_key: str, text: str) -> Dict[str, Any]:
    """
    Generates summary/checklist/risk from extracted text and returns a normalized card dict.
    Also saves a compact policy entry via storage.save_policy().
    """
    text = (text or "").strip()
    if not text:
        st.warning("No text found to process.")
        return {}

    # Summaries
    with st.spinner("Generating summary..."):
        summary = generate_summary(text)
    with st.spinner("Generating checklist..."):
        checklist = generate_checklist(text, summary)
    with st.spinner("Assessing risk..."):
        risk_obj = assess_risk(text, summary)  # dict: {"level","explainer"}
    card = compose_policy_card(source_name, summary, checklist, risk_obj)

    # Save a compact record for this council (so it persists)
    try:
        save_policy(council_key, {
            "title": source_name,
            "summary": summary[:800],
            "date": time.strftime("%Y-%m-%d"),
            "source": source_name
        })
    except Exception as e:
        st.warning(f"Could not save compact record: {e}")

    return card

def process_pdf_bytes(source_name: str, council_key: str, file_bytes: bytes) -> Dict[str, Any]:
    """
    Extracts text from PDF bytes, then passes to process_text_to_card.
    """
    with st.spinner("Reading PDF..."):
        text = load_pdf(file_bytes)
    return process_text_to_card(source_name, council_key, text)

# =========================
# Sidebar: Sales Mode & council selection (single-return selectbox)
# =========================
st.sidebar.markdown("### 🎬 Sales Mode")
if "sales_mode" not in st.session_state:
    st.session_state["sales_mode"] = SALES_MODE_DEFAULT
sales_on = st.sidebar.toggle("Enable Sales Mode", value=st.session_state["sales_mode"])
st.session_state["sales_mode"] = sales_on

council_keys = list_council_keys() or ["wyndham-city"]
labels = {k: council_label_for(k) for k in council_keys}

# Resolve current tenant key from query param / session / default
query_c = st.query_params.get("council")
if isinstance(query_c, list):
    query_c = query_c[0] if query_c else None
current_key = st.session_state.get("council_override") or query_c or council_keys[0]
if current_key not in council_keys:
    current_key = council_keys[0]

if sales_on:
    try:
        idx_default = council_keys.index(current_key)
    except ValueError:
        idx_default = 0

    chosen_key = st.sidebar.selectbox(
        "Choose council",
        council_keys,
        index=idx_default,
        format_func=lambda k: labels.get(k, k.replace("-", " ").title())
    )

    colX, colY = st.sidebar.columns(2)
    with colX:
        if st.button("Switch brand", use_container_width=True):
            st.session_state["council_override"] = chosen_key
            st.toast(f"Switched to {labels.get(chosen_key, chosen_key)}")
            st.experimental_rerun()
    with colY:
        if st.button("Use URL/default", use_container_width=True):
            st.session_state.pop("council_override", None)
            st.experimental_rerun()

TENANT_KEY = st.session_state.get("council_override") or current_key
TENANT_NAME = labels.get(TENANT_KEY, TENANT_KEY.replace("-", " ").title())

# =========================
# Header
# =========================
apply_brand_header(TENANT_KEY, TENANT_NAME)

# =========================
# Sidebar: Ingest a policy
# =========================
st.sidebar.markdown("---")
st.sidebar.markdown("### Ingest a policy")

upl = st.sidebar.file_uploader("Upload PDF", type=["pdf"])
if upl and st.sidebar.button("Process uploaded PDF"):
    card = process_pdf_bytes(upl.name, TENANT_KEY, upl.read())
    if card:
        st.session_state.setdefault("cards", [])
        st.session_state["cards"].insert(0, card)  # newest first
        st.sidebar.success("Processed uploaded PDF.")

url_in = st.sidebar.text_input("Or fetch from URL (must end with .pdf)")
if st.sidebar.button("Fetch & process URL"):
    if not url_in or not url_in.lower().endswith(".pdf"):
        st.sidebar.warning("Please provide a direct .pdf URL.")
    else:
        try:
            r = requests.get(url_in, timeout=30)
            r.raise_for_status()
            name = os.path.basename(url_in) or "Policy.pdf"
            card = process_pdf_bytes(name, TENANT_KEY, r.content)
            if card:
                st.session_state.setdefault("cards", [])
                st.session_state["cards"].insert(0, card)
                st.sidebar.success("Fetched & processed.")
        except Exception as e:
            st.sidebar.error(f"Fetch failed: {e}")

st.sidebar.markdown("---")
st.sidebar.markdown("### Demo preload")
if st.sidebar.button("Preload demo_policies.json"):
    demo = load_demo_list_for(TENANT_KEY)
    if not demo:
        st.sidebar.warning(
            f"No preloads for '{TENANT_KEY}'. Put demo_policies.json under "
            f"{PRELOAD_SHARED_BASE}/{TENANT_KEY}/"
        )
    else:
        added = 0
        for item in demo:
            try:
                r = requests.get(item["url"], timeout=30)
                r.raise_for_status()
                card = process_pdf_bytes(item["name"], TENANT_KEY, r.content)
                if card:
                    st.session_state.setdefault("cards", [])
                    st.session_state["cards"].insert(0, card)
                    added += 1
            except Exception as e:
                st.sidebar.error(f"Failed {item.get('name','(unknown)')}: {e}")
        st.sidebar.success(f"Preloaded {added} document(s).")

st.sidebar.markdown("---")
st.sidebar.markdown("### Admin")
if st.sidebar.button("🗑️ Delete ALL compact records for this council"):
    ok = clear_policies(TENANT_KEY)
    if ok:
        st.sidebar.success("Deleted compact policy list for this council (demo_policies.json).")
    else:
        st.sidebar.info("Nothing to delete.")

# =========================
# Main: load persisted compact list (for context) + show session cards
# =========================
# Session cards (full AI output) live only for the current app session
if "cards" not in st.session_state:
    st.session_state["cards"] = []

# Risk overview (session only)
st.markdown("### 1) Risk overview")
if not st.session_state["cards"]:
    st.info("Upload a PDF, paste a URL, or use **Preload demo_policies.json** in the sidebar.")
else:
    def _count_checkboxes(s: str) -> int:
        return sum(1 for ln in (s or "").splitlines() if ln.strip().startswith("- ["))

    cards = st.session_state["cards"]
    total_policies = len(cards)
    obligations = sum(_count_checkboxes(c.get("checklist","")) for c in cards)
    high = sum(1 for c in cards if c.get("risk") == "High")
    med  = sum(1 for c in cards if c.get("risk") == "Medium")
    low  = sum(1 for c in cards if c.get("risk") == "Low")

    a,b,c = st.columns(3)
    a.metric("Total Policies (this session)", total_policies)
    b.metric("High Risk", high)
    c.metric("Obligations (approx.)", obligations)

st.divider()

# Active items table (session)
st.markdown("### 2) Active compliance items")
if not st.session_state["cards"]:
    st.info("No items yet. Ingest a PDF or preload demo.")
else:
    df = pd.DataFrame([{
        "Policy": rec["policy"],
        "Summary (plain-English)": rec.get("summary",""),
        "Checklist (actions)": rec.get("checklist",""),
        "Risk": rec.get("risk",""),
        "Risk explainer": rec.get("risk_explainer",""),
        "Processed": time.strftime("%Y-%m-%d %H:%M", time.localtime(rec.get("created_at", time.time())))
    } for rec in st.session_state["cards"]])

    order = {"High":0,"Medium":1,"Low":2}
    if "Risk" in df.columns:
        df["_o"] = df["Risk"].map(order).fillna(3)
        df = df.sort_values(by=["_o","Processed","Policy"], ascending=[True,False,True]).drop(columns=["_o"])

    colA, colB = st.columns([0.7, 0.3])
    with colA:
        risk_filter = st.multiselect("Filter by risk", ["High","Medium","Low"], default=["High","Medium","Low"])
    with colB:
        high_only = st.checkbox("High risk only", value=False)

    view_df = df[df["Risk"].eq("High")] if high_only else df[df["Risk"].isin(risk_filter)]
    view_df = view_df.reset_index(drop=True)
    st.dataframe(view_df, use_container_width=True, height=420)

    st.markdown("#### Policy details")
    if len(view_df) > 0:
        idx = st.number_input("Select row #", min_value=0, max_value=len(view_df)-1, value=0, step=1)
        row = view_df.iloc[int(idx)]
        st.markdown(f"**Policy:** {row['Policy']}")
        st.markdown(f"**Risk:** {row.get('Risk','')}")
        st.markdown(f"**Processed:** {row.get('Processed','')}")
        st.markdown("**Summary:**");   st.write(row["Summary (plain-English)"])
        st.markdown("**Checklist:**"); st.write(row["Checklist (actions)"])
        st.markdown("**Risk explainer:**"); st.write(row.get("Risk explainer",""))

    st.markdown("#### Export current view")
    st.download_button("Download CSV", data=view_df.to_csv(index=False).encode("utf-8"),
                       file_name="policy_items.csv", mime="text/csv", use_container_width=True)
    st.download_button("Download JSON", data=json.dumps(view_df.to_dict(orient="records"), indent=2).encode("utf-8"),
                       file_name="policy_items.json", mime="application/json", use_container_width=True)

st.divider()

# Q&A (lightweight: just concatenates the last few summaries as context)
st.markdown("### 3) Ask the policy")
q = st.text_input("Ask a question about the policies you've processed in this session")
if st.button("Get answer"):
    if not q.strip():
        st.warning("Type a question first.")
    elif not st.session_state["cards"]:
        st.info("No context yet. Ingest a policy first.")
    else:
        # Use summaries + checklist text from the most recent policies as snippets
        snippets = []
        for c in st.session_state["cards"][:4]:
            snippets.append((c.get("summary","") + "\n" + c.get("checklist","")).strip()[:4000])
        ans = qa_answer(snippets, q)
        st.markdown("**Answer:**")
        st.write(ans)
        with st.expander("Context used"):
            for i, s in enumerate(snippets, start=1):
                st.markdown(f"**Snippet {i}**")
                st.code(s[:800])

st.caption("© 2025 PolicySimplify AI — streamlined demo build")
