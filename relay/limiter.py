"""Hand-written admission control: token buckets for RPM/TPM, a daily counter, and a
priority queue. This is the overload policy (see README section 5).

Priorities (lower = served first): 0 = retry/continuation of an in-flight request,
1 = new interactive request, 2 = low-value (e.g. optional LLM verify).

Overload policy, in order of what happens first as pressure grows:
  1. Queue (bounded by each request's own deadline).
  2. Degrade: skip optional LLM-verify, shrink top_k  -- never skip the deterministic
     citation check, never answer without retrieved evidence.
  3. Shed: if the expected wait exceeds the remaining deadline, refuse early and honestly.
"""
import asyncio
import heapq
import itertools
import time


class Bucket:
    """Continuous-refill token bucket. capacity per `period` seconds."""

    def __init__(self, capacity: float, period: float = 60.0, clock=time.monotonic):
        self.capacity = float(capacity)
        self.period = period
        self.clock = clock
        self.level = float(capacity)
        self.last = clock()

    def _refill(self):
        now = self.clock()
        self.level = min(self.capacity, self.level + (now - self.last) * self.capacity / self.period)
        self.last = now

    def try_take(self, n: float) -> bool:
        self._refill()
        if self.level >= n:
            self.level -= n
            return True
        return False

    def wait_time(self, n: float) -> float:
        self._refill()
        if self.level >= n:
            return 0.0
        return (n - self.level) * self.period / self.capacity

    def refund(self, n: float):
        self.level = min(self.capacity, self.level + n)

    def resize(self, capacity: float):
        self._refill()
        self.capacity = float(capacity)
        self.level = min(self.level, self.capacity)


class Shed(Exception):
    """Raised when admission is refused (honest 'try later')."""

    def __init__(self, reason: str, retry_after: float = 0.0):
        super().__init__(reason)
        self.reason = reason
        self.retry_after = retry_after


class DailyBudgetExhausted(Shed):
    pass


class Limiter:
    def __init__(self, rpm, tpm, rpd, daily_reserve_frac=0.1, clock=time.monotonic):
        self.clock = clock
        self.req = Bucket(rpm, 60, clock)
        self.tok = Bucket(tpm, 60, clock)
        self.rpd = rpd
        self.used_today = 0
        self.reserve = int(rpd * daily_reserve_frac)
        self._q: list = []
        self._seq = itertools.count()
        self._wake = asyncio.Event()
        self._task: asyncio.Task | None = None
        self.cooldown_until = 0.0  # set from a provider 429 retry-after
        self.tpd = None            # tokens/day: not exposed in headers, learned from a 429 body
        self.tpd_used = 0
        self.tpd_block_until = 0.0
        # Groq appears to charge prompt+max_tokens up front and not refund the unused part, so
        # by default we do NOT refund on success (conservative). Failed/rejected calls are released.
        self.refund_on_success = False

    # ---- provider feedback (limits are discovered, not hard-coded) ----
    def observe_headers(self, h: dict):
        def num(k):
            try:
                return float(h[k])
            except (KeyError, ValueError, TypeError):
                return None
        lr, lt, ld = num("x-ratelimit-limit-requests"), num("x-ratelimit-limit-tokens"), None
        if lt:
            self.tok.resize(lt)
        # Groq's *requests* limit header is per-day (RPD); do not treat it as RPM.
        if lr:
            self.rpd = int(lr)

    def note_429(self, retry_after: float | None):
        ra = retry_after if retry_after is not None else 2.0
        self.cooldown_until = max(self.cooldown_until, self.clock() + ra)

    def learn_limit(self, kind: str, limit: float, used: float, retry_after: float | None):
        """Limits that are NOT in response headers are learned from the 429 body, e.g.
        'tokens per day (TPD): Limit 200000, Used 199538' or 'requests per minute (RPM): Limit 30'.
        Daily kinds (TPD/RPD) never become a short cooldown: they flip the daily-exhausted path."""
        kind = kind.upper()
        if kind == "TPD":
            self.tpd, self.tpd_used = int(limit), int(used)
            self.tpd_block_until = max(self.tpd_block_until, self.clock() + (retry_after or 600))
        elif kind == "RPD":
            self.rpd, self.used_today = int(limit), int(used)
            self.tpd_block_until = max(self.tpd_block_until, self.clock() + (retry_after or 600))
        elif kind == "RPM":
            self.req.resize(max(1, limit * 0.9))
            self.note_429(retry_after)
        elif kind == "TPM":
            self.tok.resize(max(1, limit * 0.9))
            self.note_429(retry_after)

    def add_usage(self, tokens: float):
        self.tpd_used += tokens

    def daily_left(self):
        return self.rpd - self.used_today

    def daily_blocked(self, tokens: float = 0, priority: int = 1) -> bool:
        """True when the daily budget (requests OR tokens) cannot cover this call."""
        floor = 0 if priority <= 0 else self.reserve
        if self.daily_left() <= floor:
            return True
        if self.clock() < self.tpd_block_until:
            return True
        return self.tpd is not None and self.tpd_used + tokens > self.tpd

    # ---- admission ----
    def expected_wait(self, tokens: float, include_queue: bool = False) -> float:
        """Seconds until a call of `tokens` could be admitted. include_queue=True also counts every
        request already waiting ahead of it (what a NEW arrival will actually experience)."""
        cool = max(0.0, self.cooldown_until - self.clock())
        nq = qt = 0
        if include_queue:
            live = [e for e in self._q if not e[4].done()]
            nq, qt = len(live), sum(e[2] for e in live)
        return max(cool, self.req.wait_time(1 + nq), self.tok.wait_time(tokens + qt))

    async def acquire(self, tokens: float, priority: int, deadline: float | None):
        """Wait for capacity. Raises Shed if the daily budget (minus reserve for priority<=0)
        is gone or the wait cannot fit before `deadline` (a loop.time-style monotonic value)."""
        if self.daily_blocked(tokens, priority):
            raise DailyBudgetExhausted("daily_budget", retry_after=0)
        fut =asyncio.get_running_loop().create_future()
        heapq.heappush(self._q, (priority, next(self._seq), tokens, deadline, fut))
        self._ensure_pump()
        self._wake.set()
        return await fut

    def _ensure_pump(self):
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._pump())

    async def _pump(self):
        while self._q:
            pri, _, tokens, deadline, fut = self._q[0]
            if fut.cancelled():
                heapq.heappop(self._q)
                continue
            now = self.clock()
            if deadline is not None and now + self.expected_wait(tokens) > deadline:
                heapq.heappop(self._q)
                fut.set_exception(Shed("wait_exceeds_deadline", self.expected_wait(tokens)))
                continue
            if self.daily_blocked(tokens, pri):
                heapq.heappop(self._q)
                fut.set_exception(DailyBudgetExhausted("daily_budget"))
                continue
            if now >= self.cooldown_until and self.req.try_take(1):
                if self.tok.try_take(tokens):
                    heapq.heappop(self._q)
                    self.used_today += 1
                    if not fut.done():
                        fut.set_result(self.clock())
                    continue
                self.req.refund(1)
            await asyncio.sleep(min(0.05, max(0.005, self.expected_wait(tokens))))

    def refund_tokens(self, reserved: float, actual: float):
        """Reconcile estimate with API usage (only if the provider is known to refund)."""
        if self.refund_on_success and actual < reserved:
            self.tok.refund(reserved - actual)

    def release(self, reserved: float):
        """A request that was rejected or failed before producing output: give the tokens back."""
        self.tok.refund(reserved)
