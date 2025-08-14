"""
checklist_generator.py
- Lazy OpenAI client
- Clear system prompts
- Env-tunable chat model & truncation limits
"""

from __future__ import annotations
import os
from typing import Dict
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

CHAT_MODEL = os.getenv("OPENAI_MODEL_CHAT", "gpt-4o-mini")
# Truncate long policy text before sending to the model for speed/cost:
SUMMARY_MAX_CHARS = int(os.getenv("SUMMARY_MAX_CHARS", "12000"))
CHECKLIST_MAX_CHARS = int(os.getenv("CHECKLIST_MAX_CHARS", "10000"))
RISK_MAX_CHARS = int(os.getenv("RISK_MAX_CHARS", "8000"))

SUMMARY_SYS = (
    "You are a government policy analyst.\n"
    "Summarize the policy text into clear, plain-English bullet points for non-legal staff.\n"
    "Keep it factual and brief (5–8 bullets). Avoid legalese. No speculation."
)

CHECKLIST_SYS = (
    "You are a compliance officer.\n"
    "From the policy text and its summary, extract mandatory, actionable steps. "
    "Each bullet should start with a verb and include who is responsible if stated, "
    "and any explicit deadline. If a date isn't explicit, recommend a realistic timeframe "
    "(e.g., 'within 30 days'). Keep it concise and actionable."
)

RISK_SYS = (
    "You are a risk assessor for a government department.\n"
    "Assign a risk label (High, Medium, Low) considering scope, penalties, urgency, "
    "and implementation complexity. Start your response with just the label on the first line, "
    "then provide a 1–2 sentence reason on subsequent lines."
)

def _client() -> OpenAI:
    # Let SDK read OPENAI_API_KEY from env. Avoid passing proxies explicitly.
    return OpenAI()

def _chat(system_prompt: str, user_prompt: str, model: str = CHAT_MODEL) -> str:
    client = _client()
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
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
        f"SUMMARY:\n{summary}\n\n"
        "Return a concise checklist as bullet points."
    )
    return _chat(CHECKLIST_SYS, prompt)

def assess_risk(text: str, summary: str) -> str:
    prompt = (
        f"POLICY TEXT (truncated):\n{text[:RISK_MAX_CHARS]}\n\n"
        f"SUMMARY:\n{summary}"
    )
    return _chat(RISK_SYS, prompt)

def compose_policy_card(source_name: str, summary: str, checklist: str, risk_note: str) -> Dict:
    # First token on first line is expected to be the label
    first_line = (risk_note.splitlines() or [""]).pop(0).strip().lower()
    if "high" in first_line:
        risk_label = "High"
    elif "medium" in first_line:
        risk_label = "Medium"
    elif "low" in first_line:
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
