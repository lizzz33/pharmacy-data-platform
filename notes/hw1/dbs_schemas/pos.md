# pos_service_db

## Назначение

POS отвечает за аптеки, кассы, смены и кассовые документы — продажи и возвраты.

Главный вопрос этой базы: **что, где, когда, кому и на каких условиях было продано или возвращено**.

Идём по пути минимализма: добавляем только то, что требуется README, контрактом, инвариантами или необходимо для физической целостности модели.

---

# Что известно из README

Для POS явно заданы требования:

- кассовый документ бывает двух типов: `sale` и `refund`;
- возврат всегда ссылается на исходную продажу;
- вернуть больше, чем было продано, нельзя;
- документ оформляется на открытой смене конкретной кассы;
- покупатель может быть не идентифицирован;
- документ может быть оплачен несколькими способами;
- сумма оплат должна совпадать с суммой документа;
- продажа всегда идёт из конкретной партии;
- рецептурный препарат нельзя отпустить без рецепта;
- историческая продажа должна сохранять snapshot цены, названия SKU и признака рецептурности.

---

# Что требует контракт

POS должен отдавать четыре представления:

- `contract.v_pharmacy`;
- `contract.v_receipt`;
- `contract.v_receipt_line`;
- `contract.v_payment`.

---

# Предлагаемая физическая модель

Семь основных таблиц:

1. `pharmacy`
2. `cash_register`
3. `cashier`
4. `shift`
5. `receipt`
6. `receipt_line`
7. `payment`

## Правило по ключам

Если у сущности есть стабильный business key, используем его как PRIMARY KEY:

- `pharmacy_bk`;
- `register_bk`;
- `cashier_bk`;
- `shift_bk`;
- `receipt_bk`.

Для строк документа и оплат естественные ключи составные:

```text
(receipt_bk, line_no)
(receipt_bk, payment_no)
```

---

## 1. `pharmacy`

Справочник аптек.

Поля:

- `pharmacy_bk TEXT PRIMARY KEY`;
- `pharmacy_name TEXT NOT NULL`;
- `region TEXT NOT NULL`;
- `city TEXT NOT NULL`;
- `address TEXT NOT NULL`;
- `opened_at DATE NOT NULL`;
- `closed_at DATE NULL`;
- `is_active BOOLEAN NOT NULL`;
- `deleted_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- `pharmacy_bk` уникален и неизменяем;
- если `closed_at IS NOT NULL`, то `closed_at >= opened_at`;
- soft delete вместо физического DELETE;
- `updated_at` обновляется автоматически.

---

## 2. `cash_register`

Касса внутри аптеки.

Поля:

- `register_bk TEXT PRIMARY KEY`;
- `pharmacy_bk TEXT NOT NULL` — FK → `pharmacy.pharmacy_bk`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

---

## 3. `cashier`

Кассир.

Поля:

- `cashier_bk TEXT PRIMARY KEY`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Дополнительные персональные поля пока не добавляем: контракту нужен только `cashier_bk`.

---

## 4. `shift`

Кассовая смена конкретной кассы.

Поля:

- `shift_bk TEXT PRIMARY KEY`;
- `register_bk TEXT NOT NULL` — FK → `cash_register.register_bk`;
- `opened_at TIMESTAMPTZ NOT NULL`;
- `closed_at TIMESTAMPTZ NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Ограничения:

- если `closed_at IS NOT NULL`, то `closed_at > opened_at`;
- документ может быть создан только внутри интервала своей смены.

---

## 5. `receipt`

Кассовый документ — продажа или возврат.

Поля:

