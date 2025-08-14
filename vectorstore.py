import os
import numpy as np
import faiss
from typing import List, Dict, Tuple
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()
_OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
_VECTOR_DB_DIR = os.getenv("VECTOR_DB_DIR", "./vector_db")
os.makedirs(_VECTOR_DB_DIR, exist_ok=True)

_CLIENT = OpenAI(api_key=_OPENAI_API_KEY)

def _embed_texts(texts: List[str], model: str = "text-embedding-3-small") -> np.ndarray:
    """
    Returns (N, D) float32 embeddings.
    """
    # OpenAI API can embed up to ~8192 tokens per text; our chunks are small.
    resp = _CLIENT.embeddings.create(model=model, input=texts)
    vecs = np.array([d.embedding for d in resp.data], dtype="float32")
    return vecs

class SimpleFAISS:
    """
    Minimal FAISS wrapper (in-memory), plus save/load.
    """
    def __init__(self, dim: int = 1536):
        self.dim = dim
        self.docs: List[Dict] = []
        self.index = faiss.IndexFlatIP(dim)  # cosine via normalized vectors

    @staticmethod
    def _normalize(v: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(v, axis=1, keepdims=True) + 1e-12
        return v / norms

    def add(self, docs: List[Dict]):
        texts = [d["text"] for d in docs]
        embs = _embed_texts(texts)
        embs = self._normalize(embs)
        if len(self.docs) == 0:
            self.index = faiss.IndexFlatIP(embs.shape[1])
        self.index.add(embs)
        self.docs.extend(docs)

    def search(self, query: str, k: int = 5) -> List[Tuple[float, Dict]]:
        qv = _embed_texts([query])
        qv = self._normalize(qv)
        scores, idx = self.index.search(qv, min(k, len(self.docs) or 1))
        results = []
        for score, i in zip(scores[0], idx[0]):
            if i == -1:  # no results
                continue
            results.append((float(score), self.docs[i]))
        return results

    def save(self, name: str):
        """
        Saves index + docs to disk.
        """
        if len(self.docs) == 0:
            return
        path_base = os.path.join(_VECTOR_DB_DIR, name)
        faiss.write_index(self.index, path_base + ".faiss")
        import json
        with open(path_base + ".json", "w") as f:
            json.dump(self.docs, f)

    @classmethod
    def load(cls, name: str):
        """
        Loads index + docs; returns empty store if not found.
        """
        store = cls()
        path_base = os.path.join(_VECTOR_DB_DIR, name)
        faiss_path = path_base + ".faiss"
        json_path = path_base + ".json"
        if os.path.exists(faiss_path) and os.path.exists(json_path):
            store.index = faiss.read_index(faiss_path)
            import json
            with open(json_path, "r") as f:
                store.docs = json.load(f)
            # backfill dim from index
            store.dim = store.index.d
        return store
