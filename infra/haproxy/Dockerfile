FROM haproxy:3.0-bookworm
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY infra/haproxy/haproxy.cfg /usr/local/etc/haproxy/haproxy.cfg
USER haproxy
