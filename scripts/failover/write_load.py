#!/usr/bin/env python3
"""Generate measured single-row transactions and preserve every observation."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import time

import psycopg2


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(len(ordered) * fraction + 0.999999) - 1))
    return round(ordered[index], 3)


def connect(host, port):
    return psycopg2.connect(
        host=host,
        port=port,
        dbname="pos_service_db",
        user="app",
        password=os.environ.get("APP_PASSWORD", "app"),
        connect_timeout=2,
        application_name="hw01-failover-write-load",
    )


def summarize(run_id, started_at, elapsed, events, missing):
    successes = [event for event in events if event["status"] == "ok"]
    failures = [event for event in events if event["status"] == "error"]
    latencies = [event["latency_ms"] for event in successes]
    first_failure_index = next((i for i, event in enumerate(events) if event["status"] == "error"), None)
    last_before = None
    first_after = None
    if first_failure_index is not None:
        last_before = next(
            (event for event in reversed(events[:first_failure_index]) if event["status"] == "ok"), None
        )
        first_after = next(
            (event for event in events[first_failure_index + 1 :] if event["status"] == "ok"), None
        )
    rto = None
    if last_before and first_after:
        rto = round(first_after["completed_monotonic_s"] - last_before["completed_monotonic_s"], 3)
    return {
        "run_id": run_id,
        "started_at": started_at,
        "elapsed_s": round(elapsed, 3),
        "successful_transactions": len(successes),
        "failed_transactions": len(failures),
        "tps": round(len(successes) / elapsed, 3) if elapsed else 0,
        "latency_ms_median": round(statistics.median(latencies), 3) if latencies else None,
        "latency_ms_p95": percentile(latencies, 0.95),
        "first_error": failures[0]["error"] if failures else None,
        "last_success_before_failure": last_before["completed_at"] if last_before else None,
        "first_success_after_failure": first_after["completed_at"] if first_after else None,
        "rto_s": rto,
        "acknowledged_rows_missing": missing,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--interval", type=float, default=0.02)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--events", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--host", default="pgbouncer-rw")
    parser.add_argument("--port", type=int, default=6432)
    args = parser.parse_args()

    args.events.parent.mkdir(parents=True, exist_ok=True)
    started_wall = utc_now()
    started = time.monotonic()
    deadline = started + args.duration
    connection = None
    events = []
    sequence_no = 0

    with args.events.open("w", encoding="utf-8") as output:
        while time.monotonic() < deadline:
            sequence_no += 1
            attempt_start = time.monotonic()
            event = {
                "sequence_no": sequence_no,
                "timestamp": utc_now(),
                "monotonic_s": round(attempt_start - started, 6),
            }
            try:
                if connection is None or connection.closed:
                    connection = connect(args.host, args.port)
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO failover_bench.write_probe
                            (run_id, sequence_no, client_started_at)
                        VALUES (%s, %s, clock_timestamp())
                        RETURNING committed_at::text
                        """,
                        (args.run_id, sequence_no),
                    )
                    event["database_committed_at"] = cursor.fetchone()[0]
                connection.commit()
                event["status"] = "ok"
                event["latency_ms"] = round((time.monotonic() - attempt_start) * 1000, 3)
            except Exception as error:
                event["status"] = "error"
                event["error"] = f"{type(error).__name__}: {str(error).splitlines()[0]}"[:300]
                if connection is not None:
                    try:
                        connection.close()
                    except Exception:
                        pass
                connection = None
            event["completed_at"] = utc_now()
            event["completed_monotonic_s"] = round(time.monotonic() - started, 6)
            if "latency_ms" not in event:
                event["latency_ms"] = round((time.monotonic() - attempt_start) * 1000, 3)
            events.append(event)
            output.write(json.dumps(event, ensure_ascii=False) + "\n")
            output.flush()
            remaining = args.interval - (time.monotonic() - attempt_start)
            if remaining > 0:
                time.sleep(remaining)

    if connection is not None:
        connection.close()
    elapsed = time.monotonic() - started
    missing = None
    acknowledged = [event["sequence_no"] for event in events if event["status"] == "ok"]
    try:
        verification = connect(args.host, args.port)
        with verification.cursor() as cursor:
            cursor.execute(
                "SELECT sequence_no FROM failover_bench.write_probe WHERE run_id=%s ORDER BY sequence_no",
                (args.run_id,),
            )
            stored = {row[0] for row in cursor.fetchall()}
        verification.close()
        missing = sorted(set(acknowledged) - stored)
    except Exception:
        missing = "verification route unavailable at end of run"

    summary = summarize(args.run_id, started_wall, elapsed, events, missing)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
