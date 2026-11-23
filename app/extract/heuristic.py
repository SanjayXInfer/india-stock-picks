"""Regex/heuristic extractor, used when no ANTHROPIC_API_KEY is set (or the LLM call fails).

It recognises the common Indian stock-pick patterns:
  * "Buy Piramal Finance; target of Rs 2470: Motilal Oswal"          (Moneycontrol titles)
  * "Buy PHOENIXLTD in cash above 2285 | SL @ 2200 | Target @ 2450"   (broker technical notes)
  * "Swiggy: Buy at ₹400, target ₹440, stop loss ₹380"                (listicles)
  * "Buy Tata Chemicals ... target price of ₹1,050 ... stop loss ₹960" (free text)
  * "Citi maintains sell on Hindustan Zinc"                            (broker-rating roundups)
  * "Tata Technologies: PL Capital Retains 'Reduce'"                   (research-report headlines)
Stock names it finds are only candidates; the symbol mapper rejects anything not NSE-listed.
Reasons are short excerpts (not paraphrases) since there is no model to summarise.
"""
from __future__ import annotations

import re

from ..brokerages import find_brokerages
from ..models import Recommendation

ACTION_MAP = {
    "buy": "Buy", "strong buy": "Buy", "outperform": "Buy", "overweight": "Buy", "positive": "Buy",
    "sell": "Sell", "underweight": "Sell", "underperform": "Sell", "short": "Sell",
    "accumulate": "Accumulate", "add": "Accumulate",
    "hold": "Hold", "neutral": "Hold", "equal-weight": "Hold", "equalweight": "Hold",
    "reduce": "Reduce",
}
_ACT = r"(?:strong buy|buy|sell|accumulate|reduce|hold|add|neutral|overweight|underweight|outperform|underperform)"
_PRICE = r"(?:(?:Rs\.?|₹|INR)\s*)?(\d[\d,]*(?:\.\d+)?)"
_NAME = r"[A-Z0-9][\w&.'\-]*(?:\s+(?:of\s+|&\s+)?[A-Z0-9&][\w&.'\-]*){0,5}"
_STOP = {"at", "for", "with", "on", "in", "above", "below", "near", "around", "target", "tgt", "sl", "stop",
         "says", "from", "by", "amid", "as", "and", "or", "to", "shares", "share", "stock", "stocks", "ltd",
         "ltd.", "limited", "cmp", "price", "is", "can", "could", "may", "will", "today", "now", "rating",
         "recommends", "recommended", "between", "range", "this", "the", "a", "an", "call", "|", "-"}
_REASON_WORDS = re.compile(
    r"\b(because|due to|driven by|expect|growth|margin|earnings|breakout|support|resistance|momentum|"
    r"valuation|demand|order|rsi|macd|moving average|trend|recovery|upside|outlook|guidance|volume)\b", re.I)

RE_MC_TITLE = re.compile(rf"^(?P<action>{_ACT})\s+(?P<name>.+?);\s*target of\s*{_PRICE}\s*:\s*(?P<broker>.+)$", re.I)
_ACTI = "(?i:" + _ACT[3:]  # same alternatives, case-insensitive, while names stay case-sensitive
RE_SL_NOTE = re.compile(
    rf"\b(?P<action>(?i:buy|sell))\s+(?P<name>[A-Z][A-Z0-9&\-]{{2,}})\b(?i:\s+in\s+(?:cash|futures))?\s*"
    rf"(?i:above|below|at|around|near|@)?\s*{_PRICE}?[^\n]{{0,40}}?\b(?i:SL)\s*[@:]?\s*{_PRICE}[^\n]{{0,40}}?"
    rf"\b(?i:target|tgt)s?\s*[@:]?\s*{_PRICE}")
RE_LABEL = re.compile(rf"(?P<name>{_NAME})\s*[:–—-]\s*(?P<action>{_ACTI})\b"
                      rf"(?=\s+(?i:at|around|above|between|in|near|@|for|with|,|\(|₹|rs))")
RE_ANCHOR = re.compile(rf"\b(?P<action>(?i:buy|sell|accumulate))\s+(?P<name>{_NAME})")
RE_RATING = re.compile(
    rf"(?P<broker>[A-Z][\w&.]*(?:\s+[A-Z][\w&.]*){{0,3}})\s+(?i:maintains|retains|reiterates|recommends|has|keeps|"
    rf"upgrades?\s+\w+\s+to|downgrades?\s+\w+\s+to|initiates\s+coverage\s+(?:on\s+\w+\s+)?with|remains|turns|is)\s+"
    rf"(?i:an?\s+)?['‘\"]?(?P<action>{_ACTI}|(?i:bullish|bearish))['’\"]?\s+(?i:rating\s+|call\s+|stance\s+)?(?i:on)\s+"
    rf"(?P<name>{_NAME})")
