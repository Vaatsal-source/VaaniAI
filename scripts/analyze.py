"""Compute every results table from raw logs only.
Usage: python scripts/analyze.py <tag> [<tag> ...]
 client log : logs/load_<tag>.jsonl   (user-observed: arrive, first_byte, end, abandon, error)
 server log : logs/server_<tag>.jsonl (pipeline: send, last_token (tokens), retry, giveup, shed, ...)
Percentile definition: numpy.percentile(..., method='linear') over requests that reached that point.
TTFT = first_byte - arrive (user-visible; the answer is verified before release).
Total = end - arrive (completed requests only). Times in ms, percentages one decimal."""
import json, pathlib, sys
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parent.parent
LOGDIR = ROOT / "logs"


def read(p):
    return [json.loads(l) for l in open(p, encoding="utf-8") if l.strip()]


def load(tag):
    c = [r for r in read(LOGDIR / f"load_{tag}.jsonl") if r["event"] != "meta"]
    s = read(LOGDIR / f"server_{tag}.jsonl")
    df = {}
    for r in c:
        d = df.setdefault(r["req"], {"req": r["req"]})
        if r["event"] == "arrive": d["arrive"] = r["t"]
        elif r["event"] == "first_byte": d["first"] = r["t"]
        elif r["event"] in ("end", "abandon", "error"):
            d["last"] = r["t"]; d["outcome"] = r["event"]; d["status"] = r.get("status")
    df = pd.DataFrame(df.values())
    df["ttft_ms"] = (df["first"] - df["arrive"]) * 1000 if "first" in df else np.nan
    df["total_ms"] = (df["last"] - df["arrive"]) * 1000
    tok = {}
    retries = {}
    for r in s:
        if r["event"] == "last_token":
            tok[r["req"]] = tok.get(r["req"], 0) + r.get("prompt_tokens", 0) + r.get("completion_tokens", 0)
        if r["event"] == "retry":
            retries[r["req"]] = retries.get(r["req"], 0) + 1
    df["tokens"] = df["req"].map(tok).fillna(0)
    df["retries"] = df["req"].map(retries).fillna(0)
    return df, s


def pct(x, q):
    x = x.dropna()
    return "not measured" if len(x) == 0 else f"{np.percentile(x, q):.1f}"


def table(tag):
    df, s = load(tag)
    n = len(df)
    done = df[df.outcome == "end"]
    ans = done[done.status.isin(["answered", "abstained"])]
    out = {
        "N requests": n,
        "completed (any status)": len(done),
        "answered/abstained (full model answer)": len(ans),
        "extractive (degraded)": int(done.status.fillna("").str.startswith("extractive").sum()),
        "shed (turned away)": int((done.status == "shed").sum()),
        "declined (unverified)": int((done.status == "declined").sum()),
        "abandoned (gave up)": int((df.outcome == "abandon").sum()),
        "errors": int((df.outcome == "error").sum()),
        "retries (total)": int(df.retries.sum()),
        "n with a first token": int(df.ttft_ms.notna().sum()),
        "TTFT p50 ms": pct(df.ttft_ms, 50),
        "TTFT p95 ms": pct(df.ttft_ms, 95),
        "Total p50 ms": pct(done.total_ms, 50),
        "Total p95 ms": pct(done.total_ms, 95),
        "TTFT p50 ms, full answers only": pct(ans.ttft_ms, 50),
        "TTFT p95 ms, full answers only": pct(ans.ttft_ms, 95),
        "TTFT p50 ms, extractive only": pct(done[done.status.fillna("").str.startswith("extractive")].ttft_ms, 50),
        "tokens/answered request (mean)": f"{ans.tokens.mean():.1f}" if len(ans) else "not measured",
        "abandon %": f"{100 * (df.outcome == 'abandon').mean():.1f}",
        "shed %": f"{100 * (done.status == 'shed').sum() / n:.1f}",
    }
    return pd.Series(out, name=tag)


if __name__ == "__main__":
    t = pd.concat([table(x) for x in sys.argv[1:]], axis=1)
    print(t.to_markdown() if hasattr(t, "to_markdown") else t.to_string())
