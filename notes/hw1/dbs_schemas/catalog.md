# catalog_service_db

## Назначение

Catalog отвечает за товарную номенклатуру и цены.

Главный вопрос этой базы: **что именно продаётся и по какой цене это должно продаваться**.

Идём по пути минимализма: добавляем только то, что требуется README, контрактом, инвариантами или нужно для нормальной структуры данных.

---

# Что известно из README

Для Catalog явно заданы требования:

- один МНН может соответствовать многим SKU;
- один SKU может содержать несколько действующих веществ;
- категории:
  - `rx`;
  - `otc`;
  - `supplement`;
  - `device`;
  - `cosmetics`;
- есть признак ЖНВЛП `is_vital`;
- цена действует в интервале времени;
- цена имеет область действия:
  - вся сеть;
  - регион;
  - конкретная аптека;
- более узкая область приоритетнее широкой;
- название SKU, категория и `is_rx` могут меняться со временем.

---

# Что требует контракт

Catalog должен отдавать два представления:

- `contract.v_sku` — текущее состояние SKU;
- `contract.v_price` — все версии цен.

`contract.v_sku` требует:

- `sku`;
- `sku_name`;
- `inn_name`;
- `manufacturer_name`;
- `drug_form`;
- `category`;
- `is_rx`;
- `is_vital`;
- `pack_qty`;
- `is_active`;
- `updated_at`.

`contract.v_price` требует:

- `sku`;
- `price_scope_id` → справочник `price_scope`;
- `scope_bk`;
- `price`;
- `currency`;
- `valid_from`;
- `valid_to`;
- `is_current`;
- `updated_at`.

---

# Предлагаемая физическая модель

Девять таблиц:

1. `manufacturer`
2. `drug_form`
3. `active_ingredient`
4. `sku_category`
5. `price_scope`
6. `sku`
7. `sku_version`
8. `sku_active_ingredient`
9. `price_version`

## Правило по ключам

Если у сущности есть стабильный business key, используем его сразу как PRIMARY KEY.

Поэтому:

- `sku_bk` — PK;
- `manufacturer_bk` — PK;
- `drug_form_bk` — PK;
- `ingredient_bk` — PK.

Для version-таблиц отдельный внешний business key не нужен: это версии другой бизнес-сущности. Там используем технический `BIGINT GENERATED ... AS IDENTITY`.

---

## 1. `manufacturer`

Справочник производителей.

Поля:

- `manufacturer_bk TEXT PRIMARY KEY`;
- `manufacturer_name TEXT NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- `manufacturer_bk` уникален и неизменяем;
- `manufacturer_name UNIQUE NOT NULL`;
- soft delete вместо физического DELETE;
- `updated_at` обновляется автоматически.

---

## 2. `drug_form`

Справочник лекарственных форм.

Примеры: таблетки, раствор, мазь.

Поля:

- `drug_form_bk TEXT PRIMARY KEY`;
- `drug_form_name TEXT UNIQUE NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Для нелекарственного SKU ссылка может быть NULL.

---

## 3. `active_ingredient`

Справочник МНН / действующих веществ.

Поля:

- `ingredient_bk TEXT PRIMARY KEY`;
- `inn_name TEXT UNIQUE NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

---

## 4. `sku_category`

Небольшой справочник категорий SKU.

Поля:

- `id BIGINT GENERATED ... AS IDENTITY PRIMARY KEY`;
- `category_name TEXT UNIQUE NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Минимальный набор значений из README:

```text
rx | otc | supplement | device | cosmetics
```

Категория остаётся историзируемым атрибутом SKU, но в `sku_version` хранится уже FK на этот справочник.

---

## 5. `price_scope`

Небольшой справочник областей действия цены.

Поля:

- `id BIGINT GENERATED ... AS IDENTITY PRIMARY KEY`;
- `scope_name TEXT UNIQUE NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Минимальный набор значений из контракта:

```text
chain | region | pharmacy
```

Важно: этот справочник нормализует только **тип области действия**. Сам `scope_bk` остаётся в `price_version`:

- для `chain` → `ALL`;
- для `region` → код региона;
- для `pharmacy` → `pharmacy_bk` из POS.

---

## 6. `sku`

Стабильная идентичность товарной позиции и те атрибуты, для которых README не требует отдельной истории.

Поля:

- `sku_bk TEXT PRIMARY KEY`;
- `manufacturer_bk TEXT NOT NULL` — FK → `manufacturer.manufacturer_bk`;
- `drug_form_bk TEXT NULL` — FK → `drug_form.drug_form_bk`;
- `pack_qty NUMERIC(...) NOT NULL`;
- `is_vital BOOLEAN NOT NULL`;
- `is_active BOOLEAN NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- `sku_bk` уникален и неизменяем;
- `pack_qty > 0`;
- soft delete вместо физического DELETE.

