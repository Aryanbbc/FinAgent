# FinAgent implementation guardrails

This repository is currently at **V0.8: Data & Market Intelligence Layer**.

- Keep the platform a local historical-data research and simulation tool.
- Preserve reproducibility, no-look-ahead-bias safeguards, configurable costs, and deterministic tests.
- Keep regime detection causal, rule-based, and typed. V0.3 agents and the V0.4 critic must remain deterministic, structured, auditable, and free from future observations.
- Preserve `agents.enabled: false` as the direct V0.1/V0.2-compatible execution path.
- Critique and experiment memory are post-experiment evidence. V0.5 may use them only in the explicit, configuration-gated improvement workflow.
- V0.5 candidates must be deterministic, configuration-only, generated from an allowlist, evaluated out-of-sample chronologically, and promoted only through the configured risk-aware gate.
- V0.6 research validation is explicit and opt-in. Multi-asset, walk-forward, sensitivity, bootstrap, ablation, benchmark, and robustness results are historical research evidence, never trading instructions.
- Preserve single-asset configurations and keep V0.6 promotion robustness checks disabled unless explicitly configured.
- V0.7 API routes may expose local read-only research data and invoke only existing, validated local simulation workflows. Keep FastAPI routes thin and place orchestration in services.
- V0.7 frontend is a local, read-only/control surface; no live or paper-trading actions, credentials, accounts, or external broker/API calls.
- V0.8 providers are historical-data only. Preserve normalized UTC OHLCV data, immutable dataset revisions, deterministic caching, transparent quality scoring, and conservative missing-data handling.
- Dataset IDs/versions and collections are reproducibility inputs. Do not silently overwrite a dataset revision or let provider metadata change research logic.
- Do not add LLMs, reinforcement learning, sentiment analysis, unrestricted self-improvement, Bayesian/evolutionary optimization, code rewriting, or live/paper trading integrations.
- Do not add real-money execution or commit credentials. `LIVE_TRADING_ENABLED` must remain false.
- Prefer small, modular, configuration-driven Python components and run relevant pytest tests after changes.
