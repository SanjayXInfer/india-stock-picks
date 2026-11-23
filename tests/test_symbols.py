import pytest

from app.symbols import normalise


@pytest.mark.parametrize("name,symbol,method", [
    ("PHOENIXLTD", "PHOENIXLTD", "symbol"),          # exact NSE symbol
    ("M&M", "M&M", "symbol"),
    ("BAJAJ-AUTO", "BAJAJ-AUTO", "symbol"),
    ("RIL", "RELIANCE", "alias"),                     # alias table
    ("BoB", "BANKBARODA", "alias"),
    ("Mahindra & Mahindra", "M&M", "alias"),
    ("HDFC Bank", "HDFCBANK", "name"),                # exact normalised name
    ("Bank of India", "BANKINDIA", "name"),
    ("The Phoenix Mills", "PHOENIXLTD", "name"),
    ("KPR Mill", "KPRMILL", "name"),                  # "K.P.R. Mill" single-letter collapse
    ("J Kumar Infraprojects", "JKIL", "name"),
    ("Amber Enterprises", "AMBER", "prefix"),         # unique prefix of "Amber Enterprises India"
    ("Dixon Technologies", "DIXON", "name"),      # "(India)" is dropped by normalise()
    ("Eris Lifescience", "ERIS", "fuzzy"),            # small typo
])
def test_lookup_maps(mapper, name, symbol, method):
    m = mapper.lookup(name)
    assert m is not None, name
    assert (m.symbol, m.method) == (symbol, method)


@pytest.mark.parametrize("name", [
    "Nifty", "Bank Nifty", "Nifty 50", "Sensex", "Gold", "Bitcoin", "Apple", "Nvidia", "Nasdaq",
    "Tata",            # ambiguous prefix (Tata Steel / Chemicals / Elxsi / Technologies)
    "HDFC",            # ambiguous (HDFC Bank / HDFC Life)
    "Some Random Company", "", "Bank",
])
def test_lookup_rejects(mapper, name):
    assert mapper.lookup(name) is None


def test_lookup_loose_drops_trailing_words(mapper):
    assert mapper.lookup_loose("Tata Steel shares jump").symbol == "TATASTEEL"
    assert mapper.lookup("Tata Steel shares jump") is None


def test_normalise():
    assert normalise("K.P.R. Mill Limited") == "kpr mill"
    assert normalise("Dixon Technologies (India) Ltd.") == "dixon technologies"
    assert normalise("Dr. Reddy's") == "dr reddys"
