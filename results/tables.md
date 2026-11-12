
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

| setting                    | drafter      | question set   |   n |   quality % |   unanswerable question answered |   answerable question answered with wrong or missing facts |   declined |   tokens/answer (API usage, all calls) |   provider draft TTFT p50 ms |
|:---------------------------|:-------------|:---------------|----:|------------:|---------------------------------:|-----------------------------------------------------------:|-----------:|---------------------------------------:|-----------------------------:|
| A bm25 1200/200 k5         | gpt-oss-120b | easy 20        |  20 |       100   |                                0 |                                                          0 |          0 |                                   2312 |                        782.2 |
| B dense 1200/200 k5        | gpt-oss-120b | easy 20        |  20 |        80   |                                0 |                                                          1 |          0 |                                   2278 |                        793.2 |
| C dense+rerank 1200/200 k5 | gpt-oss-120b | easy 20        |  20 |        92.5 |                                0 |                                                          1 |          0 |                                   2288 |                        685   |
| A bm25 1200/200 k5         | gpt-oss-120b | hard 9         |   9 |        72.2 |                                0 |                                                          1 |          0 |                                   2222 |                        729.1 |
| A bm25 1200/200 k5         | gpt-oss-20b  | hard 9         |   9 |        83.3 |                                0 |                                                          0 |          0 |                                   2224 |                        961.6 |
| B dense 1200/200 k5        | gpt-oss-20b  | hard 9         |   9 |        66.7 |                                0 |                                                          1 |          0 |                                   2174 |                       1113.2 |
| C dense+rerank 1200/200 k5 | gpt-oss-20b  | hard 9         |   9 |        77.8 |                                0 |                                                          1 |          0 |                                   2209 |                       1174.2 |
| D bm25 600/100 k8          | gpt-oss-20b  | hard 9         |   9 |        61.1 |                                0 |                                                          1 |          0 |                                   1908 |                       1252.6 |
| E bm25 2400/300 k3         | gpt-oss-20b  | hard 9         |   9 |        66.7 |                                0 |                                                          0 |          0 |                                   2416 |                        884.6 |

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


### R1. Does Groq charge max_tokens or the tokens actually used? (real Groq, logs/groq_probe2_accounting_*.jsonl)

| model        | max_tokens sent   | prompt tokens   | completion tokens   | tokens charged (8000 - remaining header)   | actual usage   |
|:-------------|:------------------|:----------------|:--------------------|:-------------------------------------------|:---------------|
| gpt-oss-120b | 20                | 78              | 18                  | 98                                         | 96             |
| gpt-oss-120b | 20                | 78              | 18                  | 96                                         | 96             |
| gpt-oss-120b | 100               | 78              | 18                  | 96                                         | 96             |
| gpt-oss-120b | 300               | 78              | 18                  | 378                                        | 96             |
| gpt-oss-120b | 300               | 78              | 18                  | 96                                         | 96             |
| gpt-oss-120b | 1000              | 78              | 18                  | 96                                         | 96             |
| gpt-oss-120b | 3000              | 78              | 18                  | 544                                        | 96             |
| gpt-oss-120b | 3000              | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 20                | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 20                | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 200               | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 200               | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 800               | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 800               | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 1500              | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 1500              | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 4000              | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 4000              | 78              | 18                  | 96                                         | 96             |
| gpt-oss-20b  | 9000              | 78              | 18                  | 96                                         | 96             |


### R2. Real Groq under concurrency (tiny requests on the 20B, logs/groq_probe2_concurrency_*.jsonl)

| file       | in flight   | requests   | TTFT p50 ms   | TTFT p90 ms   | max ms   | all 200   | laptop stalls >100 ms (whole run)   | worst stall ms   |
|:-----------|:------------|:-----------|:--------------|:--------------|:---------|:----------|:------------------------------------|:-----------------|
| 1794488100 | 4           | 8          | 558           | 1060          | 1672     | True      | 153                                 | 1961.7           |
| 1794488100 | 8           | 16         | 1294          | 2815          | 2917     | True      | 153                                 | 1961.7           |
| 1794488100 | 12          | 24         | 774           | 1924          | 3009     | True      | 153                                 | 1961.7           |
| 1794488100 | 16          | 32         | 1682          | 3640          | 4378     | True      | 153                                 | 1961.7           |
| 1794497794 | 4           | 8          | 495           | 599           | 637      | True      | 113                                 | 1121500.3        |
| 1794497794 | 8           | 16         | 936           | 2060          | 2388     | True      | 113                                 | 1121500.3        |
| 1794497794 | 12          | 24         | 1005          | 1413          | 1752     | True      | 113                                 | 1121500.3        |
| 1794497794 | 16          | 32         | 662           | 791           | 891      | True      | 113                                 | 1121500.3        |

