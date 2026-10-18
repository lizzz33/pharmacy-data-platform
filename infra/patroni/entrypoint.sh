#!/bin/sh
set -eu

# The official PostgreSQL entrypoint is intentionally replaced: Patroni owns initdb.
if [ "$(id -u)" = 0 ]; then
    install -d -m 0700 -o postgres -g postgres /var/lib/postgresql/data/pgdata
    install -d -m 0775 -o postgres -g postgres /var/run/postgresql
    chown postgres:postgres /var/lib/postgresql/data
    exec gosu postgres "$@"
fi
exec "$@"
