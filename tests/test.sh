#!/bin/bash
# Run all human-guard tests
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$REPO_DIR/.venv"
FAILED=0

echo ""
echo "human-guard test suite"
echo "======================"

# 1. Unit tests — Python (if available)
if command -v python3 &>/dev/null; then
  # Ensure pytest is available — create venv if needed
  PYTHON="python3"
  if ! python3 -c "import pytest" 2>/dev/null; then
    if [ ! -d "$VENV_DIR" ]; then
      echo ""
      echo "→ Creating venv and installing pytest..."
      python3 -m venv "$VENV_DIR"
    fi
    "$VENV_DIR/bin/pip" install -q pytest 2>/dev/null
    PYTHON="$VENV_DIR/bin/python"
  fi

  if "$PYTHON" -c "import pytest" 2>/dev/null; then
    echo ""
    echo "→ Python unit tests"
    "$PYTHON" -m pytest "$SCRIPT_DIR/test_guard.py" -v || FAILED=1
  else
    echo ""
    echo "→ Python unit tests (SKIPPED — pytest install failed)"
  fi
else
  echo ""
  echo "→ Python unit tests (SKIPPED — python3 not found)"
fi

# 2. Unit tests — Node (if available)
if command -v node &>/dev/null; then
  echo ""
  echo "→ Node unit tests"
  node --test "$SCRIPT_DIR/test_guard.mjs" || FAILED=1
else
  echo ""
  echo "→ Node unit tests (SKIPPED — node not found)"
fi

# 3. E2E tests (bash — always run)
echo ""
echo "→ E2E tests"
bash "$SCRIPT_DIR/test_install.sh" || FAILED=1

echo ""
echo "======================"
if [ $FAILED -eq 0 ]; then
  echo "All test suites passed."
else
  echo "Some test suites failed."
fi
echo ""
exit $FAILED
