"""Connection defaults shared by infrastructure helpers (not domain code)."""
import os
import time

import psycopg2

SERVICES = ("crm", "catalog", "wms", "pos")


def connect(database="postgres", *, user="postgres", route="rw", pooled=False):
    password_key = {"postgres": "POSTGRES_PASSWORD", "app": "APP_PASSWORD", "checker": "CHECKER_PASSWORD"}[user]
    password = os.environ.get(password_key, user)
    host = f"pgbouncer-{route}" if pooled else "haproxy"
    port = 6432 if pooled else (5000 if route == "rw" else 5001)
    return psycopg2.connect(host=host, port=port, dbname=database, user=user,
                            password=password, connect_timeout=3,
                            application_name="hw01-infra")


def wait_for_leader(timeout=300):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            conn = connect()
            conn.autocommit = True
            with conn.cursor() as cur:
                cur.execute("SELECT NOT pg_is_in_recovery()")
                if cur.fetchone()[0]:
                    return conn
            conn.close()
        except psycopg2.Error:
            pass
        time.sleep(2)
    raise TimeoutError("leader is not reachable through haproxy:5000")
