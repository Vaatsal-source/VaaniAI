"""Stand-in for the Groq chat-completions API (OpenAI-compatible, SSE streaming).

Behaviours (calibrated from data/calibration.json, fitted from real Groq logs, see README s.2):
  * lognormal time-to-first-token per model, linear per-token decode time
  * load-dependent slowdown: ttft *= 1 + k * (inflight - 1)           (k fitted from only 4/8-way tests)
  * slow-but-successful calls: with prob p_slow, ttft *= slow_mult (no error)
  * stalls: with prob p_stall headers+200 are sent but no token for 60 s (a hang, not an error)
  * failures: with prob p_fail an HTTP 500
  * PER-MODEL limit pools (as observed on Groq): RPM (sliding 60 s), TPM (sliding 60 s, charged
    prompt+max_tokens), RPD and TPD with continuous refill (1 request per 86.4 s, tokens/86400 per s)
  * 429 + retry-after; the limit kind/numbers are in the BODY only (RPM/TPD are NOT in the headers),
    as on the real service
  * `/admin/config` lets the harness change knobs (rpd, tpd, p_fail, ...) and reset state
Content is canned (cites chunk ids found in the prompt). Answer QUALITY is NOT modelled.
"""
import asyncio
import json
import math
import pathlib
import random
import re
import time
from collections import deque

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

ROOT = pathlib.Path(__file__).resolve().parent.parent
CAL = json.loads((ROOT / "data" / "calibration.json").read_text())

S = {
    "seed": 1234, "rpm": 30, "tpm": 8000, "rpd": 1000, "tpd": 200000, "rpd_refill_s": 86.4,
    "retry_after_s": 2, "p_fail": 0.01, "p_stall": 0.005, "p_slow": 0.03, "slow_mult": 8.0,
    "stall_s": 60, "slowdown_per_inflight": CAL["concurrency"]["slowdown_per_inflight"],
    "out_tokens_draft": 180, "time_scale": 1.0,
    # Round 1 charged prompt+max_tokens against the per-minute and daily pools (the then-assumption). Round 2
    # measured on real Groq that it charges tokens actually used, so that is now the default.
    "charge_max_tokens": False,
}
rng = random.Random(S["seed"])
app = FastAPI()


class ModelState:
    def __init__(self):
        self.req_win: deque = deque()
        self.tok_win: deque = deque()
        self.rpd = float(S["rpd"]); self.tpd = float(S["tpd"]); self.t = time.monotonic()
        self.inflight = 0

    def refill(self, now):
        dt = now - self.t
        self.rpd = min(S["rpd"], self.rpd + dt / S["rpd_refill_s"])
        self.tpd = min(S["tpd"], self.tpd + dt * S["tpd"] / 86400.0)
        self.t = now

    def trim(self, now):
        while self.req_win and now - self.req_win[0] > 60:
            self.req_win.popleft()
        while self.tok_win and now - self.tok_win[0][0] > 60:
            self.tok_win.popleft()


ST: dict[str, ModelState] = {}


def st(model) -> ModelState:
    return ST.setdefault(model, ModelState())


def reset():
    global rng
    rng = random.Random(S["seed"])
    ST.clear()


@app.post("/admin/config")
async def admin(req: Request):
    body = await req.json()
    S.update(body.get("set", {}))
    if body.get("reset"):
        reset()
    return S


def _hdrs(m: ModelState, now):
    m.trim(now); m.refill(now)
    used_t = sum(n for _, n in m.tok_win)
    return {"x-ratelimit-limit-requests": str(S["rpd"]), "x-ratelimit-limit-tokens": str(S["tpm"]),
            "x-ratelimit-remaining-requests": str(int(m.rpd)),
            "x-ratelimit-remaining-tokens": str(max(0, S["tpm"] - used_t)),
            "x-ratelimit-reset-requests": f"{S['rpd_refill_s']:.1f}s", "x-ratelimit-reset-tokens": "1s"}


def _429(m, kind, ra, now, model, requested=0):
    h = _hdrs(m, now); h["retry-after"] = str(int(math.ceil(ra)))
    msgs = {"rpm": f"Rate limit reached for model `{model}` on requests per minute (RPM): Limit {S['rpm']}, Used {S['rpm']}, Requested 1. Please try again in {ra:.0f}s.",
            "tpm": f"Rate limit reached for model `{model}` on tokens per minute (TPM): Limit {S['tpm']}, Used {S['tpm']}, Requested {requested}. Please try again in {ra:.0f}s.",
            "rpd": f"Rate limit reached for model `{model}` on requests per day (RPD): Limit {S['rpd']}, Used {S['rpd']}, Requested 1. Please try again in {ra:.0f}s.",
            "tpd": f"Rate limit reached for model `{model}` on tokens per day (TPD): Limit {S['tpd']}, Used {int(S['tpd'] - m.tpd)}, Requested {requested}. Please try again in {ra:.0f}s."}
    return JSONResponse({"error": {"message": msgs[kind], "type": "tokens" if kind in ("tpm", "tpd") else "requests",
                                   "code": "rate_limit_exceeded"}}, status_code=429, headers=h)


