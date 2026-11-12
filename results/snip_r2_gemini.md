| model                 | tiny requests   | 200   | other   | TTFT p50 ms   | TTFT max ms   |
|:----------------------|:----------------|:------|:--------|:--------------|:--------------|
| gemini-2.5-flash      | 5               | 0     | 5       | -             | -             |
| gemini-2.5-flash-lite | 5               | 0     | 5       | -             | -             |
| gemini-3.1-flash-lite | 5               | 5     | 0       | 5468          | 12137         |
| gemini-3.5-flash-lite | 5               | 5     | 0       | 9623          | 22138         |

A burst of 30 tiny requests: {200: 17, 429: 10, 503: 3}. The 429 body carries the limit ("limit: 15 ... requests per minute") and the wait ("Please retry in 53.4s"); there is no `retry-after` header and no `x-ratelimit-*` header at all. The 503 replies say "experiencing high demand".
