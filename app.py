# app.py — Week 2 upgrades: multi-council, plans, admin, privacy

from __future__ import annotations
import os, sys, json, time, logging, requests, pandas as pd, streamlit as st
from dotenv import load_dotenv

from tenant import resolve_council
from brand import get_brand_for_key, inject_theme
from pdf_loader import extract_text_from_pdf_bytes, chunk_text, make_docs
from vectorstore import SimpleFAISS
from checklist_generator import generate_summary, generate_checklist, assess_risk, compose_policy_card, qa_answer
from storage import save_card, load_cards, clear_all, purge_older_than, log_event, recent_events, delete_all_for_tenant
from export_audit_pack import build_audit_pack
from utils import extract_structured_tasks
from redact import scrub
from ocr_utils import pdf_bytes_to_text_via_ocr

load_dotenv()
logging.basicConfig(stream=sys.stdout, level=os.getenv("LOG_LEVEL","INFO"),
                    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("policysimplify")

APP_NAME   = os.getenv("APP_NAME", "PolicySimplify AI")
APP_TAGLINE= os.getenv("APP_TAGLINE", "Turn any government policy into an instant compliance checklist.")
VECTOR_DB  = os.getenv("VECTOR_DB_NAME", "demo_store")
TEXT_CAP   = int(os.getenv("TEXT_CAP","120000"))
ENABLE_OCR = os.getenv("ENABLE_OCR","false").lower()=="true"
ALLOW_DB_EXPORT = os.getenv("ALLOW_DB_EXPORT","false").lower()=="true"
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN","")  # set for admin panel access

st.set_page_config(page_title=APP_NAME, page_icon="✅", layout="wide")

# Healthcheck (new API)
if st.query_params.get("health") in ("1", ["1"]):
    st.write("ok"); st.stop()

# Resolve tenant (council) + theme
TENANT = resolve_council()  # {key,name,state,plan,retention_days,primary,secondary,accent,logo}
BRAND_CFG, BRAND_LOGO = get_brand_for_key(TENANT["key"], TENANT["name"], TENANT["primary"], TENANT["secondary"], TENANT["accent"])
inject_theme(BRAND_CFG)

# Data retention per tenant
try:
    removed = purge_older_than(TENANT["key"], TENANT["retention_days"])
except Exception as e:
    removed = 0
    log.warning("Retention purge failed: %s", e)

# Session boot
if "store" not in st.session_state:
    st.session_state["store"] = SimpleFAISS.load(VECTOR_DB)
if "policy_cards" not in st.session_state:
    # Load only this tenant's cards
    st.session_state["policy_cards"] = load_cards(tenant=TENANT["key"], limit=500)

# --- Header ---
left, right = st.columns([0.8, 0.2])
with left:
    st.markdown(f"## {APP_NAME}")
    st.markdown(f"_{APP_TAGLINE}_")
    st.caption(f"Tenant: **{TENANT['name']}** ({TENANT['state']}) • Plan: **{TENANT['plan'].title()}** • Retention: **{TENANT['retention_days']} days**")
with right:
    try:
        st.image(BRAND_LOGO, use_column_width=True, caption=BRAND_CFG.get("logo_alt", TENANT["name"]))
    except Exception:
        st.write("")

st.info("We process your uploads to generate summaries/checklists. Data is not used to train models. Delete-my-data tools are available below.")
st.divider()

# --- Sidebar: ingest, diagnostics, admin ---
with st.sidebar:
    st.markdown("### Ingest a policy")
    uploaded = st.file_uploader("Upload PDF", type=["pdf"])
    if uploaded and st.button("Process uploaded PDF", use_container_width=True):
        st.session_state["_ingest_uploaded"] = (uploaded.name, uploaded.read())

    url = st.text_input("Or fetch from URL (PDF)", placeholder="https://example.gov.au/policy.pdf")
    if st.button("Fetch & process URL", use_container_width=True):
        if not url.strip():
            st.warning("Paste a valid PDF URL.")
        else:
            try:
                r = requests.get(url, timeout=20); r.raise_for_status()
                st.session_state["_ingest_url"] = (os.path.basename(url) or "Policy_From_URL.pdf", r.content)
                st.success("Downloaded. Processing…")
            except Exception as e:
                st.error(f"Fetch failed: {e}")

    st.markdown("---")
    if st.button("Use example policy", use_container_width=True):
        st.session_state["_ingest_example"] = True

    st.markdown("---")
    st.caption("Diagnostics")
    backend = "FAISS" if getattr(st.session_state["store"], "index", None) is not None else "NumPy"
    st.write(f"Council key: **{TENANT['key']}**")
    st.write(f"Vector backend: **{backend}**")
    st.write(f"Purge (last start): **{removed} rows**")

    st.markdown("---")
    st.caption("Admin (token required)")
    if "admin_ok" not in st.session_state: st.session_state["admin_ok"] = False
    if not st.session_state["admin_ok"]:
        token = st.text_input("Admin token", type="password")
        if st.button("Login as Admin"):
            if ADMIN_TOKEN and token == ADMIN_TOKEN:
                st.session_state["admin_ok"] = True
                st.success("Admin unlocked.")
            else:
                st.error("Invalid token.")
    else:
        st.success("Admin mode enabled")
        # Plan/retention editors (lightweight—persist via env or councils.json in a real admin)
        new_plan = st.selectbox("Plan", ["basic","pro","enterprise"], index=["basic","pro","enterprise"].index(TENANT["plan"]))
        new_ret  = st.number_input("Retention (days)", min_value=7, max_value=1095, value=int(TENANT["retention_days"]), step=1)
        if st.button("Apply (session)"):
            TENANT["plan"] = new_plan
            TENANT["retention_days"] = int(new_ret)
            st.success("Applied for this session.")

        st.markdown("—")
        if st.button("🗑️ Delete ALL data for this council"):
            try:
                delete_all_for_tenant(TENANT["key"])
                st.session_state["policy_cards"] = []
                st.success("All tenant data deleted.")
            except Exception as e:
                st.error(f"Delete failed: {e}")

        st.markdown("—")
        if st.button("🧹 Clear session cache"):
            st.session_state.clear()
            st.experimental_rerun()

        st.markdown("—")
        if ALLOW_DB_EXPORT:
            try:
                with open(os.getenv("DB_PATH","./policy.db"), "rb") as f:
                    st.download_button("Download SQLite (policy.db)", data=f.read(),
                                       file_name="policy.db", mime="application/octet-stream",
                                       use_container_width=True)
            except Exception as e:
                st.error(f"Export failed: {e}")

# Example policy text
example_text = """Policy Directive: Waste Services Bin Contamination

1. Households must not place hazardous items (batteries, chemicals) in general waste.
2. Repeated contamination may lead to fines or service suspension.
3. Education notices must be delivered within 30 days after first offence.
4. Annual reporting to Council on contamination rates is required by 30 September each year.

Penalties apply for non-compliance. Council teams must document outreach and enforcement actions.
"""

# Core processing
def process_policy(source_name: str, *, file_bytes: bytes | None = None, raw_text: str | None = None):
    with st.spinner("Reading policy..."):
        if file_bytes:
            text = extract_text_from_pdf_bytes(file_bytes) or ""
            if not text.strip() and ENABLE_OCR:
                text = pdf_bytes_to_text_via_ocr(file_bytes)
        else:
            text = raw_text or ""
        text = (text or "").strip()
        if not text:
            st.warning("No text found (scanned PDF without OCR?)."); return
        if len(text) > TEXT_CAP:
            text = text[:TEXT_CAP]
        text = scrub(text)  # PII guard

    chunks = chunk_text(text)
    docs = make_docs(chunks, source_name, tenant=TENANT["key"])  # tag tenant in metadata

    with st.spinner("Indexing..."):
        st.session_state["store"].add(docs)
        st.session_state["store"].save(VECTOR_DB)

    with st.spinner("Generating summary, checklist & risk..."):
        snippet = docs[len(docs)//2]["text"] if docs else text[:3000]
        summary   = generate_summary(snippet)
        checklist = generate_checklist(snippet, summary)
        risk_note = assess_risk(snippet, summary)

        card = compose_policy_card(source_name, summary, checklist, risk_note)
        card["created_at"] = int(time.time())
        card["tenant"] = TENANT["key"]
        card["structured_tasks"] = extract_structured_tasks(card["checklist"])

        st.session_state["policy_cards"].append(card)
        save_card(card)

# Handle queued actions
if "_ingest_uploaded" in st.session_state:
    n,b = st.session_state.pop("_ingest_uploaded"); process_policy(source_name=n, file_bytes=b)
if "_ingest_url" in st.session_state:
    n,b = st.session_state.pop("_ingest_url"); process_policy(source_name=n, file_bytes=b)
if st.session_state.pop("_ingest_example", False):
    process_policy(source_name="Example_Waste_Services_Policy.txt", raw_text=example_text)

# Plan gates
PLAN = TENANT["plan"]  # "basic" | "pro" | "enterprise"
def feature(enabled_in=("pro","enterprise")) -> bool:
    return PLAN in enabled_in

# Risk overview
def _count_bullets(s: str) -> int:
    c=0
    for ln in (s or "").splitlines():
        t=ln.strip()
        if not t: continue
        if t.startswith(("-", "*", "•")) or (len(t)>1 and t[0].isdigit() and t[1]=="."): c+=1
    return c

st.markdown("### 1) Risk overview")
if not st.session_state["policy_cards"]:
    st.info("Ingest a policy to see the risk dashboard.")
else:
    total_obl = sum(_count_bullets(c.get("checklist","")) for c in st.session_state["policy_cards"])
    high = sum(1 for c in st.session_state["policy_cards"] if c.get("risk")=="High")
    med  = sum(1 for c in st.session_state["policy_cards"] if c.get("risk")=="Medium")
    low  = sum(1 for c in st.session_state["policy_cards"] if c.get("risk")=="Low")
    a,b,c,d = st.columns(4)
    a.metric("Total Policies", len(st.session_state["policy_cards"]))
    b.metric("High Risk", high); c.metric("Medium Risk", med); d.metric("Low Risk", low)
    st.caption(f"Approx. obligations extracted: **{total_obl}**")

st.divider()

# Table & details
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
        "Processed": time.strftime("%Y-%m-%d %H:%M", time.localtime(c.get("created_at",0))) if c.get("created_at") else ""
    } for c in st.session_state["policy_cards"]])

    order = {"High":0,"Medium":1,"Low":2}
    if "Risk" in df.columns: df["_o"]=df["Risk"].map(order).fillna(3); df=df.sort_values(by=["_o","Processed","Policy"], ascending=[True,False,True]).drop(columns=["_o"], errors="ignore")

    colA,colB = st.columns([0.7,0.3])
    with colA:
        risk_filter = st.multiselect("Filter by risk", ["High","Medium","Low"], default=["High","Medium","Low"])
    with colB:
        high_only = st.checkbox("Show only High risk", value=False)

    view_df = df[df["Risk"].eq("High")] if high_only else df[df["Risk"].isin(risk_filter)]
    view_df = view_df.reset_index(drop=True)

    st.dataframe(view_df, use_container_width=True, height=420)

    st.markdown("#### Policy details")
    if len(view_df)>0:
        idx = st.number_input("Select row #", min_value=0, max_value=len(view_df)-1, value=0, step=1)
        row = view_df.iloc[int(idx)]
        st.markdown(f"**Policy:** {row['Policy']}")
        st.markdown(f"**Risk:** {row.get('Risk','')}")
        st.markdown(f"**Processed:** {row.get('Processed','')}")
        st.markdown("**Summary:**");   st.write(row["Summary (plain-English)"])
        st.markdown("**Checklist:**"); st.write(row["Checklist (actions)"])
        st.markdown("**Risk explainer:**"); st.write(row.get("Risk explainer",""))

    # Structured tasks (Pro+)
    st.markdown("#### Structured view (Action / Owner / Due)")
    if feature(("pro","enterprise")) and st.toggle("Show structured tasks", value=False):
        rows=[]
        cmap={c["policy"]: c for c in st.session_state["policy_cards"]}
        for rec in view_df.to_dict(orient="records"):
            c=cmap.get(rec["Policy"])
            if not c: continue
            for t in c.get("structured_tasks", []):
                rows.append({"Policy":rec["Policy"],"Action":t.get("action",""),"Owner":t.get("owner",""),"Due":t.get("due","")})
        st.dataframe(pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Policy","Action","Owner","Due"]), use_container_width=True)

    # Exports (Pro+)
    if feature(("pro","enterprise")):
        st.markdown("#### Export")
        st.download_button("Download table as CSV", data=view_df.to_csv(index=False).encode("utf-8"),
                           file_name="policy_compliance_items.csv", mime="text/csv", use_container_width=True)
        st.download_button("Download table as JSON", data=json.dumps(view_df.to_dict(orient="records"), indent=2).encode("utf-8"),
                           file_name="policy_compliance_items.json", mime="application/json", use_container_width=True)

        pdf_bytes = build_audit_pack(TENANT["name"], st.session_state["policy_cards"])
        st.download_button("Download Audit Pack (PDF)", data=pdf_bytes, file_name="PolicySimplify_Audit_Pack.pdf",
                           mime="application/pdf", use_container_width=True)

        with st.expander("Email this Audit Pack (Enterprise)"):
            if feature(("enterprise",)):
                to = st.text_input("Recipient email", key="email_to")
                if st.button("Send Audit Pack", key="send_email_btn"):
                    try:
                        from email_utils import send_email_with_pdf
                        send_email_with_pdf(to_addr=to, subject=f"[{TENANT['name']}] PolicySimplify Audit Pack",
                                            body="Attached: Audit Pack generated by PolicySimplify AI.",
                                            pdf_bytes=pdf_bytes, filename="PolicySimplify_Audit_Pack.pdf")
                        st.success("Sent!")
                    except Exception as e:
                        st.error(f"Email failed: {e}")
            else:
                st.info("Email requires Enterprise plan.")

st.divider()

# Q&A (Pro+)
st.markdown("### 3) Ask the policy")
if feature(("pro","enterprise")):
    q = st.text_input("Ask a question about your uploaded policies")
    if st.button("Get answer") and q.strip():
        hits = st.session_state["store"].search(q, k=4)
        snippets = [doc["text"] for _, doc in hits]
        if not snippets:
            st.info("No context found yet. Upload a policy first.")
        else:
            ans = qa_answer(snippets, q)
            st.markdown("**Answer:**"); st.write(ans)
            with st.expander("Sources"):
                for i,(score,doc) in enumerate(hits,1):
                    src = doc.get("metadata",{}).get("source","Unknown")
                    st.markdown(f"**{i}. {src}** (score {score:.2f})")
                    st.code(doc["text"][:700])
else:
    st.info("Upgrade to Pro to enable Q&A.")

st.markdown("---")
# Privacy / Delete-my-data (self-service)
with st.expander("Privacy & data deletion"):
    st.write("Delete all stored data (documents, summaries, vectors) for this council.")
    if st.button("Delete all my data for this council"):
        try:
            delete_all_for_tenant(TENANT["key"])
            st.session_state["policy_cards"] = []
            st.success("All data deleted for this council.")
        except Exception as e:
            st.error(f"Delete failed: {e}")

st.caption("© 2025 PolicySimplify AI — Multi-tenant demo")
