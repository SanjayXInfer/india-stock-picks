"""Publish the static site from this machine to the repo's `gh-pages` branch (served by GitHub Pages).

Why: many news sites block cloud/datacenter IPs (GitHub Actions, Netlify), but work from a home
connection. So we scrape locally and push ONLY the built ./site files.

Safety: the branch is rebuilt from scratch in a temporary folder on every publish (single orphan commit,
force-pushed), so it never contains code, history, the DB, .env or anything outside ./site, and the
public safety check must pass first.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from . import config

log = logging.getLogger(__name__)
BRANCH = "gh-pages"


class PublishError(Exception):
    pass


def _git(*args: str, cwd: Path) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise PublishError(f"git {args[0]} failed: {(r.stderr or r.stdout).strip()[:300]}")
    return r.stdout.strip()


def publish() -> str:
    """Export ./site, run the safety check, force-push ./site to gh-pages. Returns the commit message."""
    sys.path.insert(0, str(config.ROOT / "scripts"))
    from export_static import main as export_site  # noqa: PLC0415

    site = export_site()
    check = subprocess.run([sys.executable, str(config.ROOT / "scripts" / "check_public.py"), str(site)],
                           capture_output=True, text=True)
    if check.returncode != 0:
        raise PublishError("public safety check failed, nothing published:\n" + check.stdout)

    remote = _git("remote", "get-url", "origin", cwd=config.ROOT)
    name = _git("config", "user.name", cwd=config.ROOT)
    email = _git("config", "user.email", cwd=config.ROOT)
    msg = f"Publish {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC"

    with tempfile.TemporaryDirectory(prefix="publish-") as tmp:
        work = Path(tmp)
        for f in site.iterdir():
            shutil.copy2(f, work / f.name)
        _git("init", "-q", "-b", BRANCH, cwd=work)
        _git("-c", f"user.name={name}", "-c", f"user.email={email}", "-c", "core.autocrlf=false",
             "add", "-A", cwd=work)
        _git("-c", f"user.name={name}", "-c", f"user.email={email}", "commit", "-q", "-m", msg, cwd=work)
        _git("push", "--force", "--quiet", remote, f"{BRANCH}:{BRANCH}", cwd=work)
    log.info("published to %s (%s)", BRANCH, msg)
    return msg


def scrape_and_publish() -> None:
    """Scheduler/Refresh entry point: scrape, then publish if AUTO_PUBLISH=1."""
    from .pipeline import run_scrape

    result = run_scrape()
    if config.AUTO_PUBLISH and result.get("status") != "already running":
        try:
            publish()
        except Exception as e:  # noqa: BLE001 - a failed publish must not kill the scheduler
            log.error("publish failed: %s", e)
