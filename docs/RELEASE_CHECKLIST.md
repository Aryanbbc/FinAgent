# V1.0.0 release checklist

- [x] Python package, API, health, system response, frontend package, and visible UI identify V1.0.0.
- [x] Final reference configuration uses two bundled immutable CSV fixtures and a separate release SQLite path.
- [x] Fixed final benchmark labels, multi-asset validation, rolling walk-forward, leakage checks, sensitivity, bootstrap intervals, robustness, and ablation are configured.
- [x] Final Markdown, CSV, SVG, and JSON evidence artifacts are committed under `reports/v1.0/`.
- [x] README, architecture, methodology, development, troubleshooting, results, demo, viva, demo script, portfolio, changelog, and deployment docs are present.
- [x] Demo uses bundled offline data and separate demo storage.
- [x] Git-tracked secret scan finds no private-key or common cloud-token marker; `.env` and key material are ignored.
- [x] Backend tests, frontend type check/tests/build, FastAPI health/OpenAPI, CLI reference run, and demo seed have been run for this release.
- [ ] Move or replace the premature `v1.0.0` tag after reviewing this completed V1.0.0 worktree; it currently identifies the V0.9 commit.

Before creating a corrected release tag, rerun the commands in the Verification section of the README and record their output in the release notes. The previous `v1.0.0` tag points to V0.9 and must not be treated as this release artifact.
