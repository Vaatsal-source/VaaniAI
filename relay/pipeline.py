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
from .retrieval import Retriever, tokenize

ABSTAIN = "the papers don't say"
CITE = re.compile(r"[\[\u3010]\s*C:\s*([a-z]+:\d+)\s*[\]\u3011]")
NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")
STOP = set("a an the of in on and or to is are was were what which how does do did for with by as at from that this it its be used use paper papers".split())
PAPER_KW = {"attention": r"transformer|attention is all|multi-?head|bleu|wmt|positional|label smoothing|dot-product",
            "moshi": r"moshi|mimi|helium|full-duplex|depth transformer|kyutai|spoken|audio|speech|quantizer",
            "dynchunk": r"h-?net|dynamic chunk|chunk|routing module|dechunk|smoothing|ratio loss|byte"}

SYS_CLASSIFY = ("[[STEP:classify]] You route questions about three papers: attention (Attention Is All You Need), "
                "moshi (Moshi speech-text model), dynchunk (H-Net dynamic chunking). Reply with JSON only: "
                '{"intent":"factual|compare|offtopic","paper":"attention|moshi|dynchunk|any","section":"e.g. 3.2.2 or empty",'
                '"queries":["1-2 short search queries"]}')
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


class Pipeline:
    def __init__(self, cfg, retriever: Retriever, llm: LLMClient, log: EventLog, seed=1234):
        self.cfg, self.pc = cfg, cfg["pipeline"]
        self.r, self.llm, self.log = retriever, llm, log
        self.small, self.large = cfg["models"]["small"], cfg["models"]["large"]
        self.lim = llm.limiters[self.large]          # the draft model is the bottleneck
        self.lim_small = llm.limiters[self.small]
        self.tool = Tool(retriever, self.pc, random.Random(seed))
        self.base_k = retriever.top_k

    # ---------- overload policy ----------
    def pressure(self, deadline) -> int:
        """0 normal, 1 degraded (drop optional work), 2 = extractive-only (no LLM)."""
        if self.lim.daily_blocked(2200, 1):
            return 2
        remaining = max(0.1, deadline - time.monotonic())
        wait = self.lim.expected_wait(2200, include_queue=True)   # includes everyone already queued
        self.log.emit("-", "pressure", wait_s=round(wait, 2), remaining_s=round(remaining, 2),
                      queued=len(self.lim._q))
        return 0 if wait < 0.15 * remaining else 1 if wait < 0.4 * remaining else 2

    def extractive(self, question, chunks, reason):
        qt = {t for t in tokenize(question) if t not in STOP}
        picks = []
        for c in chunks[:3]:
            sents = re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", c["text"]))
            best = max(sents, key=lambda s: len(qt & set(tokenize(s))), default="")
            if best:
                picks.append(f'"{best.strip()[:300]}" [C:{c["id"]}]')
        head = {"daily": "Our language-model budget for today is used up, so I can't write a summary right now. ",
                "overload": "We're very busy right now, so I can't write a summary. "}[reason]
        return head + "Here are the most relevant passages from the papers, quoted verbatim:\n" + "\n".join(picks)

    # ---------- steps ----------
    async def _llm(self, rid, step, model, system, user, *, max_tokens, priority, deadline, json_mode=False):
        return await self.llm.chat(rid, step, model, [{"role": "system", "content": system},
                                                       {"role": "user", "content": user}],
                                   max_tokens=max_tokens, priority=priority, deadline=deadline,
                                   json_mode=json_mode)

    async def handle(self, rid: str, question: str, deadline_s: float | None = None) -> dict:
        t_arr = time.monotonic()
        deadline = t_arr + (deadline_s or self.pc["request_deadline_s"])
        self.log.emit(rid, "enqueue", question=question[:80])
        res = {"id": rid, "status": "error", "text": "", "citations": [], "level": 0, "steps": []}
        try:
            res = await self._run(rid, question, deadline, res)
        except asyncio.CancelledError:
            self.log.emit(rid, "abandon")
            raise
        finally:
            if res["status"] != "error" or True:
                pass
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
        level = self.pressure(deadline)
        res["level"] = level
        daily = self.lim.daily_blocked(2200, 1)
        no_llm = daily or level == 2     # fail fast: no model calls, answer from local retrieval or decline
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
            return [c for c, _ in hits][:max(k, len(papers))]
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
            msg = ("Today's model budget is used up and I couldn't find a passage that clearly answers this. "
                   "Please try again tomorrow." if daily else
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
        ctx = "\n\n".join(f'[C:{c["id"]}] ({c["paper"]} v{c["version"][-1]}, p.{c["pages"][0]}, sec {c["section"]})\n{c["text"]}'
                          for c in chunks)
        user = f"Passages:\n{ctx}\n\nQuestion: {question}"
        feedback = ""
        for attempt in range(2):
            try:
                out = await self._llm(rid, "draft", self.large, SYS_DRAFT, user + feedback, max_tokens=300,
                                      priority=0, deadline=deadline)
            except DailyBudgetExhausted:
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
