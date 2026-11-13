# The Relay — Technical Planning and Engineering Discussion

*An edited and reorganised account of the planning conversation. The technical decisions, measurements, and unresolved questions are retained, but the discussion has been grouped by engineering topic for clarity. This is not a verbatim conversation export.*

---

## 1. Understanding the problem and defining the engineering goals

**Me:** I need to build an internship assignment called *The Relay*. Before implementing anything, I want to understand the requirements, constraints, architectural decisions, and tradeoffs. What exactly are we building?

**Assistant:** We are building a small, multi-step LLM system that answers engineers' questions using a library of three research papers:

- Attention Is All You Need (1706.03762, v7).
- Moshi (2410.00037, v1).
- Dynamic Chunking for End-to-End Hierarchical Sequence Modeling (2507.07955, v2).

The system needs to retrieve relevant passages, generate answers grounded in those passages, cite its sources, and explicitly acknowledge when the papers do not contain the answer.

However, this is not simply a RAG implementation. The main engineering challenge is making the system reliable under bursty traffic and an unreliable, rate-limited model provider.

The assignment has three major requirements:

1. Build an LLM pipeline with at least four steps, a retrieval operation, a tool call, and a branch or loop.
2. Build a stand-in model service that reproduces important aspects of Groq's behaviour, including latency, streaming, failures, rate limits, and load-dependent slowdowns.
3. Evaluate the complete system under different traffic patterns, retaining raw experimental results.

**Me:** So the real objective is not just answer quality. We have to demonstrate that the complete system behaves sensibly when its external dependencies become unreliable.

**Assistant:** Exactly. The four competing objectives are speed, answer quality, cost, and availability. We cannot maximise all four simultaneously.

One requirement is non-negotiable: correctness must remain a minimum quality floor. Under pressure, the system should be willing to delay, return a weaker but honest fallback, or decline a request rather than fabricate an answer.

---

## 2. System architecture — how The Relay should work

**Me:** Let's translate these requirements into an actual architecture. I don't want to start coding independent components without understanding how requests move through the system.

**Assistant:** We should think of The Relay as two connected systems:

- The request-processing pipeline, responsible for answering questions.
- The traffic and provider-management layer, responsible for controlling how requests reach external model services.

The architecture can be represented as follows.

### A. Request-processing pipeline

1. **Request intake and interpretation**

   Receive the user's question, identify what information is being requested, and decide whether it needs retrieval or a more complex reasoning path.

2. **Knowledge retrieval**

   Search the three-paper library and retrieve relevant passages. BM25 is the retrieval approach referenced in the current implementation discussion.

3. **Decision and control**

   Determine whether the retrieved evidence is sufficient. Depending on the result, the pipeline can proceed, retrieve additional evidence, or take an explicit insufficient-evidence path.

4. **Answer generation**

   Send the question and retrieved context to the model provider. Generate an answer grounded in the available evidence.

5. **Verification**

   Check that the answer is supported by the retrieved passages and that citations are present. Unsupported claims should not be sent as established facts.

6. **Response and fallback**

   Stream the answer where possible. When generation cannot proceed safely, return an appropriate fallback, such as relevant quoted passages or an honest decline.

The retrieval, decision, generation, and verification stages provide the basic multi-step orchestration. The branching and possible repeated retrieval provide the conditional and iterative behaviour required by the assignment.

### B. Traffic and provider-management layer

**Me:** Where does rate limiting fit? I assume it shouldn't be mixed into the actual retrieval logic.

**Assistant:** Correct. Provider management should sit around the model calls rather than being scattered throughout the pipeline.

Conceptually, the request path becomes:

`User → Admission control → Request queue → Pipeline → Model provider → Verification → Response`

The admission-control layer manages:

- Requests per minute.
- Tokens per minute.
- Requests per day.
- Estimated waiting time.
- Overload and request rejection.
- Request cancellation and abandonment.

