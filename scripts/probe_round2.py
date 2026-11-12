"""Second round of real-Groq measurements, deliberately tiny so the free quota is not touched.

  python scripts/probe_round2.py accounting     # how many tokens does Groq charge per request?
  python scripts/probe_round2.py concurrency    # 4/8/12/16 requests in flight at once, twice each
  python scripts/probe_round2.py quiet          # a long, slow trickle to see whether failures ever happen

Every request is a few dozen tokens. Raw results go to logs/groq_probe2_<name>_<time>.jsonl.
An event-loop lag monitor runs alongside so a stalled laptop is not mistaken for a slow provider.
"""
import asyncio, json, os, pathlib, sys, time
import httpx, yaml
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
BASE = CFG["providers"]["groq"]["base_url"]
H = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}", "Content-Type": "application/json"}
SMALL, LARGE = CFG["models"]["small"], CFG["models"]["large"]
PROMPT = "Reply with the single word: ok"
OUT = None
LAG = {"max": 0.0, "n_over_100": 0, "samples": []}


def w(rec):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


async def lag_monitor():
    while True:
        t = time.perf_counter()
        await asyncio.sleep(0.05)
        late = (time.perf_counter() - t - 0.05) * 1000
        LAG["max"] = max(LAG["max"], late)
        if late > 100:
            LAG["n_over_100"] += 1
            w({"tag": "loop_lag", "t": time.time(), "lag_ms": round(late, 1)})


async def one(c, model, tag, max_tokens=40, stream=True, extra=None):
    t0 = time.perf_counter()
    body = {"model": model, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": max_tokens,
            "temperature": 0, "stream": stream}
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    if stream:
        body["stream_options"] = {"include_usage": True}
    body.update(extra or {})
    rec = {"tag": tag, "model": model, "max_tokens": max_tokens, "t_wall": time.time()}
    try:
        if stream:
            async with c.stream("POST", f"{BASE}/chat/completions", headers=H, json=body) as r:
                rec["status"] = r.status_code
                rec["headers"] = {k: v for k, v in r.headers.items() if k.startswith("x-ratelimit") or k == "retry-after"}
                if r.status_code != 200:
                    rec["body"] = (await r.aread()).decode()[:400]
                else:
                    first = usage = None
                    async for line in r.aiter_lines():
                        if line.startswith("data:") and line[5:].strip() != "[DONE]":
                            ch = json.loads(line[5:])
                            if first is None and ch.get("choices") and ch["choices"][0]["delta"].get("content"):
                                first = time.perf_counter()
                            usage = ch.get("usage") or ch.get("x_groq", {}).get("usage") or usage
                    rec["ttft_ms"] = None if first is None else (first - t0) * 1000
                    rec["usage"] = usage
        else:
            r = await c.post(f"{BASE}/chat/completions", headers=H, json=body)
            rec["status"] = r.status_code
            rec["headers"] = {k: v for k, v in r.headers.items() if k.startswith("x-ratelimit") or k == "retry-after"}
            if r.status_code == 200:
                rec["usage"] = r.json().get("usage")
            else:
                rec["body"] = r.text[:400]
    except Exception as e:
        rec["status"] = "exc"; rec["error"] = repr(e)
    rec["total_ms"] = (time.perf_counter() - t0) * 1000
    w(rec)
    return rec


async def accounting(c):
    """Back-to-back calls with very different max_tokens but the same tiny prompt and tiny real output.
    charge = remaining_before + refill(dt) - remaining_after. If Groq charges prompt+max_tokens up front,
    the charge tracks max_tokens; if it charges real usage, the charge stays small whatever max_tokens is."""
    await asyncio.sleep(1)
    prev = await one(c, SMALL, "acct_prime", 20, stream=False)
    rows = []
    # 10 s between calls: the per-minute bucket (8000 tokens, refilling ~133/s) is full again each time,
    # so charge = 8000 - remaining_after, with no refill arithmetic needed.
    for mt in (20, 800, 4000, 200, 1500, 20, 4000, 800, 200, 1500):
        await asyncio.sleep(10)
        r = await one(c, SMALL, f"acct_{mt}", mt, stream=False)
        rows.append(r)
    print("wrote", OUT)


async def concurrency(c):
    for rep in (1, 2):
        for k in (4, 8, 12, 16):
            res = await asyncio.gather(*[one(c, SMALL, f"conc{k}") for _ in range(k)])
            ok = sorted(r["ttft_ms"] for r in res if r.get("status") == 200 and r.get("ttft_ms"))
            print(f"rep{rep} conc{k}: ok={len(ok)}/{k} median ttft={ok[len(ok)//2] if ok else None}", flush=True)
            await asyncio.sleep(65)      # let the 30/min window drain so batches do not collide
    print("wrote", OUT)


async def quiet(c, n_small=60, n_large=20, gap=11.0):
    """~5 requests a minute for ~11 minutes: far below every limit, to see whether the service ever fails
    or stalls when nothing is stressing it."""
    plan = [(SMALL, "quiet")] * n_small
    plan = [p for i, p in enumerate(plan)]
    k = n_small // n_large
    seq = []
    for i, p in enumerate(plan):
        seq.append(p)
        if (i + 1) % k == 0 and sum(1 for s in seq if s[0] == LARGE) < n_large:
            seq.append((LARGE, "quiet"))
    for i, (m, tag) in enumerate(seq):
        await one(c, m, tag, 30)
        await asyncio.sleep(gap)
    print("wrote", OUT)


async def main():
    global OUT
    which = sys.argv[1]
    OUT = ROOT / "logs" / f"groq_probe2_{which}_{int(time.time())}.jsonl"
    async with httpx.AsyncClient(timeout=httpx.Timeout(30, connect=10)) as c:
        mon = asyncio.create_task(lag_monitor())
        await {"accounting": accounting, "concurrency": concurrency, "quiet": quiet}[which](c)
        mon.cancel()
    w({"tag": "summary", "max_loop_lag_ms": round(LAG["max"], 1), "lag_events_over_100ms": LAG["n_over_100"]})


if __name__ == "__main__":
    asyncio.run(main())
