"""Retrieval settings: bm25 | dense | dense_rerank, over chunks of configurable size.
CPU-heavy work is run via run_in_executor so it never blocks the event loop (and is logged
as 'working' time by the pipeline).
"""
import asyncio
import hashlib
import pathlib
import re

import numpy as np
from rank_bm25 import BM25Okapi

from .ingest import load_chunks

ROOT = pathlib.Path(__file__).resolve().parent.parent
EMB_MODEL = "BAAI/bge-small-en-v1.5"
RERANK_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
_tok = re.compile(r"[a-z0-9]+")
_models = {}


def tokenize(t):
    return _tok.findall(t.lower())


def _embedder():
    if "emb" not in _models:
        from sentence_transformers import SentenceTransformer
        _models["emb"] = SentenceTransformer(EMB_MODEL, device="cpu")
    return _models["emb"]


def _reranker():
    if "rr" not in _models:
        from sentence_transformers import CrossEncoder
        _models["rr"] = CrossEncoder(RERANK_MODEL, device="cpu")
    return _models["rr"]


class Retriever:
    def __init__(self, chunk_chars=1200, overlap=200, top_k=5, mode="bm25", rerank_pool=20):
        self.chunks = [c for c in load_chunks(chunk_chars, overlap) if not c.get("is_ref")]
        self.by_id = {c["id"]: c for c in self.chunks}
        self.top_k, self.mode, self.rerank_pool = top_k, mode, rerank_pool
        self.bm25 = BM25Okapi([tokenize(c["text"]) for c in self.chunks])
        self.emb = None
        if mode != "bm25":
            cache = ROOT / "data" / f"emb_{chunk_chars}_{overlap}.npy"
            sig = ROOT / "data" / f"emb_{chunk_chars}_{overlap}.sig"
            h = hashlib.sha1("".join(c["id"] + c["text"][:50] for c in self.chunks).encode()).hexdigest()
            if cache.exists() and sig.exists() and sig.read_text() == h:
                self.emb = np.load(cache)
            else:
                self.emb = _embedder().encode([c["text"] for c in self.chunks], normalize_embeddings=True,
                                              batch_size=32, show_progress_bar=False)
                np.save(cache, self.emb); sig.write_text(h)

    def _search_sync(self, query: str, paper: str | None = None, k: int | None = None):
        k = k or self.top_k
        n = len(self.chunks)
        mask = np.array([paper is None or c["paper"] == paper for c in self.chunks])
        if self.mode == "bm25":
            sc = np.array(self.bm25.get_scores(tokenize(query)))
        else:
            q = _embedder().encode([query], normalize_embeddings=True)[0]
            sc = self.emb @ q
        sc = np.where(mask, sc, -1e9)
        pool = self.rerank_pool if self.mode == "dense_rerank" else k
        idx = np.argsort(-sc)[:pool]
        if self.mode == "dense_rerank":
            pairs = [(query, self.chunks[i]["text"]) for i in idx]
            rr = _reranker().predict(pairs)
            order = np.argsort(-rr)[:k]
            idx, sc_out = idx[order], rr[order]
        else:
            sc_out = sc[idx]
        # confidence: normalised top score margin (used for the "verify only sometimes" branch)
        return [(self.chunks[i], float(s)) for i, s in zip(idx, sc_out)]

    async def search(self, query: str, paper: str | None = None, k: int | None = None):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._search_sync, query, paper, k)

    def get(self, chunk_id):
        return self.by_id.get(chunk_id)
