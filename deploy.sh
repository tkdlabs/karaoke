#!/bin/bash
# deploy.sh — thin wrapper around deploy.py
# See deploy.py for usage and environment variable documentation.
#
# Runs via "uv run --project workflows/deployment" so that deploy_lib's
# declared dependencies (jinja2, etc.) are available without any manual
# pip install step.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_LIB_DIR="$SCRIPT_DIR/../../workflows/deployment"
exec uv run --project "$DEPLOY_LIB_DIR" python3 "$SCRIPT_DIR/deploy.py" "$@"
