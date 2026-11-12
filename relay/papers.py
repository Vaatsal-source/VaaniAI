"""The paper list lives in config.yaml (key -> arXiv id, routing keywords, short description)."""
import pathlib

import yaml

ROOT = pathlib.Path(__file__).resolve().parent.parent
_P = yaml.safe_load(open(ROOT / "config.yaml", encoding="utf-8"))["papers"]
PAPERS = {k: v["arxiv"] for k, v in _P.items()}          # key -> versioned arXiv id (also the pdf name)
PAPER_KW = {k: v["keywords"] for k, v in _P.items()}      # key -> regex that routes a question to it
PAPER_DESC = {k: v["desc"] for k, v in _P.items()}
