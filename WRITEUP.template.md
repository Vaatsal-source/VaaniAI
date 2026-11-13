# The Relay: write-up

Long version, code and logs: `README.md`. Every number below is computed from `results.csv`. "Real" = Groq's free tier; "stand-in" = my own service.

## 1 What I built and why
A Python/asyncio pipeline over the three papers: **classify** → **retrieve** (BM25, 1,200-character chunks with pages) → **decide** (rewrite the query once if matches are poor; a `fetch_section` tool call with injected faults) → **draft** (must cite `[C:paper:n]` or say "The papers don't say") → **verify** (the citation exists and every number is in the cited text) → **release**. Limiter, retry loop, stand-in and load generator are mine; the client is plain `httpx`.
**The decision that shaped it:** under pressure the system does *less*, never *worse*. When a request's estimated wait (counting everyone queued) passes 40% of its remaining time, there is no model call: the person gets the best sentences quoted from the papers, with citations, or an honest "at capacity". Cost: in a burst most get quotes, not a written answer. "Fast" = median first token ≤ 2,500 ms, p95 ≤ 8,000 ms.

## 2 The real service and my stand-in
{{brief_table1}}

**Stand-in:** same streaming API; lognormal first-token and per-token times fitted from real probes; RPM/TPM/RPD/TPD pools; 429s naming the limit only in the body; tokens charged as used. **Least like the real thing:** failure and slowdown rates are invented (no Groq 5xx in about 950 requests); canned answers, so it says nothing about quality.

## 3 Results
Real runs are tiny on purpose (about 3 answers a minute); heavy loads ran on the stand-in. Shapes: steady, burst, sustained overload at free-tier limits and 10×, plus per-minute limits **halved** and daily budget **exhausted**; users give up after 20 s. Table 2a shows first-token times; total times and column definitions are in `results/brief_tables.md`.

{{brief_2a_core}}

{{brief_2b_core}}

**Reading the tables.** Free-tier burst of 20: 4 written answers, 16 quoted replies in a median 162.4 ms. At 10×, steady load is fully served (p95 4,396.4 ms) and overload is 81.5% written (p95 7,881.1 ms). Free-tier steady **misses the p95 target (13,717.5 ms)**. Halved limits: burst 10.0% written, steady 57.1% (498 laptop freezes, so read the tail as an upper bound). Daily budget gone: 37.0% written, 74.1% with a second provider. The real runs were tiny and slow that evening and say nothing about the policy. Cost: stand-in tokens at the 120B list price.

**Quality** (54 questions, rubric frozen before comparing settings). Table 3 counts an answer correct only if right **and** cited on a gold page, so it is stricter than the README's rubric score. Wrong answers are confident: the number check only proves a number is in the cited text, so a BLEU column read as training cost passed it.

## 4 Where the time goes
Slowest of 4 real requests (5,217.5 ms to first byte): **3,508.8 ms before my server saw it** (laptop stalls), **12.3 ms** in the limiter, **1,683.3 ms** on provider calls, 13.0 ms retrieval, **0 ms retrying**; all before the first token, since the reply is held until verified.

## 5 When a limit is hit
**Per minute:** wait under 15% of remaining time → normal; under 40% → lighter (3 passages, no classify call); 40% or more → no model call: quoted passages if they clearly match, else an honest decline. **Per day:** the wall is known from config or learned from the first 429 body; no new model call starts; a daily 429 is never retried.

## Retrieval: quality versus cost
{{brief_3_core}}

Chosen: **BM25, 1,200/200 characters, top 5, plus a table row when it shares most of the question's words.** Cross-encoder re-ranking found the gold page 100% of the time but took 8,254.6 ms (median); dense retrieval was slower and worse (91.3%).

## How this library will mislead a naive retriever
1. **Tables come out scrambled.** "How many parameters does the big Transformer model have?" (213M): answered once in 6 runs; one model read the FLOPs column.
2. **Same words recur across papers.** "How many attention heads does the base Transformer use?" ranks an appendix and an ablation table above the architecture page.
3. **Structure heuristics lie.** My heading detector took `2.95 Perplexity on HG38` for a heading and dropped the start of H-Net's Appendix A (fixed).