- `receipt_bk TEXT PRIMARY KEY`;
- `shift_bk TEXT NOT NULL` — FK → `shift.shift_bk`;
- `cashier_bk TEXT NOT NULL` — FK → `cashier.cashier_bk`;
- `customer_bk TEXT NULL` — логическая ссылка на CRM;
- `receipt_dt TIMESTAMPTZ NOT NULL`;
- `doc_type TEXT NOT NULL`;
- `parent_receipt_bk TEXT NULL` — self-FK → `receipt.receipt_bk`;
- `total_amount NUMERIC(..., 2) NOT NULL`;
- `currency TEXT NOT NULL`;
- `prescription_bk TEXT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

Допустимые `doc_type`:

```text
sale | refund
```

Ограничения:

- `total_amount >= 0`;
- валюта — 3 uppercase символа;
- для `sale` → `parent_receipt_bk IS NULL`;
- для `refund` → `parent_receipt_bk IS NOT NULL`;
- родитель возврата должен быть документом типа `sale`;
- `receipt_dt` должен попадать в интервал открытой смены;
- сумма строк документа должна совпадать с `total_amount` — deferred constraint trigger;
- сумма оплат должна совпадать с `total_amount` — deferred constraint trigger.

`discount_amount` физически в `receipt` не храним. В `contract.v_receipt` вычисляем его как сумму `line_discount` всех строк документа. Процент скидки отдельно не вводим: контракт требует именно денежную сумму скидки, а не процент.

### Как получить pharmacy_bk

Физически `pharmacy_bk` в receipt не дублируем:

```text
receipt -> shift -> cash_register -> pharmacy
```

В `contract.v_receipt` он получается JOIN-ом.

---

## 6. `receipt_line`

Одна позиция кассового документа.

Поля:

- `receipt_bk TEXT NOT NULL` — FK → `receipt.receipt_bk`;
- `line_no INT NOT NULL`;
- `sku TEXT NOT NULL` — логическая ссылка на Catalog;
- `batch_bk TEXT NOT NULL` — логическая ссылка на WMS;
- `quantity NUMERIC(...) NOT NULL`;
- `unit_price NUMERIC(..., 2) NOT NULL` — snapshot цены;
- `line_discount NUMERIC(..., 2) NOT NULL`;
- `is_rx_snapshot BOOLEAN NOT NULL`;
- `sku_name_snapshot TEXT NOT NULL`;
- `batch_expiry_date_snapshot DATE NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

PRIMARY KEY:

```text
(receipt_bk, line_no)
```

Ограничения:

- `line_no > 0`;
- `quantity > 0`;
- `unit_price >= 0`;
- `line_discount >= 0`;
- `line_discount <= quantity * unit_price`.

`line_amount` физически не храним. В `contract.v_receipt_line` вычисляем:

```text
line_amount = quantity * unit_price - line_discount
```

Так значение не может рассинхронизироваться с исходными полями.

### Почему здесь snapshot-поля

README прямо требует сохранять на момент продажи:

- цену;
- название SKU;
- признак рецептурности.

Поэтому `unit_price`, `sku_name_snapshot`, `is_rx_snapshot` физически хранятся в POS и не пересчитываются задним числом из Catalog.

### Почему добавлен batch_expiry_date_snapshot

Инвариант I8 требует, чтобы **сама POS-база физически не позволила продать просроченную партию**, но `expiry_date` принадлежит WMS и межбазовый FK/constraint невозможен.

Поэтому при формировании строки продажи POS сохраняет локальный snapshot срока годности партии:

```text
batch_expiry_date_snapshot
```

и DB constraint trigger проверяет:

```text
(receipt.receipt_dt AT TIME ZONE 'UTC')::date <= receipt_line.batch_expiry_date_snapshot
```

Дата чека берётся в UTC, а не в `TimeZone` сессии: иначе один и тот же чек принимается в одной сессии и отклоняется в другой. Так же дату чека считает checker в X07.

Это дополнительное физическое поле не входит в contract view.

### I10 — Rx без рецепта

`is_rx_snapshot` уже хранится локально.

Constraint trigger проверяет:

```text
если в документе есть строка с is_rx_snapshot = true
→ receipt.prescription_bk IS NOT NULL
```

---

