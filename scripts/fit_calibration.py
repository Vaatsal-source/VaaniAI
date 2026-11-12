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

# ---------------- round 2: re-fit the concurrency slowdown from 4/8/12/16-way tests, record failure bounds ----------------
# python scripts/fit_calibration.py --round2 [--apply]
import sys
if "--round2" in sys.argv:
    import collections
    cal = json.load(open(ROOT / "data" / "calibration.json"))
    files = sorted(glob.glob(str(ROOT / "logs/groq_probe2_concurrency_*.jsonl")))
    f = files[-1]                                           # the last file is the one produced on an idle machine
    rows = [json.loads(l) for l in open(f)]
    by = collections.defaultdict(list)
    for r in rows:
        if r.get("status") == 200 and r.get("ttft_ms"):
            by[int(r["tag"][4:])].append(r["ttft_ms"])
    q = [json.loads(l) for l in open(sorted(glob.glob(str(ROOT / "logs/groq_probe2_quiet_*.jsonl")))[-1])]
    base = float(np.median([r["ttft_ms"] for r in q if r.get("model") == "openai/gpt-oss-20b" and r.get("ttft_ms")]))
    ks = sorted(by)
    ratio = {k: float(np.median(by[k])) / base for k in ks}
    num = sum((k - 1) * (ratio[k] - 1) for k in ks); den = sum((k - 1) ** 2 for k in ks)
    slope = max(0.0, num / den)
    n_req = sum(1 for r in q if "status" in r) + sum(1 for r in rows if "status" in r)
    cal["round2"] = {"concurrency_file": pathlib.Path(f).name, "baseline_20B_median_ttft_ms_quiet": base,
                     "median_ttft_ms_by_in_flight": {k: float(np.median(by[k])) for k in ks},
                     "slowdown_per_inflight_refit": slope, "slowdown_per_inflight_round1": cal["concurrency"]["slowdown_per_inflight"],
                     "groq_requests_without_a_5xx_in_these_two_probes": n_req,
                     "note": "Groq returned no 5xx in any real request in logs/ (see README appendix A); p_fail in the stand-in is a deliberately pessimistic assumption, not a measurement."}
    if "--apply" in sys.argv:
        cal["concurrency"]["slowdown_per_inflight"] = slope
    (ROOT / "data" / "calibration.json").write_text(json.dumps(cal, indent=2))
    print(json.dumps(cal["round2"], indent=2))
