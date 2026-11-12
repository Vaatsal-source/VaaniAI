# How to add a paper

The three papers are data, not code. Adding a fourth takes about ten minutes and no changes to `relay/`.

## 1. Describe it in `config.yaml`

```yaml
papers:
  mypaper:                       # short key: it appears inside citations, e.g. [C:mypaper:12]; lowercase letters only
    arxiv: 2401.00001v2          # exact version; also the PDF file name
    desc: My Paper Short Title   # one phrase, shown to the routing model
    keywords: "my-method|special term|dataset name"   # regex: questions matching it are searched in this paper only
```

The routing prompt is generated from these entries, so there is nothing else to edit.
Keep the keywords specific. A word that appears in several papers ("transformer", "attention") sends the question to all
of them, which is correct but halves the number of chunks each paper contributes (see README section 7).

## 2. Download it and record its hash

```
python scripts/fetch_papers.py          # fetches every paper in config.yaml, rewrites papers/MANIFEST.json
```

## 3. Rebuild the chunks

```
python -m relay.ingest                  # writes data/chunks_*.json (v1 and v2, three chunk sizes) and prints chunk counts per paper
```

Look at what it did before trusting it. These are the things that went wrong with the first three papers:

* **Section labels are guesses.** Print them (`python -c "import json; ..."`) and check that a table row or a page number
  was not taken for a heading. The v2 heading pattern only accepts single-digit section numbers, `A`-`D` appendix letters
  and the word `References`. A paper with section 10 or more, or with appendices `E` and beyond, needs the pattern widened in
  `relay/ingest.py` (`HEAD2`).
* **The reference list.** v2 marks a chunk as references only if it lies inside the span from the `References` heading to the
  next numbered or lettered heading and also looks like citations (`[12]`, `arXiv`, `et al.`, years). If a paper puts an
  appendix with no letter after its references, those pages are kept, which is the safe direction.
* **Tables.** `table_blocks()` rebuilds rows from word positions. It finds tables that have wide gaps between cells and at
  least eight numbers. Check `data/chunks_v2_1200_200.json` for entries with `"kind": "table"` and read a few. Figures
  with many numeric labels can look like tables; the numeric-density test rejects most, not all.

## 4. Write questions for it and freeze them

Add 5 to 10 questions to a **new** file, for example `data/questions_mypaper.json`, in the same format as
`data/questions_hard2.json` (gold paper, gold pages, regex groups for the facts, and a few that the paper cannot answer).
Include at least one table number and one question that two papers could both seem to answer. Then record the file's hash in
`data/FROZEN.txt` **before** running anything on it, as the other sets do. Do not edit a frozen file afterwards.

## 5. Check retrieval (free) and set the guard

```
python scripts/retrieval_round2.py "v2 k5 + 1 table row"     # edit SETS at the top of the script to include your file
python scripts/check_quality.py --update                      # accept the new numbers as the baseline
python scripts/check.py                                       # tests + guard + tables
```

Only after retrieval looks sensible, spend quota on a real run:

```
python scripts/run_eval.py --provider groq --tag mypaper_run1 --questions questions_mypaper --large openai/gpt-oss-20b
```

The run aborts itself if the daily budget is reached, so it cannot silently produce a run full of fallbacks.

## What does not generalise

* The default routing keywords assume each question names its paper or uses its vocabulary. Papers with generic titles
  need the classifier model to do more work.
* PDFs that are scanned images have no text layer; PyMuPDF returns nothing and the paper silently has zero chunks.
  `python -m relay.ingest` prints the chunk count per paper: a zero means this problem.
* Two-column layouts have not been tested. All three papers here are single column, so neither the plain-text reading order
  nor the table-row rebuild (which groups words by vertical position and would merge the two columns) has been checked on one.
