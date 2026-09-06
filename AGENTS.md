# FinAgent implementation guardrails

This repository is currently at **V0.2: Quantitative Research Engine + Rule-Based Market Regimes**.

- Keep the platform a local historical-data research and simulation tool.
- Preserve reproducibility, no-look-ahead-bias safeguards, configurable costs, and deterministic tests.
- Keep regime detection causal, rule-based, typed, and separate from strategy execution. It must not use future observations or alter portfolio decisions in V0.2.
- Do not add AI/LLM agents, reinforcement learning, sentiment analysis, strategy optimization, self-improvement, or live/paper trading integrations in V0.2.
- Do not add real-money execution or commit credentials. `LIVE_TRADING_ENABLED` must remain false.
- Prefer small, modular, configuration-driven Python components and run relevant pytest tests after changes.
