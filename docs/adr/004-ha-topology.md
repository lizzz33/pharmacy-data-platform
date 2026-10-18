# ADR 004: учебный HA-кластер и исполнение миграций

**Статус:** принято и проверено на локальном HA-стенде.

## Контекст

Базовая часть HW1 требует physical replica и PgBouncer. Полная основная часть — Patroni + etcd + HAProxy на трёх PostgreSQL узлах.

При этом migrations должны применяться один раз на leader, а не независимо на каждом узле.

## Рассмотренные варианты

1. **Сначала ручной primary/standby, потом отдельно Patroni.** Отвергнуто: два разных bootstrap и два разных способа маршрутизации увеличивают объём поддержки.
2. **Запускать migrations через docker-entrypoint-initdb.d на каждом PostgreSQL.** Отвергнуто: initdb контролирует Patroni, а migrations должны выполняться на leader.
3. **Один etcd.** Отвергнуто для итогового стенда: нет quorum и нельзя показать устойчивость DCS к отказу одного узла.
4. **Сразу Patroni + 3 etcd + HAProxy + PgBouncer.** Выбрано.

## Выбор

Используем:

- 3 PostgreSQL 16 под Patroni;
- 3 etcd;
- HAProxy RW/RO;
- PgBouncer RW/RO;
- отдельный `db-init` для migrations;
- managed replication slots;
- async replication по умолчанию.

`db-init` применяет нумерованные migrations только на leader и хранит SHA-256 уже применённых файлов.

PgBouncer работает в session mode, потому что официальный checker использует session-level SET.

## Цена выбора

Стенд сложнее и тяжелее простого single-Postgres варианта.

Асинхронная репликация допускает небольшой риск потери последних подтверждённых транзакций при аварии leader.

HAProxy и PgBouncer в учебном варианте сами не дублируются, а все контейнеры живут на одном физическом хосте.

## Валидация

`scripts/wait_ready.sh` подтвердил 3 Patroni member, корректные RW/RO routes, contract views и догоняние обеих replicas.

Официальный checker подтверждает replica/PgBouncer и CDC. HA проходит 5/6 автоматических проверок; единственный красный пункт связан с тем, что checker требует `state=running` для всех members, а Patroni возвращает здоровые replicas как `state=streaming`.