| in flight   | real Groq p50 ms (each probe file)   | stand-in p50 ms   | stand-in p90 ms   |
|:------------|:-------------------------------------|:------------------|:------------------|
| 1           | 556 (quiet run)                      | 828               | 1586              |
| 4           | 558 / 495                            | 949               | 2762              |
| 8           | 1294 / 936                           | 920               | 2398              |
| 12          | 774 / 1005                           | 1124              | 2281              |
| 16          | 1682 / 662                           | 1015              | 2941              |


### R3. A slow trickle on real Groq: does anything ever fail when nothing is stressing it? (logs/groq_probe2_quiet_*.jsonl)

| model        | requests   | non-200   | no first token   | TTFT p50 ms   | TTFT p95 ms   | TTFT max ms   | slower than 3x median   | laptop stalls >100 ms   |
|:-------------|:-----------|:----------|:-----------------|:--------------|:--------------|:--------------|:------------------------|:------------------------|
| gpt-oss-120b | 20         | 0         | 0                | 545           | 1240          | 2874          | 1                       | 231                     |
| gpt-oss-20b  | 60         | 0         | 0                | 556           | 2015          | 2738          | 5                       | 231                     |


### R4. Gemini, the backup provider (real calls; logs/gemini_probe_*.jsonl)

| model                 | tiny requests   | 200   | other   | TTFT p50 ms   | TTFT max ms   |
|:----------------------|:----------------|:------|:--------|:--------------|:--------------|
| gemini-2.5-flash      | 5               | 0     | 5       | -             | -             |
| gemini-2.5-flash-lite | 5               | 0     | 5       | -             | -             |
| gemini-3.1-flash-lite | 5               | 5     | 0       | 5468          | 12137         |
| gemini-3.5-flash-lite | 5               | 5     | 0       | 9623          | 22138         |

Deliberate burst of 30 tiny requests on gemini-3.1-flash-lite: statuses {200: 17, 429: 10, 503: 3}. First 429 body (excerpt): `[{
  "error": {
    "code": 429,
    "message": "You exceeded your current quota, please check your plan and billing details. For more information on this error, head to: https://aistudio.google.com/docs/rate-limits. To monitor your current usage, head to: https://ai.dev/rate-limit. \n* Quota exceeded for metric: generativelangu`


### R5. 10x burst of 150 in 10 s: round-1 settings versus round-2 settings on the same code, three seeds

| settings   | seed   | full answers   | of which degraded (k=3)   | quoted fallback   | gave up   | TTFT p95 ms   | full-answer TTFT p95 ms   | laptop stalls >100 ms   |
|:-----------|:-------|:---------------|:--------------------------|:------------------|:----------|:--------------|:--------------------------|:------------------------|
| round1     | 1      | 38             | 2                         | 108               | 0         | 17197.4       | 12515.4                   | 0                       |
| round1     | 2      | 38             | 0                         | 108               | 0         | 17597.5       | 13849.5                   | 1 (worst 106 ms)        |
| round1     | 3      | 38             | 1                         | 110               | 0         | 16451.0       | 14137.5                   | 0                       |
| round2     | 1      | 46             | 11                        | 100               | 0         | 4101.0        | 4517.4                    | 0                       |
| round2     | 2      | 46             | 11                        | 100               | 0         | 3892.0        | 4703.8                    | 0                       |
| round2     | 3      | 45             | 10                        | 102               | 0         | 3354.4        | 4028.9                    | 0                       |


### R5b. Which round-2 change did it? (seed 1; same 150-request burst)

