"""Round-2 tables and snippets (called at the end of make_tables.py). Everything is computed from raw logs/.

Adds sections R1..R10 to results/tables.md and writes results/snip_r2_*.md, which README.template.md pulls in."""
import collections, glob, json, pathlib
import numpy as np, pandas as pd
import analyze as A

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"


def jl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def md_table(df, index=False):
    return df.to_markdown(index=index, disable_numparse=True)


def compact(tags_labels):
    rows = []
    for t, label in tags_labels:
        s = A.table(t)
        rows.append({"run": label, "N": int(s["N requests"]), "full answers": int(s["answered/abstained (full model answer)"]),
                     "quoted-passages fallback": int(s["extractive (degraded)"]), "turned away": int(s["shed (turned away)"]),
                     "gave up": int(s["abandoned (gave up)"]), "TTFT p50 ms": s["TTFT p50 ms"], "TTFT p95 ms": s["TTFT p95 ms"],
                     "full-answer TTFT p95 ms": s["TTFT p95 ms, full answers only"], "tokens/full answer": s["tokens/answered request (mean)"],
                     "laptop stalls >100 ms": stalls(t)})
    return pd.DataFrame(rows)


def stalls(tag):
    """How often did the laptop itself freeze for >100 ms during the run? (event-loop lag monitor in the server)"""
    lag = [e["lag_ms"] for e in jl(LOGS / f"server_{tag}.jsonl") if e["event"] == "loop_lag"]
    return f"{len(lag)} (worst {max(lag):.0f} ms)" if lag else "0"


def levels(tag):
    c = collections.Counter()
    for e in jl(LOGS / f"server_{tag}.jsonl"):
        if e["event"] == "done":
            c[(e["status"], e["level"])] += 1
    full0 = sum(v for (s, l), v in c.items() if s in ("answered", "abstained") and l == 0)
    full1 = sum(v for (s, l), v in c.items() if s in ("answered", "abstained") and l == 1)
    return full0, full1


