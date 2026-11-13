"""Build results.csv (one row per request) from the raw logs, as the brief asks.

  python scripts/export_results.py            -> results.csv

Columns: request_id, scenario, source, start_time, first_token_ms, total_ms, status, retries, tokens_in, tokens_out,
retrieval_setting, answer_grade. Which logs become which scenario is data/scenarios.json.

How the columns are defined (the same definitions are repeated in docs/RESULTS_TABLES.md):
  request_id      <log tag>:<request id inside that run>
  start_time      load runs: seconds after the first request of the run arrived. quality runs: seconds after the first question.
  first_token_ms  load runs: from the client's arrival to the first byte of the reply it received (for full answers this is
                  after verification, because nothing is shown before the check passes). Empty if no byte ever arrived.
                  quality runs: SERVICE time, see below.
  total_ms        load runs: arrival to the last byte, or to the moment the simulated user gave up.
                  quality runs: SERVICE time = the provider calls of the request plus local retrieval. Those runs used a 300 s
                  deadline so questions queue behind the per-minute token limit; the wait in that queue (about 20 s per question)
                  is a pacing artefact of the test, not a latency, so it is left out.
  status          ok            a verified model answer, or a verified "the papers don't say"
                  rate_limited  the request got NO model answer because a limit was reached: the quoted-passages reply
                                (extractive) or the honest "I'm at capacity" reply (shed). The person still got a reply.
                  timeout       the simulated user gave up before any reply finished
                  error         the reply was "I couldn't produce an answer I can verify" (declined), or a client/server error
  retries         provider retries recorded for the request (empty if no server log of that run exists)
  tokens_in/out   provider-reported usage summed over all calls of the request (classify, rewrite, draft, verify)
  answer_grade    quality runs only, from the frozen rubric score (data/RUBRIC.md):
                    answerable: score 1.0 -> correct; score 0.5 (right facts, wrong or missing citation) -> wrong, because the
                    table column is "correct AND cited"; score 0 and the system answered -> wrong; score 0 and it said "the papers
                    don't say" or declined -> refused_wrongly.
                    unanswerable: said "the papers don't say" without a forbidden claim -> refused_correctly; otherwise wrong.
                  load runs: not_measured (the stand-in returns canned text; the real load runs are too small to grade).
"""
import csv, json, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGS = ROOT / "logs"
COLS = ["request_id", "scenario", "source", "start_time", "first_token_ms", "total_ms", "status", "retries", "tokens_in", "tokens_out",
        "retrieval_setting", "answer_grade"]


def jl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def status_of(server_status):
    if server_status in ("answered", "abstained"):
        return "ok"
    if server_status and (server_status.startswith("extractive") or server_status == "shed"):
        return "rate_limited"
    return "error"


def server_facts(tag):
    """per request: tokens_in, tokens_out, retries, final server status (from logs/server_<tag>.jsonl)"""
    path = LOGS / f"server_{tag}.jsonl"
    f = collections.defaultdict(lambda: {"in": 0, "out": 0, "retries": 0, "status": None, "any": False})
    if not path.exists():
        return {}
    for e in jl(path):
        r = e.get("req")
        if not r or r == "-":
            continue
        d = f[r]
        if e["event"] == "last_token":
            d["in"] += e.get("prompt_tokens", 0); d["out"] += e.get("completion_tokens", 0); d["any"] = True
        elif e["event"] == "retry":
            d["retries"] += 1
        elif e["event"] == "done":
            d["status"] = e["status"]; d["any"] = True
    return f


