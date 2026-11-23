"""One scrape run: fetch sources -> extract -> map symbols -> de-duplicate -> store."""
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from . import db
from .brokerages import canonical, person_key
from .extract import get_extractor
from .extract.schema import validate
from .http import PoliteClient
from .models import Article, Recommendation
from .sources import build_sources
from .symbols import SymbolMapper, ensure_equity_csv

log = logging.getLogger(__name__)
_run_lock = threading.Lock()


def opinion_key(r: Recommendation, content_hash: str) -> str:
    """Identity of an opinion: the same house's call on the same stock and action is one opinion no matter
    how many sites syndicate it. Keyed on the brokerage (sites name it more consistently than the person),
    then the analyst; unattributed calls fall back to the article text hash, so only verbatim copies of
    the same article collapse."""
    who = (canonical(r.brokerage) or "").lower() or person_key(r.analyst) or f"article:{content_hash[:12]}"
    return f"{r.symbol}|{r.action}|{who}"


def _fill_brokerage(conn, r: Recommendation) -> None:
    """If a site names only the analyst, borrow the brokerage we've seen with that analyst before."""
    if r.brokerage or not r.analyst:
        return
    row = conn.execute(
        "SELECT brokerage FROM recommendations WHERE lower(analyst) = lower(?) AND brokerage IS NOT NULL "
        "ORDER BY id DESC LIMIT 1", (r.analyst,)).fetchone()
    if row:
        r.brokerage = row["brokerage"]


def _db_time(dt: datetime | None) -> str:
    dt = (dt or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def process_article(conn, art: Article, extractor, mapper: SymbolMapper) -> int:
    """Extract and store one article. Returns number of recommendations stored."""
    chash = art.content_hash
    dup = conn.execute(
        "SELECT a.id FROM articles a WHERE a.content_hash = ? AND a.url != ? ORDER BY a.id LIMIT 1",
        (chash, art.url)).fetchone()

    if dup:  # syndicated copy of an article we already extracted: reuse its picks, no second LLM call
        rows = conn.execute("SELECT * FROM recommendations WHERE article_id = ?", (dup["id"],)).fetchall()
        recos = [Recommendation(**{k: row[k] for k in ("stock_name", "action", "target", "target_high",
                                  "stop_loss", "cmp_at_reco", "horizon", "analyst", "brokerage",
                                  "reason_summary", "symbol")}) for row in rows]
        used = "duplicate"
    elif art.prestructured:
        recos, used = validate({"recommendations": art.prestructured}), "table"
    else:
        recos = extractor.extract(art.title, art.text)
        used = getattr(extractor, "last_used", extractor.name)

    article_id = db.insert_article(conn, url=art.url, source=art.source, title=art.title[:300],
                                   published=_db_time(art.published), content_hash=chash,
                                   extractor=used if recos else "none")
    stored = 0
    for r in recos:
        if not r.symbol:
            m = mapper.lookup_loose(r.stock_name)
            if not m:
                log.debug("unmapped: %r (%s)", r.stock_name, art.url)
                continue
            r.symbol, r.company, r.match_score = m.symbol, m.company, m.score
        else:
            r.company = mapper.companies.get(r.symbol, r.stock_name)
        r.brokerage = canonical(r.brokerage)
        _fill_brokerage(conn, r)
        db.upsert_stock(conn, r.symbol, r.company or r.stock_name)
        db.insert_reco(conn, article_id, r, opinion_key(r, chash))
        stored += 1
    return stored


def run_scrape(lookback_hours: float = 72, source_names: list[str] | None = None) -> dict:
    """Run every enabled source once. Safe to call from the scheduler and the Refresh button."""
    if not _run_lock.acquire(blocking=False):
        return {"status": "already running"}
    try:
        return _run(lookback_hours, source_names)
    finally:
        _run_lock.release()


def is_running() -> bool:
    return _run_lock.locked()


def _run(lookback_hours: float, source_names: list[str] | None) -> dict:
    started = datetime.now(timezone.utc)
    since = started - timedelta(hours=lookback_hours)
    client = PoliteClient()
    mapper = SymbolMapper(ensure_equity_csv(client))
    extractor = get_extractor()
    sources = [s for s in build_sources(client) if not source_names or s.name in source_names]

    with db.session() as conn:
        known = {row["url"] for row in conn.execute("SELECT url FROM articles")}

    def fetch(src):
        try:
            return src, src.fetch_recent_articles(since, skip=lambda u: u in known), None
        except Exception as e:  # noqa: BLE001 - one broken source must not break the run
            log.exception("source %s crashed", src.name)
            return src, [], f"crashed: {type(e).__name__}"

    # Sources fetch in parallel (each domain is rate-limited separately); extraction is sequential.
    with ThreadPoolExecutor(max_workers=max(1, len(sources))) as pool:
        results = list(pool.map(fetch, sources))

    summary = {"started": started.isoformat(), "extractor": extractor.name, "sources": {}}
    with db.session() as conn:
        for src, articles, crash in results:
            n_recos = 0
            for art in articles:
                if art.url in known:
                    continue
                known.add(art.url)
                try:
                    n_recos += process_article(conn, art, extractor, mapper)
                    conn.commit()
                except Exception:  # noqa: BLE001
                    conn.rollback()
                    log.exception("failed to process %s", art.url)
                    src.warnings.append("extraction error")
            warnings = sorted(set(src.warnings))
            error = crash or (", ".join(warnings) if warnings else None)
            ok = crash is None and not (not articles and _all_failed(src))
            db.record_source_run(conn, src.name, src.label, True, ok=ok, articles=len(articles), recos=n_recos,
                                 error=error)
            summary["sources"][src.name] = {"articles": len(articles), "recos": n_recos, "error": error}
        db.set_meta(conn, "last_run", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        db.set_meta(conn, "extractor", extractor.name)
        db.prune(conn)
    client.purge_cache()

    try:
        from .prices import refresh_prices
        refresh_prices()
    except Exception as e:  # noqa: BLE001 - prices are optional
        log.warning("price refresh failed: %s", e)
    log.info("scrape done: %s", summary)
    return summary


def _all_failed(src) -> bool:
    """True when every discovery endpoint of the source failed (vs. 'fetched fine, nothing new')."""
    opts = src.cfg.options
    endpoints = len(opts.get("feeds", [])) + len(opts.get("listings", [])) + len(opts.get("sitemaps", [])) \
        + len(opts.get("pages", [])) + len(opts.get("queries", []))
    return len(src.warnings) >= max(1, endpoints)
