"""Regenerate every table/figure in the write-up from raw logs:  python scripts/make_tables.py
Outputs results/tables.md, results/fig_*.png.  Nothing here is hand-typed."""
import glob, json, pathlib, sys
import numpy as np, pandas as pd
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import analyze as A

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
OUT = ROOT / "results"; OUT.mkdir(exist_ok=True)
md = []


def h(t): md.append(f"\n### {t}\n")
def tbl(df, **k): md.append(df.to_markdown(**k) + "\n")
def p(x, q): return "not measured" if len(x.dropna()) == 0 else f"{np.percentile(x.dropna(), q):.1f}"


# ---------------- A. real Groq probe ----------------
h("A. Real Groq probe (logs/groq_probe_1794406507.jsonl; models-404 log: groq_probe_0_model404_*.jsonl)")
rows = [json.loads(l) for l in open(LOGS / "groq_probe_1794406507.jsonl")]
out = []
for tag in ("latency:openai/gpt-oss-20b", "latency:openai/gpt-oss-120b", "conc4", "conc8"):
    ok = pd.DataFrame([r for r in rows if r.get("tag") == tag and r.get("status") == 200])
    out.append({"probe": tag, "n": len(ok), "TTFT p50 ms": p(ok.ttft_ms, 50), "TTFT p95 ms": p(ok.ttft_ms, 95),
                "TTFT max ms": f"{ok.ttft_ms.max():.1f}", "total p50 ms": p(ok.total_ms, 50), "total p95 ms": p(ok.total_ms, 95)})
tbl(pd.DataFrame(out), index=False)
lh = [r for r in rows if r.get("tag") == "limit_hit"]
st = pd.Series([r["status"] for r in lh]).value_counts().to_dict()
first429 = next(i for i, r in enumerate(sorted(lh, key=lambda r: r["t0"])) if r["status"] == 429)
md.append(f"Deliberate burst of {len(lh)} tiny requests (small model): status counts {st}; first 429 was request #{first429 + 1} "
          f"in send order; retry-after header values: {sorted({r['headers'].get('retry-after') for r in lh if r['status'] == 429})}.\n")
md.append("First 429 body (limit kind and numbers appear ONLY here): `" +
          next(r["body"] for r in lh if r["status"] == 429)[:260] + "`\n")

# ---------------- B. load runs ----------------
def run_table(tags, title, base=None):
    h(title)
    cols = {}
    for t in tags:
        if base:
            A.ROOT = base
        try:
            cols[t] = A.table(t)
        finally:
            A.ROOT = ROOT
    tbl(pd.DataFrame(cols))

REAL = ["real_steady", "real_steady2", "real_burst"]
run_table(REAL, "B1. REAL Groq runs (drafting model gpt-oss-20b; N is tiny because of the 8k tokens/min and 200k tokens/day walls)")
run_table(["s_steady_free", "s_burst_free", "s_overload_free"], "B2. STAND-IN, free-tier limits (rpm 30, tpm 8000, rpd 1000, tpd 200000)")
run_table(["s_steady_t10", "s_burst_t10", "s_overload_t10"], "B3. STAND-IN, 10x limits (a bigger plan)")
run_table(["s_daily_known", "s_daily_learned"], "B4. STAND-IN, daily token budget exhausted (tpd 40000): limiter told vs limiter learns from the 429")
run_table(["s_retry_none", "s_retry_budget", "s_retry_unbounded"], "B5. STAND-IN retries at 30% injected failures, 0.4 req/s (80% of capacity)")
run_table(["s_retrysat_none", "s_retrysat_budget", "s_retrysat_unbounded"], "B6. STAND-IN retries at 30% injected failures, 0.55 req/s (110% of capacity)")
before = LOGS / "run1_before_queue_aware"
if before.exists():
    A.LOGSDIR = before
md.append("\n*Pre-fix runs (wait estimate ignored the queue; patience=deadline=25 s) are kept in logs/run1_before_queue_aware/ "
          "and are summarised in the write-up, section 5.*\n")

