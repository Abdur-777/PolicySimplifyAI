# app.py — PolicySimplify AI (Day 6, no passcode, new query_params API)

from __future__ import annotations
import os
import sys
import json
import time
import logging
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
from redact import scrub
from ocr_utils import pdf_bytes_to_text_via_ocr

# ---------- Setup ----------

load_dotenv()

logging.basicConfig(
    stream=sys.stdout,
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
log = logging.getLogger("policysimplify")

APP_NAME        = os.getenv("APP_NAME", "PolicySimplify AI")
APP_TAGLINE     = os.getenv("APP_TAGLINE", "Turn any government policy into an instant compliance checklist.")
VECTOR_DB_NAME  = os.getenv("VECTOR_DB_NAME", "demo_store")
COUNCIL_NAME    = os.getenv("COUNCIL_NAME", "Wyndham City Council")
TEXT_CAP        = int(os.getenv("TEXT_CAP", "120000"))
RETENTION_DAYS  = int(os.getenv("RETENTION_DAYS", "14"))
ALLOW_DB_EXPORT = os.getenv("ALLOW_DB_EXPORT", "false").lower() == "true"
ENABLE_OCR      = os.getenv("ENABLE_OCR", "false").lower() == "true"

st.set_page_config(page_title=APP_NAME, page_icon="✅", layout="wide")

# Healthcheck (new Streamlit API)
params = st.query_params
if params.get("health") in ("1", ["1"]):
    st.write("ok")
    st.stop()

# Purge old rows on startup (data retention)
try:
    removed = purge_older_than(RETENTION_DAYS)
    if removed:
        log.info("Purged old rows: %s", removed)
except Exception as e:
    removed = 0
    log.warning("Retention purge failed: %s", e)

# Session state bootstrapping
if "store" not in st.session_state:
    st.session_state["store"] = SimpleFAISS.load(VECTOR_DB_NAME)
if "policy_cards" not in st.session_state:
    st.session_state["policy_cards"] = []
if "loaded_persisted" not in st.session_state:
    persisted = load_cards(limit=500)
    if persisted:
        st.session_state["policy_cards"].extend(persisted)
        log.info("Loaded %s persisted cards", len(persisted))
    st.session_state["loaded_persisted"] = True

# ---------- Header ----------

c1, c2 = st.columns([0.7, 0.3])
with c1:
    st.markdown(f"## {APP_NAME}")
    st.markdown(f"_{APP_TAGLINE}_")
with c2:
    st.markdown(
        f"<div style='text-align:right;'>🏛️ {COUNCIL_NAME}<br/>🔒 No sign-up • Demo-ready</div>",
        unsafe_allow_html=True,
    )

st.info("Your uploads are processed for this demo and are **not** used to train models.")
st.divider()

# ---------- Sidebar (ingest, tools, diagnostics) ----------

with st.sidebar:
    st.markdown("### Ingest a policy")

    uploaded = st.file_uploader("Upload PDF", type=["pdf"])
    if uploaded is not None and st.button("Process uploaded PDF"):
        try:
            content = uploaded.read()
            source_name = uploaded.name
            st.session_state["_ingest_uploaded"] = (source_name, content)
            log_event("upload", source_name)
            log.info("Queued upload: %s", source_name)
        except Exception as e:
            st.error(f"Could not read uploaded file: {e}")
            log.exception("Upload read failed")

    url = st.text_input("Or fetch from URL (PDF)", placeholder="https://example.gov.au/policy.pdf")
    if st.button("Fetch & process URL"):
        if not url.strip():
            st.warning("Please paste a valid URL to a PDF.")
        else:
            try:
                with st.spinner("Downloading PDF..."):
                    r = requests.get(url, timeout=20)
                    r.raise_for_status()
                st.session_state["_ingest_url"] = (
                    os.path.basename(url) or "Policy_From_URL.pdf",
                    r.content,
                )
                st.success("Downloaded. Processing…")
                log_event("url", url)
                log.info("Downloaded URL: %s", url)
            except Exception as e:
                st.error(f"Failed to fetch PDF: {e}")
                log.exception("URL fetch failed")

    st.markdown("---")
    if st.button("Use example policy"):
        st.session_state["_ingest_example"] = True
        log_event("example", "Example_Waste_Services_Policy.txt")
        log.info("Example queued")

    st.markdown("---")
    if st.button("🗑️ Clear session & database"):
        st.session_state["policy_cards"] = []
        st.session_state["store"] = SimpleFAISS.load(VECTOR_DB_NAME)
        try:
            clear_all()
        except Exception as e:
            st.warning(f"DB clear error: {e}")
            log.exception("DB clear failed")
        st.success("Cleared.")
        log_event("admin", "clear_all")
        log.info("Cleared session+DB")

    st.markdown("---")
    st.caption("Diagnostics")
    backend = "FAISS" if getattr(st.session_state["store"], "index", None) is not None else "NumPy"
    st.write(f"Vector backend: **{backend}**")
    st.write(f"Indexed docs: **{len(getattr(st.session_state['store'], 'docs', []))}**")
    st.write(f"Retention (days): **{RETENTION_DAYS}** | Purged: **{removed}**")

    st.markdown("---")
    st.caption("Recent activity")
    try:
        for e in recent_events(5):
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(e["ts"]))
            st.write(f"- {ts}: {e['kind']} — {e['detail']}")
    except Exception:
        st.write("- (no events yet)")

    st.markdown("---")
    st.caption("Admin")
    if ALLOW_DB_EXPORT:
        try:
            with open(os.getenv("DB_PATH", "./policy.db"), "rb") as f:
                st.download_button(
                    "Download SQLite (policy.db)",
                    data=f.read(),
                    file_name="policy.db",
                    mime="application/octet-stream",
                    use_container_width=True,
                )
        except Exception as e:
            st.error(f"Export failed: {e}")

