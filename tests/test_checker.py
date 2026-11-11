import pytest
from relay.limiter import DailyBudgetExhausted, Limiter
from relay.llm import LIMIT_RE
from relay.pipeline import CITE, deterministic_check

R = {"attention:12": {"text": "we employ h = 8 parallel attention layers, dk = dv = 64"},
     "attention:3": {"text": "label smoothing of value 0.1"}}


def test_valid_answer_passes():
    ok, issues = deterministic_check("It uses 8 heads of dimension 64 [C:attention:12].", R)
    assert ok, issues


def test_missing_citation_fails():
    ok, issues = deterministic_check("It uses 8 heads.", R)
    assert not ok and "no_citation" in issues


def test_unknown_citation_fails():
    ok, issues = deterministic_check("It uses 8 heads [C:attention:99].", R)
    assert not ok and any(i.startswith("unknown_citation") for i in issues)


def test_number_not_in_cited_chunk_fails():
    ok, issues = deterministic_check("It uses 16 heads [C:attention:12].", R)
    assert not ok and "number_not_in_cited:16" in issues


def test_abstention_passes_without_citation():
    ok, _ = deterministic_check("The papers don't say. The passages cover other topics.", R)
    assert ok


def test_fullwidth_brackets_are_parsed():
    assert CITE.findall("x 【C:attention:22】 y [C:moshi:3]") == ["attention:22", "moshi:3"]


def test_429_body_parsing_finds_limit_not_in_headers():
    m = LIMIT_RE.search("on tokens per day (TPD): Limit 200000, Used 199538, Requested 1962.")
    assert m.groups() == ("TPD", "200000", "199538")
    m = LIMIT_RE.search("on requests per minute (RPM): Limit 30, Used 30, Requested 1.")
    assert m.group(1) == "RPM" and m.group(2) == "30"


@pytest.mark.asyncio
async def test_tpd_learned_from_429_blocks_new_requests():
    lim = Limiter(rpm=600, tpm=10**7, rpd=1000)
    lim.learn_limit("TPD", 200000, 199538, 648)
    with pytest.raises(DailyBudgetExhausted):
        await lim.acquire(2000, 0, None)       # even continuation priority is blocked by a real TPD wall
