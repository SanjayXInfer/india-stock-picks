import json
from types import SimpleNamespace

import jsonschema
import pytest

from app.extract import FallbackExtractor, HeuristicExtractor, heuristic
from app.extract.schema import validate
from app.extract.text import article_text, published_date


def _mapped(recos, mapper):
    out = {}
    for r in recos:
        m = mapper.lookup_loose(r.stock_name)
        if m:
            out[m.symbol] = r
    return out


def _ids(articles):
    return [a["id"] for a in articles]


@pytest.fixture(params=range(7), ids=lambda i: f"article{i}")
def case(request, articles):
    return articles[request.param]


def test_heuristic_on_fixture(case, mapper):
    got = _mapped(heuristic.extract(case["title"], case["text"]), mapper)
    expected = {e["symbol"]: e for e in case["expect"]}
    assert set(got) == set(expected), case["id"]
    for sym, e in expected.items():
        r = got[sym]
        assert r.action == e["action"], (case["id"], sym)
        for field, attr in [("target", "target"), ("stop_loss", "stop_loss"), ("cmp", "cmp_at_reco"),
                            ("brokerage", "brokerage"), ("analyst", "analyst"), ("horizon", "horizon")]:
            if field in e:
                assert getattr(r, attr) == e[field], (case["id"], sym, field)


# ---- schema validation -------------------------------------------------

GOOD = {"recommendations": [{
    "stock_name": "Tata Steel", "action": "Buy", "target": 180, "target_high": 170, "stop_loss": 150,
    "cmp_at_reco": 160, "horizon": "short-term", "analyst": " Jane Doe ", "brokerage": "Choice Broking",
    "reason_summary": "Breakout above resistance on strong volume.",
}]}


def test_schema_accepts_and_normalises():
    [r] = validate(json.loads(json.dumps(GOOD)))
    assert (r.target, r.target_high) == (170, 180)  # swapped into low/high order
    assert r.analyst == "Jane Doe"


@pytest.mark.parametrize("mutate", [
    lambda d: d["recommendations"][0].update(action="Strong Buy"),     # not in enum
    lambda d: d["recommendations"][0].update(horizon="forever"),
    lambda d: d["recommendations"][0].pop("reason_summary"),           # required
    lambda d: d["recommendations"][0].update(extra="x"),               # additionalProperties
    lambda d: d["recommendations"][0].update(target="180"),            # wrong type
])
def test_schema_rejects(mutate):
    d = json.loads(json.dumps(GOOD))
    mutate(d)
    with pytest.raises(jsonschema.ValidationError):
        validate(d)


def test_schema_drops_implausible_target():
    d = json.loads(json.dumps(GOOD))
    d["recommendations"][0].update(target=16000, target_high=None, cmp_at_reco=160)  # 100x: a misread
    [r] = validate(d)
    assert r.target is None


# ---- LLM extractor (API mocked; no network, no key needed) ---------------

def _fake_response(payload, stop_reason="end_turn"):
    return SimpleNamespace(stop_reason=stop_reason,
                           content=[SimpleNamespace(type="text", text=json.dumps(payload))])


def test_llm_extractor_parses_structured_output(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    from app.extract.llm import LLMExtractor
    ex = LLMExtractor(model="claude-haiku-5-5")
    calls = []

    def create(**kw):
        calls.append(kw)
        return _fake_response(GOOD)

    monkeypatch.setattr(ex.client.messages, "create", create)
    [r] = ex.extract("title", "body text")
    assert r.stock_name == "Tata Steel"
    fmt = calls[0]["output_config"]["format"]
    assert fmt["type"] == "json_schema" and fmt["schema"]["required"] == ["recommendations"]
    assert "untrusted" in calls[0]["system"][0]["text"]


def test_fallback_used_when_llm_fails(monkeypatch, articles):
    class Broken:
        name = "llm"

        def extract(self, title, text):
            raise RuntimeError("model declined the request")

    ex = FallbackExtractor(Broken(), HeuristicExtractor())
    a = articles[0]
    assert ex.extract(a["title"], a["text"])
    assert ex.last_used == "heuristic"


# ---- article text extraction ----------------------------------------------

def test_article_text_prefers_jsonld_and_restores_breaks():
    page = """<html><head><script type="application/ld+json">
    {"@type": "NewsArticle", "datePublished": "2026-11-23T08:30:00+05:30",
     "articleBody": "Markets rose &amp;amp; closed higher.Analyst Jane Doe of Choice Broking likes the setup. """ + \
        "More words here to pass the length threshold. " * 10 + """"}
    </script></head><body><article><p>short</p>
    <table><tr><th>Stock</th><th>Rating</th><th>Target</th></tr><tr><td>ICICI Bank</td><td>Buy</td><td>₹1,750</td></tr></table>
    </article></body></html>"""
    text = article_text(page)
    assert "rose & closed higher.\nAnalyst" in text
    assert "ICICI Bank | Buy | ₹1,750" in text
    assert published_date(page).isoformat() == "2026-11-23T08:30:00+05:30"
