# =========================================
# PolicySimplify AI — Wyndham-only app.py
# =========================================
from __future__ import annotations

import os, json, time, requests
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any

import streamlit as st
import pandas as pd
from dotenv import load_dotenv

# Local modules (keep these files alongside app.py)
from pdf_loader import load_pdf
from checklist_generator import (
    generate_summary,
    generate_checklist,
    assess_risk,
    compose_policy_card,
)
from storage import save_policy, load_policies, clear_policies

# ---------- Fixed tenant (Wyndham only) ----------
TENANT_KEY  = "wyndham-city"
TENANT_NAME = "Wyndham City Council"

# ---------- Config / Env ----------
load_dotenv()
ADMIN_PIN = os.getenv("ADMIN_PIN", "")  # optional; set in .env to enable Admin > Delete All

# Branding (logo optional; place file if you have it)
WYNDHAM_BRAND = {
    "name": TENANT_NAME,
    "primary":   "#0051A5",
    "secondary": "#012B55",
    "accent":    "#00B3A4",
    "logo": None,  # e.g. "assets/brands/wyndham.png"
}

# Preload location
PRELOAD_JSON = "assetssss/preloads/_shared/wyndham-city/demo_policies.json"

st.set_page_config(page_title="PolicySimplify AI — Wyndham", page_icon="✅", layout="wide")


