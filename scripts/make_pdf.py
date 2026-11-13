"""Render WRITEUP.md to WRITEUP.pdf with headless Edge/Chrome, then report the page count and words.

  python scripts/make_pdf.py [--font 9.5] [--margin 12]     (margin in mm)

Needs the `markdown` package (pip install markdown), PyMuPDF and Edge or Chrome.
It checks that every heading of the write-up made it into the PDF. Not part of CI."""
import argparse, pathlib, re, subprocess, sys, tempfile
import fitz, markdown

ROOT = pathlib.Path(__file__).resolve().parent.parent
ap = argparse.ArgumentParser()
ap.add_argument("--font", type=float, default=9.5)
ap.add_argument("--margin", type=float, default=12)
a = ap.parse_args()

src = (ROOT / "WRITEUP.md").read_text(encoding="utf-8")
# python-markdown needs a blank line before a list that follows a paragraph line
lines, prev_list = [], False
for ln in src.split("\n"):
    is_list = bool(re.match(r"\s*([-*]|\d+\.)\s", ln))
    if is_list and lines and lines[-1].strip() and not prev_list and not lines[-1].lstrip().startswith("|"):
        lines.append("")
    lines.append(ln); prev_list = is_list
src_fixed = "\n".join(lines)
body = markdown.markdown(src_fixed, extensions=["tables"])
css = f"""
@page {{ size: A4; margin: {a.margin}mm; }}
body {{ font-family: Arial, sans-serif; font-size: {a.font}pt; line-height: 1.13; margin: 0; }}
h1 {{ font-size: {a.font + 6}pt; margin: 0 0 3pt 0; }}
h2 {{ break-after: avoid; font-size: {a.font + 2}pt; margin: 6pt 0 2pt 0; }}
p {{ margin: 0 0 3pt 0; }}  ul, ol {{ margin: 0 0 3pt 0; padding-left: 16pt; }}  li {{ margin: 0; }}
code {{ font-family: Consolas, monospace; font-size: {a.font - 1}pt; }}
table {{ border-collapse: collapse; margin: 2pt 0 4pt 0; width: 100%; }}
th, td {{ font-size: {a.font - 2.5}pt; border: 0.4pt solid #888; padding: 1pt 2pt; text-align: left; vertical-align: top; }}
th {{ background: #eee; }}
"""
html = f"<!doctype html><meta charset='utf-8'><style>{css}</style>{body}"
tmp = pathlib.Path(tempfile.mkdtemp()) / "w.html"
tmp.write_text(html, encoding="utf-8")
out = ROOT / "WRITEUP.pdf"
browser = next((p for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
                            r"C:\Program Files\Google\Chrome\Application\chrome.exe") if pathlib.Path(p).exists()), None)
if not browser:
    sys.exit("no Edge or Chrome found")
subprocess.run([browser, "--headless", "--disable-gpu", "--no-pdf-header-footer", f"--print-to-pdf={out}", tmp.as_uri()],
               check=True, capture_output=True, timeout=120)

doc = fitz.open(str(out))
text = " ".join(" ".join(p.get_text().split()) for p in doc)
heads = re.findall(r"^#{1,2} (.+)$", src, flags=re.M)
missing = [h for h in heads if " ".join(h.split()) not in text]
words = len(re.findall(r"\S+", re.sub(r"^\|.*$", "", src, flags=re.M)))
print(f"WRITEUP.pdf: {doc.page_count} pages (font {a.font} pt, margin {a.margin} mm); {words} words outside tables")
print("all headings present" if not missing else f"MISSING headings: {missing}")
