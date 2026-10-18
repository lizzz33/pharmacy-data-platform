# Pharmacy data platform — HW1

Командный проект: четыре PostgreSQL-источника аптечной сети и учебный HA-стенд.

Участники: Кауров Александр, Каневский Дмитрий, Бичурина Елизавета, Ляхов Артем.

## Статус

Основной HA-стенд собран и проверен локально.

Официальный checker подтверждает:

- contract, keys, volume, C01–C23, X01–X10;
- I1–I12 + P1/P2;
- async replica + PgBouncer;
- CDC automated checks;
- realism 5/5.

HA проходит 5/6 автоматических проверок. Единственный красный пункт связан с тем,
что checker требует `state=running` для всех Patroni members, тогда как здоровые
replicas возвращаются Patroni как `state=streaming`.

Подробности: [docs/infra/checker-compatibility.md](docs/infra/checker-compatibility.md).

## Быстрый запуск

Рекомендуемый путь — полностью через Docker:

```bash
docker compose up -d --build
./scripts/wait_ready.sh
./scripts/seed.sh --seed 42
./scripts/check.sh -v
```

На хосте нужны только Docker, Docker Compose и shell. Python/uv для основного
сценария не требуются: checker и generator запускаются внутри контейнера `tools`.

Для JSON-отчёта:

```bash
./scripts/check.sh --json /reports/hw01-full.json -v
```

Остановить стенд без удаления volumes:

```bash
docker compose down
```

## Структура репозитория

```text
migrations/         SQL migrations четырёх source databases
infra/              Patroni, HAProxy, PgBouncer и tools images
scripts/            shell entrypoints и infra orchestration
src/pharmacy_dwh/   детерминированный генератор данных
tests/              invariant tests и contract fixtures
docs/               итоговая документация HW1
notes/              рабочие design notes и open questions
hws_descriptions/   исходные материалы HW1 и официальный checker
reports/            generated checker reports
```

Что делает каждый script: [scripts/README.md](scripts/README.md).

## Два docker-compose

`docker-compose.yml` — основной HA/submission-стенд:

- 3 PostgreSQL под Patroni;
- 3 etcd;
- HAProxy;
- PgBouncer RW/RO;
- automatic bootstrap/migrations;
- tools container.

`docker-compose.dev.yml` — упрощённый single-Postgres dev-стенд. Он использовался
для ранней отладки schema/contract/seed без HA и сейчас нужен только как быстрый
fallback.

## Submission manifests

- `hw01_submission.yaml` — checker запускается **с хоста**, DSN через `localhost`;
- `hw01_submission.container.yaml` — checker запускается **в Docker network**;
  именно его использует `./scripts/check.sh`;
- `hw01_submission.dev.yaml` — только для упрощённого dev-стенда.

Для обычной проверки ничего выбирать не нужно:

```text
./scripts/check.sh
    -> hw01_submission.container.yaml
```

Альтернативно checker можно запустить с хоста:

```bash
uv sync
uv run python hws_descriptions/hw1/hw01_check.py \
  --submission hw01_submission.yaml \
  -v
```

## Бонусы

### +1: реалистичные данные

Бонус за реалистичность данных уже получен автоматически: официальный checker
показывает `realism 5/5`.

Генератор проходит все проверяемые признаки реалистичности:

- недельная сезонность продаж;
- long-tail по SKU;
- неравномерность продаж по аптекам;
- доля покупок без карты в допустимом диапазоне;
- доля возвратов в допустимом диапазоне.

То есть этот бонус подтверждён самим checker и не требует отдельной ручной проверки.

### +1: журнал отказоустойчивости

Бонусный журнал Э1–Э7 полностью выполнен на реальном HA-стенде.

Основной документ:

- [docs/failover_journal.md](docs/failover_journal.md) — команды, измеренные RTO/TPS/latency, raw excerpts и выводы.

Сырые доказательства:

