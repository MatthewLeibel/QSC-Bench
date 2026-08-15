#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ENV_DIR=${QSC_BENCH_VENV:-"$PROJECT_DIR/.venv"}
PYTHON_BIN=${QSC_BENCH_PYTHON:-}

if [ ! -x "$ENV_DIR/bin/python" ]; then
  if [ -z "$PYTHON_BIN" ]; then
    if command -v python3.13 >/dev/null 2>&1; then
      PYTHON_BIN=python3.13
    elif command -v python3.12 >/dev/null 2>&1; then
      PYTHON_BIN=python3.12
    else
      echo "QSC-Bench requires Python 3.12 or 3.13; set QSC_BENCH_PYTHON." >&2
      exit 2
    fi
  fi
  "$PYTHON_BIN" -m venv "$ENV_DIR"
fi

"$ENV_DIR/bin/python" -m pip install --no-cache-dir -r "$PROJECT_DIR/requirements-core.lock"
"$ENV_DIR/bin/python" -m pip install --no-cache-dir --no-deps -e "$PROJECT_DIR"
"$ENV_DIR/bin/python" -m unittest discover -s "$PROJECT_DIR/tests" -v

echo "QSC-Bench core environment is ready at $ENV_DIR"
echo "Metriq Gym is optional for the draft adapter; see reports/METRIQ_INTEGRATION.md."
