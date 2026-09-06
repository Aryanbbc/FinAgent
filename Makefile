PYTHON ?= .venv/bin/python

.PHONY: check-env dev demo api frontend

check-env:
	$(PYTHON) scripts/check_environment.py

api:
	$(PYTHON) -m uvicorn finagent.api.main:app --host 127.0.0.1 --port 8000

frontend:
	cd frontend && npm run dev

dev:
	@sh -c '$(PYTHON) -m uvicorn finagent.api.main:app --host 127.0.0.1 --port 8000 & api_pid=$$!; (cd frontend && npm run dev) & frontend_pid=$$!; trap "kill $$api_pid $$frontend_pid 2>/dev/null" INT TERM EXIT; wait $$api_pid $$frontend_pid'

demo:
	$(PYTHON) scripts/seed_demo.py
	$(MAKE) dev
