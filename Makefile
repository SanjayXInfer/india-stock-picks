# Thin wrapper around dev.py (which also works on Windows without make).
PY ?= python

.PHONY: dev seed export test install

install:
	$(PY) -m venv .venv && .venv/bin/python -m pip install -r requirements.txt

dev:
	$(PY) dev.py

seed:
	$(PY) dev.py seed

export:
	$(PY) dev.py export

test:
	$(PY) dev.py test