The provider adapter is responsible for communicating with the actual model service or the stand-in.

This separation is important because the pipeline should not need to know whether it is talking to Groq or a simulated provider.

### C. Model-provider abstraction

The provider layer has three relevant roles:

| Provider | Purpose |
|---|---|
| Groq | Real service used for calibration and initial experiments |
| Stand-in service | Controlled simulation for burst and overload experiments |
| Gemini | Potential secondary provider for failover |

The stand-in should reproduce observed provider behaviour rather than simply return predetermined responses. It needs configurable latency, streaming, failures, rate-limit refusals, and load-dependent degradation.

Gemini was configured as a possible backup, but the original discussion explicitly says it had not yet been tested.

---

## 3. Technology stack and implementation decisions

**Me:** What technology choices should we make, and why? I want the stack to be justified by the requirements rather than selecting tools simply because they are popular.

**Assistant:** The assignment permits Python, C++, or Go. The implementation discussed here points towards a Python-based approach.

The technologies and tools explicitly referenced in the planning notes are:

| Component | Technology | Purpose |
|---|---|---|
| Pipeline and orchestration | Python | Implement the multi-step workflow |
| Model inference | Groq API | Real LLM generation and calibration |
| Retrieval | BM25 | Retrieve relevant paper passages |
| Document processing | PDF processing; PyMuPDF proposed for table extraction | Build the searchable paper library |
| Simulated inference | Custom stand-in service | Reproduce provider behaviour |
| Secondary inference | Gemini API | Potential provider failover |
| Testing | pytest | Validate components and regression behaviour |
| Experiment records | JSONL | Preserve raw request-level results |
| Experiment tooling | Python scripts, including `make_tables.py` and `scripts/probe_gemini.py` | Rebuild results and probe services |

We should not assume that a particular web framework, database, distributed queue, or orchestration framework was used: those choices are not established by the conversation.

**Me:** Why not immediately introduce a vector database or a more complicated retrieval stack?

**Assistant:** Because the library contains only three papers. BM25 gives us a relatively simple baseline that is easy to inspect, evaluate, and debug.

The important question is not whether a sophisticated retriever looks impressive. It is whether the retriever consistently provides the evidence required by the answer-generation stage.

We should first establish a reliable baseline and then compare alternative chunking, retrieval depth, and reranking configurations.

**Me:** And why build our own stand-in instead of just testing Groq?

**Assistant:** Because the real free-tier service cannot reliably sustain the heavy traffic patterns required by the assignment.

The stand-in allows us to control workload conditions, repeat experiments, and test overload policies without exhausting the real provider's quota.

However, its behaviour must be calibrated against actual observations. A simulator that produces convenient results but does not resemble the real service would undermine the experiments.

---

## 4. Engineering tradeoffs and the decisions behind them

**Me:** Let's discuss the actual tradeoffs. Which architectural choices have the biggest consequences?

**Assistant:** There are several.

### A. Answer quality versus latency

Verification improves reliability but introduces additional processing and potentially additional model calls.

Two possible strategies are:

- Verify every answer, accepting additional latency.
- Use conditional verification, applying more expensive checks when evidence is weak or the question is complex.

The first is safer and simpler. The second may improve average latency but requires a dependable way of identifying risky answers.

Given the assignment's correctness requirement, verification cannot simply be removed during overload.

### B. Retrieval quality versus token consumption

Retrieving more passages can improve answer coverage, but it also increases:

- Prompt-token consumption.
- Model inference time.
- TPM pressure.
- The possibility of irrelevant context confusing the model.

The assignment therefore requires experimentation with at least three configurations of chunk size, retrieval depth, and reranking.

We should select a configuration based on measured quality, token usage, and time to first token rather than retrieval quality alone.

### C. Availability versus overload protection

When demand exceeds the provider's capacity, we have three broad options:

