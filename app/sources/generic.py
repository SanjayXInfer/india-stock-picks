"""Config-only source: everything comes from `feeds`, `listings` and `sitemaps` in sources.yaml."""
from .base import Source


class Generic(Source):
    pass


Plugin = Generic
