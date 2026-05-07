#!/usr/bin/env bash
# Run mcp-agent locally. Loads .env automatically.
# Usage:
#   ./scripts/run.sh                          # check NuGet versions
#   ./scripts/run.sh analyze                  # analyze pending releases
#   ./scripts/run.sh analyze --product zip    # specific product
#   ./scripts/run.sh upgrade --repos-dir ...  # upgrade local repos
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Load .env if present
if [ -f .env ]; then
  set -o allexport
  source .env
  set +o allexport
fi

COMMAND="${1:-check}"
shift || true

case "$COMMAND" in
  check)
    python scripts/check_nuget.py "$@"
    ;;
  analyze)
    python scripts/analyze_release_aspose.py "$@"
    ;;
  merge)
    python scripts/merge_dependabot_aspose.py "$@"
    ;;
  upgrade)
    python scripts/upgrade_product.py "$@"
    ;;
  new)
    python scripts/analyze_new_product_aspose.py "$@"
    ;;
  scaffold)
    python scripts/new_product.py "$@"
    ;;
  test)
    bash scripts/ci-test.sh
    ;;
  *)
    echo "Usage: $0 [check|analyze|merge|upgrade|new|scaffold|test] [args...]"
    exit 1
    ;;
esac
