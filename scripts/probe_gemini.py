"""Small, quota-friendly look at the backup provider (Gemini, OpenAI-compatible endpoint).
Writes logs/gemini_probe_<time>.jsonl. About 30 requests in total; it never tries to hit a limit.

  python scripts/probe_gemini.py
"""
import asyncio, json, os, pathlib, sys, time
import httpx, yaml
from dotenv import load_dotenv

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
CFG = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
BASE = CFG["providers"]["gemini"]["base_url"].rstrip("/")
H = {"Authorization": f"Bearer {os.environ['GEMINI_API_KEY']}", "Content-Type": "application/json"}
OUT = ROOT / "logs" / f"gemini_probe_{int(time.time())}.jsonl"
MODELS = [CFG["fallback"]["models"]["small"], CFG["fallback"]["models"]["large"]]
PROMPT = "Reply with the single word: ok"


def w(rec):
    with open(OUT, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


async def one(c, model, tag, content=PROMPT, system=None, max_tokens=60, extra=None):
    t0 = time.perf_counter()
    msgs = ([{"role": "system", "content": system}] if system else []) + [{"role": "user", "content": content}]
    body = {"model": model, "messages": msgs, "max_tokens": max_tokens, "temperature": 0, "stream": True,
            "stream_options": {"include_usage": True}}
    body.update(extra or {})
    rec = {"tag": tag, "model": model, "extra": extra, "t_wall": time.time()}
    try:
        async with c.stream("POST", f"{BASE}/chat/completions", headers=H, json=body) as r:
            rec["status"] = r.status_code
            rec["headers"] = {k: v for k, v in r.headers.items() if k.startswith("x-ratelimit") or k == "retry-after"}
            if r.status_code != 200:
                rec["body"] = (await r.aread()).decode()[:600]
            else:
                first, usage, text = None, None, []
                async for line in r.aiter_lines():
                    if line.startswith("data:") and line[5:].strip() != "[DONE]":
                        ch = json.loads(line[5:])
                        for cc in ch.get("choices", []):
                            piece = cc.get("delta", {}).get("content")
                            if piece:
                                if first is None:
                                    first = time.perf_counter()
                                text.append(piece)
                        usage = ch.get("usage") or usage
                rec["ttft_ms"] = None if first is None else (first - t0) * 1000
                rec["usage"] = usage
                rec["text"] = "".join(text)[:300]
    except Exception as e:
        rec["status"], rec["error"] = "exc", repr(e)
    rec["total_ms"] = (time.perf_counter() - t0) * 1000
    w(rec)
    return rec


async def main():
    async with httpx.AsyncClient(timeout=httpx.Timeout(60, connect=10)) as c:
        for m in MODELS:
            for i in range(5):
                r = await one(c, m, "latency")
                print(m, r.get("status"), r.get("ttft_ms") and round(r["ttft_ms"]), r.get("usage"), (r.get("body") or "")[:150], flush=True)
                await asyncio.sleep(4)
            # does the reasoning knob exist, and how many hidden tokens does a tiny question cost?
            for eff in ("none", "low"):
                r = await one(c, m, f"reasoning_{eff}", "What is 17 times 23? Answer with just the number.", extra={"reasoning_effort": eff})
                print(m, "reasoning", eff, r.get("status"), r.get("text"), r.get("usage"), (r.get("body") or "")[:150], flush=True)
                await asyncio.sleep(4)
            r = await one(c, m, "json_mode", 'Return JSON {"ok": true}', extra={"response_format": {"type": "json_object"}})
            print(m, "json", r.get("status"), r.get("text"), (r.get("body") or "")[:150], flush=True)
            await asyncio.sleep(4)
    print("wrote", OUT)

asyncio.run(main())
