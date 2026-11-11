"""Per-setting quality / tokens / TTFT computed from eval logs. Usage: summarize_quality.py tag..."""
import json, sys, pathlib, numpy as np
R = pathlib.Path(__file__).resolve().parent.parent / "logs"
print("| tag | n | quality % | confident-wrong | declined | tokens/q (mean) | provider TTFT p50 ms (draft) | user TTFT p50 ms | total p50 ms |")
print("|---|---|---|---|---|---|---|---|---|")
for tag in sys.argv[1:]:
    res = json.load(open(R / f"eval_{tag}_results.json"))
    ev = [json.loads(l) for l in open(R / f"eval_{tag}.jsonl")]
    tok = {}; dttft = []; first = {}; arr = {}
    for e in ev:
        if e["event"] == "last_token": tok[e["req"]] = tok.get(e["req"], 0) + e["prompt_tokens"] + e["completion_tokens"]
        if e["event"] == "first_token" and e["step"] == "draft": dttft.append(e["ttft_ms"])
        if e["event"] == "enqueue": arr[e["req"]] = e["t"]
        if e["event"] == "user_first_token": first[e["req"]] = e["t"]
    ut = [(first[r] - arr[r]) * 1000 for r in first if r in arr]
    n = len(res)
    print(f"| {tag} | {n} | {100*sum(r['score'] for r in res)/n:.1f} | {sum(r['confident_wrong'] for r in res)} | "
          f"{sum(r['status']=='declined' for r in res)} | {np.mean(list(tok.values())):.0f} | {np.median(dttft):.1f} | "
          f"{np.median(ut):.1f} | {np.median([r['ms'] for r in res]):.1f} |")
    for r in res:
        if r["score"] < 1: print(f"|  ↳ {r['id']} score={r['score']} status={r['status']} | | | | | | | |")
