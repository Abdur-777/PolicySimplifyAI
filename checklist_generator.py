"""
checklist_generator.py — Day 4
- Tuned, structured outputs for gov readers
- Lazy OpenAI client (avoids proxy kwargs)
- Adds qa_answer() for retrieval Q&A
"""

from __future__ import annotations
import os
from typing import Dict, List
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

CHAT_MODEL = os.getenv("OPENAI_MODEL_CHAT", "gpt-4o-mini")

# Truncation limits (tune via .env)
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "12000"))
CHECKLIST_MAX_CHARS = int(os.getenv("CHECKLIST_MAX_CHARS", "10000"))
RISK_MAX_CHARS = int(os.getenv("RISK_MAX_CHARS", "8000"))

SUMMARY_SYS = (
    "You are a senior government policy analyst.\n"
    "Rewrite the policy into a short brief for non-lawyers.\n"
    "Output EXACTLY this structure and labels:\n"
    "1) Purpose: <1–2 sentences>\n"
    "2) Scope: <who/what is covered; 1–2 sentences>\n"
    "3) Key Points:\n"
    " - <bullet 1>\n"
    " - <bullet 2>\n"
    " - <bullet 3>\n"
    "Keep total under ~200 words. Avoid legalese."
)

CHECKLIST_SYS = (
    "You are a government compliance officer.\n"
    "Extract ONLY mandatory, actionable steps. Each bullet MUST:\n"
    " - Start with a strong verb\n"
    " - Include an Owner (team/role) if available\n"
    " - Include Due date if explicit; else 'Ongoing' or a pragmatic timeframe (e.g., 'within 30 days')\n"
    "Return bullets only. Use the pattern:\n"
    " - <Action> — Owner: <Role/Team> — Due: <date or timeframe>\n"
)

RISK_SYS = (
    "You are a risk assessor for a council.\n"
    "Assess overall risk as exactly one of: High / Medium / Low (first line only),\n"
    "then 1–2 short bullets on why (penalties, urgency, scope, complexity)."
)

QA_SYS = (
  "You answer questions using ONLY the provided context snippets from local policies. "
  "If the answer isn't in the snippets, reply exactly: 'Not found in the provided policies.' "
  "Be concise (1–3 sentences) and avoid legalese."
)

def _client() -> OpenAI:
    # Let SDK read OPENAI_API_KEY from env
    return OpenAI()

def _chat(system_prompt: str, user_prompt: str, model: str = CHAT_MODEL) -> str:
    client = _client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()

def generate_summary(text: str) -> str:
    prompt = f"POLICY TEXT (truncated):\n{text[:SUMMARY_MAX_CHARS]}"
    return _chat(SUMMARY_SYS, prompt)

def generate_checklist(text: str, summary: str) -> str:
    prompt = (
        f"POLICY TEXT (truncated):\n{text[:CHECKLIST_MAX_CHARS]}\n\n"
        f"SUMMARY FOR CONTEXT:\n{summary}\n\n"
        "Return bullets only, formatted as specified."
    )
    return _chat(CHECKLIST_SYS, prompt)

def assess_risk(text: str, summary: str) -> str:
    prompt = (
        f"POLICY TEXT (truncated):\n{text[:RISK_MAX_CHARS]}\n\n"
        f"SUMMARY FOR CONTEXT:\n{summary}"
    )
    return _chat(RISK_SYS, prompt)

def qa_answer(snippets: List[str], question: str, model: str = CHAT_MODEL) -> str:
    client = _client()
    context = "\n\n---\n\n".join(snippets[:6])
    prompt = f"CONTEXT SNIPPETS:\n{context}\n\nQUESTION:\n{question}\n\nAnswer:"
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role":"system","content":QA_SYS},
            {"role":"user","content":prompt},
        ],
        temperature=0.1,
    )
    return resp.choices[0].message.content.strip()

def compose_policy_card(source_name: str, summary: str, checklist: str, risk_note: str) -> Dict:
    # Determine risk label from the first non-empty line
    first_line = next((ln.strip() for ln in risk_note.splitlines() if ln.strip()), "").lower()
    if first_line.startswith("high"):
        risk_label = "High"
    elif first_line.startswith("medium"):
        risk_label = "Medium"
    elif first_line.startswith("low"):
        risk_label = "Low"
    else:
        risk_label = "Medium"

    return {
        "policy": source_name,
        "summary": summary,
        "checklist": checklist,
        "risk": risk_label,
        "risk_explainer": risk_note,
    }
