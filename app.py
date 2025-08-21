# app.py — PolicySimplify AI (VIC 79 councils) — Sales Mode + Preloads + Summaries/Checklists/Q&A
from __future__ import annotations

import os, io, json, time, logging, requests
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv
import streamlit as st
import pandas as pd

# =========================
# Setup
# =========================
load_dotenv()
APP_NAME    = os.getenv("APP_NAME", "PolicySimplify AI")
APP_TAGLINE = os.getenv("APP_TAGLINE", "Turn any government policy into an instant compliance checklist.")
TEXT_CAP    = int(os.getenv("TEXT_CAP", "120000"))
ENABLE_OCR  = os.getenv("ENABLE_OCR", "false").lower() == "true"
SALES_MODE_DEFAULT = os.getenv("SALES_MODE_DEFAULT", "true").lower() == "true"
VECTOR_DB_NAME = os.getenv("VECTOR_DB_NAME", "demo_store")

# Important: your assets folder name
PRELOAD_BASE_SHARED = "assetssss/preloads/_shared"
PRELOAD_BASE_TENANT = "assetssss/preloads"  # optional per-tenant local files
COUNCIL_BRANDS_FILE = "council_brands.json"  # optional (colors + logo per council)

st.set_page_config(page_title=APP_NAME, page_icon="✅", layout="wide")
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("policysimplify")

# =========================
# Optional imports (graceful fallbacks so demo never breaks)
# =========================
missing: List[str] = []

try:
    from pdf_loader import extract_text_from_pdf_bytes, chunk_text, make_docs
except Exception:
    missing.append("pdf_loader.py")
    def extract_text_from_pdf_bytes(b: bytes) -> str: return ""
    def chunk_text(t: str, chunk_size: int = 1200, overlap: int = 150) -> List[str]: return [t]
    def make_docs(chunks: List[str], source_name: str, tenant: str = "default") -> List[Dict[str, Any]]:
        return [{"text": c, "metadata": {"source": source_name, "tenant": tenant}} for c in chunks]

try:
    from checklist_generator import generate_summary, generate_checklist, assess_risk, compose_policy_card, qa_answer
except Exception:
    missing.append("checklist_generator.py")
    def generate_summary(text: str) -> str: return "Summary unavailable (install checklist_generator.py)."
    def generate_checklist(text: str, summary: str) -> str: return "- [ ] Example action\n- [ ] Another action"
    def assess_risk(text: str, summary: str) -> str: return "Low"
    def compose_policy_card(policy: str, summary: str, checklist: str, risk: str) -> Dict[str, Any]:
        return {"policy": policy, "summary": summary, "checklist": checklist, "risk": risk, "risk_explainer": "N/A"}
    def qa_answer(snippets: List[str], question: str) -> str:
        return "Q&A unavailable (install checklist_generator.py)."

try:
    from vectorstore import SimpleFAISS
except Exception:
    missing.append("vectorstore.py")
    class SimpleFAISS:
        def __init__(self): self._docs=[]
        @classmethod
        def load(cls, name: str): return cls()
        def save(self, name: str): pass
        def add(self, docs: List[Dict[str, Any]]): self._docs.extend([(1.0, d) for d in docs])
        def search(self, q: str, k: int = 4) -> List[Tuple[float, Dict[str, Any]]]:
            return self._docs[:k]

try:
    from storage import save_card, load_cards, purge_older_than, delete_all_for_tenant
except Exception:
    missing.append("storage.py")
    _MEM = {}
    def save_card(card: Dict[str, Any]): _MEM.setdefault(card.get("tenant","default"), []).append(card)
    def load_cards(tenant: str, limit: int = 500): return list(reversed(_MEM.get(tenant, [])))[:limit]
    def purge_older_than(tenant: str, days: int) -> int: return 0
    def delete_all_for_tenant(tenant: str): _MEM[tenant]=[]

try:
    from utils import extract_structured_tasks
except Exception:
    missing.append("utils.py")
    def extract_structured_tasks(checklist: str) -> List[Dict[str,str]]:
        rows=[]
        for ln in (checklist or "").splitlines():
            t=ln.strip("-*• ").strip()
            if t: rows.append({"action": t, "owner": "", "due": ""})
        return rows

try:
    from ocr_utils import pdf_bytes_to_text_via_ocr
except Exception:
    def pdf_bytes_to_text_via_ocr(_bytes: bytes) -> str: return ""

try:
    from redact import scrub
except Exception:
    def scrub(x: str) -> str: return x

