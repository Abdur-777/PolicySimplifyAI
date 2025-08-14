# bulk_ingest.py
from __future__ import annotations
import csv, os, time, requests
from pdf_loader import extract_text_from_pdf_bytes, chunk_text, make_docs
from vectorstore import SimpleFAISS
from checklist_generator import generate_summary, generate_checklist, assess_risk, compose_policy_card
from storage import save_card
from redact import scrub

VECTOR_DB_NAME = os.getenv("VECTOR_DB_NAME", "demo_store")
ENABLE_OCR = os.getenv("ENABLE_OCR","false").lower()=="true"

def run(csv_path: str):
    store = SimpleFAISS.load(VECTOR_DB_NAME)
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            url = (row.get("url") or "").strip()
            if not url: continue
            name = row.get("name") or os.path.basename(url) or "policy.pdf"
            print(f"[ingest] {name} <- {url}")
            r = requests.get(url, timeout=25); r.raise_for_status()
            pdf_bytes = r.content
            text = extract_text_from_pdf_bytes(pdf_bytes) or ""
            if not text.strip() and ENABLE_OCR:
                from ocr_utils import pdf_bytes_to_text_via_ocr
                text = pdf_bytes_to_text_via_ocr(pdf_bytes)
            text = scrub(text)
            docs = make_docs(chunk_text(text), name)
            store.add(docs)
            snippet = docs[len(docs)//2]["text"] if docs else text[:3000]
            summary = generate_summary(snippet)
            checklist = generate_checklist(snippet, summary)
            risk_note = assess_risk(snippet, summary)
            card = compose_policy_card(name, summary, checklist, risk_note)
            card["created_at"] = int(time.time()); save_card(card)
    store.save(VECTOR_DB_NAME); print("Done.")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python bulk_ingest.py policies.csv   # columns: name,url"); raise SystemExit(2)
    run(sys.argv[1])
