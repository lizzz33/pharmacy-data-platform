# crm_service_db

## Назначение

CRM отвечает за клиента, его контактные данные, согласия и программу лояльности.

Главный вопрос этой базы: **кто наш клиент и как меняется его клиентский профиль**.

Идём по пути минимализма: добавляем только то, что требуется заданием, контрактом или необходимо для связей и инвариантов.

---

# Что известно из задания

Для CRM явно заданы следующие требования:

- клиент может иметь несколько карт лояльности за жизнь;
- одновременно активна только одна карта;
- согласия версионируются;
- у согласия есть тип, дата выдачи и дата отзыва;
- активное согласие одного типа только одно;
- физически удалять клиента нельзя;
- при soft delete клиент должен исчезнуть из `contract.v_customer`;
- его контакты должны быть обезличены;
- история продаж при этом должна сохраниться;
- наружу CRM отдаёт текущее состояние клиента и карты лояльности.

Контракт `contract.v_customer` требует:

- `customer_bk`;
- `birth_year`;
- `sex`;
- `city`;
- `region`;
- `loyalty_level`;
- `marketing_opt_in`;
- `registered_at`;
- `updated_at`.

---

# Предлагаемая физическая модель

Восемь таблиц:

1. `customer`
2. `customer_profile_version`
3. `customer_contact`
4. `contact_type`
5. `consent`
6. `consent_type`
7. `loyalty_card`
8. `loyalty_level`

## Правило по ключам

Если у сущности есть стабильный business key, используем его сразу как PRIMARY KEY.

Для `customer_contact` тоже вводим собственный `contact_bk`, чтобы связи и идентичность оставались единообразными. Технический `BIGINT GENERATED ... AS IDENTITY` оставляем в основном для небольших справочников типов и version-таблиц, где внешний business key не нужен.

---

## 1. `customer`

Основная сущность клиента.

Поля:

- `customer_bk TEXT PRIMARY KEY`;
- `birth_year INT NULL`;
- `sex TEXT NULL`;
- `registered_at TIMESTAMPTZ NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- `customer_bk` уникален благодаря PRIMARY KEY;
- `customer_bk` неизменяем;
- `sex` ∈ `M | F | NULL`;
- физический DELETE не используем;
- `updated_at` обновляется автоматически.

Примечание по `birth_year`: контракт требует тип `INT NULL`, но не задаёт допустимый диапазон, поэтому отдельный CHECK по году пока не вводим.

---

## 2. `customer_profile_version`

История изменяемого профиля клиента.

Одна строка = одна версия состояния `city / region / loyalty_level` на некотором интервале времени.

Поля:

- `id BIGINT GENERATED ... AS IDENTITY PRIMARY KEY`;
- `customer_bk TEXT NOT NULL` — FK → `customer.customer_bk`;
- `city TEXT NULL`;
- `region TEXT NULL`;
- `loyalty_level_id BIGINT NULL` — FK → `loyalty_level.id`;
- `valid_from TIMESTAMPTZ NOT NULL`;
- `is_current BOOLEAN NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- у клиента только одна строка с `is_current = true`;
- для одного клиента значения `valid_from` должны быть уникальны.

При изменении города, региона или уровня лояльности старой версии ставим `is_current = false`, а новую добавляем отдельной строкой с новым `valid_from` и `is_current = true`.

`valid_to` не храним. Конец действия версии определяется началом следующей версии. Для восстановления состояния на момент времени выбираем последнюю запись с `valid_from <= нужного момента`.

---

## 3. `customer_contact`

Контактные данные клиента.

Хотя отдельный business key для контакта прямо не требуется контрактом, для единообразия модели используем собственный стабильный `contact_bk` вместо технического bigint-id.

Поля:

- `contact_bk TEXT PRIMARY KEY`;
- `customer_bk TEXT NOT NULL` — FK → `customer.customer_bk`;
- `contact_type_id BIGINT NOT NULL` — FK → `contact_type.id`;
- `contact_value TEXT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

### Soft delete клиента

При soft delete клиента:

- `customer.deleted_at` заполняется;
- `customer_contact.contact_value` обнуляется или обезличивается;
- запись клиента физически остаётся;
- в `contract.v_customer` клиент больше не показывается.

---

## 4. `contact_type`

Справочник типов контактов.

Примеры значений:

- `phone`;
- `email`.

Поля:

- `id BIGINT GENERATED ... AS IDENTITY PRIMARY KEY`;
- `type_name TEXT UNIQUE NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Связь:

```text
contact_type 1 --- N customer_contact
```

---

## 5. `consent`

История согласий клиента.

Одна строка = одна выданная версия согласия.

Поля:

