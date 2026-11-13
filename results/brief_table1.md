| Limit | Value found | How I found it | Confidence |
|:--|:--|:--|:--|
| Requests per minute | 30 (both gpt-oss models) | Only in a 429 body ("Limit 30, Used 30, Requested 1") after a 40-request burst; no header carries it (`logs/groq_probe_1794406507.jsonl`) | high |
| Tokens per minute | 8,000 | Header `x-ratelimit-limit-tokens`, confirmed by a TPM 429; refills about 133 tokens/s | high |
| Requests per day | 1,000, refilling 1 per 86.4 s | Header `x-ratelimit-limit-requests` and its reset ("1m26.4s") | medium (never used up) |
| Tokens per day | 200,000 on the 120B (about 85 answers); the 20B's is higher | Only in a 429 body, hit by accident ("Limit 200000, Used 199538"); no header | high (120B), low (20B) |
| Requests in flight | None found up to 16 | 4, 8, 12, 16 at once, twice each (`logs/groq_probe2_concurrency_*.jsonl`) | low |
| Reply when a limit is hit | HTTP 429, JSON text names the limit and numbers; `retry-after` in seconds; tokens charged as used, not `max_tokens` | The 429s above; `logs/groq_probe2_accounting_*.jsonl` | high |
| Time to recover | RPM 2 s; TPM seconds; TPD 648 s for a 1,962-token request (rolling refill, about 2.3 tokens/s) | 429 headers and bodies; a test reproduces the 648 s | high |
