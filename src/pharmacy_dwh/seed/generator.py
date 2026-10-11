from __future__ import annotations

import random
from collections import defaultdict
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP

from .config import Settings
from .context import BatchData, PlannedLine, PlannedReceipt, SeedContext, SkuData, SkuVersion
from .db import ids_by_name, insert_rows, transaction

UTC = timezone.utc
CENT = Decimal("0.01")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _dt(day, hour: int = 10, minute: int = 0) -> datetime:
    return datetime.combine(day, time(hour, minute), UTC)


class Generator:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.ctx = SeedContext()
        self.ns = settings.namespace
        self.scale = settings.scale
        self.audit_ts = _dt(settings.as_of)
        self.start_day = settings.as_of - timedelta(days=548)
        self.start_ts = _dt(self.start_day, 0)

    def run(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        counts.update(self._catalog())
        counts.update(self._crm())
        counts.update(self._pos_master())
        self._plan_batches()
        self._plan_receipts()
        counts.update(self._wms())
        counts.update(self._pos_transactions())
        return counts

    def _catalog(self) -> dict[str, int]:
        categories = ("rx", "otc", "supplement", "device", "cosmetics")
        forms = ("tablets", "capsules", "solution", "spray", "cream", "gel", "drops", "powder")
        with transaction(self.settings, "catalog") as cur:
            insert_rows(cur, """
                INSERT INTO sku_category (category_name, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, [(x, self.audit_ts, self.audit_ts) for x in categories])
            insert_rows(cur, """
                INSERT INTO price_scope (scope_name, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, [(x, self.audit_ts, self.audit_ts) for x in ("chain", "region", "pharmacy")])
            manufacturers = [
                (f"MFR-{self.ns}-{i:03d}", f"Manufacturer {self.ns} {i:03d}", self.audit_ts, self.audit_ts)
                for i in range(1, max(16, self.scale.sku // 18) + 1)
            ]
            insert_rows(cur, """
                INSERT INTO manufacturer
                    (manufacturer_bk, manufacturer_name, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, manufacturers)
            form_rows = [
                (f"FORM-{self.ns}-{i:02d}", f"{name.title()} {self.ns}", self.audit_ts, self.audit_ts)
                for i, name in enumerate(forms, 1)
            ]
            insert_rows(cur, """
                INSERT INTO drug_form (drug_form_bk, drug_form_name, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, form_rows)
            ingredient_count = max(40, self.scale.sku // 4)
            ingredients = [
                (f"ING-{self.ns}-{i:04d}", f"Ingredient {self.ns} {i:04d}", self.audit_ts, self.audit_ts)
                for i in range(1, ingredient_count + 1)
            ]
            insert_rows(cur, """
                INSERT INTO active_ingredient
                    (ingredient_bk, inn_name, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, ingredients)
            category_ids = ids_by_name(cur, "sku_category", "category_name")
            scope_ids = ids_by_name(cur, "price_scope", "scope_name")

            sku_rows = []
            version_rows = []
            ingredient_rows = []
            price_rows = []
            price_cut_1 = self.start_ts + timedelta(days=183)
            price_cut_2 = self.start_ts + timedelta(days=366)
            history_cut = self.start_ts + timedelta(days=275)
            for i in range(1, self.scale.sku + 1):
                bk = f"SKU-{self.ns}-{i:05d}"
                if i <= max(20, self.scale.sku // 10):
                    category = "otc" if i % 4 else "rx"
                    base_price = Decimal(950 + (i % 17) * 35)
                else:
                    category = categories[(i * 7) % len(categories)]
                    base_price = Decimal(110 + (i * 29) % 390)
                is_rx = category == "rx"
                drug_form = None if category in {"device", "cosmetics"} else form_rows[i % len(form_rows)][0]
                mfr = manufacturers[i % len(manufacturers)][0]
                sku_rows.append((bk, mfr, drug_form, Decimal(1 + i % 50), i % 8 == 0, True,
                                 self.audit_ts, self.audit_ts))
                current_name = f"Pharmacy product {self.ns} {i:05d}"
                versions: list[SkuVersion] = []
                if i % 4 == 0:
                    old_category = category
                    old_rx = is_rx
                    if i > self.scale.sku - 5:
                        old_category = "rx" if category != "rx" else "otc"
                        old_rx = not is_rx
                    old_name = f"Legacy product {self.ns} {i:05d}"
                    version_rows.append((bk, old_name, category_ids[old_category], old_rx,
                                         self.start_ts - timedelta(days=60), False,
                                         self.audit_ts, self.audit_ts))
                    version_rows.append((bk, current_name, category_ids[category], is_rx,
                                         history_cut, True, self.audit_ts, self.audit_ts))
                    versions.extend((
                        SkuVersion(self.start_ts - timedelta(days=60), old_name, old_category, old_rx),
                        SkuVersion(history_cut, current_name, category, is_rx),
                    ))
                else:
                    version_rows.append((bk, current_name, category_ids[category], is_rx,
                                         self.start_ts - timedelta(days=60), True,
                                         self.audit_ts, self.audit_ts))
                    versions.append(SkuVersion(self.start_ts - timedelta(days=60), current_name, category, is_rx))
                if category not in {"device", "cosmetics"}:
                    ingredient_rows.append((bk, ingredients[(i * 11) % ingredient_count][0],
                                            self.audit_ts, self.audit_ts))
                    if i % 5 == 0:
                        ingredient_rows.append((bk, ingredients[(i * 11 + 7) % ingredient_count][0],
                                                self.audit_ts, self.audit_ts))
                for valid_from, valid_to, factor, current in (
                    (self.start_ts - timedelta(days=60), price_cut_1, Decimal("0.90"), False),
                    (price_cut_1, price_cut_2, Decimal("0.95"), False),
                    (price_cut_2, None, Decimal("1.00"), True),
                ):
                    price_rows.append((bk, scope_ids["chain"], "ALL", _money(base_price * factor),
                                       "RUB", valid_from, valid_to, current,
                                       self.audit_ts, self.audit_ts))
                self.ctx.skus.append(SkuData(bk, i, base_price, tuple(versions)))

            insert_rows(cur, """
                INSERT INTO sku
                    (sku_bk, manufacturer_bk, drug_form_bk, pack_qty, is_vital, is_active,
                     created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, sku_rows)
            insert_rows(cur, """
                INSERT INTO sku_version
                    (sku_bk, sku_name, category_id, is_rx, valid_from, is_current,
                     created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, version_rows)
            insert_rows(cur, """
                INSERT INTO sku_active_ingredient
                    (sku_bk, ingredient_bk, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, ingredient_rows)
            insert_rows(cur, """
                INSERT INTO price_version
                    (sku_bk, price_scope_id, scope_bk, price, currency, valid_from, valid_to,
                     is_current, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, price_rows)
        return {"catalog.sku": len(sku_rows), "catalog.price_version": len(price_rows)}

    def _crm(self) -> dict[str, int]:
        levels = ("basic", "silver", "gold", "platinum")
        cities = (("Moscow", "Moscow"), ("Kazan", "Tatarstan"), ("Perm", "Perm Krai"),
                  ("Samara", "Samara Oblast"), ("Omsk", "Omsk Oblast"),
                  ("Sochi", "Krasnodar Krai"))
        with transaction(self.settings, "crm") as cur:
            for table, column, values in (
                ("loyalty_level", "level_name", levels),
                ("contact_type", "type_name", ("email", "phone")),
                ("consent_type", "type_name", ("marketing", "personal_data")),
            ):
                insert_rows(cur, f"""
                    INSERT INTO {table} ({column}, created_at, updated_at)
                    VALUES %s ON CONFLICT DO NOTHING
                """, [(x, self.audit_ts, self.audit_ts) for x in values])
            level_ids = ids_by_name(cur, "loyalty_level", "level_name")
            contact_ids = ids_by_name(cur, "contact_type", "type_name")
            consent_ids = ids_by_name(cur, "consent_type", "type_name")
            customers = []
            profiles = []
            contacts = []
            consents = []
            cards = []
            for i in range(1, self.scale.customers + 1):
                bk = f"CUSTOMER-{self.ns}-{i:06d}"
                registered = self.start_ts - timedelta(days=30 + i % 900)
                customers.append((bk, 1945 + (i * 13) % 61, "F" if i % 2 else "M", registered,
                                  self.audit_ts, self.audit_ts))
                city, region = cities[i % len(cities)]
                level = levels[min(3, (i * 7) % 10 // 3)]
                if i % 6 == 0:
                    profiles.append((bk, city, region, level_ids["basic"], registered, False,
                                     self.audit_ts, self.audit_ts))
                    profiles.append((bk, city, region, level_ids[level], self.start_ts + timedelta(days=250), True,
                                     self.audit_ts, self.audit_ts))
                else:
                    profiles.append((bk, city, region, level_ids[level], registered, True,
                                     self.audit_ts, self.audit_ts))
                contacts.append((f"CONTACT-{self.ns}-{i:06d}-E", bk, contact_ids["email"],
                                 f"customer{i}.{self.ns.lower()}@example.test", self.audit_ts, self.audit_ts))
                if i % 3:
                    contacts.append((f"CONTACT-{self.ns}-{i:06d}-P", bk, contact_ids["phone"],
                                     f"+79{(self.settings.seed % 100):02d}{i:07d}"[-12:],
                                     self.audit_ts, self.audit_ts))
                consents.append((f"CONSENT-{self.ns}-{i:06d}-P", bk, consent_ids["personal_data"],
                                 registered, None, self.audit_ts, self.audit_ts))
                if i % 5:
                    consents.append((f"CONSENT-{self.ns}-{i:06d}-M", bk, consent_ids["marketing"],
                                     registered + timedelta(days=1), None, self.audit_ts, self.audit_ts))
                if i <= self.scale.cards:
                    issued = registered + timedelta(days=2)
                    cards.append((f"CARD-{self.ns}-{i:06d}", bk, issued, None, "active",
                                  _money(Decimal((i * 37) % 5000) / 10), self.audit_ts, self.audit_ts))
            insert_rows(cur, """
                INSERT INTO customer
                    (customer_bk, birth_year, sex, registered_at, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, customers)
            insert_rows(cur, """
                INSERT INTO customer_profile_version
                    (customer_bk, city, region, loyalty_level_id, valid_from, is_current,
                     created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, profiles)
            insert_rows(cur, """
                INSERT INTO customer_contact
                    (contact_bk, customer_bk, contact_type_id, contact_value, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, contacts)
            insert_rows(cur, """
                INSERT INTO consent
                    (consent_bk, customer_bk, consent_type_id, issued_at, revoked_at,
                     created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, consents)
            insert_rows(cur, """
                INSERT INTO loyalty_card
                    (card_bk, customer_bk, issued_at, closed_at, status, bonus_balance,
                     created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, cards)
        self.ctx.customers = [row[0] for row in customers]
        return {"crm.customer": len(customers), "crm.loyalty_card": len(cards)}

    def _pos_master(self) -> dict[str, int]:
        regions = (("Moscow", "Moscow"), ("Tatarstan", "Kazan"), ("Perm Krai", "Perm"),
                   ("Samara Oblast", "Samara"), ("Omsk Oblast", "Omsk"),
                   ("Krasnodar Krai", "Sochi"))
        pharmacies = []
        registers = []
        cashiers = []
        shifts = []
        for i in range(1, self.scale.pharmacies + 1):
            ph = f"PH-{self.ns}-{i:04d}"
            region, city = regions[(i - 1) % len(regions)]
            pharmacies.append((ph, f"Pharmacy 108 {self.ns} #{i}", region, city,
                               f"{i * 3} Central Street", self.start_day - timedelta(days=900 + i),
                               True, self.audit_ts, self.audit_ts))
            reg = f"REG-{self.ns}-{i:04d}"
            cashier = f"CASHIER-{self.ns}-{i:04d}"
            shift = f"SHIFT-{self.ns}-{i:04d}"
            registers.append((reg, ph, self.audit_ts, self.audit_ts))
            cashiers.append((cashier, self.audit_ts, self.audit_ts))
            shifts.append((shift, reg, self.start_ts - timedelta(days=1),
                           _dt(self.settings.as_of + timedelta(days=2), 23),
                           self.audit_ts, self.audit_ts))
        with transaction(self.settings, "pos") as cur:
            insert_rows(cur, """
                INSERT INTO pharmacy
                    (pharmacy_bk, pharmacy_name, region, city, address, opened_at, is_active,
                     created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, pharmacies)
            insert_rows(cur, """
                INSERT INTO cash_register
                    (register_bk, pharmacy_bk, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, registers)
            insert_rows(cur, """
                INSERT INTO cashier (cashier_bk, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, cashiers)
            insert_rows(cur, """
                INSERT INTO shift
                    (shift_bk, register_bk, opened_at, closed_at, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, shifts)
        self.ctx.pharmacies = [row[0] for row in pharmacies]
        return {"pos.pharmacy": len(pharmacies)}

    def _plan_batches(self) -> None:
        for sku in self.ctx.skus:
            for slot in range(self.scale.batches_per_sku):
                received = self.start_ts - timedelta(days=30) + timedelta(days=slot * 90)
                self.ctx.batches.append(BatchData(
                    bk=f"BATCH-{self.ns}-{sku.index:05d}-{slot + 1:02d}",
                    sku=sku.bk,
                    received_at=received,
                    expiry_date=self.settings.as_of + timedelta(days=540 + slot * 30),
                ))

    def _sale_day(self, rng: random.Random) -> datetime:
        days = [self.start_day + timedelta(days=i) for i in range(548)]
        weekday_weights = (1.00, 1.00, 1.05, 1.10, 1.30, 1.65, 1.30)
        day = rng.choices(days, weights=[weekday_weights[d.isoweekday() - 1] for d in days], k=1)[0]
        return _dt(day, 8 + rng.randrange(13), rng.randrange(60))

    def _price_at(self, sku: SkuData, timestamp: datetime) -> Decimal:
        elapsed = (timestamp - self.start_ts).days
        factor = Decimal("0.90") if elapsed < 183 else Decimal("0.95") if elapsed < 366 else Decimal("1.00")
        return _money(sku.base_price * factor)

    def _plan_receipts(self) -> None:
        rng = random.Random(self.settings.seed ^ 0x505)
        ph_weights = [1.0 + (self.scale.pharmacies - i) / self.scale.pharmacies * 2.2
                      for i in range(self.scale.pharmacies)]
        popular_cut = max(20, self.scale.sku // 10)
        batches_by_sku: dict[str, list[BatchData]] = defaultdict(list)
        for batch in self.ctx.batches:
            batches_by_sku[batch.sku].append(batch)
        sales: list[PlannedReceipt] = []
        for i in range(1, self.scale.sales + 1):
            ph_index = rng.choices(range(self.scale.pharmacies), weights=ph_weights, k=1)[0]
            ph = self.ctx.pharmacies[ph_index]
            timestamp = self._sale_day(rng)
            customer = None if rng.random() < 0.43 else rng.choice(self.ctx.customers)
            lines = []
            for _ in range(3):
                if rng.random() < 0.72:
                    sku = self.ctx.skus[rng.randrange(popular_cut)]
                else:
                    sku = self.ctx.skus[rng.randrange(popular_cut, self.scale.sku)]
                eligible = [b for b in batches_by_sku[sku.bk]
                            if b.received_at + timedelta(days=1) <= timestamp]
                batch = rng.choice(eligible or batches_by_sku[sku.bk][:1])
                version = sku.at(timestamp)
                quantity = Decimal(2 if rng.random() < 0.14 else 1)
                unit_price = self._price_at(sku, timestamp)
                discount = _money(quantity * unit_price * Decimal("0.05")) if rng.random() < 0.12 else Decimal("0.00")
                lines.append(PlannedLine(sku.bk, batch.bk, quantity, unit_price, discount,
                                         version.is_rx, version.name, batch.expiry_date))
            has_rx = any(line.is_rx for line in lines)
            bk = f"RCPT-{self.ns}-{i:07d}"
            sales.append(PlannedReceipt(
                bk, ph, customer, f"CASHIER-{self.ns}-{ph_index + 1:04d}",
                f"SHIFT-{self.ns}-{ph_index + 1:04d}", timestamp, "sale", None,
                f"PRESCRIPTION-{self.ns}-{i:07d}" if has_rx else None, tuple(lines),
            ))
        refunds: list[PlannedReceipt] = []
        refund_parents = rng.sample(sales, self.scale.refunds)
        for i, parent in enumerate(refund_parents, 1):
            line = parent.lines[0]
            refund_line = PlannedLine(line.sku, line.batch_bk, Decimal(1), line.unit_price,
                                      Decimal("0.00"), line.is_rx, line.sku_name, line.expiry_date)
            timestamp = min(parent.timestamp + timedelta(days=1), _dt(self.settings.as_of, 22))
            refunds.append(PlannedReceipt(
                f"REFUND-{self.ns}-{i:06d}", parent.pharmacy_bk, parent.customer_bk,
                parent.cashier_bk, parent.shift_bk, timestamp, "refund", parent.bk,
                parent.prescription_bk if line.is_rx else None, (refund_line,),
            ))
        self.ctx.receipts = sales + refunds

    def _wms(self) -> dict[str, int]:
        suppliers = [
            (f"SUP-{self.ns}-{i:03d}", f"Distributor {self.ns} {i:03d}",
             ("RU", "BY", "KZ", "DE", "IN")[i % 5], True, self.audit_ts, self.audit_ts)
            for i in range(1, max(12, self.scale.sku // 35) + 1)
        ]
        dcs = [
            (f"DC-{self.ns}-{i:02d}", f"Distribution center {self.ns} {i}",
             ("Moscow", "Tatarstan", "Perm Krai", "Samara Oblast")[i - 1],
             ("Moscow", "Kazan", "Perm", "Samara")[i - 1], True,
             self.audit_ts, self.audit_ts)
            for i in range(1, 5)
        ]
        batch_rows = []
        batch_by_bk = {b.bk: b for b in self.ctx.batches}
        for i, batch in enumerate(self.ctx.batches, 1):
            batch_rows.append((batch.bk, batch.sku, f"SERIES-{self.ns}-{i:06d}",
                               batch.received_at.date() - timedelta(days=120), batch.expiry_date,
                               batch.received_at, self.audit_ts, self.audit_ts))
        po_count = (self.scale.purchase_lines + 2) // 3
        purchase_orders = []
        purchase_lines = []
        for po_i in range(1, po_count + 1):
            po_bk = f"PO-{self.ns}-{po_i:06d}"
            supplier = suppliers[(po_i - 1) % len(suppliers)][0]
            dc = dcs[(po_i - 1) % len(dcs)][0]
            purchase_orders.append((po_bk, supplier, dc, self.start_ts - timedelta(days=45),
                                    self.audit_ts, self.audit_ts))
            for line_no in range(1, 4):
                idx = (po_i - 1) * 3 + line_no - 1
                if idx >= self.scale.purchase_lines:
                    break
                if idx < len(self.ctx.batches):
                    batch = self.ctx.batches[idx]
                    sku = batch.sku
                    batch_bk = batch.bk
                else:
                    sku = self.ctx.skus[idx % len(self.ctx.skus)].bk
                    batch_bk = None
                unit_cost = _money(self.ctx.skus[idx % len(self.ctx.skus)].base_price * Decimal("0.55"))
                purchase_lines.append((po_bk, line_no, sku, batch_bk, Decimal(300), unit_cost,
                                       "RUB", self.audit_ts, self.audit_ts))

        sold_qty: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal(0))
        sale_lines: list[tuple[PlannedReceipt, int, PlannedLine]] = []
        for receipt in self.ctx.receipts:
            if receipt.doc_type != "sale":
                continue
            for line_no, line in enumerate(receipt.lines, 1):
                sold_qty[(line.batch_bk, receipt.pharmacy_bk)] += line.quantity
                sale_lines.append((receipt, line_no, line))
        outgoing_by_batch: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
        for (batch_bk, _), qty in sold_qty.items():
            outgoing_by_batch[batch_bk] += qty + Decimal(5)
        movements = []
        dc_by_batch: dict[str, str] = {}
        for i, batch in enumerate(self.ctx.batches, 1):
            dc = dcs[(i - 1) % len(dcs)][0]
            dc_by_batch[batch.bk] = dc
            supplier = suppliers[(i - 1) % len(suppliers)][0]
            receipt_qty = outgoing_by_batch[batch.bk] + Decimal(100)
            movements.append((f"MOV-{self.ns}-IN-{i:07d}", batch.bk, "receipt", "supplier",
                              supplier, "dc", dc, receipt_qty,
                              batch.received_at - timedelta(days=1), batch.received_at,
                              self.audit_ts, self.audit_ts))
        for i, ((batch_bk, ph), qty) in enumerate(sorted(sold_qty.items()), 1):
            batch = batch_by_bk[batch_bk]
            dc = dc_by_batch[batch_bk]
            movements.append((f"MOV-{self.ns}-TR-{i:07d}", batch_bk, "transfer", "dc", dc,
                              "pharmacy", ph, qty + Decimal(5), batch.received_at,
                              batch.received_at + timedelta(days=1), self.audit_ts, self.audit_ts))
        for i, (receipt, line_no, line) in enumerate(sale_lines, 1):
            movements.append((f"MOV-{self.ns}-SALE-{i:08d}", line.batch_bk, "sale_writeoff",
                              "pharmacy", receipt.pharmacy_bk, "customer",
                              receipt.customer_bk or "ANONYMOUS", line.quantity,
                              receipt.timestamp, receipt.timestamp, self.audit_ts, self.audit_ts))

        with transaction(self.settings, "wms") as cur:
            insert_rows(cur, """
                INSERT INTO supplier
                    (supplier_bk, supplier_name, country, is_active, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, suppliers)
            insert_rows(cur, """
                INSERT INTO distribution_center
                    (dc_bk, dc_name, region, city, is_active, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, dcs)
            insert_rows(cur, """
                INSERT INTO purchase_order
                    (purchase_bk, supplier_bk, dc_bk, ordered_at, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, purchase_orders)
            insert_rows(cur, """
                INSERT INTO batch
                    (batch_bk, sku, series_no, manufactured_date, expiry_date, received_at,
                     created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, batch_rows)
            insert_rows(cur, """
                INSERT INTO purchase_line
                    (purchase_bk, line_no, sku, batch_bk, quantity, unit_cost, currency,
                     created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, purchase_lines)
            insert_rows(cur, """
                INSERT INTO movement
                    (movement_bk, batch_bk, movement_type, src_type, src_bk, dst_type, dst_bk,
                     qty, dispatched_at, moved_at, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, movements, page_size=1_000)
        return {"wms.batch": len(batch_rows), "wms.purchase_line": len(purchase_lines),
                "wms.movement": len(movements), "wms.stock_expected_min": len(self.ctx.batches) + len(sold_qty)}

    def _pos_transactions(self) -> dict[str, int]:
        receipt_rows = []
        line_rows = []
        payment_rows = []
        for receipt in self.ctx.receipts:
            receipt_rows.append((receipt.bk, receipt.shift_bk, receipt.cashier_bk, receipt.customer_bk,
                                 receipt.timestamp, receipt.doc_type, receipt.parent_bk, receipt.total,
                                 "RUB", receipt.prescription_bk, self.audit_ts, self.audit_ts))
            for line_no, line in enumerate(receipt.lines, 1):
                line_rows.append((receipt.bk, line_no, line.sku, line.batch_bk, line.quantity,
                                  line.unit_price, line.discount, line.is_rx, line.sku_name,
                                  line.expiry_date, self.audit_ts, self.audit_ts))
            split = receipt.doc_type == "sale" and int(receipt.bk.rsplit("-", 1)[1]) % 10 == 0
            if split:
                first = _money(receipt.total * Decimal("0.30"))
                payment_rows.append((receipt.bk, 1, "bonus", first, "RUB", self.audit_ts, self.audit_ts))
                payment_rows.append((receipt.bk, 2, "card", receipt.total - first, "RUB",
                                     self.audit_ts, self.audit_ts))
            else:
                method = "cash" if int(receipt.bk.rsplit("-", 1)[1]) % 4 == 0 else "card"
                payment_rows.append((receipt.bk, 1, method, receipt.total, "RUB",
                                     self.audit_ts, self.audit_ts))
        with transaction(self.settings, "pos") as cur:
            cur.execute("SET CONSTRAINTS ALL DEFERRED")
            insert_rows(cur, """
                INSERT INTO receipt
                    (receipt_bk, shift_bk, cashier_bk, customer_bk, receipt_dt, doc_type,
                     parent_receipt_bk, total_amount, currency, prescription_bk,
                     created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, receipt_rows, page_size=2_000)
            insert_rows(cur, """
                INSERT INTO receipt_line
                    (receipt_bk, line_no, sku, batch_bk, quantity, unit_price, line_discount,
                     is_rx_snapshot, sku_name_snapshot, batch_expiry_date_snapshot,
                     created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, line_rows, page_size=2_000)
            insert_rows(cur, """
                INSERT INTO payment
                    (receipt_bk, payment_no, payment_method, amount, currency, created_at, updated_at)
                VALUES %s ON CONFLICT DO NOTHING
            """, payment_rows, page_size=2_000)
        return {"pos.receipt": len(receipt_rows), "pos.receipt_line": len(line_rows),
                "pos.payment": len(payment_rows)}

