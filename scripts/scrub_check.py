#!/usr/bin/env python3
"""Fail if anything private is in the repo: tracked files, packed PNG payloads, and commit messages.

usage: python3 scripts/scrub_check.py [root]
Scans every file git tracks (plus untracked, not ignored files), decodes PNGs packed by
voiced-deck and scans their payload, scans the metadata of audio embedded as data: URIs,
then scans commit messages. Exits 1 on any hit.
"""
import base64
import os
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else pathlib.Path(__file__).resolve().parents[1]).resolve()
SELF = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(ROOT / "plugins" / "voiced-deck" / "tools"))

RULES = [
    ("absolute home path", r"/Users/[A-Za-z0-9._-]+|/home/[a-z][A-Za-z0-9._-]+/|[A-Z]:\\Users\\"),
    ("podkst live or test key", r"pk_(live|test)_[A-Za-z0-9]{4,}"),
    ("secret key", r"\bsk[-_](live_|test_|proj-|ant-)?[A-Za-z0-9]{16,}"),
    ("Studio project id", r"\bprj_[A-Za-z0-9]{6,}"),
    ("Studio job id", r"\b(s?job|rnd)_[A-Za-z0-9]{6,}"),
    ("take or segment id", r"\b(tk|seg)_[A-Za-z0-9_-]{8,}"),
    ("email address", r"[A-Za-z0-9._%+-]+@(?!example\.(com|org)\b)[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("BRL amount", r"R\$\s?\d"),
    ("Brazilian payment or tax id term", r"\b(Pix|CPF|CNPJ|NFS-e)\b"),
]
# Project-specific phrases stay out of the public repo: one case-insensitive regex per line in
# $SCRUB_PRIVATE_FILE or ~/.config/agent-tools/scrub-private.txt (lines starting with # are comments).
PRIVATE = pathlib.Path(os.environ.get("SCRUB_PRIVATE_FILE", pathlib.Path.home() / ".config" / "agent-tools" / "scrub-private.txt"))
if PRIVATE.is_file():
    for line in PRIVATE.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            RULES.append(("private phrase", "(?i)" + line.strip()))
RX = [(name, re.compile(rx)) for name, rx in RULES]
DATA_AUDIO = re.compile(r"data:audio/[a-z0-9.+-]+;base64,([A-Za-z0-9+/=]+)")
TEXT_EXT = {".md", ".py", ".js", ".json", ".html", ".txt", ".yml", ".yaml", ".toml", ".cfg", ".sh", ".tsv", ".csv", ""}


def files():
    out = subprocess.run(["git", "ls-files", "-co", "--exclude-standard"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode:
        return [p for p in ROOT.rglob("*") if p.is_file() and ".git" not in p.parts]
    return [ROOT / f for f in out.stdout.splitlines() if (ROOT / f).is_file()]


def scan(label, text, hits):
    for name, rx in RX:
        for m in rx.finditer(text):
            line = text.count("\n", 0, m.start()) + 1
            hits.append(f"{label}:{line}: {name}: {m.group(0)[:40]!r}")


def main():
    hits, n = [], 0
    try:
        from vdeck import pngpack
    except ImportError:
        pngpack = None
    for p in files():
        if p.resolve() == SELF:
            continue
        rel = p.relative_to(ROOT)
        data = p.read_bytes()
        if p.suffix.lower() in TEXT_EXT or p.name in ("LICENSE", "voiced-deck"):
            text = data.decode("utf-8", "replace")
            for m in DATA_AUDIO.finditer(text):
                head = base64.b64decode(m.group(1)[:5464] + "=" * (-len(m.group(1)[:5464]) % 4))
                scan(str(rel) + " [embedded audio metadata]", head[:4096].decode("latin-1"), hits)
            scan(str(rel), DATA_AUDIO.sub("data:audio", text), hits)
            n += 1
        elif p.suffix.lower() == ".png" and pngpack:
            try:
                payload = pngpack.unpack(data)
            except Exception:
                continue
            if payload[:4] == b"\x00\x00\x00\x00" or b"ftyp" in payload[:12]:
                scan(str(rel) + " [packed audio metadata]", payload[:4096].decode("latin-1"), hits)
            else:
                scan(str(rel) + " [packed]", payload.decode("utf-8", "replace"), hits)
            n += 1
        elif p.suffix.lower() in (".m4a", ".mp4", ".wav"):
            scan(str(rel) + " [audio metadata]", data[:4096].decode("latin-1"), hits)
            n += 1
    log = subprocess.run(["git", "log", "--all", "--format=%H%n%B"], cwd=ROOT, capture_output=True, text=True)
    if log.returncode == 0:
        msgs = re.sub(r"(?im)^co-authored-by: .*$", "", log.stdout)
        scan("git log", msgs, hits)
    for h in hits:
        print("FAIL", h)
    print(f"scrub check: {n} files and the commit log scanned, {len(hits)} hits")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
