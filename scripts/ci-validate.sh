#!/usr/bin/env bash
# Validate all Python scripts compile and start correctly.
set -euo pipefail

echo "=== Syntax check ==="
for f in scripts/*.py; do
  python -m py_compile "$f"
  echo "  OK: $f"
done

echo ""
echo "=== Help flags ==="
python scripts/analyze_release.py --help         > /dev/null
python scripts/analyze_release_aspose.py --help  > /dev/null
python scripts/merge_dependabot.py --help        > /dev/null
python scripts/merge_dependabot_aspose.py --help > /dev/null
python scripts/upgrade_product.py --help         > /dev/null
python scripts/new_product.py --help             > /dev/null
python scripts/analyze_new_product.py --help     > /dev/null
python scripts/analyze_new_product_aspose.py --help > /dev/null
echo "  All --help flags OK"

echo ""
echo "=== docker-compose config ==="
if command -v docker &> /dev/null; then
  docker compose config --quiet && echo "  docker-compose.yml OK"
else
  echo "  Docker not available — skipping compose validation"
fi

echo ""
echo "Validation passed."
