# Инфраструктура HW1

Статус: конфигурации и скрипты подготовлены, выполнена только статическая
проверка. Образы не собирались, контейнеры не запускались, failover и официальный
чекер на кластере не выполнялись. Работоспособность требует отдельного прогона.

## Состав

| Компонент | Сервисы | Назначение |
|---|---|---|
| PostgreSQL 16 + Patroni 4.1.0 | postgres1, postgres2, postgres3 | Один лидер и две физические реплики; четыре БД на каждом узле |
| etcd 3.5.21 | etcd1, etcd2, etcd3 | DCS с кворумом 2 из 3 |
| HAProxy 3.0 | haproxy | Порт 5000 выбирает лидера, 5001 — только реплики |
| PgBouncer из Debian Bookworm | pgbouncer-rw, pgbouncer-ro | Отдельные пулы к RW/RO-маршрутам |
| Инициализация | db-init | Базы, нумерованные миграции, роли, публикации, replica identity |
| Python 3.12 + psql | tools | Генератор, чекер и диагностика без Python/Ruby/uv на хосте |

По умолчанию постоянно работают 9 контейнеров: 3 PostgreSQL, 3 etcd, HAProxy
и 2 PgBouncer. `db-init` завершается после настройки; `tools` запускается по запросу.
Три PostgreSQL на одном компьютере позволяют исследовать отказы процессов,
но не защищают от отказа самого компьютера. Для учебного первого запуска
разумно выделить Docker 4 CPU и 6–8 GB RAM; это ориентир, а не измерение.

```mermaid
flowchart TD
    A["Генератор и чекер"] --> RW["PgBouncer RW :6432"]
    A --> RO["PgBouncer RO :6433"]
    RW --> H["HAProxy :5000 / :5001"]
    RO --> H
    H --> P1["PostgreSQL 1 + Patroni"]
    H --> P2["PostgreSQL 2 + Patroni"]
    H --> P3["PostgreSQL 3 + Patroni"]
    P1 <--> D["etcd: 3 узла"]
    P2 <--> D
    P3 <--> D
```

## Порядок первого запуска — выполнять позднее

Требуется Docker с Compose v2, Linux containers и доступ к реестрам образов,
Debian APT и PyPI при сборке. На Windows команды `.sh` выполнять из WSL или
Git Bash. Можно также вызывать соответствующие `docker compose run` напрямую.
`COMPOSE_PROJECT_NAME` в необязательном `.env` должен отличаться от dev-стенда,
если оба работают одновременно.

```bash
docker compose up -d --build
./scripts/wait_ready.sh
./scripts/seed.sh --seed 42
./scripts/check.sh --json /reports/hw01-full.json -v
```

`up -d` запускает инициализацию, но сам по себе не означает, что готовы
пользовательские схемы. `wait_ready.sh` проверяет топологию, роли RW/RO,
все контрактные представления и догоняние обеих реплик. Healthcheck PostgreSQL
проверяет работающий сервер, а не наличие бизнес-данных.

Перед полной проверкой прочитать [checker-compatibility.md](checker-compatibility.md):
у выданного чекера есть несовместимость с состоянием `streaming` в API Patroni.
Оригинальный файл преподавателя не изменён. Семантические ошибки генератора
из [business-review.md](business-review.md) также остаются в ведении команды.

Минимальные будущие проверки:

```bash
docker compose ps -a
docker compose logs db-init
./scripts/check.sh --sections contract,keys,volume,dq,cross,inv,realism --skip-exec -v
./scripts/check.sh --sections repl,cdc,ha -v
```

`--skip-exec` у чекера отключает запуск `seed_delta`; негативные SQL-тесты при
этом всё равно выполняются. После проверки `repl` на стенде останется новая
порция данных — это ожидаемое действие официального чекера.

## Подключения

Все опубликованные порты привязаны к `127.0.0.1`.

| Назначение | На хосте | Из Docker-сети |
|---|---|---|
| Приложение/чекер, лидер через пул | localhost:6432 | pgbouncer-rw:6432 |
| Чекер, реплики через пул | localhost:6433 | pgbouncer-ro:6432 |
| Администрирование / RW HAProxy | localhost:5000 | haproxy:5000 |
| RO HAProxy | localhost:5001 | haproxy:5001 |
| PostgreSQL 1 / 2 / 3 напрямую | 15432 / 25432 / 35432 | postgres1/2/3:5432 |
| API Patroni 1 / 2 / 3 | 8008 / 8009 / 8010 | postgres1/2/3:8008 |
| HAProxy statistics | http://localhost:8404/stats | haproxy:8404/stats |

На каждом узле одинаковые базы: `crm_service_db`, `catalog_service_db`,
`pos_service_db`, `wms_service_db`. Номер узла не задаёт роль: лидер может меняться.

Примеры DSN с локальными значениями по умолчанию:

```text
postgresql://checker:checker@localhost:6432/pos_service_db
postgresql://checker:checker@localhost:6433/pos_service_db
postgresql://app:app@localhost:6432/pos_service_db
postgresql://postgres:postgres@localhost:5000/pos_service_db
```

