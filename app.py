# app.py — PolicySimplify AI (Day 2)
# ---------------------------------------------------------
# - Sidebar ingest (upload/URL/example)
# - Tuned AI outputs (Day 2 prompts)
# - Risk KPIs (High/Medium/Low), triage toggle
# - Table + details + CSV/JSON export
# - Healthcheck (?health=1) for Render
# ---------------------------------------------------------

from __future__ import annotations

import os
import json
import requests
import pandas as pd
import streamlit as st
from dotenv import load_dotenv

from pdf_loader import extract_text_from_pdf_bytes, chunk_text, make_docs
from vectorstore import SimpleFAISS
from checklist_generator import (
    generate_summary,
    generate_checklist,
    assess_risk,
    compose_policy_card,
)

# --------------------- Setup ---------------------
load_dotenv()
APP_NAME = os.getenv("APP_NAME", "PolicySimplify AI")
APP_TAGLINE = os.getenv("APP_TAGLINE", "Turn any government policy into an instant compliance checklist.")
VECTOR_DB_NAME = os.getenv("VECTOR_DB_NAME", "demo_store")
COUNCIL_NAME = os.getenv("COUNCIL_NAME", "Wyndham City Council")
TEXT_CAP = int(os.getenv("TEXT_CAP", "120000"))

st.set_page_config(page_title=APP_NAME, page_icon="✅", layout="wide")

# Healthcheck
if st.experimental_get_query_params().get("health") == ["1"]:
    st.write("ok")
    st.stop()

# --------------------- Session ---------------------
if "store" not in st.session_state:
    st.session_state["store"] = SimpleFAISS.load(VECTOR_DB_NAME)
if "policy_cards" not in st.session_state:
    st.session_state["policy_cards"] = []

# --------------------- Header ---------------------
hdr_left, hdr_right = st.columns([0.75, 0.25])
with hdr_left:
    st.markdown(f"## {APP_NAME}")
    st.markdown(f"_{APP_TAGLINE}_")
with hdr_right:
    st.markdown(f"<div style='text-align:right;'>🏛️ {COUNCIL_NAME}<br/>🔒 No sign-up • Demo-ready</div>", unsafe_allow_html=True)
st.divider()

# --------------------- Sidebar Ingest ---------------------
with st.sidebar:
    st.markdown("### Ingest a policy")
    uploaded = st.file_uploader("Upload PDF", type=["pdf"])

    url = st.text_input("Or fetch from URL (PDF)", placeholder="https://example.gov.au/policy.pdf")
    if st.button("Fetch & process URL"):
        if not url.strip():
            st.warning("Please paste a valid URL to a PDF.")
        else:
            try:
                with st.spinner("Downloading PDF..."):
                    r = requests.get(url, timeout=20)
                    r.raise_for_status()
                st.session_state["_pending_url_pdf"] = (os.path.basename(url) or "Policy_From_URL.pdf", r.content)
            except Exception as e:
                st.error(f"Failed to fetch PDF: {e}")

    st.markdown("---")
    if st.button("Use example policy"):
        st.session_state["_pending_example"] = True

    st.markdown("---")
    if st.button("🗑️ Clear session"):
        st.session_state["policy_cards"] = []
        st.session_state["store"] = SimpleFAISS.load(VECTOR_DB_NAME)
        st.success("Cleared session for this demo.")

    # Diagnostics
    st.markdown("---")
    st.caption("Diagnostics")
    backend = "FAISS" if hasattr(st.session_state["store"], "index") and st.session_state["store"].index is not None else "NumPy"
    st.write(f"Vector backend: **{backend}**")
    st.write(f"Indexed docs: **{len(getattr(st.session_state['store'], 'docs', []))}**")

# --------------------- Example Text ---------------------
example_text = """Policy Directive: Waste Services Bin Contamination

1. Households must not place hazardous items (batteries, chemicals) in general waste.
2. Repeated contamination may lead to fines or service suspension.
3. Education notices must be delivered within 30 days after first offence.
4. Annual reporting to Council on contamination rates is required by 30 September each year.

Penalties apply for non-compliance. Council teams must document outreach and enforcement actions.
"""

