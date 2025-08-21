# ================================
# PolicySimplify AI – Full app.py (with test flow help)
# ================================
import os, io, json, time
from datetime import datetime

import streamlit as st
import pandas as pd

# Local modules
from pdf_loader import load_pdf
from checklist_generator import (
    generate_summary, generate_checklist, assess_risk, compose_policy_card
)
from storage import save_policy, load_policies

# ---- APP CONFIG ----
st.set_page_config(page_title="PolicySimplify AI", page_icon="✅", layout="wide")

TENANT_KEY = st.sidebar.selectbox("Switch brand / tenant", ["wyndham-city", "default"], index=0)

# ================================
# HELP PANEL — YOUR TEST FLOW
# ================================
with st.expander("❓ How this works (test flow) — click to open", expanded=False):
    st.markdown("""
**Upload screen**
- You’ll see the file appear in the uploader box with its name (e.g., `child-safe-policy.pdf`).
- Click **“Process uploaded PDF”**.

**Processing**
- A spinner will show:
  - “Reading policy…”
  - “Generating summary…”
  - “Generating checklist…”
  - “Assessing risk…”

**Confirmation**
- A green ✅ success message:
  - `Added child-safe-policy.pdf to wyndham-city.`

**Dashboard table (main view)**
- A new row at the top of the table:
  - **Policy** → `child-safe-policy.pdf`
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

# ================================
# PROCESS POLICY FUNCTION
# ================================
def process_policy(
    source_name: str,
    tenant_key: str,
    file_bytes: bytes | None = None,
    raw_text: str | None = None,
    source_type: str | None = None,
):
    """
    Ingests a PDF (bytes) or raw text, generates summary/checklist/risk,
    saves a compact record to storage, adds a full 'card' to session, and returns it.
    """
    with st.spinner("Reading policy..."):
        if file_bytes:
            text = load_pdf(file_bytes)
            if source_type is None:
                source_type = "Uploaded"
        else:
            text = (raw_text or "").strip()
            if source_type is None:
                source_type = "Text"

    if not text:
        st.warning("No text found in the policy (is it a scanned PDF or empty file?).")
        return None

    # Generate AI outputs
    with st.spinner("Generating summary..."):
        summary = generate_summary(text)
    with st.spinner("Generating checklist..."):
        checklist = generate_checklist(text, summary)
    with st.spinner("Assessing risk..."):
        risk_obj = assess_risk(text, summary)

    # Compose display card
    card = compose_policy_card(
        policy=source_name,
        summary=summary,
        checklist=checklist,
        risk=risk_obj
    )
    card["created_at"] = datetime.now().timestamp()
    card["source_type"] = source_type

    # Persist compact record
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
        st.warning(f"Saved session only (could not persist record): {e}")

    # Add to session
    st.session_state.setdefault("cards", [])
    st.session_state["cards"].insert(0, card)

    st.success(f"✅ Added **{source_name}** to **{tenant_key}**.")
    return card

# ================================
# DASHBOARD RENDERER
# ================================
def render_dashboard_table(tenant_key: str):
    """Renders merged table of saved records + session cards."""
    # Saved compact records
    saved = load_policies(tenant_key)
    saved_rows = []
    for rec in saved:
        saved_rows.append({
            "Policy": rec.get("title", ""),
            "Summary (plain-English)": rec.get("summary", ""),
            "Checklist (actions)": "",
            "Risk": rec.get("risk", ""),
            "Risk explainer": rec.get("risk_explainer", ""),
            "Source Type": rec.get("type", "Saved"),
            "Processed": rec.get("date", ""),
            "_source": "saved",
            "_created_ts": 0.0,
        })

    # Session cards
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
    if not rows:
        st.info("No items yet. Upload a PDF or paste text above.")
        return

    df = pd.DataFrame(rows)
    order_risk = {"High": 0, "Medium": 1, "Low": 2, "": 3}
    df["_r"] = df["Risk"].map(order_risk).fillna(3)
    df = df.sort_values(by=["_source", "_r", "_created_ts"], ascending=[True, True, False]).drop(columns=["_r","_created_ts"])

    st.markdown("### 2) Active compliance items")
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
        use_container_width=True,
        height=420
    )

    # Details panel
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

    # Export
    st.markdown("#### Export current view")
    st.download_button(
        "Download CSV",
        data=view_df.to_csv(index=False).encode("utf-8"),
        file_name="policy_items.csv",
        mime="text/csv",
        use_container_width=True
    )
    st.download_button(
        "Download JSON",
        data=json.dumps(view_df.to_dict(orient="records"), indent=2).encode("utf-8"),
        file_name="policy_items.json",
        mime="application/json",
        use_container_width=True
    )

# ================================
# MAIN APP LAYOUT
# ================================
st.title("✅ PolicySimplify AI")
st.markdown("### 1) Upload or paste a policy")

upl = st.file_uploader("Upload a PDF", type=["pdf"], key="uploader")
if upl is not None and st.button("Process uploaded PDF", use_container_width=True):
    process_policy(source_name=upl.name, tenant_key=TENANT_KEY, file_bytes=upl.read())

txt = st.text_area("...or paste raw policy text")
if txt.strip() and st.button("Process pasted text", use_container_width=True):
    process_policy(source_name="pasted-policy.txt", tenant_key=TENANT_KEY, raw_text=txt)

# Dashboard
render_dashboard_table(TENANT_KEY)
