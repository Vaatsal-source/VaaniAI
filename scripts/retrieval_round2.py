"""Retrieval-only comparison for round 2 (no model calls, no quota). Writes logs/retrieval_round2.json.

For every answerable question in a set it records
  hit      : a retrieved chunk is from a gold paper and overlaps a gold page (+-1)
  has_ans  : every `must` group of the question matches the retrieved text, i.e. the facts needed to answer
             are actually in the context the drafter will see (a free stand-in for answer quality)
  ctx      : characters sent to the drafter
  search   : local search time (ms)

  python scripts/retrieval_round2.py            # all settings, all question sets
"""
import asyncio, json, pathlib, re, sys, time
import numpy as np
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from relay.retrieval import Retriever
from relay.pipeline import Pipeline, detect_papers

ROOT = pathlib.Path(__file__).resolve().parent.parent
SETS = {"original 29 (easy 20 + hard 9)": ["questions", "questions_hard"], "new hard 25": ["questions_hard2"]}
SETTINGS = {
    "v1 k5 (round 1)": dict(chunk_chars=1200, overlap=200, top_k=5, ingest="v1", trim=0, table_extra=0),
    "v1 k4": dict(chunk_chars=1200, overlap=200, top_k=4, ingest="v1", trim=0, table_extra=0),
    "v2 k5 no table rows": dict(chunk_chars=1200, overlap=200, top_k=5, ingest="v2", trim=0, table_extra=0),
    "v2 k5 + table rows": dict(chunk_chars=1200, overlap=200, top_k=5, ingest="v2", trim=0, table_extra=2),
    "v2 k5 + 1 table row, no relevance gate": dict(chunk_chars=1200, overlap=200, top_k=5, ingest="v2", trim=0, table_extra=1, cover=0.0),
    "v2 k5 + 1 table row, gated (chosen)": dict(chunk_chars=1200, overlap=200, top_k=5, ingest="v2", trim=0, table_extra=1),
    "v2 k4 + table rows": dict(chunk_chars=1200, overlap=200, top_k=4, ingest="v2", trim=0, table_extra=2),
    "v2 k3 + table rows": dict(chunk_chars=1200, overlap=200, top_k=3, ingest="v2", trim=0, table_extra=2),
    "v2 k5 + tables, trim 800": dict(chunk_chars=1200, overlap=200, top_k=5, ingest="v2", trim=800, table_extra=2),
    "v2 k5 + tables, trim 600": dict(chunk_chars=1200, overlap=200, top_k=5, ingest="v2", trim=600, table_extra=2),
    "v2 k4 + tables, trim 800": dict(chunk_chars=1200, overlap=200, top_k=4, ingest="v2", trim=800, table_extra=2),
    "v2 k4 + tables, trim 600": dict(chunk_chars=1200, overlap=200, top_k=4, ingest="v2", trim=600, table_extra=2),
}


def load(files):
    return [q for f in files for q in json.load(open(ROOT / "data" / f"{f}.json", encoding="utf-8")) if q["type"] != "unanswerable"]


async def main():
    out = {}
    for name, s in SETTINGS.items():
        if len(sys.argv) > 1 and not any(a in name for a in sys.argv[1:]):
            continue
        r = Retriever(s["chunk_chars"], s["overlap"], s["top_k"], "bm25", ingest=s["ingest"], table_extra=s["table_extra"], table_cover=s.get("cover", 0.4))
        await r.search("warm up")
        out[name] = {}
        for setname, files in SETS.items():
            qs = load(files)
            hits = has = 0; ctx = []; lat = []; miss = []; noans = []
            for q in qs:
                papers = detect_papers(q["q"]) or [None]
                per_k = max(1, -(-s["top_k"] // len(papers)))
                t = time.perf_counter(); got = []
                for p in papers:
                    got += [c for c, _ in await r.search(q["q"], p, per_k)]
                lat.append((time.perf_counter() - t) * 1000)
                prose = [c for c in got if c.get("kind") != "table"][:max(s["top_k"], len(papers))]
                tabs = [c for c in got if c.get("kind") == "table"][:s["table_extra"]]
                got = prose + tabs
                ok = any(c["paper"] in q["paper"] and any(abs(p - g) <= 1 for p in c["pages"] for g in q["pages"]) for c in got)
                text = " ".join(Pipeline.trim_context(c["text"], q["q"], s["trim"]) for c in got)
                ans = all(any(re.search(p, text, re.I) for p in grp) for grp in q["must"])
                hits += ok; has += ans; ctx.append(len(text))
                if not ok: miss.append(q["id"])
                if not ans: noans.append(q["id"])
            out[name][setname] = {"n": len(qs), "hit_pct": round(100 * hits / len(qs), 1), "has_answer_pct": round(100 * has / len(qs), 1),
                                  "mean_ctx_chars": round(float(np.mean(ctx))), "search_ms_p50": round(float(np.percentile(lat, 50)), 1),
                                  "missed_page": miss, "answer_not_in_context": noans}
            print(name, "|", setname, out[name][setname], flush=True)
    (ROOT / "logs" / ("retrieval_round2.json" if len(sys.argv) == 1 else "retrieval_round2_partial.json")).write_text(json.dumps(out, indent=1), encoding="utf-8")


asyncio.run(main())
