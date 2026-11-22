PY := .venv/bin/python

install:
	uv venv .venv && uv pip install --python $(PY) -r requirements-dev.txt

redis:
	redis-server --port 6379 --save "" --appendonly no

api:
	$(PY) -m uvicorn app.main:app --reload --port 8000

worker:
	$(PY) -m worker.vton_worker

test:
	$(PY) -m pytest -q

.PHONY: install redis api worker test
