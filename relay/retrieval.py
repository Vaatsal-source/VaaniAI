"""Retrieval settings: bm25 | dense | dense_rerank, over chunks of configurable size.
CPU-heavy work is run via run_in_executor so it never blocks the event loop (and is logged
as 'working' time by the pipeline).

Table-row chunks (ingest v2) never compete with prose chunks for the top-k slots. After the normal top-k is
chosen, up to `table_extra` table chunks that sit on the same page as a retrieved chunk are added, best
query match first, because a table's numbers live on the same page as the text that discusses it.
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
STOP = set("a an the of in on and or to is are was were what which how does do did for with by as at from that this it its be used use paper papers".split())
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
    def __init__(self, chunk_chars=1200, overlap=200, top_k=5, mode="bm25", rerank_pool=20, ingest="v1",
                 table_extra=1, table_cover=0.4):
        self.ingest, self.table_extra, self.table_cover = ingest, table_extra, table_cover
        everything = load_chunks(chunk_chars, overlap, ingest)
        # v1 deleted reference chunks before indexing. v2 keeps them in the BM25 corpus (so word statistics do not
        # shift when references are removed) but masks them out of every result list.
        loaded = [c for c in everything if ingest != "v1" or not c.get("is_ref")]
        self.chunks = [c for c in loaded if c.get("kind") != "table"]      # prose chunks: what top-k ranks
        self.ref_mask = np.array([bool(c.get("is_ref")) for c in self.chunks])
        self.tables = [c for c in loaded if c.get("kind") == "table"]      # table rows: attached by page
        self.by_id = {c["id"]: c for c in loaded if not c.get("is_ref")}
        self.top_k, self.mode, self.rerank_pool = top_k, mode, rerank_pool
        self.bm25 = BM25Okapi([tokenize(c["text"]) for c in self.chunks])
        self.bm25_t = BM25Okapi([tokenize(c["text"]) for c in self.tables]) if self.tables else None
        self.emb = None
        if mode != "bm25":
            tag = "" if ingest == "v1" else f"{ingest}_"
            cache = ROOT / "data" / f"emb_{tag}{chunk_chars}_{overlap}.npy"
            sig = ROOT / "data" / f"emb_{tag}{chunk_chars}_{overlap}.sig"
            h = hashlib.sha1("".join(c["id"] + c["text"][:50] for c in self.chunks).encode()).hexdigest()
            if cache.exists() and sig.exists() and sig.read_text() == h:
                self.emb = np.load(cache)
            else:
                self.emb = _embedder().encode([c["text"] for c in self.chunks], normalize_embeddings=True,
                                              batch_size=32, show_progress_bar=False)
                np.save(cache, self.emb); sig.write_text(h)

    def _tables_for(self, query: str, picked, paper, extra: int):
        """Table chunks on the same (paper, page) as the picked chunks, best BM25 match to the query first."""
        if not self.tables or extra <= 0:
            return []
        pages = {(c["paper"], p) for c, _ in picked for p in c["pages"]}
        sc = self.bm25_t.get_scores(tokenize(query))
        qt = {t for t in tokenize(query) if t not in STOP and len(t) > 1}

        def covers(t):    # a table that shares fewer than table_cover of the question's content words is unlikely to hold the answer
            return not qt or sum(w in set(tokenize(t["text"])) for w in qt) / len(qt) >= self.table_cover
        cand = [(float(sc[i]), t) for i, t in enumerate(self.tables)
                if (paper is None or t["paper"] == paper) and any((t["paper"], p) in pages for p in t["pages"]) and covers(t)]
        cand.sort(key=lambda x: -x[0])
        return [(t, s) for s, t in cand[:extra]]

    def _search_sync(self, query: str, paper: str | None = None, k: int | None = None, table_extra: int | None = None):
        k = k or self.top_k
        mask = np.array([paper is None or c["paper"] == paper for c in self.chunks]) & ~self.ref_mask
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
        picked = [(self.chunks[i], float(s)) for i, s in zip(idx, sc_out)]
        extra = self.table_extra if table_extra is None else table_extra
        return picked + self._tables_for(query, picked, paper, extra)

    async def search(self, query: str, paper: str | None = None, k: int | None = None, table_extra: int | None = None):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._search_sync, query, paper, k, table_extra)

    def get(self, chunk_id):
        return self.by_id.get(chunk_id)
