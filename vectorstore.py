"""
vectorstore.py
- Prefers FAISS for similarity search if installed.
- Falls back to pure-NumPy cosine similarity when FAISS isn't available.
- Lazy-creates the OpenAI client so import-time errors don't crash the app.
"""

from __future__ import annotations
import os, json
from typing import List, Dict, Tuple, Optional

import numpy as np
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

# ---- Config (env-tunable) ----
VECTOR_DB_DIR = os.getenv("VECTOR_DB_DIR", "./vector_db")
EMBED_MODEL = os.getenv("OPENAI_MODEL_EMBEDDING", "text-embedding-3-small")  # 1536-dim
os.makedirs(VECTOR_DB_DIR, exist_ok=True)

# ---- Optional FAISS import ----
_USE_FAISS = True
try:
    import faiss  # type: ignore
except Exception:
    _USE_FAISS = False
    faiss = None  # noqa: F401


# ---- OpenAI client (lazy) ----
def _get_client() -> OpenAI:
    # Let the SDK read OPENAI_API_KEY from the environment.
    return OpenAI()


def _embed_texts(texts: List[str], model: str = EMBED_MODEL) -> np.ndarray:
    """
    Returns (N, D) float32 embeddings. Trims empty strings to avoid API errors.
    """
    cleaned = [t if (t and t.strip()) else " " for t in texts]
    client = _get_client()
    resp = client.embeddings.create(model=model, input=cleaned)
    vecs = np.array([d.embedding for d in resp.data], dtype="float32")
    return vecs


def _normalize(mat: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(mat, axis=1, keepdims=True) + 1e-12
    return mat / norms


class SimpleFAISS:
    """
    Minimal vector store with a FAISS backend (if available) or NumPy fallback.

    Docs format: Dict with keys:
      - "id": str
      - "text": str
      - "metadata": Dict[str, Any]
    """
    def __init__(self, dim: int = 1536):
        self.dim = dim
        self.docs: List[Dict] = []
        self._embs: Optional[np.ndarray] = None  # used for NumPy mode

        if _USE_FAISS:
            # Inner Product with normalized vectors = cosine similarity
            self.index = faiss.IndexFlatIP(dim)
        else:
            self.index = None  # NumPy mode

    # ---------- Core ops ----------
    def add(self, docs: List[Dict]) -> None:
        if not docs:
            return
        texts = [d["text"] for d in docs]
        embs = _normalize(_embed_texts(texts))

        if _USE_FAISS:
            if len(self.docs) == 0:
                # Ensure FAISS index dimension matches embeddings
                self.index = faiss.IndexFlatIP(embs.shape[1])
                self.dim = embs.shape[1]
            self.index.add(embs)
        else:
            if self._embs is None:
                self._embs = embs
            else:
                self._embs = np.vstack([self._embs, embs])

        self.docs.extend(docs)

    def search(self, query: str, k: int = 5) -> List[Tuple[float, Dict]]:
        if len(self.docs) == 0:
            return []
        qv = _normalize(_embed_texts([query]))
        k = min(k, len(self.docs))

        if _USE_FAISS:
            scores, idxs = self.index.search(qv, k)
            out: List[Tuple[float, Dict]] = []
            for s, i in zip(scores[0], idxs[0]):
                if int(i) == -1:
                    continue
                out.append((float(s), self.docs[int(i)]))
            return out
        else:
            sims = (self._embs @ qv.T).ravel()  # (N,)
            order = np.argsort(-sims)[:k]
            return [(float(sims[i]), self.docs[int(i)]) for i in order]

    # ---------- Persistence ----------
    def save(self, name: str) -> None:
        if len(self.docs) == 0:
            return
        base = os.path.join(VECTOR_DB_DIR, name)

        # Save docs json
        with open(base + ".json", "w") as f:
            json.dump(self.docs, f)

        # Save index
        if _USE_FAISS and self.index is not None:
            faiss.write_index(self.index, base + ".faiss")
        else:
            if self._embs is not None:
                np.save(base + ".npy", self._embs)

    @classmethod
    def load(cls, name: str) -> "SimpleFAISS":
        store = cls()
        base = os.path.join(VECTOR_DB_DIR, name)
        json_path = base + ".json"
        faiss_path = base + ".faiss"
        npy_path = base + ".npy"

        # Load docs
        if os.path.exists(json_path):
            with open(json_path, "r") as f:
                store.docs = json.load(f)

        # Load index
        if _USE_FAISS and os.path.exists(faiss_path):
            store.index = faiss.read_index(faiss_path)
            store.dim = store.index.d
        elif (not _USE_FAISS) and os.path.exists(npy_path):
            arr = np.load(npy_path)
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            store._embs = arr.astype("float32")
            store.dim = store._embs.shape[1]

        return store
