# vectorstore.py
from __future__ import annotations
import os, json, pickle, numpy as np
from typing import List, Tuple, Dict

try:
    import faiss  # type: ignore
    _HAS_FAISS = True
except Exception:
    _HAS_FAISS = False

class SimpleFAISS:
    def __init__(self, dim: int = 384):
        self.dim = dim
        self.docs: List[Dict] = []
        self.embs: np.ndarray | None = None
        self.index = faiss.IndexFlatIP(dim) if _HAS_FAISS else None

    @staticmethod
    def _embed(texts: List[str]) -> np.ndarray:
        # lightweight local bag-of-words-ish embedding to avoid external calls
        # (Replace with real embeddings if desired.)
        vecs = []
        for t in texts:
            rng = np.random.default_rng(abs(hash(t)) % (2**32))
            v = rng.normal(size=384).astype("float32")
            v /= (np.linalg.norm(v) + 1e-6)
            vecs.append(v)
        return np.vstack(vecs)

    def add(self, docs: List[Dict]):
        texts = [d["text"] for d in docs]
        embs = self._embed(texts)
        if self.embs is None: self.embs = embs
        else: self.embs = np.vstack([self.embs, embs])
        base = len(self.docs)
        self.docs.extend(docs)
        if self.index is not None:
            self.index.add(embs)

    def search(self, query: str, k: int = 4) -> List[Tuple[float, Dict]]:
        if not self.docs:
            return []
        q = self._embed([query])
        if self.index is not None:
            scores, idx = self.index.search(q, min(k, len(self.docs)))
            return [(float(scores[0][i]), self.docs[int(idx[0][i])]) for i in range(scores.shape[1])]
        # NumPy cosine
        X = self.embs
        sims = (X @ q[0]) / (np.linalg.norm(X, axis=1) * np.linalg.norm(q[0]) + 1e-6)
        top = np.argsort(-sims)[:k]
        return [(float(sims[i]), self.docs[i]) for i in top]

    def save(self, name: str):
        os.makedirs("./", exist_ok=True)
        with open(f"{name}.docs.pkl", "wb") as f: pickle.dump(self.docs, f)
        if self.index is not None:
            faiss.write_index(self.index, f"{name}.faiss")
        else:
            with open(f"{name}.npy", "wb") as f: np.save(f, self.embs if self.embs is not None else np.zeros((0,self.dim),dtype="float32"))

    @classmethod
    def load(cls, name: str):
        obj = cls()
        try:
            with open(f"{name}.docs.pkl", "rb") as f: obj.docs = pickle.load(f)
        except Exception:
            obj.docs = []
        try:
            if _HAS_FAISS and os.path.exists(f"{name}.faiss"):
                obj.index = faiss.read_index(f"{name}.faiss")
            elif os.path.exists(f"{name}.npy"):
                obj.embs = np.load(f"{name}.npy").astype("float32")
        except Exception:
            pass
        return obj
