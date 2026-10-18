# Карта склейки источников для DWH

> Этот документ заполняет шаблон HW1 и фиксирует, как четыре независимых источника будут интегрироваться в следующих ДЗ. Физических FK между сервисами нет: интеграция строится по стабильным business key.

## 1. Реестр систем-источников

| код источника | сервис | БД | владелец данных | частота изменений |
|---|---|---|---|---|
| `CRM` | crm_service | crm_service_db | команда CRM / клиентские данные | постоянно; профиль и согласия меняются реже, чем продажи |
| `CAT` | catalog_service | catalog_service_db | команда каталога | справочники и SKU — умеренно; цены — регулярно |
| `POS` | pos_service | pos_service_db | команда POS | высокая: чеки, строки и оплаты появляются непрерывно |
| `WMS` | wms_service | wms_service_db | команда WMS | высокая: закупки, движения и остатки меняются постоянно |

## 2. Бизнес-сущности и их ключи

| бизнес-сущность | business key | в каких источниках встречается | как выглядит BK | кто первичный владелец |
|---|---|---|---|---|
| клиент | `customer_bk` | CRM, POS | `CUSTOMER-<namespace>-000123` | CRM |
| товарная позиция | `sku` / `sku_bk` | CAT, POS, WMS | `SKU-<namespace>-00148` | CAT |
| аптека | `pharmacy_bk` | POS, WMS | `PH-<namespace>-0034` | POS |
| партия | `batch_bk` | WMS, POS | `BATCH-<namespace>-<sku>-<slot>` | WMS |
| поставщик | `supplier_bk` | WMS | `SUP-<namespace>-001` | WMS |
| распредцентр | `dc_bk` | WMS | `DC-<namespace>-01` | WMS |
| кассовый документ | `receipt_bk` | POS | `RCPT-<namespace>-0000731` | POS |
| закупка | `purchase_bk` | WMS | `PO-<namespace>-000001` | WMS |

Сущности, которые встречаются в нескольких источниках и потребуют общей интеграционной идентичности в ДЗ2:

- **клиент**: CRM → POS через `customer_bk`;
- **SKU**: Catalog → POS/WMS через `sku`;
- **аптека**: POS → WMS через `pharmacy_bk`;
- **партия**: WMS → POS через `batch_bk`.

Именно эти BK считаются integration identity. Суррогатные ID внутри сервисных БД наружу не используются.

## 3. Изменяющиеся атрибуты

| сущность | атрибут | меняется | история хранится | зачем нужна история |
|---|---|---|---|---|
| SKU | цена | да | `catalog.price_version`, интервалы `valid_from/valid_to` | корректная цена на дату продажи и анализ динамики цен |
| SKU | название | да | `catalog.sku_version` | исторические отчёты не должны переписываться после rename |
| SKU | признак Rx | да | `catalog.sku_version`; дополнительно snapshot в POS | корректная историческая трактовка продажи и I10 |
| SKU | категория | да | `catalog.sku_version` | анализ продаж в категории на дату факта |
| клиент | уровень лояльности | да | `crm.customer_profile_version` | анализ поведения по уровню программы во времени |
| клиент | город | да | `crm.customer_profile_version` | историческая география клиента |
| клиент | регион | да | `crm.customer_profile_version` | историческая география клиента |
| аптека | адрес | может меняться | отдельной истории нет; хранится текущее значение в POS | для HW1 достаточно текущего справочного атрибута; это известное ограничение |
| аптека | активность | да | текущее состояние + soft delete | сохранить исторические ссылки, не удаляя сущность |
| поставщик / РЦ | активность | да | текущее состояние + soft delete | сохранить исторические закупки и движения |

На факте POS физически сохраняются snapshots: `unit_price`, `sku_name_snapshot`, `is_rx_snapshot`, `batch_expiry_date_snapshot`.

## 4. Связи между сущностями (будущие линки)

| связь | кардинальность | где физически хранится | опциональна? |
|---|---|---|---|
| чек — клиент | N:1 | POS `receipt.customer_bk`, логическая ссылка в CRM | да, покупка без карты |
| чек — аптека | N:1 | через `receipt -> shift -> cash_register -> pharmacy` в POS | нет |
| позиция чека — SKU | N:1 | POS `receipt_line.sku` → CAT `sku_bk` логически | нет |
| позиция чека — партия | N:1 | POS `receipt_line.batch_bk` → WMS `batch_bk` логически | нет |
| партия — SKU | N:1 | WMS `batch.sku` → CAT `sku_bk` логически | нет |
| перемещение — партия | N:1 | WMS `movement.batch_bk` FK | нет |
| перемещение — локация | N:1 для каждой стороны | WMS `src_type/src_bk`, `dst_type/dst_bk` | одна сторона может быть NULL для внешнего прихода/списания |
| закупка — поставщик | N:1 | WMS `purchase_order.supplier_bk` FK | нет |
| закупка — РЦ | N:1 | WMS `purchase_order.dc_bk` FK | нет |
| возврат — исходная продажа | N:1 | POS `receipt.parent_receipt_bk` self-FK | только для refund |

## 5. Инкрементальная выгрузка

Все contract views отдают `updated_at`; в базовых таблицах оно обновляется автоматически.

