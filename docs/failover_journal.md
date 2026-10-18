# Журнал отказоустойчивости — ДЗ №1

Все значения ниже получены 18 октября 2026 года на локальном стенде. Полные
команды, JSONL write-loop, JSON summaries и логи Patroni сохранены в
[`reports/failover/`](../reports/failover/). Время в evidence — UTC.

## 0. Стенд

| параметр | значение |
|----------|----------|
| машина | MacBook Pro, Apple M1 Pro, 8 CPU cores, 16 GB RAM, SSD |
| ОС | macOS 26.5.2 arm64; Docker VM — Linux arm64 |
| Docker / Compose | Docker Engine 24.0.2 / Docker Compose 2.19.1 |
| образ PostgreSQL | PostgreSQL 16 (Patroni 4.1.0) |
| топология | 3 Patroni/PostgreSQL + 3 etcd; HAProxy RW/RO; PgBouncer RW/RO |
| `ttl` / `loop_wait` / `retry_timeout` | 30 / 10 / 10 секунд |
| `synchronous_mode` | `false`; для Э5 динамически включался и затем выключался |

```text
client -> PgBouncer RW :6432 -> HAProxy RW :5000 -> Patroni leader
       -> PgBouncer RO :6433 -> HAProxy RO :5001 -> Patroni replica
Patroni postgres1/2/3 <-> etcd1/2/3 (quorum 2/3)
```

Технические записи идут только в `pos_service_db.failover_bench.write_probe`,
созданную migration `migrations/pos/004_failover_benchmark.sql`; бизнес-факты не изменяются.

## Э1. Baseline: запись под нагрузкой

```bash
./scripts/failover/run.sh e1
```

Сырой фрагмент `reports/failover/e1-baseline/write-events.jsonl`:

```text
seq=1    status=ok committed=15:52:43.291827 latency=23.025 ms
seq=2    status=ok committed=15:52:43.293598 latency=1.119 ms
seq=3    status=ok committed=15:52:43.315159 latency=1.451 ms
...
seq=2872 status=ok committed=15:53:43.216572 latency=0.985 ms
seq=2873 status=ok committed=15:53:43.236820 latency=1.239 ms
seq=2874 status=ok committed=15:53:43.257391 latency=2.005 ms
```

| метрика | значение |
|---------|----------|
| успешных транзакций за 60.009 с | 2 874 |
| TPS | 47.893 |
| задержка записи, медиана / p95 | 3.809 / 8.535 мс |
| ошибки / потерянные подтверждённые записи | 0 / 0 |

Вывод: обычный RW-маршрут устойчиво даёт около 48 одиночных транзакций/с при
искусственном интервале 20 мс между попытками.

## Э2. Аварийная потеря лидера

```bash
./scripts/failover/run.sh e2-e3
# внутри после wait_ready: docker compose stop -t 0 postgres1
```

Фрагмент write-loop и Patroni:

```text
15:58:15.996 last acknowledged write before failure
15:58:16.014 OperationalError: server closed the connection unexpectedly
15:58:40.437 postgres2: promoted self to leader by acquiring session lock
15:58:43.574 first acknowledged write after failover
```

| метрика | значение |
|---------|----------|
| старая / новая роль лидера | postgres1 / postgres2 |
| последняя / первая успешная запись | 15:58:15.996 / 15:58:43.574 UTC |
| **RTO записи** | **27.579 с** |
| отклонённых транзакций | 1 |
| потеря подтверждённых записей | нет; все acknowledged `(run_id, sequence_no)` найдены после failover |

RTO согласуется с `ttl=30` и `loop_wait=10`: promotion появился через 24.333 с
после команды остановки, затем маршруту и пулу потребовалось несколько секунд.

## Э3. Возврат упавшего узла

```bash
# продолжение той же явной команды Э2/Э3
docker compose start postgres1
```

```text
15:58:41.842 running pg_rewind from postgres2
15:58:42.953 pg_rewind exit code=0
servers diverged at WAL location 0/11C71F80 on timeline 4
rewinding from last common checkpoint at 0/11B37700 on timeline 4
15:59:01.920 started streaming WAL ... on timeline 5
```

| метрика | значение |
|---------|----------|
| понадобился ли `pg_rewind` | да, exit code 0 |
| время до `streaming` | 23.116 с после `docker compose start` |
| диапазон divergent WAL по LSN | 1 288 320 байт (≈1.23 MiB) |
| роль после возврата | replica |

После promotion появилась новая timeline, поэтому обычного продолжения старой
timeline было недостаточно; Patroni автоматически выполнил `pg_rewind`.

## Э4. Плановое переключение

```bash
./scripts/failover/run.sh e4
# patronictl ... switchover pharmacy-hw1 --leader postgres2 --candidate postgres1 --force
```

```text
15:59:48.460 postgres2: switchover: demoting myself
15:59:49.651 postgres1: promoted self to leader by acquiring session lock
15:59:50.415 Successfully switched over to "postgres1"
first error: OperationalError: server closed the connection unexpectedly
```

| метрика | значение |
|---------|----------|
| RTO | 3.419 с |
| отклонённых транзакций | 3 |
| потеря подтверждённых записей | нет |

Плановое переключение по RTO в 8.1 раза дешевле аварийного (3.419 против
27.579 с), потому что Patroni согласованно демотирует лидера без ожидания TTL.

## Э5. Цена синхронной репликации

```bash
./scripts/failover/run.sh e5
# patronictl edit-config pharmacy-hw1 --set synchronous_mode=true --force
# ... измерения и failover ...
# patronictl edit-config pharmacy-hw1 --set synchronous_mode=false --force
```

