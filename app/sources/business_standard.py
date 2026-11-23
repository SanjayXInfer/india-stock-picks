"""Business Standard. Topic pages + markets RSS. NOTE: BS returns HTTP 403 (incl. robots.txt) to any
self-identifying bot User-Agent, so this source only works with `user_agent: browser` in sources.yaml."""
from .base import Source


class BusinessStandard(Source):
    DEFAULT_OPTIONS = {
        "listings": [
            {"url": "https://www.business-standard.com/topic/stocks-to-buy-today",
             "pattern": r"business-standard\.com/markets/.+_1\.html$"},
            {"url": "https://www.business-standard.com/topic/stock-recommendations",
             "pattern": r"business-standard\.com/markets/.+_1\.html$"},
        ],
        "feeds": ["https://www.business-standard.com/rss/markets-106.rss"],
    }


Plugin = BusinessStandard
