
Claude
The_Relay_Assignment_Brief.pdf
The_Relay_Assignment_Brief.pdf
PDF
Alright Claude I need to tackle this assignment for a intern , I need you to first read the first page and tell me what is that we need to do , what all do we need to consider , what all the requirements , and what are the constraints , and what tradeoff's am I to make , then we will discuss further

Read a file
1072a46a-The_Relay_Assignment_Brief.pdf

This is only page 1, as you asked. The footer says “Page 1”, so there may be more pages with deliverables or grading criteria.

What you need to do
Build a small working version of a multi-step LLM pipeline called “The Relay” in Python, C++ or Go. It answers engineers’ questions about three research papers, with citations, and it has to hold up under bursty, unreliable load. The brief is partly an engineering exercise and partly a test of judgment: it says outright that it left details out on purpose and wants to see what you decide and how you justify it.

There are three parts of work:

The pipeline. It needs at least four steps, at least one tool call, at least one branch or loop, and one step that retrieves passages from the library. The scenario describes the shape: work out what the person is asking, retrieve passages, decide what to do, draft a cited reply, and check the reply before sending.
A stand-in model service you write yourself. It must be able to be slow, fail, refuse when a limit is hit, slow down under load, and stream its reply a piece at a time. You calibrate it from measurements of the real Groq service.
Experiments. First send a modest number of real requests to Groq to learn its latency spread, its limits, and what it does when a limit is hit. Then run your pipeline under at least three load shapes you design, such as steady, a sudden burst, and sustained overload. Use the stand-in for loads the real service can’t take. Keep the raw results from both.
What to consider
Library. Only three papers, at exact versions: Attention Is All You Need (1706.03762 v7), Moshi (2410.00037 v1), and Dynamic Chunking for End-to-End Hierarchical Sequence Modeling (2507.07955 v2). You fetch them yourself.
Grounding. Every answer cites where in the papers it came from. If the papers don’t say, the assistant must say so rather than guess. Expect test questions that can’t be answered from memory and some the papers don’t answer at all.
Traffic. Requests arrive in bursts, usually when something breaks and many users hit it at once. Most requests need a few steps, some need many, and a few loop.
Provider behaviour. Groq limits requests per minute, tokens per minute and requests per day. The limits differ by plan and model and can change without notice, so discover them rather than hard-code them. Tools time out, and some calls are slow without failing, which is harder to handle than a clean error.
Users. They’re waiting and they abandon sooner than you’d expect, so latency and cancellation matter.
Requirements
Python, C++ or Go, your choice.
At least four steps, one tool call, one branch or loop, and a retrieval step.
Citations on every answer, with an explicit “the papers don’t say” path.
A real Groq free-tier account and key, plus your own calibration of its limits.
A stand-in service with these behaviours: slow, failing, refusing at a limit, degrading under load, streaming.
A statement of where the stand-in is least like the real service.
At least three load shapes of your own design.
Raw results kept for both the real service and the stand-in.
Stated tradeoffs: wherever you give up one goal for another, say so.
Constraints
Goals that can’t all be met. The company wants fast, good, cheap and nobody turned away, and the brief says it can’t have all four.
Hard rule. The assistant never sends a wrong or embarrassing answer just to stay fast. Correctness works as a floor, not something to trade freely.
Free tier. It will not survive heavy load, which is why the stand-in exists.
Ambiguity. “Fast” is undefined. You pick the target and the numbers.
Tradeoffs you’ll have to make
Fast vs good. The verification step improves quality but adds a call and latency. Do you always verify, or only when retrieval confidence is low? Do you use a small, fast model for some steps and a large one for others?
Good vs cheap. More retrieved passages, more loop iterations and retries all improve quality and burn tokens against your per-minute and per-day caps.
Cheap vs nobody turned away. Under overload you can queue, which raises latency and risks abandonment. You can degrade, for example by skipping verification or using a smaller model, which lowers quality. Or you can shed load, which turns people away. You have to choose which of these happens first, and for which requests.
Never wrong vs fast. When the system is stressed, the safe fallback is a slower answer or an honest “I can’t answer that right now”, not a cheaper, shakier answer.
Retries vs overload. Retrying a slow or failed call can help one request and make the whole system worse. You need backoff and budgets, plus a policy on timeouts versus waiting out slow calls.
Simple vs many-step requests. A few requests loop. Without a step cap, one of them can eat the shared rate limit and starve everyone else. A cap means some hard questions get a worse answer.
Defining “fast”. Pick something like a p95 latency or time-to-first-token target, and decide whether streaming counts as fast. Streaming improves perceived speed without changing total time.
Calibration fidelity. The stand-in is only as good as your measurements. You’ll need to be honest about where it differs from Groq, such as how its latency tails and rate-limit signals behave.
The most important design decision is probably the overload policy: when a limit is hit, who waits, who gets a degraded answer and who gets turned away. The load experiments are meant to show that choice working.