def load_rows(entry, setting_names):
    tag = entry["tag"]
    client = [e for e in jl(LOGS / f"load_{tag}.jsonl") if e["event"] != "meta"]
    sf = server_facts(tag)
    by = collections.OrderedDict()
    for e in client:
        d = by.setdefault(e["req"], {})
        if e["event"] == "arrive":
            d["arrive"] = e["t"]
        elif e["event"] == "first_byte":
            d["first"] = e["t"]
        elif e["event"] in ("end", "abandon", "error"):
            d["last"], d["outcome"], d["cstatus"] = e["t"], e["event"], e.get("status")
    t0 = min(d["arrive"] for d in by.values() if "arrive" in d)
    rows = []
    for rid, d in by.items():
        if "arrive" not in d or "outcome" not in d:
            continue
        s = sf.get(rid)
        if d["outcome"] == "abandon":
            status = "timeout"
        elif d["outcome"] == "error":
            status = "error"
        else:
            status = status_of((s or {}).get("status") or d.get("cstatus"))
        rows.append({"request_id": f"{tag}:{rid}", "scenario": entry["scenario"], "source": entry["source"],
                     "start_time": f"{d['arrive'] - t0:.3f}",
                     "first_token_ms": f"{(d['first'] - d['arrive']) * 1000:.1f}" if "first" in d else "",
                     "total_ms": f"{(d['last'] - d['arrive']) * 1000:.1f}", "status": status,
                     "retries": s["retries"] if s else "", "tokens_in": s["in"] if s else "", "tokens_out": s["out"] if s else "",
                     "retrieval_setting": setting_names[entry["setting"]], "answer_grade": "not_measured"})
    return rows


def grade(q, res):
    low = res["text"].lower().replace("’", "'")
    abst = "the papers don't say" in low
    if q["type"] == "unanswerable":
        return "refused_correctly" if res["score"] == 1.0 else "wrong"
    if res["score"] == 1.0:
        return "correct"
    if res["score"] == 0.5:
        return "wrong"
    return "refused_wrongly" if (abst or res["status"] in ("declined", "abstained") or res["status"].startswith("extractive")) else "wrong"


def eval_rows(entry):
    tag = entry["tag"]
    res = json.load(open(LOGS / f"eval_{tag}_results.json", encoding="utf-8"))
    ev = jl(LOGS / f"eval_{tag}.jsonl")
    per = collections.defaultdict(lambda: {"svc": 0.0, "in": 0, "out": 0, "retries": 0, "t_enq": None, "open": {}})
    for e in ev:
        r = e.get("req")
        if not r or r == "-":
            continue
        d = per[r]
        if e["event"] == "enqueue":
            d["t_enq"] = e["t"]
        elif e["event"] == "last_token":
            d["svc"] += e["total_ms"]; d["in"] += e["prompt_tokens"]; d["out"] += e["completion_tokens"]
        elif e["event"] == "retry":
            d["retries"] += 1
        elif e["event"] == "step_start" and e["step"] == "retrieve":
            d["open"]["retrieve"] = e["t"]
        elif e["event"] == "step_end" and e["step"] == "retrieve" and "retrieve" in d["open"]:
            d["svc"] += (e["t"] - d["open"].pop("retrieve")) * 1000
    qs = {}
    for name in ("questions", "questions_hard", "questions_hard2"):
        for q in json.load(open(ROOT / "data" / f"{name}.json", encoding="utf-8")):
            qs[q["id"]] = q
    t0 = min(d["t_enq"] for d in per.values() if d["t_enq"] is not None)
    rows = []
    for r in res:
        d = per[r["id"]]
        q = qs[r["id"]]
        svc = d["svc"]
        rows.append({"request_id": f"{tag}:{r['id']}", "scenario": entry["scenario"], "source": entry["source"],
                     "start_time": f"{(d['t_enq'] - t0):.3f}", "first_token_ms": f"{svc:.1f}", "total_ms": f"{svc:.1f}",
                     "status": status_of(r["status"]), "retries": d["retries"], "tokens_in": d["in"], "tokens_out": d["out"],
                     "retrieval_setting": entry["setting"], "answer_grade": grade(q, r)})
    return rows


def main():
    man = json.load(open(ROOT / "data" / "scenarios.json", encoding="utf-8"))
    rows = []
    for e in man["load"]:
        rows += load_rows(e, man["retrieval_settings"])
    for e in man["eval"]:
        rows += eval_rows(e)
    with open(ROOT / "results.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    c = collections.Counter(r["scenario"] for r in rows)
    print(f"results.csv: {len(rows)} rows, {len(c)} scenarios")


if __name__ == "__main__":
    main()
