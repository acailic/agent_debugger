#!/bin/bash
# Dead code detection - run weekly or on demand
echo "=== Python dead code ==="
python3 -m vulture agent_debugger_sdk/ api/ storage/ collector/ auth/ redaction/ \
  --min-confidence 80 \
  --exclude "*__pycache__*" \
  --exclude "*.venv*" \
  --exclude "*/tests/*" \
  --exclude "*/examples/*" 2>&1 | head -50
echo ""
echo "=== Run with: bash scripts/check_dead_code.sh ==="
