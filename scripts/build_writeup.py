"""Fill {{snip_name}} markers in WRITEUP.template.md with generated tables -> WRITEUP.md, and report its size.

  python scripts/build_writeup.py

The tables come from results/ (written by scripts/tables_from_csv.py and scripts/make_tables.py). The brief limits the writing to 2 pages;
the script prints the word count of the prose (everything outside the tables) so that can be checked: about 600 words per page."""
import pathlib, re

R = pathlib.Path(__file__).resolve().parent.parent
t = (R / "WRITEUP.template.md").read_text(encoding="utf-8")
t = re.sub(r"\{\{(snip_\w+|brief_\w+)\}\}", lambda m: (R / "results" / f"{m.group(1).replace('snip_', '')}.md").read_text(encoding="utf-8").strip(), t)
(R / "WRITEUP.md").write_text(t, encoding="utf-8")
prose = re.sub(r"^\|.*$", "", t.split("<!-- TABLES -->")[0], flags=re.M)
print("WRITEUP.md written:", len(t), "chars; prose before the tables:", len(prose.split()), "words (about", round(len(prose.split()) / 600, 1), "pages)")
