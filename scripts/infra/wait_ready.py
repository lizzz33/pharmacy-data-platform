"""Read-only readiness: topology, roles, contract views and replay position."""
import argparse
import json
from pathlib import Path
import time
import urllib.request

from psycopg2 import sql
import yaml

from common import SERVICES, connect

ROOT = Path(__file__).resolve().parents[2]


def probe():
    contract = yaml.safe_load((ROOT / "hws_descriptions/hw1/hw01_contract.yaml").read_text())
    with urllib.request.urlopen("http://postgres1:8008/cluster", timeout=3) as response:
        members = json.load(response).get("members", [])
    if len(members) != 3 or sum(m.get("role") == "leader" for m in members) != 1:
        raise RuntimeError("expected 3 members and exactly one leader")
    if any(m.get("state") not in {"running", "streaming"} for m in members):
        raise RuntimeError("a PostgreSQL member is not running")
    for service in SERVICES:
        database = f"{service}_service_db"
        for route in ("rw", "ro"):
            conn = connect(database, user="checker", route=route, pooled=True)
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT pg_is_in_recovery()")
                    if cur.fetchone()[0] != (route == "ro"):
                        raise RuntimeError(f"wrong {route} route for {service}")
                    for view in contract["services"][service]["views"]:
                        cur.execute(sql.SQL("SELECT * FROM contract.{} LIMIT 0").format(sql.Identifier(view)))
            finally:
                conn.close()
    admin = connect()
    try:
        with admin.cursor() as cur:
            cur.execute("SELECT pg_current_wal_lsn()::text")
            lsn = cur.fetchone()[0]
    finally:
        admin.close()
    for member in members:
        if member["role"] == "leader":
            continue
        # Check BOTH replicas, not only whichever HAProxy currently selects.
        import os
        import psycopg2
        replica = psycopg2.connect(host=member["name"], port=5432, dbname="pos_service_db",
                                  user="checker", password=os.environ.get("CHECKER_PASSWORD", "checker"),
                                  connect_timeout=3)
        try:
            with replica.cursor() as cur:
                cur.execute("SELECT pg_last_wal_replay_lsn() >= %s::pg_lsn", (lsn,))
                if cur.fetchone()[0] is not True:
                    raise RuntimeError(f"{member['name']} has not replayed schema changes yet")
        finally:
            replica.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    deadline = time.monotonic() + args.timeout
    last = "not checked"
    while time.monotonic() < deadline:
        try:
            probe()
            print("ready: 3 PostgreSQL members, RW/RO pools, 4 contracts, both replicas caught up")
            return
        except Exception as error:
            # Do not print DSNs/passwords from connection exceptions.
            last = type(error).__name__
        time.sleep(2)
    raise SystemExit(f"readiness timeout ({last}); inspect docker compose ps and db-init logs")


if __name__ == "__main__":
    main()
