# FinAgent implementation guardrails

This repository is currently at **V0.3: Quantitative Research Engine + Rule-Based Regimes + Decision Agents**.

- Keep the platform a local historical-data research and simulation tool.
- Preserve reproducibility, no-look-ahead-bias safeguards, configurable costs, and deterministic tests.
- Keep regime detection causal, rule-based, and typed. V0.3 agents must remain deterministic, structured, auditable, and free from future observations.
- Preserve `agents.enabled: false` as the direct V0.1/V0.2-compatible execution path.
- Do not add LLMs, reinforcement learning, sentiment analysis, strategy optimization, self-improvement, or live/paper trading integrations in V0.3.
- Do not add real-money execution or commit credentials. `LIVE_TRADING_ENABLED` must remain false.
- Prefer small, modular, configuration-driven Python components and run relevant pytest tests after changes.
