"""
checklist_generator.py — Day 2 tuned
- Clearer, tighter outputs for government readers
- Consistent formats for summary/checklist/risk
- Lazy OpenAI client (no proxy issues)
"""

from __future__ import annotations
import os
from typing import Dict
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

CHAT_MODEL = os.getenv("OPENAI_MODEL_CHAT", "gpt-4o-mini")

# Truncation limits (tune in .env if needed)
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "12000"))
CHECKLIST_MAX_CHARS = int(os.getenv("CHECKLIST_MAX_CHARS", "10000"))
RISK_MAX_CHARS = int(os.getenv("RISK_MAX_CHARS", "8000"))

SUMMARY_SYS = (
    "You are a senior government policy analyst.\n"
    "Rewrite policy text into a brief, accurate brief for non-lawyers.\n"
    "Output using this exact structure and labels:\n"
    "1) Purpose: <1–2 sentences>\n"
    "2) Scope: <who/what is covered; 1–2 sentences>\n"
    "3) Key Points:\n"
    " - <bullet 1>\n"
    " - <bullet 2>\n"
    " - <bullet 3>\n"
    "Keep total under ~200 words. No legalese. No speculation."
)

CHECKLIST_SYS = (
    "You are a government compliance officer.\n"
    "Extract only mandatory, actionable steps from the policy.\n"
    "Each bullet must start with a strong verb, include a responsible team/role if mentioned, "
    "and include an explicit deadline if present; otherwise label as 'Ongoing' or suggest "
    "a pragmatic timeframe like 'within 30 days'.\n"
    "Output as bullets only, e.g.:\n"
    " - Issue contamination notices to offending households — Owner: Waste Services — Due: within 30 days of first offence\n"
    " - Submit annual contamination report — Owner: Sustainability Unit — Due: 30 September each year\n"
    "Do not repeat background or non-actionable info."
)

RISK_SYS = (
    "You are a risk assessor for a local council.\n"
    "Assess compliance risk considering penalties, urgency, scope, and implementation complexity.\n"
    "Start with ONLY one of: High / Medium / Low on the first line.\n"
    "Then provide 1–2 short bullet points explaining why.\n"
    "Example:\n"
    "High\n"
    " - Statutory fines apply for late reporting\n"
    " - Immediate operational changes required"
)

def _client() -> OpenAI:
    # Let the SDK read OPENAI_API_KEY from env.
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
        "Return bullets only."
    )
    return _chat(CHECKLIST_SYS, prompt)

def assess_risk(text: str, summary: str) -> str:
    prompt = (
        f"POLICY TEXT (truncated):\n{text[:RISK_MAX_CHARS]}\n\n"
        f"SUMMARY FOR CONTEXT:\n{summary}"
    )
    return _chat(RISK_SYS, prompt)

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