# retries / tokens in the B6 runs, straight from the server logs
h("B6b. Calls sent and tokens reserved in the retry-saturation runs (from server logs)")
rr = []
for t in ["s_retrysat_none", "s_retrysat_budget", "s_retrysat_unbounded"]:
    ev = [json.loads(l) for l in open(LOGS / f"server_{t}.jsonl")]
    sends = [e for e in ev if e["event"] == "send"]
    rr.append({"run": t, "provider calls sent": len(sends), "retries": sum(e["event"] == "retry" for e in ev),
               "tokens reserved (est)": sum(e["est_tokens"] for e in sends),
               "tokens in successful calls (API usage)": sum(e["prompt_tokens"] + e["completion_tokens"] for e in ev if e["event"] == "last_token")})
tbl(pd.DataFrame(rr), index=False)

# ---------------- C. arrival-rank outcomes in bursts ----------------
h("C. Who gets what in a burst: outcome by arrival order (4 equal groups, earliest arrivals first)")
for t in ["s_burst_free", "s_burst_t10", "real_burst"]:
    df, _ = A.load(t)
    df = df.sort_values("arrive").reset_index(drop=True)
    df["group"] = pd.qcut(df.index, 4, labels=["1st quarter", "2nd", "3rd", "4th (last arrivals)"])
    df["kind"] = df.apply(lambda r: "abandoned" if r.outcome == "abandon" else
                          ("full answer" if r.status in ("answered", "abstained") else str(r.status)), axis=1)
    ct = pd.crosstab(df.group, df.kind)
    md.append(f"**{t}** (n={len(df)})\n")
    tbl(ct)

# ---------------- D. quality / retrieval ----------------
h("D. Answer quality, tokens and provider time-to-first-token per retrieval setting (REAL Groq; rubric: data/RUBRIC.md)")
def qrow(tag, label, model, qset):
    res = json.load(open(LOGS / f"eval_{tag}_results.json"))
    ev = [json.loads(l) for l in open(LOGS / f"eval_{tag}.jsonl")]
    tok = {}; dt = []
    for e in ev:
        if e["event"] == "last_token": tok[e["req"]] = tok.get(e["req"], 0) + e["prompt_tokens"] + e["completion_tokens"]
        if e["event"] == "first_token" and e["step"] == "draft": dt.append(e["ttft_ms"])
    n = len(res)
    return {"setting": label, "drafter": model, "question set": qset, "n": n,
            "quality %": f"{100 * sum(r['score'] for r in res) / n:.1f}",
            "unanswerable question answered": sum(r["confident_wrong"] for r in res),
            "answerable question answered with wrong or missing facts": sum(r["type"] != "unanswerable" and r["status"] == "answered" and r["score"] == 0 for r in res),
            "declined": sum(r["status"] == "declined" for r in res),
            "tokens/answer (API usage, all calls)": f"{np.mean(list(tok.values())):.0f}",
            "provider draft TTFT p50 ms": f"{np.median(dt):.1f}"}
Q = [("q_bm25_1200_k5", "A bm25 1200/200 k5", "gpt-oss-120b", "easy 20"),
     ("r_B_dense_1200_k5_easy", "B dense 1200/200 k5", "gpt-oss-120b", "easy 20"),
     ("r_C_denserr_1200_k5_easy", "C dense+rerank 1200/200 k5", "gpt-oss-120b", "easy 20"),
     ("r_A_bm25_1200_k5_hard", "A bm25 1200/200 k5", "gpt-oss-120b", "hard 9"),
     ("r20_A_bm25_1200_k5_hard", "A bm25 1200/200 k5", "gpt-oss-20b", "hard 9"),
     ("r20_B_dense_1200_k5_hard", "B dense 1200/200 k5", "gpt-oss-20b", "hard 9"),
     ("r20_C_denserr_1200_k5_hard", "C dense+rerank 1200/200 k5", "gpt-oss-20b", "hard 9"),
     ("r20_D_bm25_600_k8_hard", "D bm25 600/100 k8", "gpt-oss-20b", "hard 9"),
     ("r20_E_bm25_2400_k3_hard", "E bm25 2400/300 k3", "gpt-oss-20b", "hard 9")]