# ---------- Example policy text ----------

example_text = """Policy Directive: Waste Services Bin Contamination

1. Households must not place hazardous items (batteries, chemicals) in general waste.
2. Repeated contamination may lead to fines or service suspension.
3. Education notices must be delivered within 30 days after first offence.
4. Annual reporting to Council on contamination rates is required by 30 September each year.

Penalties apply for non-compliance. Council teams must document outreach and enforcement actions.
"""

# ---------- Core processing ----------

def process_policy(source_name: str, *, file_bytes: bytes | None = None, raw_text: str | None = None):
    log.info("Processing policy: %s", source_name)
    with st.spinner("Reading policy..."):
        if file_bytes:
            text = extract_text_from_pdf_bytes(file_bytes) or ""
            if not text.strip() and ENABLE_OCR:
                text = pdf_bytes_to_text_via_ocr(file_bytes)
        else:
            text = raw_text or ""

        text = (text or "").strip()
        if not text:
            st.warning("No text found (maybe a scanned PDF without OCR).")
            log.warning("Empty text after extraction")
            return

        if len(text) > TEXT_CAP:
            log.info("Truncate text from %s to %s chars", len(text), TEXT_CAP)
            text = text[:TEXT_CAP]

        # Redact PII before embedding / LLM calls
        text = scrub(text)

    # Chunk + docify
    chunks = chunk_text(text)
    docs = make_docs(chunks, source_name)

    with st.spinner("Indexing..."):
        st.session_state["store"].add(docs)
        st.session_state["store"].save(VECTOR_DB_NAME)
        log.info("Indexed %s chunks", len(docs))

    with st.spinner("Generating summary, checklist & risk..."):
        snippet = docs[len(docs)//2]["text"] if docs else text[:3000]
        try:
            summary = generate_summary(snippet)
            checklist = generate_checklist(snippet, summary)
            risk_note = assess_risk(snippet, summary)
        except Exception as e:
            st.error(f"LLM error: {e}")
            log.exception("LLM call failed")
            return

        card = compose_policy_card(source_name, summary, checklist, risk_note)
        card["created_at"] = int(time.time())
        card["structured_tasks"] = extract_structured_tasks(card["checklist"])

        st.session_state["policy_cards"].append(card)
        try:
            save_card(card)
        except Exception as e:
            st.warning(f"DB persist error: {e}")

# Trigger queued actions from sidebar
if "_ingest_uploaded" in st.session_state:
    n, b = st.session_state.pop("_ingest_uploaded")
    process_policy(source_name=n, file_bytes=b)

if "_ingest_url" in st.session_state:
    n, b = st.session_state.pop("_ingest_url")
    process_policy(source_name=n, file_bytes=b)

if st.session_state.pop("_ingest_example", False):
    process_policy(source_name="Example_Waste_Services_Policy.txt", raw_text=example_text)

# ---------- Risk overview ----------

def _count_bullets(text: str) -> int:
    cnt = 0
    for ln in (text or "").splitlines():
        s = ln.strip()
        if not s:
            continue
        if s.startswith(("-", "*", "•")):
            cnt += 1
        elif (len(s) > 1 and s[0].isdigit() and s[1] == "."):
            cnt += 1
    return cnt

def _risk_counts(cards: list[dict]) -> tuple[int, int, int, int]:
    total_obl = sum(_count_bullets(c.get("checklist", "")) for c in cards)
    high = sum(1 for c in cards if c.get("risk") == "High")
    med  = sum(1 for c in cards if c.get("risk") == "Medium")
    low  = sum(1 for c in cards if c.get("risk") == "Low")
    return total_obl, high, med, low

st.markdown("### 1) Risk overview")
if not st.session_state["policy_cards"]:
    st.info("Ingest a policy to see the risk dashboard.")
else:
    total_obl, high_c, med_c, low_c = _risk_counts(st.session_state["policy_cards"])
    a, b, c, d = st.columns(4)
    a.metric("Total Policies", len(st.session_state["policy_cards"]))
    b.metric("High Risk Policies", high_c)
    c.metric("Medium Risk Policies", med_c)
    d.metric("Low Risk Policies", low_c)
    st.caption(f"Approx. obligations extracted: **{total_obl}**")

st.divider()

# ---------- Table & details ----------

st.markdown("### 2) Active compliance items")
if not st.session_state["policy_cards"]:
    st.info("Upload a PDF, paste a policy URL, or use the example.")
else:
    df = pd.DataFrame([{
        "Policy": c["policy"],
        "Summary (plain-English)": c["summary"],
        "Checklist (actions)": c["checklist"],
        "Risk": c["risk"],
        "Risk explainer": c["risk_explainer"],
        "Processed": time.strftime("%Y-%m-%d %H:%M", time.localtime(c.get("created_at", 0))) if c.get("created_at") else "",
    } for c in st.session_state["policy_cards"]])

    order = {"High": 0, "Medium": 1, "Low": 2}
    df["_o"] = df["Risk"].map(order).fillna(3)
    df = df.sort_values(by=["_o", "Processed", "Policy"], ascending=[True, False, True]).drop(columns=["_o"])

    colA, colB = st.columns([0.7, 0.3])
    with colA:
        risk_filter = st.multiselect("Filter by risk", ["High", "Medium", "Low"], default=["High", "Medium", "Low"])
    with colB:
        high_only = st.checkbox("Show only High risk", value=False)

    view_df = df[df["Risk"].eq("High")] if high_only else df[df["Risk"].isin(risk_filter)]
    view_df = view_df.reset_index(drop=True)

    st.dataframe(view_df, use_container_width=True, height=420)

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

    st.markdown("#### Structured view (Action / Owner / Due)")
    if st.toggle("Show structured tasks", value=False):
        rows = []
        cmap = {c["policy"]: c for c in st.session_state["policy_cards"]}
        for rec in view_df.to_dict(orient="records"):
            c = cmap.get(rec["Policy"])
            if not c:
                continue
            for t in c.get("structured_tasks", []):
                rows.append({
                    "Policy": rec["Policy"],
                    "Action": t.get("action", ""),
                    "Owner": t.get("owner", ""),
                    "Due": t.get("due", "")
                })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True)
        else:
            st.info("No structured tasks yet for current selection.")

    # Export
    st.markdown("#### Export")
    st.download_button(
        "Download table as CSV",
        data=view_df.to_csv(index=False).encode("utf-8"),
        file_name="policy_compliance_items.csv",
        mime="text/csv",
        use_container_width=True,
    )
    st.download_button(
        "Download table as JSON",
        data=json.dumps(view_df.to_dict(orient="records"), indent=2).encode("utf-8"),
        file_name="policy_compliance_items.json",
        mime="application/json",
        use_container_width=True,
    )

    pdf_bytes = build_audit_pack(COUNCIL_NAME, st.session_state["policy_cards"])
    st.download_button(
        "Download Audit Pack (PDF)",
        data=pdf_bytes,
        file_name="PolicySimplify_Audit_Pack.pdf",
        mime="application/pdf",
        use_container_width=True,
    )

    with st.expander("Email this Audit Pack"):
        to = st.text_input("Recipient email", key="email_to")
        if st.button("Send Audit Pack", key="send_email_btn"):
            try:
                from email_utils import send_email_with_pdf
                send_email_with_pdf(
                    to_addr=to,
                    subject=f"[{COUNCIL_NAME}] PolicySimplify Audit Pack",
                    body="Attached: Audit Pack generated by PolicySimplify AI.",
                    pdf_bytes=pdf_bytes,
                    filename="PolicySimplify_Audit_Pack.pdf",
                )
                st.success("Sent!")
                log_event("email", f"to={to}")
                log.info("Audit Pack emailed to %s", to)
            except Exception as e:
                st.error(f"Email failed: {e}")
                log.exception("Email send failed")

st.divider()

# ---------- Q&A ----------

st.markdown("### 3) Ask the policy")
q = st.text_input("Ask a question about your uploaded policies")
if st.button("Get answer") and q.strip():
    hits = st.session_state["store"].search(q, k=4)
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
            log.info("Q&A answered: %s", q)
        except Exception:
            pass

st.caption("© 2025 PolicySimplify AI — Demo build")
