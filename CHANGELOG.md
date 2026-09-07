# Changelog

All notable changes to FinAgent are documented here.

## 1.1.0 — Live Market Intelligence Mode

- Added an opt-in, backend-keyed Twelve Data recent-OHLCV polling adapter with bounded exponential backoff and explicit feed states.
- Added a rolling live OHLCV buffer that reuses the causal feature pipeline, regime detector, and deterministic Technical → Regime → Strategy → Risk chain.
- Added separate bounded persistence for live research signals, regime observations, and feed events; historical experiments and trades remain unchanged.
- Added typed `/api/live/*` routes, a monitoring-only `/live` terminal, and a credential-safe live smoke command.
- Added XNYS-calendar-aware U.S. equity market states that keep provider health separate from pre-market, regular, after-hours, closed, and delayed feed status.
- Preserved the V1.0 historical release suite and prohibited order creation, paper trading, brokerage connectivity, LLMs, reinforcement learning, and sentiment analysis.

## 1.0.0 — Final Research Release

- Added a fixed, reproducible two-fixture final evaluation configuration and explicit final benchmark labels.
- Added portable release evidence exports: Markdown report, CSV tables, SVG benchmark chart, and JSON validation record.
- Added final-results, demo, viva, demo-script, portfolio, and release-checklist documentation.
- Added a Mermaid architecture diagram, explicit reproducibility commands, version alignment, and release hygiene checks.
- Preserved the V0.1–V0.9 deterministic historical-research behaviour and safety boundaries.

## 0.9.0 — Production Polish

- Added API consistency, operational checks, demo tooling, production CORS/deployment wiring, and research UI polish.

## 0.1.0–0.8.0

- Added the deterministic backtesting, regime, agent, critic/memory, controlled improvement, validation, API/UI, and historical-data foundations described in the README version history.
