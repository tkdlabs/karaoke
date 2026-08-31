#!/bin/bash
# deploy.sh — thin wrapper around the self-contained deploy.py
# See deploy.py for usage and environment variable documentation.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/deploy.py" "$@"