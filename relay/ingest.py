"""PDF -> page-tagged text -> overlapping chunks with (paper, pages, section) metadata.

A citation is "[C:<chunk id>]"; each chunk carries the page(s) and section it came from, so the
deterministic checker can verify it and the UI can render "paper vN, sec, p.X".

Two chunker versions are kept side by side so the original results stay reproducible:
  v1  the original chunker (data/chunks_<size>_<overlap>.json)
  v2  fixes the reference filter (it deleted the start of Appendix A) and adds extra "table row" chunks
      rebuilt from word positions, because PyMuPDF's normal text order separates a table's row labels from
      its numbers (data/chunks_v2_<size>_<overlap>.json). v2 never changes the ids of the v1 chunks, so a
      citation id means the same thing in both; table chunks are extra ids of the form "<paper>:t<j>".
"""
import json
import pathlib
import re

import fitz

from .papers import PAPERS

ROOT = pathlib.Path(__file__).resolve().parent.parent
# PyMuPDF emits "3.1\nEncoder and Decoder Stacks\n" for numbered headings.
# v1 (original) also accepted table rows such as "2.95\nPerplexity on HG38" and page numbers such as "24\nReferences".
HEAD = re.compile(r"^((?:[1-9]|1\d|2[0-5])(?:\.\d{1,2}){0,2}|[A-D](?:\.\d{1,2}){0,2})\s*\n([A-Z][A-Za-z][^\n]{2,80})\n", re.M)
# v2: single-digit section numbers only, so decimals and page numbers are not headings; plus the unnumbered
# "References" heading, which v1 only found by accident when a page number sat in front of it.
HEAD2 = re.compile(r"^(?:((?:[1-9])(?:\.\d){0,2}|[A-D](?:\.\d){0,2})\s*\n([A-Z][A-Za-z][^\n]{2,80})|(References|Bibliography))\s*\n", re.M)
REFLIKE = re.compile(r"\[\d{1,3}\]|arXiv|et al\.|Proceedings|\b(?:19|20)\d\d\)?\.")
NUMTOK = re.compile(r"^[-+±~]?\d[\d.,%×·KMBkmb]*$")
TABLE_CAP = re.compile(r"^Table\s+\d+[:.]")
MAX_TABLE_CHARS = 2400


def load_pages(key: str):
    doc = fitz.open(ROOT / "papers" / f"{PAPERS[key]}.pdf")
    return [(i + 1, p.get_text("text")) for i, p in enumerate(doc)]


def clean(t: str) -> str:
    t = t.replace("­", "").replace("-\n", "")
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n{2,}", "\n\n", t)


# ---------------------------------------------------------------- tables (v2)
def _lines(page, ytol=3.0):
    """Words on the same visual line (same y within ytol points), left to right."""
    ws = sorted(page.get_text("words"), key=lambda w: ((w[1] + w[3]) / 2, w[0]))
    lines, cur, cy = [], [], None
    for w in ws:
        y = (w[1] + w[3]) / 2
        if cy is None or abs(y - cy) <= ytol:
            cur.append(w)
            cy = y if cy is None else (cy + y) / 2
        else:
            lines.append(cur)
            cur, cy = [w], y
    if cur:
        lines.append(cur)
    out = []
    for ln in lines:
        ln.sort(key=lambda w: w[0])
        gaps = [ln[i + 1][0] - ln[i][2] for i in range(len(ln) - 1)]
        toks = [w[4] for w in ln]
        out.append({"y": ln[0][1], "text": " ".join(toks), "gap": max(gaps) if gaps else 0.0,
                    "n": len(toks), "nums": sum(bool(NUMTOK.match(t)) for t in toks)})
    return out


def table_blocks(page, min_gap=14.0):
    """Rebuild table rows from word positions. A table row is a visual line with a wide horizontal gap between
    its cells. Consecutive such lines form a table if they carry enough numbers (this rejects figure labels and
    word-by-word attention plots). Returns [{"caption": str, "rows": [str]}]."""
    lines = _lines(page)
    tab = [ln["gap"] >= min_gap and ln["n"] >= 3 for ln in lines]
    blocks, i = [], 0
    while i < len(lines):
        if not tab[i]:
            i += 1
            continue
        j = i
        def glue(k):     # a short label between table rows, e.g. "(A)" or the sub-heading "Depth Transformer"
            return (k + 1 < len(lines) and tab[k + 1] and lines[k]["n"] <= 4 and len(lines[k]["text"]) <= 40
                    and lines[k + 1]["y"] - lines[k]["y"] <= 25)
        while j + 1 < len(lines) and (tab[j + 1] or glue(j + 1)):
            j += 1
        rows = lines[i:j + 1]
        trows = [r for r in rows if r["gap"] >= min_gap and r["n"] >= 3]
        with_nums = sum(r["nums"] >= 1 for r in trows)
        if len(trows) >= 3 and with_nums >= 0.6 * len(trows) and sum(r["nums"] for r in trows) >= 8:
            cap = ""
            for k in range(i - 1, max(-1, i - 14), -1):          # caption above the table
                if TABLE_CAP.match(lines[k]["text"]):
                    cap = " ".join(l["text"] for l in lines[k:i] if l["gap"] < min_gap)
                    break
            if not cap and j + 1 < len(lines) and TABLE_CAP.match(lines[j + 1]["text"]):   # caption below
                cap = " ".join(l["text"] for l in lines[j + 1:j + 4] if l["gap"] < min_gap)
            blocks.append({"caption": cap[:400], "rows": [r["text"] for r in rows]})
        i = j + 1
    return blocks


