"""Quota-aware real-Groq calibration. Writes raw logs to logs/groq_probe_*.jsonl.

Phases (each capped; total <= ~90 requests so we never burn the daily quota):
  0. GET /models (what's available) and one tiny call per model -> read x-ratelimit-* headers
  1. latency: N sequential streamed calls per model (short prompt, ~60-token output)
  2. concurrency: small parallel bursts (4, 8) on the SMALL model only
  3. limit hit: one deliberate burst of 40 tiny requests on the SMALL model to trigger a 429,
     capturing the status, body, retry-after and the headers.
Never probes the large model's daily limit (it only has ~1K RPD on free tier).
"""
import asyncio, json, os, sys, time, pathlib
import httpx, yaml
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
CFG = yaml.safe_load((ROOT / "config.yaml").read_text())
BASE = CFG["providers"]["groq"]["base_url"]
KEY = os.environ["GROQ_API_KEY"]
H = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
OUT = ROOT / "logs" / f"groq_probe_{int(time.time())}.jsonl"
PROMPT = "In one sentence, what is scaled dot-product attention?"


def w(rec):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


async def one(c, model, tag, max_tokens=200):
    t0 = time.perf_counter(); first = None; usage = None
    body = {"model": model, "messages": [{"role": "user", "content": PROMPT}], "max_tokens": max_tokens,
            "temperature": 0, "reasoning_effort": "low", "stream": True, "stream_options": {"include_usage": True}}
    try:
        async with c.stream("POST", f"{BASE}/chat/completions", headers=H, json=body) as r:
            hd = {k: v for k, v in r.headers.items() if k.startswith("x-ratelimit") or k == "retry-after"}
            if r.status_code != 200:
                txt = (await r.aread()).decode()[:400]
                w({"tag": tag, "model": model, "t0": t0, "status": r.status_code, "headers": hd, "body": txt,
                   "total_ms": (time.perf_counter() - t0) * 1000})
                return r.status_code
            async for line in r.aiter_lines():
                if line.startswith("data:") and line[5:].strip() != "[DONE]":
                    ch = json.loads(line[5:])
                    if first is None and ch.get("choices") and ch["choices"][0]["delta"].get("content"):
                        first = time.perf_counter()
                    usage = ch.get("usage") or ch.get("x_groq", {}).get("usage") or usage
            t1 = time.perf_counter()
            w({"tag": tag, "model": model, "t0": t0, "status": 200, "headers": hd,
               "ttft_ms": None if first is None else (first - t0) * 1000,
               "total_ms": (t1 - t0) * 1000, "usage": usage})
            return 200
    except Exception as e:
        w({"tag": tag, "model": model, "t0": t0, "status": "exc", "error": repr(e)})
        return "exc"


async def main(n_lat=15):
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(f"{BASE}/models", headers=H)
        w({"tag": "models", "status": r.status_code,
           "models": [m["id"] for m in r.json().get("data", [])]})
        print("models:", [m["id"] for m in r.json().get("data", [])])
        for m in (CFG["models"]["small"], CFG["models"]["large"]):
            for i in range(n_lat):
                await one(c, m, f"latency:{m}")
                await asyncio.sleep(2.2)   # stay far below 30 RPM
        small = CFG["models"]["small"]
        for k in (4, 8):
            await asyncio.gather(*[one(c, small, f"conc{k}") for _ in range(k)])
            await asyncio.sleep(10)
        if "--hit-limit" in sys.argv:
            res = await asyncio.gather(*[one(c, small, "limit_hit", 5) for _ in range(40)])
            print("limit_hit statuses:", {s: res.count(s) for s in set(res)})
    print("wrote", OUT)


if __name__ == "__main__":
    asyncio.run(main())
