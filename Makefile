.PHONY: setup db demo serve web dev test lint monitors docker
PY = PYTHONPATH=src .venv/bin/python

setup:            ## install Python and web dependencies
	uv sync
	cd web && npm ci --no-audit --no-fund

db:               ## start a private Postgres in .data/ (uses your installed Postgres 18)
	./scripts/pg.sh start

demo: db web      ## rebuild the demo: an invented company, 60 simulated days, then serve it
	$(PY) -m outbound demo 60
	$(PY) -m outbound serve

serve:            ## serve the API and the built web app on :8800
	$(PY) -m outbound serve

web:              ## build the web app
	cd web && npm run build

dev:              ## web app with hot reload on :5173, API on :8800
	$(PY) -m outbound serve & cd web && npm run dev

test: db          ## the whole suite, on real Postgres
	$(PY) -m pytest

lint:
	.venv/bin/ruff check src tests
	cd web && npm run typecheck

monitors:         ## run every monitor once
	$(PY) -m outbound monitors

docker:           ## the same image the hosted demo runs
	docker build -t outbound-desk . && docker run --rm -p 8800:8800 outbound-desk
