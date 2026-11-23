"""Known brokerages/research houses: canonical names, used for detection and de-duplication."""
from __future__ import annotations

import re

# canonical -> alternative spellings (lower-case). Order matters only for display.
BROKERAGES: dict[str, list[str]] = {
    "Motilal Oswal": ["motilal oswal", "mofsl"],
    "ICICI Securities": ["icici securities", "i-sec", "icicidirect", "icici direct"],
    "Kotak Securities": ["kotak securities", "kotak institutional equities", "kotak neo"],
    "Choice Broking": ["choice broking", "choice equity"],
    "Anand Rathi": ["anand rathi"],
    "Geojit": ["geojit"],
    "PL Capital": ["prabhudas lilladher", "pl capital", "plindia"],
    "Emkay Global": ["emkay"],
    "Nuvama": ["nuvama"],
    "JM Financial": ["jm financial"],
    "HDFC Securities": ["hdfc securities"],
    "Axis Securities": ["axis securities", "axis capital"],
    "Sharekhan": ["sharekhan"],
    "LKP Securities": ["lkp securities", "lkp"],
    "Religare Broking": ["religare"],
    "SMC Global": ["smc global"],
    "Angel One": ["angel one", "angel broking"],
    "Bonanza": ["bonanza"],
    "Elara Capital": ["elara"],
    "Citi": ["citi", "citigroup", "citibank"],
    "Morgan Stanley": ["morgan stanley"],
    "Goldman Sachs": ["goldman sachs", "goldman"],
    "Jefferies": ["jefferies"],
    "CLSA": ["clsa"],
    "Nomura": ["nomura"],
    "UBS": ["ubs"],
    "HSBC": ["hsbc"],
    "BofA Securities": ["bofa", "bank of america", "bofa securities"],
    "Macquarie": ["macquarie"],
    "Bernstein": ["bernstein"],
    "JP Morgan": ["jp morgan", "jpmorgan", "j.p. morgan"],
    "Ambit": ["ambit"],
    "Centrum Broking": ["centrum"],
    "Antique Stock Broking": ["antique"],
    "Systematix": ["systematix"],
    "Ventura Securities": ["ventura"],
    "Mehta Equities": ["mehta equities"],
    "Asit C Mehta": ["asit c mehta", "asit c. mehta"],
    "StoxBox": ["stoxbox"],
    "Master Capital": ["master capital"],
    "BOB Capital Markets": ["bob capital", "bobcaps"],
    "IDBI Capital": ["idbi capital"],
    "Yes Securities": ["yes securities"],
    "Dolat Capital": ["dolat"],
    "Investec": ["investec"],
    "PhillipCapital": ["phillipcapital", "phillip capital"],
    "Nirmal Bang": ["nirmal bang"],
    "InCred Equities": ["incred"],
    "Monarch Networth": ["monarch networth"],
    "Equirus": ["equirus"],
    "Arihant Capital": ["arihant capital"],
    "Bajaj Broking": ["bajaj broking"],
    "SAMCO": ["samco"],
    "Tradebulls": ["tradebulls"],
    "Enrich Money": ["enrich money"],
    "Lakshmishree": ["lakshmishree"],
    "Reliance Securities": ["reliance securities"],
    "Ashika": ["ashika"],
    "Sushil Finance": ["sushil finance"],
    "Hem Securities": ["hem securities"],
    "Wealth Mine Networks": ["wealthmine"],
    "Pace 360": ["pace 360"],
    "Jainam Broking": ["jainam"],
    "Swastika Investmart": ["swastika"],
}

_PATTERNS = sorted(
    ((alt, canon) for canon, alts in BROKERAGES.items() for alt in (alts or [canon.lower()])),
    key=lambda x: -len(x[0]),
)
_RE = re.compile(r"\b(" + "|".join(re.escape(a) for a, _ in _PATTERNS) + r")\b", re.I)
_CANON = {a: c for a, c in _PATTERNS}


def find_brokerages(text: str) -> list[str]:
    """Canonical brokerage names in order of first appearance."""
    seen: list[str] = []
    for m in _RE.finditer(text or ""):
        c = _CANON[m.group(1).lower()]
        if c not in seen:
            seen.append(c)
    return seen


def canonical(name: str | None) -> str | None:
    if not name:
        return None
    found = find_brokerages(name)
    return found[0] if found else name.strip()


def person_key(name: str | None) -> str | None:
    """Normalise an analyst name for identity: 'Mr. Ganesh Dongre' -> 'ganesh dongre'."""
    if not name:
        return None
    s = re.sub(r"\b(mr|ms|mrs|dr|shri)\.?\s+", "", name.lower())
    s = re.sub(r"[^a-z ]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s or None
