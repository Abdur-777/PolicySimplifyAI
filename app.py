# app.py — PolicySimplify AI (Streamlit)
# ---------------------------------------------------------
# - No signup required
# - Upload a policy PDF OR use a built-in example
# - Plain-English summary, compliance checklist, risk label
# - Vector store: FAISS if available, else pure NumPy fallback
# - Friendly exports & diagnostics
# ---------------------------------------------------------

from __future__ import annotations

import os
import io
import json
import time
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

# Local modules (already provided)
from pdf_loader import extract_text_from_pdf_bytes, chunk_text, make_docs
from vectorstore import SimpleFAISS
from checklist_generator import (
    generate_summary,
    generate_checklist,
    assess_risk,
    compose_policy_card,
)

# --------------------- Setup & Config ---------------------
load_dotenv()

APP_NAME = os.getenv("APP_NAME", "PolicySimplify AI")
APP_TAGLINE = os.getenv("APP_TAGLINE", "Turn any government policy into an instant compliance checklist.")
VECTOR_DB_NAME = os.getenv("VECTOR_DB_NAME", "demo_store")

# Safety caps for very large policies (chars)
TEXT_CAP = int(os.getenv("TEXT_CAP", "120000"))

# Page config
st.set_page_config(page_title=APP_NAME, page_icon="✅", layout="wide")

# Query-param healthcheck (Render/uptime monitors)
# Example: https://your-app-url/?health=1
if st.experimental_get_query_params().get("health") == ["1"]:
    st.write("ok")
    st.stop()

# --------------------- Session State ----------------------
if "store" not in st.session_state:
    st.session_state["store"] = SimpleFAISS.load(VECTOR_DB_NAME)

if "policy_cards" not in st.session_state:
    st.session_state["policy_cards"] = []

# --------------------- Header / Branding ------------------
with st.container():
    col1, col2 = st.columns([0.75, 0.25])
    with col1:
        st.markdown(f"## {APP_NAME}")
        st.markdown(f"_{APP_TAGLINE}_")
    with col2:
        st.markdown("<div style='text-align:right;'>🔒 No sign-up • Demo-ready</div>", unsafe_allow_html=True)
st.divider()

# --------------------- Sidebar Controls ------------------
with st.sidebar:
    st.markdown("### Controls")
    st.caption("Quick actions & diagnostics")
    clear_btn = st.button("🗑️ Clear session (policies & index)")
    if clear_btn:
        st.session_state["policy_cards"] = []
        # Reinitialize a fresh store
        st.session_state["store"] = SimpleFAISS.load(VECTOR_DB_NAME)
        st.success("Cleared session memory for this demo.")

    st.markdown("---")
    st.markdown("### Diagnostics")
    # Detect backend type (FAISS vs NumPy) by attribute presence
    backend = "FAISS" if hasattr(st.session_state["store"], "index") and st.session_state["store"].index is not None else "NumPy"
    st.write(f"Vector backend: **{backend}**")
    st.write(f"Indexed docs: **{len(getattr(st.session_state['store'], 'docs', []))}**")
    st.write(f"Saved store name: `{VECTOR_DB_NAME}`")

# --------------------- Example Policy ---------------------
example_text = """Policy Directive: Waste Services Bin Contamination

1. Households must not place hazardous items (batteries, chemicals) in general waste.
2. Repeated contamination may lead to fines or service suspension.
3. Education notices must be delivered within 30 days after first offence.
4. Annual reporting to Council on contamination rates is required by 30 September each year.

Penalties apply for non-compliance. Council teams must document outreach and enforcement actions.
"""

# --------------------- Core Processor ---------------------
def process_policy(source_name: str, *, file_bytes: bytes | None = None, raw_text: str | None = None):
    """
    Reads, indexes, and generates summary/checklist/risk for a policy.
    Appends a policy card dict into session state.
    """
    # 1) Get text
    with st.spinner("Reading policy..."):
        if file_bytes:
            text = extract_text_from_pdf_bytes(file_bytes)
        else:
            text = raw_text or ""
        text = (text or "").strip()
        if not text:
            st.warning("No text found in the policy (this may be a scanned PDF without OCR).")
            return
        # Cap extreme size for cost/perf safety
        if len(text) > TEXT_CAP:
            text = text[:TEXT_CAP]

    # 2) Chunk + make docs
    chunks = chunk_text(text)
    docs = make_docs(chunks, source_name)

    # 3) Index into vector store (helps future extensions/Q&A)
    with st.spinner("Indexing..."):
        st.session_state["store"].add(docs)
        st.session_state["store"].save(VECTOR_DB_NAME)

    # 4) Generate outputs (use middle chunk as a representative slice)
    with st.spinner("Generating summary, checklist & risk..."):
        center_idx = len(docs) // 2 if docs else 0
        text_for_ai = docs[center_idx]["text"] if docs else text

        try:
            summary = generate_summary(text_for_ai)
            checklist = generate_checklist(text_for_ai, summary)
            risk_note = assess_risk(text_for_ai, summary)
        except Exception as e:
            st.error(f"OpenAI error: {e}")
            return

        card = compose_policy_card(source_name, summary, checklist, risk_note)
        st.session_state["policy_cards"].append(card)

