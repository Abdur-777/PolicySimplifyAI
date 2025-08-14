# redact.py
from __future__ import annotations
import regex as re
_EMAIL = re.compile(r"\b[a-zA-Z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_PHONE = re.compile(r"(?<!\d)(\+?\d[\d\-\s]{6,}\d)(?!\d)")

def scrub(text: str) -> str:
    if not text: return text
    text = _EMAIL.sub("[REDACTED_EMAIL]", text)
    text = _PHONE.sub("[REDACTED_PHONE]", text)
    return text
