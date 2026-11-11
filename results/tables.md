
### A. Real Groq probe (logs/groq_probe_1794406507.jsonl; models-404 log: groq_probe_0_model404_*.jsonl)

| probe                       |   n |   TTFT p50 ms |   TTFT p95 ms |   TTFT max ms |   total p50 ms |   total p95 ms |
|:----------------------------|----:|--------------:|--------------:|--------------:|---------------:|---------------:|
| latency:openai/gpt-oss-20b  |  15 |         706.9 |        1678.3 |        1777.6 |          968.1 |         1728.6 |
| latency:openai/gpt-oss-120b |  15 |         420.9 |         736.6 |         836.8 |          517.5 |          801.4 |
| conc4                       |   4 |         534.1 |         627.1 |         639.3 |          593.1 |          702.9 |
| conc8                       |   8 |        1029.9 |        1326.5 |        1434.7 |         1092.5 |         1390.9 |

Deliberate burst of 40 tiny requests (small model): status counts {200: 30, 429: 10}; first 429 was request #7 in send order; retry-after header values: ['2'].

First 429 body (limit kind and numbers appear ONLY here): `{"error":{"message":"Rate limit reached for model `openai/gpt-oss-20b` in organization `org_01m75egbx4e6karavgqg9q3r3b` service tier `on_demand` on requests per minute (RPM): Limit 30, Used 30, Requested 1. Please try again in 2s. Need more tokens? Upgrade to `


### B1. REAL Groq runs (drafting model gpt-oss-20b; N is tiny because of the 8k tokens/min and 200k tokens/day walls)

|                                        | real_steady   | real_steady2   |   real_burst |
|:---------------------------------------|:--------------|:---------------|-------------:|
| N requests                             | 4             | 4              |          8   |
| completed (any status)                 | 4             | 4              |          8   |
| answered/abstained (full model answer) | 4             | 4              |          3   |
| extractive (degraded)                  | 0             | 0              |          4   |
| shed (turned away)                     | 0             | 0              |          1   |
| declined (unverified)                  | 0             | 0              |          0   |
| abandoned (gave up)                    | 0             | 0              |          0   |
| errors                                 | 0             | 0              |          0   |
| retries (total)                        | 0             | 0              |          0   |
| n with a first token                   | 4             | 4              |          8   |
| TTFT p50 ms                            | 3737.3        | 2624.0         |        967.9 |
| TTFT p95 ms                            | 8468.9        | 4890.6         |       3230   |
| Total p50 ms                           | 3742.1        | 2628.8         |        973.2 |
| Total p95 ms                           | 8579.5        | 4893.0         |       3239.5 |
| TTFT p50 ms, full answers only         | 3737.3        | 2624.0         |       2098.6 |
| TTFT p95 ms, full answers only         | 8468.9        | 4890.6         |       3210.7 |
| TTFT p50 ms, extractive only           | not measured  | not measured   |         22.5 |
| tokens/answered request (mean)         | 2192.8        | 2193.8         |       1876   |
| abandon %                              | 0.0           | 0.0            |          0   |
| shed %                                 | 0.0           | 0.0            |         12.5 |


### B2. STAND-IN, free-tier limits (rpm 30, tpm 8000, rpd 1000, tpd 200000)

|                                        |   s_steady_free |   s_burst_free |   s_overload_free |
|:---------------------------------------|----------------:|---------------:|------------------:|
| N requests                             |            19   |           20   |              30   |
| completed (any status)                 |            19   |           20   |              30   |
| answered/abstained (full model answer) |            15   |            3   |              12   |
| extractive (degraded)                  |             4   |           17   |              18   |
| shed (turned away)                     |             0   |            0   |               0   |
| declined (unverified)                  |             0   |            0   |               0   |
| abandoned (gave up)                    |             0   |            0   |               0   |
| errors                                 |             0   |            0   |               0   |
| retries (total)                        |             1   |            0   |               0   |
| n with a first token                   |            19   |           20   |              30   |
| TTFT p50 ms                            |          1817.4 |           26.2 |              41.2 |
| TTFT p95 ms                            |          3363.8 |         5310.4 |            4315.8 |
| Total p50 ms                           |          1981.4 |           31.8 |              56.1 |
| Total p95 ms                           |          3452.4 |         5314.7 |            4319.4 |
| TTFT p50 ms, full answers only         |          2065.7 |         1825.6 |            1603.4 |
| TTFT p95 ms, full answers only         |          3650.9 |         4908.8 |            4578.5 |
| TTFT p50 ms, extractive only           |           817.6 |           25.4 |              24.5 |
| tokens/answered request (mean)         |          2029.9 |         2033   |            1678.8 |
| abandon %                              |             0   |            0   |               0   |
| shed %                                 |             0   |            0   |               0   |


