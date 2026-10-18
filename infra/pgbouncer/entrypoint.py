"""Render local pooler config; never print credentials."""
import os
from pathlib import Path

mode = os.environ.get("POOL_ROUTE", "rw")
if mode not in {"rw", "ro"}:
    raise SystemExit("POOL_ROUTE must be rw or ro")
backend_port = 5000 if mode == "rw" else 5001
run = Path("/run/pgbouncer")
run.mkdir(mode=0o700, exist_ok=True)
(run / "pgbouncer.pid").unlink(missing_ok=True)


def quoted(value: str) -> str:
    if any(c in value for c in "\r\n\x00"):
        raise ValueError("credential contains a control character")
    return '"' + value.replace('"', '""') + '"'


users = {"checker": os.environ["CHECKER_PASSWORD"]}
if mode == "rw":
    users["app"] = os.environ["APP_PASSWORD"]
userfile = run / "userlist.txt"
userfile.write_text("".join(f'{quoted(name)} {quoted(password)}\n' for name, password in users.items()))
userfile.chmod(0o600)
databases = "\n".join(
    f"{s}_service_db = host=haproxy port={backend_port} dbname={s}_service_db"
    for s in ("crm", "catalog", "pos", "wms")
)
config = f"""[databases]
{databases}

[pgbouncer]
listen_addr = 0.0.0.0
listen_port = 6432
unix_socket_dir = /run/pgbouncer
pidfile = /run/pgbouncer/pgbouncer.pid
auth_type = scram-sha-256
auth_file = /run/pgbouncer/userlist.txt
pool_mode = session
max_client_conn = 1000
default_pool_size = 10
reserve_pool_size = 2
reserve_pool_timeout = 3
max_db_connections = 30
server_reset_query = DISCARD ALL
server_check_query = SELECT 1
server_check_delay = 5
server_connect_timeout = 5
server_login_retry = 1
server_idle_timeout = 60
server_lifetime = 600
query_wait_timeout = 120
ignore_startup_parameters = extra_float_digits
stats_users = checker
log_connections = 1
log_disconnections = 1
"""
path = run / "pgbouncer.ini"
path.write_text(config)
path.chmod(0o600)
os.execvp("pgbouncer", ["pgbouncer", str(path)])
