import pathlib

import yaml
from dotenv import load_dotenv

from .events import EventLog
from .limiter import Limiter
from .llm import LLMClient
from .pipeline import Pipeline
from .retrieval import Retriever

ROOT = pathlib.Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")


def load_cfg(path=None):
    return yaml.safe_load(open(path or ROOT / "config.yaml"))


def build(cfg, provider: str, log_path: str | None, retrieval: dict | None = None, limits: dict | None = None):
    r = dict(cfg["retrieval"], **(retrieval or {}))
    lim = dict(cfg["limits"], **(limits or {}))
    log = EventLog(log_path)
    retr = Retriever(r["chunk_chars"], r["overlap_chars"], r["top_k"], r["mode"])
    limiters = {}
    for m in {cfg["models"]["small"], cfg["models"]["large"]}:   # Groq limits are per model
        L = Limiter(lim["rpm"], lim["tpm"], lim["rpd"], lim["daily_reserve_frac"])
        if lim.get("tpd"):
            L.tpd = lim["tpd"]
        limiters[m] = L
    llm = LLMClient(cfg, provider, log, limiters)
    return Pipeline(cfg, retr, llm, log, cfg["seed"]), log
