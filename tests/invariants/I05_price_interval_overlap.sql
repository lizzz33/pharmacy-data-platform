INSERT INTO manufacturer (manufacturer_bk, manufacturer_name) VALUES ('MFR-I05', 'Invariant I05 Manufacturer');
INSERT INTO sku_category (category_name) VALUES ('otc')
    ON CONFLICT DO NOTHING;
INSERT INTO price_scope (scope_name) VALUES ('chain')
    ON CONFLICT DO NOTHING;
INSERT INTO sku (sku_bk, manufacturer_bk, pack_qty, is_vital, is_active)
VALUES ('SKU-I05', 'MFR-I05', 1, false, true);
INSERT INTO price_version
(sku_bk, price_scope_id, scope_bk, price, currency, valid_from, valid_to, is_current)
SELECT 'SKU-I05', id, 'ALL', 100, 'RUB', '2026-01-01', '2026-06-01', false
FROM price_scope WHERE scope_name = 'chain';

INSERT INTO price_version
(sku_bk, price_scope_id, scope_bk, price, currency, valid_from, valid_to, is_current)
SELECT 'SKU-I05', id, 'ALL', 110, 'RUB', '2026-05-01', '2026-07-01', false
FROM price_scope WHERE scope_name = 'chain';
