"""Google News RSS search (discovery fallback).

DISABLED BY DEFAULT: news.google.com/robots.txt disallows /rss/ for all user agents, and the item links
are Google redirect URLs (also disallowed). If enabled, the PoliteClient will still refuse disallowed
URLs, so this module only works if Google's robots.txt changes. Titles are used as the article text.
"""
from __future__ import annotations

from datetime import datetime
from urllib.parse import quote_plus

from ..http import FetchError
from ..models import Article
from .base import Source, is_reco_title


class GoogleNews(Source):
    DEFAULT_OPTIONS = {
        "queries": ["stocks to buy today", "stock recommendations India", "target price brokerage buy"],
    }

    def fetch_recent_articles(self, since: datetime, skip=lambda u: False) -> list[Article]:
        out = []
        for q in self.cfg.options.get("queries", []):
            url = f"https://news.google.com/rss/search?q={quote_plus(q)}+when:1d&hl=en-IN&gl=IN&ceid=IN:en"
            try:
                cands = list(self.rss(url))
            except FetchError as e:
                self.warnings.append(e.kind)
                continue
            for c in cands:
                if is_reco_title(c.title) and (c.published is None or c.published >= since) and not skip(c.url):
                    out.append(Article(source=self.name, url=c.url, title=c.title, published=c.published,
                                       text=c.title))
        return out[: self.cfg.max_articles]


Plugin = GoogleNews