def _table_chunks(key, start_idx):
    out, j = [], start_idx
    for pno, _ in load_pages(key):
        page = fitz.open(ROOT / "papers" / f"{PAPERS[key]}.pdf")[pno - 1]
        for blk in table_blocks(page):
            head = "Table rows reassembled from the page layout (columns left to right). " + blk["caption"]
            piece, size = [], len(head)
            for r in blk["rows"] + [None]:
                if r is None or size + len(r) + 1 > MAX_TABLE_CHARS:
                    if piece:
                        out.append({"id": f"{key}:t{j}", "paper": key, "version": PAPERS[key], "pages": [pno],
                                    "section": f"Table rows (p.{pno})", "is_ref": False, "kind": "table",
                                    "text": head + "\n" + "\n".join(piece)})
                        j += 1
                    piece, size = [], len(head)
                if r is not None:
                    piece.append(r)
                    size += len(r) + 1
    return out


# ---------------------------------------------------------------- chunks
def build_chunks(chunk_chars=1200, overlap=200, version="v1"):
    chunks = []
    v2 = version == "v2"
    head_rx = HEAD2 if v2 else HEAD
    for key in PAPERS:
        full, bounds = "", []
        for pno, raw in load_pages(key):
            raw = clean(raw)
            bounds.append((len(full), len(full) + len(raw) + 1, pno))
            full += raw + "\n"
        heads = []
        for m in head_rx.finditer(full):
            if v2 and m.group(3):
                heads.append((m.start(), m.group(3), True))
            elif v2:
                heads.append((m.start(), f"{m.group(1)} {m.group(2).strip()}", False))
            else:
                heads.append((m.start(), f"{m.group(1)} {m.group(2).strip()}", False))
        ref_span = None
        if v2:      # the real reference list: from the "References" heading to the next numbered/lettered heading
            starts = [p for p, _, is_ref in heads if is_ref and p > 0.3 * len(full)]
            if starts:
                end = next((p for p, _, is_ref in heads if not is_ref and p > starts[0]), len(full))
                ref_span = (starts[0], end)
        step = chunk_chars - overlap
        n = 0
        for start in range(0, len(full), step):
            seg = full[start:start + chunk_chars].strip()
            if len(seg) < 80:
                continue
            end = start + chunk_chars
            pages = sorted({p for a, b, p in bounds if a < end and b > start})
            sec = next((h for pos, h, _ in reversed(heads) if pos <= start + chunk_chars // 2), "front matter")
            if v2:
                inside = 0.0
                if ref_span:
                    inside = max(0, min(end, ref_span[1]) - max(start, ref_span[0])) / max(1, min(chunk_chars, len(full) - start))
                is_ref = inside >= 0.8 and len(REFLIKE.findall(seg)) >= 4
            else:
                is_ref = "References" in sec
            chunks.append({"id": f"{key}:{n}", "paper": key, "version": PAPERS[key],
                           "pages": pages, "section": sec, "is_ref": is_ref, "text": seg})
            n += 1
        if v2:
            chunks += _table_chunks(key, 0)
    return chunks


def chunk_path(chunk_chars, overlap, version="v1"):
    name = f"chunks_{chunk_chars}_{overlap}.json" if version == "v1" else f"chunks_{version}_{chunk_chars}_{overlap}.json"
    return ROOT / "data" / name


def load_chunks(chunk_chars=1200, overlap=200, version="v1"):
    path = chunk_path(chunk_chars, overlap, version)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    ch = build_chunks(chunk_chars, overlap, version)
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(ch), encoding="utf-8")
    return ch


if __name__ == "__main__":
    import collections
    for version in ("v1", "v2"):
        for size, ov in ((600, 100), (1200, 200), (2400, 300)):
            ch = load_chunks(size, ov, version)
            print(version, size, len(ch), "chunks", dict(collections.Counter(c["paper"] for c in ch)),
                  "refs", sum(c["is_ref"] for c in ch), "tables", sum(c.get("kind") == "table" for c in ch))
