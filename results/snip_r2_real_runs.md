| run                                                                             | N   | full answers   | quoted-passages fallback   | turned away   | gave up   | TTFT p50 ms   | TTFT p95 ms   | full-answer TTFT p95 ms   | tokens/full answer   | laptop stalls >100 ms   |
|:--------------------------------------------------------------------------------|:----|:---------------|:---------------------------|:--------------|:----------|:--------------|:--------------|:--------------------------|:---------------------|:------------------------|
| failover demo: Groq daily budget set to 6,000 tokens, then Gemini (20B drafter) | 4   | 4              | 0                          | 0             | 0         | 2307.0        | 12736.9       | 12736.9                   | 2161.0               | 28 (worst 409 ms)       |
| steady, about 0.035 req/s (20B drafter)                                         | 3   | 3              | 0                          | 0             | 0         | 2499.0        | 2797.1        | 2797.1                    | 2232.0               | 43 (worst 685 ms)       |

Calls sent by provider in the failover demo: {'groq': 6, 'gemini': 2}.
