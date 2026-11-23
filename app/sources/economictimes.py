"""Economic Times Markets. The dedicated /recos RSS is stale (last item May 2026); stock-pick articles
now appear in the Expert View and Stocks feeds, so we read those and keep reco-like titles."""
from .base import Source


class EconomicTimes(Source):
    DEFAULT_OPTIONS = {
        "feeds": [
            "https://economictimes.indiatimes.com/markets/expert-view/rssfeeds/50649960.cms",
            "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
            "https://economictimes.indiatimes.com/markets/stocks/recos/rssfeeds/3053611.cms",
        ],
    }


Plugin = EconomicTimes