# --------------------- Core Processor ---------------------
def process_policy(source_name: str, *, file_bytes: bytes | None = None, raw_text: str | None = None):
    # 1) Extract text
    with st.spinner("Reading policy..."):
        if file_bytes:
            text = extract_text_from_pdf_bytes(file_bytes)
        else:
            text = raw_text or ""
        text = (text or "").strip()
        if not text:
            st.warning("No text found (scanned PDF without OCR?).")
            return
        if len(text) > TEXT_CAP:
            text = text[:TEXT_CAP]

    # 2) Chunk & docs
    chunks = chunk_text(text)
    docs = make_docs(chunks, source_name)

    # 3) Index
    with st.spinner("Indexing..."):
        st.session_state["store"].add(docs)
        st.session_state["store"].save(VECTOR_DB_NAME)

    # 4) AI outputs (middle chunk for speed)
    with st.spinner("Generating summary, checklist & risk..."):
        snippet = docs[len(docs)//2]["text"] if docs else text
        try:
            summary = generate_summary(snippet)
            checklist = generate_checklist(snippet, summary)
            risk_note = assess_risk(snippet, summary)
        except Exception as e:
            st.error(f"OpenAI error: {e}")
            return
        card = compose_policy_card(source_name, summary, checklist, risk_note)
        st.session_state["policy_cards"].append(card)

# Trigger processing from sidebar actions
if uploaded is not None and st.sidebar.button("Process uploaded PDF"):
    process_policy(source_name=uploaded.name, file_bytes=uploaded.read())

if st.session_state.pop("_pending_url_pdf", None):
    name, content = st.session_state["_pending_url_pdf"]
    process_policy(source_name=name, file_bytes=content)

if st.session_state.pop("_pending_example", False):
    process_policy(source_name="Example_Waste_Services_Policy.txt", raw_text=example_text)

# --------------------- Risk KPIs ---------------------
def _count_bullets(text: str) -> int:
    # Heuristic: lines starting with '-', '*', '•', or numbered '1.' etc.
    cnt = 0
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith(("-", "*", "•")):
            cnt += 1
        elif s[:2].isdigit() and (s[2:3] == "." or s[1:2] == "."):
            cnt += 1
    return cnt

def _risk_counts(cards: list[dict]) -> tuple[int,int,int,int]:
    total_obligations = sum(_count_bullets(c.get("checklist", "")) for c in cards)
    high = sum(1 for c in cards if c.get("risk") == "High")
    med = sum(1 for c in cards if c.get("risk") == "Medium")
    low = sum(1 for c in cards if c.get("risk") == "Low")
    return total_obligations, high, med, low

st.markdown("### 1) Risk overview")
if not st.session_state["policy_cards"]:
    st.info("Ingest a policy to see the risk dashboard.")
else:
    total_obl, high_c, med_c, low_c = _risk_counts(st.session_state["policy_cards"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Policies", len(st.session_state["policy_cards"]))
    m2.metric("High Risk Policies", high_c)
    m3.metric("Medium Risk Policies", med_c)
    m4.metric("Low Risk Policies", low_c)
    st.caption(f"Approx. obligations extracted: **{total_obl}**")

st.divider()

# --------------------- Table & Details ---------------------
st.markdown("### 2) Active compliance items")

if not st.session_state["policy_cards"]:
    st.info("Upload a PDF, paste a policy URL, or use the example.")
else:
    # Build DataFrame
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

    # Sort by risk (High > Medium > Low)
    risk_order = {"High": 0, "Medium": 1, "Low": 2}
    df["_risk_order"] = df["Risk"].map(risk_order).fillna(3)
    df = df.sort_values(by=["_risk_order", "Policy"]).drop(columns=["_risk_order"])

    # Filters
    colA, colB = st.columns([0.7, 0.3])
    with colA:
        risk_filter = st.multiselect("Filter by risk", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    with colB:
        high_only = st.checkbox("Show only High risk", value=False)

    if high_only:
        view_df = df[df["Risk"] == "High"].reset_index(drop=True)
    else:
        view_df = df[df["Risk"].isin(risk_filter)].reset_index(drop=True)

    st.dataframe(view_df, use_container_width=True, height=380)

    # Detail viewer
    st.markdown("#### Policy details")
    if len(view_df) > 0:
        idx = st.number_input("Select row #", min_value=0, max_value=len(view_df) - 1, value=0, step=1)
        row = view_df.iloc[int(idx)]
        st.markdown(f"**Policy:** {row['Policy']}")
        st.markdown(f"**Risk:** {row['Risk']}")
        st.markdown("**Summary:**")
        st.write(row["Summary (plain-English)"])
        st.markdown("**Checklist:**")
        st.write(row["Checklist (actions)"])
        st.markdown("**Risk explainer:**")
        st.write(row["Risk explainer"])

    # Exports
    st.markdown("#### Export")
    csv_bytes = view_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download table as CSV", data=csv_bytes, file_name="policy_compliance_items.csv", mime="text/csv", use_container_width=True)

    json_bytes = json.dumps(view_df.to_dict(orient="records"), indent=2).encode("utf-8")
    st.download_button("Download table as JSON", data=json_bytes, file_name="policy_compliance_items.json", mime="application/json", use_container_width=True)

st.divider()

# --------------------- Future Hooks ---------------------
st.markdown("### 3) Export & alerts (demo stubs)")
c1, c2, c3 = st.columns(3)
with c1:
    st.button("Export Audit Pack (PDF) — Coming soon")
with c2:
    st.button("Email Weekly Digest — Coming soon")
with c3:
    st.button("Assign in MS Teams — Coming soon")

st.caption("© 2025 PolicySimplify AI — Demo build")
