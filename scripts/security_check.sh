#!/usr/bin/env bash
# Run optional security scanners without making them application dependencies.
set -uo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
status=0

run_optional() {
  local label="$1"
  shift
  if command -v "$1" >/dev/null 2>&1; then
    echo "==> ${label}"
    "$@" || status=1
  else
    echo "==> ${label}: unavailable (install it to enable this check)"
  fi
}

cd "$root"
run_optional "pip-audit" pip-audit
run_optional "bandit" bandit -r finagent
run_optional "gitleaks history scan" gitleaks detect --source . --log-opts="--all"

if command -v npm >/dev/null 2>&1 && [ -d frontend ]; then
  echo "==> npm audit"
  (cd frontend && npm audit) || status=1
else
  echo "==> npm audit: unavailable"
fi

echo "==> Python tests"
python -m pytest || status=1
if command -v npm >/dev/null 2>&1 && [ -d frontend ]; then
  echo "==> Frontend checks"
  (cd frontend && npm run check && npm test) || status=1
fi
exit "$status"
