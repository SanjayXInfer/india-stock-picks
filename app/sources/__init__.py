"""Source registry: each module in this package exposes `Plugin`, a `Source` subclass.

To add a site: create app/sources/<module>.py with a Plugin class (often just DEFAULT_OPTIONS),
then add an entry to sources.yaml. A site that only needs RSS/listing/sitemap URLs can instead use
`module: generic` and list the URLs in sources.yaml without writing any code.
"""
from __future__ import annotations

import importlib

from ..config import SourceConfig, load_sources
from ..http import PoliteClient
from .base import Source


def build_sources(client: PoliteClient, include_disabled: bool = False,
                  configs: list[SourceConfig] | None = None) -> list[Source]:
    out = []
    for cfg in configs if configs is not None else load_sources():
        if not cfg.enabled and not include_disabled:
            continue
        module = importlib.import_module(f"{__name__}.{cfg.module}")
        out.append(module.Plugin(cfg, client))
    return out