tbl(pd.DataFrame([qrow(*q) for q in Q]), index=False)
md.append("Per-question misses (score < 1):\n")
for tag, label, model, qs in Q:
    res = json.load(open(LOGS / f"eval_{tag}_results.json"))
    md.append(f"- {label} / {model} / {qs}: " + (", ".join(f"{r['id']}={r['score']}({r['status']})" for r in res if r["score"] < 1) or "none") + "\n")

h("E. Retrieval only (no model calls): is the gold page among the retrieved chunks? 23 answerable questions (easy+hard)")
rh = {}
for f in glob.glob(str(LOGS / "retrieval_hit_*.json")):
    rh.update(json.load(open(f)))
tbl(pd.DataFrame(rh).T.sort_index().rename(columns={"hit_pct": "gold page retrieved %", "mean_ctx_chars": "context chars/answer",
                                                      "search_ms_p50": "search p50 ms", "search_ms_p95": "search p95 ms"}))

(OUT / "tables.md").write_text("\n".join(md), encoding="utf-8")
print("wrote", OUT / "tables.md")

# ---------------- figures ----------------
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
fig, ax = plt.subplots(1, 2, figsize=(11, 3.8))
for t, lab in [("s_steady_t10", "steady (10x)"), ("s_burst_t10", "burst (10x)"), ("s_overload_t10", "overload (10x)"),
               ("s_burst_free", "burst (free tier)")]:
    df, _ = A.load(t); x = np.sort(df.ttft_ms.dropna()); ax[0].plot(x, np.arange(1, len(x) + 1) / len(x), label=lab)
ax[0].set_xscale("log"); ax[0].set_xlabel("time to first token, ms (log)"); ax[0].set_ylabel("fraction of requests"); ax[0].legend(); ax[0].set_title("TTFT CDF, stand-in")
labels, bars = [], {}
for t in ["s_steady_free", "s_burst_free", "s_overload_free", "s_steady_t10", "s_burst_t10", "s_overload_t10"]:
    df, _ = A.load(t); labels.append(t[2:])
    for k, v in df.assign(kind=df.apply(lambda r: "abandoned" if r.outcome == "abandon" else
                          ("full answer" if r.status in ("answered", "abstained") else str(r.status)), axis=1)).kind.value_counts(normalize=True).items():
        bars.setdefault(k, {})[t[2:]] = 100 * v
bd = pd.DataFrame(bars).reindex(labels).fillna(0)
bd.plot(kind="bar", stacked=True, ax=ax[1]); ax[1].set_ylabel("% of requests"); ax[1].set_title("Outcome mix, stand-in"); ax[1].tick_params(axis="x", rotation=30)
plt.tight_layout(); plt.savefig(OUT / "fig_load.png", dpi=130)
print("wrote figure")


# ---------------- snippets for the write-up (filled into README by scripts/build_readme.py) ----------------
def compact(tags_labels):
    rows = []
    for t, svc, label in tags_labels:
        s_ = A.table(t)
        n = int(s_["N requests"])
        rows.append({"run": label, "service": svc, "N": n,
                     "full answers": int(s_["answered/abstained (full model answer)"]),
                     "quoted-passages fallback": int(s_["extractive (degraded)"]),
                     "turned away (shed)": int(s_["shed (turned away)"]),
                     "declined": int(s_["declined (unverified)"]),
                     "gave up (abandoned)": int(s_["abandoned (gave up)"]),
                     "errors": int(s_["errors"]), "retries": int(s_["retries (total)"]),
                     "TTFT p50 ms": s_["TTFT p50 ms"], "TTFT p95 ms": s_["TTFT p95 ms"],
                     "Total p50 ms": s_["Total p50 ms"], "Total p95 ms": s_["Total p95 ms"],
                     "gave-up %": s_["abandon %"], "shed %": s_["shed %"],
                     "tokens/full answer": s_["tokens/answered request (mean)"]})
    return pd.DataFrame(rows)


