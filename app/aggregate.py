"""Build the dashboard payload (data.json). The same payload feeds the local server and the public site.

PUBLIC-SAFETY: every field is copied explicitly from an allowlist below. Nothing is dumped wholesale
from the DB or the environment, so secrets, local paths, raw errors and article text can't leak.
Grouping/ranking happens in the browser (web/app.js) so the lookback selector works on a static host.
"""
from __future__ import annotations

from datetime import datetime, timezone

from . import config, db

DISCLAIMER = "Aggregated third-party opinions. Not investment advice."


def _iso(ts: str | None) -> str | None:
    """'YYYY-MM-DD HH:MM:SS' (UTC) or ISO -> ISO8601 with Z."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace(" ", "T").replace("Z", "+00:00"))
    except ValueError:
        return None
    dt = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_payload(mode: str = "local", days: int = 4) -> dict:
    labels = {s.name: (s.label or s.name) for s in config.load_sources()}
    enabled = {s.name for s in config.load_sources() if s.enabled}
    with db.session() as conn:
        rows = conn.execute(
            "SELECT r.id, r.symbol, s.company, r.action, r.target, r.target_high, r.stop_loss, r.cmp_at_reco, "
            "r.horizon, r.analyst, r.brokerage, r.reason_summary, r.opinion_key, "
            "a.url, a.source, a.title, a.published "
            "FROM recommendations r JOIN articles a ON a.id = r.article_id JOIN stocks s ON s.symbol = r.symbol "
            "WHERE a.published >= datetime('now', ?) ORDER BY a.published DESC", (f"-{days} days",)).fetchall()
        stocks = conn.execute(
            "SELECT symbol, company, cmp, cmp_updated_at FROM stocks WHERE symbol IN "
            "(SELECT DISTINCT r.symbol FROM recommendations r JOIN articles a ON a.id = r.article_id "
            " WHERE a.published >= datetime('now', ?))", (f"-{days} days",)).fetchall()
        src_rows = conn.execute("SELECT * FROM sources ORDER BY name").fetchall()
        last_run = db.get_meta(conn, "last_run")
        extractor = db.get_meta(conn, "extractor")

    recos = [{
        "id": r["id"],
        "symbol": r["symbol"],
        "company": r["company"],
        "action": r["action"],
        "target": r["target"],
        "target_high": r["target_high"],
        "stop_loss": r["stop_loss"],
        "cmp_at_reco": r["cmp_at_reco"],
        "horizon": r["horizon"],
        "analyst": r["analyst"],
        "brokerage": r["brokerage"],
        "reason": r["reason_summary"],
        "opinion": r["opinion_key"],
        "url": r["url"] if str(r["url"]).startswith("https://") else None,
        "source": r["source"],
        "source_label": labels.get(r["source"], r["source"]),
        "title": r["title"],
        "published": _iso(r["published"]),
    } for r in rows]

    sources = [{
        "name": s["name"],
        "label": labels.get(s["name"], s["label"]),
        "enabled": s["name"] in enabled,
        "last_attempt": _iso(s["last_attempt"]),
        "last_success": _iso(s["last_success"]),
        "new_articles": s["last_articles"],  # new articles found by the last run
        "picks": sum(1 for r in recos if r["source"] == s["name"]),  # picks in the payload window
        # Errors are short categories produced by our code ("HTTP 403", "timeout"), never tracebacks.
        "error": (s["last_error"] or None) and str(s["last_error"])[:120],
    } for s in src_rows if s["name"] in labels]

    return {
        "mode": mode,
        "generated_at": _iso(datetime.now(timezone.utc).isoformat()),
        "last_run": _iso(last_run),
        "extractor": extractor if extractor in ("llm", "heuristic") else None,
        "disclaimer": DISCLAIMER,
        "recommendations": recos,
        "stocks": {s["symbol"]: {"company": s["company"], "cmp": s["cmp"],
                                 "cmp_updated_at": _iso(s["cmp_updated_at"])} for s in stocks},
        "sources": sources,
    }
