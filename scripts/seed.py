"""Run one scrape so the dashboard isn't empty on first launch."""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.pipeline import run_scrape  # noqa: E402

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    only = sys.argv[1:] or None  # optional: source names to run
    print(json.dumps(run_scrape(source_names=only), indent=2))
