"""Score the 20 frozen questions (data/RUBRIC.md). Usage:
  python scripts/run_eval.py --provider groq|standin --mode bm25 --chunk 1200 --overlap 200 --k 5 --tag NAME
Writes logs/eval_<tag>.jsonl (events) and logs/eval_<tag>_results.json (per-question scores).
Sequential by default (paced to respect real-service limits)."""
import argparse, asyncio, json, pathlib, re, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from relay.runtime import build, load_cfg, ROOT
from relay.pipeline import ABSTAIN, CITE


def score(q, res):
    txt = res["text"]; low = txt.lower().replace("’", "'")
    cites = res["citations"]
    if q["type"] == "unanswerable":
        ok = ABSTAIN in low and not any(re.search(p, txt, re.I) for p in q["forbid"])
        confident_wrong = (ABSTAIN not in low) and res["status"] in ("answered",)
        return (1.0 if ok else 0.0), confident_wrong
    if res["status"] != "answered" or ABSTAIN in low:
        return 0.0, False
    facts = all(any(re.search(p, txt, re.I) for p in grp) for grp in q["must"])
    if not facts:
        return 0.0, False
    cite_ok = any(c["paper"] in q["paper"] and any(abs(p - g) <= 1 for p in c["pages"] for g in q["pages"]) for c in cites)
    return (1.0 if cite_ok else 0.5), False


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", default="groq"); ap.add_argument("--mode", default="bm25")
    ap.add_argument("--chunk", type=int, default=1200); ap.add_argument("--overlap", type=int, default=200)
    ap.add_argument("--k", type=int, default=5); ap.add_argument("--tag", required=True); ap.add_argument("--questions", default="questions"); ap.add_argument("--large", default=None)
    ap.add_argument("--ingest", default=None, help="v1 = round-1 chunker, v2 = fixed (default: config)"); ap.add_argument("--ctx_trim", type=int, default=None)
    ap.add_argument("--small", default=None, help="override the small model (for example when the whole run goes to another provider)")
    ap.add_argument("--cfg", default="{}", help="JSON deep-merged into the config (for example a larger retry budget for a slow provider)")
    ap.add_argument("--ids", default=None, help="comma-separated question ids to run (repeat runs of a subset)")
    ap.add_argument("--gap", type=float, default=0.0, help="seconds between questions")
    ap.add_argument("--deadline", type=float, default=300, help="per-question deadline; long so quality runs queue instead of shedding")
    a = ap.parse_args()
    cfg = load_cfg()
    from relay.runtime import deep_update
    deep_update(cfg, json.loads(a.cfg))
    if a.large:
        cfg["models"]["large"] = a.large
    if a.small:
        cfg["models"]["small"] = a.small
    if a.provider == "gemini":      # the whole run goes to Gemini: its own limits, its own request options
        cfg["limits"].update(cfg["fallback"]["limits"])
    logp = ROOT / "logs" / f"eval_{a.tag}.jsonl"
    logp.write_text("")
    pipe, log = build(cfg, a.provider, str(logp), dict({"mode": a.mode, "chunk_chars": a.chunk, "overlap_chars": a.overlap, "top_k": a.k}, **({"ingest": a.ingest} if a.ingest else {}), **({"ctx_trim_chars": a.ctx_trim} if a.ctx_trim is not None else {})))
    qs = json.load(open(ROOT / "data" / f"{a.questions}.json"))
    if a.ids:
        qs = [q for q in qs if q["id"] in a.ids.split(",")]
    out = []
    for q in qs:
        t0 = time.perf_counter()
        res = await pipe.handle(q["id"], q["q"], a.deadline)
        s, bad = score(q, res)
        out.append({"id": q["id"], "type": q["type"], "score": s, "confident_wrong": bad, "status": res["status"],
                    "ms": round((time.perf_counter() - t0) * 1000, 1), "text": res["text"]})
        print(q["id"], res["status"], s, f'{out[-1]["ms"]:.0f}ms', flush=True)
        if res["status"] in ("extractive_daily", "shed"):
            # the daily quota is gone: every later answer would be a fallback, which would make the run meaningless
            print("ABORT: daily budget reached; this run is invalid (do not report it)"); out[-1]["aborted"] = True
            break
        if a.gap: await asyncio.sleep(a.gap)
    (ROOT / "logs" / f"eval_{a.tag}_results.json").write_text(json.dumps(out, indent=1))
    print("quality %.1f%%" % (100 * sum(o["score"] for o in out) / len(out)))
    await pipe.llm.aclose(); log.close()

asyncio.run(main())
