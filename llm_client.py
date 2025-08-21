# llm_client.py
import os
from typing import List, Dict, Any
from openai import OpenAI

_client = None

def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        base_url = os.getenv("OPENAI_BASE_URL", "").strip() or None  # Azure or custom, optional
        org      = os.getenv("OPENAI_ORG", "").strip() or None       # optional

        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY is not set. Add it to your environment and redeploy."
            )

        # Do NOT pass unknown kwargs (like proxies) to OpenAI(...)
        _client = OpenAI(api_key=api_key, base_url=base_url, organization=org)
    return _client

def chat(model: str, messages: List[Dict[str, Any]], temperature: float = 0.2, max_tokens: int = 600) -> str:
    client = _get_client()
    resp = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    return (resp.choices[0].message.content or "").strip()
