"""De-duplication, Trendlyne parsing, the public payload and the publish safety check."""
import json
import subprocess
import sys
from datetime import datetime, timezone

from app import db
from app.extract import HeuristicExtractor
from app.models import Article
from app.pipeline import process_article
from app.sources.base import is_reco_title
from app.sources.trendlyne import parse_table

from conftest import FIXTURES, ROOT

NOW = datetime.now(timezone.utc)
MINT = ("Top 3 stocks to buy: Swiggy, Tata Chemicals, Amber Enterprises by Ganesh Dongre",
        "Ganesh Dongre of Anand Rathi recommended these.\n1] Swiggy: Buy at ₹179 | Target ₹190 | "
        "Stop-loss ₹175;")


def _art(source, url, title, text):
    return Article(source=source, url=url, title=title, published=NOW, text=text)


def test_same_analyst_on_two_sites_is_one_opinion(temp_db, mapper):
    ex = HeuristicExtractor()
    with db.session() as conn:
        process_article(conn, _art("livemint", "https://a.example/1", *MINT), ex, mapper)
        # Same call, rewritten by a different site (different text => different content hash).
        process_article(conn, _art("goodreturns", "https://b.example/2", "Ganesh Dongre picks Swiggy",
                                   "Analyst Ganesh Dongre of Anand Rathi: Swiggy: Buy at ₹180 | "
                                   "Target ₹190 | Stop-loss ₹175"), ex, mapper)
        rows = conn.execute("SELECT opinion_key, article_id FROM recommendations WHERE symbol='SWIGGY'").fetchall()
    assert len(rows) == 2                                  # listed under each website...
    assert len({r["opinion_key"] for r in rows}) == 1      # ...but one analyst opinion
    assert rows[0]["opinion_key"] == "SWIGGY|Buy|anand rathi"


def test_syndicated_copy_reuses_extraction(temp_db, mapper):
    class Counting(HeuristicExtractor):
        calls = 0

        def extract(self, title, text):
            Counting.calls += 1
            return super().extract(title, text)

    ex = Counting()
    with db.session() as conn:
        process_article(conn, _art("livemint", "https://a.example/1", *MINT), ex, mapper)
        process_article(conn, _art("goodreturns", "https://b.example/copy", *MINT), ex, mapper)
        n = conn.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
        extractors = [r[0] for r in conn.execute("SELECT extractor FROM articles ORDER BY id")]
    assert Counting.calls == 1                 # second copy did not trigger a second extraction
    assert n == 2 and extractors == ["heuristic", "duplicate"]


def test_buy_and_sell_kept_separate(temp_db, mapper):
    ex = HeuristicExtractor()
    with db.session() as conn:
        process_article(conn, _art("et", "https://a.example/x", "Brokerages split on Dixon",
                                   "Citi maintains sell on Dixon with a target price of Rs 12,000. "
                                   "Morgan Stanley remains overweight on Dixon with a target of Rs 18,500."), ex, mapper)
        actions = sorted(r[0] for r in conn.execute("SELECT action FROM recommendations WHERE symbol='DIXON'"))
    assert actions == ["Buy", "Sell"]


def test_trendlyne_parse_table():
    [row] = parse_table((FIXTURES / "trendlyne_sample.html").read_text(encoding="utf-8"))
    assert row["symbol"] == "ERIS" and row["type"] == "Buy"
    assert row["target"] == 1674.0 and row["price_at_reco"] == 1317.2
    assert row["broker"] == "BOB Capital Markets Ltd."
    assert row["url"].startswith("https://trendlyne.com/posts/")


def test_title_filter():
    assert is_reco_title("Buy Piramal Finance; target of Rs 2470: Motilal Oswal")
    assert is_reco_title("Stocks to buy today: 3 technical ideas by Choice Equity")
    assert not is_reco_title("Rajasthan Highway Upgrade: NHAI plans to widen NH-148")
    assert not is_reco_title("Gold rate today: should you buy?")
    assert not is_reco_title("Sensex, Nifty fall as AI sell-off deepens")


def test_payload_is_allowlisted(temp_db, mapper, monkeypatch):
    from app.aggregate import build_payload
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api03-SHOULD-NEVER-APPEAR-0123456789")
    with db.session() as conn:
        process_article(conn, _art("livemint", "https://a.example/1", *MINT), HeuristicExtractor(), mapper)
        db.record_source_run(conn, "livemint", "Livemint", True, ok=False, error="HTTP 403")
    payload = build_payload(mode="static")
    blob = json.dumps(payload)
    assert "sk-ant" not in blob and str(ROOT) not in blob
    assert set(payload) == {"mode", "generated_at", "last_run", "extractor", "disclaimer",
                            "recommendations", "stocks", "sources"}
    assert set(payload["recommendations"][0]) == {
        "id", "symbol", "company", "action", "target", "target_high", "stop_loss", "cmp_at_reco", "horizon",
        "analyst", "brokerage", "reason", "opinion", "url", "source", "source_label", "title", "published"}
    assert payload["disclaimer"] == "Aggregated third-party opinions. Not investment advice."


def test_check_public_blocks_secrets(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text("<p>ok</p>")
    (site / "data.json").write_text('{"x": 1}')
    script = str(ROOT / "scripts" / "check_public.py")
    assert subprocess.run([sys.executable, script, str(site)], capture_output=True).returncode == 0

    (site / "data.json").write_text('{"k": "sk-ant-api03-abcdefghijklmnopqrstuvwxyz"}')
    assert subprocess.run([sys.executable, script, str(site)], capture_output=True).returncode == 1

    (site / "data.json").write_text('{"x": 1}')
    (site / "dashboard.db").write_text("")  # unexpected file
    assert subprocess.run([sys.executable, script, str(site)], capture_output=True).returncode == 1
