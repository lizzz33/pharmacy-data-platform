INSERT INTO manufacturer (manufacturer_bk, manufacturer_name)
VALUES ('MFR-CONTRACT', 'Contract Manufacturer');
INSERT INTO drug_form (drug_form_bk, drug_form_name)
VALUES ('FORM-CONTRACT', 'Contract Form');
INSERT INTO active_ingredient (ingredient_bk, inn_name)
VALUES ('ING-CONTRACT-B', 'Ingredient B'), ('ING-CONTRACT-A', 'Ingredient A');
INSERT INTO sku_category (category_name) VALUES ('otc')
    ON CONFLICT DO NOTHING;
INSERT INTO price_scope (scope_name) VALUES ('chain')
    ON CONFLICT DO NOTHING;
INSERT INTO sku
(sku_bk, manufacturer_bk, drug_form_bk, pack_qty, is_vital, is_active)
VALUES ('SKU-CONTRACT', 'MFR-CONTRACT', 'FORM-CONTRACT', 20, true, true);
INSERT INTO sku_version
(sku_bk, sku_name, category_id, is_rx, valid_from, is_current)
SELECT 'SKU-CONTRACT', 'Contract SKU', id, false, '2025-01-01', true
FROM sku_category WHERE category_name = 'otc';
INSERT INTO sku_active_ingredient (sku_bk, ingredient_bk)
VALUES ('SKU-CONTRACT', 'ING-CONTRACT-B'), ('SKU-CONTRACT', 'ING-CONTRACT-A');
INSERT INTO price_version
(sku_bk, price_scope_id, scope_bk, price, currency, valid_from, valid_to, is_current)
SELECT 'SKU-CONTRACT', id, 'ALL', 250.00, 'RUB', '2025-01-01', NULL, true
FROM price_scope WHERE scope_name = 'chain';

SELECT 'SMOKE:catalog_sku', count(*)
  FROM contract.v_sku
 WHERE sku = 'SKU-CONTRACT' AND sku_name = 'Contract SKU'
   AND inn_name = 'Ingredient A, Ingredient B'
   AND manufacturer_name = 'Contract Manufacturer'
   AND drug_form = 'Contract Form' AND category = 'otc' AND NOT is_rx;
UPDATE active_ingredient SET deleted_at = clock_timestamp()
 WHERE ingredient_bk = 'ING-CONTRACT-B';
SELECT 'SMOKE:catalog_deleted_ingredient', count(*)
  FROM contract.v_sku
 WHERE sku = 'SKU-CONTRACT' AND inn_name = 'Ingredient A, Ingredient B'
   AND updated_at = (SELECT updated_at FROM active_ingredient
                      WHERE ingredient_bk = 'ING-CONTRACT-B');
SELECT 'SMOKE:catalog_price', count(*)
  FROM contract.v_price
 WHERE sku = 'SKU-CONTRACT' AND price_scope = 'chain'
   AND scope_bk = 'ALL' AND price = 250.00 AND is_current;
