# Linux/macOS shortcuts (on Windows run the python commands directly).
PY ?= python

.PHONY: install index cache results test eval run docker up

install:
	$(PY) -m pip install -r requirements.txt
index:
	$(PY) scripts/build_index.py
cache:
	$(PY) scripts/warm_cache.py
results:
	$(PY) scripts/gen_results.py
test:
	$(PY) -m pytest -q
eval:
	$(PY) eval/run_eval.py
run:
	uvicorn app.main:app --host 0.0.0.0 --port 8000
docker:
	docker build -t smart-guided-troubleshooting .
up:
	docker compose up --build
