import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def mapper():
    from app.symbols import SymbolMapper
    return SymbolMapper(csv_path=FIXTURES / "EQUITY_L_sample.csv")


@pytest.fixture(scope="session")
def articles():
    return json.loads((FIXTURES / "articles.json").read_text(encoding="utf-8"))


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Point the app at an empty temporary database (and away from the real one)."""
    from app import config
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "test.db")
    return tmp_path / "test.db"
