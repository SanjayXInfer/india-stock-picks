"""Extractor selection: LLM when ANTHROPIC_API_KEY is set, regex/heuristic otherwise (and as fallback)."""
from __future__ import annotations

import logging

from .. import config
from ..models import Recommendation
from . import heuristic

log = logging.getLogger(__name__)


class HeuristicExtractor:
    name = "heuristic"

    def extract(self, title: str, text: str) -> list[Recommendation]:
        return heuristic.extract(title, text)


class FallbackExtractor:
    """Try the LLM; on any API/validation failure fall back to the heuristic for that article."""

    def __init__(self, primary, fallback):
        self.primary, self.fallback = primary, fallback
        self.name = primary.name
        self.last_used = primary.name

    def extract(self, title: str, text: str) -> list[Recommendation]:
        try:
            self.last_used = self.primary.name
            return self.primary.extract(title, text)
        except Exception as e:  # noqa: BLE001
            log.warning("LLM extraction failed (%s); using heuristic for: %s", type(e).__name__, title[:80])
            self.last_used = self.fallback.name
            return self.fallback.extract(title, text)


def get_extractor():
    if config.has_api_key():
        from .llm import LLMExtractor
        return FallbackExtractor(LLMExtractor(), HeuristicExtractor())
    return HeuristicExtractor()