### Почему здесь нет sku_name / category / is_rx

README прямо говорит, что:

- название SKU меняется;
- категория меняется;
- признак рецептурности меняется.

Поэтому эти поля лежат в `sku_version`.

---

## 7. `sku_version`

История изменяемого состояния SKU.

Поля:

- `id BIGINT GENERATED ... AS IDENTITY PRIMARY KEY`;
- `sku_bk TEXT NOT NULL` — FK → `sku.sku_bk`;
- `sku_name TEXT NOT NULL`;
- `category_id BIGINT NOT NULL` — FK → `sku_category.id`;
- `is_rx BOOLEAN NOT NULL`;
- `valid_from TIMESTAMPTZ NOT NULL`;
- `is_current BOOLEAN NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- для одного SKU только одна строка с `is_current = true`;
- для одного SKU `valid_from` уникален;
- `category_id` обязан ссылаться на существующую категорию.

`valid_to` здесь не обязателен. Как и в CRM profile history, конец действия версии определяется началом следующей версии, а текущую версию быстро находим по `is_current = true`.

---

## 8. `sku_active_ingredient`

Связующая таблица M:N между SKU и действующими веществами.

Поля:

- `sku_bk TEXT NOT NULL` — FK → `sku.sku_bk`;
- `ingredient_bk TEXT NOT NULL` — FK → `active_ingredient.ingredient_bk`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

PRIMARY KEY:

```text
(sku_bk, ingredient_bk)
```

Это покрывает оба требования README:

- один МНН может быть у многих SKU;
- один SKU может иметь несколько МНН.

### Как отдать один inn_name в contract

В физической модели остаётся нормальная M:N-связь.

В `contract.v_sku` несколько МНН агрегируем детерминированно, например:

```text
string_agg(inn_name, ', ' ORDER BY inn_name)
```

Для нелекарственного SKU результат может быть NULL.

---

## 9. `price_version`

История цен. Здесь `valid_to` обязателен для модели, потому что контракт и checker работают именно с полуоткрытыми интервалами `[valid_from, valid_to)`.

Поля:

- `id BIGINT GENERATED ... AS IDENTITY PRIMARY KEY`;
- `sku_bk TEXT NOT NULL` — FK → `sku.sku_bk`;
- `price_scope_id BIGINT NOT NULL` — FK → `price_scope.id`;
- `scope_bk TEXT NOT NULL`;
- `price NUMERIC(..., 2) NOT NULL`;
- `currency TEXT NOT NULL`;
- `valid_from TIMESTAMPTZ NOT NULL`;
- `valid_to TIMESTAMPTZ NULL`;
- `is_current BOOLEAN NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Семантика `scope_bk` определяется значением связанного `price_scope.scope_name`:

- `chain` → `ALL`;
- `region` → код региона;
- `pharmacy` → `pharmacy_bk` из POS.

Ограничения:

- `price > 0`;
- валюта — 3 uppercase символа;
- `valid_to > valid_from`, если `valid_to IS NOT NULL`;
- интервалы одной комбинации `(sku_bk, price_scope_id, scope_bk)` не пересекаются;
- только одна текущая версия на одну комбинацию;
- `is_current` согласован с `valid_to`: `CHECK (is_current = (valid_to IS NULL))`. Текущая версия — ровно открытая; C11 детерминирован и не зависит от `now()`.

### I5 — непересекающиеся интервалы

Используем `btree_gist` + `EXCLUDE USING gist` по:

- `sku_bk WITH =`;
- `price_scope_id WITH =`;
- `scope_bk WITH =`;
- `tstzrange(valid_from, valid_to, '[)') WITH &&`.

### I6 — одна текущая версия

Partial unique index:

```text
UNIQUE (sku_bk, price_scope_id, scope_bk)
WHERE is_current = true
```

---

# Как модель покрывает README

## 1. Один МНН соответствует многим SKU, бывают комбинированные препараты

Покрытие:

- `active_ingredient`;
- `sku_active_ingredient`;
- связь M:N.

## 2. Категории имеют фиксированный набор

Покрытие:

- `sku_category` хранит допустимый набор;
- `sku_version.category_id` ссылается на справочник.

## 3. ЖНВЛП

Покрытие:

- `sku.is_vital`.

