# Answer-quality rubric (fixed before any retrieval-setting comparison)

Questions: `data/questions.json` (20 total: 16 answerable incl. 1 cross-paper, 4 unanswerable).
Frozen before experiments; do not edit after the first retrieval-setting run.

Scoring is automatic and objective:

**Answerable / cross-paper** (score 0, 0.5 or 1)
- 1.0 = every `must` group has at least one regex hit in the answer text AND at least one cited
  chunk (a) is from a gold paper, (b) overlaps a gold page (+-1 page tolerance for chunk spill), and
  the answer is not an abstention.
- 0.5 = all `must` groups hit but citation is missing / wrong paper / wrong page.
- 0 = any `must` group missing, or the system abstained ("the papers don't say") on an answerable question.

**Unanswerable** (score 0 or 1)
- 1.0 = answer contains the abstain marker "the papers don't say" and matches none of the `forbid` patterns.
- 0 = otherwise. A confident invented answer is additionally counted as an **embarrassing** answer.

**Safe-failure** (e.g. "I can't answer right now" under overload) is counted separately as
`declined`, scored 0 for quality but NOT counted as wrong/embarrassing.

Also reported per run: citation validity (% of cited chunk ids that exist in the retrieved set,
checked deterministically), tokens per answer (API `usage`), TTFT.
Quality is the mean score over the 20 questions, reported as a percentage with one decimal.