# --------------------- Ingest Section ---------------------
st.markdown("### 1) Ingest a policy")
up_col, url_col, ex_col = st.columns([0.45, 0.35, 0.2])

with up_col:
    uploaded = st.file_uploader("Upload a policy PDF", type=["pdf"], help="Drag and drop or click to select a PDF.")
    if uploaded is not None:
        if st.button("Process uploaded PDF"):
            process_policy(source_name=uploaded.name, file_bytes=uploaded.read())

with url_col:
    st.text("Fetch PDF from URL")
    policy_url = st.text_input("Policy PDF URL (https://...)", placeholder="https://example.gov.au/policy.pdf")
    if st.button("Fetch & process URL"):
        if not policy_url.strip():
            st.warning("Please paste a valid URL to a PDF.")
        else:
            try:
                with st.spinner("Downloading PDF..."):
                    r = requests.get(policy_url, timeout=20)
                    r.raise_for_status()
                    content_type = r.headers.get("Content-Type", "")
                    if "pdf" not in content_type.lower() and not policy_url.lower().endswith(".pdf"):
                        st.warning("The URL does not look like a PDF; attempting anyway.")
                process_policy(source_name=os.path.basename(policy_url) or "Policy_From_URL.pdf", file_bytes=r.content)
            except Exception as e:
                st.error(f"Failed to fetch policy PDF: {e}")

with ex_col:
    st.text("No PDF handy?")
    if st.button("Use example policy"):
        process_policy(source_name="Example_Waste_Services_Policy.txt", raw_text=example_text)

st.caption("Tip: If your PDF is scanned, run OCR first (Preview/Adobe → Export with OCR).")
st.divider()

# --------------------- Results Table ----------------------
st.markdown("### 2) Active compliance items")
if not st.session_state["policy_cards"]:
    st.info("Upload a PDF, paste a policy URL, or click **Use example policy** to generate actions.")
else:
    df = pd.DataFrame(
        [
            {
                "Policy": c["policy"],
                "Summary (plain-English)": c["summary"],
                "Checklist (actions)": c["checklist"],
                "Risk": c["risk"],
                "Risk explainer": c["risk_explainer"],
            }
            for c in st.session_state["policy_cards"]
        ]
    )

    # Filters
    risk_filter = st.multiselect("Filter by risk", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    view_df = df[df["Risk"].isin(risk_filter)].reset_index(drop=True)

    st.dataframe(view_df, use_container_width=True, height=380)

    # Detail viewer
    st.markdown("#### Policy details")
    if len(view_df) > 0:
        idx = st.number_input(
            "Select row # to view details",
            min_value=0,
            max_value=len(view_df) - 1,
            value=0,
            step=1,
        )
        row = view_df.iloc[int(idx)]
        st.markdown(f"**Policy:** {row['Policy']}")
        st.markdown(f"**Risk:** {row['Risk']}")
        st.markdown("**Summary:**")
        st.write(row["Summary (plain-English)"])
        st.markdown("**Checklist:**")
        st.write(row["Checklist (actions)"])

    # Exports (CSV/JSON)
    st.markdown("#### Export")
    csv_bytes = view_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download table as CSV",
        data=csv_bytes,
        file_name="policy_compliance_items.csv",
        mime="text/csv",
        use_container_width=True,
    )

    json_bytes = json.dumps(view_df.to_dict(orient="records"), indent=2).encode("utf-8")
    st.download_button(
        "Download table as JSON",
        data=json_bytes,
        file_name="policy_compliance_items.json",
        mime="application/json",
        use_container_width=True,
    )

st.divider()

# --------------------- Future Hooks / Stubs ----------------
st.markdown("### 3) Export & alerts (demo stubs)")
c1, c2, c3 = st.columns(3)
with c1:
    st.button("Export Audit Pack (PDF) — Coming soon")
with c2:
    st.button("Email Weekly Digest — Coming soon")
with c3:
    st.button("Assign in MS Teams — Coming soon")

# Footer
st.caption("© 2025 PolicySimplify AI — Demo build")
