# api.py
from __future__ import annotations
import os, time, base64
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from pdf_loader import extract_text_from_pdf_bytes, chunk_text, make_docs
from vectorstore import SimpleFAISS
from checklist_generator import generate_summary, generate_checklist, assess_risk, compose_policy_card, qa_answer
from storage import save_card
from redact import scrub

API_SECRET = os.getenv("API_SECRET", "")
VECTOR_DB_NAME = os.getenv("VECTOR_DB_NAME", "demo_store")
ENABLE_OCR = os.getenv("ENABLE_OCR","false").lower()=="true"
app = FastAPI(title="PolicySimplify API", version="1.0")
store = SimpleFAISS.load(VECTOR_DB_NAME)

def _auth(x_api_key: str | None):
    if not API_SECRET or x_api_key == API_SECRET: return
    raise HTTPException(status_code=401, detail="Unauthorized")

class IngestReq(BaseModel):
    source_name: str
    content_b64: str

class QAReq(BaseModel):
    question: str
    k: int = 4

@app.post("/ingest")
def ingest(req: IngestReq, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    pdf_bytes = base64.b64decode(req.content_b64)
    text = extract_text_from_pdf_bytes(pdf_bytes) or ""
    if not text.strip() and ENABLE_OCR:
        from ocr_utils import pdf_bytes_to_text_via_ocr
        text = pdf_bytes_to_text_via_ocr(pdf_bytes)
    text = scrub(text)
    docs = make_docs(chunk_text(text), req.source_name)
    store.add(docs); store.save(VECTOR_DB_NAME)
    snippet = docs[len(docs)//2]["text"] if docs else text[:3000]
    summary = generate_summary(snippet)
    checklist = generate_checklist(snippet, summary)
    risk_note = assess_risk(snippet, summary)
    card = compose_policy_card(req.source_name, summary, checklist, risk_note)
    card["created_at"] = int(time.time()); save_card(card)
    return {"ok": True, "policy": card["policy"], "risk": card["risk"]}

@app.post("/qa")
def qa(req: QAReq, x_api_key: str | None = Header(default=None)):
    _auth(x_api_key)
    hits = store.search(req.question, k=max(1, min(8, req.k)))
    snippets = [doc["text"] for _, doc in hits]
    if not snippets: return {"answer": "No context found."}
    answer = qa_answer(snippets, req.question)
    sources = [{"source": doc.get("metadata",{}).get("source","Unknown"), "score": float(score)} for score, doc in hits]
    return {"answer": answer, "sources": sources}
