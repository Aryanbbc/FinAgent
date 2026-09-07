PYTHON ?= .venv/bin/python
HOST ?= 0.0.0.0
PORT ?= 8000

.PHONY: check-env release-check dev demo api frontend

check-env:
	$(PYTHON) scripts/check_environment.py

release-check:
	$(PYTHON) scripts/check_release.py

api:
	$(PYTHON) -m uvicorn finagent.api.main:app --host $(HOST) --port $(PORT)

frontend:
	cd frontend && npm run dev

dev:
	@sh -c '$(PYTHON) -m uvicorn finagent.api.main:app --host $(HOST) --port $(PORT) & api_pid=$$!; (cd frontend && npm run dev) & frontend_pid=$$!; trap "kill $$api_pid $$frontend_pid 2>/dev/null" INT TERM EXIT; wait $$api_pid $$frontend_pid'

demo:
	$(PYTHON) scripts/seed_demo.py
	DATABASE_URL=sqlite:///data/demo/finagent_v1_demo.db $(MAKE) dev
