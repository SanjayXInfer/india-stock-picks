"""NDTV Profit. RSS + research-reports listing. NOTE: its CDN returns HTTP 403 (incl. robots.txt) to
self-identifying bot User-Agents, so this source only works with `user_agent: browser` in sources.yaml."""
from .base import Source


class NDTVProfit(Source):
    DEFAULT_OPTIONS = {
        "feeds": ["https://www.ndtvprofit.com/rss"],
        "listings": [
            {"url": "https://www.ndtvprofit.com/research-reports",
             "pattern": r"ndtvprofit\.com/markets/[a-z0-9-]{20,}"},
        ],
    }


Plugin = NDTVProfit