I’ve only seen page 1. If there’s a second page, send it over, or tell me and we’ll go on to scoping and design.

alright now for page 2

Read a file
1072a46a-The_Relay_Assignment_Brief.pdf

Page 2 is the write-up spec, and it changes how you should build. The write-up is two pages, with required headings in a fixed order, and the numbers in it must match your raw data. The page ends mid-section, just before the results tables, so there is probably a page 3.

Required headings, in order
What I built and why. The design, plus the one decision that shaped it most.
The real service and my stand-in. The Groq limits you found and how you found them. Also how the stand-in behaves, how you calibrated it from real measurements, and where it differs most from the real thing.
Results. For each load shape, report time to first token and total time, each at the median and the slow end. You choose and state the percentiles and the number of requests. Also report failures and given-up requests, and say which runs were real and which used the stand-in. Every number goes in the results tables. Include at least one number you couldn’t have guessed without running it. Also report answer quality on at least 15 questions you wrote yourself, and tokens used per answer.
Where the time goes. Take one slow request and split its latency into waiting, working and retrying. Say whether the delay came before or after the first token, and show how you know.
When a limit is hit. Say what the system does at the per-minute limit and at the per-day limit. Who is delayed, who is dropped, who gets a weaker answer, and why.
Retrieval: quality versus cost. This heading is inserted after 5. Try at least three settings for chunk size, number of chunks fetched, and any re-ranking. For each, report answer quality, tokens per answer and time to first token. Choose one, say why, and say what retrieval does when a limit is close.
How this library will mislead a naive retriever. This is also inserted after 5. Name three ways, each with an example question where it goes wrong.
Retries. Your policy, plus one case where retrying made things worse.
What the person sees. At 3pm the daily budget is gone. Describe the reply a waiting person receives.
What I’m unsure about, what I left out, what I learned. This covers your least certain assumption and what breaks if it’s wrong, two things you deliberately didn’t build, and one new thing you learned, taught in your own words.
Feedback on Vaani. Visit vaani.dev and give your honest view in a few lines: what stood out, what confused you, and one thing you’d change.
How I worked with the assistant. This section comes last and has three parts:
Your real conversation history with the assistant, not a cleaned-up one. If the tool can’t export it, give the prompts instead.
Half a page on the three prompts that mattered most and why, one thing it got wrong that you caught and how you caught it, and one decision where you overruled it.
What in the submission is distinctly yours.
The brief doesn’t say exactly where the Vaani heading goes. I’ve put it after the main body and before the final section, but check whether page 3 says anything.

The results tables are required. Fill every cell, write “not measured” where you didn’t measure, use milliseconds for time and one decimal for percentages, and copy the tables into the write-up. Reviewers recompute them from your raw file, so your logs have to reproduce them exactly.

What this means for how you work
Instrument first. Log timestamps for queue entry, send, first token, last token, each retry and each give-up, per request. Sections 3, 4 and 8 can’t be written without that data, and you can’t go back and collect it afterwards.
Include a surprise. The brief wants a result that couldn’t have been guessed without running it. Real Groq behaviour will probably supply one, such as odd latency tails, unusual rate-limit headers or a limit that behaves differently from its docs.
Define quality before you run. You write at least 15 questions and need a scoring rule, including questions the papers can’t answer and the expected “the papers don’t say” behaviour. Settle the rubric before comparing retrieval settings, or you’ll be tempted to tune it to the results.
Make the daily-limit path real. Section 9 means you need an actual degraded-mode response when the daily budget is exhausted, not just a description.
Keep the conversation history. Section 12 asks for the real, uncleaned transcript. That includes this session, so keep it exported or saved.
Don’t count on me for the personal parts. The Vaani feedback, the “new to me” explanation, and the choices you overruled should come from you.
The two-page limit is tight against 12 sections plus tables, so you’ll have to be terse. Do you want me to read page 3 next, in case there are more tables or submission details?


later I also fixed up these issues , 
## 1. Fix the weak spots the tests found

**The big-burst delay (the missed 8-second target).**
- *Problem:* people admitted just under the 40% line were told "short wait" but waited much longer. The slowest 5% waited 13.2 s.
- *How:* make the wait estimate more cautious, for example by adding a safety margin, or lowering the cut-off to 30%. Re-run the burst test and see if the slowest-5% wait falls under 8 s. The cost is that a few more people get the quoted fallback.

