"""Open-loop load generator (separate process). Arrivals follow a schedule regardless of completions.
Writes one JSONL per run: arrive, first_byte, end, abandon, error  (time.perf_counter()).
Shapes (all seeded):
  steady   : Poisson arrivals at --rate for --duration
  burst    : --n requests inside --window seconds (a sudden spike), then silence
  overload : Poisson arrivals at --rate (well above capacity) for --duration
Each simulated user abandons after --patience seconds without a complete answer.
Question mix: sampled from data/questions.json plus 'loopy' variants (section-hint questions)."""
import argparse, asyncio, json, pathlib, random, sys, time
import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent


def schedule(shape, a, rng):
    ts = []
    if shape == "burst":
        ts = sorted(rng.uniform(0, a.window) for _ in range(a.n))
    else:
        t = 0.0
        while t < a.duration:
            t += rng.expovariate(a.rate)
            if t < a.duration:
                ts.append(t)
    return ts


async def user(c, base, i, q, patience, out, t0):
    rid = f"{out['tag']}-{i:04d}"
    arrive = time.perf_counter()
    rec = lambda ev, **k: out["f"].write(json.dumps({"t": time.perf_counter(), "req": rid, "event": ev, **k}) + "\n")
    rec("arrive", sched=arrive - t0, q=q[:60])
    status, first = None, None

    async def go():
        nonlocal status, first
        async with c.stream("GET", f"{base}/ask", params={"q": q, "req": rid, "deadline": max(1.0, patience - 3.0)}) as r:  # server gives up 3 s before the user does
            ev = None
            async for line in r.aiter_lines():
                if line.startswith("event:"):
                    ev = line[6:].strip()
                elif line.startswith("data:"):
                    if ev == "status":
                        status = json.loads(line[5:])["status"]
                    elif first is None and ev is None:
                        first = time.perf_counter(); rec("first_byte")
                    if ev == "end":
                        return
                    if ev == "status":
                        ev = None
    try:
        await asyncio.wait_for(go(), patience)
        rec("end", status=status)
    except asyncio.TimeoutError:
        rec("abandon", status=status, after_first_byte=first is not None)
    except Exception as e:
        rec("error", error=repr(e))


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shape", required=True, choices=["steady", "burst", "overload"])
    ap.add_argument("--base", default="http://127.0.0.1:8100")
    ap.add_argument("--rate", type=float, default=0.03); ap.add_argument("--duration", type=float, default=120)
    ap.add_argument("--n", type=int, default=20); ap.add_argument("--window", type=float, default=5)
    ap.add_argument("--patience", type=float, default=25); ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--tag", required=True)
    ap.add_argument("--drain", type=float, default=0, help="extra seconds to wait after last arrival")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    qs = json.load(open(ROOT / "data" / "questions.json"))
    pool = [q["q"] for q in qs]
    pool += ["In Section 3.2.2 of the Transformer paper, how is multi-head attention defined?",
             "In section 2.2 of the dynamic chunking paper, what does dechunking do?"]
    ts = schedule(a.shape, a, rng)
    path = ROOT / "logs" / f"load_{a.tag}.jsonl"
    out = {"f": open(path, "w", buffering=1), "tag": a.tag}
    out["f"].write(json.dumps({"event": "meta", "args": vars(a), "n": len(ts), "perf0": time.perf_counter()}) + "\n")
    async with httpx.AsyncClient(timeout=None, limits=httpx.Limits(max_connections=1000)) as c:
        t0 = time.perf_counter(); tasks = []
        for i, st in enumerate(ts):
            await asyncio.sleep(max(0, st - (time.perf_counter() - t0)))
            tasks.append(asyncio.create_task(user(c, a.base, i, rng.choice(pool), a.patience, out, t0)))
        await asyncio.gather(*tasks)
    out["f"].close()
    print("done", len(ts), "requests ->", path)

asyncio.run(main())
