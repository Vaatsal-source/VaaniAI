"""Redact the Groq organization id from the committed session transcript and check it for keys.

  python scripts/redact_transcript.py [docs/claude-session.jsonl]

Run it again every time you re-copy the transcript. It changes nothing except
replacing the organization id with [REDACTED-GROQ-ORG-ID], keeps every line valid
JSON, and exits non-zero if anything key-shaped (or the exact values in your
.env) is still present. It never prints a secret."""
import json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
path = pathlib.Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "docs" / "claude-session.jsonl"
ORG = re.compile(r"org_[0-9a-z]{10,}")
KEYS = re.compile(r"gsk_[A-Za-z0-9]{20,}|AIza[0-9A-Za-z_-]{30,}")

text = path.read_text(encoding="utf-8")
new, n_org = ORG.subn("[REDACTED-GROQ-ORG-ID]", text)

env_values = []
env = ROOT / ".env"
if env.exists():
    for line in env.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.strip().startswith("#"):
            v = line.split("=", 1)[1].strip().strip("'\"")
            if len(v) >= 12:
                env_values.append(v)

bad = len(KEYS.findall(new)) + sum(new.count(v) for v in env_values)
for i, line in enumerate(new.splitlines(), 1):
    if line.strip():
        json.loads(line)  # raises if a replacement broke a line

path.write_text(new, encoding="utf-8")
print(f"{path.name}: replaced {n_org} organization-id occurrence(s); key-shaped strings left: {bad}")
sys.exit(1 if bad else 0)
