#!/bin/bash
# deploy.sh — thin wrapper around deploy.py
# See deploy.py for usage and environment variable documentation.
exec python3 "$(dirname "$0")/deploy.py" "$@"