| Strategy | Benefit | Cost |
|---|---|---|
| Queue requests | Preserves the opportunity to answer | Increases latency and abandonment |
| Degrade responses | Reduces model usage | May provide less complete answers |
| Shed load | Protects the remaining system | Some users receive no generated answer |

The system needs a deliberate admission policy. Accepting every request and allowing the queue to grow indefinitely is not a reliable solution.

### D. Retries versus system-wide congestion

Retries can recover from temporary failures, but they also generate additional traffic.

Under overload, repeated retries can make the original congestion worse. We therefore need:

- Bounded retries.
- Backoff.
- A total retry budget.
- Clear distinctions between temporary failures and rate-limit refusals.
- A policy for slow calls that have not failed.

### E. Simple requests versus complex requests

Some questions require additional retrieval or reasoning iterations.

Without a step or iteration cap, one complex request can consume a disproportionate share of the shared token budget.

A cap improves fairness but may prevent some difficult questions from receiving a complete answer.

**Me:** Which tradeoff should shape the whole design?

**Assistant:** Overload behaviour. We need to decide which requests wait, which receive a quoted-passage fallback, which can use another provider, and which must be rejected.

The system should never silently sacrifice correctness just to satisfy a latency target.

---

## 5. Experimental architecture and the initial evaluation

**Me:** How do we demonstrate that these choices work instead of simply describing an architecture?

**Assistant:** We need two categories of experiments.

### A. Real-provider calibration

First, use a real Groq account to measure:

- Latency distribution.
- Streaming behaviour.
- Rate-limit responses.
- RPM, TPM, and RPD constraints.
- Slow-but-successful requests.
- Behaviour when limits are reached.

The limits should be discovered through experiments instead of hard-coded assumptions.

### B. Controlled load experiments

Next, use the stand-in to evaluate different traffic patterns.

The assignment requires at least three load shapes. Suitable examples are:

1. Steady traffic.
2. A sudden burst, where many users arrive almost simultaneously.
3. Sustained overload, where incoming demand remains above the system's capacity.

Each experiment should capture:

- Time to first token.
- Total response time.
- Failures.
- Requests given up or abandoned.
- Token consumption.
- Retry counts.
- The number of users receiving full answers versus fallbacks.

The stand-in makes it possible to study conditions that the free-tier provider cannot sustain.

### C. Instrumentation

**Me:** What should we log? I don't want to realise after the experiments that I missed a measurement.

**Assistant:** Log timestamps for each request at the important transitions:

- Queue entry.
- Provider submission.
- First token.
- Last token.
- Each retry.
- Timeout or give-up.
- Final response.

Keep raw records for both Groq and the stand-in.

This makes it possible to separate queue waiting time, model processing time, and retry delay rather than treating total latency as a single number.

The logs should be retained independently of the summary tables so that the reported statistics can be reproduced.

---

## 6. Results obtained and what they reveal

**Me:** Let's evaluate the results rather than just discussing the architecture. What did the initial experiments tell us?

**Assistant:** The existing measurements exposed several weaknesses.

### A. Sudden-burst performance

The 150-request burst at 10× load missed the 8-second target.

| Metric | Observed result |
|---|---:|
| Burst size | 150 requests |
| Load shape | 10× burst |
| Target | 8,000 ms |
| p95 time to first token for full answers | 13,231.3 ms |
| Quoted-passage fallbacks | 108 / 150 |
| Fallback proportion | 72% |

The admission controller used a 40% threshold. Requests admitted just below this threshold were told to expect a short wait, but the slowest 5% experienced a substantially longer delay.

This suggests that the waiting-time estimator was too optimistic.

The initial results demonstrate why admission decisions must be evaluated against actual tail latency, not just average latency.

### B. Retrieval and answer quality

The initial hard-question evaluation contained only nine questions.

The reported hard-set score was 83.3%.

One particularly revealing case involved a question about a paper's 213M-parameter configuration:

| Metric | Initial result |
|---|---:|
| Correct answers | 1 |
| Repeated attempts | 6 |
| Observed correctness | 16.7% |

The issue was traced to poor extraction of tabular information from PDFs. Table numbers and their corresponding headers were becoming disconnected.

Another observed retrieval issue occurred in `s_daily_learned`, where one fallback quoted a figure caption rather than an appropriately relevant passage.

These are not merely language-model problems. They expose weaknesses in document ingestion, retrieval, and evidence selection.

**Me:** So increasing the model's capability wouldn't necessarily solve this?

**Assistant:** Correct. When the information enters the model incorrectly, better generation alone cannot reliably recover the missing structure.

The PDF extraction and chunking pipeline needs attention before we attribute every incorrect answer to the model.

### C. Real-provider experiment size

The real-service runs contained only 4, 4, and 8 requests across the reported runs.

These samples are useful for initial exploration, but they are too small for strong statistical conclusions about tail latency, failures, and rare provider behaviour.

### D. Token efficiency

The reported prompt size was approximately 1,800 tokens per answer, while an 8,000-token-per-minute budget was referenced.

This suggests that retrieval depth and prompt construction can have a substantial influence on throughput.

However, the assumption that Groq reserves the maximum output allowance up front was not yet verified experimentally.

### E. Stand-in fidelity

The stand-in's overload slowdown was fitted using only two measurements. The referenced slope was 0.0625.

Failure rates were also invented rather than measured from sufficiently large real-service observations.

Consequently, the stand-in was useful for controlled testing but was not yet a highly validated model of Groq's behaviour.

---

## 7. Diagnosing the weaknesses and improving the architecture

**Me:** Based on those results, I want to fix the actual weaknesses. Let's prioritise improvements according to their impact.

**Assistant:** We should approach this in several layers.

### A. Improve admission control and burst latency

**Observed problem:** The burst test produced a p95 time to first token of 13,231.3 ms, exceeding the 8-second target.

**Proposed improvement:**

- Introduce a safety margin into the waiting-time estimate.
- Alternatively, reduce the admission threshold from 40% to approximately 30%.
- Re-run the 150-request burst.
- Compare the new p95 latency and number of quoted-passage fallbacks.

The tradeoff is explicit: a more conservative admission policy protects accepted users from unexpectedly long waits but may send more users to the fallback path.

The improvement is not validated until the new experiment provides the updated p95 and fallback count.

### B. Use the actual retry-after information

**Observed problem:** The system suggested that users should come back tomorrow, even though the provider's limit was based on a rolling window.

**Proposed improvement:**

Use the retry-after information supplied by the 429 response.

For example, a retry-after value of 648 seconds should translate into a message such as:

"Please try again in about 11 minutes."

This is more accurate than presenting a rolling-window limit as a daily reset.

### C. Repair reference-list filtering

**Observed problem:** The reference-list filter removed 26 legitimate chunks, including the beginning of Appendix A in the dynamic chunking paper.

**Proposed improvement:**

Only discard material between the actual References heading and the next major heading, rather than deleting every chunk after a broad textual match.

Then:

- Rebuild the paper index.
- Re-run the retrieval comparison.
- Add an explicit Appendix A question to the evaluation set.
- Check whether the newly indexed material can be retrieved correctly.

This addresses evidence loss during ingestion rather than trying to compensate for it at generation time.

### D. Improve table extraction

**Observed problem:** PDF tables were extracted in a scrambled form, causing poor numerical answers.

**Proposed improvement:**

Extract tables as structured tables, joining the header information to each row. PyMuPDF table extraction was suggested as one possible implementation.

An alternative is to retain an entire table as a single chunk when preserving its structure is more important than keeping every chunk small.

After the change, repeat the 213M-parameter question across multiple runs and compare the hard-set answer-quality score.

### E. Improve experimental confidence

**Observed problem:** Nine hard questions and small real-provider runs are not sufficient for strong statistical conclusions.