- `consent_bk TEXT PRIMARY KEY`;
- `customer_bk TEXT NOT NULL` — FK → `customer.customer_bk`;
- `consent_type_id BIGINT NOT NULL` — FK → `consent_type.id`;
- `issued_at TIMESTAMPTZ NOT NULL`;
- `revoked_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- `revoked_at > issued_at`, если отзыв есть;
- у клиента только одно активное согласие каждого типа;
- в `consent_type` должны существовать как минимум типы `personal_data` и `marketing`.

Практический вариант:

```text
UNIQUE (customer_bk, consent_type_id)
WHERE revoked_at IS NULL
```

### Как получить `marketing_opt_in`

В `contract.v_customer`:

```text
marketing_opt_in = true
```

если существует активное согласие, у которого:

```text
consent_type.type_name = 'marketing'
AND consent.revoked_at IS NULL
AND consent_type.deleted_at IS NULL
```

Удалённый тип согласия даёт `marketing_opt_in = false`. Это не скрытие значения справочника (их `v_customer` показывает и после удаления, например `loyalty_level`), а смысл согласия: согласие несуществующего типа не действует.

---

## 6. `consent_type`

Справочник типов согласий.

Примеры значений:

- `personal_data`;
- `marketing`.

Поля:

- `id BIGINT GENERATED ... AS IDENTITY PRIMARY KEY`;
- `type_name TEXT UNIQUE NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Связь:

```text
consent_type 1 --- N consent
```

---

## 7. `loyalty_card`

Карты лояльности клиента.

Поля:

- `card_bk TEXT PRIMARY KEY`;
- `customer_bk TEXT NOT NULL` — FK → `customer.customer_bk`;
- `issued_at TIMESTAMPTZ NOT NULL`;
- `closed_at TIMESTAMPTZ NULL`;
- `status TEXT NOT NULL` — `active | blocked | closed`;
- `bonus_balance NUMERIC(...) NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- `status` ∈ `active | blocked | closed`;
- `bonus_balance >= 0`;
- `closed_at >= issued_at`, если дата закрытия есть;
- если `closed_at IS NOT NULL`, карта не может иметь `status = 'active'`;
- у одного клиента одновременно только одна активная карта.

Практический вариант:

```text
UNIQUE (customer_bk)
WHERE status = 'active'
```

---

## 8. `loyalty_level`

Небольшой справочник уровней программы лояльности.

Поля:

- `id BIGINT GENERATED ... AS IDENTITY PRIMARY KEY`;
- `level_name TEXT UNIQUE NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Связь:

```text
loyalty_level 1 --- N customer_profile_version
```

---

# Предварительная ER-структура

```text
loyalty_level
     1
     |
     N
customer_profile_version
     N
     |
     1
  customer
   /  |  \
  /   |   \
 N    N    N
contact consent loyalty_card
  |       |
  1       1
  |       |
contact_type consent_type
```

---

# Как модель покрывает пункты README про клиентов

## 1. Несколько карт за жизнь, активная только одна

Требование README:

> Клиент может за жизнь получить несколько карт (перевыпуск), активная — одна.

Покрытие модели:

- `loyalty_card.customer_bk` позволяет хранить много карт одного клиента;
- старые карты не удаляются;
- при перевыпуске старая карта переводится из `active` в `blocked` или `closed`, затем создаётся новая;
- partial UNIQUE index:

```text
UNIQUE (customer_bk)
WHERE status = 'active'
```

гарантирует не более одной активной карты на клиента.

## 2. Согласия версионируются, активное согласие типа только одно

Требование README:

> Согласия версионируются: тип согласия, дата выдачи, дата отзыва. Активное согласие данного типа только одно.

Покрытие модели:

- каждая выдача согласия — отдельная строка `consent`;
- тип вынесен в `consent_type`;
- `issued_at` хранит начало действия;
- `revoked_at` хранит отзыв;
- отсутствие `revoked_at` означает активное согласие;
- partial UNIQUE index:

```text
UNIQUE (customer_bk, consent_type_id)
WHERE revoked_at IS NULL
```

не позволяет иметь две активные версии одного типа одновременно.

Минимально нужны типы:

- `personal_data`;
- `marketing`.

Текущее поле `marketing_opt_in` в контракте вычисляется по активному `marketing` consent.

## 3. Клиента нельзя физически удалить, но нужно убрать из аналитики и обезличить контакты

Требование README:

> Физическое удаление клиента запрещено, но по запросу клиента он обязан исчезнуть из аналитики, а его контакты — быть обезличены.

Покрытие модели:

- `customer.deleted_at` реализует soft delete;
- физическая строка клиента остаётся;
- при soft delete все `customer_contact.contact_value` обнуляются или обезличиваются;
- `contract.v_customer` содержит фильтр `customer.deleted_at IS NULL`;
- удалённый уровень лояльности показывается в `loyalty_level` как есть — то же правило, что для справочников в `v_sku`;
- исторические связи по `customer_bk` остаются валидными;
- контакты отдельно не историзируем, чтобы после обезличивания старые PII не оставались в history.