| settings                                                                    | full answers (normal / degraded)   | quoted fallback   | TTFT p95 ms   | full-answer TTFT p95 ms   | laptop stalls >100 ms   |
|:----------------------------------------------------------------------------|:-----------------------------------|:------------------|:--------------|:--------------------------|:------------------------|
| round 1 as it was (stand-in charges max_tokens)                             | 36 / 2                             | 108               | 17197.4       | 12515.4                   | 0                       |
| round 1 + count admitted requests' coming draft calls                       | 34 / 2                             | 109               | 5269.5        | 12158.0                   | 14 (worst 714 ms)       |
| round 1 limiter, stand-in charges real usage                                | 34 / 3                             | 108               | 18072.3       | 14888.2                   | 23 (worst 1514 ms)      |
| + real-usage token estimate and refunds (stand-in still charges max_tokens) | 39 / 0                             | 108               | 5264.9        | 4557.7                    | 9 (worst 171 ms)        |
| + both of the above (stand-in still charges max_tokens)                     | 33 / 8                             | 105               | 3471.2        | 3539.4                    | 3 (worst 144 ms)        |
| all round-2 changes (stand-in charges real usage)                           | 35 / 11                            | 100               | 4101.0        | 4517.4                    | 0                       |


### R5c. Shedding threshold: 40% versus 30% of the remaining time (round-2 code, seed 1234)

| run                                    | N   | full answers   | quoted-passages fallback   | turned away   | gave up   | TTFT p50 ms   | TTFT p95 ms   | full-answer TTFT p95 ms   | tokens/full answer   | laptop stalls >100 ms   |
|:---------------------------------------|:----|:---------------|:---------------------------|:--------------|:----------|:--------------|:--------------|:--------------------------|:---------------------|:------------------------|
| shed at 40% of remaining time (chosen) | 150 | 46             | 101                        | 3             | 0         | 38.9          | 3556.4        | 3910.7                    | 1817.9               | 5 (worst 151 ms)        |
| shed at 30%                            | 150 | 45             | 101                        | 4             | 0         | 88.5          | 3980.7        | 5274.2                    | 1821.4               | 8 (worst 158 ms)        |


### R6. Daily token budget gone (stand-in, 10x, daily budget 40,000 tokens)

| run                                                  | N   | full answers   | quoted-passages fallback   | turned away   | gave up   | TTFT p50 ms   | TTFT p95 ms   | full-answer TTFT p95 ms   | tokens/full answer   | laptop stalls >100 ms   |
|:-----------------------------------------------------|:----|:---------------|:---------------------------|:--------------|:----------|:--------------|:--------------|:--------------------------|:---------------------|:------------------------|
| round 1: limiter told the budget                     | 54  | 20             | 34                         | 0             | 0         | 28.4          | 4506.0        | 5941.7                    | 2004.0               | 0                       |
| round 2: limiter told the budget                     | 54  | 20             | 34                         | 0             | 0         | 71.1          | 3825.8        | 5859.0                    | 2073.7               | 15 (worst 481 ms)       |
| round 1: limiter learns it from the 429              | 54  | 20             | 34                         | 0             | 0         | 22.8          | 2517.0        | 5113.9                    | 2004.0               | 0                       |
| round 2: limiter learns it from the 429              | 54  | 20             | 34                         | 0             | 0         | 37.1          | 2542.4        | 2998.4                    | 2084.9               | 12 (worst 413 ms)       |
| round 2 + second provider ready (also 40,000 tokens) | 54  | 40             | 14                         | 0             | 0         | 1190.3        | 3882.7        | 4101.7                    | 2082.7               | 19 (worst 1043 ms)      |

Draft calls by provider in the failover run: {'standin': 21, 'standin_fb': 21}. Failover events: 1.


### R6b. Real Groq (and Gemini) runs of round 2

| run                                                                             | N   | full answers   | quoted-passages fallback   | turned away   | gave up   | TTFT p50 ms   | TTFT p95 ms   | full-answer TTFT p95 ms   | tokens/full answer   | laptop stalls >100 ms   |
|:--------------------------------------------------------------------------------|:----|:---------------|:---------------------------|:--------------|:----------|:--------------|:--------------|:--------------------------|:---------------------|:------------------------|
| failover demo: Groq daily budget set to 6,000 tokens, then Gemini (20B drafter) | 4   | 4              | 0                          | 0             | 0         | 2307.0        | 12736.9       | 12736.9                   | 2161.0               | 28 (worst 409 ms)       |
| steady, about 0.035 req/s (20B drafter)                                         | 3   | 3              | 0                          | 0             | 0         | 2499.0        | 2797.1        | 2797.1                    | 2232.0               | 43 (worst 685 ms)       |

Calls sent by provider in the failover demo: {'groq': 6, 'gemini': 2}; failover events 0.


### R6c. The same 8-request burst in 3 seconds on real Groq, different code and different times