`checker` имеет SELECT на контракт и `pg_monitor` для диагностики реплики;
записи в бизнес-таблицы у него нет. `app` имеет DML на бизнес-таблицы, доступ
к их sequences и SELECT контракта. `postgres` используется миграциями и
административными проверками, `replicator` — физической репликацией.
Учётные записи `pharmacy/pharmacy` сохранены только в dev-варианте.

Пул работает в **session mode**, потому что выданный чекер устанавливает
`TimeZone`, `DateStyle`, `statement_timeout` отдельными SET-запросами.
При transaction pooling произвольные параметры сессии могут потеряться между
транзакциями. Размер одного пула 10 серверных соединений плюс 2 резервных,
лимит одной базы 30. На RO-пуле разрешён только checker; PostgreSQL-реплика
в любом случае отклоняет записи.

`.env` необязателен: значения по умолчанию уже согласованы. При смене паролей
обновить оба манифеста по инструкции `.env.example`. На существующем кластере
простая смена переменной Patroni не меняет пароль уже созданного superuser или
replicator: понадобится согласованная ротация SQL/config. Для обычной сдачи
оставьте локальные значения или задайте их до первого старта.

## Миграции и параллельная работа

Доменная команда владеет `db/migrations/<service>/`, `src/pharmacy_dwh/seed/`
и `tests/`. Инфраструктурная ветка не меняет содержимое этих файлов.

`db-init` обращается к лидеру через HAProxy. В каждой базе есть
`infra.schema_migrations` с именем и SHA-256 применённого SQL. Миграция и запись
в журнал коммитятся атомарно; внешние `BEGIN/COMMIT` существующих файлов
удаляются только в памяти исполнителя. Session advisory lock сериализует
повторные запуски для одной базы. Изменённый уже применённый файл вызывает ошибку.

После добавления нового SQL:

```bash
./scripts/migrate.sh
./scripts/wait_ready.sh
```

Миграции применяются как postgres. Новые файлы должны быть транзакционными:
не использовать внутренние COMMIT, CREATE DATABASE или CREATE INDEX CONCURRENTLY.
При наличии внешней пары BEGIN/COMMIT она должна охватывать весь файл.
Если команда переписывает начальные `001–003`, для существующих данных нужен
новый номер миграции; для чистого учебного старта можно пересоздать volumes.
`docker compose down -v` удаляет данные всего этого учебного кластера.
Обычный `docker compose down` данные сохраняет.

Изменения миграций и Python-кода видны через bind mount, пересборка образов
не нужна. Изменения Dockerfile, требований Python и конфигов, скопированных
в образы, требуют `docker compose up -d --build`. Параметры `bootstrap.dcs`
после первого старта нужно менять через `patronictl edit-config`, а не только
редактированием YAML; не выполнять это до отдельной проверки.

Dev-стенд команды сохранён в `docker-compose.dev.yml` и `hw01_submission.dev.yaml`:

```bash
docker compose -p pharmacy-dev -f docker-compose.dev.yml up -d
uv run python -m pharmacy_dwh.seed.cli --seed 42
uv run python hws_descriptions/hw1/hw01_check.py --submission hw01_submission.dev.yaml --sections contract,keys,volume,dq,cross,inv,realism --skip-exec
```

Этот вариант использует прежние localhost:5432 и pharmacy/pharmacy. Новые
shell-обёртки в `scripts/` относятся к HA-стенду; для dev использовать команды
выше. Команда может продолжать исправления, не запуская Patroni.

## CDC и повторные дельты

`wal_level=logical` задан кластеру. В каждой source DB создаётся публикация
`hw01_all_tables FOR ALL TABLES`, включая технический журнал миграций и будущие
таблицы. Таблицы с PK используют default replica identity; таблицам без PK
исполнитель назначает FULL. Режим NOTHING исправляется на DEFAULT/FULL.
Новый DML/DDL доступ обновляется при каждом запуске `db-init`.

Это подготовка источников к CDC. Коннектор доставки, подписка и DWH не создаются.
Физический DELETE будет представлен logical decoding, soft delete — UPDATE
исходной таблицы. Если строка скрывается из VIEW, выгрузка только по
`updated_at` её исчезновение не обнаружит: механизм tombstone и обезличивание
истории должен определить доменный процесс и карта DWH mapping.

`scripts/seed.sh --seed N` сохраняет детерминированность и идемпотентность
генератора. `seed_delta` дополнительно получает новый N из sequence в POS,
начиная с 1 000 000 000. Поэтому каждый запуск проверки репликации действительно
добавляет строки. Sequence расходуется даже при неудачном запуске; пропуски
допустимы. Дельта команды создаёт новые namespace клиентов/SKU/аптек, а не
обновления существующих сущностей. После исправления этого поведения командой
обёртку можно заменить без изменения топологии кластера.

## Что ещё предстоит

- Сборка образов, запуск с чистыми volumes, проверки ролей и миграций.
- Полный официальный чекер, проверка несовместимости `running/streaming`.
- Повторный seed и две последовательные проверки репликации.
- Реальные failover/switchover и эксперименты Э1–Э7 с логами и числами.
- Документы ERD, обязательные ADR и DWH mapping в окончательном виде.
- Исправления предметной области командой.

Теги PostgreSQL/HAProxy и пакеты APT закреплены по major/distribution, а не по
digest/snapshot. После первого успешного прогона можно зафиксировать digests
и версии всей транзитивной среды; сейчас они не объявляются проверенными.