# ---------- Branding helpers ----------
def apply_brand():
    primary   = WYNDHAM_BRAND["primary"]
    secondary = WYNDHAM_BRAND["secondary"]
    accent    = WYNDHAM_BRAND["accent"]
    st.markdown(
        f"""
        <style>
          :root {{
            --ps-primary: {primary};
            --ps-secondary: {secondary};
            --ps-accent: {accent};
          }}
          .ps-title h2 {{ color: var(--ps-secondary); margin: 0; }}
          .ps-sub {{ opacity: .85; }}
          .stButton>button {{
            background: var(--ps-primary); color:#fff; border:0; border-radius:.5rem; padding:.5rem .9rem;
          }}
          .stButton>button:hover {{ filter: brightness(.95); }}
          .searchbox input {{
            border: 1px solid var(--ps-secondary) !important;
          }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    c1, c2 = st.columns([0.82, 0.18])
    with c1:
        st.markdown(
            f"<div class='ps-title'><h2>PolicySimplify AI</h2>"
            f"<div class='ps-sub'><em>Turn any government policy into an instant compliance checklist.</em></div></div>",
            unsafe_allow_html=True,
        )
        st.caption(f"Tenant: **{TENANT_NAME}** • Key: `{TENANT_KEY}`")
    with c2:
        logo = WYNDHAM_BRAND.get("logo")
        if logo and os.path.exists(logo):
            st.image(logo, use_column_width=True)
    st.divider()


# ---------- Core pipeline ----------
def process_policy(
    source_name: str,
    tenant_key: str,
    file_bytes: bytes | None = None,
    raw_text: str | None = None,
    source_type: str | None = None,
):
    """Extracts text, generates summary/checklist/risk, persists compact record, stores session card."""
    # 1) Text
    with st.spinner("Reading policy..."):
        if file_bytes:
            text = load_pdf(file_bytes)
            source_type = source_type or "Uploaded"
        else:
            text = (raw_text or "").strip()
            source_type = source_type or "Text"

    if not text:
        st.warning("No text found in the policy (is it a scanned/empty PDF?).")
        return None

    # 2) AI passes
    with st.spinner("Generating summary..."):
        summary = generate_summary(text)
    with st.spinner("Generating checklist..."):
        checklist = generate_checklist(text, summary)
    with st.spinner("Assessing risk..."):
        risk_obj = assess_risk(text, summary)  # dict: {"level","explainer"}

    # 3) Compose full card for this session
    card = compose_policy_card(
        policy=source_name,
        summary=summary,
        checklist=checklist,
        risk=risk_obj,
    )
    card["created_at"]  = datetime.now().timestamp()
    card["source_type"] = source_type

    # 4) Persist compact record for Wyndham
    try:
        save_policy(tenant_key, {
            "title": source_name,
            "summary": summary[:800],
            "date": datetime.now().strftime("%Y-%m-%d"),
            "type": source_type,
            "risk": risk_obj.get("level", "Medium"),
            "risk_explainer": risk_obj.get("explainer", "")
        })
    except Exception as e:
        st.warning(f"Saved session only (could not persist compact record): {e}")

    # 5) Add to session
    st.session_state.setdefault("cards", [])
    st.session_state["cards"].insert(0, card)

    st.success(f"✅ Added **{source_name}** to **{tenant_key}**.")
    return card


def _load_preload_list() -> List[Dict[str, Any]]:
    """Load a list of {'name': '...', 'url': 'https://...pdf'} from demo_policies.json."""
    fp = Path(PRELOAD_JSON)
    if not fp.exists():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        out = []
        if isinstance(data, list):
            for item in data:
                url = item.get("url")
                nm  = item.get("name") or (os.path.basename(url) if url else "Policy.pdf")
                if url and url.lower().endswith(".pdf"):
                    out.append({"name": nm, "url": url})
        return out
    except Exception as e:
        st.warning(f"Invalid JSON in {PRELOAD_JSON}: {e}")
        return []


def render_dashboard_table(tenant_key: str):
    """Merged table: Saved compact records + full session cards + search & filters."""
    # Saved compact records (from storage.py)
    saved = load_policies(tenant_key)
    saved_rows = []
    for rec in saved:
        saved_rows.append({
            "Policy": rec.get("title", ""),
            "Summary (plain-English)": rec.get("summary", ""),
            "Checklist (actions)": "",  # compact store doesn't keep full checklist
            "Risk": rec.get("risk", ""),
            "Risk explainer": rec.get("risk_explainer", ""),
            "Source Type": rec.get("type", "Saved"),
            "Processed": rec.get("date", ""),
            "_source": "saved",
            "_created_ts": 0.0,
        })

    # Session cards (full)
    session_cards = st.session_state.get("cards", [])
    session_rows = []
    for c in session_cards:
        session_rows.append({
            "Policy": c.get("policy", ""),
            "Summary (plain-English)": c.get("summary", ""),
            "Checklist (actions)": c.get("checklist", ""),
            "Risk": c.get("risk", ""),
            "Risk explainer": c.get("risk_explainer", ""),
            "Source Type": c.get("source_type", "Session"),
            "Processed": time.strftime("%Y-%m-%d %H:%M", time.localtime(c.get("created_at", time.time()))),
            "_source": "session",
            "_created_ts": c.get("created_at", time.time()),
        })

    rows = session_rows + saved_rows
    st.markdown("### 2) Active compliance items")
    if not rows:
        st.info("No items yet. Upload a PDF or use Preload in the sidebar.")
        return

    df = pd.DataFrame(rows)
    order_risk = {"High": 0, "Medium": 1, "Low": 2, "": 3}
    df["_r"] = df["Risk"].map(order_risk).fillna(3)
    df = df.sort_values(by=["_source", "_r", "_created_ts"], ascending=[True, True, False]).drop(columns=["_r","_created_ts"])

    # Search + filters
    colL, colR = st.columns([0.72, 0.28])
    with colL:
        q = st.text_input("Search (title/summary/checklist)", key="search_q", placeholder="e.g., child safety, recycling", help="Filters rows containing these keywords.")
    with colR:
        risk_filter = st.multiselect("Risk filter", ["High","Medium","Low"], default=["High","Medium","Low"])

    if q:
        q_lower = q.lower()
        df = df[
            df["Policy"].str.lower().str.contains(q_lower) |
            df["Summary (plain-English)"].str.lower().str.contains(q_lower) |
            df["Checklist (actions)"].str.lower().str.contains(q_lower)
        ]

    if risk_filter:
        df = df[df["Risk"].isin(risk_filter)]

    view_df = df.reset_index(drop=True)
    st.dataframe(
        view_df[["Policy","Summary (plain-English)","Checklist (actions)","Risk","Risk explainer","Source Type","Processed"]],
        use_container_width=True, height=420
    )

    st.markdown("#### Policy details")
    if len(view_df) > 0:
        idx = st.number_input("Select row #", min_value=0, max_value=len(view_df)-1, value=0, step=1)
        row = view_df.iloc[int(idx)]
        st.markdown(f"**Policy:** {row['Policy']}")
        st.markdown(f"**Risk:** {row.get('Risk','')}")
        st.markdown(f"**Source Type:** {row.get('Source Type','')}")
        st.markdown(f"**Processed:** {row.get('Processed','')}")
        st.markdown("**Summary:**");   st.write(row["Summary (plain-English)"])
        st.markdown("**Checklist:**"); st.write(row["Checklist (actions)"])
        st.markdown("**Risk explainer:**"); st.write(row.get("Risk explainer",""))

    st.markdown("#### Export current view")
    st.download_button(
        "Download CSV",
        data=view_df.to_csv(index=False).encode("utf-8"),
        file_name="policy_items_wyndham.csv",
        mime="text/csv",
        use_container_width=True
    )
    st.download_button(
        "Download JSON",
        data=json.dumps(view_df.to_dict(orient="records"), indent=2).encode("utf-8"),
        file_name="policy_items_wyndham.json",
        mime="application/json",
        use_container_width=True
    )

    # --- Audit Pack (PDF) — stub now writes TXT to avoid extra deps
    st.markdown("#### Audit Pack")
    if st.button("Generate Audit Pack (TXT)"):
        if len(view_df) == 0:
            st.warning("Nothing to export.")
        else:
            # Build a simple text pack
            lines = []
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")
            lines.append(f"PolicySimplify AI — Audit Pack ({TENANT_NAME}) — {ts}")
            lines.append("="*80)
            for i, r in view_df.iterrows():
                lines.append(f"\n[{i+1}] {r['Policy']}")
                lines.append(f"Risk: {r.get('Risk','')}")
                lines.append(f"Processed: {r.get('Processed','')}")
                lines.append("\nSummary:\n" + (r.get("Summary (plain-English)","") or ""))
                cl = r.get("Checklist (actions)","") or ""
                lines.append("\nChecklist:\n" + cl)
                lines.append("\n" + "-"*60)

            txt = "\n".join(lines).encode("utf-8")
            st.download_button(
                "Download Audit Pack (TXT)",
                data=txt,
                file_name="audit_pack_wyndham.txt",
                mime="text/plain",
                use_container_width=True
            )
            st.info("This is a lightweight TXT export. Swap to a real PDF generator later (e.g., `reportlab` or `fpdf`).")


# ---------- App UI ----------
apply_brand()

# Help / test flow
with st.expander("❓ How this works — click to open", expanded=False):
    st.markdown("""
**Upload**
1) Choose a PDF, then click **Process uploaded PDF**.

