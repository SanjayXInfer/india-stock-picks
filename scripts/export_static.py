"""Build the public static site into ./site (index.html, app.js, styles.css, data.json).

Only these four files are published. data.json comes from the allowlisted payload builder.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.aggregate import build_payload  # noqa: E402

PUBLIC_FILES = ["index.html", "app.js", "styles.css"]


def main() -> Path:
    out = config.SITE_DIR
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    for name in PUBLIC_FILES:
        shutil.copy2(config.WEB_DIR / name, out / name)
    (out / "data.json").write_text(json.dumps(build_payload(mode="static"), ensure_ascii=False, separators=(",", ":")),
                                   encoding="utf-8")
    (out / ".nojekyll").write_text("")  # GitHub Pages: serve files as-is
    print(f"Static site written to {out.relative_to(config.ROOT)}/ ({len(list(out.iterdir()))} files)")
    return out


if __name__ == "__main__":
    main()
