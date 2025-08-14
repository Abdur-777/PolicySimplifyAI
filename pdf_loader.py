# pdf_loader.py
# Utilities for extracting text from PDFs, normalizing, chunking, and building doc objects.

from __future__ import annotations
import io
import re
from typing import List, Dict, Any, Iterable

from pypdf import PdfReader


# ---------------------------
# Text extraction
# ---------------------------

def extract_text_from_pdf_bytes(data: bytes) -> str:
    """
    Extract UTF-8 text from a PDF byte string using pypdf.
    Returns a single normalized string (one doc) or "" if nothing extracted.
    """
    if not data:
        return ""

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception:
        # corrupted or unsupported file
        return ""

    if reader.is_encrypted:
        # Try to decrypt with empty password (common for lightly "secured" PDFs)
        try:
            reader.decrypt("")
        except Exception:
            return ""

    texts: List[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text:
            texts.append(page_text)

    raw = "\n".join(texts)
    return normalize_whitespace(raw)


# ---------------------------
# Normalization & chunking
# ---------------------------

_WHITESPACE_RE = re.compile(r"[ \t\u00A0]+")

def normalize_whitespace(text: str) -> str:
    """
    Collapse runs of spaces/tabs, preserve newlines, trim edges.
    """
    if not text:
        return ""
    # Convert Windows newlines and weird non-breaking spaces
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse multiple spaces/tabs
    text = _WHITESPACE_RE.sub(" ", text)
    # Strip trailing spaces on each line
    text = "\n".join(line.strip() for line in text.split("\n"))
    # Remove leading/trailing blank lines
    return text.strip()


def _paragraphs(text: str) -> Iterable[str]:
    """
    Split text into paragraphs on blank lines.
    """
    para: List[str] = []
    for line in text.split("\n"):
        if line.strip() == "":
            if para:
                yield " ".join(para).strip()
                para = []
        else:
            para.append(line.strip())
    if para:
        yield " ".join(para).strip()


def chunk_text(
    text: str,
    *,
    target_chars: int = 1200,
    overlap_chars: int = 200,
    hard_max_chars: int = 2000,
) -> List[str]:
    """
    Greedy paragraph-based chunker with overlap. Keeps chunks readable for LLMs.
    - target_chars: desired chunk size
    - overlap_chars: trailing context appended to next chunk (from prior end)
    - hard_max_chars: never exceed this size (fallback to line-split if one para is too long)
    """
    text = normalize_whitespace(text)
    if not text:
        return []

    paras = list(_paragraphs(text))
    chunks: List[str] = []

    cur = ""
    for p in paras:
        if not cur:
            cur = p
        elif len(cur) + 1 + len(p) <= target_chars:
            cur = f"{cur}\n{p}"
        else:
            # finalize current chunk
            chunks.append(cur)
            # start next with overlap tail
            if overlap_chars > 0:
                tail = cur[-overlap_chars:].split("\n")
                tail = "\n".join(t for t in tail[-3:] if t.strip())  # a few trailing lines
                cur = (tail + "\n" + p).strip()
            else:
                cur = p

        # very long paragraph fallback: hard wrap
        if len(cur) > hard_max_chars:
            # cut safely on whitespace near boundary
            cut = _safe_cut(cur, hard_max_chars)
            chunks.append(cur[:cut].strip())
            remainder = cur[cut:].strip()
            cur = remainder

    if cur.strip():
        chunks.append(cur.strip())

    # final defense: drop empty
    return [c for c in chunks if c.strip()]


def _safe_cut(s: str, limit: int) -> int:
    """
    Find a whitespace boundary at or before limit; if none, cut at limit.
    """
    if len(s) <= limit:
        return len(s)
    i = s.rfind(" ", 0, limit)
    if i == -1:
        i = s.rfind("\n", 0, limit)
    return i if i != -1 else limit


# ---------------------------
# Doc objects
# ---------------------------

def make_docs(chunks: List[str], source_name: str, tenant: str = "default") -> List[Dict[str, Any]]:
    """
    Wrap raw chunks into doc dicts consumable by the vectorstore / retriever.
    """
    docs: List[Dict[str, Any]] = []
    for i, txt in enumerate(chunks):
        docs.append({
            "text": txt,
            "metadata": {
                "source": source_name,
                "chunk": i,
                "tenant": tenant
            }
        })
    return docs