SN = {}
SN["compact_real"] = compact([("real_steady", "REAL Groq (20B drafter)", "steady #1"),
                              ("real_steady2", "REAL Groq (20B drafter)", "steady #2"),
                              ("real_burst", "REAL Groq (20B drafter)", "burst (8 in 3 s)")]).to_markdown(index=False, disable_numparse=True)
SN["compact_free"] = compact([("s_steady_free", "stand-in", "steady (0.03 req/s, 600 s)"),
                              ("s_burst_free", "stand-in", "burst (20 in 5 s)"),
                              ("s_overload_free", "stand-in", "overload (0.15 req/s, 180 s)")]).to_markdown(index=False, disable_numparse=True)
SN["compact_t10"] = compact([("s_steady_t10", "stand-in 10x", "steady (0.3 req/s, 240 s)"),
                             ("s_burst_t10", "stand-in 10x", "burst (150 in 10 s)"),
                             ("s_overload_t10", "stand-in 10x", "overload (1.0 req/s, 240 s)")]).to_markdown(index=False, disable_numparse=True)
SN["compact_daily"] = compact([("s_daily_known", "stand-in 10x, tpd 40k", "daily budget gone, limiter told"),
                               ("s_daily_learned", "stand-in 10x, tpd 40k", "daily budget gone, limiter learns from the 429")]).to_markdown(index=False, disable_numparse=True)
SN["compact_retry"] = compact([("s_retry_none", "stand-in 10x, 30% failures", "0.4 req/s, no retries"),
                               ("s_retry_budget", "stand-in 10x, 30% failures", "0.4 req/s, budgeted retries"),
                               ("s_retry_unbounded", "stand-in 10x, 30% failures", "0.4 req/s, unbounded retries"),
                               ("s_retrysat_none", "stand-in 10x, 30% failures", "0.55 req/s, no retries"),
                               ("s_retrysat_budget", "stand-in 10x, 30% failures", "0.55 req/s, budgeted retries"),
                               ("s_retrysat_unbounded", "stand-in 10x, 30% failures", "0.55 req/s, unbounded retries")]).to_markdown(index=False, disable_numparse=True)
SN["retry_calls"] = pd.DataFrame(rr).to_markdown(index=False, disable_numparse=True)
SN["probe"] = pd.DataFrame(out).to_markdown(index=False, disable_numparse=True)
SN["quality"] = pd.DataFrame([qrow(*q) for q in Q]).to_markdown(index=False, disable_numparse=True)
SN["retrieval"] = pd.DataFrame(rh).T.sort_index().rename(
    columns={"hit_pct": "gold page retrieved %", "mean_ctx_chars": "context chars/answer",
             "search_ms_p50": "search p50 ms", "search_ms_p95": "search p95 ms"}).to_markdown()
for k, v in SN.items():
    (OUT / f"snip_{k}.md").write_text(v + "\n", encoding="utf-8")
print("wrote", len(SN), "snippets")

# ---------------- run 1 (before the queue-aware fix) ----------------
before = LOGS / "run1_before_queue_aware"
if before.exists():
    A.LOGDIR = before
    pre = compact([("s_burst_free", "stand-in", "BEFORE fix: burst (20 in 5 s)"), ("s_overload_free", "stand-in", "BEFORE fix: overload (0.15 req/s)"),
                   ("s_burst_t10", "stand-in 10x", "BEFORE fix: burst (150 in 10 s)"), ("s_overload_t10", "stand-in 10x", "BEFORE fix: overload (1.0 req/s)")])
    (OUT / "snip_before_fix.md").write_text(pre.to_markdown(index=False, disable_numparse=True) + "\n", encoding="utf-8")
    A.LOGDIR = LOGS
    print("wrote before-fix snippet")

# ---------------- round 2 ----------------
import make_tables_r2 as R2
n0 = len(SN)
R2.run(md, SN, OUT)
for k, v in SN.items():
    (OUT / f"snip_{k}.md").write_text(v + "\n", encoding="utf-8")
(OUT / "tables.md").write_text("\n".join(md), encoding="utf-8")
print("wrote round-2 tables and", len(SN) - n0, "snippets")