# =========================
# Branding helpers
# =========================
def load_brand_map() -> Dict[str, Dict[str, Any]]:
    if os.path.exists(COUNCIL_BRANDS_FILE):
        try:
            with open(COUNCIL_BRANDS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            st.warning(f"Brand file error: {e}")
    return {}

BRANDS = load_brand_map()

def list_council_keys_from_shared() -> List[str]:
    if not os.path.isdir(PRELOAD_BASE_SHARED):
        return []
    return sorted([d for d in os.listdir(PRELOAD_BASE_SHARED)
                   if os.path.isdir(os.path.join(PRELOAD_BASE_SHARED, d))])

def apply_brand(council_key: str, council_label: str):
    cfg = BRANDS.get(council_key, {})
    primary   = cfg.get("primary", "#0B2A5C")
    secondary = cfg.get("secondary", "#1555C0")
    accent    = cfg.get("accent", "#00B3A4")
    css = f"""
    <style>
      :root {{ --ps-primary:{primary}; --ps-secondary:{secondary}; --ps-accent:{accent}; }}
      .ps-header h2 {{ color: var(--ps-secondary); }}
      .stButton>button {{ background: var(--ps-primary); color:#fff; border-radius:.5rem; }}
      .stButton>button:hover {{ filter:brightness(.95); }}
      .ps-chip {{ background:#eef4ff; color:var(--ps-secondary); border-radius:999px; padding:.2rem .6rem; font-size:.8rem; }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)
    logo = cfg.get("logo")
    c1, c2 = st.columns([0.82, 0.18])
    with c1:
        st.markdown(f"<div class='ps-header'><h2>{APP_NAME}</h2><div><em>{APP_TAGLINE}</em></div></div>", unsafe_allow_html=True)
        st.caption(f"Tenant: **{council_label}**  •  Key: `{council_key}`")
    with c2:
        if logo and os.path.exists(logo):
            st.image(logo, use_column_width=True)
        else:
            st.markdown(f"<div style='text-align:right' class='ps-chip'>{council_label}</div>", unsafe_allow_html=True)
    st.divider()

# =========================
# Preload discovery
# =========================
def _read_json_urls(fp: str) -> List[Dict[str, Any]]:
    try:
        with open(fp, "r", encoding="utf-8") as f:
            data = json.load(f)
        out=[]
        for it in data if isinstance(data, list) else []:
            url = it.get("url")
            nm  = it.get("name") or (os.path.basename(url) if url else "Policy.pdf")
            if url: out.append({"type":"url","name":nm,"url":url})
        return out
    except Exception as e:
        st.warning(f"Invalid JSON in {fp}: {e}")
        return []

def list_preloads_for(council_key: str) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []

    # tenant-specific (optional)
    tdir = os.path.join(PRELOAD_BASE_TENANT, council_key)
    if os.path.isdir(tdir):
        for name in sorted(os.listdir(tdir)):
            path = os.path.join(tdir, name)
            if os.path.isdir(path): continue
            ext = os.path.splitext(name)[1].lower()
            if name == "demo_policies.json": items += _read_json_urls(path)
            elif ext == ".pdf":
                try:
                    with open(path, "rb") as f: items.append({"type":"pdf","name":name,"bytes":f.read()})
                except: pass
            elif ext in (".txt",".md"):
                try:
                    with open(path, "r", encoding="utf-8") as f: items.append({"type":"text","name":name,"text":f.read()})
                except: pass

    # shared
    sdir = os.path.join(PRELOAD_BASE_SHARED, council_key)
    if os.path.isdir(sdir):
        for name in sorted(os.listdir(sdir)):
            path = os.path.join(sdir, name)
            if os.path.isdir(path): continue
            ext = os.path.splitext(name)[1].lower()
            if name == "demo_policies.json": items += _read_json_urls(path)
            elif ext == ".pdf":
                try:
                    with open(path, "rb") as f: items.append({"type":"pdf","name":name,"bytes":f.read()})
                except: pass
            elif ext in (".txt",".md"):
                try:
                    with open(path, "r", encoding="utf-8") as f: items.append({"type":"text","name":name,"text":f.read()})
                except: pass

    return items

# =========================
# Core processing
# =========================
def process_policy(source_name: str, *, tenant_key: str, file_bytes: bytes | None = None, raw_text: str | None = None):
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
        text = scrub(text)

    chunks = chunk_text(text)
    docs = make_docs(chunks, source_name, tenant=tenant_key)

    with st.spinner("Indexing..."):
        st.session_state["store"].add(docs)
        st.session_state["store"].save(VECTOR_DB_NAME)

    with st.spinner("Generating summary, checklist & risk..."):
        snippet = docs[len(docs)//2]["text"] if docs else text[:3000]
        summary   = generate_summary(snippet)
        checklist = generate_checklist(snippet, summary)
        risk      = assess_risk(snippet, summary)

        card = compose_policy_card(source_name, summary, checklist, risk)
        card["created_at"] = int(time.time())
        card["tenant"] = tenant_key
        card["structured_tasks"] = extract_structured_tasks(card["checklist"])

        st.session_state["policy_cards"].append(card)
        save_card(card)

# =========================
# Boot session state
# =========================
if "store" not in st.session_state:
    st.session_state["store"] = SimpleFAISS.load(VECTOR_DB_NAME)
if "policy_cards" not in st.session_state:
    boot_key = os.getenv("COUNCIL_KEY") or "wyndham-city"
    st.session_state["policy_cards"] = load_cards(tenant=boot_key, limit=500)

# =========================
# Sidebar: Sales Mode & council selection (FIXED selectbox usage)
# =========================
st.sidebar.markdown("### 🎬 Sales Mode")
if "sales_mode" not in st.session_state:
    st.session_state["sales_mode"] = SALES_MODE_DEFAULT
sales_on = st.sidebar.toggle("Enable Sales Mode", value=st.session_state["sales_mode"],
                             help="Instantly switch branding + preload demo policies")
st.session_state["sales_mode"] = sales_on

# councils from filesystem (fallback to wyndham-city if none)
council_keys = list_council_keys_from_shared() or ["wyndham-city"]
labels = {k: BRANDS.get(k, {}).get("name", k.replace("-", " ").title()) for k in council_keys}

# current key from query param or session or env
query_c = st.query_params.get("council")
if isinstance(query_c, list):  # safety
    query_c = query_c[0] if query_c else None
current_key = st.session_state.get("council_override") or query_c or os.getenv("COUNCIL_KEY") or council_keys[0]
if current_key not in council_keys:
    current_key = council_keys[0]

if sales_on:
    try:
        idx_default = council_keys.index(current_key)
    except ValueError:
        idx_default = 0

    # ✅ selectbox returns ONE value only
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

# Header with branding
apply_brand(TENANT_KEY, TENANT_NAME)

# Missing modules banner
if missing:
    st.warning("The following modules were not found and have been stubbed: " + ", ".join(missing))

# =========================
# Sidebar: Ingest & Preload
# =========================
st.sidebar.markdown("---")
st.sidebar.markdown("### Ingest a policy")

upl = st.sidebar.file_uploader("Upload PDF", type=["pdf"])
if upl and st.sidebar.button("Process uploaded PDF"):
    process_policy(source_name=upl.name, tenant_key=TENANT_KEY, file_bytes=upl.read())

url_in = st.sidebar.text_input("Or fetch from URL (direct PDF link)")
if st.sidebar.button("Fetch & process URL"):
    if not url_in.strip():
        st.sidebar.warning("Enter a direct PDF URL.")
    else:
        try:
            r = requests.get(url_in, timeout=30)
            r.raise_for_status()
            name = os.path.basename(url_in) or "Policy.pdf"
            process_policy(source_name=name, tenant_key=TENANT_KEY, file_bytes=r.content)
            st.sidebar.success("Fetched & processed.")
        except Exception as e:
            st.sidebar.error(f"Fetch failed: {e}")

st.sidebar.markdown("---")
if st.sidebar.button("Preload demo policies"):
    items = list_preloads_for(TENANT_KEY)
    if not items:
        st.sidebar.warning(f"No preloads found for '{TENANT_KEY}'. Put demo_policies.json in {PRELOAD_BASE_SHARED}/{TENANT_KEY}/")
    else:
        count=0
        for it in items:
            try:
                if it["type"] == "pdf":
                    process_policy(source_name=it["name"], tenant_key=TENANT_KEY, file_bytes=it["bytes"]); count+=1
                elif it["type"] == "text":
                    process_policy(source_name=it["name"], tenant_key=TENANT_KEY, raw_text=it["text"]); count+=1
                elif it["type"] == "url":
                    r = requests.get(it["url"], timeout=25); r.raise_for_status()
                    process_policy(source_name=it["name"], tenant_key=TENANT_KEY, file_bytes=r.content); count+=1
            except Exception as e:
                st.sidebar.error(f"Failed {it.get('name','(unknown)')}: {e}")
        st.sidebar.success(f"Preloaded {count} document(s).")

# Admin
st.sidebar.markdown("---")
st.sidebar.markdown("### Admin")
if st.sidebar.button("🗑️ Delete ALL data for this council"):
    try:
        delete_all_for_tenant(TENANT_KEY)
        st.session_state["policy_cards"] = []
        st.sidebar.success("Deleted all data for this council.")
    except Exception as e:
        st.sidebar.error(f"Delete failed: {e}")

# =========================
# Risk overview
# =========================
def _count_bullets(s: str) -> int:
    c=0
    for ln in (s or "").splitlines():
        t=ln.strip()
        if not t: continue
        if t.startswith(("-", "*", "•")) or (len(t)>1 and t[0].isdigit() and t[1]=="."): c+=1
    return c

st.markdown("### 1) Risk overview")

cards = load_cards(tenant=TENANT_KEY, limit=500)
st.session_state["policy_cards"] = cards

if not cards:
    st.info("Upload a PDF, paste a URL, or use **Preload demo policies** in the sidebar.")
else:
    total_obl = sum(_count_bullets(c.get("checklist","")) for c in cards)
    high = sum(1 for c in cards if c.get("risk")=="High")
    med  = sum(1 for c in cards if c.get("risk")=="Medium")
    low  = sum(1 for c in cards if c.get("risk")=="Low")
    a,b,c = st.columns(3)
    a.metric("Total Policies", len(cards))
    b.metric("High Risk", high)
    c.metric("Obligations (approx.)", total_obl)

st.divider()

# =========================
# Table & details
# =========================
st.markdown("### 2) Active compliance items")
if not cards:
    st.info("No data yet.")
else:
    df = pd.DataFrame([{
        "Policy": rec["policy"],
        "Summary (plain-English)": rec["summary"],
        "Checklist (actions)": rec["checklist"],
        "Risk": rec.get("risk",""),
        "Risk explainer": rec.get("risk_explainer",""),
        "Processed": time.strftime("%Y-%m-%d %H:%M", time.localtime(rec.get("created_at",0))) if rec.get("created_at") else ""
    } for rec in cards])

    order = {"High":0,"Medium":1,"Low":2}
    if "Risk" in df.columns:
        df["_o"] = df["Risk"].map(order).fillna(3)
        df = df.sort_values(by=["_o","Processed","Policy"], ascending=[True,False,True]).drop(columns=["_o"], errors="ignore")

    colA,colB = st.columns([0.7,0.3])
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

    # Structured tasks
    st.markdown("#### Structured view (Action / Owner / Due)")
    rows=[]
    cmap={c["policy"]: c for c in cards}
    for rec in view_df.to_dict(orient="records"):
        c=cmap.get(rec["Policy"])
        if not c: continue
        for t in c.get("structured_tasks", []):
            rows.append({"Policy":rec["Policy"],"Action":t.get("action",""),"Owner":t.get("owner",""),"Due":t.get("due","")})
    st.dataframe(pd.DataFrame(rows) if rows else pd.DataFrame(columns=["Policy","Action","Owner","Due"]), use_container_width=True)

    # Exports
    st.markdown("#### Export")
    st.download_button("Download table as CSV", data=view_df.to_csv(index=False).encode("utf-8"),
                       file_name="policy_compliance_items.csv", mime="text/csv", use_container_width=True)
    st.download_button("Download table as JSON", data=json.dumps(view_df.to_dict(orient="records"), indent=2).encode("utf-8"),
                       file_name="policy_compliance_items.json", mime="application/json", use_container_width=True)

st.divider()

# =========================
# Q&A
# =========================
st.markdown("### 3) Ask the policy")
q = st.text_input("Ask a question about your uploaded policies")
if st.button("Get answer"):
    if not q.strip():
        st.warning("Type a question.")
    else:
        hits = st.session_state["store"].search(q, k=4)
        snippets = [doc["text"] for _, doc in hits]
        if not snippets:
            st.info("No context found yet. Upload or preload a policy.")
        else:
            ans = qa_answer(snippets, q)
            st.markdown("**Answer:**"); st.write(ans)
            with st.expander("Sources"):
                for i,(score,doc) in enumerate(hits,1):
                    src = doc.get("metadata",{}).get("source","Unknown")
                    st.markdown(f"**{i}. {src}** (score {score:.2f})")
                    st.code(doc["text"][:700])

st.caption("© 2025 PolicySimplify AI — Multi-tenant sales build (VIC 79)")
