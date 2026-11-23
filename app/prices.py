"""Optional delayed prices via Yahoo Finance (yfinance, '<SYMBOL>.NS'). Cached in the stocks table."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from . import config, db

log = logging.getLogger(__name__)


def refresh_prices(max_age_minutes: int = 30) -> int:
    if not config.FETCH_PRICES:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)).isoformat(timespec="seconds")
    with db.session() as conn:
        symbols = [r["symbol"] for r in conn.execute(
            "SELECT DISTINCT s.symbol FROM stocks s JOIN recommendations r ON r.symbol = s.symbol "
            "JOIN articles a ON a.id = r.article_id WHERE a.published >= datetime('now', '-4 days') "
            "AND (s.cmp_updated_at IS NULL OR s.cmp_updated_at < ?)", (cutoff,))]
    if not symbols:
        return 0
    import yfinance as yf

    tickers = [f"{s}.NS" for s in symbols]
    data = yf.download(tickers, period="5d", interval="1d", progress=False, auto_adjust=False,
                       group_by="ticker", threads=True)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    updated = 0
    with db.session() as conn:
        for sym, t in zip(symbols, tickers):
            try:
                closes = (data[t]["Close"] if len(tickers) > 1 else data["Close"]).dropna()
                price = float(closes.iloc[-1].item() if hasattr(closes.iloc[-1], "item") else closes.iloc[-1])
            except Exception:  # noqa: BLE001 - delisted/renamed symbol etc.
                continue
            conn.execute("UPDATE stocks SET cmp = ?, cmp_updated_at = ? WHERE symbol = ?", (price, now, sym))
            updated += 1
    log.info("updated %d/%d prices", updated, len(symbols))
    return updated
