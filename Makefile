.PHONY: setup db demo serve web dev test lint monitors docker evals evals-live
PY = PYTHONPATH=src .venv/bin/python

setup:            ## install Python and web dependencies
	uv sync
	cd web && npm ci --no-audit --no-fund

db:               ## start a private Postgres in .data/ (uses your installed Postgres 18)
	./scripts/pg.sh start

demo: db web      ## rebuild the demo: an invented company, 90 simulated days, then serve it
	$(PY) -m outbound demo 90
	$(PY) -m outbound serve

serve:            ## serve the API and the built web app on :8800
	$(PY) -m outbound serve

web:              ## build the web app
	cd web && npm run build

dev:              ## web app with hot reload on :5173, API on :8800
	$(PY) -m outbound serve & cd web && npm run dev

test: db          ## the whole suite, on real Postgres
	$(PY) -m pytest

evals:            ## every AI eval, replayed from recordings (free; what CI does)
	$(PY) evals/run_replies.py && $(PY) evals/run_writing.py && $(PY) evals/run_suggest.py && $(PY) evals/run_extract.py && \
	$(PY) evals/run_themes.py && $(PY) evals/run_draft_play.py

evals-live:       ## every AI eval against live Claude, recording each answer (costs roughly $5 to $10)
	ANTHROPIC_LIVE=1 $(PY) evals/run_replies.py; ANTHROPIC_LIVE=1 $(PY) evals/run_writing.py; \
	ANTHROPIC_LIVE=1 $(PY) evals/run_suggest.py; ANTHROPIC_LIVE=1 $(PY) evals/run_extract.py; \
	ANTHROPIC_LIVE=1 $(PY) evals/run_themes.py; ANTHROPIC_LIVE=1 $(PY) evals/run_draft_play.py

lint:
	.venv/bin/ruff check src tests evals
	cd web && npm run typecheck

monitors:         ## run every monitor once
	$(PY) -m outbound monitors

docker:           ## the same image the hosted demo runs
	docker build -t account-desk . && docker run --rm -p 8800:8800 account-desk
