.PHONY: install run lint format typecheck test cov check live-check snapshot

PY ?= .venv/bin/python

install:
	python3 -m venv .venv && $(PY) -m pip install -r requirements-dev.txt

run:
	$(PY) -m uvicorn app.main:app --reload

lint:
	$(PY) -m ruff check . && $(PY) -m ruff format --check .

format:
	$(PY) -m ruff check --fix . && $(PY) -m ruff format .

typecheck:
	$(PY) -m mypy

test:
	$(PY) -m pytest -q

cov:
	$(PY) -m pytest -q --cov --cov-fail-under=90

check: lint typecheck cov  ## what CI runs

live-check:  ## needs NASA_API_KEY in .env
	$(PY) -m scripts.check_donki_live
