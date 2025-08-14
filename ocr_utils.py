# ocr_utils.py
from __future__ import annotations
import io, pytesseract
from PIL import Image
import pypdfium2 as pdfium

def pdf_bytes_to_text_via_ocr(pdf_bytes: bytes, max_pages: int = 50) -> str:
    text_chunks = []
    pdf = pdfium.PdfDocument(io.BytesIO(pdf_bytes))
    n = min(len(pdf), max_pages)
    for i in range(n):
        page = pdf[i]
        pil = page.render(scale=2.0).to_pil().convert("L")
        txt = pytesseract.image_to_string(pil)
        if txt and txt.strip(): text_chunks.append(txt.strip())
    return "\n\n".join(text_chunks).strip()
