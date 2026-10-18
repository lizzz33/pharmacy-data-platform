#!/usr/bin/env python3
"""Compare bounded concurrent sessions through PostgreSQL and PgBouncer."""

import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import statistics
import time
import urllib.request

import psycopg2


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))
    return round(ordered[index], 3)


def leader():
    with urllib.request.urlopen("http://postgres1:8008/cluster", timeout=3) as response:
        members = json.load(response)["members"]
    return next(member["name"] for member in members if member["role"] == "leader")


def one_connection(host, port, hold_s):
    start = time.monotonic()
    try:
        connection = psycopg2.connect(
            host=host,
            port=port,
            dbname="pos_service_db",
            user="app",
            password=os.environ.get("APP_PASSWORD", "app"),
            connect_timeout=5,
            application_name="hw01-connection-pressure",
        )
        connected_ms = (time.monotonic() - start) * 1000
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_sleep(%s), pg_backend_pid()", (hold_s,))
            backend_pid = cursor.fetchone()[1]
        connection.close()
        return {"ok": True, "connect_ms": round(connected_ms, 3), "backend_pid": backend_pid}
    except Exception as error:
        return {"ok": False, "error": f"{type(error).__name__}: {str(error).splitlines()[0]}"[:300]}


def run_step(route, concurrency, hold_s):
    if route == "direct":
        host, port = leader(), 5432
    else:
        host, port = "pgbouncer-rw", 6432
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        results = list(executor.map(lambda _: one_connection(host, port, hold_s), range(concurrency)))
    elapsed = time.monotonic() - started
    successes = [result for result in results if result["ok"]]
    errors = [result for result in results if not result["ok"]]
    latencies = [result["connect_ms"] for result in successes]
    return {
        "route": route,
        "concurrency": concurrency,
        "successful_clients": len(successes),
        "failed_clients": len(errors),
        "elapsed_s": round(elapsed, 3),
        "connect_ms_median": round(statistics.median(latencies), 3) if latencies else None,
        "connect_ms_p95": percentile(latencies, 0.95),
        "distinct_backend_pids": len({result["backend_pid"] for result in successes}),
        "first_error": errors[0]["error"] if errors else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--levels", default="50,100,150,200,250")
    parser.add_argument("--hold", type=float, default=0.5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    levels = [int(value) for value in args.levels.split(",")]
    report = []
    for route in ("direct", "pooled"):
        for level in levels:
            result = run_step(route, level, args.hold)
            report.append(result)
            print(json.dumps(result), flush=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
