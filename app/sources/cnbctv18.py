"""CNBC-TV18. Single large market RSS feed (~200 items); keep reco-like titles."""
from .base import Source


class CNBCTV18(Source):
    DEFAULT_OPTIONS = {
        "feeds": ["https://www.cnbctv18.com/commonfeeds/v1/cne/rss/market.xml"],
    }


Plugin = CNBCTV18
