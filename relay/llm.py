"""Raw-httpx OpenAI-compatible chat client (works for Groq, Gemini-compat and the stand-in).

Logs per attempt: send, first_token, last_token, http_429 (+ rate-limit headers), retry, giveup.
Retries are a hand-written loop with exponential backoff + full jitter and a rolling
retry budget so retries cannot amplify an overload (see README section 8).
"""
import asyncio
import json
import os
import random
import re
import time
from collections import deque

import httpx

from .events import EventLog
from .limiter import DailyBudgetExhausted, Limiter, Shed

LIMIT_RE = re.compile(r"\((TPD|TPM|RPM|RPD)\):\s*Limit\s+(\d+)(?:,\s*Used\s+(\d+))?")
RL_HEADERS = ("x-ratelimit-limit-requests", "x-ratelimit-limit-tokens",
              "x-ratelimit-remaining-requests", "x-ratelimit-remaining-tokens",
              "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens", "retry-after")


class RetryBudget:
    """Retries allowed <= frac * first attempts over a rolling window."""

    def __init__(self, frac: float, window: float = 30.0):
        self.frac, self.window = frac, window
        self.firsts: deque = deque()
        self.retries: deque = deque()

    def _trim(self, now):
        for dq in (self.firsts, self.retries):
            while dq and now - dq[0] > self.window:
                dq.popleft()

    def note_first(self):
        self.firsts.append(time.monotonic())

    def allow_retry(self) -> bool:
        now = time.monotonic()
        self._trim(now)
        if len(self.retries) + 1 <= max(1, self.frac * len(self.firsts)):
            self.retries.append(now)
            return True
        return False


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, cfg: dict, provider: str, log: EventLog, limiters: dict):
        p = cfg["providers"][provider]
        self.base = p["base_url"].rstrip("/")
        key = os.environ.get(p["key_env"], "") if p["key_env"] else "standin"
        self.headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        self.log, self.limiters = log, limiters   # one Limiter per model: Groq limits are per model
        self.rc = cfg["retries"]
        self.budget = RetryBudget(self.rc["retry_budget_frac"])
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(connect=5, read=30, write=10, pool=None),
                                      limits=httpx.Limits(max_connections=200))
        self.total_usage = {"prompt": 0, "completion": 0}

    async def aclose(self):
        await self.http.aclose()

    async def chat(self, req_id: str, step: str, model: str, messages: list, *,
                   max_tokens=400, temperature=0.0, priority=1, deadline=None,
                   est_tokens=None, on_token=None, json_mode=False) -> dict:
        """Returns {text, usage, ttft_ms}. Raises Shed / LLMError."""
        est = est_tokens or (sum(len(m["content"]) for m in messages) // 3 + max_tokens)
        self.budget.note_first()
        lim = self.limiters[model]
        attempt = 0
        while True:
            attempt += 1
            await lim.acquire(est, priority, deadline)  # may raise Shed
            body = {"model": model, "messages": messages, "max_tokens": max_tokens,
                    "temperature": temperature, "stream": True,
                    "stream_options": {"include_usage": True}}
            if model.startswith("openai/gpt-oss"):
                body["reasoning_effort"] = "low"
            if json_mode:
                body["response_format"] = {"type": "json_object"}
            self.log.emit(req_id, "send", step=step, model=model, attempt=attempt, est_tokens=est)
            try:
                remaining = None if deadline is None else deadline - time.monotonic()
                if remaining is not None and remaining <= 0:
                    self.log.emit(req_id, "giveup", step=step, reason="deadline", attempt=attempt)
                    raise Shed("deadline")
                # slow-without-failing: a call that streams nothing is cut at min(call_timeout, remaining)
                tmo = min(self.rc.get("call_timeout_s", 12), remaining) if remaining is not None else self.rc.get("call_timeout_s", 12)
                try:
                    out = await asyncio.wait_for(self._stream(req_id, step, body, on_token, lim), tmo)
                except asyncio.TimeoutError:
                    self.log.emit(req_id, "call_timeout", step=step, after_s=round(tmo, 2), attempt=attempt)
                    raise _Retryable("call_timeout", 0, None, refund=False)
                lim.refund_tokens(est, out["usage"]["total"]); lim.add_usage(out["usage"]["total"])
                return out
            except _Retryable as e:
                lim.release(est) if e.refund else None
                if e.retry_after is not None or e.status == 429:
                    lim.note_429(e.retry_after)
                remaining = None if deadline is None else deadline - time.monotonic()
                backoff = min(self.rc["max_backoff_s"], self.rc["base_backoff_s"] * 2 ** (attempt - 1))
                wait = max(e.retry_after or 0, random.uniform(0, backoff))
                if attempt >= self.rc["max_attempts"] or (remaining is not None and wait >= remaining):
                    self.log.emit(req_id, "giveup", step=step, reason=e.reason, attempt=attempt)
                    raise LLMError(e.reason)
                if not self.budget.allow_retry():
                    self.log.emit(req_id, "giveup", step=step, reason="retry_budget", attempt=attempt)
                    raise LLMError("retry_budget")
                self.log.emit(req_id, "retry", step=step, attempt=attempt, reason=e.reason,
                              backoff_ms=round(wait * 1000, 1))
                await asyncio.sleep(wait)

    async def _stream(self, req_id, step, body, on_token, lim):
        t_send = time.perf_counter()
        first = None
        text, usage = [], {"prompt": 0, "completion": 0, "total": 0}
        prov = {}   # provider-reported timing (Groq usage: queue_time/prompt_time/completion_time/total_time, seconds)
        try:
            async with self.http.stream("POST", f"{self.base}/chat/completions",
                                        headers=self.headers, json=body) as r:
                hdrs = {k: r.headers.get(k) for k in RL_HEADERS if r.headers.get(k) is not None}
                if r.status_code == 200:
                    lim.observe_headers(hdrs)
                if r.status_code == 429:
                    ra = r.headers.get("retry-after")
                    await r.aread()
                    self.log.emit(req_id, "http_429", step=step, headers=hdrs, body=r.text[:300])
                    m = LIMIT_RE.search(r.text)
                    if m:   # limit kind + numbers are only in the body, not the headers
                        kind, limit, used = m.group(1), float(m.group(2)), float(m.group(3) or 0)
                        lim.learn_limit(kind, limit, used, float(ra) if ra else None)
                        if kind.upper() in ("TPD", "RPD"):
                            self.log.emit(req_id, "daily_limit", step=step, kind=kind, limit=limit, used=used,
                                          retry_after=ra)
                            raise DailyBudgetExhausted(f"{kind}_exhausted", float(ra) if ra else 0)
                    raise _Retryable("429", 429, float(ra) if ra else None, refund=True)
                if r.status_code >= 500:
                    await r.aread()
                    raise _Retryable(f"http_{r.status_code}", r.status_code, None, refund=True)
                if r.status_code != 200:
                    await r.aread()
                    self.log.emit(req_id, "giveup", step=step, reason=f"http_{r.status_code}", body=r.text[:300])
                    raise LLMError(f"http_{r.status_code}: {r.text[:200]}")
                async for line in r.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    ch = json.loads(data)
                    if ch.get("usage"):
                        u = ch["usage"]
                    elif ch.get("x_groq", {}).get("usage"):
                        u = ch["x_groq"]["usage"]
                    else:
                        u = None
                    if u:
                        prov = {k: round(u[k] * 1000, 1) for k in ("queue_time", "total_time") if k in u}
                        usage = {"prompt": u.get("prompt_tokens", 0), "completion": u.get("completion_tokens", 0),
                                 "total": u.get("total_tokens", 0)}
                    for c in ch.get("choices", []):
                        piece = c.get("delta", {}).get("content")
                        if piece:
                            if first is None:
                                first = time.perf_counter()
                                self.log.emit(req_id, "first_token", step=step,
                                              ttft_ms=round((first - t_send) * 1000, 1))
                            text.append(piece)
                            if on_token:
                                on_token(piece)
        except (httpx.ReadTimeout, httpx.ConnectTimeout, httpx.RemoteProtocolError, httpx.ConnectError) as e:
            raise _Retryable(type(e).__name__, 0, None, refund=True)
        t_last = time.perf_counter()
        self.log.emit(req_id, "last_token", step=step, total_ms=round((t_last - t_send) * 1000, 1),
                      prompt_tokens=usage["prompt"], completion_tokens=usage["completion"],
                      provider_queue_ms=prov.get("queue_time"), provider_total_ms=prov.get("total_time"))
        self.total_usage["prompt"] += usage["prompt"]
        self.total_usage["completion"] += usage["completion"]
        return {"text": "".join(text), "usage": usage,
                "ttft_ms": None if first is None else (first - t_send) * 1000}


class _Retryable(Exception):
    def __init__(self, reason, status, retry_after, refund=False):
        super().__init__(reason)
        self.reason, self.status, self.retry_after, self.refund = reason, status, retry_after, refund
