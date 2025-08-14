# pdf_loader.py
from __future__ import annotations
from pypdf import PdfReader
from typing import List, Dict

def extract_text_from_pdf_bytes(data: bytes) -> str:
    try:
        r = PdfReader(stream=data)
        out = []
        for p in r.pages:
            t = p.extract_text() or ""
            if t.strip(): out.append(t)
        return "\n\n".join(out)
    except Exception:
        return ""

def chunk_text(text: str, chunk_size: int = 1200, overlap: int = 200) -> List[str]:
    words = text.split()
    chunks, buff = [], []
    count = 0
    for w in words:
        buff.append(w); count += len(w) + 1
        if count >= chunk_size:
            chunks.append(" ".join(buff)); 
            buff = buff[-overlap:] if overlap > 0 else []
            count = sum(len(x)+1 for x in buff)
    if buff: chunks.append(" ".join(buff))
    return chunks

def make_docs(chunks: List[str], source_name: str) -> List[Dict]:
    docs = []
    for i, ch in enumerate(chunks):
        docs.append({"text": ch, "metadata": {"source": source_name, "chunk": i}})
    return docs
