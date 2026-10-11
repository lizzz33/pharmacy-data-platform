INSERT INTO manufacturer (manufacturer_bk, manufacturer_name) VALUES ('MFR-I06', 'Invariant I06 Manufacturer');
INSERT INTO sku_category (category_name) VALUES ('otc')
    ON CONFLICT DO NOTHING;
INSERT INTO sku (sku_bk, manufacturer_bk, pack_qty, is_vital, is_active)
VALUES ('SKU-I06', 'MFR-I06', 1, false, true);
INSERT INTO sku_version (sku_bk, sku_name, category_id, is_rx, valid_from, is_current)
SELECT 'SKU-I06', 'I06 first', id, false, '2026-01-01', true
FROM sku_category WHERE category_name = 'otc';

INSERT INTO sku_version (sku_bk, sku_name, category_id, is_rx, valid_from, is_current)
SELECT 'SKU-I06', 'I06 second', id, false, '2026-02-01', true
FROM sku_category WHERE category_name = 'otc';
