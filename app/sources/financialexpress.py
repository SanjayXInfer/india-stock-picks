"""Financial Express. WordPress feeds are disabled (HTTP 410); the Google-News sitemap lists the last
~2 days of articles with titles and timestamps."""
from .base import Source


class FinancialExpress(Source):
    DEFAULT_OPTIONS = {
        "sitemaps": ["https://www.financialexpress.com/news-sitemap.xml"],
    }


Plugin = FinancialExpress
