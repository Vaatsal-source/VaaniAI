"""Quality regression guard. Two modes.

FREE mode (default, no model calls, safe for CI): runs retrieval exactly as the pipeline does for every answerable
question in the frozen sets and checks two numbers against data/quality_baseline.json:
    hit      % of questions where a retrieved chunk is from a gold paper and overlaps a gold page (+-1)
    has_ans  % of questions where every fact pattern of the question appears in the retrieved context
A change that makes either number fall by more than the tolerance (default 1 question = 2.4 points) fails.

  python scripts/check_quality.py                 # compare with the baseline
  python scripts/check_quality.py --update        # accept the current numbers as the new baseline

RESULTS mode: compares a real evaluation run (logs/eval_<tag>_results.json from scripts/run_eval.py) with the
baseline for that question set; fails if the score is lower than the baseline minus the tolerance.

  python scripts/check_quality.py --results logs/eval_r2_hard2_v2_20B_run1_results.json --set hard2
"""
import argparse, asyncio, json, pathlib, re, sys
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from relay.pipeline import detect_papers
from relay.retrieval import Retriever
from relay.runtime import load_cfg

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASE = ROOT / "data" / "quality_baseline.json"
SETS = {"original": ["questions", "questions_hard"], "hard2": ["questions_hard2"]}


def questions(files):
    return [q for f in files for q in json.load(open(ROOT / "data" / f"{f}.json", encoding="utf-8")) if q["type"] != "unanswerable"]


async def free_metrics():
    cfg = load_cfg()
    r = cfg["retrieval"]
    ret = Retriever(r["chunk_chars"], r["overlap_chars"], r["top_k"], "bm25", ingest=cfg["ingest"]["version"])
    k = r["top_k"]
    out = {}
    for name, files in SETS.items():
        qs = questions(files)
        hit = has = 0
        for q in qs:
            papers = detect_papers(q["q"]) or [None]
            per = max(1, -(-k // len(papers)))
            got = []
            for p in papers:
                got += [c for c, _ in await ret.search(q["q"], p, per)]
            prose = [c for c in got if c.get("kind") != "table"][:max(k, len(papers))]
            tabs = [c for c in got if c.get("kind") == "table"][:ret.table_extra]
            got = prose + tabs
            hit += any(c["paper"] in q["paper"] and any(abs(p - g) <= 1 for p in c["pages"] for g in q["pages"]) for c in got)
            text = " ".join(c["text"] for c in got)
            has += all(any(re.search(p, text, re.I) for p in grp) for grp in q["must"])
        out[name] = {"n": len(qs), "hit_pct": round(100 * hit / len(qs), 1), "has_answer_pct": round(100 * has / len(qs), 1)}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--tol", type=float, default=2.5, help="allowed drop, in percentage points")
    ap.add_argument("--results"); ap.add_argument("--set", choices=list(SETS) + ["hard2"], default="hard2")
    a = ap.parse_args()
    base = json.loads(BASE.read_text(encoding="utf-8")) if BASE.exists() else {}
    if a.results:
        res = json.load(open(a.results, encoding="utf-8"))
        if any(r.get("aborted") for r in res):
            sys.exit("run was aborted (daily quota): not a valid run")
        score = round(100 * sum(r["score"] for r in res) / len(res), 1)
        floor = base.get("real", {}).get(a.set)
        print(f"score {score}% on {len(res)} questions; baseline {floor}")
        if floor is not None and score < floor - 100 / len(res) - 1e-9:     # more than one question worse
            sys.exit(f"FAIL: {score}% is more than one question below the baseline {floor}%")
        print("ok"); return
    now = asyncio.run(free_metrics())
    if a.update:
        base["retrieval"] = now
        base["note"] = "retrieval-only guard; produced by scripts/check_quality.py --update"
        BASE.write_text(json.dumps(base, indent=1), encoding="utf-8")
        print("baseline written:", json.dumps(now)); return
    bad = []
    for name, cur in now.items():
        old = base.get("retrieval", {}).get(name)
        print(f"{name:10s} hit {cur['hit_pct']}% (baseline {old and old['hit_pct']})  has_answer {cur['has_answer_pct']}% (baseline {old and old['has_answer_pct']})")
        if old:
            for key in ("hit_pct", "has_answer_pct"):
                if cur[key] < old[key] - a.tol:
                    bad.append(f"{name}.{key}: {cur[key]} < {old[key]} - {a.tol}")
    if bad:
        sys.exit("FAIL: " + "; ".join(bad))
    print("ok")


if __name__ == "__main__":
    main()