---

# Контрактные представления

## `contract.v_customer`

Сопоставление:

- `customer_bk` → `customer.customer_bk`;
- `birth_year` → `customer.birth_year`;
- `sex` → `customer.sex`;
- `city` → текущая `customer_profile_version.city`;
- `region` → текущая `customer_profile_version.region`;
- `loyalty_level` → `loyalty_level.level_name` через текущую `customer_profile_version`;
- `marketing_opt_in` → наличие активного consent типа `marketing`;
- `registered_at` → `customer.registered_at`;
- `updated_at` → актуальное время последнего изменения клиентского состояния.

Условие:

```text
customer.deleted_at IS NULL
```

## `contract.v_loyalty_card`

Сопоставление:

- `card_bk`;
- `customer_bk`;
- `issued_at`;
- `closed_at`;
- `status`;
- `bonus_balance`;
- `updated_at`.

---

# Связанные требования и инварианты

Для CRM напрямую важны:

- I1 — уникальность business key;
- I2 — business key нельзя изменять;
- P1 — `updated_at` обновляется автоматически;
- P2 — soft delete клиента:
  - клиент исчезает из `contract.v_customer`;
  - физическая запись остаётся;
  - контакты обезличены.

Дополнительно модель должна соблюдать:

- только одна активная loyalty card на клиента;
- только одно активное согласие каждого типа на клиента.

---

# Важные выводы по требованиям

## Текущее состояние в contract != отсутствие физической истории

`contract.v_customer` должен отдавать только текущее состояние клиента. Это не запрещает хранить историю во внутренних таблицах.

Для минимальной модели историю стоит хранить только там, где изменение действительно ожидается или прямо требуется заданием.

Предварительно:

- `birth_year` — без истории;
- `sex` — без истории;
- `city`, `region`, `loyalty_level` — храним в `customer_profile_version` с историей;
- контакты — без историзации значений, чтобы soft delete действительно удалял персональные данные;
- consent — история хранится через отдельные версии согласия;
- loyalty cards — история естественно хранится набором карточек одного клиента.

## Ограничения на поля клиента

### `sex`

Контракт явно допускает только:

```text
'M' | 'F' | NULL
```

Следовательно, нужен CHECK.

### `birth_year`

Контракт требует `INT NULL`, но не задаёт допустимый диапазон годов.

Поэтому диапазон вроде `1900..текущий год` можно добавить только как наше отдельное допущение. Это не обязательное требование задания.

## Типы согласий

Из README следуют как минимум два типа:

- `personal_data`;
- `marketing`.

Они должны существовать в `consent_type`.

`marketing_opt_in` в контракте вычисляется по наличию активного согласия типа `marketing`.

## Что значит «согласия версионируются»

Не перезаписываем старую историю согласия.

Пример:

```text
CONS-001: marketing, issued_at=2026-01-10, revoked_at=2026-03-01
CONS-002: marketing, issued_at=2026-05-15, revoked_at=NULL
```

Это две версии / два периода действия согласия одного типа.

Правило:

```text
UNIQUE (customer_bk, consent_type_id)
WHERE revoked_at IS NULL
```

не позволяет иметь две активные версии одного типа одновременно.

## Карты лояльности

Контракт разрешает только статусы:

```text
active | blocked | closed
```

Для минимальной модели отдельный справочник статусов не нужен — достаточно CHECK.

Один клиент может иметь много карт за жизнь, но только одну активную:

```text
UNIQUE (customer_bk)
WHERE status = 'active'
```

При перевыпуске старую карту не удаляем: переводим её из `active` в `closed`/другой допустимый статус и создаём новую.

## Soft delete клиента

Soft delete — это не физический DELETE.

Предлагаемая операция:

1. заполнить `customer.deleted_at`;
2. обезличить все `customer_contact.contact_value` этого клиента;
3. не удалять строку клиента;
4. `contract.v_customer` фильтрует `deleted_at IS NULL`.

Важно: контактные значения не стоит историзировать в отдельной таблице, иначе после soft delete персональные данные останутся в истории. Если когда-либо появится история контактов, обезличивать нужно будет все исторические версии тоже.

## История клиентского профиля

Из требования «история там, где атрибут меняется» следует, что текущая таблица `customer` может оказаться недостаточной для меняющихся атрибутов.

Наиболее естественные кандидаты:

- `city`;
- `region`;
- `loyalty_level`.

Принятое решение — хранить эти поля в `customer_profile_version` по `valid_from` и признаку текущей версии, а в `contract.v_customer` выбирать только текущую запись.

---

# Открытые вопросы

1. Как именно считать `updated_at` в `contract.v_customer`, если изменение consent или customer profile тоже должно считаться изменением состояния клиента?
