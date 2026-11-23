"""Trendlyne research reports (/research-reports/<type>/): a table of broker reports with targets.

Rows are already structured (date, stock, broker, LTP, target, price at reco, type), and each row embeds
JSON-LD with the NSE symbol and the report URL, so no LLM call is needed. robots.txt asks for a
crawl-delay; the PoliteClient honours it (we use >= 10 s regardless).
"""
from __future__ import annotations

import html
import json
import re
from datetime import datetime, time, timezone

from selectolax.lexbor import LexborHTMLParser

from ..config import IST
from ..http import FetchError
from ..models import Article
from .base import Source

_TYPES = {"buy": "Buy", "sell": "Sell", "accumulate": "Accumulate", "hold": "Hold", "reduce": "Reduce",
          "neutral": "Hold", "add": "Accumulate", "strong buy": "Buy"}


def _num(s: str) -> float | None:
    m = re.match(r"\s*([\d,]+(?:\.\d+)?)", s or "")
    return float(m.group(1).replace(",", "")) if m else None


def parse_table(html: str) -> list[dict]:
    """Parse the research-report table into row dicts (pure function, unit-tested with a fixture)."""
    tree = LexborHTMLParser(html)
    table = tree.css_first("table")
    if table is None:
        return []
    headers = [th.text(strip=True).lower() for th in table.css("thead th")]
    rows = []
    for tr in table.css("tbody tr"):
        cells = [td.text(strip=True) for td in tr.css("td")]
        if len(cells) < 8:
            continue
        col = dict(zip(headers, cells)) if len(headers) == len(cells) else {}
        meta = {}
        for s in tr.css('script[type="application/ld+json"]'):
            try:
                obj = json.loads(s.text(), strict=False)
            except ValueError:
                continue
            if obj.get("@type") == "Review":
                meta = obj
        sym = None
        same_as = (meta.get("itemReviewed") or {}).get("sameAs", "")
        if m := re.search(r"/equity/\d+/([^/]+)/", same_as):
            sym = m.group(1)
        stock_a = tr.css_first('a[href*="/research-reports/stock/"]')
        rows.append({
            "date": col.get("date") or cells[1],
            "stock": stock_a.text(strip=True) if stock_a else (col.get("stock") or cells[2]),
            "symbol": sym,
            "broker": (meta.get("author") or {}).get("name") or col.get("author") or cells[3],
            "target": _num(col.get("target") or cells[5]),
            "price_at_reco": _num(col.get("price at reco(change since reco%)") or cells[6]),
            "type": (col.get("type") or cells[8]).strip(),
            "url": meta.get("url") or "",
            "description": meta.get("description") or "",
        })
    return rows


class Trendlyne(Source):
    DEFAULT_OPTIONS = {"pages": ["https://trendlyne.com/research-reports/buy/",
                                 "https://trendlyne.com/research-reports/sell/"]}

    def fetch_recent_articles(self, since: datetime, skip=lambda u: False) -> list[Article]:
        out = []
        for page in self.cfg.options.get("pages", []):
            try:
                page_html = self.get(page).decode("utf-8", "replace")
            except FetchError as e:
                self.warnings.append(e.kind)
                continue
            for row in parse_table(page_html):
                try:
                    day = datetime.strptime(row["date"], "%d %b %Y").date()
                except ValueError:
                    continue
                # Reports carry a date only; treat as published at market close IST that day.
                published = datetime.combine(day, time(15, 30), IST).astimezone(timezone.utc)
                action = _TYPES.get(row["type"].lower())
                if not action or published < since or not row["url"] or skip(row["url"]):
                    continue
                desc = re.sub(r"View Report$", "", html.unescape(row["description"])).strip()
                desc = re.sub(r"^[^|]*\|\s*", "", desc)  # drop "BOBCAPS Research | "
                out.append(Article(
                    source=self.name, url=row["url"], title=f"{row['broker']}: {action} {row['stock']}",
                    published=published, text=desc,
                    prestructured=[{
                        "stock_name": row["symbol"] or row["stock"], "action": action,
                        "target": row["target"], "target_high": None, "stop_loss": None,
                        "cmp_at_reco": row["price_at_reco"], "horizon": "long-term", "analyst": None,
                        "brokerage": row["broker"],
                        # Trendlyne's one-line report headline, trimmed; the heuristic can't paraphrase.
                        "reason_summary": re.sub(r"^.*?\)\s*:\s*", "", desc)[:220],
                    }],
                ))
        return out[: self.cfg.max_articles * 2]


Plugin = Trendlyne
