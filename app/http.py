"""Polite HTTP client: robots.txt, per-domain rate limiting, disk cache, retries."""
from __future__ import annotations

import hashlib
import logging
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import truststore
from protego import Protego

from . import config

truststore.inject_into_ssl()  # use the OS certificate store (fixes Windows/corporate CA issues)
log = logging.getLogger(__name__)


class FetchError(Exception):
    """A fetch failed; `kind` is a short, non-sensitive category shown in Source health."""

    def __init__(self, kind: str, url: str):
        super().__init__(f"{kind}: {url}")
        self.kind = kind


class PoliteClient:
    def __init__(self, cache_dir: Path = config.HTTP_CACHE_DIR, timeout: float = 20.0, retries: int = 3):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.retries = retries
        self._clients = {
            mode: httpx.Client(
                http2=True,
                timeout=timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": ua,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Accept-Language": "en-IN,en;q=0.9",
                },
            )
            for mode, ua in (("bot", config.BOT_USER_AGENT), ("browser", config.BROWSER_USER_AGENT))
        }
        self._robots: dict[str, Protego | None] = {}
        self._last_hit: dict[str, float] = {}
        self._domain_locks: dict[str, threading.Lock] = {}
        self._lock = threading.Lock()

    # -- helpers -----------------------------------------------------------
    def _domain_lock(self, host: str) -> threading.Lock:
        with self._lock:
            return self._domain_locks.setdefault(host, threading.Lock())

    def _wait_turn(self, host: str, min_delay: float) -> None:
        wait = self._last_hit.get(host, 0) + min_delay - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._last_hit[host] = time.monotonic()

    def _robots_for(self, scheme: str, host: str, ua_mode: str) -> Protego | None:
        key = f"{ua_mode}|{host}"
        if key not in self._robots:
            try:
                r = self._clients[ua_mode].get(f"{scheme}://{host}/robots.txt")
                self._robots[key] = Protego.parse(r.text) if r.status_code == 200 else None
                if r.status_code in (401, 403):
                    # Can't read the rules: treat as "disallow all" (the conservative choice).
                    self._robots[key] = Protego.parse("User-agent: *\nDisallow: /")
            except httpx.HTTPError:
                self._robots[key] = None  # unreachable robots.txt => no restrictions known
        return self._robots[key]

    def allowed(self, url: str, ua_mode: str = "bot") -> bool:
        parts = urlsplit(url)
        rp = self._robots_for(parts.scheme, parts.netloc, ua_mode)
        return True if rp is None else rp.can_fetch(url, "IndiaStockRecoDashboard")

    def crawl_delay(self, url: str, ua_mode: str = "bot") -> float:
        rp = self._robots.get(f"{ua_mode}|{urlsplit(url).netloc}")
        try:
            return float(rp.crawl_delay("IndiaStockRecoDashboard") or 0) if rp else 0.0
        except (TypeError, ValueError):
            return 0.0

    # -- public ------------------------------------------------------------
    def get(self, url: str, *, ua_mode: str = "bot", min_delay: float = 3.0, cache_ttl: float = 600) -> bytes:
        """Fetch a URL, honouring robots.txt and rate limits. Raises FetchError."""
        key = hashlib.sha1(f"{ua_mode}|{url}".encode()).hexdigest()
        cache_file = self.cache_dir / key
        if cache_ttl and cache_file.exists() and time.time() - cache_file.stat().st_mtime < cache_ttl:
            return cache_file.read_bytes()

        host = urlsplit(url).netloc
        with self._domain_lock(host):
            if not self.allowed(url, ua_mode):
                raise FetchError("blocked by robots.txt", url)
            delay = max(min_delay, self.crawl_delay(url, ua_mode))
            last_exc: Exception | None = None
            for attempt in range(self.retries):
                self._wait_turn(host, delay)
                try:
                    r = self._clients[ua_mode].get(url)
                except httpx.TimeoutException:
                    last_exc = FetchError("timeout", url)
                except httpx.HTTPError:
                    last_exc = FetchError("network error", url)
                else:
                    if r.status_code == 200:
                        cache_file.write_bytes(r.content)
                        return r.content
                    last_exc = FetchError(f"HTTP {r.status_code}", url)
                    if r.status_code not in (429, 500, 502, 503, 504):
                        break  # not retryable
                time.sleep(2 ** attempt)
            raise last_exc  # type: ignore[misc]

    def purge_cache(self, max_age_s: float = 2 * 86400) -> None:
        now = time.time()
        for f in self.cache_dir.iterdir():
            if now - f.stat().st_mtime > max_age_s:
                f.unlink(missing_ok=True)