**The "come back tomorrow" message.**
- *Problem:* the limit is a rolling window, so the real wait might be 11 minutes.
- *How:* use the retry-after time from the error to say "try again in about N minutes". This is a small change and an honest one.

**The deleted chunks of the third paper.**
- *Problem:* my filter that removes reference lists also deleted 26 real chunks, including the start of Appendix A.
- *How:* only drop chunks after the actual "References" heading and before the next major heading. Then rebuild and re-run the search comparison. Add a test question about Appendix A.

## 2. Better answers on tables and numbers

*Problem:* table numbers come out of the PDF scrambled. The 213M-parameters question was right only 1 time in 6.
*How:* extract tables as tables, with the header joined to each row. PyMuPDF can find tables. Or keep a whole table together as one chunk. Then re-run the 9 hard questions to see if the score goes up.
## 3. More confidence in the results

*Problem:* only 9 hard questions, so one question moves the score by 11 points. The real-service runs were also tiny (4, 4 and 8 requests).
*How:*
**More questions.** Write 20 to 30 more hard ones, freeze them first, then run every setting.
**Repeat runs.** Run each setting 3 times and report the range, so luck is separated from real differences.
**A bigger real run.** Do it when the daily quota is fresh. Keep it small enough to stay under the daily limit.
## 4. Make the fake Groq more truthful

*Problem:* the failure rates were invented, and the busy-slowdown line came from only two tests.
*How:* run the real service at 12-way and 16-way concurrency to check the slowdown line. Leave a long, quiet test running to see whether real failures or stalls ever appear. Then replace my guessed numbers with measured ones, or say "still unmeasured".
## 5. Use the backup provider (Gemini)

*Problem:* it's configured but never tried. If Groq runs out of daily tokens, the system can only quote the papers.
*How:* when the daily wall hits, send the request to Gemini instead. This needs its limits probed first, the same way as Groq. Then test the switch on the stand-in by making it fail, and check the answers still pass the same verification.
## 6. Smarter use of the quota

**Cache answers.** Ask the same question twice and the second reply costs nothing.
**Shorter prompts.** Each answer sends about 1,800 prompt tokens. Sending fewer or shorter chunks would let more questions fit in the 8,000-a-minute budget. Test how much accuracy drops.
**Confirm the token accounting.** I guessed that Groq charges the maximum answer length up front. If it only charges for what's used, my limiter wastes about a quarter of the quota. A quick test would settle it: send a request with a large max_tokens, then check what the headers say was used.
## 7. Make it easier to run and trust

A single command that runs everything small (tests, a 5-question real check, table rebuild).
A check that fails if a quality score drops, so a change that hurts answers gets caught.
A short "how to add a paper" guide, because the system is only proven on three.
If needed make a edit in your answers for sections for my submission for the project using the info in the readme I gave you earlier

I have no results from these fixes: your list says how to do each one, but not what came out. So I’ve edited the sections that become false once the fixes are in, and left [brackets] for every number that has to come from your regenerated tables.

I’ve assumed each item was finished. If any were only planned, don’t describe them as done. List them under “what I left out” in section 10, which the brief wants anyway.

Two rules before you paste anything:

Re-run everything the change touches. The chunk and table fixes alter chunk IDs, so rebuild with make_tables.py and re-run the retrieval comparison. Don’t leave old rows next to new ones. Keep the old runs in logs/ as before-fix runs, as you did with run1_before_queue_aware/.
Keep the new questions honest. You wrote them after seeing the earlier results, so say that, and freeze them before any setting runs.
Fix	README sections that change
1a Burst delay	1, 3 (“Did it meet fast?”), 5
1b Retry-after message	9
1c Chunk filter	6, 7 (point 3), 3d
2 Table extraction	7 (point 1), 3d, 6
3 More questions, repeats, bigger real run	3a, 3d, top scope note
4 Stand-in measured	2 (limitations 1, 2), 10
5 Gemini	1, 2, 5, 9, 10, 12(c)
6 Quota use	1, 2 (limitation 5), 10
7 Tooling	“Reproducing it”
Section 3: “Did it meet fast?” (replace the burst sentences)
The 150-request burst at 10× first missed: full answers had a p95 time to first token of 13,231.3 ms, because the wait estimate was too optimistic for requests admitted just under the 40% line. I [added a safety margin of [M] ms to the estimate / lowered the cut-off from 40% to [30]%] and re-ran it (logs/load_[tag].jsonl). The p95 for full answers is now [X] ms, [under / still over] the 8,000 ms target. The cost is that quoted-passage fallbacks rose from 108 to [Y] of 150, so [Y−108] more people got a quote instead of a written answer. The original run stays in logs/ as the before.

