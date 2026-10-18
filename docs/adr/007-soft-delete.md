# ADR 007: soft delete и историческая видимость в contract

**Статус:** принято.

## Контекст

Задание требует soft delete для справочников и отдельно требует, чтобы удалённый по запросу клиент исчезал из аналитики.

При этом исторические факты продолжают ссылаться на SKU, pharmacy, supplier и DC.

Если просто скрыть все строки с `deleted_at IS NOT NULL`, историческая ссылочная целостность contract ломается.

## Рассмотренные варианты

1. **Скрывать все soft-deleted сущности из contract.** Отвергнуто: исторические факты становятся orphaned.
2. **Никого не скрывать.** Отвергнуто для customer: это противоречит явному требованию задания.
3. **Разная семантика для master data и customer deletion.** Выбрано.

## Выбор

- SKU, pharmacy, supplier, DC и reference values остаются в contract после soft delete;
- их состояние видно через `is_active=false`;
- deleted entity не может оставаться active;
- customer — исключение: исчезает из `contract.v_customer`;
- customer contacts обезличиваются.

## Цена выбора

Soft delete имеет разную семантику по типам сущностей.

Для DWH/CDC это нужно явно учитывать, особенно для customer: исчезновение строки из contract view нельзя корректно обработать только обычным watermark по `updated_at`.