def _canned(messages, max_tokens):
    text = "\n".join(m["content"] for m in messages)
    sysm = messages[0]["content"] if messages else ""
    if "[[STEP:classify]]" in sysm:
        return json.dumps({"intent": "factual", "paper": "attention", "section": "", "queries": ["standin query"]})
    if "[[STEP:verify]]" in sysm:
        return json.dumps({"supported": True, "issues": []})
    if "[[STEP:rewrite]]" in sysm:
        return "standin rewritten query"
    ids = re.findall(r"\[C:([a-z]+:\d+)\]", text)[:2]
    cites = " ".join(f"[C:{i}]" for i in ids)
    body = ("According to the retrieved passages, the mechanism is described in detail and the "
            "relevant quantities are defined there. ") * 6
    words = body.split()
    n = max(8, min(S["out_tokens_draft"], max_tokens) * 3 // 4)
    return " ".join(words[:n]) + (" " + cites if cites else "")


@app.get("/v1/models")
async def models():
    return {"data": [{"id": m} for m in CAL["models"]]}


@app.post("/v1/chat/completions")
async def chat(req: Request):
    body = await req.json()
    now = time.monotonic()
    model = body.get("model", "openai/gpt-oss-120b")
    cal = CAL["models"].get(model) or CAL["models"]["openai/gpt-oss-120b"]
    m = st(model)
    msgs = body["messages"]; max_tokens = int(body.get("max_tokens", 256))
    ptok = sum(len(x["content"]) for x in msgs) // 4 + 8
    m.trim(now); m.refill(now)
    text = _canned(msgs, max_tokens)
    ctok = max(1, len(text) // 4)
    cost = ptok + (max_tokens if S["charge_max_tokens"] else ctok)
    if len(m.req_win) >= S["rpm"]:
        return _429(m, "rpm", S["retry_after_s"], now, model)
    used = sum(n for _, n in m.tok_win)
    if used + cost > S["tpm"]:
        wait = (m.tok_win[0][0] + 60 - now) if m.tok_win else 1.0
        return _429(m, "tpm", max(1.0, wait), now, model, cost)
    if m.rpd < 1:
        return _429(m, "rpd", S["rpd_refill_s"], now, model)
    if m.tpd < cost:
        return _429(m, "tpd", (cost - m.tpd) * 86400.0 / S["tpd"], now, model, cost)
    m.rpd -= 1; m.tpd -= cost
    m.req_win.append(now); m.tok_win.append((now, cost))
    m.inflight += 1
    try:
        ts = S["time_scale"]
        if rng.random() < S["p_fail"]:
            await asyncio.sleep(0.05 * ts)
            m.inflight -= 1
            return JSONResponse({"error": {"message": "internal error", "type": "server_error"}}, status_code=500)
        ttft = math.exp(rng.gauss(cal["ttft_mu"], cal["ttft_sigma"])) * (1 + S["slowdown_per_inflight"] * (m.inflight - 1))
        if rng.random() < S["p_slow"]:
            ttft *= S["slow_mult"]
        stall = rng.random() < S["p_stall"]
        hdrs = _hdrs(m, now)
    except Exception:
        m.inflight -= 1
        raise

    async def gen():
        try:
            await asyncio.sleep(ttft / 1000 * ts)
            if stall:                       # slow *without failing*: 200 sent, then silence
                await asyncio.sleep(S["stall_s"])
            words = text.split(" ")
            for i, w in enumerate(words):
                chunk = {"choices": [{"delta": {"content": (w if i == 0 else " " + w)}}]}
                yield f"data: {json.dumps(chunk)}\n\n"
                await asyncio.sleep(cal["ms_per_token"] * 1.33 / 1000 * ts * (1 + S["slowdown_per_inflight"] * (m.inflight - 1)))
            usage = {"prompt_tokens": ptok, "completion_tokens": ctok, "total_tokens": ptok + ctok}
            yield f"data: {json.dumps({'choices': [], 'usage': usage})}\n\n"
            yield "data: [DONE]\n\n"
        finally:
            m.inflight -= 1

    return StreamingResponse(gen(), media_type="text/event-stream", headers=hdrs)
