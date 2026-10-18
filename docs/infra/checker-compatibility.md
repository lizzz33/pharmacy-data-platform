# Выданный чекер: состояние реплик Patroni

Оригинальный `hws_descriptions/hw1/hw01_check.py` не изменён.

В `check_ha` строка:

```python
running = [m for m in members if m.get("state") == "running"]
```

считает исправными только члены с `state=running`. В официальном примере
`GET /cluster` Patroni лидер имеет `state=running`, а исправная реплика —
`state=streaming`. Поэтому ожидается ложный красный результат HA/running,
даже если PostgreSQL и физическая репликация исправны.

Источник: https://patroni.readthedocs.io/en/latest/rest_api.html#cluster-status-endpoints

Требуется проверить фактический ответ закреплённой версии при будущем запуске
и согласовать с преподавателем принятие `streaming` для replica. Готовое
минимальное предложение изменения находится в
`hw01_check.patroni-state.patch`. Оно не применено автоматически.
Не заменять реальный Patroni API прокси, который подделывает состояние.

Readiness нашего стенда принимает running/streaming, но официальный чекер
запускается в исходном виде. Сам факт наличия трёх etcd не подтверждает бонус:
нужны реальные эксперименты с потерей одного и двух членов, с логами.
