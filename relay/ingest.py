"""PDF -> page-tagged text -> overlapping chunks with (paper, pages, section) metadata.

A citation is "[C:<chunk id>]"; each chunk carries the page(s) and section it came from, so the
deterministic checker can verify it and the UI can render "paper vN, §sec, p.X".
"""
import json
import pathlib
import re

import fitz

ROOT = pathlib.Path(__file__).resolve().parent.parent
PAPERS = {"attention": "1706.03762v7", "moshi": "2410.00037v1", "dynchunk": "2507.07955v2"}
# PyMuPDF emits "3.1\nEncoder and Decoder Stacks\n" for numbered headings.
HEAD = re.compile(r"^((?:[1-9]|1\d|2[0-5])(?:\.\d{1,2}){0,2}|[A-D](?:\.\d{1,2}){0,2})\s*\n([A-Z][A-Za-z][^\n]{2,80})\n", re.M)


def load_pages(key: str):
    doc = fitz.open(ROOT / "papers" / f"{PAPERS[key]}.pdf")
    return [(i + 1, p.get_text("text")) for i, p in enumerate(doc)]


def clean(t: str) -> str:
    t = t.replace("­", "").replace("-\n", "")
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{2,}", "\n\n", t)


def build_chunks(chunk_chars=1200, overlap=200):
    chunks = []
    for key in PAPERS:
        full, bounds = "", []
        for pno, raw in load_pages(key):
            raw = clean(raw)
            bounds.append((len(full), len(full) + len(raw) + 1, pno))
            full += raw + "\n"
        heads = [(m.start(), f"{m.group(1)} {m.group(2).strip()}") for m in HEAD.finditer(full)]
        step = chunk_chars - overlap
        n = 0
        for start in range(0, len(full), step):
            seg = full[start:start + chunk_chars].strip()
            if len(seg) < 80:
                continue
            end = start + chunk_chars
            pages = sorted({p for a, b, p in bounds if a < end and b > start})
            sec = next((h for pos, h in reversed(heads) if pos <= start + chunk_chars // 2), "front matter")
            chunks.append({"id": f"{key}:{n}", "paper": key, "version": PAPERS[key],
                           "pages": pages, "section": sec, "is_ref": "References" in sec, "text": seg})
            n += 1
    return chunks


def load_chunks(chunk_chars=1200, overlap=200):
    path = ROOT / "data" / f"chunks_{chunk_chars}_{overlap}.json"
    if path.exists():
        return json.loads(path.read_text())
    ch = build_chunks(chunk_chars, overlap)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(ch))
    return ch


if __name__ == "__main__":
    import collections
    for size, ov in ((600, 100), (1200, 200), (2400, 300)):
        ch = load_chunks(size, ov)
        print(size, len(ch), "chunks", dict(collections.Counter(c["paper"] for c in ch)))
    ch = load_chunks(1200, 200)
    print(collections.Counter(c["section"] for c in ch if c["paper"] == "attention").most_common(10))
    print(collections.Counter(c["section"] for c in ch if c["paper"] == "dynchunk").most_common(6))