Историю `is_vital` пока не вводим, потому что README не говорит о её изменяемости.

## 4. Цена действует во времени и имеет scope

Покрытие:

- `price_version.valid_from / valid_to`;
- `price_scope`;
- `scope_bk`;
- история хранится SCD2-интервалами.

Приоритет `pharmacy > region > chain` — бизнес-правило выбора цены, которое будет использоваться приложением/генератором и cross-service checker. Оно не требует отдельной физической таблицы.

## 5. Название, категория и is_rx меняются

Покрытие:

- отдельная `sku_version`;
- текущая версия определяется через `is_current`;
- `contract.v_sku` показывает только текущую версию.

---

# Контрактные представления

## `contract.v_sku`

JOIN текущей `sku_version` с `sku`, `manufacturer`, `drug_form`, `active_ingredient`.

Сопоставление:

- `sku` ← `sku.sku_bk`;
- `sku_name` ← текущая `sku_version.sku_name`;
- `inn_name` ← агрегат действующих веществ;
- `manufacturer_name` ← `manufacturer.manufacturer_name`;
- `drug_form` ← `drug_form.drug_form_name`;
- `category` ← `sku_category.category_name` через текущую `sku_version`;
- `is_rx` ← текущая `sku_version.is_rx`;
- `is_vital` ← `sku.is_vital`;
- `pack_qty` ← `sku.pack_qty`;
- `is_active` ← `sku.is_active`;
- `updated_at` ← актуальное время последнего изменения текущего состояния.

Soft delete справочника не скрывает сущность из контракта: на неё ссылается история (чеки, закупки, партии, цены). С фильтром `deleted_at IS NULL` удаление аптеки или SKU с историей ломает C07/C08, X01/X03/X06. Статус виден через `is_active`; `CHECK (deleted_at IS NULL OR NOT is_active)` (`ck_<table>_deleted_inactive`) не даёт удалённой записи остаться активной. Из контракта по soft delete исчезает только клиент — этого требует контракт.
Удалённые производитель, категория, лекарственная форма и МНН тоже показываются в атрибутах `v_sku` — правило одно для всех. Скрывать их выборочно нельзя: `manufacturer_name` и `category` в контракте `NOT NULL`.

Soft-deleted SKU в view не отдаём.

## `contract.v_price`

JOIN `price_version` → `price_scope`:

- `sku` ← `sku_bk`;
- `price_scope` ← `price_scope.scope_name`;
- `scope_bk`;
- `price`;
- `currency`;
- `valid_from`;
- `valid_to`;
- `is_current`;
- `updated_at`.

---

# Ограничения и проверки

Для Catalog напрямую важны:

- I1 — уникальность BK;
- I2 — неизменяемость BK;
- I5 — интервалы действия цены не пересекаются;
- I6 — только одна текущая версия;
- P1 — автоматический `updated_at`.

Checker дополнительно проверяет:

- C09 — интервалы цен не пересекаются;
- C10 — одна текущая версия цены на scope;
- C11 — `is_current` согласован с `valid_to`;
- C12 — `price > 0`, валюта состоит из 3 uppercase символов.

---

# Принятые решения

1. **Историзируем только явно меняющиеся атрибуты SKU:** `sku_name`, `category`, `is_rx`. `manufacturer`, `drug_form`, `pack_qty`, `is_vital` пока считаем стабильными.
2. **Состав SKU не историзируем.** `sku_active_ingredient` хранит текущее стабильное соответствие SKU ↔ МНН.
3. **Отдельный business key для `price_version` не вводим.** Версия цены — это версия состояния, а не самостоятельная бизнес-сущность; технического ID достаточно.
4. **`price_version.is_current` храним физически**, а не вычисляем через `now()` в VIEW. Это соответствует замечанию контракта и не создаёт расхождения между мастером и репликой.
5. **`contract.v_sku.updated_at` должен отражать последнее изменение любого компонента текущего представления SKU.** Практически это `GREATEST(...updated_at...)` по `sku`, текущей `sku_version`, `manufacturer`, `drug_form` и агрегированным данным МНН/связи.
6. **Категории SKU и типы price scope вынесены в небольшие справочники** `sku_category` и `price_scope`. Это наше решение по нормализации, а не прямое требование задания.
7. **Отдельный справочник регионов в Catalog не вводим.** Для `price_scope = region` поле `scope_bk` хранит внешний код региона как логический business key области действия.

# Осталось уточнить

- Нужно будет аккуратно определить, как именно считать агрегированный `updated_at` по M:N связи SKU ↔ МНН в SQL VIEW.
