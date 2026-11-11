| setting                    | drafter      | question set   | n   | quality %   | confident-wrong   | declined   | tokens/answer (API usage, all calls)   | provider draft TTFT p50 ms   |
|:---------------------------|:-------------|:---------------|:----|:------------|:------------------|:-----------|:---------------------------------------|:-----------------------------|
| A bm25 1200/200 k5         | gpt-oss-120b | easy 20        | 20  | 100.0       | 0                 | 0          | 2312                                   | 782.2                        |
| B dense 1200/200 k5        | gpt-oss-120b | easy 20        | 20  | 80.0        | 0                 | 0          | 2278                                   | 793.2                        |
| C dense+rerank 1200/200 k5 | gpt-oss-120b | easy 20        | 20  | 92.5        | 0                 | 0          | 2288                                   | 685.0                        |
| A bm25 1200/200 k5         | gpt-oss-120b | hard 9         | 9   | 72.2        | 0                 | 0          | 2222                                   | 729.1                        |
| A bm25 1200/200 k5         | gpt-oss-20b  | hard 9         | 9   | 83.3        | 0                 | 0          | 2224                                   | 961.6                        |
| B dense 1200/200 k5        | gpt-oss-20b  | hard 9         | 9   | 66.7        | 0                 | 0          | 2174                                   | 1113.2                       |
| C dense+rerank 1200/200 k5 | gpt-oss-20b  | hard 9         | 9   | 77.8        | 0                 | 0          | 2209                                   | 1174.2                       |
| D bm25 600/100 k8          | gpt-oss-20b  | hard 9         | 9   | 61.1        | 0                 | 0          | 1908                                   | 1252.6                       |
| E bm25 2400/300 k3         | gpt-oss-20b  | hard 9         | 9   | 66.7        | 0                 | 0          | 2416                                   | 884.6                        |
