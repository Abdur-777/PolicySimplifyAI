# checklist_generator.py
"""
LLM-backed generators for PolicySimplify AI with graceful fallbacks.

Exports:
- generate_summary(text) -> str
- generate_checklist(text, summary) -> str
- assess_risk(text, summary) -> {"level": "High|Medium|Low", "explainer": str}
- compose_policy_card(policy, summary, checklist, risk) -> dict
- qa_answer(snippets, question) -> str
"""

from __future__ import annotations
import os, re, json
from typing import List, Dict, Any, Tuple

try:
    # Our safe wrapper around OpenAI
    from llm_client import chat as _llm_chat
except Exception:
    _llm_chat = None  # will trigger fallbacks

# Optional: surface warnings nicely if Streamlit is present
try:
    import streamlit as st
except Exception:
    st = None

# --------------------------
# Config
# --------------------------
DEFAULT_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
MAX_TOKENS_OUT = int(os.getenv("LLM_MAX_TOKENS", "700"))
TEXT_CAP = int(os.getenv("TEXT_CAP", "120000"))

# --------------------------
# System prompts
# --------------------------
SUMMARY_SYS = (
    "You are a plain-English policy explainer for local councils. "
    "Summarize key obligations, who is responsible, and any reporting or deadlines. "
    "Keep it crisp and actionable, avoid legalese."
)

CHECKLIST_SYS = (
    "You convert policy text into a practical compliance checklist. "
    "Return bullet points with checkboxes like '- [ ] ...'. "
    "Each item should be a single concrete action. Include owners/roles and timeframes if present."
)

RISK_SYS = (
    "You are a risk assessor for compliance. "
    "Read the text and summary and output a JSON object with fields: "
    "{\"level\": \"High|Medium|Low\", \"explainer\": \"1-2 sentences on why\"}. "
    "Factors: penalties, statutory deadlines, safety/financial exposure, frequency of breach, oversight requirements."
)

QA_SYS = (
    "You are a helpful policy Q&A assistant. "
    "Answer based on the provided snippets only. If unsure, say you don't have that information."
)

# --------------------------
# Internal helpers
# --------------------------
def _clamp_text(text: str, cap: int = TEXT_CAP) -> str:
    text = text or ""
    if len(text) > cap:
        return text[:cap]
    return text

def _warn(msg: str):
    if st:
        st.warning(msg)
    else:
        print(f"[WARN] {msg}")

def _chat(system_prompt: str, user_prompt: str, *, model: str = DEFAULT_MODEL,
          temperature: float = 0.2, max_tokens: int = MAX_TOKENS_OUT) -> str:
    """
    Wrapper around llm_client.chat with robust error handling.
    """
    if not _llm_chat:
        _warn("LLM client not available; returning placeholder.")
        return ""
    try:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        out = _llm_chat(model, messages, temperature=temperature, max_tokens=max_tokens)
        return (out or "").strip()
    except Exception as e:
        _warn(f"LLM call failed: {e}; returning placeholder.")
        return ""

def _first_sentences(text: str, n: int = 5) -> str:
    sents = re.split(r'(?<=[.!?])\s+', (text or "").strip())
    return " ".join(sents[:n]).strip()

def _fallback_summary(text: str) -> str:
    text = _clamp_text(text, 5000)
    # lightweight heuristic: pull imperative lines and deadlines
    bullets = []
    for ln in text.splitlines():
        t = ln.strip()
        if not t:
            continue
        if re.search(r"\b(must|shall|required|prohibit|ban|forbid)\b", t, re.I):
            bullets.append(t)
        if len(bullets) >= 6:
            break
    head = _first_sentences(text, 3)
    out = "Overview: " + (head or "No overview available.") + "\n\nKey Obligations:\n"
    for b in bullets:
        out += f"- {b}\n"
    return out.strip()

def _fallback_checklist(text: str) -> str:
    # turn potential obligations into checkbox tasks
    items = []
    for ln in text.splitlines():
        t = ln.strip("-*• \t")
        if not t:
            continue
        if re.search(r"\b(must|shall|required to|ensure|submit|report|review|train|audit)\b", t, re.I):
            items.append(t.rstrip("."))
        if len(items) >= 10:
            break
    if not items:
        items = [
            "Identify applicable obligations",
            "Assign responsible owner",
            "Book a review meeting",
        ]
    return "\n".join(f"- [ ] {it}" for it in items)

