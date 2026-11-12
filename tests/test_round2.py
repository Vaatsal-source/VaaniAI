"""Tests for the second round of changes: commit accounting, retry-after estimate, token reconciliation,
answer cache + single flight, provider failover routing, context trimming, table-row reassembly."""
import asyncio
import copy
import pathlib
from types import SimpleNamespace

import pytest

from relay.events import EventLog
from relay.limiter import Bucket, Limiter
from relay.pipeline import Pipeline, norm_question
from relay.runtime import load_cfg

ROOT = pathlib.Path(__file__).resolve().parent.parent


class FakeClock:
    def __init__(self): self.t = 1000.0
    def __call__(self): return self.t


def test_commit_counts_in_expected_wait():
    c = FakeClock()
    lim = Limiter(rpm=600, tpm=6000, rpd=1000, clock=c)
    assert lim.expected_wait(2000, include_queue=True) == 0
    lim.commit(5000)                       # an admitted request will still send a 5000-token call
    assert lim.expected_wait(2000, include_queue=True) == pytest.approx((7000 - 6000) * 60 / 6000)
    lim.uncommit(5000)
    assert lim.expected_wait(2000, include_queue=True) == 0
    assert lim.committed_n == 0 and lim.committed_tokens == 0


def test_daily_retry_after_matches_the_real_429():
    """The real 429 said: Limit 200000, Used 199538, Requested 1962, retry-after 648."""
    lim = Limiter(rpm=30, tpm=8000, rpd=1000, clock=FakeClock())
    lim.tpd, lim.tpd_used = 200000, 199538
    assert lim.daily_retry_after(1962) == pytest.approx(648, abs=1)


def test_daily_retry_after_zero_when_budget_left():
    lim = Limiter(rpm=30, tpm=8000, rpd=1000, clock=FakeClock())
    lim.tpd, lim.tpd_used = 200000, 1000
    assert lim.daily_retry_after(2000) == 0


def test_token_reconciliation_refunds_and_charges():
    c = FakeClock()
    lim = Limiter(rpm=600, tpm=8000, rpd=1000, clock=c, refund_on_success=True)
    assert lim.tok.try_take(2000)
    lim.refund_tokens(2000, 1500)
    assert lim.tok.level == pytest.approx(8000 - 1500)
    lim.refund_tokens(1000, 1400)          # under-reserved: the extra 400 is charged
    assert lim.tok.level == pytest.approx(8000 - 1500 - 400)
    off = Limiter(rpm=600, tpm=8000, rpd=1000, clock=c)
    assert off.tok.try_take(2000)
    off.refund_tokens(2000, 1500)          # default: no reconciliation
    assert off.tok.level == pytest.approx(6000)


def test_bucket_charge_can_go_into_debt_but_is_bounded():
    c = FakeClock(); b = Bucket(100, 60, c)
    b.charge(150)
    assert b.level == -50 and b.wait_time(10) == pytest.approx(36.0)
    b.charge(1000)
    assert b.level == -100


def test_norm_question():
    assert norm_question("  How many   heads?? ") == norm_question("how many heads")


def _pipe(cache=True, fallback=False):
    cfg = copy.deepcopy(load_cfg())
    cfg["cache"].update(enabled=cache, ttl_s=60)
    lim = {m: Limiter(30, 8000, 1000, clock=FakeClock()) for m in (cfg["models"]["small"], cfg["models"]["large"], "fb-small", "fb-large")}
    llm = SimpleNamespace(limiters=lim, primary="groq")
    retr = SimpleNamespace(top_k=5, chunks=[], by_id={})
    fb = {"provider": "gemini", "small": "fb-small", "large": "fb-large"} if fallback else None
    return Pipeline(cfg, retr, llm, EventLog(None), 1234, fallback=fb), lim, cfg


@pytest.mark.asyncio
async def test_cache_and_single_flight():
    pipe, _, _ = _pipe()
    calls = []

    async def fake_run(rid, q, deadline, res):
        calls.append(rid)
        await asyncio.sleep(0.05)
        res.update(status="answered", text="42 [C:attention:1]")
        return res
    pipe._run = fake_run
    # three identical questions at once: one run, two joiners
    out = await asyncio.gather(*[pipe.handle(f"r{i}", "How many heads?") for i in range(3)])
    assert len(calls) == 1 and [o.get("cached") for o in out].count(True) == 2
    again = await pipe.handle("r9", "how many heads")
    assert again["cached"] and len(calls) == 1 and again["text"] == "42 [C:attention:1]"


@pytest.mark.asyncio
async def test_only_verified_answers_are_cached():
    pipe, _, _ = _pipe()
    n = []

    async def fake_run(rid, q, deadline, res):
        n.append(1)
        res.update(status="extractive_overload", text="quotes")
        return res
    pipe._run = fake_run
    await pipe.handle("a", "q?"); await pipe.handle("b", "q?")
    assert len(n) == 2                     # a degraded reply must never be served later as if it were an answer


