# Demo mode

FinAgent V1.0.0 includes an offline, idempotent demo. It uses only the two bundled CSV fixtures and stores all generated state below `data/demo/finagent_v1_demo.db`; normal research data is untouched. `make demo` starts the API against that database.

```bash
.venv/bin/python scripts/seed_demo.py
make dev
```

The demo seeds immutable dataset revisions, a collection, a causal agent experiment, critique/memory evidence, validation, bounded candidate history, and a Markdown report. The System page shows that sample data is active.

For a clean reseed, remove only the explicitly demo-scoped `data/demo/` directory yourself, then rerun the command. Do not delete a normal research database. Demo output is historical simulation only and never submits an order, opens an account, or uses credentials.