**Proposed improvement:**

- Create another 20–30 difficult questions.
- Freeze the evaluation set before running retrieval comparisons.
- Evaluate every retrieval configuration on the same questions.
- Repeat each configuration three times.
- Report the observed range, not just a single score.
- Increase the real-service sample when the daily quota permits.

One important methodological detail: some new questions were written after observing previous failures. That should be disclosed, and the questions should be frozen before subsequent comparisons.

### F. Make the stand-in more representative

**Observed problem:** The failure behaviour was partly invented, and the slowdown estimate relied on only two real-service measurements.

**Proposed improvement:**

- Run real-service experiments at 12-way and 16-way concurrency.
- Re-estimate the load-dependent slowdown.
- Perform a longer quiet test for rare failures and stalls.
- Replace guessed failure rates with observed values where the sample permits.
- Clearly label still-unmeasured behaviour instead of pretending it has been calibrated.

The stand-in should remain an approximation, particularly outside the concurrency range actually measured.

### G. Introduce tested provider failover

**Me:** Gemini is configured, so why not use it when Groq reaches its daily limit?

**Assistant:** This is a sensible extension, but configuration is not proof of reliability.

We should first probe Gemini's limits and behaviour, then integrate it as a secondary provider.

When Groq reaches its daily wall:

1. Stop initiating new Groq calls.
2. Route eligible new requests to Gemini.
3. Apply the same evidence and verification requirements.
4. Provide a quoted-passage fallback or honest decline if Gemini is also unavailable.

The critical architectural principle is that provider failover must not bypass answer verification.

The Gemini path needs its own experiments before its results can be reported.

### H. Improve quota efficiency

Several optimisations were identified:

**Caching:** Identical normalised questions can reuse stored verified answers, avoiding repeat model calls.

**Prompt reduction:** Test whether fewer or shorter retrieved passages reduce token consumption without unacceptable quality loss.

**Token-accounting validation:** Test whether the provider accounts for the maximum requested output or actual token usage. The existing limiter may be wasting quota if its reservation assumption is wrong.

These changes should be measured individually so their effect on latency, cost, and answer quality is visible.

---

## 8. Reliability, observability, and reproducibility

**Me:** I also want someone else to be able to reproduce the results. What should the final engineering workflow look like?

**Assistant:** The experiment process should be repeatable through a small set of commands.

The proposed improvements include:

- A single `make check` command that runs tests, a small real-service check, and the results-table rebuild.
- A quality regression check that fails when answer quality drops below a predefined threshold.
- A guide explaining how to add a new paper to the knowledge library.
- Persistent raw JSONL logs for all experiments.
- Clear separation between before-fix and after-fix results.

For example, the original burst experiment should remain available as a before-fix result rather than being overwritten by the new run.

This is important because the engineering story is not simply that the final version performs better. We should be able to demonstrate which change produced which improvement.

Two additional architectural limitations were identified:

1. **Persistent multi-process rate limiting was not built.** The limiter's state lives in memory, so a restart can forget learned limits and separate workers could independently spend the same quota.
2. **Request hedging for slow calls was not built.** The system therefore does not yet have a complete strategy for simultaneously protecting against long-running requests and avoiding duplicate provider work.

These omissions should be disclosed rather than hidden.

---

## 9. What should happen when the system reaches its limits?

**Me:** I want the final behaviour to be understandable from the user's perspective. What happens if the system is overloaded or Groq runs out of quota?

**Assistant:** The user-facing response depends on which limit is reached.

| Situation | Intended behaviour |
|---|---|
| Short-lived congestion | Queue the request when the estimated wait is acceptable |
| Excessive predicted wait | Offer a quoted-passage fallback or decline |
| Rolling rate limit | Use the actual retry-after duration |
| Groq daily limit | Route to Gemini if available and validated |
| Both providers unavailable | Return relevant evidence or an honest decline |
| Insufficient paper evidence | State that the papers do not provide the answer |

