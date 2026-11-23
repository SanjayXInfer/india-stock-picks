"""One-command launcher (cross-platform; `make` is optional).

    python dev.py              start server + scheduler on http://127.0.0.1:8000 (seeds first if DB is empty)
    python dev.py seed [src..] run one scrape now
    python dev.py export       build the public static site in ./site and run the safety check
    python dev.py publish      export + safety check + push ONLY ./site to the gh-pages branch
    python dev.py test         run unit tests
"""
from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV_PY = ROOT / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def _reexec_in_venv() -> None:
    if VENV_PY.exists() and Path(sys.executable).resolve() != VENV_PY.resolve():
        sys.exit(subprocess.call([str(VENV_PY), __file__, *sys.argv[1:]]))


def main() -> int:
    _reexec_in_venv()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "dev"
    py = sys.executable
    if cmd == "seed":
        return subprocess.call([py, "scripts/seed.py", *sys.argv[2:]], cwd=ROOT)
    if cmd == "export":
        rc = subprocess.call([py, "scripts/export_static.py"], cwd=ROOT)
        return rc or subprocess.call([py, "scripts/check_public.py"], cwd=ROOT)
    if cmd == "publish":
        sys.path.insert(0, str(ROOT))
        from app.publish import PublishError, publish
        try:
            print(publish(), "-> gh-pages")
            return 0
        except PublishError as e:
            print(e)
            return 1
    if cmd == "test":
        return subprocess.call([py, "-m", "pytest", "-q", *sys.argv[2:]], cwd=ROOT)
    if cmd != "dev":
        print(__doc__)
        return 2

    sys.path.insert(0, str(ROOT))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    from app import config, db
    from app.publish import scrape_and_publish

    from datetime import datetime, timedelta, timezone

    with db.session() as conn:
        last = db.get_meta(conn, "last_run")
    stale = not last or datetime.fromisoformat(last) < datetime.now(timezone.utc) - timedelta(minutes=30)
    if stale:
        # Catch up on anything published while the PC was off (scheduled runs that were missed don't replay).
        import threading
        print("Data is older than 30 min: scraping now in the background (and publishing if AUTO_PUBLISH=1)...")
        threading.Thread(target=scrape_and_publish, daemon=True).start()

    import uvicorn
    print(f"Dashboard: http://127.0.0.1:{config.PORT}")
    uvicorn.run("app.server:app", host="127.0.0.1", port=config.PORT, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
