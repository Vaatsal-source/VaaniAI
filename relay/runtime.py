import copy
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
    return yaml.safe_load(open(path or ROOT / "config.yaml", encoding="utf-8"))


def deep_update(base: dict, upd: dict) -> dict:
    """Merge `upd` into `base` in place (nested dicts merged, everything else replaced)."""
    for k, v in upd.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_update(base[k], v)
        else:
            base[k] = v
    return base


def build(cfg, provider: str, log_path: str | None, retrieval: dict | None = None, limits: dict | None = None):
    cfg = copy.deepcopy(cfg)
    r = dict(cfg["retrieval"], **(retrieval or {}))
    lim = dict(cfg["limits"], **(limits or {}))
    refund = bool(cfg.get("tokens", {}).get("refund_on_success", False))
    log = EventLog(log_path)
    ingest = r.get("ingest", cfg.get("ingest", {}).get("version", "v1"))
    retr = Retriever(r["chunk_chars"], r["overlap_chars"], r["top_k"], r["mode"], ingest=ingest)
    cfg["retrieval"] = r

    def limiter(spec):
        L = Limiter(spec["rpm"], spec["tpm"], spec["rpd"], spec["daily_reserve_frac"], refund_on_success=refund)
        if spec.get("tpd"):
            L.tpd = spec["tpd"]
        return L

    limiters = {}
    for m in {cfg["models"]["small"], cfg["models"]["large"]}:       # limits are per model
        limiters[m] = limiter(lim)
    fb, fbc = None, cfg.get("fallback", {})
    if fbc.get("enabled"):
        fl = dict(lim, **fbc.get("limits", {}))
        for m in fbc["models"].values():
            limiters[m] = limiter(fl)
        fb = {"provider": fbc["provider"], "small": fbc["models"]["small"], "large": fbc["models"]["large"]}
    llm = LLMClient(cfg, provider, log, limiters, extra_providers=(fb["provider"],) if fb else ())
    return Pipeline(cfg, retr, llm, log, cfg["seed"], fallback=fb), log
