# wms_service_db

## Назначение

WMS отвечает за поставщиков, распределительные центры, закупки, партии, перемещения и текущие остатки товара.

Главный вопрос этой базы: **где находится конкретная партия товара, откуда она пришла и как перемещалась**.

Идём по пути минимализма: добавляем только сущности и поля, которые нужны README, контракту, инвариантам или внутренней целостности модели.

## Рассмотренная альтернатива: типизированные таблицы movement

Рассматривали вариант разделить движение на общую таблицу-заголовок `movement` и отдельные subtype-таблицы по типам операций, например:

- `movement_receipt`;
- `movement_transfer`;
- `movement_sale_writeoff`;
- `movement_return`;
- `movement_writeoff`.

Плюс такого подхода: направление и влияние на stock становятся структурно более явными. Например, триггер на `movement_transfer` всегда знает, что нужно уменьшить остаток source и увеличить destination, а недопустимые маршруты вроде `supplier -> customer` сложнее представить физически.

От этого варианта отказались по двум причинам:

1. Все subtype-таблицы имели бы почти одинаковый набор полей, а обязательный `contract.v_movement` пришлось бы собирать через `UNION ALL`.
2. Появляется новая сложность: нужно гарантировать, что каждой строке `movement` соответствует ровно одна subtype-запись. Для этого всё равно понадобился бы дополнительный constraint trigger.

Выбран единый `movement` с полиморфными `src_type/src_bk` и `dst_type/dst_bk`, а влияние на stock определяется не `movement_type`, а тем, является ли source/destination внутренней складской локацией:

- `dc`, `pharmacy` → участвуют в stock;
- `supplier`, `customer`, `NULL` → в stock не материализуются.

Таким образом один общий trigger/function на вставку movement может детерминированно обновлять stock без большого `CASE movement_type`.


---

# Что известно из README

Для склада явно заданы требования:

- партия определяется как `(SKU, номер серии производителя, дата производства, дата годности)`;
- номер серии уникален в рамках SKU;
- просроченную партию нельзя принять на склад;
- просроченную партию нельзя продать;
- товар движется по цепочке `поставщик → РЦ → аптека → покупатель`;
- есть обратные и списательные движения:
  - возврат поставщику;
  - списание брака;
  - списание просрочки;
- остаток партии в локации не может стать отрицательным;
- для отгрузки известны момент отправки и момент приёмки.

WMS также отвечает за:

- поставщиков;
- распределительные центры;
- заказы поставщикам;
- приёмки;
- партии;
- перемещения;
- остатки.

---

# Что требует контракт

WMS должен отдать шесть представлений:

- `contract.v_supplier`;
- `contract.v_distribution_center`;
- `contract.v_batch`;
- `contract.v_purchase_line`;
- `contract.v_movement`;
- `contract.v_stock`.

---

# Предлагаемая физическая модель

Предлагаем семь основных таблиц:

1. `supplier`
2. `distribution_center`
3. `purchase_order`
4. `purchase_line`
5. `batch`
6. `movement`
7. `stock`

## Правило по ключам

Если у сущности есть стабильный business key из предметной области, используем его как PRIMARY KEY.

Поэтому:

- `supplier_bk` — PK;
- `dc_bk` — PK;
- `purchase_bk` — PK;
- `batch_bk` — PK;
- `movement_bk` — PK.

Для строк закупки естественный ключ составной:

```text
(purchase_bk, line_no)
```

Для остатка естественный ключ:

```text
(location_type, location_bk, batch_bk)
```

---

## 1. `supplier`

Справочник поставщиков.

Поля:

- `supplier_bk TEXT PRIMARY KEY`;
- `supplier_name TEXT NOT NULL`;
- `country TEXT NOT NULL`;
- `is_active BOOLEAN NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- `supplier_bk` уникален и неизменяем;
- soft delete вместо физического DELETE;
- `updated_at` обновляется автоматически.

---

## 2. `distribution_center`

Справочник распределительных центров.

Поля:

- `dc_bk TEXT PRIMARY KEY`;
- `dc_name TEXT NOT NULL`;
- `region TEXT NOT NULL`;
- `city TEXT NOT NULL`;
- `is_active BOOLEAN NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- `dc_bk` уникален и неизменяем;
- soft delete вместо физического DELETE;
- `updated_at` обновляется автоматически.

---

## 3. `purchase_order`

Заказ поставщику.

Поля:

