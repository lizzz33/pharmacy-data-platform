"""Create source DBs, apply numbered migrations, configure roles and publications.

Only the db-init service invokes this helper. Domain SQL remains team-owned.
Run again after adding a migration: docker compose run --rm -T db-init
"""
from hashlib import sha256
import os
from pathlib import Path
import re

import psycopg2
from psycopg2 import sql
import yaml

from common import SERVICES, connect, wait_for_leader

ROOT = Path(__file__).resolve().parents[2]


def create_roles_and_databases(conn):
    with conn.cursor() as cur:
        for role, key in (("app", "APP_PASSWORD"), ("checker", "CHECKER_PASSWORD")):
            cur.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE ROLE {} LOGIN").format(sql.Identifier(role)))
            cur.execute(sql.SQL("ALTER ROLE {} WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                                "NOREPLICATION NOBYPASSRLS PASSWORD %s").format(sql.Identifier(role)),
                        (os.environ.get(key, role),))
        # Needed for pg_stat_wal_receiver.status on replicas; no application writes.
        cur.execute("GRANT pg_monitor TO checker")
        for service in SERVICES:
            database = f"{service}_service_db"
            cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database,))
            if cur.fetchone() is None:
                cur.execute(sql.SQL("CREATE DATABASE {} OWNER postgres").format(sql.Identifier(database)))


def migration_body(text):
    """Remove the team's outer transaction so SQL + ledger commit atomically."""
    start = re.match(r"\A\s*BEGIN\s*;", text, re.IGNORECASE)
    end = re.search(r"\bCOMMIT\s*;\s*\Z", text, re.IGNORECASE)
    if bool(start) != bool(end):
        raise ValueError("migration must have both outer BEGIN/COMMIT or neither")
    return text[start.end():end.start()] if start and end else text


def prepare_ledger(conn):
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE SCHEMA IF NOT EXISTS infra;
                CREATE TABLE IF NOT EXISTS infra.schema_migrations (
                    filename text PRIMARY KEY,
                    sha256 text NOT NULL,
                    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
                    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
                );
                CREATE OR REPLACE FUNCTION infra.touch_updated_at()
                RETURNS trigger LANGUAGE plpgsql AS $$
                BEGIN NEW.updated_at := clock_timestamp(); RETURN NEW; END;
                $$;
                DROP TRIGGER IF EXISTS touch_updated_at ON infra.schema_migrations;
                CREATE TRIGGER touch_updated_at BEFORE UPDATE ON infra.schema_migrations
                FOR EACH ROW EXECUTE FUNCTION infra.touch_updated_at();
            """)


def apply_migrations(conn, service):
    paths = sorted((ROOT / "db/migrations" / service).glob("[0-9]*.sql"))
    if not paths:
        raise RuntimeError(f"no migrations for {service}")
    for path in paths:
        text = path.read_text(encoding="utf-8")
        checksum = sha256(text.encode("utf-8")).hexdigest()
        with conn:
            with conn.cursor() as cur:
                cur.execute("SELECT sha256 FROM infra.schema_migrations WHERE filename=%s", (path.name,))
                applied = cur.fetchone()
                if applied:
                    if applied[0] != checksum:
                        raise RuntimeError(f"{service}/{path.name} changed after application; add a new migration")
                    print(f"skip {service}/{path.name}", flush=True)
                    continue
                cur.execute(migration_body(text))
                cur.execute("INSERT INTO infra.schema_migrations(filename, sha256) VALUES (%s,%s)",
                            (path.name, checksum))
        print(f"applied {service}/{path.name}", flush=True)


def configure_access_and_cdc(conn, service):
    with conn:
        with conn.cursor() as cur:
            # Future team migrations are executed as postgres by this runner.
            cur.execute("SELECT nspname FROM pg_namespace WHERE nspname NOT IN "
                        "('pg_catalog','information_schema','contract','infra') AND nspname NOT LIKE 'pg_%'")
            business_schemas = [r[0] for r in cur.fetchall()]
            for schema in business_schemas:
                ident = sql.Identifier(schema)
                cur.execute(sql.SQL("GRANT USAGE ON SCHEMA {} TO app").format(ident))
                cur.execute(sql.SQL("GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA {} TO app").format(ident))
                cur.execute(sql.SQL("GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA {} TO app").format(ident))
                cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA {} "
                                    "GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO app").format(ident))
                cur.execute(sql.SQL("ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA {} "
                                    "GRANT USAGE,SELECT ON SEQUENCES TO app").format(ident))
            cur.execute("GRANT USAGE ON SCHEMA contract TO checker, app")
            cur.execute("GRANT SELECT ON ALL TABLES IN SCHEMA contract TO checker, app")
            cur.execute("ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA contract "
                        "GRANT SELECT ON TABLES TO checker, app")
            if service == "pos":
                # Each checker run gets a new explicit deterministic namespace.
                cur.execute("CREATE SEQUENCE IF NOT EXISTS infra.delta_seed_seq START WITH 1000000000")
                cur.execute("GRANT USAGE ON SCHEMA infra TO app")
                cur.execute("GRANT USAGE,SELECT ON SEQUENCE infra.delta_seed_seq TO app")
            cur.execute("SELECT puballtables FROM pg_publication WHERE pubname='hw01_all_tables'")
            publication = cur.fetchone()
            if publication is None:
                cur.execute("CREATE PUBLICATION hw01_all_tables FOR ALL TABLES")
            elif not publication[0]:
                raise RuntimeError("hw01_all_tables exists but does not publish all tables")
            cur.execute("""
                SELECT n.nspname, c.relname,
                       EXISTS (SELECT 1 FROM pg_constraint k WHERE k.conrelid=c.oid AND k.contype='p'),
                       c.relreplident
                FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
                WHERE c.relkind IN ('r','p') AND n.nspname NOT IN ('pg_catalog','information_schema')
                  AND n.nspname NOT LIKE 'pg_%'
            """)
            for schema, table, has_pk, identity in cur.fetchall():
                if identity == 'n' or (identity == 'd' and not has_pk):
                    mode = sql.SQL("DEFAULT" if has_pk else "FULL")
                    cur.execute(sql.SQL("ALTER TABLE {}.{} REPLICA IDENTITY {}").format(
                        sql.Identifier(schema), sql.Identifier(table), mode))
            # Fail before reporting success if a required view is absent.
            contract = yaml.safe_load((ROOT / "hws_descriptions/hw1/hw01_contract.yaml").read_text())
            for view in contract["services"][service]["views"]:
                cur.execute(sql.SQL("SELECT * FROM contract.{} LIMIT 0").format(sql.Identifier(view)))


def main():
    admin = wait_for_leader()
    try:
        create_roles_and_databases(admin)
    finally:
        admin.close()
    for service in SERVICES:
        conn = connect(f"{service}_service_db")
        try:
            # Session lock survives individual migration transactions.
            with conn.cursor() as cur:
                cur.execute("SELECT pg_advisory_lock(hashtextextended('hw01:migrations',0))")
            conn.commit()
            prepare_ledger(conn)
            apply_migrations(conn, service)
            configure_access_and_cdc(conn, service)
            print(f"ready {service}: schema, grants, publication", flush=True)
        finally:
            conn.close()
    print("db-init completed; data generation is a separate command", flush=True)


if __name__ == "__main__":
    main()
