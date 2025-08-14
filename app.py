# app.py — PolicySimplify AI (Day 4)
# ---------------------------------------------------------
# - Ingest: upload/pdf URL/example (no signup)
# - AI: Summary / Checklist / Risk (tuned), Retrieval Q&A
# - Vector store: FAISS or NumPy fallback (vectorstore.py)
# - Persistence: SQLite (cards + events) with retention
# - Exports: CSV/JSON + Audit Pack PDF
# - Healthcheck: add ?health=1
# ---------------------------------------------------------

from __future__ import annotations

import os
import json
import time
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
    qa_answer,
)
from storage import save_card, load_cards, clear_all, log_event, recent_events, purge_older_than
from export_audit_pack import build_audit_pack
from utils import extract_structured_tasks

# --------------------- Setup & Config ---------------------
load_dotenv()

APP_NAME = os.getenv("APP_NAME", "PolicySimplify AI")
APP_TAGLINE = os.getenv("APP_TAGLINE", "Turn any government policy into an instant compliance checklist.")
VECTOR_DB_NAME = os.getenv("VECTOR_DB_NAME", "demo_store")
COUNCIL_NAME = os.getenv("COUNCIL_NAME", "Wyndham City Council")
TEXT_CAP = int(os.getenv("TEXT_CAP", "120000"))  # safety cap for very large PDFs
RETENTION_DAYS = int(os.getenv("RETENTION_DAYS", "14"))

st.set_page_config(page_title=APP_NAME, page_icon="✅", layout="wide")

# Healthcheck for monitors: https://your-app-url/?health=1
if st.experimental_get_query_params().get("health") == ["1"]:
    st.write("ok")
    st.stop()

# Purge old data on startup (light governance)
try:
    removed = purge_older_than(RETENTION_DAYS)
except Exception:
    removed = 0

# --------------------- Session State ----------------------
if "store" not in st.session_state:
    st.session_state["store"] = SimpleFAISS.load(VECTOR_DB_NAME)
if "policy_cards" not in st.session_state:
    st.session_state["policy_cards"] = []
if "loaded_persisted" not in st.session_state:
    persisted = load_cards(limit=500)
    if persisted:
        st.session_state["policy_cards"].extend(persisted)
    st.session_state["loaded_persisted"] = True

# --------------------- Header / Branding ------------------
hdr_left, hdr_right = st.columns([0.70, 0.30])
with hdr_left:
    st.markdown(f"## {APP_NAME}")
    st.markdown(f"_{APP_TAGLINE}_")
with hdr_right:
    st.markdown(
        f"<div style='text-align:right;'>🏛️ {COUNCIL_NAME}<br/>🔒 No sign-up • Demo-ready</div>",
        unsafe_allow_html=True,
    )
st.info("Your uploads are processed for this demo and are **not** used to train models.")
st.divider()

# --------------------- Sidebar (Ingest & Admin) -----------
with st.sidebar:
    st.markdown("### Ingest a policy")

    # Upload
    uploaded = st.file_uploader("Upload PDF", type=["pdf"])
    if uploaded is not None:
        if st.button("Process uploaded PDF"):
            try:
                content = uploaded.read()
                source_name = uploaded.name
                st.session_state["_ingest_uploaded"] = (source_name, content)
                log_event("upload", source_name)
            except Exception as e:
                st.error(f"Could not read uploaded file: {e}")

    # URL fetch
    url = st.text_input("Or fetch from URL (PDF)", placeholder="https://example.gov.au/policy.pdf")
    if st.button("Fetch & process URL"):
        if not url.strip():
            st.warning("Please paste a valid URL to a PDF.")
        else:
            try:
                with st.spinner("Downloading PDF..."):
                    r = requests.get(url, timeout=20)
                    r.raise_for_status()
                st.session_state["_ingest_url"] = (os.path.basename(url) or "Policy_From_URL.pdf", r.content)
                st.success("Downloaded. Processing…")
                log_event("url", url)
            except Exception as e:
                st.error(f"Failed to fetch PDF: {e}")

    st.markdown("---")
    if st.button("Use example policy"):
        st.session_state["_ingest_example"] = True
        log_event("example", "Example_Waste_Services_Policy.txt")

    st.markdown("---")
    if st.button("🗑️ Clear session & database"):
        st.session_state["policy_cards"] = []
        st.session_state["store"] = SimpleFAISS.load(VECTOR_DB_NAME)
        try:
            clear_all()
        except Exception as e:
            st.warning(f"DB clear error: {e}")
        st.success("Cleared session and database.")
        log_event("admin", "clear_all")

    st.markdown("---")
    st.caption("Diagnostics")
    backend = "FAISS" if hasattr(st.session_state["store"], "index") and st.session_state["store"].index is not None else "NumPy"
    st.write(f"Vector backend: **{backend}**")
    st.write(f"Indexed docs: **{len(getattr(st.session_state['store'], 'docs', []))}**")
    st.write(f"Retention (days): **{RETENTION_DAYS}**  | Purged: **{removed}**")

    st.markdown("---")
    st.caption("Recent activity")
    try:
        events = recent_events(5)
        for e in events:
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(e["ts"]))
            st.write(f"- {ts}: {e['kind']} — {e['detail']}")
    except Exception:
        st.write("- (no events yet)")