RE_RATING_HEAD = re.compile(
    rf"^(?P<name>[^:]{{3,60}}):\s*(?P<broker>[^:]{{2,60}}?)\s+(?:retains|maintains|reiterates|upgrades to|"
    rf"downgrades to|initiates with|remains|recommends)\s+['‘\"]?(?P<action>{_ACT}|bullish|bearish)['’\"]?", re.I)
RE_TARGET = re.compile(rf"\b(?:target(?:\s+price)?|tgt|TP)s?\b\s*(?:of|at|to|is|:|@|-)?\s*{_PRICE}"
                       rf"(?:\s*(?:-|–|to|and)\s*{_PRICE})?", re.I)
RE_SL = re.compile(rf"\b(?:stop[\s-]?loss|SL)\b\s*(?:of|at|is|:|@|-|below|above)?\s*{_PRICE}", re.I)
RE_ENTRY = re.compile(rf"\b(?:buy|sell|accumulate)\b[^.\n]{{0,60}}?\b(?:at|around|above|near|between|@|cmp)\s*"
                      rf"{_PRICE}", re.I)
_PERSON = r"(?P<name>[A-Z][a-z]+(?:\s+[A-Z]\.?)?(?:\s+[A-Z][a-z]+){1,2})"
RE_ANALYST = re.compile(r"\b(?:by|says|said|according to|recommended by|suggests?|picks? by|[Aa]nalyst)\s+"
                        + _PERSON + r"\b")
# "Vatsal Bhuva, Technical and Derivative Research Analyst at LKP Securities"
RE_ANALYST_TITLE = re.compile(_PERSON + r",\s+(?:[A-Za-z&–-]+\s+){0,8}?(?:at|of|with|from)\s+")
RE_TITLE_BY = re.compile(r"\bby\s+" + _PERSON + r"\b")


def _num(s: str | None) -> float | None:
    if not s:
        return None
    try:
        v = float(s.replace(",", ""))
    except ValueError:
        return None
    return v if v > 0 else None


def clean_name(raw: str) -> str:
    """Cut a captured name at the first stop word: 'Tata Steel For Target Of' -> 'Tata Steel'."""
    words = []
    for w in raw.strip().split():
        if words and w.lower().strip(",;:") in _STOP:
            break
        words.append(w.strip(",;:'\"’‘"))
    return " ".join(words).strip(" .-")


def horizon_of(text: str, default: str | None = None) -> str | None:
    t = text.lower()
    if re.search(r"\bintraday\b|\bfor today\b|\btoday'?s? trad", t):
        return "intraday"
    if re.search(r"\b(12|twelve|18|24)[ -]?months?\b|\blong[ -]term\b|\bone year\b|\bfy2\d\b|\bmultibagger", t):
        return "long-term"
    if re.search(r"\bpositional\b|\b(1|2|3|one|two|three)[- ]?(?:to[- ]\d[- ])?months?\b|\bmedium[ -]term\b", t):
        return "positional"
    if re.search(r"\bshort[ -]term\b|\bswing\b|\b\d[ -]?(?:to[ -]\d[ -])?weeks?\b|\bnear[ -]term\b|\bbtst\b", t):
        return "short-term"
    return default


def _reason(window: str) -> str:
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", window) if s.strip()]
    cand = [s for s in sentences[1:] + sentences[:1]
            if _REASON_WORDS.search(s) and len(s) > 30 and "|" not in s and not re.search(r"disclaimer", s, re.I)]
    pick = (cand or [""])[0]
    return (pick[:217] + "...") if len(pick) > 220 else pick


def _analyst(title: str, text: str) -> str | None:
    """A person's name, only trusted if a known brokerage is mentioned right after it."""
    for rx in (RE_ANALYST_TITLE, RE_ANALYST):
        for m in rx.finditer(text):
            after = text[m.end(): m.end() + 60]
            if find_brokerages(after) and not find_brokerages(m.group("name")):
                return m.group("name")
    if m := RE_TITLE_BY.search(title):  # "Top 3 stocks to buy ... by Ganesh Dongre"
        if not find_brokerages(m.group("name")):
            return m.group("name")
    return None


