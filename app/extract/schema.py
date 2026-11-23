"""Strict JSON schema for extracted recommendations, plus validation/normalisation."""
from __future__ import annotations

import jsonschema

from ..models import ACTIONS, HORIZONS, Recommendation

_num = {"type": ["number", "null"]}
_str = {"type": ["string", "null"]}

RECO_ITEM = {
    "type": "object",
    "properties": {
        "stock_name": {"type": "string", "description": "Company name or NSE symbol as written"},
        "action": {"type": "string", "enum": list(ACTIONS)},
        "target": {**_num, "description": "Target price in INR (lower bound if a range)"},
        "target_high": {**_num, "description": "Upper bound if a target range was given, else null"},
        "stop_loss": _num,
        "cmp_at_reco": {**_num, "description": "Price when recommended / buy-above level, if stated"},
        "horizon": {"type": ["string", "null"], "enum": [*HORIZONS, None]},
        "analyst": {**_str, "description": "Person who made the call, if named"},
        "brokerage": {**_str, "description": "Firm the analyst works for / that issued the report"},
        "reason_summary": {"type": "string", "description": "1-2 sentences, paraphrased, why"},
    },
    "required": ["stock_name", "action", "target", "target_high", "stop_loss", "cmp_at_reco", "horizon",
                 "analyst", "brokerage", "reason_summary"],
    "additionalProperties": False,
}

EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {"recommendations": {"type": "array", "items": RECO_ITEM}},
    "required": ["recommendations"],
    "additionalProperties": False,
}

_validator = jsonschema.Draft202012Validator(EXTRACTION_SCHEMA)


def validate(payload: dict) -> list[Recommendation]:
    """Validate against the schema (raises jsonschema.ValidationError), then sanity-check values."""
    _validator.validate(payload)
    out = []
    for item in payload["recommendations"]:
        r = Recommendation(**item)
        r.stock_name = r.stock_name.strip()
        for f in ("target", "target_high", "stop_loss", "cmp_at_reco"):
            v = getattr(r, f)
            if v is not None and not (0 < v < 10_000_000):
                setattr(r, f, None)
        if r.target and r.target_high and r.target_high < r.target:
            r.target, r.target_high = r.target_high, r.target
        # A target wildly off the reference price is almost certainly a mis-read.
        if r.target and r.cmp_at_reco and not (0.2 < r.target / r.cmp_at_reco < 5):
            r.target = r.target_high = None
        r.reason_summary = (r.reason_summary or "").strip()[:400]
        r.analyst = (r.analyst or "").strip() or None
        r.brokerage = (r.brokerage or "").strip() or None
        if r.stock_name:
            out.append(r)
    return out
