from typing import List, Dict
from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
_CLIENT = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SUMMARY_SYS = """You are a government policy analyst.
Summarize the policy text into clear, plain-English points for non-legal staff.
Keep it factual and brief (5-8 bullets max)."""

CHECKLIST_SYS = """You are a compliance officer.
From the policy text and its summary, extract mandatory, actionable steps with owners and due dates when present.
Output a concise checklist. If dates are not explicit, recommend realistic timelines (e.g., 'within 30 days')."""

RISK_SYS = """You are a risk assessor.
Assign a risk label (High, Medium, Low) based on scope, penalties, and urgency in the policy text.
Explain in 1-2 sentences why."""

def _chat(system_prompt: str, user_prompt: str, model: str = "gpt-4o-mini") -> str:
    resp = _CLIENT.chat.completions.create(
        model=model,
        messages=[
            {"role":"system","content":system_prompt},
            {"role":"user","content":user_prompt}
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content.strip()

def generate_summary(text: str) -> str:
    prompt = f"POLICY TEXT:\n{text[:12000]}"
    return _chat(SUMMARY_SYS, prompt)

def generate_checklist(text: str, summary: str) -> str:
    prompt = f"POLICY TEXT (truncated):\n{text[:10000]}\n\nSUMMARY:\n{summary}\n\nReturn as bullet points with verbs first."
    return _chat(CHECKLIST_SYS, prompt)

def assess_risk(text: str, summary: str) -> str:
    prompt = f"POLICY TEXT (truncated):\n{text[:8000]}\n\nSUMMARY:\n{summary}"
    return _chat(RISK_SYS, prompt)

def compose_policy_card(source_name: str, summary: str, checklist: str, risk_note: str) -> Dict:
    # Extract risk label if present at start of response
    risk_label = "Medium"
    for lvl in ["High", "Medium", "Low"]:
        if risk_note.strip().lower().startswith(lvl.lower()):
            risk_label = lvl
            break
    return {
        "policy": source_name,
        "summary": summary,
        "checklist": checklist,
        "risk": risk_label,
        "risk_explainer": risk_note
    }
