"""Orchestrate one load experiment: [stand-in] + relay server + separate loadgen process.
  python scripts/run_load.py --tag steady_free --shape steady --rate 0.035 --duration 300
  python scripts/run_load.py --provider groq --tag real_steady --shape steady --rate 0.03 --duration 240
Flags: --tier N multiplies rpm/tpm/rpd (stand-in AND relay limiter) to model a higher plan;
       --rpd overrides the daily budget (daily-limit-exhaustion experiment);
       --mode retrieval mode (bm25 default).
Raw outputs: logs/load_<tag>.jsonl (client), logs/server_<tag>.jsonl (pipeline), logs/standin_<tag>.json (config)."""
import argparse, json, os, pathlib, subprocess, sys, time
PRIO = getattr(subprocess, "HIGH_PRIORITY_CLASS", 0)    # Windows: keep the measured processes ahead of the laptop's background apps (see README appendix)
import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable          # whichever Python (the venv's) launched this script


def wait(url, t=60):
    for _ in range(int(t * 4)):
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(f"server not up: {url}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True); ap.add_argument("--provider", default="standin")
    ap.add_argument("--shape", required=True); ap.add_argument("--tier", type=float, default=1.0)
    ap.add_argument("--rpd", type=int, default=None); ap.add_argument("--mode", default="bm25")
    ap.add_argument("--p_fail", type=float, default=None)
    ap.add_argument("--tpd", type=int, default=None, help="daily token budget (stand-in)")
    ap.add_argument("--tpd_unknown", action="store_true", help="relay limiter does not know the TPD; must learn it from a 429 body")
    ap.add_argument("--large", default=None, help="override the drafting model")
    ap.add_argument("--cfg", default="{}", help="JSON deep-merged into config.yaml for the relay server, e.g. '{\"pipeline_policy\": {\"shed_frac\": 0.3}}'")
    ap.add_argument("--relay_port", type=int, default=8110, help="port for the relay server under test")
    ap.add_argument("--cache", action="store_true", help="enable the answer cache (pinned off by default so experiments stay comparable)")
    ap.add_argument("--charge_max_tokens", action="store_true", help="stand-in charges prompt+max_tokens (the round-1 assumption) instead of real usage")
    ap.add_argument("--retries", default="", help="overrides for config retries as k=v,k=v e.g. max_attempts=1,retry_budget_frac=10")
    a, rest = ap.parse_known_args()
    procs = []
    try:
        base_l = {"rpm": 27 * a.tier, "tpm": 7200 * a.tier, "rpd": a.rpd or int(1000 * a.tier),
                  "tpd": 0 if a.tpd_unknown else (a.tpd or int(200000 * a.tier))}
        if a.provider == "standin":
            procs.append(subprocess.Popen([PY, "-m", "uvicorn", "standin.server:app", "--port", "8099", "--log-level", "warning"],
                                          cwd=ROOT, stdout=subprocess.DEVNULL, creationflags=PRIO))
            wait("http://127.0.0.1:8099/v1/models")
            s = {"rpm": int(30 * a.tier), "tpm": int(8000 * a.tier), "rpd": a.rpd or int(1000 * a.tier),
                 "tpd": a.tpd or int(200000 * a.tier)}
            if a.p_fail is not None: s["p_fail"] = a.p_fail
            if a.charge_max_tokens: s["charge_max_tokens"] = True
            conf = httpx.post("http://127.0.0.1:8099/admin/config", json={"set": s, "reset": True}).json()
            (ROOT / "logs" / f"standin_{a.tag}.json").write_text(json.dumps(conf, indent=1))
        env = dict(os.environ, RELAY_PROVIDER=a.provider, RELAY_LOG=str(ROOT / "logs" / f"server_{a.tag}.jsonl"),
                   RELAY_LIMITS=json.dumps(base_l) if a.provider == "standin" else json.dumps({"rpd": a.rpd} if a.rpd else {}),
                   RELAY_RETRIEVAL=json.dumps({"mode": a.mode}), RELAY_CFG=a.cfg, RELAY_CACHE="1" if a.cache else "0", RELAY_LARGE=a.large or "", RELAY_RETRIES=json.dumps({k: float(v) for k, v in (kv.split("=") for kv in a.retries.split(",") if kv)}))
        (ROOT / "logs" / f"server_{a.tag}.jsonl").write_text("")
        procs.append(subprocess.Popen([PY, "-m", "uvicorn", "relay.server:app", "--port", str(a.relay_port), "--log-level", "warning"],
                                      cwd=ROOT, env=env, stdout=subprocess.DEVNULL, creationflags=PRIO))
        wait(f"http://127.0.0.1:{a.relay_port}/health", 120)
        subprocess.run([PY, str(ROOT / "loadgen" / "loadgen.py"), "--shape", a.shape, "--tag", a.tag, "--base", f"http://127.0.0.1:{a.relay_port}"] + rest, check=True, creationflags=PRIO)
        time.sleep(1)
    finally:
        for p in procs:
            p.terminate()


if __name__ == "__main__":
    main()
