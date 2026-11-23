"""Core data types shared by sources, extractors and storage."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime

ACTIONS = ("Buy", "Sell", "Accumulate", "Hold", "Reduce")
HORIZONS = ("intraday", "short-term", "positional", "long-term")


@dataclass
class Article:
    """One article found by a source. `text` is transient: used for extraction, never stored."""

    source: str
    url: str
    title: str
    published: datetime | None = None
    text: str = ""
    # Some sources (e.g. Trendlyne's table) already yield structured picks; extraction is skipped.
    prestructured: list[dict] = field(default_factory=list)

    @property
    def content_hash(self) -> str:
        """Hash of normalised body text, used to spot the same article syndicated twice."""
        norm = re.sub(r"\W+", " ", (self.text or self.title).lower()).strip()
        return hashlib.sha1(norm[:4000].encode()).hexdigest()


@dataclass
class Recommendation:
    stock_name: str
    action: str
    target: float | None = None
    target_high: float | None = None
    stop_loss: float | None = None
    cmp_at_reco: float | None = None
    horizon: str | None = None
    analyst: str | None = None
    brokerage: str | None = None
    reason_summary: str = ""
    # Filled by the symbol mapper.
    symbol: str | None = None
    company: str | None = None
    match_score: float = 0.0
