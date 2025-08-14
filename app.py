import os
import io
import time
import numpy as np
import streamlit as st
from dotenv import load_dotenv

from pdf_loader import extract_text_from_pdf_bytes, chunk_text, make_docs
from vectorstore import SimpleFAISS
from checklist_generator import generate_summary, generate_checklist, assess_risk, compose_policy_card

# ---- Setup ----
load_dotenv()
APP_NAME = os.getenv("APP_NAME", "PolicySimplify AI")
APP_TAGLINE = os.getenv("APP_TAGLINE", "Turn any government policy into an instant compliance checklist.")

st.set_page_config(page_title=APP_NAME, page_icon="✅", layout="wide")

# ---- Header / Branding ----
with st.container():
    col1, col2 = st.columns([0.8, 0.2])
    with col1:
        st.markdown(f"## {APP_NAME}")
        st.markdown(f"_{APP_TAGLINE}_")
    with col2:
        st.markdown("<div style='text-align:right;'>🔒 No sign-up • Demo-ready</div>", unsafe_allow_html=True)
st.divider()

# ---- Upload & Example ----
st.markdown("### 1) Upload a policy (PDF) or try an example")
uploaded = st.file_uploader("Drop a policy PDF here", type=["pdf"])
use_example = st.button("Use example policy text")

if "store" not in st.session_state:
    st.session_state["store"] = SimpleFAISS.load("demo_store")

if "policy_cards" not in st.session_state:
    st.session_state["policy_cards"] = []

example_text = """Policy Directive: Waste Services Bin Contamination
- Households must not place hazardous items (batteries, chemicals) in general waste.
- Repeated contamination may lead to fines or suspension.
- Education notices must be delivered within 30 days after first offence.
- Annual reporting to Council on contamination rates is required by Sept 30 each year."""

def process_policy(source_name: str, file_bytes: bytes = None, raw_text: str = None):
    with st.spinner("Reading policy..."):
        if file_bytes:
            text = extract_text_from_pdf_bytes(file_bytes)
        else:
            text = raw_text or ""
        if not text.strip():
            st.warning("No text found in the policy (is it a scanned PDF?).")
            return

    chunks = chunk_text(text)
    docs = make_docs(chunks, source_name)

    # Index to FAISS for retrieval (useful for future Q&A & expansions)
    with st.spinner("Indexing..."):
        st.session_state["store"].add(docs)
        st.session_state["store"].save("demo_store")

    # Summarize + Checklist + Risk
    with st.spinner("Generating summary & checklist..."):
        # Use the most central chunk for speed (middle)
        center_idx = len(docs)//2
        text_for_ai = docs[center_idx]["text"] if docs else text[:3000]
        summary = generate_summary(text_for_ai)
        checklist = generate_checklist(text_for_ai, summary)
        risk_note = assess_risk(text_for_ai, summary)
        card = compose_policy_card(source_name, summary, checklist, risk_note)
        st.session_state["policy_cards"].append(card)

st.markdown(
    "<small>Tip: For scanned PDFs, run OCR first (e.g., in Preview > Export as PDF > 'Use OCR').</small>",
    unsafe_allow_html=True
)

colA, colB = st.columns(2)
with colA:
    if uploaded is not None:
        if st.button("Process uploaded policy"):
            process_policy(source_name=uploaded.name, file_bytes=uploaded.read())
with colB:
    if use_example:
        process_policy(source_name="Example_Waste_Services_Policy.txt", raw_text=example_text)

st.divider()

# ---- Results Table ----
st.markdown("### 2) Active Compliance Items")
if not st.session_state["policy_cards"]:
    st.info("Upload a PDF or click 'Use example policy text' to generate summaries and checklists.")
else:
    import pandas as pd
    df = pd.DataFrame([{
        "Policy": c["policy"],
        "Summary (plain-English)": c["summary"],
        "Checklist (actions)": c["checklist"],
        "Risk": c["risk"],
        "Risk explainer": c["risk_explainer"]
    } for c in st.session_state["policy_cards"]])

    # Simple filters
    risk_filter = st.multiselect("Filter by risk", ["High", "Medium", "Low"], default=["High","Medium","Low"])
    view_df = df[df["Risk"].isin(risk_filter)].reset_index(drop=True)

    st.dataframe(view_df, use_container_width=True, height=380)

    # Detail viewer
    st.markdown("#### Policy Details")
    idx = st.number_input("Select row # to view details", min_value=0, max_value=len(view_df)-1, value=0, step=1)
    if len(view_df) > 0:
        row = view_df.iloc[int(idx)]
        st.markdown(f"**Policy:** {row['Policy']}")
        st.markdown(f"**Risk:** {row['Risk']}")
        st.markdown("**Summary:**")
        st.write(row["Summary (plain-English)"])
        st.markdown("**Checklist:**")
        st.write(row["Checklist (actions)"])

st.divider()

# ---- Digest / Export (stubs for Day 5) ----
st.markdown("### 3) Export & Alerts (Demo stubs)")
col1, col2, col3 = st.columns(3)
with col1:
    st.button("Export Audit Pack (PDF) — Coming soon")
with col2:
    st.button("Email Weekly Digest — Coming soon")
with col3:
    st.button("Assign in MS Teams — Coming soon")

st.caption("© 2025 PolicySimplify AI — Demo build")