### B3. STAND-IN, 10x limits (a bigger plan)

|                                        | s_steady_t10   |   s_burst_t10 |   s_overload_t10 |
|:---------------------------------------|:---------------|--------------:|-----------------:|
| N requests                             | 82             |         150   |            248   |
| completed (any status)                 | 82             |         149   |            248   |
| answered/abstained (full model answer) | 82             |          38   |            165   |
| extractive (degraded)                  | 0              |         108   |             77   |
| shed (turned away)                     | 0              |           3   |              6   |
| declined (unverified)                  | 0              |           0   |              0   |
| abandoned (gave up)                    | 0              |           1   |              0   |
| errors                                 | 0              |           0   |              0   |
| retries (total)                        | 3              |           4   |             16   |
| n with a first token                   | 82             |         149   |            248   |
| TTFT p50 ms                            | 1324.5         |         585.1 |           1762.8 |
| TTFT p95 ms                            | 4465.3         |       18071.7 |           6877.6 |
| Total p50 ms                           | 1328.7         |         593.1 |           1768.2 |
| Total p95 ms                           | 4470.7         |       18103.5 |           6882.1 |
| TTFT p50 ms, full answers only         | 1324.5         |        3943.3 |           2471.9 |
| TTFT p95 ms, full answers only         | 4465.3         |       13231.3 |           6880   |
| TTFT p50 ms, extractive only           | not measured   |         102.7 |             24.4 |
| tokens/answered request (mean)         | 2019.4         |        1940.8 |           1778.9 |
| abandon %                              | 0.0            |           0.7 |              0   |
| shed %                                 | 0.0            |           2   |              2.4 |


### B4. STAND-IN, daily token budget exhausted (tpd 40000): limiter told vs limiter learns from the 429

|                                        |   s_daily_known |   s_daily_learned |
|:---------------------------------------|----------------:|------------------:|
| N requests                             |            54   |              54   |
| completed (any status)                 |            54   |              54   |
| answered/abstained (full model answer) |            20   |              20   |
| extractive (degraded)                  |            34   |              34   |
| shed (turned away)                     |             0   |               0   |
| declined (unverified)                  |             0   |               0   |
| abandoned (gave up)                    |             0   |               0   |
| errors                                 |             0   |               0   |
| retries (total)                        |             1   |               1   |
| n with a first token                   |            54   |              54   |
| TTFT p50 ms                            |            28.4 |              22.8 |
| TTFT p95 ms                            |          4506   |            2517   |
| Total p50 ms                           |            36   |              29.9 |
| Total p95 ms                           |          4514.9 |            2522.6 |
| TTFT p50 ms, full answers only         |          1516.4 |            1465.6 |
| TTFT p95 ms, full answers only         |          5941.7 |            5113.9 |
| TTFT p50 ms, extractive only           |            19.2 |              16.2 |
| tokens/answered request (mean)         |          2004   |            2004   |
| abandon %                              |             0   |               0   |
| shed %                                 |             0   |               0   |


### B5. STAND-IN retries at 30% injected failures, 0.4 req/s (80% of capacity)

|                                        |   s_retry_none |   s_retry_budget |   s_retry_unbounded |
|:---------------------------------------|---------------:|-----------------:|--------------------:|
| N requests                             |           82   |             82   |                82   |
| completed (any status)                 |           82   |             82   |                82   |
| answered/abstained (full model answer) |           55   |             64   |                72   |
| extractive (degraded)                  |           27   |             18   |                10   |
| shed (turned away)                     |            0   |              0   |                 0   |
| declined (unverified)                  |            0   |              0   |                 0   |
| abandoned (gave up)                    |            0   |              0   |                 0   |
| errors                                 |            0   |              0   |                 0   |
| retries (total)                        |            0   |             29   |                84   |
| n with a first token                   |           82   |             82   |                82   |
| TTFT p50 ms                            |          817.8 |           1155.9 |              2459.1 |
| TTFT p95 ms                            |         2815.3 |           4111.4 |              6522.7 |
| Total p50 ms                           |          824.3 |           1164.1 |              2465.5 |
| Total p95 ms                           |         2820.6 |           4116   |              6527.7 |
| TTFT p50 ms, full answers only         |          890.5 |           1288.5 |              2274.8 |
| TTFT p95 ms, full answers only         |         2933.1 |           3860   |              5509.5 |
| TTFT p50 ms, extractive only           |          530.7 |            787.2 |              4498.9 |
| tokens/answered request (mean)         |         1681.8 |           1827.3 |              1945.2 |
| abandon %                              |            0   |              0   |                 0   |
| shed %                                 |            0   |              0   |                 0   |


