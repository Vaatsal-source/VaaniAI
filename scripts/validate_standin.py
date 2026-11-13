"""Does the stand-in behave like the real service under concurrency? Same tiny request, 4/8/12/16 at once, repeated.

  python scripts/validate_standin.py            # writes logs/standin_validation.json

Compare the printed medians with scripts/make_tables.py section R2 (the real Groq concurrency probe)."""
import asyncio, json, pathlib, subprocess, sys, time
import httpx, numpy as np

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable
PORT = 8097
MODEL = "openai/gpt-oss-20b"


async def one(c):
    t0 = time.perf_counter(); first = None
    body = {"model": MODEL, "messages": [{"role": "user", "content": "Reply with the single word: ok"}], "max_tokens": 40, "stream": True}
    async with c.stream("POST", f"http://127.0.0.1:{PORT}/v1/chat/completions", json=body) as r:
        async for line in r.aiter_lines():
            if first is None and line.startswith("data:") and '"content"' in line:
                first = time.perf_counter()
    return None if first is None else (first - t0) * 1000


async def main(reps=12):
    p = subprocess.Popen([PY, "-m", "uvicorn", "standin.server:app", "--port", str(PORT), "--log-level", "warning"], cwd=ROOT, stdout=subprocess.DEVNULL)
    try:
        for _ in range(100):
            try:
                if httpx.get(f"http://127.0.0.1:{PORT}/v1/models", timeout=1).status_code == 200:
                    break
            except Exception:
                time.sleep(0.2)
        conf = httpx.post(f"http://127.0.0.1:{PORT}/admin/config", json={"set": {"rpm": 10000, "tpm": 10**7, "rpd": 10**6, "tpd": 10**9, "p_fail": 0, "p_stall": 0, "p_slow": 0}, "reset": True}).json()
        out = {}
        async with httpx.AsyncClient(timeout=60) as c:
            for k in (1, 4, 8, 12, 16):
                xs = []
                for _ in range(reps if k > 1 else reps * 4):
                    xs += [x for x in await asyncio.gather(*[one(c) for _ in range(k)]) if x]
                    await asyncio.sleep(0.2)
                out[k] = {"n": len(xs), "p50": round(float(np.median(xs))), "p90": round(float(np.percentile(xs, 90)))}
                print(f"{k:2d} in flight: median {out[k]['p50']} ms, p90 {out[k]['p90']} ms (n={len(xs)})", flush=True)
        (ROOT / "logs" / "standin_validation.json").write_text(json.dumps({"slowdown_per_inflight": conf["slowdown_per_inflight"], "results": out}, indent=1), encoding="utf-8")
    finally:
        p.terminate()


asyncio.run(main())
