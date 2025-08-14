from typing import List, Dict
from pypdf import PdfReader

def extract_text_from_pdf_bytes(file_bytes: bytes) -> str:
    """
    Extract text from a PDF file (bytes). Returns a single concatenated string.
    Robust to scanned PDFs only insofar as pypdf can read them (no OCR).
    """
    # pypdf can read from file-like; wrap in memory
    import io
    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for i, page in enumerate(reader.pages):
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return "\n\n".join(pages)

def chunk_text(text: str, chunk_size: int = 1500, chunk_overlap: int = 200) -> List[str]:
    """
    Simple recursive-ish chunker: splits on paragraphs, then combines up to chunk_size chars,
    overlapping by chunk_overlap to preserve context.
    """
    paras = [p.strip() for p in text.split("\n") if p.strip()]
    chunks = []
    buf = ""
    for p in paras:
        if len(buf) + len(p) + 1 <= chunk_size:
            buf += (("\n" if buf else "") + p)
        else:
            if buf:
                chunks.append(buf)
            # start next; include tail overlap from previous buffer
            tail = buf[-chunk_overlap:] if chunk_overlap and len(buf) > chunk_overlap else ""
            buf = (tail + ("\n" if tail else "") + p)
    if buf:
        chunks.append(buf)
    return chunks

def make_docs(chunks: List[str], source_name: str) -> List[Dict]:
    """
    Convert raw chunk strings into doc dicts with metadata.
    """
    docs = []
    for i, c in enumerate(chunks):
        docs.append({
            "id": f"{source_name}::chunk_{i}",
            "text": c,
            "metadata": {"source": source_name, "chunk": i}
        })
    return docs