**What you’ll see**
- Spinners: *Reading policy → Generating summary → Generating checklist → Assessing risk*
- ✅ Success toast
- A new row appears at the top of the **Active compliance items** table
- Select a row to view **Summary**, **Checklist**, **Risk explainer**

**Exports**
- Download CSV/JSON
- Generate **Audit Pack (TXT)** (swap to PDF later)
""")

# Sidebar — Upload / Paste / Preload / Admin
st.sidebar.markdown("### Ingest a policy")
upl = st.sidebar.file_uploader("Upload PDF", type=["pdf"])
if upl and st.sidebar.button("Process uploaded PDF"):
    process_policy(source_name=upl.name, tenant_key=TENANT_KEY, file_bytes=upl.read())

raw = st.sidebar.text_area("...or paste raw policy text")
if raw.strip() and st.sidebar.button("Process pasted text"):
    process_policy(source_name="pasted-policy.txt", tenant_key=TENANT_KEY, raw_text=raw)

st.sidebar.markdown("---")
st.sidebar.markdown("### Preload (Wyndham)")
if st.sidebar.button("Preload demo_policies.json"):
    items = _load_preload_list()
    if not items:
        st.sidebar.warning(f"No preloads found at {PRELOAD_JSON}")
    else:
        added = 0
        for item in items:
            try:
                r = requests.get(item["url"], timeout=30)
                r.raise_for_status()
                process_policy(source_name=item["name"], tenant_key=TENANT_KEY, file_bytes=r.content, source_type="URL")
                added += 1
            except Exception as e:
                st.sidebar.error(f"Failed {item.get('name','(unknown)')}: {e}")
        st.sidebar.success(f"Preloaded {added} document(s).")

st.sidebar.markdown("---")
st.sidebar.markdown("### Admin")
pin = st.sidebar.text_input("Enter admin PIN", type="password")
if st.sidebar.button("🗑️ Delete ALL saved items") and ADMIN_PIN:
    if pin == ADMIN_PIN:
        ok = clear_policies(TENANT_KEY)
        st.sidebar.success("Deleted saved compact records for this tenant.")
    else:
        st.sidebar.error("Wrong PIN.")
elif ADMIN_PIN == "":
    st.sidebar.caption("Set ADMIN_PIN in .env to enable delete.")


# ---------- Main sections ----------
st.markdown("### 1) Dashboard")
render_dashboard_table(TENANT_KEY)

st.caption("© 2025 PolicySimplify AI — Wyndham demo")
