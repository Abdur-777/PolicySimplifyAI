# llm_client.py
"""
Safe wrapper around OpenAI chat calls.
Supports new openai>=1.0 client.
"""

import os
from openai import OpenAI

# One global client
_api_key = os.getenv("OPENAI_API_KEY")
client = None
if _api_key:
    try:
        client = OpenAI(api_key=_api_key)
    except Exception as e:
        print(f"[WARN] Could not init OpenAI client: {e}")
        client = None

def chat(model: str, messages: list[dict], temperature: float = 0.2, max_tokens: int = 700) -> str:
    """
    Run a chat completion and return the text output.
    """
    if not client:
        return ""

    try:
        resp = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print(f"[WARN] LLM call failed: {e}")
        return ""