| run            | code                                       | drafter   | full answers   | quoted fallback   | turned away   | TTFT p95 ms   | median first token of the classify calls, ms   | laptop stalls >100 ms                      |
|:---------------|:-------------------------------------------|:----------|:---------------|:------------------|:--------------|:--------------|:-----------------------------------------------|:-------------------------------------------|
| real_burst     | round-1 code, earlier                      | 20B       | 3              | 4                 | 1             | 3230.0        | 736                                            | 0                                          |
| real_burst_r2  | round-2 code                               | 20B       | 0              | 7                 | 1             | 16583.8       | 3625                                           | 3 (worst 462 ms)                           |
| real_burst_r2b | round-2 code, repeat                       | 20B       | 0              | 7                 | 1             | 17067.8       | 8983                                           | 0                                          |
| cmp_r1code_a   | round-1 code (old server on :8100), pair A | 120B      | 3              | 4                 | 1             | 16877.7       | -                                              | n/a (server log is in server_mytest.jsonl) |
| cmp_r2code_a   | round-2 code, pair A (right after)         | 120B      | 2              | 5                 | 1             | 13999.9       | 741                                            | 21 (worst 497 ms)                          |
| cmp_r1code_b   | round-1 code (old server on :8100), pair B | 120B      | 1              | 6                 | 1             | 6054.0        | -                                              | n/a (server log is in server_mytest.jsonl) |
| cmp_r2code_b   | round-2 code, pair B (right after)         | 120B      | 1              | 6                 | 1             | 18049.5       | 832                                            | 10 (worst 967 ms)                          |
| real_burst_r2c | round-2 code, alone                        | 120B      | 2              | 5                 | 1             | 11667.1       | 730                                            | 0                                          |


### R7. Answer cache (identical questions share one answer; the load generator draws from 22 questions, so repeats are heavy)

| run                              | full answers   | quoted fallback   | gave up   | model calls   | cache hits   | joined an in-flight answer   | tokens used   | TTFT p50 ms   | TTFT p95 ms   | laptop stalls >100 ms   |
|:---------------------------------|:---------------|:------------------|:----------|:--------------|:-------------|:-----------------------------|:--------------|:--------------|:--------------|:------------------------|
| 10x burst of 150, cache off      | 44             | 102               | 0         | 84            | 0            | 0                            | 83988         | 603.5         | 4495.2        | 8 (worst 318 ms)        |
| 10x burst of 150, cache on       | 149            | 1                 | 0         | 58            | 95           | 33                           | 51800         | 14.6          | 4189.2        | 0                       |
| free-tier burst of 20, cache off | 4              | 16                | 0         | 8             | 0            | 0                            | 7161          | 28.8          | 2202.4        | 0                       |
| free-tier burst of 20, cache on  | 8              | 12                | 0         | 8             | 2            | 1                            | 8383          | 38.2          | 2236.3        | 0                       |


### R8. Retrieval only (no model calls): round-1 chunker (v1) versus the fixed chunker (v2), prompt trimming, fewer chunks

| setting                                | original: page hit %   | original: answer in context %   | original: context chars   | new: page hit %   | new: answer in context %   | new: context chars   |
|:---------------------------------------|:-----------------------|:--------------------------------|:--------------------------|:------------------|:---------------------------|:---------------------|
| v1 k5 (round 1)                        | 95.7                   | 100.0                           | 5906                      | 94.7              | 89.5                       | 6002                 |
| v1 k4                                  | 95.7                   | 95.7                            | 4770                      | 94.7              | 84.2                       | 4801                 |
| v2 k5 no table rows                    | 95.7                   | 100.0                           | 5906                      | 94.7              | 89.5                       | 6002                 |
| v2 k5 + table rows                     | 100.0                  | 100.0                           | 6349                      | 94.7              | 89.5                       | 6378                 |
| v2 k5 + 1 table row, no relevance gate | 100.0                  | 100.0                           | 6518                      | 94.7              | 89.5                       | 6655                 |
| v2 k5 + 1 table row, gated (chosen)    | 100.0                  | 100.0                           | 6245                      | 94.7              | 89.5                       | 6280                 |
| v2 k4 + table rows                     | 95.7                   | 95.7                            | 4999                      | 94.7              | 89.5                       | 5178                 |
| v2 k3 + table rows                     | 91.3                   | 91.3                            | 3734                      | 94.7              | 89.5                       | 3880                 |
| v2 k5 + tables, trim 800               | 100.0                  | 91.3                            | 4311                      | 94.7              | 89.5                       | 4292                 |
| v2 k5 + tables, trim 600               | 100.0                  | 87.0                            | 3267                      | 94.7              | 84.2                       | 3234                 |
| v2 k4 + tables, trim 800               | 95.7                   | 82.6                            | 3393                      | 94.7              | 89.5                       | 3499                 |
| v2 k4 + tables, trim 600               | 95.7                   | 78.3                            | 2572                      | 94.7              | 84.2                       | 2638                 |


