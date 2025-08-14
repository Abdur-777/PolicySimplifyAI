# llm_client.py
from __future__ import annotations
import os
from typing import Dict, Any
from dotenv import load_dotenv
from openai import OpenAI, AzureOpenAI

load_dotenv()
_PROVIDER = os.getenv("LLM_PROVIDER", "openai").lower()
_OPENAI_MODEL = os.getenv("OPENAI_MODEL_CHAT", "gpt-4o-mini")
_AZURE_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT")
_AZURE_KEY = os.getenv("AZURE_OPENAI_API_KEY")
_AZURE_DEPLOYMENT = os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o-mini")

def chat(model: str | None, messages: list[Dict[str, Any]], temperature: float = 0.2) -> str:
    if _PROVIDER == "azure":
        client = AzureOpenAI(api_key=_AZURE_KEY, api_version="2024-05-01-preview", azure_endpoint=_AZURE_ENDPOINT)
        resp = client.chat.completions.create(model=_AZURE_DEPLOYMENT, messages=messages, temperature=temperature)
    else:
        client = OpenAI()
        resp = client.chat.completions.create(model=model or _OPENAI_MODEL, messages=messages, temperature=temperature)
    return resp.choices[0].message.content.strip()
