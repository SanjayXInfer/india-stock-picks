"""Source plugin interface and reusable discovery helpers (RSS, HTML listings, news sitemaps)."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Callable, Iterable
from urllib.parse import urljoin

import feedparser
from lxml import etree
from selectolax.lexbor import LexborHTMLParser

from ..config import SourceConfig
from ..extract.text import article_text, published_date
from ..http import FetchError, PoliteClient
from ..models import Article

log = logging.getLogger(__name__)

RECO_TITLE = re.compile(
    r"\b(buy|sell|accumulate|reduce|target(?: price)?|stocks? to (?:buy|watch)|recommend\w*|top picks?|"
    r"stock picks?|picks|trade setup|stop[- ]?loss|(?:technical|stock|trading) ideas?|overweight|underweight|"
    r"upgrades?|downgrades?|bullish on|bearish on|rating|brokerages?)\b", re.I)
NOT_RECO_TITLE = re.compile(
    r"\b(live updates?|live blog|sell-?off|gold|silver|bitcoin|crypto|ipo|mutual funds?|nfo|wall street|"
    r"us stocks?|nasdaq|lottery|horoscope|fixed deposit|fd rates?)\b", re.I)


MARKET_CONTEXT = re.compile(
    r"\b(stocks?|shares?|target|brokerages?|buy|sell|picks?|rating|analysts?|ideas?|recommend\w*|"
    r"accumulate|stop[- ]?loss|overweight|underweight|upside)\b|;\s*target of", re.I)


def is_reco_title(title: str) -> bool:
    t = title or ""
    if not RECO_TITLE.search(t) or NOT_RECO_TITLE.search(t):
        return False
    # "upgrade"/"downgrade"/"reduce" alone are too generic ("Highway Upgrade"): need market context too.
    hits = {m.group(0).lower() for m in MARKET_CONTEXT.finditer(t)}
    return bool(hits - {"upgrade", "downgrade"})


class Candidate:
    __slots__ = ("title", "url", "published")

    def __init__(self, title: str, url: str, published: datetime | None = None):
        self.title, self.url, self.published = title.strip(), url.strip(), published


class Source:
    """Base class. Subclasses implement `discover()` or override `fetch_recent_articles()`.

    Options read from sources.yaml (all optional): feeds, listings (list of {url, pattern}),
    sitemaps, title_filter (bool, default true).
    """

    DEFAULT_OPTIONS: dict = {}

    def __init__(self, cfg: SourceConfig, client: PoliteClient):
        cfg.options = {**self.DEFAULT_OPTIONS, **cfg.options}  # sources.yaml overrides module defaults
        self.cfg = cfg
        self.client = client
        self.name = cfg.name
        self.label = cfg.label or cfg.name
        self.warnings: list[str] = []

    # ---- interface ------------------------------------------------------
    def fetch_recent_articles(self, since: datetime, skip: Callable[[str], bool] = lambda u: False) -> list[Article]:
        """Return articles published after `since` with body text. `skip(url)` => already processed."""
        seen, out = set(), []
        cands = [c for c in self.discover() if c.url and c.url not in seen and not seen.add(c.url)]
        if self.cfg.options.get("title_filter", True):
            cands = [c for c in cands if is_reco_title(c.title)]
        cands = [c for c in cands if c.published is None or c.published >= since]
        for c in cands:
            if len(out) >= self.cfg.max_articles:
                break
            if skip(c.url):
                continue
            try:
                page = self.get(c.url, cache_ttl=6 * 3600)
            except FetchError as e:
                self.warnings.append(e.kind)
                continue
            published = c.published or published_date(page)
            if published and published < since:
                continue
            out.append(Article(source=self.name, url=c.url, title=c.title, published=published,
                               text=article_text(page)))
        return out

    def discover(self) -> Iterable[Candidate]:
        opts = self.cfg.options
        for url in opts.get("feeds", []):
            yield from self._safe(self.rss, url)
        for item in opts.get("listings", []):
            yield from self._safe(self.html_listing, item["url"], item.get("pattern", "."))
        for url in opts.get("sitemaps", []):
            yield from self._safe(self.news_sitemap, url)

    # ---- helpers --------------------------------------------------------
    def get(self, url: str, cache_ttl: float = 600) -> bytes:
        return self.client.get(url, ua_mode=self.cfg.user_agent, min_delay=self.cfg.min_delay_s, cache_ttl=cache_ttl)

    def _safe(self, fn, *args) -> list[Candidate]:
        """Run one discovery endpoint; a failure is recorded but doesn't stop the other endpoints."""
        try:
            return list(fn(*args))
        except FetchError as e:
            self.warnings.append(e.kind)
        except Exception as e:  # noqa: BLE001 - malformed feed etc.
            log.warning("%s: discovery failed for %s: %s", self.name, args[0], e)
            self.warnings.append("parse error")
        return []

    def rss(self, url: str) -> Iterable[Candidate]:
        feed = feedparser.parse(self.get(url))
        for e in feed.entries:
            yield Candidate(e.get("title", ""), e.get("link", ""), _parse_date(e.get("published") or e.get("updated")))

    def html_listing(self, url: str, pattern: str) -> Iterable[Candidate]:
        tree = LexborHTMLParser(self.get(url).decode("utf-8", "replace"))
        rx = re.compile(pattern)
        for a in tree.css("a[href]"):
            href = urljoin(url, a.attributes.get("href") or "")
            title = (a.text(strip=True) or a.attributes.get("title") or "").strip()
            if len(title) > 25 and rx.search(href):
                yield Candidate(title, href.split("#")[0])

    def news_sitemap(self, url: str) -> Iterable[Candidate]:
        root = etree.fromstring(self.get(url))
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9", "n": "http://www.google.com/schemas/sitemap-news/0.9"}
        for u in root.findall("s:url", ns):
            yield Candidate(u.findtext("n:news/n:title", "", ns), u.findtext("s:loc", "", ns),
                            _parse_date(u.findtext("n:news/n:publication_date", None, ns)))


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