- [reports/failover/](reports/failover/) — JSONL write-loop, summaries, Patroni/etcd logs, topology snapshots и exact commands;
- [reports/failover/README.md](reports/failover/README.md) — какие прогоны считаются валидными и какие диагностические прогоны были отвергнуты.

Ключевые измерения:

- emergency failover RTO: 27.579 с;
- planned switchover RTO: 3.419 с;
- возвращённый узел снова стал streaming-replica через 23.116 с;
- PgBouncer обслужил 250/250 клиентов, тогда как прямой PostgreSQL дал 25 ошибок из 250.

### +1: кворумный etcd

Стенд использует 3 etcd member, quorum = 2/3. Отдельная демонстрация выполнена в эксперименте Э6.

Где смотреть доказательство:

- [docs/failover_journal.md — Э6](docs/failover_journal.md) — итог и интерпретация;
- `reports/failover/e6-one-etcd-down/` — один etcd недоступен, quorum сохраняется, запись продолжается;
- `reports/failover/e6-quorum-loss/` — доступны только 1 из 3 etcd, quorum теряется;
- `reports/failover/e6-etcd-quorum/` — служебные проверки и итоговое восстановление.

Фактически продемонстрировано:

```text
3/3 etcd healthy
   ↓ stop 1
2/3 available -> quorum сохраняется -> 728/728 writes succeed
   ↓ restore
3/3 healthy
   ↓ stop 2
1/3 available -> quorum lost -> Patroni demotes leader -> read-only
   ↓ restore
3/3 healthy, 1 leader + 2 streaming replicas
```

После экспериментов `./scripts/wait_ready.sh` снова проходит, `synchronous_mode=false` восстановлен.

## Документация для проверки

Основные submission-документы лежат в `docs/`:

- [ERD четырёх источников](docs/erd/) — физическая модель, PK/FK и cross-service BK;
- [ADR](docs/adr/) — архитектурные решения и отвергнутые альтернативы;
- [DWH mapping](docs/dwh_mapping.md) — карта склейки источников для следующих ДЗ;
- [Failover journal](docs/failover_journal.md) — выполненные Э1–Э7 с реальными измерениями;
- [Failover evidence](reports/failover/) — raw logs, write events, summaries и доказательство quorum etcd;
- [Sources](docs/sources.md) — внешние источники и документация;
- [Infrastructure notes](docs/infra/README.md) — состав стенда, порты и детали запуска.

Рабочие проектные заметки и незакрытые вопросы:

- [notes/hw1/plan.md](notes/hw1/plan.md)
- [notes/hw1/open_questions.md](notes/hw1/open_questions.md)

## Connection strings

Через PgBouncer:

```text
RW checker: postgresql://checker:checker@localhost:6432/<service>_service_db
RO checker: postgresql://checker:checker@localhost:6433/<service>_service_db
RW app:     postgresql://app:app@localhost:6432/<service>_service_db
```

HAProxy напрямую:

```text
RW admin:   postgresql://postgres:postgres@localhost:5000/<service>_service_db
RO:         postgresql://postgres:postgres@localhost:5001/<service>_service_db
```

Service names:

```text
crm
catalog
pos
wms
```

Например: `pos_service_db`.

## Если добавили новую migration

Не переписывайте уже применённые migrations. Добавляйте новый нумерованный SQL-файл
и запускайте:

```bash
./scripts/migrate.sh
```

## Что ещё требует ручной проверки

Автоматический checker не закрывает всё задание. Перед сдачей нужно глазами проверить:

- читаемость ERD;
- минимум 5 ADR с реальными trade-off;
- полноту `docs/dwh_mapping.md`;
- корректность `README.md` и connection strings;
- `docs/sources.md`;
- сопоставить итоговые числа bonus-экспериментов с raw evidence из
  `reports/failover/` перед сдачей.

Известные предметные edge cases, которые не блокируют текущий checker, собраны в
[notes/hw1/open_questions.md](notes/hw1/open_questions.md).
