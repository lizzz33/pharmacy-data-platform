# Pharmacy data platform — HW1

Командный проект: четыре PostgreSQL-источника аптечной сети и учебный HA-стенд.

**Текущее состояние инфраструктуры:** файлы подготовлены и статически проверены.
Образы не собирались, контейнеры не запускались, работоспособность и баллы
официального чекера на HA-стенде пока не подтверждены.

## Документация

- [Состав, порты, запуск и параллельная работа](docs/infra/README.md).
- [Замечания команде бизнес-логики и метод проверки](docs/infra/business-review.md).
- [Несовместимость чекера с Patroni streaming](docs/infra/checker-compatibility.md).
- [Внешние источники инфраструктуры](docs/sources.md).
- [Статус проекта и исходные дизайн-заметки](notes/hw1/plan.md).

## Стенд

`docker-compose.yml` описывает три PostgreSQL 16 с Patroni, три etcd,
HAProxy, два PgBouncer, автоматическую инициализацию и контейнер tools.
На каждом PostgreSQL находятся четыре БД:

- `crm_service_db`
- `catalog_service_db`
- `pos_service_db`
- `wms_service_db`

Основные локальные DSN, одинаковые для всех четырёх имён баз:

```text
postgresql://checker:checker@localhost:6432/pos_service_db
postgresql://checker:checker@localhost:6433/pos_service_db
postgresql://app:app@localhost:6432/pos_service_db
postgresql://postgres:postgres@localhost:5000/pos_service_db
```

6432 — пул к лидеру, 6433 — пул к репликам. HAProxy напрямую: 5000 RW,
5001 RO. API Patroni: 8008/8009/8010; HAProxy statistics: 8404/stats.
Пароли по умолчанию предназначены для этого локального учебного стенда.

## Первый запуск — отдельный будущий этап

Требуется Docker с Compose v2. Python/uv/Ruby на хосте для HA-команд не нужны.
Shell-команды на Windows выполнять из WSL/Git Bash.

```bash
docker compose up -d --build
./scripts/wait_ready.sh
./scripts/seed.sh --seed 42
./scripts/check.sh --json /reports/hw01-full.json -v
```

Данные генерируются отдельной командой после создания схем. Readiness проверяет
все четыре контракта и обе реплики. `scripts/check.sh` вызывает **неизменённый**
официальный чекер с контейнерными адресами. Прочитать заметку о streaming выше:
одна проверка HA может оказаться ложной ошибкой самого чекера.

Проверка с хоста при наличии Python >=3.12 и uv:

```bash
uv run python hws_descriptions/hw1/hw01_check.py --submission hw01_submission.yaml -v
```

`hw01_submission.yaml` содержит адреса localhost; `hw01_submission.container.yaml`
— имена Docker-сервисов. Оба манифеста включают master, replica, writer и admin.
`seed_delta` получает новый seed из sequence для каждого прогона репликации.

После добавления нумерованной миграции:

```bash
./scripts/migrate.sh
```

После обычной остановки volumes сохраняются:

```bash
docker compose down
```

## Работа команды

Доменный SQL, генератор и тесты сохранены. Команда продолжает исправлять их
независимо от инфраструктурной ветки. Уже применённые миграции не переписывать:
добавлять следующий номер или согласовать чистое пересоздание учебного стенда.

Прежний одиночный PostgreSQL доступен через `docker-compose.dev.yml` с отдельным
Compose project; команды для него приведены в инфраструктурной документации.

Не завершены: живой прогон HA, эксперименты отказоустойчивости, исправления
бизнес-логики, финальные ERD, обязательные ADR и карта DWH mapping. Наличие
конфигурации etcd из трёх узлов само по себе ещё не подтверждает бонус.
