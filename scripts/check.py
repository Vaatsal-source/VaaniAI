"""One command that answers "is the project still healthy?".

  python scripts/check.py               # unit tests + retrieval quality guard + tables match the logs   (about 30 s, no quota)
  python scripts/check.py --standin     # ... plus a 20-request burst on the stand-in (no quota)
  python scripts/check.py --real        # ... plus 5 real questions on the small model (about 11k tokens of Groq)
  python scripts/check.py --standin --real

Exit code 0 only if every step passed. Each step prints PASS/FAIL and the reason."""
import argparse, json, pathlib, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
PY = sys.executable
results = []


def step(name, fn):
    try:
        msg = fn()
        results.append((name, True, msg or ""))
        print(f"PASS  {name}  {msg or ''}", flush=True)
    except Exception as e:                                   # noqa: BLE001 - report every failure, keep going
        results.append((name, False, str(e)))
        print(f"FAIL  {name}  {e}", flush=True)


def run(*args, check=True, timeout=1500):
    p = subprocess.run([PY, *args], cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError((p.stdout + p.stderr).strip().splitlines()[-1][:300] if (p.stdout + p.stderr).strip() else "non-zero exit")
    return p.stdout


def tests():
    out = run("-m", "pytest", "-q")
    return [l for l in out.splitlines() if "passed" in l][-1]


def quality_guard():
    return run("scripts/check_quality.py").strip().splitlines()[-1]


def tables_match():
    files = [ROOT / "results" / "tables.md", ROOT / "README.md"]
    before = [f.read_bytes() if f.exists() else b"" for f in files]
    run("scripts/make_tables.py"); run("scripts/build_readme.py")
    changed = [f.name for f, b in zip(files, before) if f.read_bytes() != b]
    if changed:
        raise RuntimeError(f"{', '.join(changed)} did not match what logs/ and README.template.md produce (they have now been regenerated): "
                           "edit README.template.md, never README.md, and commit the result")
    return "tables and README are in sync with logs/"


def standin_burst():
    run("scripts/run_load.py", "--tag", "check_standin", "--shape", "burst", "--n", "20", "--window", "5", "--patience", "20", timeout=300)
    sys.path.insert(0, str(ROOT / "scripts"))
    import analyze
    t = analyze.table("check_standin")
    full, ext = int(t["answered/abstained (full model answer)"]), int(t["extractive (degraded)"])
    if int(t["errors"]) or int(t["abandoned (gave up)"]):
        raise RuntimeError(f"errors={t['errors']} abandoned={t['abandoned (gave up)']}")
    if full < 3:
        raise RuntimeError(f"only {full} full answers out of 20 (free-tier capacity is about 3-4)")
    return f"20 requests: {full} full answers, {ext} quoted-passages fallbacks, none lost"


def real_smoke(model):
    tag = "check_real"
    out = run("scripts/run_eval.py", "--provider", "groq", "--tag", tag, "--questions", "questions_smoke",
              "--large", model, check=False, timeout=900)
    if "ABORT" in out:
        raise RuntimeError("daily quota reached; try again later")
    res = json.load(open(ROOT / "logs" / f"eval_{tag}_results.json", encoding="utf-8"))
    wrong = [r["id"] for r in res if r["confident_wrong"]]
    score = sum(r["score"] for r in res)
    if wrong:
        raise RuntimeError(f"confidently wrong: {wrong}")
    if score < 4:
        raise RuntimeError(f"score {score}/5 (need 4)")
    return f"{score}/5 on real Groq, no confident-wrong answers"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--standin", action="store_true"); ap.add_argument("--real", action="store_true")
    ap.add_argument("--real-model", default="openai/gpt-oss-20b", help="drafting model for --real (the 20B and the 120B have separate daily quotas)")
    a = ap.parse_args()
    step("unit tests", tests)
    step("retrieval quality guard", quality_guard)
    step("tables match the logs", tables_match)
    if a.standin:
        step("stand-in burst", standin_burst)
    if a.real:
        step("real Groq smoke (5 questions)", lambda: real_smoke(a.real_model))
    bad = [n for n, ok, _ in results if not ok]
    print("\n" + ("ALL CHECKS PASSED" if not bad else f"{len(bad)} CHECK(S) FAILED: " + ", ".join(bad)))
    sys.exit(1 if bad else 0)
