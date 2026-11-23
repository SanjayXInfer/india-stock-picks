"""Fail (exit 1) if the files about to be published contain anything that looks sensitive.

Run automatically before every deploy. Checks: only expected files exist; no API keys / tokens;
no values of secret environment variables; no local filesystem paths or e-mail addresses.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "site"
ALLOWED = {"index.html", "app.js", "styles.css", "data.json", ".nojekyll"}

PATTERNS = {
    "Anthropic key": re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    "generic secret": re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[\"':=]\s*[\"']?[A-Za-z0-9_\-]{16,}"),
    "GitHub token": re.compile(r"gh[pousr]_[A-Za-z0-9]{30,}"),
    "AWS key": re.compile(r"AKIA[0-9A-Z]{16}"),
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "Windows path": re.compile(r"[A-Za-z]:\\\\?(Users|Documents and Settings)\\\\?", re.I),
    "home path": re.compile(r"/(home|Users)/[A-Za-z0-9._-]+/"),
    "e-mail address": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
}
SECRET_ENV = re.compile(r"(KEY|TOKEN|SECRET|PASSWORD)", re.I)


def main() -> int:
    problems = []
    if not SITE.is_dir():
        print(f"{SITE} does not exist; run the export first")
        return 1
    files = [p for p in SITE.rglob("*") if p.is_file()]
    for p in files:
        if p.relative_to(SITE).as_posix() not in ALLOWED:
            problems.append(f"unexpected file: {p.relative_to(SITE)}")
    secret_values = [v for k, v in os.environ.items() if SECRET_ENV.search(k) and len(v) >= 8]
    for p in files:
        text = p.read_text(encoding="utf-8", errors="replace")
        for label, rx in PATTERNS.items():
            if m := rx.search(text):
                problems.append(f"{p.name}: possible {label}: {m.group(0)[:12]}...")
        for v in secret_values:
            if v in text:
                problems.append(f"{p.name}: contains the value of a secret environment variable")
    if problems:
        print("PUBLIC SAFETY CHECK FAILED:\n  " + "\n  ".join(problems))
        return 1
    print(f"Public safety check passed ({len(files)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
