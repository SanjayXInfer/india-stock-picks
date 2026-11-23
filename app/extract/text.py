"""Pull readable body text out of an article page (JSON-LD articleBody first, then <p> tags)."""
from __future__ import annotations

import html
import json
import re

from selectolax.lexbor import LexborHTMLParser


def _clean(s: str) -> str:
    for _ in range(3):  # some sites double/triple-escape (&amp;amp;#039;)
        u = html.unescape(s)
        if u == s:
            break
        s = u
    s = re.sub(r"<[^>]+>", " ", s).replace("\xa0", " ")
    # JSON-LD bodies often glue paragraphs together ("profit-taking.Vatsal"): restore the break.
    s = re.sub(r"([a-z%)\]][.!?:;])(?=[A-Z“\"])", r"\1\n", s)
    return re.sub(r"[ \t\r\f\v]+", " ", s).strip()


def _walk(node):
    if isinstance(node, list):
        for n in node:
            yield from _walk(n)
    elif isinstance(node, dict):
        yield node
        for k in ("@graph", "mainEntity"):
            if k in node:
                yield from _walk(node[k])


def published_date(page: bytes | str):
    """datePublished from JSON-LD or <meta property="article:published_time">, as aware datetime or None."""
    from datetime import datetime, timezone

    tree = LexborHTMLParser(page if isinstance(page, str) else page.decode("utf-8", "replace"))
    candidates = []
    for s in tree.css('script[type="application/ld+json"]'):
        try:
            for obj in _walk(json.loads(s.text(), strict=False)):
                if obj.get("datePublished"):
                    candidates.append(str(obj["datePublished"]))
        except ValueError:
            continue
    for sel in ('meta[property="article:published_time"]', 'meta[itemprop="datePublished"]',
                'meta[name="publish-date"]'):
        if (m := tree.css_first(sel)) and m.attributes.get("content"):
            candidates.append(m.attributes["content"])
    for c in candidates:
        try:
            dt = datetime.fromisoformat(c.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None


def _tables(root) -> str:
    """Render <table>s as 'cell | cell' lines (broker target tables are common and get mangled otherwise)."""
    lines = []
    for table in root.css("table"):
        for tr in table.css("tr"):
            cells = [c.text(strip=True) for c in tr.css("th, td")]
            if len(cells) >= 2 and any(cells):
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def article_text(page: bytes | str) -> str:
    tree = LexborHTMLParser(page if isinstance(page, str) else page.decode("utf-8", "replace"))
    ld = ""
    for s in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(s.text(), strict=False)
        except ValueError:
            continue
        for obj in _walk(data):
            body = obj.get("articleBody")
            if isinstance(body, str) and len(body) > len(ld):
                ld = body
    ld = _clean(ld)
    root = tree.css_first("article") or tree.css_first("main") or tree.body
    if root is None:
        return ld
    paras = _clean("\n".join(p.text(strip=True) for p in root.css("p") if len(p.text(strip=True)) > 40))
    # JSON-LD is cleanest but sometimes truncated; take whichever is substantially longer.
    text = ld if len(ld) >= 0.8 * len(paras) else paras
    tables = _tables(root)
    return f"{text}\n\n{tables}".strip() if tables else text
