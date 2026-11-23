"""Map free-text stock names to NSE symbols using NSE's EQUITY_L.csv + aliases + fuzzy matching."""
from __future__ import annotations

import csv
import io
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import yaml
from rapidfuzz import fuzz, process

from . import config

log = logging.getLogger(__name__)

EQUITY_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
_SUFFIXES = re.compile(r"\b(limited|ltd|the|inc|corporation|corp|company|co)\b")


def normalise(name: str) -> str:
    s = name.lower().replace("&", " & ").replace("'s", "s")
    s = re.sub(r"\(.*?\)", " ", s)  # "(India)", "(I)"
    s = re.sub(r"[^a-z0-9& ]+", " ", s)
    s = _SUFFIXES.sub(" ", s)
    s = re.sub(r"\s+", " ", s).strip()
    # Collapse runs of single letters: "k p r mill" -> "kpr mill", "r r kabel" -> "rr kabel".
    return re.sub(r"\b(?:[a-z] )+[a-z]\b", lambda m: m.group(0).replace(" ", ""), s)


@dataclass
class Match:
    symbol: str
    company: str
    score: float
    method: str


class SymbolMapper:
    def __init__(self, csv_path: Path = config.EQUITY_CSV, aliases_path: Path = config.ALIASES_YAML,
                 threshold: float = 90.0):
        self.threshold = threshold
        self.companies: dict[str, str] = {}  # symbol -> company name
        with open(csv_path, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                row = {k.strip(): (v or "").strip() for k, v in row.items()}
                if row.get("SYMBOL"):
                    self.companies[row["SYMBOL"]] = row["NAME OF COMPANY"]
        self.by_norm: dict[str, str] = {}
        for sym, name in self.companies.items():
            self.by_norm.setdefault(normalise(name), sym)
        self._norm_names = list(self.by_norm)

        raw = yaml.safe_load(aliases_path.read_text(encoding="utf-8")) or {}
        self.aliases = {normalise(k): v for k, v in (raw.get("aliases") or {}).items()}
        self.blocklist = {normalise(b) for b in raw.get("blocklist") or []}

    def _hit(self, symbol: str, score: float, method: str) -> Match | None:
        if symbol not in self.companies:
            return None
        return Match(symbol, self.companies[symbol], score, method)

    def lookup(self, name: str) -> Match | None:
        """Return the best NSE match for `name`, or None if not confidently an Indian listed equity."""
        if not name or len(name) > 80:
            return None
        raw = name.strip()
        raw = re.sub(r"\s+(shares?|stock|share price|ltd\.?)$", "", raw, flags=re.I)
        norm = normalise(raw)
        if not norm or norm in self.blocklist or norm.split()[0] in {"nifty", "sensex", "banknifty"}:
            return None

        # 1. Exact NSE symbol ("PHOENIXLTD", "M&M", "BAJAJ-AUTO").
        if raw.upper() in self.companies:
            return self._hit(raw.upper(), 100, "symbol")
        # 2. Alias table.
        if norm in self.aliases:
            return self._hit(self.aliases[norm], 100, "alias")
        # 3. Exact normalised company name.
        if norm in self.by_norm:
            return self._hit(self.by_norm[norm], 100, "name")
        # 4. Unique prefix: "Amber Enterprises" -> "amber enterprises india".
        if len(norm) >= 4:
            pref = [n for n in self._norm_names if n.startswith(norm + " ")]
            if len(pref) == 1:
                return self._hit(self.by_norm[pref[0]], 95, "prefix")
        # 5. Fuzzy, conservative.
        best = process.extractOne(norm, self._norm_names, scorer=fuzz.token_sort_ratio,
                                  score_cutoff=self.threshold)
        if best:
            return self._hit(self.by_norm[best[0]], float(best[1]), "fuzzy")
        return None

    def lookup_loose(self, name: str) -> Match | None:
        """lookup(), then retry with up to two trailing words dropped ('Tata Steel Shares Jump')."""
        words = (name or "").split()
        for drop in range(0, min(3, len(words))):
            cand = " ".join(words[: len(words) - drop])
            if len(cand) < 3:
                break
            if m := self.lookup(cand):
                return m
        return None


def ensure_equity_csv(client=None, max_age_days: float = 7) -> Path:
    """Download NSE's equity master list if missing or stale. Falls back to the cached copy on failure."""
    path = config.EQUITY_CSV
    if path.exists() and time.time() - path.stat().st_mtime < max_age_days * 86400:
        return path
    try:
        from .http import PoliteClient
        client = client or PoliteClient()
        data = client.get(EQUITY_URL, min_delay=1, cache_ttl=0)
        next(csv.reader(io.StringIO(data.decode("utf-8-sig"))))  # sanity: parseable header
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    except Exception as e:  # noqa: BLE001 - stale list is better than none
        if not path.exists():
            raise
        log.warning("Could not refresh EQUITY_L.csv (%s); using cached copy", e)
    return path
