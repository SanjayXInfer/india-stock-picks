"""Livemint. Markets RSS + stock-market-news listing ("Top 3 stocks to buy ... by <analyst>")."""
from .base import Source


class Livemint(Source):
    DEFAULT_OPTIONS = {
        "feeds": ["https://www.livemint.com/rss/markets"],
        "listings": [
            {"url": "https://www.livemint.com/market/stock-market-news",
             "pattern": r"livemint\.com/market/stock-market-news/.+-\d+\.html$"},
        ],
    }


Plugin = Livemint