def _table_rows(text: str):
    """Rows like 'ICICI Bank | Buy | ₹1,750 | 8.8%' -> (name, action, target)."""
    for line in text.splitlines():
        if line.count("|") < 2:
            continue
        cells = [c.strip() for c in line.split("|")]
        act_idx = next((i for i, c in enumerate(cells[1:], 1) if c.lower() in ACTION_MAP), None)
        if act_idx is None:
            continue
        price = next((m for c in cells[act_idx + 1:] if (m := re.fullmatch(_PRICE, c.replace(" ", "")))), None)
        if price:
            yield cells[0], cells[act_idx], price.group(1)


def extract(title: str, text: str) -> list[Recommendation]:
    title = (title or "").strip()
    text = (text or "").strip()
    title_brokers, body_brokers = find_brokerages(title), find_brokerages(text[:3000])
    brokers = title_brokers or body_brokers
    article_broker = brokers[0] if len(brokers) == 1 else None
    article_analyst = _analyst(title, text)
    if article_analyst and not article_broker:
        near = text.find(article_analyst)
        nb = find_brokerages(text[near: near + 150]) if near >= 0 else []
        article_broker = nb[0] if nb else None
    title_horizon = horizon_of(title)
    found: dict[tuple[str, str], Recommendation] = {}

    def add(name, action, *, target=None, target_high=None, sl=None, cmp=None, broker=None, window="",
            horizon=None):
        name = clean_name(name)
        action = ACTION_MAP.get(action.lower(), {"bullish": "Buy", "bearish": "Sell"}.get(action.lower()))
        if not name or not action or len(name) < 2:
            return
        key = (name.lower(), action)
        new = Recommendation(
            stock_name=name, action=action, target=_num(target), target_high=_num(target_high),
            stop_loss=_num(sl), cmp_at_reco=_num(cmp),
            # A stop-loss with no stated horizon is almost always a short-term trading call.
            horizon=horizon or horizon_of(window, title_horizon) or ("short-term" if _num(sl) else None),
            analyst=article_analyst, brokerage=broker or article_broker, reason_summary=_reason(window),
        )
        if key in found:  # a second pattern hit the same pick: fill in whatever the first one missed
            old = found[key]
            for f in ("target", "target_high", "stop_loss", "cmp_at_reco", "horizon", "brokerage", "reason_summary"):
                if not getattr(old, f) and getattr(new, f):
                    setattr(old, f, getattr(new, f))
            return
        found[key] = new

    # 1. Moneycontrol-style title.
    if m := RE_MC_TITLE.match(title):
        add(m["name"], m["action"], target=m[3], broker=(find_brokerages(m["broker"]) or [m["broker"]])[0],
            window=text[:1200], horizon=horizon_of(text[:1500], "long-term"))
    # 2. Research-report headline: "Stock: Broker Retains 'Reduce'".
    elif m := RE_RATING_HEAD.match(title):
        t = RE_TARGET.search(text[:800])
        add(m["name"], m["action"], broker=(find_brokerages(m["broker"]) or [m["broker"]])[0],
            window=text[:1200], horizon="long-term", target=t[1] if t else None)

    body = title + "\n" + text
    # 3. "Buy X ... SL @ ... Target @ ..."
    for m in RE_SL_NOTE.finditer(body):
        add(m["name"], m["action"], cmp=m[3], sl=m[4], target=m[5], window=body[m.end(): m.end() + 500])
    # 4. Broker rating sentences.
    for m in RE_RATING.finditer(body):
        broker = find_brokerages(m["broker"])
        if broker:
            window = body[m.end(): m.end() + 500]
            t = RE_TARGET.search(window[:250])
            add(m["name"], m["action"], broker=broker[0], window=window, horizon="long-term",
                target=t[1] if t else None, target_high=t[2] if t else None)
    # 5. Target tables.
    for name, action, target in _table_rows(text):
        add(name, action, target=target, window=text[:1500], horizon=title_horizon or "long-term")
    # 6. "Name: Buy at ..." and "Buy Name ... target ..." with details in the following window.
    anchors = [(m.start(), m.end(), m["name"], m["action"]) for m in RE_LABEL.finditer(body)]
    anchors += [(m.start(), m.end(), m["name"], m["action"]) for m in RE_ANCHOR.finditer(body)]
    anchors.sort()
    for i, (start, end, name, action) in enumerate(anchors):
        nxt = next((a[0] for a in anchors[i + 1:] if a[0] > end + 20), len(body))
        window = body[start: min(nxt, end + 450)]
        t = RE_TARGET.search(window)
        if not t:
            continue  # without a target it's usually not a concrete pick ("buy on dips")
        sl = RE_SL.search(window)
        entry = RE_ENTRY.search(window)
        add(name, action, target=t[1], target_high=t[2], sl=sl[1] if sl else None,
            cmp=entry[1] if entry else None, window=window)
    return list(found.values())