def _heuristic_risk(text: str, summary: str) -> Tuple[str, str]:
    # Simple scoring
    t = f"{text}\n{summary}".lower()
    score = 0
    for kw, w in [
        ("penalty", 3), ("fine", 3), ("offence", 2), ("non-compliance", 2),
        ("deadline", 2), ("must", 1), ("shall", 1), ("suspend", 2),
        ("license", 2), ("safety", 2), ("audit", 1), ("reporting", 1)
    ]:
        hits = t.count(kw)
        score += hits * w
    if score >= 12:
        return "High", "Multiple penalties/deadlines and enforcement indicators are present."
    if score >= 6:
        return "Medium", "Some deadlines/penalties or oversight requirements are present."
    return "Low", "Limited enforcement cues; general guidance with lower exposure."

# --------------------------
# Public API
# --------------------------
def generate_summary(text: str) -> str:
    """
    Returns a plain-English summary.
    """
    text = _clamp_text(text)
    prompt = f"Text:\n{text}\n\nReturn a short, plain-English summary (5–8 bullets or a compact paragraph)."
    out = _chat(SUMMARY_SYS, prompt)
    if out:
        return out
    return _fallback_summary(text)

def generate_checklist(text: str, summary: str) -> str:
    """
    Returns a checklist string with '- [ ]' bullets.
    """
    text = _clamp_text(text)
    summary = _clamp_text(summary, 8000)
    prompt = (
        "Create a compliance checklist in '- [ ] ' format. "
        "Focus on concrete actions, owners/roles, and any timeframes.\n\n"
        f"Summary:\n{summary}\n\nText:\n{text}\n\nChecklist:"
    )
    out = _chat(CHECKLIST_SYS, prompt)
    if out:
        # Ensure checkbox format
        lines = []
        for ln in out.splitlines():
            t = ln.strip()
            if not t:
                continue
            if not t.startswith("- ["):
                t = "- [ ] " + t.lstrip("-*• ")
            lines.append(t)
        return "\n".join(lines)
    return _fallback_checklist(f"{summary}\n\n{text}")

def assess_risk(text: str, summary: str) -> Dict[str, str]:
    """
    Returns {"level": "High|Medium|Low", "explainer": "..."}.
    """
    text = _clamp_text(text)
    summary = _clamp_text(summary, 8000)
    prompt = f"Summary:\n{summary}\n\nText:\n{text}\n\nReturn ONLY a JSON object with 'level' and 'explainer'."
    out = _chat(RISK_SYS, prompt)
    if out:
        # Try to parse JSON from the model
        try:
            # strip code fences if any
            m = re.search(r'\{.*\}', out, re.S)
            if m:
                obj = json.loads(m.group(0))
            else:
                obj = json.loads(out)
            level = str(obj.get("level", "")).strip().title()
            expl = str(obj.get("explainer", "")).strip() or "No explainer provided."
            if level not in {"High", "Medium", "Low"}:
                level = "Medium"
            return {"level": level, "explainer": expl}
        except Exception:
            pass
    # Fallback heuristic
    lvl, expl = _heuristic_risk(text, summary)
    return {"level": lvl, "explainer": expl}

def compose_policy_card(policy: str, summary: str, checklist: str, risk: Any) -> Dict[str, Any]:
    """
    Normalizes risk into strings and builds the card dict your app expects.
    - risk can be a string ('High') or dict({'level','explainer'})
    """
    risk_level = "Medium"
    risk_expl = ""
    if isinstance(risk, dict):
        risk_level = str(risk.get("level", "Medium")).title()
        risk_expl  = str(risk.get("explainer", "")).strip()
    elif isinstance(risk, str):
        risk_level = risk.title()
    else:
        risk_level = "Medium"

    return {
        "policy": policy,
        "summary": summary.strip(),
        "checklist": checklist.strip(),
        "risk": risk_level,
        "risk_explainer": risk_expl,
    }

def qa_answer(snippets: List[str], question: str) -> str:
    """
    Answers a user question using provided snippets (retrieved context).
    """
    # Join snippets with markers so the model can cite, even though the UI shows sources separately.
    joined = "\n\n".join(f"[Snippet {i+1}]\n{_clamp_text(s, 4000)}" for i, s in enumerate(snippets))
    prompt = (
        f"Question: {question}\n\n"
        f"Use ONLY this context to answer:\n{joined}\n\n"
        "If the answer isn't in the snippets, reply: 'I don't have that information in the provided policy text.'"
    )
    out = _chat(QA_SYS, prompt, temperature=0.1, max_tokens=600)
    if out:
        return out
    # Fallback: extremely conservative
    return "I don't have that information in the provided policy text."
