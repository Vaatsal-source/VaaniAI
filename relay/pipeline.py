"""The Relay pipeline.

  1 classify  (small LLM, or heuristic when degraded)      -> intent, section hint, queries
  2 retrieve  (local, in executor)                          -> top-k chunks + coverage confidence
  3 decide    (branch/loop)  low confidence -> rewrite query (small LLM) & re-retrieve, capped
                              section hint  -> tool call fetch_section() with a timeout
  4 draft     (large LLM, streamed from provider, BUFFERED)
  5 verify    deterministic citation check always; LLM verify only when confidence is low
  6 release   stream the verified text to the user (user-visible first token happens here)

Never-wrong floor: anything that fails verification is regenerated once, then replaced by an
honest decline. Overload only ever removes OPTIONAL work (classify LLM, loop, LLM-verify,
top-k) or ends in an extractive/decline reply; it never skips the deterministic check.
"""
import asyncio
import json
import random
import re
import time

from .events import EventLog
from .limiter import DailyBudgetExhausted, Limiter, Shed
from .llm import LLMClient, LLMError
from .papers import PAPER_DESC, PAPER_KW
from .retrieval import STOP, Retriever, tokenize

ABSTAIN = "the papers don't say"
CITE = re.compile(r"[\[\u3010]\s*C:\s*([a-z]+:t?\d+)\s*[\]\u3011]")     # "attention:12" or a table chunk "attention:t1"
NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")

SYS_CLASSIFY = ("[[STEP:classify]] You route questions about three papers: "
                + ", ".join(f"{k} ({v})" for k, v in PAPER_DESC.items())
                + '. Reply with JSON only: {"intent":"factual|compare|offtopic","paper":"' + "|".join(PAPER_DESC) + '|any",'
                '"section":"e.g. 3.2.2 or empty","queries":["1-2 short search queries"]}')
SYS_DRAFT = ("[[STEP:draft]] Answer ONLY from the numbered passages below; never use outside knowledge. "
             "Cite every claim with the passage id in the form [C:paper:n] using plain ASCII square brackets. If the passages do not contain the answer, "
             "reply exactly: The papers don't say. followed by one short sentence on what is missing. "
             "Be concise (max 100 words).")
SYS_VERIFY = ("[[STEP:verify]] Check whether the ANSWER is fully supported by the PASSAGES. "
              'Reply JSON only: {"supported":true|false,"issues":["..."]}')
SYS_REWRITE = "[[STEP:rewrite]] Rewrite the question as one keyword-rich search query for scientific paper text. Output the query only."


def detect_papers(q: str):
    return [p for p, rx in PAPER_KW.items() if re.search(rx, q, re.I)]


def coverage(query: str, chunks) -> float:
    qt = {t for t in tokenize(query) if t not in STOP and len(t) > 1}
    if not qt:
        return 0.0
    text = " ".join(c["text"] for c in chunks).lower()
    toks = set(tokenize(text))
    return sum(t in toks for t in qt) / len(qt)


def deterministic_check(answer: str, retrieved: dict) -> tuple[bool, list]:
    """Cheap, always-on check. retrieved: id -> chunk.
    1) abstentions are fine; 2) otherwise >=1 citation; 3) every cited id exists;
    4) every number in the answer appears in some cited chunk."""
    issues = []
    if ABSTAIN in answer.lower().replace("’", "'"):
        return True, issues
    ids = CITE.findall(answer)
    if not ids:
        issues.append("no_citation")
    unknown = [i for i in ids if i not in retrieved]
    if unknown:
        issues.append(f"unknown_citation:{unknown}")
    cited_text = " ".join(retrieved[i]["text"] for i in ids if i in retrieved)
    norm = cited_text.replace(",", "")
    for n in NUM.findall(CITE.sub("", answer)):
        if n not in norm and n not in ("1", "2", "3"):
            issues.append(f"number_not_in_cited:{n}")
    return (not issues), issues


class Tool:
    """fetch_section(paper, section): returns chunks of a section. Has an injected failure mode."""

    def __init__(self, retriever: Retriever, cfg: dict, rng: random.Random):
        self.r, self.c, self.rng = retriever, cfg, rng

    async def fetch_section(self, paper: str, section: str):
        if self.rng.random() < self.c["tool_p_slow"]:
            await asyncio.sleep(self.c["tool_slow_s"])     # slow without failing
        if self.rng.random() < self.c["tool_p_fail"]:
            raise RuntimeError("tool_error")
        return [c for c in self.r.chunks if c["paper"] == paper and c["section"].split(" ")[0] == section][:2]


