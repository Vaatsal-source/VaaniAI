"""Tables 2a, 2b and 3 of the brief, computed from results.csv ONLY (plus data/pricing.json for the cost column).

  python scripts/tables_from_csv.py        -> results/brief_tables.md

Percentiles: numpy.percentile, linear interpolation, over the requests that have the value. All times in ms, percentages one decimal.
Where a scenario was produced by several runs (for example the real bursts), requests are pooled for the percentiles and rates, and
"Duration", "Offered rate" and "Peak queue length" are taken per run and averaged (peak: the largest)."""
import json, pathlib
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
df = pd.read_csv(ROOT / "results.csv", dtype={"retries": "float", "tokens_in": "float", "tokens_out": "float"})
price = json.load(open(ROOT / "data" / "pricing.json", encoding="utf-8"))
P_IN, P_OUT = price["usd_per_million_input_tokens"], price["usd_per_million_output_tokens"]
df["run"] = df.request_id.str.split(":").str[0]


def pct(x, q):
    x = x.dropna()
    return "not measured" if len(x) == 0 else f"{np.percentile(x, q):.1f}"


def p3(x):
    return " / ".join(pct(x, q) for q in (50, 95, 99))


def peak_waiting(run):
    """largest number of requests that had arrived and not yet seen a first token (or given up / been answered)."""
    ev = []
    for _, r in run.iterrows():
        end = r.start_time * 1000 + (r.first_token_ms if pd.notna(r.first_token_ms) else r.total_ms)
        ev += [(r.start_time * 1000, 1), (end, -1)]
    cur = best = 0
    for _, d in sorted(ev, key=lambda e: (e[0], e[1])):
        cur += d; best = max(best, cur)
    return best


def run_stats(run):
    n = len(run)
    dur = float((run.start_time * 1000 + run.total_ms).max() - 0) / 1000
    span = max(float(run.start_time.max()), 1.0)
    return {"duration": dur, "rate": n / span * 60, "peak": peak_waiting(run)}


load = df[~df.scenario.str.startswith("quality_")]
order = []
for s in load.scenario:
    if s not in order:
        order.append(s)

a_rows, b_rows = [], []
for sc in order:
    g = load[load.scenario == sc]
    stats = [run_stats(r) for _, r in g.groupby("run")]
    n = len(g)
    ok = g[g.status == "ok"]
    known = g.dropna(subset=["tokens_in"])
    toks = (ok.tokens_in + ok.tokens_out).dropna()
    total_cost = ((known.tokens_in * P_IN + known.tokens_out * P_OUT) / 1e6).sum()
    cost = f"{1000 * total_cost / len(ok[ok.tokens_in.notna()]):.3f}" if len(ok[ok.tokens_in.notna()]) and len(known) == n else "not measured"
    a_rows.append({"Scenario": sc, "Real or stand-in": g.source.iloc[0], "Requests sent": n, "Runs": g.run.nunique(),
                   "Duration (s)": f"{np.mean([s['duration'] for s in stats]):.1f}",
                   "Offered rate (per min)": f"{np.mean([s['rate'] for s in stats]):.1f}",
                   "Requests with a first token": int(g.first_token_ms.notna().sum()),
                   "First token p50 / p95 / p99 (ms)": p3(g.first_token_ms), "Total time p50 / p95 / p99 (ms)": p3(g.total_ms)})
    b_rows.append({"Scenario": sc, "Succeeded %": f"{100 * (g.status == 'ok').mean():.1f}",
                   "Rate-limited %": f"{100 * (g.status == 'rate_limited').mean():.1f}",
                   "Timed out or given up %": f"{100 * (g.status == 'timeout').mean():.1f}",
                   "Error %": f"{100 * (g.status == 'error').mean():.1f}",
                   "Retries per request": f"{g.retries.mean():.2f}" if g.retries.notna().any() else "not measured",
                   "Peak queue length": max(s["peak"] for s in stats),
                   "Tokens per answer": f"{toks.mean():.1f}" if len(toks) else "not measured",
                   "Cost per 1,000 answers (USD)": cost})