# --------------------- Example Text -----------------------
example_text = """Policy Directive: Waste Services Bin Contamination

1. Households must not place hazardous items (batteries, chemicals) in general waste.
2. Repeated contamination may lead to fines or service suspension.
3. Education notices must be delivered within 30 days after first offence.
4. Annual reporting to Council on contamination rates is required by 30 September each year.

Penalties apply for non-compliance. Council teams must document outreach and enforcement actions.
"""

# --------------------- Core Processor (FULL) --------------
def process_policy(source_name: str, *, file_bytes: bytes | None = None, raw_text: str | None = None):
    """
    Reads, indexes, and generates summary/checklist/risk for a policy.
    Appends a policy card dict into session state and persists to DB.
    """
    # 1) Extract text
    with st.spinner("Reading policy..."):
        if file_bytes:
            text = extract_text_from_pdf_bytes(file_bytes)
        else:
            text = raw_text or ""
        text = (text or "").strip()
        if not text:
            st.warning("No text found (this may be a scanned PDF without OCR).")
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

        # Compose card
        card = compose_policy_card(source_name, summary, checklist, risk_note)
        card["created_at"] = int(time.time())
        # Structured tasks (Action / Owner / Due)
        card["structured_tasks"] = extract_structured_tasks(card["checklist"])

        # Save to memory and DB
        st.session_state["policy_cards"].append(card)
        try:
            save_card(card)
        except Exception as e:
            st.warning(f"Could not persist to DB: {e}")

# Trigger processing for queued ingest actions
if "_ingest_uploaded" in st.session_state:
    name, bytes_ = st.session_state.pop("_ingest_uploaded")
    process_policy(source_name=name, file_bytes=bytes_)

if "_ingest_url" in st.session_state:
    name, bytes_ = st.session_state.pop("_ingest_url")
    process_policy(source_name=name, file_bytes=bytes_)

if st.session_state.pop("_ingest_example", False):
    process_policy(source_name="Example_Waste_Services_Policy.txt", raw_text=example_text)

# --------------------- Risk KPIs --------------------------
def _count_bullets(text: str) -> int:
    cnt = 0
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith(("-", "*", "•")):
            cnt += 1
        elif (len(s) > 1 and s[0].isdigit() and s[1] == ".") or (len(s) > 2 and s[:2].isdigit() and s[2] == "."):
            cnt += 1
    return cnt

def _risk_counts(cards: list[dict]) -> tuple[int, int, int, int]:
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

# --------------------- Table & Details --------------------
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
                "Processed": time.strftime("%Y-%m-%d %H:%M", time.localtime(c.get("created_at", 0))) if c.get("created_at") else "",
            }
            for c in st.session_state["policy_cards"]
        ]
    )

    # Sort by risk (High > Medium > Low), then latest
    risk_order = {"High": 0, "Medium": 1, "Low": 2}
    df["_risk_order"] = df["Risk"].map(risk_order).fillna(3)
    df = df.sort_values(by=["_risk_order", "Processed", "Policy"], ascending=[True, False, True]).drop(columns=["_risk_order"])

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

    st.dataframe(view_df, use_container_width=True, height=420)

    # Detail viewer
    st.markdown("#### Policy details")
    if len(view_df) > 0:
        idx = st.number_input("Select row #", min_value=0, max_value=len(view_df) - 1, value=0, step=1)
        row = view_df.iloc[int(idx)]
        st.markdown(f"**Policy:** {row['Policy']}")
        st.markdown(f"**Risk:** {row['Risk']}")
        st.markdown(f"**Processed:** {row['Processed']}")
        st.markdown("**Summary:**")
        st.write(row["Summary (plain-English)"])
        st.markdown("**Checklist:**")
        st.write(row["Checklist (actions)"])
        st.markdown("**Risk explainer:**")
        st.write(row["Risk explainer"])

    # Structured view across selected rows
    st.markdown("#### Structured view (Action / Owner / Due)")
    if st.toggle("Show structured tasks", value=False):
        rows = []
        # Map policy -> card to access structured_tasks
        card_map = {c["policy"]: c for c in st.session_state["policy_cards"]}
        for rec in view_df.to_dict(orient="records"):
            c = card_map.get(rec["Policy"])
            if not c:
                continue
            for t in c.get("structured_tasks", []):
                rows.append({"Policy": rec["Policy"], "Action": t.get("action",""), "Owner": t.get("owner",""), "Due": t.get("due","")})
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("No structured tasks yet for current selection.")

    # Exports
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

    # Audit Pack PDF (all cards so auditors get full context)
    pdf_bytes = build_audit_pack(COUNCIL_NAME, st.session_state["policy_cards"])
    st.download_button(
        "Download Audit Pack (PDF)",
        data=pdf_bytes,
        file_name="PolicySimplify_Audit_Pack.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

st.divider()

# --------------------- Retrieval Q&A ----------------------
st.markdown("### 3) Ask the policy")
q = st.text_input("Ask a question about your uploaded policies")
if st.button("Get answer") and q.strip():
    hits = st.session_state["store"].search(q, k=4)  # list[(score, doc)]
    snippets = [doc["text"] for _, doc in hits]
    if not snippets:
        st.info("No context found yet. Upload a policy first.")
    else:
        ans = qa_answer(snippets, q)
        st.markdown("**Answer:**")
        st.write(ans)
        with st.expander("Sources"):
            for i, (score, doc) in enumerate(hits, 1):
                src = doc.get("metadata", {}).get("source", "Unknown")
                st.markdown(f"**{i}. {src}** (score {score:.2f})")
                st.code(doc["text"][:700])
        try:
            log_event("qa", q)
        except Exception:
            pass