- `purchase_bk TEXT PRIMARY KEY`;
- `supplier_bk TEXT NOT NULL` — FK → `supplier.supplier_bk`;
- `dc_bk TEXT NOT NULL` — FK → `distribution_center.dc_bk`;
- `ordered_at TIMESTAMPTZ NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- `purchase_bk` уникален и неизменяем.

---

## 4. `purchase_line`

Строка заказа поставщику.

Поля:

- `purchase_bk TEXT NOT NULL` — FK → `purchase_order.purchase_bk`;
- `line_no INT NOT NULL`;
- `sku TEXT NOT NULL` — логическая cross-service ссылка на Catalog;
- `batch_bk TEXT NULL` — появляется после приёмки;
- `quantity NUMERIC(...) NOT NULL`;
- `unit_cost NUMERIC(..., 2) NOT NULL`;
- `currency TEXT NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

PRIMARY KEY:

```text
(purchase_bk, line_no)
```

Ограничения:

- `line_no > 0`;
- `quantity > 0`;
- `unit_cost >= 0`;
- валюта — трёхбуквенный код ISO 4217 в верхнем регистре;
- `fk_purchase_line_batch_sku`: `(batch_bk, sku)` → `batch (batch_bk, sku)`. Принятая партия обязана быть того же SKU, что строка закупки; обе колонки в одной БД, поэтому это проверяет сама база. Для ссылки в `batch` есть `UNIQUE (batch_bk, sku)`. Пока `batch_bk IS NULL` (строка не принята), FK не проверяется.

`supplier_bk`, `dc_bk` и `ordered_at` не дублируем физически в строке: они берутся из `purchase_order` при построении contract view.

`received_at` физически в `purchase_line` не храним: после появления `batch_bk` берём его из `batch.received_at`. В нашей упрощённой модели это один и тот же момент приёмки, поэтому отдельное поле только дублировало бы данные.

`line_cost` физически не храним: в `contract.v_purchase_line` вычисляем как `quantity * unit_cost`. Так не возникает риска рассинхронизации между тремя значениями.

---

## 5. `batch`

Конкретная партия / серия товара.

Поля:

- `batch_bk TEXT PRIMARY KEY`;
- `sku TEXT NOT NULL` — логическая cross-service ссылка на Catalog;
- `series_no TEXT NOT NULL`;
- `manufactured_date DATE NOT NULL`;
- `expiry_date DATE NOT NULL`;
- `received_at TIMESTAMPTZ NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- `batch_bk` уникален и неизменяем;
- `UNIQUE (sku, series_no)`;
- `expiry_date > manufactured_date`;
- при создании/приёмке партии `expiry_date` не должна быть раньше момента приёмки: `expiry_date >= (received_at AT TIME ZONE 'UTC')::date`. Дата приёмки берётся в UTC, чтобы результат не зависел от `TimeZone` сессии.

Важно: для `sku` здесь нет FOREIGN KEY, потому что Catalog — другая БД. Целостность проверяется генератором и cross-service checker.

---

## 6. `movement`

Журнал движения партии.

Поля:

- `movement_bk TEXT PRIMARY KEY`;
- `batch_bk TEXT NOT NULL` — FK → `batch.batch_bk`;
- `movement_type TEXT NOT NULL`;
- `src_type TEXT NULL`;
- `src_bk TEXT NULL`;
- `dst_type TEXT NULL`;
- `dst_bk TEXT NULL`;
- `qty NUMERIC(...) NOT NULL`;
- `dispatched_at TIMESTAMPTZ NULL`;
- `moved_at TIMESTAMPTZ NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Допустимые `movement_type` по контракту:

```text
receipt | transfer | sale_writeoff | return | writeoff
```

Допустимые типы локаций:

```text
src_type: dc | pharmacy | supplier | NULL
dst_type: dc | pharmacy | customer | supplier | NULL
```

Ограничения:

- `qty > 0`;
- источник и получатель не могут быть одной и той же локацией;
- одновременно `src_type` и `dst_type` не могут быть NULL;
- `src_type IS NULL` тогда и только тогда, когда `src_bk IS NULL`;
- `dst_type IS NULL` тогда и только тогда, когда `dst_bk IS NULL`;
- если `dispatched_at IS NOT NULL`, то `dispatched_at <= moved_at`;
- дополнительно нужен составной CHECK по `movement_type + src_type + dst_type`, чтобы разрешать только осмысленные маршруты предметной области.

