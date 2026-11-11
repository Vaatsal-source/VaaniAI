"""Relay HTTP service. Env: RELAY_PROVIDER (groq|standin), RELAY_LOG (jsonl path),
RELAY_RETRIEVAL (json overrides), RELAY_LIMITS (json overrides).
GET /ask?q=...&req=...&deadline=...  -> SSE stream of the VERIFIED answer text.
A client disconnect cancels the handler (logged as 'abandon' by the pipeline)."""
import asyncio
import json
import os
import time

from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from .runtime import build, load_cfg

cfg = load_cfg()
cfg["retries"].update(json.loads(os.environ.get("RELAY_RETRIES", "{}")))
if os.environ.get("RELAY_LARGE"):
    cfg["models"]["large"] = os.environ["RELAY_LARGE"]
pipe, log = build(cfg, os.environ.get("RELAY_PROVIDER", "standin"), os.environ.get("RELAY_LOG"),
                  json.loads(os.environ.get("RELAY_RETRIEVAL", "{}")), json.loads(os.environ.get("RELAY_LIMITS", "{}")))
app = FastAPI()


@app.on_event("startup")
async def _lag_monitor():
    """Log event-loop stalls > 100 ms. A stalled loop (CPU starvation, GC, laptop power state) inflates
    every span at once; without this we could not tell it apart from a slow provider."""
    async def mon():
        while True:
            t = time.perf_counter()
            await asyncio.sleep(0.05)
            lag = time.perf_counter() - t - 0.05
            if lag > 0.1:
                log.emit("-", "loop_lag", lag_ms=round(lag * 1000, 1))
    asyncio.get_running_loop().create_task(mon())


@app.get("/health")
async def health():
    return {"ok": True, "daily_left": pipe.lim.daily_left(), "tpd_used": pipe.lim.tpd_used}


@app.get("/ask")
async def ask(q: str, req: str, deadline: float | None = None):
    async def gen():
        res = await pipe.handle(req, q, deadline)
        yield f"event: status\ndata: {json.dumps({'status': res['status'], 'level': res['level']})}\n\n"
        for w in res["text"].split(" "):
            yield f"data: {json.dumps(w + ' ')}\n\n"
        yield "event: end\ndata: {}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")