def run(md, SN, OUT):
    def h(t): md.append(f"\n### {t}\n")
    def tb(df, index=False): md.append(md_table(df, index) + "\n")
    def snip(name, text): SN["r2_" + name] = text

    # ---- R1 token accounting (real Groq) ----
    h("R1. Does Groq charge max_tokens or the tokens actually used? (real Groq, logs/groq_probe2_accounting_*.jsonl)")
    files = sorted(glob.glob(str(LOGS / "groq_probe2_accounting*.jsonl")))
    files = [f for f in files if not f.endswith("_1794487800.jsonl")]       # first attempt: 2 s gaps, bucket not refilled
    rows = []
    for f in files:
        for r in jl(f):
            if r.get("tag", "").startswith("acct") and r.get("status") == 200 and r["tag"] != "acct_prime":
                rem = float(r["headers"]["x-ratelimit-remaining-tokens"])
                u = r["usage"]
                rows.append({"model": r["model"].split("/")[-1], "max_tokens sent": r["max_tokens"], "prompt tokens": u["prompt_tokens"],
                             "completion tokens": u["completion_tokens"], "tokens charged (8000 - remaining header)": int(round(8000 - rem)),
                             "actual usage": u["total_tokens"]})
    acc = pd.DataFrame(rows).sort_values(["model", "max_tokens sent"])
    tb(acc)
    same = int((acc["tokens charged (8000 - remaining header)"] == acc["actual usage"]).sum())
    snip("accounting", md_table(acc) + f"\n\n{same} of {len(acc)} requests were charged exactly their real usage whatever `max_tokens` was "
         f"(20 to 4,000 on the 20B, 20 to 3,000 on the 120B; one 9,000 request was accepted and charged 96). "
         f"The other {len(acc) - same} were charged extra (see table): they do not track `max_tokens`.")

    # ---- R2 concurrency (real Groq) ----
    h("R2. Real Groq under concurrency (tiny requests on the 20B, logs/groq_probe2_concurrency_*.jsonl)")
    out = []
    for f in sorted(glob.glob(str(LOGS / "groq_probe2_concurrency_*.jsonl"))):
        rows_ = jl(f)
        reqs = [r for r in rows_ if "status" in r]
        summ = next(r for r in rows_ if r.get("tag") == "summary")
        by = collections.defaultdict(list)
        for r in reqs:
            if r.get("ttft_ms"):
                by[int(r["tag"][4:])].append(r["ttft_ms"])
        for k in sorted(by):
            out.append({"file": pathlib.Path(f).name[-16:-6], "in flight": k, "requests": len(by[k]), "TTFT p50 ms": f"{np.median(by[k]):.0f}",
                        "TTFT p90 ms": f"{np.percentile(by[k], 90):.0f}", "max ms": f"{max(by[k]):.0f}",
                        "all 200": all(r["status"] == 200 for r in reqs), "laptop stalls >100 ms (whole run)": summ["lag_events_over_100ms"],
                        "worst stall ms": summ["max_loop_lag_ms"]})
    conc = pd.DataFrame(out)
    tb(conc)
    snip("concurrency", md_table(conc))
    # stand-in versus real, same tiny request at the same concurrency (scripts/validate_standin.py)
    val = json.load(open(LOGS / "standin_validation.json", encoding="utf-8"))
    qf = sorted(glob.glob(str(LOGS / "groq_probe2_quiet_*.jsonl")))[-1]
    single = np.median([r["ttft_ms"] for r in jl(qf) if r.get("model") == "openai/gpt-oss-20b" and r.get("ttft_ms")])
    cmp_rows = []
    for k in (1, 4, 8, 12, 16):
        real_ = [float(x["TTFT p50 ms"]) for x in out if x["in flight"] == k]
        cmp_rows.append({"in flight": k, "real Groq p50 ms (each probe file)": " / ".join(f"{v:.0f}" for v in real_) if real_ else f"{single:.0f} (quiet run)",
                         "stand-in p50 ms": val["results"][str(k)]["p50"], "stand-in p90 ms": val["results"][str(k)]["p90"]})
    cm = pd.DataFrame(cmp_rows)
    tb(cm)
    snip("concurrency_vs_standin", md_table(cm))

    # ---- R3 quiet run (real Groq) ----
    h("R3. A slow trickle on real Groq: does anything ever fail when nothing is stressing it? (logs/groq_probe2_quiet_*.jsonl)")
    q = []
    for f in sorted(glob.glob(str(LOGS / "groq_probe2_quiet_*.jsonl"))):
        rows_ = jl(f)
        reqs = [r for r in rows_ if "status" in r and r.get("tag") == "quiet"]
        summ = next(r for r in rows_ if r.get("tag") == "summary")
        for m in sorted({r["model"] for r in reqs}):
            t = np.array([r["ttft_ms"] for r in reqs if r["model"] == m and r.get("ttft_ms")])
            q.append({"model": m.split("/")[-1], "requests": sum(r["model"] == m for r in reqs), "non-200": sum(r["model"] == m and r["status"] != 200 for r in reqs),
                      "no first token": sum(r["model"] == m and not r.get("ttft_ms") for r in reqs),
                      "TTFT p50 ms": f"{np.median(t):.0f}", "TTFT p95 ms": f"{np.percentile(t, 95):.0f}", "TTFT max ms": f"{t.max():.0f}",
                      "slower than 3x median": int((t > 3 * np.median(t)).sum()), "laptop stalls >100 ms": summ["lag_events_over_100ms"]})
    qd = pd.DataFrame(q)
    tb(qd)
    snip("quiet", md_table(qd))

    # ---- R4 Gemini ----
    h("R4. Gemini, the backup provider (real calls; logs/gemini_probe_*.jsonl)")
    g = []
    for f in sorted(glob.glob(str(LOGS / "gemini_probe_[0-9]*.jsonl"))):
        for m in sorted({r["model"] for r in jl(f) if "model" in r}):
            lat = [r for r in jl(f) if r.get("model") == m and r.get("tag") == "latency"]
            if not lat:
                continue
            ok = [r["ttft_ms"] for r in lat if r.get("status") == 200 and r.get("ttft_ms")]
            g.append({"model": m, "tiny requests": len(lat), "200": len(ok), "other": len(lat) - len(ok),
                      "TTFT p50 ms": f"{np.median(ok):.0f}" if ok else "-", "TTFT max ms": f"{max(ok):.0f}" if ok else "-"})
    gd = pd.DataFrame(g)
    tb(gd)
    lim = [r for f in glob.glob(str(LOGS / "gemini_probe_limit_*.jsonl")) for r in jl(f)]
    st = collections.Counter(r["status"] for r in lim)
    first429 = next((r["body"] for r in lim if r["status"] == 429), "")
    md.append(f"Deliberate burst of {len(lim)} tiny requests on gemini-3.1-flash-lite: statuses {dict(st)}. First 429 body (excerpt): `{first429[:330].strip()}`\n")
    snip("gemini", md_table(gd) + f"\n\nA burst of {len(lim)} tiny requests: {dict(st)}. The 429 body carries the limit (\"limit: 15 ... requests per minute\") and the wait "
         f"(\"Please retry in 53.4s\"); there is no `retry-after` header and no `x-ratelimit-*` header at all. The 503 replies say \"experiencing high demand\".")

    # ---- R5 burst: round 1 versus round 2, three seeds, plus ablation ----
    h("R5. 10x burst of 150 in 10 s: round-1 settings versus round-2 settings on the same code, three seeds")
    rows = []
    for rd in ("round1", "round2"):
        for sd in (1, 2, 3):
            t = f"r2_cmp_burst_t10_{rd}_s{sd}"
            s = A.table(t); f0, f1 = levels(t)
            rows.append({"settings": rd, "seed": sd, "full answers": int(s["answered/abstained (full model answer)"]), "of which degraded (k=3)": f1,
                         "quoted fallback": int(s["extractive (degraded)"]), "gave up": int(s["abandoned (gave up)"]),
                         "TTFT p95 ms": s["TTFT p95 ms"], "full-answer TTFT p95 ms": s["TTFT p95 ms, full answers only"], "laptop stalls >100 ms": stalls(t)})
    cmp_ = pd.DataFrame(rows)
    tb(cmp_)
    snip("burst_seeds", md_table(cmp_))
    h("R5b. Which round-2 change did it? (seed 1; same 150-request burst)")
    abl = [("r2_cmp_burst_t10_round1_s1", "round 1 as it was (stand-in charges max_tokens)"),
           ("r2_abl_burst_t10_commit_only", "round 1 + count admitted requests' coming draft calls"),
           ("r2_abl_burst_t10_actualcharge_only", "round 1 limiter, stand-in charges real usage"),
           ("r2_burst_t10_maxtok_cmt_off", "+ real-usage token estimate and refunds (stand-in still charges max_tokens)"),
           ("r2_burst_t10_maxtok_cmt_on", "+ both of the above (stand-in still charges max_tokens)"),
           ("r2_cmp_burst_t10_round2_s1", "all round-2 changes (stand-in charges real usage)")]
    rows = []
    for t, lab in abl:
        s = A.table(t); f0, f1 = levels(t)
        rows.append({"settings": lab, "full answers (normal / degraded)": f"{f0} / {f1}", "quoted fallback": int(s["extractive (degraded)"]),
                     "TTFT p95 ms": s["TTFT p95 ms"], "full-answer TTFT p95 ms": s["TTFT p95 ms, full answers only"], "laptop stalls >100 ms": stalls(t)})
    ab = pd.DataFrame(rows)
    tb(ab)
    snip("ablation", md_table(ab))
    h("R5c. Shedding threshold: 40% versus 30% of the remaining time (round-2 code, seed 1234)")
    th = compact([("r2_burst_t10_commit", "shed at 40% of remaining time (chosen)"), ("r2_burst_t10_commit_s30", "shed at 30%")])
    tb(th)
    snip("threshold", md_table(th))

    # ---- R6 daily wall ----
    h("R6. Daily token budget gone (stand-in, 10x, daily budget 40,000 tokens)")
    dly = compact([("s_daily_known", "round 1: limiter told the budget"), ("r2_daily_known", "round 2: limiter told the budget"),
                   ("s_daily_learned", "round 1: limiter learns it from the 429"), ("r2_daily_learned", "round 2: limiter learns it from the 429"),
                   ("r2_daily_failover", "round 2 + second provider ready (also 40,000 tokens)")])
    tb(dly)
    ev = jl(LOGS / "server_r2_daily_failover.jsonl")
    prov = collections.Counter(e.get("provider") for e in ev if e["event"] == "send" and e.get("step") == "draft")
    dm = json.load(open(LOGS / "r2_daily_msg.json", encoding="utf-8"))
    msg = next(x["reply"] for x in dm if x["status"] == "shed")
    md.append(f"Draft calls by provider in the failover run: {dict(prov)}. Failover events: {sum(e['event'] == 'failover' for e in ev)}.\n")
    snip("daily", md_table(dly) + f"\n\nDraft calls by provider in the failover run: {dict(prov)}; calls moved mid-request after a daily 429: {sum(e['event'] == 'failover' for e in ev)}.")
    snip("daily_msg", msg or "(no low-confidence decline occurred in that run)")

    # ---- R6b real service: failover, bursts, steady ----
    h("R6b. Real Groq (and Gemini) runs of round 2")
    real_runs = [("real_failover_r2", "failover demo: Groq daily budget set to 6,000 tokens, then Gemini (20B drafter)"),
                 ("real_steady_r2", "steady, about 0.035 req/s (20B drafter)")]
    rr_ = compact(real_runs)
    ev = jl(LOGS / "server_real_failover_r2.jsonl")
    prov = collections.Counter(e.get("provider") for e in ev if e["event"] == "send")
    tb(rr_)
    md.append(f"Calls sent by provider in the failover demo: {dict(prov)}; failover events {sum(e['event'] == 'failover' for e in ev)}.\n")
    snip("real_runs", md_table(rr_) + f"\n\nCalls sent by provider in the failover demo: {dict(prov)}.")
    h("R6c. The same 8-request burst in 3 seconds on real Groq, different code and different times")
    bursts = [("real_burst", "round-1 code, earlier", "20B"), ("real_burst_r2", "round-2 code", "20B"), ("real_burst_r2b", "round-2 code, repeat", "20B"),
              ("cmp_r1code_a", "round-1 code (old server on :8100), pair A", "120B"), ("cmp_r2code_a", "round-2 code, pair A (right after)", "120B"),
              ("cmp_r1code_b", "round-1 code (old server on :8100), pair B", "120B"), ("cmp_r2code_b", "round-2 code, pair B (right after)", "120B"),
              ("real_burst_r2c", "round-2 code, alone", "120B")]
    rows = []
    for t, lab, mdl in bursts:
        x = A.table(t)
        first = [e["ttft_ms"] for e in jl(LOGS / f"server_{t}.jsonl") if e["event"] == "first_token" and e["step"] == "classify"]
        rows.append({"run": t, "code": lab, "drafter": mdl, "full answers": int(x["answered/abstained (full model answer)"]),
                     "quoted fallback": int(x["extractive (degraded)"]), "turned away": int(x["shed (turned away)"]),
                     "TTFT p95 ms": x["TTFT p95 ms"], "median first token of the classify calls, ms": f"{np.median(first):.0f}" if first else "-",
                     "laptop stalls >100 ms": "n/a (server log is in server_mytest.jsonl)" if t.startswith("cmp_r1code") else stalls(t)})
    bd = pd.DataFrame(rows)
    tb(bd)
    snip("real_bursts", md_table(bd))

    # ---- R7 cache ----
    h("R7. Answer cache (identical questions share one answer; the load generator draws from 22 questions, so repeats are heavy)")
    cache_rows = []
    for t, lab in [("r2_cache_burst_t10_off", "10x burst of 150, cache off"), ("r2_cache_burst_t10_on", "10x burst of 150, cache on"),
                   ("r2_cache_burst_free_off", "free-tier burst of 20, cache off"), ("r2_cache_burst_free_on", "free-tier burst of 20, cache on")]:
        ev = jl(LOGS / f"server_{t}.jsonl")
        s = A.table(t)
        cache_rows.append({"run": lab, "full answers": int(s["answered/abstained (full model answer)"]), "quoted fallback": int(s["extractive (degraded)"]),
                           "gave up": int(s["abandoned (gave up)"]), "model calls": sum(e["event"] == "send" for e in ev),
                           "cache hits": sum(e["event"] == "cache_hit" for e in ev), "joined an in-flight answer": sum(e["event"] == "cache_join" for e in ev),
                           "tokens used": sum(e["prompt_tokens"] + e["completion_tokens"] for e in ev if e["event"] == "last_token"),
                           "TTFT p50 ms": s["TTFT p50 ms"], "TTFT p95 ms": s["TTFT p95 ms"], "laptop stalls >100 ms": stalls(t)})
    cd = pd.DataFrame(cache_rows)
    tb(cd)
    snip("cache", md_table(cd))

    # ---- R8 retrieval ----
    h("R8. Retrieval only (no model calls): round-1 chunker (v1) versus the fixed chunker (v2), prompt trimming, fewer chunks")
    rr = json.load(open(LOGS / "retrieval_round2.json", encoding="utf-8"))
    rows = []
    for setting, sets in rr.items():
        row = {"setting": setting}
        for sname, v in sets.items():
            short = "original" if sname.startswith("original") else "new"
            row[f"{short}: page hit %"] = v["hit_pct"]; row[f"{short}: answer in context %"] = v["has_answer_pct"]
            row[f"{short}: context chars"] = v["mean_ctx_chars"]
        rows.append(row)
    rd_ = pd.DataFrame(rows)
    tb(rd_)
    snip("retrieval", md_table(rd_))

    # ---- R9 token estimate ----
    h("R9. How well did the limiter's token estimate match what the call really cost? (draft calls, from eval logs)")
    rows = []
    for tag, lab in [("q_bm25_1200_k5", "round 1 estimate (chars/3 + max_tokens), easy 20"), ("r2_hard2_v2_20B_run1", "round 2 estimate (chars/3.3 + typical reply), new 25")]:
        ev = jl(LOGS / f"eval_{tag}.jsonl")
        est = {}
        for e in ev:
            if e["event"] == "send" and e["step"] == "draft" and e["attempt"] == 1:
                est[e["req"]] = e["est_tokens"]
        act = {e["req"]: e["prompt_tokens"] + e["completion_tokens"] for e in ev if e["event"] == "last_token" and e["step"] == "draft"}
        ks = [k for k in est if k in act]
        r = np.array([est[k] / act[k] for k in ks])
        rows.append({"estimate": lab, "draft calls": len(ks), "mean reserved tokens": f"{np.mean([est[k] for k in ks]):.0f}",
                     "mean real tokens": f"{np.mean([act[k] for k in ks]):.0f}", "reserved / real, median": f"{np.median(r):.2f}",
                     "reserved < real": int((r < 1).sum())})
    te = pd.DataFrame(rows)
    tb(te)
    snip("estimate", md_table(te))

    # ---- R9b every real request, by provider and outcome ----
    h("R9b. Every real request recorded in logs/, by provider and outcome (probes and pipeline calls)")
    cnt = collections.defaultdict(collections.Counter)
    for f in glob.glob(str(LOGS / "groq_probe*.jsonl")) + glob.glob(str(LOGS / "gemini_probe*.jsonl")):
        prov_ = "gemini" if "gemini" in f else "groq"
        for r in jl(f):
            st_ = r.get("status")
            if st_ is None or r.get("tag") in ("models",):
                continue
            key = "ok" if st_ == 200 else "429" if st_ == 429 else "5xx" if isinstance(st_, int) and st_ >= 500 else "404" if st_ == 404 else "client error"
            cnt[prov_][("probe", key)] += 1
    real_logs = [f for f in glob.glob(str(LOGS / "eval_*.jsonl")) + glob.glob(str(LOGS / "server_real*.jsonl")) 
                 if "standin" not in f and "_results" not in f and "check_" not in f]     # check_* are scratch runs of scripts/check.py
    for f in real_logs:
        for e in jl(f):
            ev = e["event"]
            prov_ = e.get("provider") or ("gemini" if "gemini" in f else "groq")      # older logs have no provider field
            if ev == "send":
                cnt[prov_][("pipeline", "sent")] += 1
            elif ev == "http_429":
                cnt[prov_][("pipeline", "429")] += 1
            elif ev == "retry":
                r_ = str(e.get("reason"))
                cnt[prov_][("pipeline", "5xx" if r_.startswith("http_5") else "timeout or connection error" if r_ != "429" else "retry after 429")] += 1
    rows = []
    for prov_, c in sorted(cnt.items()):
        rows.append({"provider": prov_, "probe requests": sum(v for (k, _), v in c.items() if k == "probe"),
                     "probe: 5xx": c[("probe", "5xx")], "probe: 429": c[("probe", "429")],
                     "pipeline calls sent": c[("pipeline", "sent")], "pipeline: 429": c[("pipeline", "429")],
                     "pipeline: 5xx retried": c[("pipeline", "5xx")], "pipeline: timeout or connection errors": c[("pipeline", "timeout or connection error")]})
    rq = pd.DataFrame(rows)
    tb(rq)
    snip("real_requests", md_table(rq))

    # ---- R10 quality ----
    h("R10. Answer quality on real models, round 2 (rubric: data/RUBRIC.md, unchanged)")
    def qrow(tag, label, model, qset):
        res = json.load(open(LOGS / f"eval_{tag}_results.json", encoding="utf-8"))
        ev = jl(LOGS / f"eval_{tag}.jsonl")
        tok = {}
        for e in ev:
            if e["event"] == "last_token":
                tok[e["req"]] = tok.get(e["req"], 0) + e["prompt_tokens"] + e["completion_tokens"]
        n = len(res)
        adj = json.load(open(ROOT / "data" / "adjudication.json", encoding="utf-8"))
        tot, keep = 0.0, 0
        for r in res:
            v = adj.get(f"{tag}|{r['id']}", {}).get("verdict")
            if v == "exclude":
                continue
            keep += 1
            tot += 1.0 if v == "correct" else r["score"]
        by_hand = f"{100 * tot / keep:.1f} (n={keep})"
        return {"run": label, "drafter": model, "question set": qset, "n": n, "quality % (frozen rubric)": f"{100 * sum(r['score'] for r in res) / n:.1f}",
                "after reading by hand (data/adjudication.json)": by_hand,
                "unanswerable question answered": sum(r["confident_wrong"] for r in res),
                "answerable question answered with wrong or missing facts": sum(r["type"] != "unanswerable" and r["status"] == "answered" and r["score"] == 0 for r in res),
                "declined": sum(r["status"] == "declined" for r in res),
                "tokens/question": f"{np.mean(list(tok.values())):.0f}"}
    QR = [t for t in [("r2_hard2_v2_20B_run1", "run 1", "gpt-oss-20b", "new hard 25"),
                      ("r2_hard2_v2_120B_run1", "run 1", "gpt-oss-120b", "new hard 25"),
                      ("r2_hard_v2_120B_run1", "run 1", "gpt-oss-120b", "round-1 hard 9"),
                      ("r2_hard2_v2_20B_rep_a", "repeat A (the 6 imperfect questions)", "gpt-oss-20b", "6 of the new 25"),
                      ("r2_hard2_v2_20B_rep_b", "repeat B (the 6 imperfect questions)", "gpt-oss-20b", "6 of the new 25"),
                      ("r2_hard2_gemini_run1", "run 1", "gemini-3.1-flash-lite", "new hard 25")]
          if (LOGS / f"eval_{t[0]}_results.json").exists()]
    qd = pd.DataFrame([qrow(*t) for t in QR])
    tb(qd)
    snip("quality", md_table(qd))
    mat = {}
    for tag, lab, model, qs in QR:
        if qs in ("new hard 25",):
            for r in json.load(open(LOGS / f"eval_{tag}_results.json", encoding="utf-8")):
                mat.setdefault(r["id"], {})[f"{model} {lab}"] = r["score"] if r["status"] != "declined" else "declined"
    if mat:
        mm = pd.DataFrame(mat).T
        mm = mm[(mm != 1.0).any(axis=1)] if len(mm) else mm
        md.append("Questions that did not score 1.0 in at least one run:\n")
        tb(mm.reset_index().rename(columns={"index": "question"}))
        snip("quality_misses", md_table(mm.reset_index().rename(columns={"index": "question"})))
    return
