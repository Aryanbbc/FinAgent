# FinAgent architecture

FinAgent is a local-only, layered historical-research application. The boundary between layers is intentional: UI/API code reads or invokes validated orchestration, while calculation and persistence remain in typed Python modules.

```mermaid
flowchart TD
    source[Historical CSV / historical provider] --> data[Normalize, validate, cache, immutable revision]
    data --> features[Causal feature pipeline]
    features --> regime[Rule-based market regime detector]
    features --> direct[Direct baseline strategy]
    regime --> agents[Technical → Regime → Strategy → Risk]
    direct --> engine[Cost-aware deterministic backtest]
    agents --> engine
    engine --> evidence[Metrics + benchmark + critique + memory]
    evidence --> validation[Explicit multi-asset validation]
    validation --> export[Markdown, CSV, SVG, JSON exports]
    export --> database[(SQLite local / PostgreSQL production research evidence)]
    database --> api[FastAPI]
    api --> ui[Next.js / CLI / Streamlit debug]
```

`finagent/runner.py` remains the compatible V0.1–V0.4 experiment entry point. `finagent/validation/` and `finagent/learning/` are opt-in and must be invoked explicitly. `finagent/services/research_service.py` is the thin orchestration boundary for FastAPI; routes do not directly calculate research results.

The persistence abstraction owns experiments, trades, metrics, regimes, agent records, critiques, memory, candidate history, validation evidence, manifests, and data revisions. SQLite remains the local backend with WAL, integrity checks, and explicit backups; PostgreSQL is the production backend with the same repository interfaces and versioned startup schema initialization. Atomic context-managed writes and foreign keys apply to both. The dataset registry never silently replaces a content revision and persists canonical OHLCV rows for production-safe retrieval.

The Next.js app never reads a database directly. Its typed client consumes only FastAPI responses and presents persisted data, bounded controls, loading/error/empty states, and clear historical-research labels. The V1.0 release exporter reads only persisted validation evidence and produces a report, CSV tables, a dependency-free SVG chart, and a JSON record; it does not rerun an experiment.

## Safety boundaries

- All features and regimes are causal; no future observations are used in a decision.
- `agents.enabled: false` keeps the direct V0.1/V0.2 strategy path available.
- Critic and improvement outputs are evidence and configuration records, never autonomous code changes.
- APIs remain local and only call existing local simulations.
- There are no accounts, credentials, webhooks, broker calls, live feeds, paper trading, or order execution.