@pytest.mark.asyncio
async def test_cache_off_by_default_in_experiments():
    pipe, _, _ = _pipe(cache=False)
    n = []

    async def fake_run(rid, q, deadline, res):
        n.append(1); res.update(status="answered", text="x"); return res
    pipe._run = fake_run
    await pipe.handle("a", "q?"); await pipe.handle("b", "q?")
    assert len(n) == 2


def test_failover_routing():
    pipe, lim, cfg = _pipe(fallback=True)
    big = cfg["models"]["large"]
    assert pipe.active()[0] == "groq"
    lim[big].tpd, lim[big].tpd_used = 200000, 199900          # primary's daily tokens are gone
    route = pipe.active()
    assert route[0] == "gemini" and route[2] == "fb-large"
    lim["fb-large"].tpd, lim["fb-large"].tpd_used = 100, 100   # ... and so are the backup's
    assert pipe.active() is None
    assert pipe.pressure(1e12) == 2


def test_no_fallback_means_no_route_when_primary_daily_is_gone():
    pipe, lim, cfg = _pipe(fallback=False)
    big = cfg["models"]["large"]
    lim[big].tpd, lim[big].tpd_used = 200000, 199900
    assert pipe.active() is None


def test_retry_phrase_is_honest_about_time():
    pipe, lim, cfg = _pipe()
    big = cfg["models"]["large"]
    lim[big].tpd, lim[big].tpd_used = 200000, 199538
    pipe.avg_draft_tokens = 1962
    assert "11 minutes" in pipe.retry_phrase()        # 648 s


def test_trim_context_keeps_the_relevant_sentences():
    text = ("Intro filler sentence one. Another filler about nothing. The big Transformer has 213 million parameters. "
            "More filler follows here. And a closing remark.")
    out = Pipeline.trim_context(text, "How many parameters does the big Transformer have", 70)
    assert "213 million parameters" in out and len(out) < len(text)
    assert Pipeline.trim_context(text, "x", 0) == text and Pipeline.trim_context(text, "x", 10000) == text


@pytest.mark.skipif(not (ROOT / "papers" / "1706.03762v7.pdf").exists(), reason="papers not downloaded")
def test_table_rows_are_rebuilt_from_page_layout():
    import fitz
    from relay.ingest import table_blocks
    page = fitz.open(ROOT / "papers" / "1706.03762v7.pdf")[8]            # Table 3: Transformer variations
    blocks = table_blocks(page)
    assert blocks, "no table found on the page that holds Table 3"
    rows = "\n".join(blocks[0]["rows"])
    assert "big 6 1024 4096 16 0.3 300K 4.33 26.4 213" in rows            # label and number on one line
    assert blocks[0]["caption"].startswith("Table 3")


@pytest.mark.skipif(not (ROOT / "papers" / "2507.07955v2.pdf").exists(), reason="papers not downloaded")
def test_reference_filter_keeps_appendix_a_opening():
    from relay.ingest import load_chunks
    v1 = {c["id"]: c for c in load_chunks(1200, 200, "v1")}
    v2 = {c["id"]: c for c in load_chunks(1200, 200, "v2")}
    opening = "The fundamental challenge of transforming raw sequential data"
    assert v1["dynchunk:111"]["is_ref"] and opening in v1["dynchunk:111"]["text"]       # round 1 dropped it
    assert not v2["dynchunk:111"]["is_ref"]                                             # round 2 keeps it
    refs = [c for c in v2.values() if c["paper"] == "dynchunk" and c["id"].split(":")[1].isdigit()
            and 86 <= int(c["id"].split(":")[1]) <= 110]
    assert len(refs) == 25 and all(c["is_ref"] for c in refs)                           # the real reference list is still dropped


def test_table_chunk_citations_are_recognised_and_checked():
    from relay.pipeline import CITE, deterministic_check
    assert CITE.findall("The big model has 213M parameters [C:attention:t1].") == ["attention:t1"]
    assert CITE.findall("fullwidth 【C:moshi:t0】 and plain [C:moshi:84]") == ["moshi:t0", "moshi:84"]
    retrieved = {"attention:t1": {"text": "big 6 1024 4096 16 0.3 300K 4.33 26.4 213"}}
    ok, issues = deterministic_check("The big model has 213 million parameters [C:attention:t1].", retrieved)
    assert ok, issues
    ok, issues = deterministic_check("It has 999 million parameters [C:attention:t1].", retrieved)
    assert not ok and any(i.startswith("number_not_in_cited") for i in issues)


def test_limiter_believes_the_provider_when_fewer_tokens_remain():
    """A freshly started process has a full bucket, but the provider remembers what an earlier process spent."""
    lim = Limiter(rpm=30, tpm=8000, rpd=1000, clock=FakeClock())
    lim.observe_headers({"x-ratelimit-limit-tokens": "8000", "x-ratelimit-remaining-tokens": "380"})
    assert lim.tok.level == 380
    assert lim.expected_wait(2000) > 10          # about (2000 - 380) / (8000 / 60) s
    lim.observe_headers({"x-ratelimit-limit-tokens": "8000", "x-ratelimit-remaining-tokens": "7900"})
    assert lim.tok.level == 380                  # never raised from a header: we reserve more than we use
