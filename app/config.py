"""Paths, environment and source configuration."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
SITE_DIR = ROOT / "site"
DB_PATH = DATA_DIR / "dashboard.db"
HTTP_CACHE_DIR = DATA_DIR / "http_cache"
EQUITY_CSV = DATA_DIR / "EQUITY_L.csv"
SOURCES_YAML = ROOT / "sources.yaml"
ALIASES_YAML = ROOT / "app" / "aliases.yaml"

IST = ZoneInfo("Asia/Kolkata")


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader (KEY=VALUE lines); real env vars take precedence."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if value and key not in os.environ:
            os.environ[key] = value


_load_dotenv(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


ANTHROPIC_MODEL = env("ANTHROPIC_MODEL", "claude-haiku-5-5")
CONTACT_URL = env("CONTACT_URL")
FETCH_PRICES = env("FETCH_PRICES", "1") not in ("0", "false", "no")
PORT = int(env("PORT", "8000"))

BOT_USER_AGENT = "Mozilla/5.0 (compatible; IndiaStockRecoDashboard/1.0" + (
    f"; +{CONTACT_URL})" if CONTACT_URL else ")"
)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)


def has_api_key() -> bool:
    return bool(env("ANTHROPIC_API_KEY"))


@dataclass
class SourceConfig:
    name: str
    module: str
    enabled: bool = True
    label: str = ""
    user_agent: str = "bot"  # "bot" (descriptive) or "browser"
    min_delay_s: float = 3.0
    max_articles: int = 25
    options: dict = field(default_factory=dict)


def load_sources(path: Path = SOURCES_YAML) -> list[SourceConfig]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    defaults = raw.get("defaults", {})
    out = []
    fields = set(SourceConfig.__dataclass_fields__) - {"name", "options"}
    for name, cfg in (raw.get("sources") or {}).items():
        merged = {**defaults, **(cfg or {})}
        known = {k: merged.pop(k) for k in list(merged) if k in fields}
        options = {**merged.pop("options", {}), **merged}  # unknown keys become options
        out.append(SourceConfig(name=name, options=options, **known))
    return out
