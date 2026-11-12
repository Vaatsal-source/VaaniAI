"""Show what a person sees when the daily token budget is gone, on the stand-in (no quota).

  python scripts/demo_daily_message.py     -> logs/server_r2_daily_msg.jsonl and logs/r2_daily_msg.json

The relay is told the daily budget (3,000 tokens). One answerable question uses it up; then a question the papers
clearly match gets the quoted-passages reply, and an off-topic question gets the honest decline with a wait time."""
import json, os, pathlib, subprocess, sys, time
import httpx

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = str(ROOT / ".venv" / "Scripts" / "python.exe") if (ROOT / ".venv").exists() else sys.executable
RELAY = 8113


def wait(url):
    for _ in range(240):
        try:
            if httpx.get(url, timeout=1).status_code < 500:
                return
        except Exception:
            time.sleep(0.25)
    raise RuntimeError(url)


def ask(q, req):
    text = []
    with httpx.stream("GET", f"http://127.0.0.1:{RELAY}/ask", params={"q": q, "req": req, "deadline": 17}, timeout=60) as r:
        status = None
        for line in r.iter_lines():
            if line.startswith("data:") and "status" in line and status is None:
                try:
                    status = json.loads(line[5:]).get("status")
                    continue
                except ValueError:
                    pass
            if line.startswith("data:"):
                try:
                    text.append(json.loads(line[5:]))
                except ValueError:
                    pass
    return status, "".join(x for x in text if isinstance(x, str)).strip()


procs = []
try:
    procs.append(subprocess.Popen([PY, "-m", "uvicorn", "standin.server:app", "--port", "8099", "--log-level", "warning"], cwd=ROOT, stdout=subprocess.DEVNULL))
    wait("http://127.0.0.1:8099/v1/models")
    httpx.post("http://127.0.0.1:8099/admin/config", json={"set": {"p_fail": 0, "p_stall": 0, "p_slow": 0, "tpd": 3000}, "reset": True})
    log = ROOT / "logs" / "server_r2_daily_msg.jsonl"
    log.write_text("")
    env = dict(os.environ, RELAY_PROVIDER="standin", RELAY_LOG=str(log), RELAY_CACHE="0",
               RELAY_LIMITS=json.dumps({"rpm": 300, "tpm": 80000, "rpd": 10000, "tpd": 3000}))
    procs.append(subprocess.Popen([PY, "-m", "uvicorn", "relay.server:app", "--port", str(RELAY), "--log-level", "warning"], cwd=ROOT, env=env, stdout=subprocess.DEVNULL))
    wait(f"http://127.0.0.1:{RELAY}/health")
    out = []
    for i, (label, q) in enumerate([("uses up the budget", "How many attention heads does the base Transformer use?"),
                                     ("budget gone, passages match", "What BLEU score did the big Transformer reach on WMT 2014 English-to-German translation?"),
                                     ("budget gone, nothing matches", "Who won the football world cup in 2022?")]):
        status, text = ask(q, f"daily-{i}")
        out.append({"case": label, "question": q, "status": status, "reply": text})
        print(f"[{label}] status={status}\n{text}\n", flush=True)
    (ROOT / "logs" / "r2_daily_msg.json").write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
finally:
    for p in procs:
        p.terminate()
