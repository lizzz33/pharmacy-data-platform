#!/usr/bin/env python3
"""Print Patroni topology from the live REST API."""

import json
import urllib.request


def main():
    last_error = None
    for host in ("postgres1", "postgres2", "postgres3"):
        try:
            with urllib.request.urlopen(f"http://{host}:8008/cluster", timeout=3) as response:
                cluster = json.load(response)
            break
        except Exception as error:
            last_error = error
    else:
        raise SystemExit(f"Patroni API unavailable: {type(last_error).__name__}")
    print(json.dumps(cluster, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