Section 9: the message
Replace “Please try again tomorrow.” with “Please try again in about {N} minutes.” The first line of the fallback has the same flaw, so change “budget for today is used up” to “budget is used up for now”. Then replace the “two weaknesses” paragraph:

One weakness I know about: the quoted passages are only as relevant as BM25’s coverage score lets them be, and in s_daily_learned one reply quoted a figure caption. The other, a reply that said “tomorrow” when the limit is a rolling window, I fixed. The message now takes N from the 429’s retry-after, so 648 s reads as “about 11 minutes”.

If Gemini now catches the daily wall (below), the reply most people see at 3 pm is a Gemini-written answer. This message then only appears when both providers are out.

Section 7: points 1 and 3
Add to point 3, replacing “I didn’t test that exact question”:

I fixed the filter so it only drops chunks between the real “References” heading and the next major heading. Appendix A is back in the index ([N] H-Net chunks kept instead of 120). I added “What does Appendix A of the dynamic chunking paper say about related work?” as h10, and it [scored X].

Add to point 1:

I then extracted tables as tables, with the header joined to every row [or kept each table as one chunk]. The 213M question went from 1 correct in 6 runs to [k] in [n], and the hard-set score from 83.3% to [X]% (n=[N], so one question is [100/N] points).

Section 3d and “A note on scope”
Update the question counts (20 easy plus [N] hard, [n] answerable). Report repeated runs as a range, such as “[min]–[max] over 3 runs”, and recompute “one question is 11 points”. In the scope note, replace “tiny” with the new real-run sizes.

Section 2: stand-in limitations 1, 2 and 5
Heavy overload. The slowdown was a line through two points. I added 12-way and 16-way runs on the real service, and the slope is now [x] per extra in-flight request (it was 0.0625), [still roughly linear / curved]. Beyond 16 in flight the stand-in is still extrapolating.
Rare events. I left a [N]-minute quiet test running ([M] requests). It saw [k] 5xx, [j] stalls and [i] slow-but-successful calls, so the stand-in’s rates are now [measured / still guesses, because the sample is too small].
Token accounting. I sent a request with max_tokens=[N] and a short prompt. The headers dropped by [prompt+max_tokens / actual usage], so Groq [does / does not] reserve the maximum up front.
Section 10
Rewrite “least certain assumption” around whatever is still unverified. Candidates from your README are the 20B’s daily pool being assumed equal to the 120B’s, Groq’s queue_time not being modelled, and failure rates if the quiet test saw none. Then replace the two things not built:

A persistent, multi-process limiter. The limiter’s state, including limits learned from 429 bodies, lives in memory, so a restart forgets them and two workers would each spend the full budget.
Request hedging for slow calls. [unchanged text]
Gemini ripple (sections 1, 2, 5, 9)
Section 2. Add a Gemini row to the limits table, with limits from scripts/probe_gemini.py.
Section 5, daily paragraph. Replace “no new model call starts” with: “no new Groq call starts. New arrivals go to Gemini [when? only on the daily wall / also on repeated 429s]. If Gemini is also out, they get the quoted-passages reply or an honest decline.”
Section 1, decision paragraph. Add: “Failing over to Gemini isn’t the sloppy swap I ruled out, because its drafts pass the same deterministic check. It scored [X]% on the hard set against 83.3% for the 20B.”
Daily-budget table. The existing rows become “before failover”. Add new rows from the run where the stand-in fails the way Groq’s daily wall does.
Sections 1, “Reproducing it” and 12(c)
Section 1, step list. If you added caching, add a step 0: “Cache: identical questions, after normalisation, return the stored verified answer at no token cost.” Add: “The cache is off in every evaluation and load run, so tokens per answer and latency aren’t flattered.” [CONFIRM]
Reproducing it. Add: “make check runs the tests, a 5-question real check and the table rebuild, and fails if a quality score drops below [threshold]. docs/ADD_A_PAPER.md explains how to add a paper. pytest now runs [N] tests.”
12(c). Replace the Gemini bullet with: “Choosing Gemini as a secondary provider, first left configured but unused and later [probed, wired in and tested on the stand-in].” Add: “After the tests, choosing which weak spots to fix ([list]) and which to leave ([list]). [CONFIRM which of these you decided and which the assistant proposed.]”
Send me the regenerated tables, or the new numbers, and tell me which of the seven were finished. I’ll fill in the brackets and check the prose against the figures.





Claude finished the response