Предварительно допустимые комбинации:

```text
receipt:
    supplier -> dc
    NULL     -> dc      # приёмка извне, если источник в WMS не моделируется

transfer:
    dc       -> pharmacy

sale_writeoff:
    pharmacy -> customer

return:
    pharmacy -> dc
    dc       -> supplier

writeoff:
    dc       -> NULL
    pharmacy -> NULL
```

Все остальные комбинации считаем недопустимыми. В частности, не разрешаем такие маршруты, как `supplier -> pharmacy`, `supplier -> customer`, `dc -> customer`, если они не описаны предметной областью.

`sku` физически в movement не храним: для `contract.v_movement` он получается через `batch.sku`.

### Почему ссылки на локации полиморфные

Одна колонка `src_bk/dst_bk` может указывать на разные типы сущностей.

Внутри WMS:

- `dc_bk` принадлежит WMS;
- `supplier_bk` принадлежит WMS.

Но:

- `pharmacy_bk` принадлежит POS;
- customer в destination тоже внешний для WMS.

Поэтому обычный FK на `src_bk/dst_bk` сделать нельзя.

---

## 7. `stock`

Материализованный текущий остаток партии в локации.

Поля:

- `location_type TEXT NOT NULL`;
- `location_bk TEXT NOT NULL`;
- `batch_bk TEXT NOT NULL` — FK → `batch.batch_bk`;
- `qty_on_hand NUMERIC(...) NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

PRIMARY KEY:

```text
(location_type, location_bk, batch_bk)
```

Допустимые `location_type`:

```text
dc | pharmacy
```

Ограничение:

```text
qty_on_hand >= 0
```

### Почему выбираем материализованный stock

README и I7 требуют физически не допустить отрицательный остаток.

Материализованная таблица позволяет сделать это непосредственно через CHECK и обновлять остаток вместе с записью движения в одной транзакции.

Альтернатива — вычислять остаток как сумму movement — возможна, но тогда запрет отрицательного промежуточного/итогового остатка сложнее гарантировать на уровне БД.

Это решение нужно будет оформить отдельным ADR, потому что тема прямо обязательна в задании.

---

# Как модель покрывает пункты README про склад

## 1. Партия и уникальность серии

Требование:

> Партия — это SKU, номер серии, дата производства и дата годности. Номер серии уникален в рамках SKU.

Покрытие:

- таблица `batch`;
- `batch_bk` — стабильный business key;
- `UNIQUE (sku, series_no)`;
- `manufactured_date` и `expiry_date` хранятся непосредственно в партии.

## 2. Просроченную партию нельзя принять и продать

Для WMS:

- I9 проверяется при приёмке / создании принятой партии;
- `expiry_date` должна быть не раньше даты приёмки.

Продажа относится к POS, но POS хранит `batch_bk`, поэтому сможет проверить срок годности конкретной партии из WMS.

## 3. Цепочка поставщик → РЦ → аптека → покупатель и обратные движения

Покрытие:

- `purchase_order` и `purchase_line` описывают закупку у supplier в DC;
- `movement` хранит фактические перемещения;
- `src_type/src_bk` и `dst_type/dst_bk` позволяют представить РЦ, аптеку, поставщика и покупателя;
- `movement_type` различает приёмку, transfer, sale write-off, return и writeoff.

## 4. Остаток не может быть отрицательным

Покрытие:

- текущий остаток хранится в `stock`;
- `CHECK (qty_on_hand >= 0)`;
- movement и stock должны изменяться атомарно в одной транзакции.

Это напрямую закрывает I7.

## 5. Известны моменты отгрузки и приёмки

Покрытие:

- `movement.dispatched_at`;
- `movement.moved_at`.

В `contract.v_movement` разница между ними позволяет считать время обработки и задержки.

---

# Контрактные представления

## `contract.v_supplier`

Практически напрямую из `supplier`:

- `supplier_bk`;
- `supplier_name`;
- `country`;
- `is_active`;
- `updated_at`.

Soft-deleted supplier остаётся в контракте.

Soft delete справочника не скрывает сущность из контракта: на неё ссылается история (чеки, закупки, перемещения). С фильтром `deleted_at IS NULL` удаление аптеки или SKU с историей ломает C07/C08, X01/X03/X06. Статус виден через `is_active`; `CHECK (deleted_at IS NULL OR NOT is_active)` (`ck_<table>_deleted_inactive`) не даёт удалённой записи остаться активной. Из контракта по soft delete исчезает только клиент — этого требует контракт.

## `contract.v_distribution_center`

Практически напрямую из `distribution_center`:

- `dc_bk`;
- `dc_name`;
- `region`;
- `city`;
- `is_active`;
- `updated_at`.

Soft-deleted DC остаётся в контракте.

## `contract.v_batch`

Из `batch`:

- `batch_bk`;
- `sku`;
- `series_no`;
- `manufactured_date`;
- `expiry_date`;
- `received_at`;
- `updated_at`.

## `contract.v_purchase_line`

JOIN `purchase_line` → `purchase_order`:

- `purchase_bk`;
- `line_no`;
- `supplier_bk` ← purchase_order;
- `dc_bk` ← purchase_order;
- `sku`;
- `batch_bk`;
- `ordered_at` ← purchase_order;
- `received_at` ← `batch.received_at` через `batch_bk`;
- `quantity`;
- `unit_cost`;
- `line_cost` ← вычисляется как `quantity * unit_cost`;
- `currency`;
- `updated_at`.

## `contract.v_movement`

Из `movement` + `batch`:

- `movement_bk`;
- `batch_bk`;
- `sku` ← batch;
- `movement_type`;
- `src_type`;
- `src_bk`;
- `dst_type`;
- `dst_bk`;
- `qty`;
- `dispatched_at`;
- `moved_at`;
- `updated_at`.

## `contract.v_stock`

Из `stock` + `batch`:

- `location_type`;
- `location_bk`;
- `sku` ← batch;
- `batch_bk`;
- `qty_on_hand`;
- `updated_at`.

---

# Ограничения и проверки из контракта

Кроме I1/I2/I7/I9/P1, checker проверяет:

- C13: `expiry_date > manufactured_date`;
- C14: `(sku, series_no)` уникальна;
- C15: остатки неотрицательны;
- C16: `qty > 0`, источник != получатель, обе стороны не NULL одновременно;
- C17: `dispatched_at <= moved_at`;
- C18: в `contract.v_purchase_line` `line_cost = quantity * unit_cost`, при этом `quantity > 0`, `unit_cost >= 0`;
- C19: в `contract.v_purchase_line` `received_at` и `batch_bk` либо оба заполнены, либо оба NULL. Это обеспечивается тем, что `received_at` выводится из `batch.received_at`: пока `batch_bk IS NULL`, `received_at` также NULL;
- C20: movement и stock ссылаются на существующие batch.

Cross-service checker дополнительно проверяет:

- SKU закупок существует в Catalog;
- SKU партии существует в Catalog;
- pharmacy-получатель movement существует в POS.

---

# Принятые решения

1. **Отдельную таблицу приёмки не вводим.** Для требований задания достаточно:
   - `purchase_line.batch_bk`;
   - `batch.received_at`;
   - созданной `batch`;
   - движения `movement_type = 'receipt'`.
   Поле `received_at` в `purchase_line` физически не дублируем; контракт получает его из `batch`.

2. **`movement` — журнал изменений, `stock` — материализованное текущее состояние.**
   Запись movement и изменение stock должны выполняться атомарно средствами БД в одной транзакции. Предпочтительный вариант — DB function/trigger, чтобы приложение не могло записать movement и забыть обновить stock.
   `movement` после вставки считаем неизменяемым: UPDATE/DELETE запрещены, а исправление бизнес-факта оформляется компенсирующим movement. Это не позволяет журналу и materialized stock разъехаться.
   Триггер — `AFTER INSERT`: `BEFORE INSERT` срабатывает до разрешения `ON CONFLICT`, и идемпотентная повторная вставка того же movement меняет stock, хотя строка не вставляется.

3. **Отдельный справочник `movement_type` не вводим.**
   Набор фиксирован контрактом и удобно защищается CHECK:
   `receipt | transfer | sale_writeoff | return | writeoff`.
   При этом одного CHECK по самому `movement_type` недостаточно: добавляем ещё составной CHECK по `movement_type + src_type + dst_type`, чтобы физически запретить нелогичные маршруты.

4. **Отдельную таблицу endpoints/locations не вводим.**
   Оставляем полиморфные пары `src_type/src_bk` и `dst_type/dst_bk`: часть сущностей находится в других сервисных БД, поэтому отдельная таблица всё равно не дала бы настоящего FK-контроля для pharmacy/customer.


