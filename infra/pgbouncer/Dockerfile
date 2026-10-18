FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends pgbouncer postgresql-client python3 ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && install -d -m 0700 -o postgres -g postgres /run/pgbouncer
COPY infra/pgbouncer/entrypoint.py /usr/local/bin/pgbouncer-entrypoint.py
USER postgres
ENTRYPOINT ["python3", "/usr/local/bin/pgbouncer-entrypoint.py"]