## 7. `payment`

Одна оплата документа.

Поля:

- `receipt_bk TEXT NOT NULL` — FK → `receipt.receipt_bk`;
- `payment_no INT NOT NULL`;
- `payment_method TEXT NOT NULL`;
- `amount NUMERIC(..., 2) NOT NULL`;
- `currency TEXT NOT NULL`;
- `created_at TIMESTAMPTZ NOT NULL`;
- `updated_at TIMESTAMPTZ NOT NULL`.

PRIMARY KEY:

```text
(receipt_bk, payment_no)
```

Допустимые способы оплаты:

```text
cash | card | bonus | certificate
```

Ограничения:

- `payment_no > 0`;
- `amount >= 0`;
- валюта — 3 uppercase символа;
- сумма всех payment одного документа должна совпадать с `receipt.total_amount`.

---

# Как модель покрывает README

## 1. Продажа и возврат

- `receipt.doc_type = sale | refund`;
- `parent_receipt_bk` обязателен только для refund;
- parent должен быть sale.

## 2. Возврат не превышает проданное

I11 реализуется constraint trigger.

Для refund:

- берём исходный `parent_receipt_bk`;
- считаем количество проданного SKU;
- вычитаем уже оформленные возвраты;
- новый возврат не может превышать остаток доступного к возврату количества.

Проверка срабатывает не только на изменение возврата, но и на изменение самой продажи (чека и его строк): после правки продажи перепроверяются все её возвраты. Иначе можно оформить возврат, а потом уменьшить количество в продаже.

## 3. Документ оформляется на открытой смене конкретной кассы

Связь:

```text
receipt -> shift -> cash_register -> pharmacy
```

Проверяем, что `receipt_dt` находится между `shift.opened_at` и `shift.closed_at` либо смена ещё открыта.

## 4. Покупатель может быть неизвестен

`receipt.customer_bk` nullable.

Это логическая cross-service ссылка на CRM без FOREIGN KEY.

## 5. Несколько способов оплаты

У одного receipt может быть много строк `payment`.

I12 проверяет:

```text
SUM(payment.amount) = receipt.total_amount
```

## 6. Продажа из конкретной партии

Каждая `receipt_line` обязательно содержит `batch_bk`.

## 7. Rx только по рецепту

`is_rx_snapshot` хранится в строке.

Если хотя бы одна строка Rx, у receipt обязан быть `prescription_bk`.


## Как моделируем возврат денег

Отдельную таблицу для возвратных платежей не вводим. Используем ту же таблицу `payment`, что и для обычной продажи.

Смысл payment определяется типом документа:

```text
sale   + payment -> деньги получены от покупателя
refund + payment -> деньги возвращены покупателю
```

Суммы храним положительными и для sale, и для refund.

Пример продажи:

```text
receipt:
doc_type = sale
total_amount = 1000

payment:
card  = 700
bonus = 300
```

Пример возврата:

```text
receipt:
doc_type = refund
parent_receipt_bk = исходная sale
total_amount = 400

receipt_line:
что именно и сколько вернули

payment:
card = 400
```

Таким образом:

- `receipt_line` refund-документа отвечает на вопрос **что и сколько вернули**;
- `payment` refund-документа отвечает на вопрос **каким способом и какую сумму вернули покупателю**;
- отдельный `direction` в payment не нужен — он выводится из `receipt.doc_type`;
- I12 одинаков для sale и refund:

```text
SUM(payment.amount) = receipt.total_amount
```

Задание не требует, чтобы способ возврата совпадал со способом исходной оплаты, поэтому такого ограничения пока не вводим.


---

# Контрактные представления

## `contract.v_pharmacy`

Практически напрямую из `pharmacy`:

- `pharmacy_bk`;
- `pharmacy_name`;
- `region`;
- `city`;
- `address`;
- `opened_at`;
- `closed_at`;
- `is_active`;
- `updated_at`.

