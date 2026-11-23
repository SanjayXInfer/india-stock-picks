"""Moneycontrol. All RSS feeds are frozen (Apr 2024), so we read the HTML tag/listing pages.
The recommendations tag lists broker-report headlines like "Buy X; target of Rs N: Broker"."""
from .base import Source


class Moneycontrol(Source):
    DEFAULT_OPTIONS = {
        "listings": [
            {"url": "https://www.moneycontrol.com/news/tags/recommendations.html",
             "pattern": r"moneycontrol\.com/news/business/(stocks|markets)/.+-\d+\.html$"},
            {"url": "https://www.moneycontrol.com/news/business/stocks/",
             "pattern": r"moneycontrol\.com/news/business/(stocks|markets)/.+-\d+\.html$"},
        ],
    }


Plugin = Moneycontrol