| представление контракта | поле инкремента | как отслеживаются удаления | ожидаемый объём суточного дельта |
|---|---|---|---|
| `crm.v_customer` | `updated_at` | customer soft delete скрывает строку из view; для CDC нужен tombstone/обработка delete-события базовой таблицы | низкий/средний |
| `crm.v_loyalty_card` | `updated_at` | статус/закрытие; физического delete не требуется | низкий |
| `catalog.v_sku` | `updated_at` | soft-deleted SKU остаётся в contract с `is_active=false` | низкий |
| `catalog.v_price` | `updated_at` | интервалы закрываются UPDATE; новые версии — INSERT | средний |
| `pos.v_pharmacy` | `updated_at` | soft delete остаётся как `is_active=false` | низкий |
| `pos.v_receipt` | `updated_at` | факты не удаляются; новые документы — INSERT | высокий |
| `pos.v_receipt_line` | `updated_at` | факты не удаляются | высокий |
| `pos.v_payment` | `updated_at` | факты не удаляются | высокий |
| `wms.v_supplier` | `updated_at` | soft delete остаётся как `is_active=false` | низкий |
| `wms.v_distribution_center` | `updated_at` | soft delete остаётся как `is_active=false` | низкий |
| `wms.v_batch` | `updated_at` | партии не удаляются | средний |
| `wms.v_purchase_line` | `updated_at` | факт закупки сохраняется | средний |
| `wms.v_movement` | `updated_at` | movement immutable; correction = compensating movement | высокий |
| `wms.v_stock` | `updated_at` | текущее состояние обновляется движениями | высокий |

Важно: для `v_customer` одной watermark-выгрузки по view недостаточно, потому что после soft delete строка исчезает из view. В CDC-потоке это должно обрабатываться по изменению базовой `customer` и доменной семантике удаления/обезличивания.

## 6. Готовность к CDC

Автоматическая секция официального checker уже проходит.

| сервис | `wal_level` | publication | покрытие таблиц | replica identity |
|---|---|---|---|---|
| CRM | `logical` | `hw01_all_tables` | `FOR ALL TABLES` | DEFAULT для таблиц с PK, FULL там, где PK нет |
| Catalog | `logical` | `hw01_all_tables` | `FOR ALL TABLES` | DEFAULT/FULL по наличию PK |
| POS | `logical` | `hw01_all_tables` | `FOR ALL TABLES` | DEFAULT/FULL по наличию PK |
| WMS | `logical` | `hw01_all_tables` | `FOR ALL TABLES` | DEFAULT/FULL по наличию PK |

Publication и replica identity настраиваются в `scripts/infra/bootstrap.py`.

## 7. Известные проблемы интеграции

1. **Полиморфные WMS endpoints.** `movement.src_bk/dst_bk` могут обозначать supplier, DC, pharmacy, customer или внешний мир. В DWH потребуется типизированный ключ локации/участника, а физический FK на все варианты в source невозможен.
2. **Soft delete клиента.** После запроса на удаление customer исчезает из `contract.v_customer`, но исторические продажи обязаны сохраниться. В DWH потребуется отдельная политика tombstone/anonymization, чтобы не потерять факт и не хранить запрещённые PII.
3. **Часть справочников не историзируется.** Например адрес аптеки хранится как текущее состояние. Для HW1 это осознанное упрощение; если в DWH потребуется исторический адрес, source не сможет восстановить его задним числом.
4. **POS snapshots дублируют Catalog/WMS.** Это намеренно: исторический факт должен оставаться неизменным даже после изменения каталога. В DWH потребуется решить, когда использовать snapshot факта, а когда текущий/исторический satellite каталога.
5. **Нет прямой связи purchase → movement.** Закупка и складское движение связываются через `batch_bk`: `purchase_line.batch_bk -> batch -> movement.batch_bk`. Для текущего HW этого достаточно, но в DWH нельзя без дополнительной логики однозначно считать каждый `movement` частью конкретного `purchase_bk`, особенно если у партии несколько движений.
6. **Семантика удаления customer отличается от остальных master-data.** Customer исчезает из `contract.v_customer`, а остальные soft-deleted master/reference entities остаются в contract с неактивным статусом. CDC/DWH должен обрабатывать эти два сценария по-разному.
7. **`marketing_opt_in` — производное текущее состояние consent.** История согласий хранится в CRM, но contract отдаёт итоговый признак. Для исторической аналитики согласий нужно использовать базовые consent-события/CDC, а не только текущее значение из `v_customer`.
8. **Текущий seed не демонстрирует все типы изменений.** Delta добавляет новый namespace и хорошо проверяет репликацию, но почти не показывает UPDATE существующих бизнес-сущностей.

## 8. Заготовка витрин ДЗ3

| витрина ДЗ3 | нужные поля | откуда возьмутся |
|---|---|---|
| Аналитика закупок: дата, товар, категория, поставщик, количество, сумма, средняя цена | `ordered_at`, `sku`, категория SKU на дату, `supplier_bk`, `quantity`, `line_cost`, `unit_cost` | WMS `v_purchase_line`; Catalog `sku_version`/история SKU для категории на дату. Текущий `v_sku` сам по себе даёт только current-state. |
| Доставка по складам: дата, склад, число заказов, объём, среднее время обработки, задержки, уникальные заказчики | `moved_at`, `dispatched_at`, `src/dst`, `qty`, `batch_bk`, `sku`, связанная закупка/локация | WMS `v_movement`, `v_batch`, `v_purchase_line`, `v_distribution_center`; pharmacy при необходимости из POS. Связь movement с purchase восстанавливается через `batch_bk`. |

Ограничение второй витрины: текущая source-модель не хранит прямой `purchase_bk` в movement, поэтому связь движения с закупкой восстанавливается через batch и purchase_line. Это допустимо для текущей модели, но является интеграционным trade-off.