Soft delete справочника не скрывает сущность из контракта: на неё ссылается история (чеки, закупки, перемещения). С фильтром `deleted_at IS NULL` удаление аптеки или SKU с историей ломает C07/C08, X01/X03/X06. Статус виден через `is_active`; `CHECK (deleted_at IS NULL OR NOT is_active)` (`ck_<table>_deleted_inactive`) не даёт удалённой записи остаться активной. Из контракта по soft delete исчезает только клиент — этого требует контракт.

Soft-deleted pharmacy остаётся в view.

## `contract.v_receipt`

JOIN `receipt → shift → cash_register → pharmacy`:

- `receipt_bk`;
- `pharmacy_bk`;
- `customer_bk`;
- `cashier_bk`;
- `shift_bk`;
- `receipt_dt`;
- `doc_type`;
- `parent_receipt_bk`;
- `total_amount`;
- `discount_amount` ← `SUM(receipt_line.line_discount)`;
- `currency`;
- `prescription_bk`;
- `updated_at`.

## `contract.v_receipt_line`

Из `receipt_line`:

- `receipt_bk`;
- `line_no`;
- `sku`;
- `batch_bk`;
- `quantity`;
- `unit_price`;
- `line_discount`;
- `line_amount` ← `quantity * unit_price - line_discount`;
- `is_rx_snapshot`;
- `sku_name_snapshot`;
- `updated_at`.

`batch_expiry_date_snapshot` наружу не отдаём.

## `contract.v_payment`

Из `payment`:

- `receipt_bk`;
- `payment_no`;
- `payment_method`;
- `amount`;
- `currency`;
- `updated_at`.

---

# Ограничения и проверки

Для POS напрямую важны:

- I1 — уникальность BK;
- I2 — неизменяемость BK;
- I3 — сумма документа совпадает с суммой строк;
- I4 — арифметика позиции;
- I8 — нельзя продать просроченную партию;
- I10 — Rx нельзя продать без рецепта;
- I11 — возврат не превышает проданное;
- I12 — сумма оплат совпадает с документом;
- P1 — `updated_at` обновляется автоматически.

Checker дополнительно проверяет:

- C01 — сумма receipt = сумма line_amount;
- C02 — сумма payment = total_amount;
- C03 — арифметика receipt_line;
- C04 — Rx не продан без prescription;
- C05 — refund имеет parent, sale не имеет;
- C06 — возврат не превышает продажу;
- C07 — receipt_line ссылается на существующий receipt;
- C08 — receipt ссылается на существующую pharmacy.

Cross-service checker дополнительно проверяет:

- SKU позиции существует в Catalog;
- batch позиции существует в WMS;
- customer receipt существует в CRM, если он указан;
- на дату продажи существовала действующая цена;
- SKU позиции совпадает с SKU партии;
- snapshot `is_rx` не противоречит Catalog в пределах допуска.

---

# Принятые решения

1. `doc_type` пока оставляем строкой с CHECK по `sale | refund`; отдельный справочник не нужен.
2. `payment_method` пока оставляем строкой с CHECK по `cash | card | bonus | certificate`; отдельный справочник не нужен.
3. Географию аптеки не нормализуем: `region`, `city`, `address` остаются обычными текстовыми полями `pharmacy`.
4. `line_amount` физически не храним; вычисляем в contract view как `quantity * unit_price - line_discount`.
5. `discount_amount` физически не храним; вычисляем в `contract.v_receipt` как сумму `line_discount` по строкам документа. Отдельный процент скидки не вводим, потому что контракт его не требует.
6. `batch_expiry_date_snapshot` сохраняем локально в POS ради I8 — запрета продажи просроченной партии средствами самой POS-БД.
7. I11 (возврат не превышает проданное) реализуем constraint trigger, учитывающим исходную продажу и предыдущие возвраты.
8. Отдельную таблицу `prescription` пока не вводим: для задания достаточно `prescription_bk` в receipt.
