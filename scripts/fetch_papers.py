"""Download the three exact arXiv versions and record SHA-256 of each."""
import hashlib, json, pathlib, sys, urllib.request

PAPERS = {
    "attention": "1706.03762v7",
    "moshi": "2410.00037v1",
    "dynchunk": "2507.07955v2",
}
OUT = pathlib.Path(__file__).resolve().parent.parent / "papers"


def main():
    OUT.mkdir(exist_ok=True)
    manifest = {}
    for key, ver in PAPERS.items():
        dest = OUT / f"{ver}.pdf"
        if not dest.exists():
            req = urllib.request.Request(
                f"https://arxiv.org/pdf/{ver}", headers={"User-Agent": "relay-fetch/1.0"}
            )
            with urllib.request.urlopen(req, timeout=120) as r:
                dest.write_bytes(r.read())
        data = dest.read_bytes()
        if not data.startswith(b"%PDF"):
            sys.exit(f"{ver}: not a PDF")
        manifest[key] = {"arxiv": ver, "file": dest.name, "bytes": len(data),
                         "sha256": hashlib.sha256(data).hexdigest()}
        print(key, manifest[key])
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