### B6. STAND-IN retries at 30% injected failures, 0.55 req/s (110% of capacity)

|                                        |   s_retrysat_none |   s_retrysat_budget |   s_retrysat_unbounded |
|:---------------------------------------|------------------:|--------------------:|-----------------------:|
| N requests                             |             113   |               113   |                  113   |
| completed (any status)                 |             113   |               113   |                  113   |
| answered/abstained (full model answer) |              77   |                75   |                   81   |
| extractive (degraded)                  |              36   |                38   |                   32   |
| shed (turned away)                     |               0   |                 0   |                    0   |
| declined (unverified)                  |               0   |                 0   |                    0   |
| abandoned (gave up)                    |               0   |                 0   |                    0   |
| errors                                 |               0   |                 0   |                    0   |
| retries (total)                        |               0   |                40   |                  100   |
| n with a first token                   |             113   |               113   |                  113   |
| TTFT p50 ms                            |            1138.4 |              1456.5 |                 2022.1 |
| TTFT p95 ms                            |            4037.5 |              6269.2 |                 8530.1 |
| Total p50 ms                           |            1142.8 |              1459.1 |                 2023.6 |
| Total p95 ms                           |            4166.4 |              6271.9 |                 8531.9 |
| TTFT p50 ms, full answers only         |            1131.2 |              1569.8 |                 2163.3 |
| TTFT p95 ms, full answers only         |            3909.6 |              4956.8 |                 8374.1 |
| TTFT p50 ms, extractive only           |            1141.2 |              1204.6 |                   13.2 |
| tokens/answered request (mean)         |            1704.8 |              1860.5 |                 1943.3 |
| abandon %                              |               0   |                 0   |                    0   |
| shed %                                 |               0   |                 0   |                    0   |


*Pre-fix runs (wait estimate ignored the queue; patience=deadline=25 s) are kept in logs/run1_before_queue_aware/ and are summarised in the write-up, section 5.*


### B6b. Calls sent and tokens reserved in the retry-saturation runs (from server logs)

| run                  |   provider calls sent |   retries |   tokens reserved (est) |   tokens in successful calls (API usage) |
|:---------------------|----------------------:|----------:|------------------------:|-----------------------------------------:|
| s_retrysat_none      |                   228 |         0 |                  285255 |                                   134729 |
| s_retrysat_budget    |                   261 |        40 |                  361836 |                                   142981 |
| s_retrysat_unbounded |                   277 |       100 |                  411873 |                                   158526 |


### C. Who gets what in a burst: outcome by arrival order (4 equal groups, earliest arrivals first)

**s_burst_free** (n=20)

| group               |   extractive_overload |   full answer |
|:--------------------|----------------------:|--------------:|
| 1st quarter         |                     2 |             3 |
| 2nd                 |                     5 |             0 |
| 3rd                 |                     5 |             0 |
| 4th (last arrivals) |                     5 |             0 |

**s_burst_t10** (n=150)

| group               |   abandoned |   extractive_overload |   full answer |   shed |
|:--------------------|------------:|----------------------:|--------------:|-------:|
| 1st quarter         |           1 |                     8 |            29 |      0 |
| 2nd                 |           0 |                    28 |             9 |      0 |
| 3rd                 |           0 |                    36 |             0 |      1 |
| 4th (last arrivals) |           0 |                    36 |             0 |      2 |

**real_burst** (n=8)

| group               |   extractive_overload |   full answer |   shed |
|:--------------------|----------------------:|--------------:|-------:|
| 1st quarter         |                     0 |             2 |      0 |
| 2nd                 |                     1 |             1 |      0 |
| 3rd                 |                     2 |             0 |      0 |
| 4th (last arrivals) |                     1 |             0 |      1 |


### D. Answer quality, tokens and provider time-to-first-token per retrieval setting (REAL Groq; rubric: data/RUBRIC.md)

