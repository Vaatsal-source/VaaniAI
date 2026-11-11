import asyncio, time, pytest
from relay.limiter import Bucket, Limiter, Shed, DailyBudgetExhausted


class FakeClock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def test_bucket_refill_and_wait():
    c = FakeClock(); b = Bucket(60, 60, c)
    assert b.try_take(60) and not b.try_take(1)
    assert b.wait_time(1) == pytest.approx(1.0)
    c.t += 5
    assert b.try_take(5) and not b.try_take(1)


def test_bucket_never_exceeds_capacity():
    c = FakeClock(); b = Bucket(10, 60, c)
    c.t += 1000
    b._refill()
    assert b.level == 10


@pytest.mark.asyncio
async def test_daily_budget_exhausted_and_reserve():
    lim = Limiter(rpm=6000, tpm=10**7, rpd=10, daily_reserve_frac=0.2)  # reserve = 2
    for _ in range(8):
        await lim.acquire(1, 1, None)
    with pytest.raises(DailyBudgetExhausted):
        await lim.acquire(1, 1, None)          # normal priority blocked at the reserve
    await lim.acquire(1, 0, None)              # continuation priority may use the reserve


@pytest.mark.asyncio
async def test_shed_when_wait_exceeds_deadline():
    lim = Limiter(rpm=1, tpm=10**7, rpd=1000)
    await lim.acquire(1, 1, None)              # drains the single request token
    with pytest.raises(Shed):
        await lim.acquire(1, 1, time.monotonic() + 0.5)  # needs ~60s


@pytest.mark.asyncio
async def test_priority_order():
    lim = Limiter(rpm=600, tpm=10**7, rpd=1000)  # 10/s
    for _ in range(600):
        lim.req.try_take(1)
    order = []
    async def go(p, name):
        await lim.acquire(1, p, None); order.append(name)
    await asyncio.gather(go(2, "low"), go(1, "normal"), go(0, "high"))
    assert order == ["high", "normal", "low"]
