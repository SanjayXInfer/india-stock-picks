"""Goodreturns. The 'shares-to-buy' feed is stale (Mar 2025), so we filter the general news feed.
Expect few hits from this source."""
from .base import Source


class Goodreturns(Source):
    DEFAULT_OPTIONS = {
        "feeds": [
            "https://www.goodreturns.in/rss/news-fb.xml",
            "https://www.goodreturns.in/rss/feeds/shares-to-buy-fb.xml",
        ],
    }


Plugin = Goodreturns