## 6 Retries
At most 3 attempts, jittered backoff never shorter than `retry-after`, never past the deadline, never a daily-limit 429, retries capped at 20% of first attempts. **Where retrying made it worse** (stand-in, 30% failures, 110% of capacity): unbounded retries sent 277 provider calls against 228, reserved 44.4% more tokens for 4 more full answers (81 vs 77), and p95 first token more than doubled (8,530.1 vs 4,037.5 ms).

## 7 What the person sees
At 3 pm, within about 20–30 ms: *"Our language-model budget for today is used up, so I can't write a summary right now. Here are the most relevant passages from the papers, quoted verbatim:"* plus citations. If nothing matched, an honest decline with a retry time (about 5 hours).

## 8 What I'm unsure about, what I left out, what I learned
**Least certain:** that the stand-in's heavy-load behaviour and failure rates stand for the real service; the policies do not depend on it. **Not built:** request hedging and a multi-process limiter. **Learned:**
**A limit you only learn from an error body.** A provider's headers don't tell you the limits that will actually stop you. Groq's response headers gave me 8,000 tokens a minute and 1,000 requests a day. The 30-requests-a-minute limit appears in no header, only in the text of a 429 ("Limit 30, Used 30, Requested 1"). The 200,000-tokens-a-day limit on the 120B appeared the same way, after I had already used it up. That second limit is the one that matters. At about 2.3k tokens an answer it allows roughly 85 answers a day, nowhere near what 1,000 requests suggests. [...] In the stand-in, a limiter told the daily budget and one that learned it from the 429 differed by exactly one request, the one that hit the wall.

## Feedback on Vaani
- **What stood out.** The docs say a 200 from the call API means the call was dispatched, not answered. That is an honest line between "accepted" and "done". The prompt diff in Teacher AI also keeps a person in control.
- **What confused me.** The homepage says p90 latency is about 450 ms, while the developers page gives p50 600 ms and p90 900–1,200 ms. Nothing says what is being timed or over how many calls.
- **What I'd change.** Publish one latency page with what is timed, the percentiles, the sample size and the conditions, plus what happens when a customer goes over their concurrent-call limit. I'd want that before trusting a voice agent with real callers.

## How I worked with the assistant
The raw, uncleaned transcript is `docs/claude-session.jsonl` (my Groq organization id replaced by `[REDACTED-GROQ-ORG-ID]`; nothing else edited), plus the planning chat, copied unedited, in `docs/planning-chat.md`. Excerpt of the full account in the README:

*The three prompts that mattered most:*
1. **My request to read the first page and list what we need to do** (planning chat): the requirements, the constraints and the tradeoffs, before any design. It made me work out that the overload policy is the central decision, and it led to the rule that every table must be recomputable from raw logs. [...]
2. **"What tech stack should I use for this?"** (planning chat). The answer set the architecture: plain asyncio and httpx, no LangChain, my own limiter and retry loop, and an open-loop load generator in a separate process. [...]
3. **"Choose the groq models urself… keep in mind the rate limits so that we don't burn out our complete quota in testing itself… Gemini as secondary."** This is the instruction that kept the round-1 real runs at 4, 4 and 8 requests and made the stand-in necessary.

*What the assistant got wrong.* I did not catch these myself. The assistant found each one while checking its own results, and each is kept in `logs/` under a name that says what happened:
- Its citation parser understood `[ ]` but not `【 】`, so the first quality run wrongly declined 12 of 20 easy questions (`eval_run0_citeparse_bug*`).
[...]

*A decision where I overruled it.* The assistant's `.gitignore` excluded the three paper PDFs, since the fetch script can download them again and check them against `papers/MANIFEST.json`. I removed that rule, so the PDFs are in the repository.

*What in this submission is distinctly mine:*
- The instruction to protect the free quota, which shaped the whole test plan: tiny real runs, heavy load on the stand-in.
- [...]
- Reading vaani.dev and writing the sections on what I learned and on Vaani myself.
- Reading the brief first and settling the stack in the planning chat.

What the assistant did, in full: README section 12.

<!-- TABLES -->