### R9. How well did the limiter's token estimate match what the call really cost? (draft calls, from eval logs)

| estimate                                             | draft calls   | mean reserved tokens   | mean real tokens   | reserved / real, median   | reserved < real   |
|:-----------------------------------------------------|:--------------|:-----------------------|:-------------------|:--------------------------|:------------------|
| round 1 estimate (chars/3 + max_tokens), easy 20     | 20            | 2558                   | 1938               | 1.36                      | 0                 |
| round 2 estimate (chars/3.3 + typical reply), new 25 | 25            | 2448                   | 2191               | 1.12                      | 1                 |


### R9b. Every real request recorded in logs/, by provider and outcome (probes and pipeline calls)

| provider   | probe requests   | probe: 5xx   | probe: 429   | pipeline calls sent   | pipeline: 429   | pipeline: 5xx retried   | pipeline: timeout or connection errors   |
|:-----------|:-----------------|:-------------|:-------------|:----------------------|:----------------|:------------------------|:-----------------------------------------|
| gemini     | 62               | 3            | 10           | 115                   | 0               | 8                       | 9                                        |
| groq       | 393              | 0            | 10           | 598                   | 16              | 0                       | 2                                        |


### R10. Answer quality on real models, round 2 (rubric: data/RUBRIC.md, unchanged)

| run                                  | drafter               | question set    | n   | quality % (frozen rubric)   | after reading by hand (data/adjudication.json)   | unanswerable question answered   | answerable question answered with wrong or missing facts   | declined   | tokens/question   |
|:-------------------------------------|:----------------------|:----------------|:----|:----------------------------|:-------------------------------------------------|:---------------------------------|:-----------------------------------------------------------|:-----------|:------------------|
| run 1                                | gpt-oss-20b           | new hard 25     | 25  | 78.0                        | 85.4 (n=24)                                      | 1                                | 1                                                          | 1          | 2667              |
| run 1                                | gpt-oss-120b          | new hard 25     | 25  | 68.0                        | 79.2 (n=24)                                      | 1                                | 4                                                          | 1          | 2559              |
| run 1                                | gpt-oss-120b          | round-1 hard 9  | 9   | 88.9                        | 88.9 (n=9)                                       | 0                                | 0                                                          | 0          | 2473              |
| repeat A (the 6 imperfect questions) | gpt-oss-20b           | 6 of the new 25 | 6   | 8.3                         | 30.0 (n=5)                                       | 1                                | 1                                                          | 1          | 2610              |
| repeat B (the 6 imperfect questions) | gpt-oss-20b           | 6 of the new 25 | 6   | 8.3                         | 30.0 (n=5)                                       | 1                                | 1                                                          | 1          | 2624              |
| run 1                                | gemini-3.1-flash-lite | new hard 25     | 25  | 76.0                        | 82.6 (n=23)                                      | 1                                | 0                                                          | 2          | 2539              |

Questions that did not score 1.0 in at least one run:

| question   | gpt-oss-20b run 1   | gpt-oss-120b run 1   | gemini-3.1-flash-lite run 1   |
|:-----------|:--------------------|:---------------------|:------------------------------|
| n08        | 1.0                 | 0.0                  | 1.0                           |
| n10        | 1.0                 | 0.0                  | 1.0                           |
| n11        | 1.0                 | 1.0                  | declined                      |
| n12        | 0.0                 | 0.0                  | 1.0                           |
| n14        | 0.0                 | 0.0                  | 0.0                           |
| n16        | 0.0                 | 0.0                  | 0.0                           |
| n17        | 0.5                 | 0.0                  | 1.0                           |
| n18        | declined            | declined             | 1.0                           |
| n19        | 1.0                 | 1.0                  | declined                      |
| u03        | 1.0                 | 1.0                  | 0.0                           |
| u06        | 0.0                 | 0.0                  | 0.0                           |