| setting                    | drafter      | question set   |   n |   quality % |   confident-wrong |   declined |   tokens/answer (API usage, all calls) |   provider draft TTFT p50 ms |
|:---------------------------|:-------------|:---------------|----:|------------:|------------------:|-----------:|---------------------------------------:|-----------------------------:|
| A bm25 1200/200 k5         | gpt-oss-120b | easy 20        |  20 |       100   |                 0 |          0 |                                   2312 |                        782.2 |
| B dense 1200/200 k5        | gpt-oss-120b | easy 20        |  20 |        80   |                 0 |          0 |                                   2278 |                        793.2 |
| C dense+rerank 1200/200 k5 | gpt-oss-120b | easy 20        |  20 |        92.5 |                 0 |          0 |                                   2288 |                        685   |
| A bm25 1200/200 k5         | gpt-oss-120b | hard 9         |   9 |        72.2 |                 0 |          0 |                                   2222 |                        729.1 |
| A bm25 1200/200 k5         | gpt-oss-20b  | hard 9         |   9 |        83.3 |                 0 |          0 |                                   2224 |                        961.6 |
| B dense 1200/200 k5        | gpt-oss-20b  | hard 9         |   9 |        66.7 |                 0 |          0 |                                   2174 |                       1113.2 |
| C dense+rerank 1200/200 k5 | gpt-oss-20b  | hard 9         |   9 |        77.8 |                 0 |          0 |                                   2209 |                       1174.2 |
| D bm25 600/100 k8          | gpt-oss-20b  | hard 9         |   9 |        61.1 |                 0 |          0 |                                   1908 |                       1252.6 |
| E bm25 2400/300 k3         | gpt-oss-20b  | hard 9         |   9 |        66.7 |                 0 |          0 |                                   2416 |                        884.6 |

Per-question misses (score < 1):

- A bm25 1200/200 k5 / gpt-oss-120b / easy 20: none

- B dense 1200/200 k5 / gpt-oss-120b / easy 20: q03=0.0(abstained), q07=0.0(abstained), q12=0.0(answered), q14=0.0(abstained)

- C dense+rerank 1200/200 k5 / gpt-oss-120b / easy 20: q12=0.0(answered), q14=0.5(answered)

- A bm25 1200/200 k5 / gpt-oss-120b / hard 9: h01=0.0(answered), h03=0.0(abstained), h04=0.5(answered)

- A bm25 1200/200 k5 / gpt-oss-20b / hard 9: h03=0.0(abstained), h04=0.5(answered)

- B dense 1200/200 k5 / gpt-oss-20b / hard 9: h02=0.0(abstained), h03=0.0(answered), h04=0.5(answered), h05=0.5(answered)

- C dense+rerank 1200/200 k5 / gpt-oss-20b / hard 9: h03=0.0(abstained), h06=0.0(answered)

- D bm25 600/100 k8 / gpt-oss-20b / hard 9: h02=0.0(abstained), h03=0.0(abstained), h04=0.5(answered), h06=0.0(answered)

- E bm25 2400/300 k3 / gpt-oss-20b / hard 9: h02=0.0(abstained), h04=0.0(abstained), h06=0.5(answered), h07=0.5(answered)


### E. Retrieval only (no model calls): is the gold page among the retrieved chunks? 23 answerable questions (easy+hard)

|                               |   n |   gold page retrieved % |   context chars/answer |   search p50 ms |   search p95 ms | misses                       |
|:------------------------------|----:|------------------------:|-----------------------:|----------------:|----------------:|:-----------------------------|
| A bm25 1200/200 k5            |  23 |                    95.7 |                   5902 |             2.5 |             7.1 | ['h04']                      |
| B dense 1200/200 k5           |  23 |                    91.3 |                   5999 |           195.8 |           846   | ['q07', 'h04']               |
| C dense+rerank 1200/200 k5    |  23 |                   100   |                   5999 |          8254.6 |         17664.9 | []                           |
| D bm25 600/100 k8             |  23 |                    91.3 |                   4780 |             8.1 |            22   | ['q09', 'h04']               |
| E bm25 2400/300 k3            |  23 |                    82.6 |                   7071 |             2.9 |             6.4 | ['q09', 'h04', 'h06', 'h07'] |
| F bm25 1200/200 k3 (degraded) |  23 |                    91.3 |                   3567 |             1.7 |             3.4 | ['h04', 'h07']               |
