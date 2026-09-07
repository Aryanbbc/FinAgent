# Viva guide

## One-minute overview

FinAgent is a deterministic historical-research platform. CSV/provider data is normalized and quality-checked, features and regimes are causal, strategies are simulated with costs, and every experiment is persisted with a reproducibility manifest. V1.0 adds a fixed release evaluation and portable evidence exports.

## Questions to expect

| Question | Concise answer |
| --- | --- |
| How is look-ahead bias avoided? | Features, regimes, and walk-forward splits use observations available at each timestamp; leakage tests check chronology, feature equivalence, and held-out windows. |
| What do the agents do? | Typed rule-based Technical, Regime, Strategy, and Risk components produce auditable reason codes. They are not LLMs. |
| Is it self-improving? | Only an explicit configuration-bounded V0.5 workflow can evaluate a candidate out of sample. It cannot rewrite code or trade. |
| Why include critic/memory? | They explain completed experiments and retrieve evidence; they do not affect an already simulated path. |
| What does robustness prove? | Nothing about future returns. It is a transparent aggregate diagnostic over the configured historical checks. |

Demonstrate `config/final_validation.yaml`, `reports/v1.0/research_report.md`, the Validation page, then the System capability boundary. State the limitations in [RESULTS.md](RESULTS.md).
