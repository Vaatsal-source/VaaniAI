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

---
## Round 2 additions (the rubric above is unchanged)

* `data/questions_hard2.json` (25 questions: 19 answerable or cross-paper, 6 unanswerable) was written and frozen on
  2026-11-12 before any model run on it; its hash is in `data/FROZEN.txt`. It was written after the v2 chunker existed and
  knowing the table rows would be available, so table questions are over-represented on purpose (n05, n06, n08, n10, n12).
* The scoring is the same automatic regex scoring. Reading the answers by hand afterwards showed three kinds of problem
  with the *questions or patterns*, not with the model: a pattern that rejects "32 000" or "500 k" written with a space (n10, n12),
  and one defective question (u06: the Moshi paper does report a speaker-consistency figure of about 98-99%, so "speaker
  identification accuracy" is not cleanly unanswerable). These are not edited out of the frozen file. They are listed with
  my reading in `data/adjudication.json`, and README appendix F reports the score both as the rubric computed it and after
  the adjudication, so nobody has to take either number on trust.
* `data/questions_smoke.json` is five questions copied from the earlier sets for `scripts/check.py --real`.
