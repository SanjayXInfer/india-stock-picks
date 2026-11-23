"""One-command launcher (cross-platform; `make` is optional).

    python dev.py              start server + scheduler on http://127.0.0.1:8000 (seeds first if DB is empty)
    python dev.py seed [src..] run one scrape now
    python dev.py export       build the public static site in ./site and run the safety check
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
    if cmd == "test":
        return subprocess.call([py, "-m", "pytest", "-q", *sys.argv[2:]], cwd=ROOT)
    if cmd != "dev":
        print(__doc__)
        return 2

    sys.path.insert(0, str(ROOT))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    from app import config, db
    from app.pipeline import run_scrape

    with db.session() as conn:
        empty = conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 0
    if empty:
        import threading
        print("Database is empty: running a first scrape in the background (takes a few minutes)...")
        threading.Thread(target=run_scrape, daemon=True).start()

    import uvicorn
    print(f"Dashboard: http://127.0.0.1:{config.PORT}")
    uvicorn.run("app.server:app", host="127.0.0.1", port=config.PORT, log_level="info")
    return 0


if __name__ == "__main__":
    sys.exit(main())
