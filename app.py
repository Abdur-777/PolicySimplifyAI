# =========================================
# PolicySimplify AI — Wyndham-only app.py
# =========================================
from __future__ import annotations

import os, json, time, requests
from datetime import datetime

import streamlit as st
import pandas as pd

# Local modules you already have:
# - pdf_loader.py -> load_pdf(bytes) -> str
# - checklist_generator.py -> generate_summary, generate_checklist, assess_risk, compose_policy_card
# - storage.py -> save_policy(tenant, dict), load_policies(tenant)
from pdf_loader import load_pdf
from checklist_generator import (
    generate_summary,
    generate_checklist,
    assess_risk,
    compose_policy_card,
)
from storage import save_policy, load_policies

# ---------- Fixed tenant (Wyndham only) ----------
TENANT_KEY  = "wyndham-city"
TENANT_NAME = "Wyndham City Council"

# ---------- App config ----------
st.set_page_config(page_title="PolicySimplify AI — Wyndham", page_icon="✅", layout="wide")

# ---------- Simple Wyndham branding ----------
WYNDHAM_BRAND = {
    "name": TENANT_NAME,
    "primary":   "#0051A5",
    "secondary": "#012B55",
    "accent":    "#00B3A4",
    # Optional local asset path if you have it in your repo:
    # "logo": "assets/brands/wyndham.png",
    "logo": None,
}

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

apply_brand()

# ---------- Help / test flow ----------
with st.expander("❓ How this works (test flow) — click to open", expanded=False):
    st.markdown("""
**Upload screen**
- You’ll see the file appear in the uploader box with its name (e.g., `child-safe-policy-example.pdf`).
- Click **“Process uploaded PDF”**.

**Processing**
- A spinner will show:
  - “Reading policy…”
  - “Generating summary…”
  - “Generating checklist…”
  - “Assessing risk…”

**Confirmation**
- A green ✅ success message:
  - `Added child-safe-policy-example.pdf to wyndham-city.`

**Dashboard table (main view)**
- A new row at the top of the table:
  - **Policy** → `child-safe-policy-example.pdf`
  - **Summary (plain-English)** → AI-generated summary of the document
  - **Checklist (actions)** → action points extracted from the policy
  - **Risk** → “High”, “Medium”, or “Low”
  - **Risk explainer** → short reasoning for that risk level
  - **Source Type** → “Uploaded”
  - **Processed** → today’s date/time

**Details panel (below the table)**
- When you select the row #, you’ll see:
  - **Policy name**
  - **Risk**
  - **Source Type**
  - **Processed date**
  - **Full plain-English summary**
  - **Checklist (actions)**
  - **Risk explainer**

**Export**
- Click:
  - **Download CSV** → exports the table view
  - **Download JSON** → exports full details
""")


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


def render_dashboard_table(tenant_key: str):
    """Merged table: Saved compact records + full session cards."""
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
        st.info("No items yet. Upload a PDF or use the sample button above.")
        return

    df = pd.DataFrame(rows)
    order_risk = {"High": 0, "Medium": 1, "Low": 2, "": 3}
    df["_r"] = df["Risk"].map(order_risk).fillna(3)
    df = df.sort_values(by=["_source", "_r", "_created_ts"], ascending=[True, True, False]).drop(columns=["_r","_created_ts"])

    left, right = st.columns([0.7, 0.3])
    with left:
        risk_filter = st.multiselect("Filter by risk", ["High","Medium","Low"], default=["High","Medium","Low"])
    with right:
        high_only = st.checkbox("High risk only", value=False)

    if high_only:
        view_df = df[df["Risk"].eq("High")]
    else:
        view_df = df[df["Risk"].isin(risk_filter)]

    view_df = view_df.reset_index(drop=True)
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


# ---------- Main layout (Wyndham only) ----------
st.title("✅ PolicySimplify AI — Wyndham")
st.markdown("### 1) Upload or test a policy")

colA, colB = st.columns(2)

with colA:
    upl = st.file_uploader("Upload a PDF", type=["pdf"], key="uploader")
    if upl is not None and st.button("Process uploaded PDF", use_container_width=True):
        process_policy(source_name=upl.name, tenant_key=TENANT_KEY, file_bytes=upl.read())

with colB:
    if st.button("▶️ Test with sample PDF (Vic Child Safe Policy)", use_container_width=True):
        demo_url = "https://www.vic.gov.au/sites/default/files/2021-04/child-safe-policy-example.pdf"
        try:
            r = requests.get(demo_url, timeout=30)
            r.raise_for_status()
            process_policy(
                source_name="child-safe-policy-example.pdf",
                tenant_key=TENANT_KEY,
                file_bytes=r.content,
                source_type="URL"
            )
        except Exception as e:
            st.error(f"Demo fetch failed: {e}")

# Optional: paste raw text
txt = st.text_area("...or paste raw policy text")
if txt.strip() and st.button("Process pasted text", use_container_width=True):
    process_policy(source_name="pasted-policy.txt", tenant_key=TENANT_KEY, raw_text=txt)

# Dashboard table
render_dashboard_table(TENANT_KEY)

st.caption("© 2025 PolicySimplify AI — Wyndham demo")
