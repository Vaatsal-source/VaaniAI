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

16 of 19 requests were charged exactly their real usage whatever `max_tokens` was (20 to 4,000 on the 20B, 20 to 3,000 on the 120B; one 9,000 request was accepted and charged 96). The other 3 were charged extra (see table): they do not track `max_tokens`.
