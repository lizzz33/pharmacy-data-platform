# ADR 005: единая polymorphic movement вместо subtype-таблиц

**Статус:** принято.

## Контекст

WMS должен хранить движения партии между разными endpoint-типами:

- supplier;
- distribution center;
- pharmacy;
- customer;
- внешнее списание.

Часть сущностей находится в WMS, а pharmacy/customer — в других сервисах.

## Рассмотренные варианты

1. **Отдельные таблицы для supplier→DC, DC→pharmacy, pharmacy→customer, return, writeoff.** Отвергнуто: много почти одинаковых таблиц и сложный UNION для общего журнала.
2. **Единая таблица location/endpoints.** Отвергнуто: она всё равно не даёт физического FK на pharmacy/customer из других БД.
3. **Одна movement с `src_type/src_bk` и `dst_type/dst_bk`.** Выбрано.

## Выбор

Используем одну таблицу `movement` с:

- `movement_type`;
- `src_type/src_bk`;
- `dst_type/dst_bk`;
- `batch_bk`;
- количеством;
- `dispatched_at`;
- `moved_at`.

DB CHECK ограничивает допустимые комбинации movement type и endpoint types.

Cross-service существование pharmacy/customer проверяется generator/checker, а не FK.

## Цена выбора

Полиморфная ссылка слабее обычного FK и требует учитывать endpoint type в запросах.

Зато contract остаётся единым, журнал проще анализировать, а схема не дублирует одну и ту же структуру по множеству subtype tables.