The important distinction is between a service being temporarily unable to generate an answer and the source documents not containing the information.

The system should not confuse those two cases or invent an answer to conceal either limitation.

---

## 10. What the current engineering evidence actually establishes

**Me:** Before writing the report, let's distinguish what we have demonstrated from what still needs testing.

**Assistant:** Based on the measurements and discussion available, the evidence can be grouped as follows.

| Area | Established evidence | Remaining uncertainty |
|---|---|---|
| Pipeline requirements | Multi-step retrieval and generation design | Exact implementation details should be confirmed against the code |
| Burst handling | 150-request, 10× test; p95 TTFB of 13,231.3 ms | Performance after admission-control changes |
| Fallback behaviour | 108 of 150 requests used quoted passages | New fallback rate after policy changes |
| Retrieval quality | A figure-caption retrieval issue was observed | Results after retrieval changes |
| PDF tables | 213M question correct in only 1 of 6 attempts | Improvement after structured extraction |
| Hard-set quality | Reported score of 83.3% | Larger frozen test set and repeated runs |
| Real-provider calibration | Three reported runs containing 4, 4, and 8 requests | More representative concurrency and failure measurements |
| Stand-in | Some load behaviour approximated using measured observations | Failure rates and higher-concurrency behaviour remain insufficiently validated |
| Gemini | Configured as a secondary provider | Limits, integration, failover, and quality results |
| Caching and token accounting | Optimisation opportunities identified | Actual quota and quality impact |

There is also an evaluation-accounting issue worth checking: the reported 83.3% hard-set score is presented alongside a nine-question hard set. If the score is calculated directly over nine binary-scored questions, each question changes the percentage by approximately 11.1 points. The denominator or scoring aggregation should therefore be verified before submission.

The current results establish several real weaknesses. They do not yet establish that the proposed fixes have resolved them.

---

## 11. Prioritised next steps

**Me:** What should I implement and test next? I want the changes to be ordered sensibly rather than working on optimisations while correctness problems remain.

**Assistant:** I would prioritise them as follows.

| Priority | Work | Validation |
|---|---|---|
| 1 | Fix reference filtering and PDF table extraction | Appendix A and 213M-parameter questions |
| 2 | Improve burst admission estimates | New 150-request burst and p95 TTFB |
| 3 | Correct retry-after messaging | Test against a real rolling-window 429 |
| 4 | Expand and freeze the evaluation set | Repeated quality comparisons |
| 5 | Improve Groq calibration | 12-way, 16-way, and quiet-period tests |
| 6 | Implement and test Gemini failover | Simulated Groq daily-wall failure |
| 7 | Reduce prompt and quota consumption | Compare tokens, latency, and quality |
| 8 | Improve reproducibility and documentation | `make check`, regression tests, and paper-ingestion guide |

The order matters. First ensure that the correct evidence enters the system. Then improve scheduling and reliability. After that, optimise costs and make the entire experiment reproducible.

---

## 12. Final engineering takeaway

**Me:** What is the biggest lesson from this project so far?

**Assistant:** The main lesson is that building a reliable LLM application is not the same as building an application that can call an LLM.

The model is just one component. Overall system quality depends on the interaction between document ingestion, retrieval, orchestration, provider behaviour, admission control, retries, verification, and fallback policies.

The initial experiments showed this clearly:

- A fast model does not guarantee fast user-perceived responses when queueing dominates latency.
- Good generation cannot compensate for missing or scrambled source evidence.
- Retries can increase congestion instead of solving it.
- A simulator is only useful when its assumptions are supported by real measurements.
- A fallback policy is part of the architecture, not an afterthought.

The goal for the next iteration is therefore not simply to make The Relay faster. It is to make its behaviour more predictable, its answers more trustworthy, its resource usage more efficient, and its results reproducible.