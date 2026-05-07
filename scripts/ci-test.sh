#!/usr/bin/env bash
# Run the full pytest suite.
set -euo pipefail

echo "=== Installing test dependencies ==="
pip install -r requirements-dev.txt -q

echo ""
echo "=== Running tests ==="
pytest tests/ -v --tb=short

echo ""
echo "Tests passed."
