# FinAgent implementation guardrails

This repository is currently at **V0.1: Quantitative Research Engine**.

- Keep the platform a local historical-data research and simulation tool.
- Preserve reproducibility, no-look-ahead-bias safeguards, configurable costs, and deterministic tests.
- Do not add AI/LLM agents, reinforcement learning, sentiment analysis, regime detection, or live/paper trading integrations in V0.1.
- Do not add real-money execution or commit credentials. `LIVE_TRADING_ENABLED` must remain false.
- Prefer small, modular, configuration-driven Python components and run relevant pytest tests after changes.
