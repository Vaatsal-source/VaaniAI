"""Retrieval-only comparison (no LLM calls). For every answerable question in both frozen sets:
hit = a retrieved chunk is from a gold paper AND overlaps a gold page (+-1).  Also records the context
size (chars sent to the drafter) and local search latency. Writes logs/retrieval_hit.json."""
import asyncio, json, pathlib, sys, time
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from relay.retrieval import Retriever
from relay.pipeline import detect_papers

ROOT = pathlib.Path(__file__).resolve().parent.parent
SETTINGS = {
    "A bm25 1200/200 k5": dict(mode="bm25", chunk_chars=1200, overlap=200, top_k=5),
    "B dense 1200/200 k5": dict(mode="dense", chunk_chars=1200, overlap=200, top_k=5),
    "C dense+rerank 1200/200 k5": dict(mode="dense_rerank", chunk_chars=1200, overlap=200, top_k=5),
    "D bm25 600/100 k8": dict(mode="bm25", chunk_chars=600, overlap=100, top_k=8),
    "E bm25 2400/300 k3": dict(mode="bm25", chunk_chars=2400, overlap=300, top_k=3),
    "F bm25 1200/200 k3 (degraded)": dict(mode="bm25", chunk_chars=1200, overlap=200, top_k=3),
}


async def main():
    qs = [q for f in ("questions", "questions_hard") for q in json.load(open(ROOT / "data" / f"{f}.json"))
          if q["type"] != "unanswerable"]
    out = {}
    only = sys.argv[1:]
    for name, s in SETTINGS.items():
        if only and name[0] not in only:
            continue
        r = Retriever(s["chunk_chars"], s["overlap"], s["top_k"], s["mode"])
        await r.search("warm up")                       # load models outside the timed region
        hits, ctx, lat, per = 0, [], [], {}
        for q in qs:
            papers = detect_papers(q["q"]) or [None]
            per_k = max(1, -(-s["top_k"] // len(papers)))
            t = time.perf_counter(); got = []
            for p in papers:
                got += [c for c, _ in await r.search(q["q"], p, per_k)]
            lat.append((time.perf_counter() - t) * 1000)
            got = got[:max(s["top_k"], len(papers))]
            ok = any(c["paper"] in q["paper"] and any(abs(p - g) <= 1 for p in c["pages"] for g in q["pages"]) for c in got)
            hits += ok; per[q["id"]] = ok; ctx.append(sum(len(c["text"]) for c in got))
        out[name] = {"n": len(qs), "hit_pct": round(100 * hits / len(qs), 1), "mean_ctx_chars": round(float(np.mean(ctx))),
                     "search_ms_p50": round(float(np.percentile(lat, 50)), 1), "search_ms_p95": round(float(np.percentile(lat, 95)), 1),
                     "misses": [k for k, v in per.items() if not v]}
        print(name, out[name])
    (ROOT / "logs" / ("retrieval_hit_" + "".join(only or ["ALL"]) + ".json")).write_text(json.dumps(out, indent=1))

asyncio.run(main())