```text
synchronous_mode: true
standby "postgres3" is now a synchronous standby with priority 1
sync failover first error: server closed the connection unexpectedly
synchronous_mode: true -> false; Configuration changed
```

| метрика | async | sync | дельта sync к async |
|---------|-------|------|----------------------|
| TPS (30 с) | 47.670 | 47.752 | +0.082 (+0.17%) |
| median latency | 3.828 мс | 4.844 мс | +1.016 мс (+26.5%) |
| p95 latency | 10.378 мс | 10.991 мс | +0.613 мс (+5.9%) |
| failover RTO | 27.579 с | 32.201 с | +4.622 с (+16.8%) |
| rejected attempts при failover | 1 | 30 | +29 |
| потеря acknowledged writes | нет | нет | без изменения |

На одном физическом хосте sync почти не изменил TPS, но добавил 1.016 мс к
median и 0.613 мс к p95. Это локальное измерение нельзя переносить на сеть между
ЦОД. После опыта dynamic config действительно возвращён к `false`.

## Э6. Отказ DCS / etcd quorum

```bash
./scripts/failover/run.sh e6
# внутри: stop etcd3; restore; затем stop etcd2 etcd3; restore
```

```text
one down: etcd1 healthy; etcd2 healthy; etcd3 unhealthy
one down workload: 728 successful, 0 failed, 48.531 TPS
16:07:54.894 demoting self because DCS is not accessible and I was a leader
16:07:55.207 database system is ready to accept read-only connections
16:08:26.117 RO query: pg_is_in_recovery=t, count=22448
final: etcd1 healthy; etcd2 healthy; etcd3 healthy
```

| метрика | значение |
|---------|----------|
| один etcd недоступен | quorum сохранён, 0 ошибок записи |
| только один etcd доступен | quorum потерян; бывший лидер demote в read-only |
| время от остановки 2 узлов до последней записи | ≈17.9 с |
| окно недоступности записи | 36.206 с |
| чтение при потере quorum | доступно через RO, 22 448 строк |
| после возврата | 3/3 etcd healthy, 1 leader + 2 streaming replicas |

Для переживания падения одного участника требуется 3-node etcd: большинство
2/3 остаётся. Один из трёх большинства не образует, поэтому Patroni безопасно
демотирует leader и предотвращает split brain.

## Э7. Пул соединений под наплывом

```bash
./scripts/failover/run.sh e7
```

```text
direct 200: success=200 failed=0 p95_connect=211.182 ms
direct 250: success=225 failed=25 p95_connect=387.318 ms
first error: FATAL: sorry, too many clients already
pooled 200: success=200 failed=0 p95_connect=584.724 ms
pooled 250: success=250 failed=0 p95_connect=784.466 ms
```

| метрика | PostgreSQL напрямую | PgBouncer RW |
|---------|----------------------|--------------|
| первая проверенная ступень с ошибками | 250 clients (25 errors) | ошибок нет до 250 |
| representative error | `FATAL: sorry, too many clients already` | — |
| p95 connect при 250 clients | 387.318 мс для успешных | 784.466 мс |
| полное время ступени 250 | 1.188 с, но 25 отказов | 12.680 с, все 250 завершены |

PgBouncer заменил отказ очередью: все клиенты обслужены, но хвостовая задержка
выросла. Стенд оставлен в session pooling, потому что официальный checker задаёт
`TimeZone`, `DateStyle` и `statement_timeout` отдельными session-level `SET`;
transaction pooling без отдельной адаптации потерял бы такое состояние.

## Э8. Сетевой раздел

Не выполнялся: это необязательный опыт и не нужен для заявленных бонусов.

## Итоговая таблица: отказ → кто чинит → цена

| отказ | кто чинит | измеренная цена |
|-------|-----------|-----------------|
| много подключений | PgBouncer | 250/250 вместо 225/250; p95 connect 784.466 мс |
| упал узел БД | Patroni + etcd | RTO 27.579 с, 1 rejected attempt |
| клиент не знает нового адреса | HAProxy + PgBouncer | ручной смены DSN нет; цена входит в RTO 27.579 с |
| потеря последних транзакций | sync replica | потерь не наблюдалось; p95 +0.613 мс, sync RTO +4.622 с |
| `DROP TABLE` / логическая ошибка | backup/PITR и оператор | не измерялось: физическая HA реплицирует ошибку, сама не отменяет |
| весь физический хост | внешний host/AZ-level failover | не защищено и не измерялось: все контейнеры на одном Mac |

## Что бы я поменял после измерений

1. Проверил бы меньший `ttl` на отдельном reliability-прогоне: аварийные 27.579 с
   намного дороже плановых 3.419 с, но снижение TTL повышает риск ложного failover.
2. Для критичных подтверждений рассмотрел бы sync mode: здесь цена p95 составила
   только 0.613 мс, хотя failover оказался на 4.622 с дольше.
3. Оставил бы session pool для checker, но добавил бы отдельный transaction pool
   для stateless application traffic: текущий pool принял 250 клиентов без отказа,
   но завершал ступень 12.680 с из-за очереди.

## Ограничения

- Физическая HA не отменяет логические ошибки вроде `DROP TABLE`: изменение
  реплицируется на standby, для восстановления нужны backup/PITR.
- Три контейнера PostgreSQL и три контейнера etcd на одном физическом Mac не
  защищают от потери всего хоста/диска/питания.
- Результаты latency относятся только к этой машине и локальной Docker network.
