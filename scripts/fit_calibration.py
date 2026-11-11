"""Fit lognormal latency + decode rate from the real Groq probe logs -> data/calibration.json"""
import json, glob, numpy as np, pathlib
ROOT = pathlib.Path(__file__).resolve().parent.parent
f = sorted(glob.glob(str(ROOT / "logs/groq_probe_17*.jsonl")))[-1]
rows = [json.loads(l) for l in open(f)]
out = {"source": pathlib.Path(f).name, "models": {}}
for m in ("openai/gpt-oss-20b", "openai/gpt-oss-120b"):
    ok = [r for r in rows if r.get("model") == m and r.get("status") == 200 and r["tag"].startswith("latency")]
    ttft = np.log([r["ttft_ms"] for r in ok]); tail = np.array([r["total_ms"] - r["ttft_ms"] for r in ok])
    comp = np.array([r["usage"]["completion_tokens"] for r in ok])
    out["models"][m] = {"n": len(ok), "ttft_mu": float(ttft.mean()), "ttft_sigma": float(ttft.std(ddof=1)),
                        "ms_per_token": float(tail.sum() / max(1, comp.sum()))}
c8 = [r["ttft_ms"] for r in rows if r.get("tag") == "conc8" and r.get("status") == 200]
c4 = [r["ttft_ms"] for r in rows if r.get("tag") == "conc4" and r.get("status") == 200]
out["concurrency"] = {"conc4_median_ms": float(np.median(c4)), "conc8_median_ms": float(np.median(c8)),
                      "note": "20B only; slowdown per extra in-flight request fitted below"}
base = np.exp(out["models"]["openai/gpt-oss-20b"]["ttft_mu"])
out["concurrency"]["slowdown_per_inflight"] = float(max(0.0, (np.median(c8) / base - 1) / 7))
out["limits"] = {"rpm": 30, "tpm": 8000, "rpd": 1000, "retry_after_s": 2, "rpd_refill_s_per_req": 86.4}
(ROOT / "data" / "calibration.json").write_text(json.dumps(out, indent=2))
print(json.dumps(out, indent=2))
