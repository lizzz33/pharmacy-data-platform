FROM postgres:16-bookworm

ARG PATRONI_VERSION=4.1.0
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && python3 -m venv /opt/patroni \
    && /opt/patroni/bin/pip install --no-cache-dir \
       "patroni[etcd3]==${PATRONI_VERSION}" "psycopg2-binary==2.9.13" \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/patroni/bin:${PATH}"
COPY infra/patroni/patroni.yml /etc/patroni/patroni.yml
COPY infra/patroni/entrypoint.sh /usr/local/bin/patroni-entrypoint
RUN chmod 755 /usr/local/bin/patroni-entrypoint \
    && chmod 644 /etc/patroni/patroni.yml

ENTRYPOINT ["/usr/local/bin/patroni-entrypoint"]
CMD ["patroni", "/etc/patroni/patroni.yml"]