def norm_question(q: str) -> str:
    return re.sub(r"\s+", " ", q.strip().lower()).strip(" ?!.")


class Pipeline:
    def __init__(self, cfg, retriever: Retriever, llm: LLMClient, log: EventLog, seed=1234, fallback=None):
        self.cfg, self.pc = cfg, cfg["pipeline"]
        self.pol = cfg.get("pipeline_policy", {})
        self.degrade_frac = self.pol.get("degrade_frac", 0.15)
        self.shed_frac = self.pol.get("shed_frac", 0.40)
        self.commit_admitted = self.pol.get("commit_admitted", False)
        self.r, self.llm, self.log = retriever, llm, log
        self.small, self.large = cfg["models"]["small"], cfg["models"]["large"]
        self.lim = llm.limiters[self.large]          # the draft model is the bottleneck
        self.lim_small = llm.limiters[self.small]
        # optional second provider, used only while the first one's daily budget is gone
        self.fb = fallback        # {"provider": name, "small": model, "large": model} or None
        self.fb_lim = llm.limiters[fallback["large"]] if fallback else None
        self.tool = Tool(retriever, self.pc, random.Random(seed))
        self.base_k = retriever.top_k
        self.ctx_trim = cfg.get("retrieval", {}).get("ctx_trim_chars", 0)
        self.avg_draft_tokens = 2000.0       # running average of what a draft really costs (prompt + reply)
        cc = cfg.get("cache", {})
        self.cache_on, self.cache_max, self.cache_ttl = bool(cc.get("enabled")), cc.get("max_entries", 500), cc.get("ttl_s", 3600)
        self.join_frac = cc.get("join_wait_frac", 0.5)   # a request that joins an identical in-flight one waits at most this share of its remaining time
        self._cache: dict = {}               # normalised question -> (expires, result)
        self._inflight: dict = {}            # normalised question -> Future (identical concurrent questions share one run)

    # ---------- overload policy ----------
    def active(self):
        """(provider, small model, large model, large-model limiter) to use right now: the primary, or the fallback
        provider while the primary's daily budget is gone. None when no provider can take a call."""
        t = self.avg_draft_tokens
        if not self.lim.daily_blocked(t, 1):
            return (self.llm.primary, self.small, self.large, self.lim)
        if self.fb and not self.fb_lim.daily_blocked(t, 1):
            return (self.fb["provider"], self.fb["small"], self.fb["large"], self.fb_lim)
        return None

    def pressure(self, deadline) -> int:
        """0 normal, 1 degraded (drop optional work), 2 = extractive-only (no LLM)."""
        route = self.active()
        if route is None:
            return 2
        lim = route[3]
        remaining = max(0.1, deadline - time.monotonic())
        # Includes everyone already queued AND the model calls that already-admitted requests still have to make.
        wait = lim.expected_wait(self.avg_draft_tokens, include_queue=True)
        self.log.emit("-", "pressure", wait_s=round(wait, 2), remaining_s=round(remaining, 2),
                      queued=len(lim._q), committed=lim.committed_n, provider=route[0])
        return 0 if wait < self.degrade_frac * remaining else 1 if wait < self.shed_frac * remaining else 2

    def retry_phrase(self) -> str:
        """'in about N minutes' from the limiter's own estimate of when a call will be allowed again."""
        sec = self.lim.daily_retry_after(self.avg_draft_tokens)
        if sec <= 0:
            return "in a minute"
        if sec < 90:
            return "in about a minute"
        if sec < 5400:
            return f"in about {int(round(sec / 60))} minutes"
        return f"in about {int(round(sec / 3600))} hours"

    def extractive(self, question, chunks, reason):
        qt = {t for t in tokenize(question) if t not in STOP}
        picks = []
        for c in [c for c in chunks if c.get("kind") != "table"][:3]:
            sents = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", c["text"]))
            best = max(sents, key=lambda s: len(qt & set(tokenize(s))), default="")
            if best:
                picks.append(f'"{best.strip()[:300]}" [C:{c["id"]}]')
        head = {"daily": "Our language-model budget for today is used up, so I can't write a summary right now. ",
                "overload": "We're very busy right now, so I can't write a summary. "}[reason]
        return head + "Here are the most relevant passages from the papers, quoted verbatim:\n" + "\n".join(picks)

    # ---------- steps ----------
    async def _llm(self, rid, step, model, system, user, *, max_tokens, priority, deadline, json_mode=False):
        provider = self.llm.primary
        if self.fb and model in (self.small, self.large) and self.lim.daily_blocked(self.avg_draft_tokens, priority):
            provider = self.fb["provider"]      # primary's daily budget is gone: same job, second provider
            model = self.fb["small"] if model == self.small else self.fb["large"]
        return await self.llm.chat(rid, step, model, [{"role": "system", "content": system},
                                                       {"role": "user", "content": user}],
                                   max_tokens=max_tokens, priority=priority, deadline=deadline,
                                   json_mode=json_mode, provider=provider)

    @staticmethod
    def trim_context(text: str, query: str, max_chars: int) -> str:
        """Keep the sentences that overlap the question most, in their original order, up to max_chars."""
        if max_chars <= 0 or len(text) <= max_chars:
            return text
        qt = {t for t in tokenize(query) if t not in STOP and len(t) > 1}
        sents = re.split(r"(?<=[.!?])\s+|\n", text)
        scored = sorted(range(len(sents)), key=lambda i: -(len(qt & set(tokenize(sents[i]))) + 0.01 * (i == 0)))
        keep, size = set(), 0
        for i in scored:
            if size + len(sents[i]) + 1 > max_chars and keep:
                continue
            keep.add(i); size += len(sents[i]) + 1
        return " ".join(sents[i] for i in sorted(keep))[:max_chars + 200]

    async def handle(self, rid: str, question: str, deadline_s: float | None = None) -> dict:
        t_arr = time.monotonic()
        deadline = t_arr + (deadline_s or self.pc["request_deadline_s"])
        self.log.emit(rid, "enqueue", question=question[:80])
        key = norm_question(question)
        if self.cache_on:
            hit = self._cache.get(key)
            if hit and hit[0] > t_arr:                          # served without touching the limiter or the provider
                res = dict(hit[1], id=rid, cached=True, steps=["cache"])
                self.log.emit(rid, "cache_hit")
                self.log.emit(rid, "user_first_token"); self.log.emit(rid, "user_last_token")
                self.log.emit(rid, "done", status=res["status"], level=0, steps=res["steps"], answer=res["text"][:2000], cached=True)
                return res
            fut = self._inflight.get(key)
            if fut is not None:                                 # the same question is being answered right now: share it
                self.log.emit(rid, "cache_join")
                try:
                    base = await asyncio.wait_for(asyncio.shield(fut), max(0.1, (deadline - time.monotonic()) * self.join_frac))
                    res = dict(base, id=rid, cached=True, steps=["cache_join"])
                    self.log.emit(rid, "user_first_token"); self.log.emit(rid, "user_last_token")
                    self.log.emit(rid, "done", status=res["status"], level=res["level"], steps=res["steps"], answer=res["text"][:2000], cached=True)
                    return res
                except (asyncio.TimeoutError, Exception):
                    pass                                        # leader failed or was too slow: run our own
            fut = asyncio.get_running_loop().create_future()
            self._inflight[key] = fut
        res = {"id": rid, "status": "error", "text": "", "citations": [], "level": 0, "steps": []}
        try:
            res = await self._run(rid, question, deadline, res)
        except asyncio.CancelledError:
            self.log.emit(rid, "abandon")
            if self.cache_on and self._inflight.get(key) is fut:
                del self._inflight[key]
                fut.cancel()
            raise
        finally:
            if self.cache_on and self._inflight.get(key) is fut:
                del self._inflight[key]
                if not fut.done():
                    fut.set_result(res) if res["status"] in ("answered", "abstained") else fut.cancel()
        if self.cache_on and res["status"] in ("answered", "abstained"):   # only verified answers are ever cached
            if len(self._cache) >= self.cache_max:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic() + self.cache_ttl, res)
        self.log.emit(rid, "done", status=res["status"], level=res["level"], steps=res["steps"],
                      answer=res["text"][:2000])
        return res

    def _release(self, rid, res, text, status):
        """Release text to the user as a stream; the first piece is the user-visible first token."""
        self.log.emit(rid, "user_first_token")
        res.update(status=status, text=text,
                   citations=[{"id": i, "paper": self.r.by_id[i]["paper"], "version": self.r.by_id[i]["version"],
                               "pages": self.r.by_id[i]["pages"], "section": self.r.by_id[i]["section"]}
                              for i in dict.fromkeys(CITE.findall(text)) if i in self.r.by_id])
        self.log.emit(rid, "user_last_token")
        return res

    async def _run(self, rid, question, deadline, res):
        route = self.active()
        level = self.pressure(deadline)
        res["level"] = level
        daily = route is None            # no provider has daily budget left
        no_llm = daily or level == 2     # fail fast: no model calls, answer from local retrieval or decline
        state = {"tokens": 0.0, "lim": None}
        if not no_llm and self.commit_admitted:
            # tell the limiter about the draft call this request will make later, so new arrivals count it
            state["tokens"], state["lim"] = self.avg_draft_tokens, route[3]
            route[3].commit(state["tokens"])

        def release():                   # idempotent: called when the draft enters the queue, or when the request ends
            if state["lim"] is not None:
                state["lim"].uncommit(state["tokens"])
                state["lim"] = None
        try:
            return await self._steps(rid, question, deadline, res, level, daily, no_llm, route, release)
        finally:
            release()                    # a request that ends early must not leave its commitment behind

    async def _steps(self, rid, question, deadline, res, level, daily, no_llm, route, release):
        # ---- 1 classify ----
        self.log.emit(rid, "step_start", step="classify")
        cls = {"intent": "factual", "section": "", "queries": [question]}
        if level == 0 and not no_llm:
            try:
                out = await self._llm(rid, "classify", self.small, SYS_CLASSIFY, question, max_tokens=150,
                                      priority=1, deadline=deadline, json_mode=True)
                m = re.search(r"\{.*\}", out["text"], re.S)
                cls.update(json.loads(m.group(0)) if m else {})
            except (Shed, LLMError, ValueError):
                self.log.emit(rid, "degrade", what="classify_heuristic")
                level = max(level, 1)
        else:
            self.log.emit(rid, "degrade", what="classify_heuristic")
        res["steps"].append("classify")
        self.log.emit(rid, "step_end", step="classify")
        queries = [q for q in (cls.get("queries") or [question]) if isinstance(q, str)][:2] or [question]
        query = " ".join(dict.fromkeys([question] + queries))
        papers = detect_papers(question) or ([cls["paper"]] if cls.get("paper") in PAPER_KW else [None])
        k = self.base_k if level == 0 else max(2, self.base_k - 2)

        # ---- 2 retrieve (+ 3 decide loop) ----
        async def retrieve(q):
            self.log.emit(rid, "step_start", step="retrieve")
            per = max(1, -(-k // len(papers)))
            hits = []
            for p in papers:
                hits += await self.r.search(q, p, per)
            self.log.emit(rid, "step_end", step="retrieve")
            prose = [c for c, _ in hits if c.get("kind") != "table"][:max(k, len(papers))]
            tabs = [c for c, _ in hits if c.get("kind") == "table"][:self.r.table_extra]
            return prose + tabs
        chunks = await retrieve(query)
        res["steps"].append("retrieve")
        conf = coverage(question, chunks)
        iters = 0
        while conf < self.pc["conf_threshold"] and iters < self.pc["max_loop_iters"] and level == 0 \
                and not daily:
            self.log.emit(rid, "decide", branch="loop_rewrite", conf=round(conf, 2))
            try:
                out = await self._llm(rid, "rewrite", self.small, SYS_REWRITE, question, max_tokens=60,
                                      priority=2, deadline=deadline)
            except (Shed, LLMError):
                break
            chunks2 = await retrieve(out["text"].strip() or question)
            if coverage(question + " " + out["text"], chunks2) > conf:
                chunks = chunks2
                conf = coverage(question, chunks)
            iters += 1
            res["steps"].append("loop")
        if no_llm:
            reason = "daily" if daily else "overload"
            if conf >= self.pc["conf_threshold"]:
                self.log.emit(rid, "degrade", what="extractive_daily" if daily else "extractive_overload")
                retrieved = {c["id"]: c for c in chunks}
                return self._release(rid, res, self.extractive(question, chunks, reason),
                                     "extractive_daily" if daily else "extractive_overload")
            # retrieval did not clearly match: quoting unrelated passages would be misleading -> honest decline
            self.log.emit(rid, "shed", reason=reason + "_low_confidence")
            self.log.emit(rid, "user_first_token")
            msg = (f"Our model budget is used up for now and I couldn't find a passage that clearly answers this. "
                   f"Please try again {self.retry_phrase()}." if daily else
                   "I'm at capacity and couldn't find a passage that clearly answers this. Please try again in a minute.")
            res.update(status="shed", text=msg)
            return res
        sec = str(cls.get("section") or "").strip()
        if sec and len(papers) == 1 and papers[0]:
            self.log.emit(rid, "decide", branch="tool_fetch_section")
            self.log.emit(rid, "tool_call", name="fetch_section", paper=papers[0], section=sec)
            try:
                extra = await asyncio.wait_for(self.tool.fetch_section(papers[0], sec), self.pc["tool_timeout_s"])
                seen = {c["id"] for c in chunks}
                chunks = (extra + [c for c in chunks if c["id"] not in {e["id"] for e in extra}])[:k + 1]
                res["steps"].append("tool")
            except asyncio.TimeoutError:
                self.log.emit(rid, "tool_timeout", name="fetch_section")
            except Exception as e:
                self.log.emit(rid, "tool_error", name="fetch_section", error=str(e))
        retrieved = {c["id"]: c for c in chunks}
        self.log.emit(rid, "decide", branch="draft", conf=round(conf, 2), k=len(chunks))

        # ---- 4 draft (priority 0: a started request outranks new arrivals) ----
        ctx = "\n\n".join(f'[C:{c["id"]}] ({c["paper"]} v{c["version"][-1]}, p.{c["pages"][0]}, sec {c["section"]})\n'
                          f'{self.trim_context(c["text"], question, self.ctx_trim)}' for c in chunks)
        user = f"Passages:\n{ctx}\n\nQuestion: {question}"
        feedback = ""
        attempt, switched = -1, False
        while attempt < 1:
            attempt += 1
            release()                    # from here the draft call itself sits in the limiter queue
            try:
                out = await self._llm(rid, "draft", self.large, SYS_DRAFT, user + feedback, max_tokens=300,
                                      priority=0, deadline=deadline)
                tot = out["usage"].get("total") or 0
                if tot:
                    self.avg_draft_tokens = 0.8 * self.avg_draft_tokens + 0.2 * tot
            except DailyBudgetExhausted:
                if self.fb and not switched and not self.fb_lim.daily_blocked(self.avg_draft_tokens, 0):
                    switched = True      # the first provider's daily wall was just learned from its 429: use the second
                    attempt -= 1
                    self.log.emit(rid, "failover", to=self.fb["provider"])
                    continue
                self.log.emit(rid, "degrade", what="extractive_daily")
                return self._release(rid, res, self.extractive(question, chunks, "daily"), "extractive_daily")
            except (Shed, LLMError) as e:
                self.log.emit(rid, "degrade", what="extractive_overload", why=str(e), wait_s=getattr(e, "retry_after", None),
                              remaining_s=round(deadline - time.monotonic(), 1))
                return self._release(rid, res, self.extractive(question, chunks, "overload"), "extractive_overload")
            res["steps"].append("draft")
            ans = CITE.sub(lambda m: f"[C:{m.group(1)}]", out["text"].strip().replace("\u202f", " "))
            # ---- 5 verify ----
            ok, issues = deterministic_check(ans, retrieved)
            self.log.emit(rid, "verify_det", ok=ok, issues=issues)
            if ok and level == 0 and conf < self.pc["verify_llm_when_confidence_below"] and ABSTAIN not in ans.lower():
                try:
                    v = await self._llm(rid, "verify", self.small, SYS_VERIFY, f"PASSAGES:\n{ctx}\n\nANSWER:\n{ans}",
                                        max_tokens=100, priority=1, deadline=deadline, json_mode=True)
                    res["steps"].append("verify_llm")
                    m = re.search(r"\{.*\}", v["text"], re.S)
                    if m and json.loads(m.group(0)).get("supported") is False:
                        ok, issues = False, ["llm_unsupported"]
                        self.log.emit(rid, "verify_llm", ok=False)
                except (Shed, LLMError, ValueError):
                    pass   # optional stage; deterministic check already passed
            if ok:
                return self._release(rid, res, ans, "abstained" if ABSTAIN in ans.lower().replace("’", "'") else "answered")
            feedback = f"\n\nYour previous answer failed checks ({issues}). Cite only passage ids shown above and use only facts they contain."
            self.log.emit(rid, "decide", branch="regenerate", issues=issues)
        # failed twice -> honest decline, never a shaky answer
        self.log.emit(rid, "degrade", what="decline_unverified")
        return self._release(rid, res, "I couldn't produce an answer I can verify against the papers. "
                             "Please rephrase or try again shortly.", "declined")
