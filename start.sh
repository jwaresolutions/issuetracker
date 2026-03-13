#!/usr/bin/env bash
# Start the Issue Tracker server
cd "$(dirname "$0")"
source .venv/bin/activate
exec python server.py "$@"
