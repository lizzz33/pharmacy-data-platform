#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
exec docker compose run --rm -T --no-deps tools python scripts/infra/wait_ready.py "$@"