# ---- Table 3: quality per retrieval setting ----
q = df[df.scenario.str.startswith("quality_")]
t3 = []
for (sc, setting), g in q.groupby(["scenario", "retrieval_setting"], sort=False):
    n = len(g)
    tok = (g.tokens_in + g.tokens_out)
    t3.append({"Setting (piece size, pieces fetched, re-rank)": setting, "Question set and drafting model": sc.replace("quality_", ""),
               "Questions asked": n, "Correct and cited %": f"{100 * (g.answer_grade == 'correct').mean():.1f}",
               "Wrong %": f"{100 * (g.answer_grade == 'wrong').mean():.1f}",
               "Correctly refused %": f"{100 * (g.answer_grade == 'refused_correctly').mean():.1f}",
               "Refused wrongly %": f"{100 * (g.answer_grade == 'refused_wrongly').mean():.1f}",
               "Tokens per answer": f"{tok.mean():.0f}",
               "First token p50 / p95 (ms)": " / ".join(pct(g.first_token_ms, x) for x in (50, 95)),
               "Total time p50 / p95 (ms)": " / ".join(pct(g.total_ms, x) for x in (50, 95))})

md = f"""# Results tables computed from results.csv

Everything below is produced by `python scripts/tables_from_csv.py` from `results.csv` alone (the cost column also reads `data/pricing.json`).
`results.csv` is produced by `python scripts/export_results.py` from the raw logs in `logs/` using `data/scenarios.json`.
Column definitions are at the top of `scripts/export_results.py`.

* **Succeeded** = a verified model answer or a verified "the papers don't say". **Rate-limited** = no model answer because a limit was reached,
  so the person got the quoted-passages reply or the honest "I'm at capacity" reply (nobody receives a bare 429 from this system).
  **Timed out or given up** = the simulated user left (patience 20 s). **Error** = a declined unverifiable answer or a client error.
* **Offered rate** = requests divided by the time over which they arrived. **Duration** = first arrival to last completion.
* **Peak queue length** = the largest number of requests that had arrived and not yet seen a first token (computed from `start_time` and `first_token_ms`).
* **Tokens per answer** = mean of tokens_in + tokens_out over the requests with status ok. **Cost per 1,000 answers** = every token of every request in the
  scenario, priced at the list price in `data/pricing.json` (the 120B's, an upper bound; the free tier itself costs nothing), divided by the number of ok answers, times 1,000.
* Percentiles over fewer than 100 requests: p99 is then essentially the slowest request. Read the "Requests with a first token" column.
* Quality runs (Table 3) used a 300 s deadline, so their times are SERVICE times (provider calls plus local retrieval, queue waits excluded).

## Table 2a: Latency, one row per scenario

{pd.DataFrame(a_rows).to_markdown(index=False, disable_numparse=True)}

## Table 2b: Outcomes, same rows

{pd.DataFrame(b_rows).to_markdown(index=False, disable_numparse=True)}

## Table 3: Retrieval settings (real Groq; quality graded by the frozen rubric)

{pd.DataFrame(t3).to_markdown(index=False, disable_numparse=True)}

Grades: `correct` = right facts and a gold-page citation; a right answer with a wrong or missing citation (score 0.5) is counted as `wrong`
because the column is "correct and cited". `refused_wrongly` = the system said "the papers don't say" or declined on a question the papers do answer.
"""
# ---- the short versions that go into the 2-page write-up (the full tables stay in results/brief_tables.md) ----
CORE = ["steady_free_tier", "burst_free_tier", "overload_free_tier", "steady_per_minute_limits_halved", "burst_per_minute_limits_halved",
        "steady_10x_limits", "burst_10x_limits", "overload_10x_limits", "daily_budget_exhausted_limiter_learns",
        "daily_budget_exhausted_second_provider", "steady_real", "burst_real", "daily_budget_exhausted_real_second_provider"]
A_ = pd.DataFrame(a_rows).set_index("Scenario"); B_ = pd.DataFrame(b_rows).set_index("Scenario")
core_a = A_.loc[[c for c in CORE if c in A_.index]].drop(columns=["Runs", "Total time p50 / p95 / p99 (ms)", "Requests with a first token"]).reset_index()
core_b = B_.loc[[c for c in CORE if c in B_.index]].reset_index()
T3 = pd.DataFrame(t3)
core_3 = T3[T3["Question set and drafting model"].isin(["hard9_gpt-oss-20b", "hard25_gpt-oss-20b"])]
for name, frame in (("brief_2a_core", core_a), ("brief_2b_core", core_b), ("brief_3_core", core_3)):
    (ROOT / "results" / f"{name}.md").write_text(frame.to_markdown(index=False, disable_numparse=True) + "\n", encoding="utf-8")

(ROOT / "results").mkdir(exist_ok=True)
(ROOT / "results" / "brief_tables.md").write_text(md, encoding="utf-8")
print("wrote results/brief_tables.md:", len(a_rows), "load scenarios,", len(t3), "retrieval settings")
