#!/usr/bin/env bash
set -euo pipefail
repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

if (($# != 1)); then
  echo "usage: $0 {e1|e2-e3|e4|e5|e6|e7|all}" >&2
  exit 2
fi

exec python3 scripts/failover/orchestrate.py "$1"
