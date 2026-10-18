BEGIN;

CREATE SCHEMA contract;

CREATE VIEW contract.v_sku AS
WITH ingredients AS (
    SELECT sai.sku_bk,
           string_agg(ai.inn_name, ', ' ORDER BY ai.inn_name) AS inn_name,
           max(GREATEST(sai.updated_at, ai.updated_at)) AS updated_at
      FROM sku_active_ingredient sai
      JOIN active_ingredient ai ON ai.ingredient_bk = sai.ingredient_bk
     GROUP BY sai.sku_bk
)
SELECT s.sku_bk AS sku,
       sv.sku_name,
       i.inn_name,
       m.manufacturer_name,
       df.drug_form_name AS drug_form,
       sc.category_name AS category,
       sv.is_rx,
       s.is_vital,
       s.pack_qty,
       s.is_active,
       GREATEST(
           s.updated_at,
           sv.updated_at,
           m.updated_at,
           sc.updated_at,
           COALESCE(df.updated_at, s.updated_at),
           COALESCE(i.updated_at, s.updated_at)
       ) AS updated_at
  FROM sku s
  JOIN sku_version sv ON sv.sku_bk = s.sku_bk AND sv.is_current
  JOIN manufacturer m ON m.manufacturer_bk = s.manufacturer_bk
  JOIN sku_category sc ON sc.id = sv.category_id
  LEFT JOIN drug_form df ON df.drug_form_bk = s.drug_form_bk
  LEFT JOIN ingredients i ON i.sku_bk = s.sku_bk;

CREATE VIEW contract.v_price AS
SELECT pv.sku_bk AS sku,
       ps.scope_name AS price_scope,
       pv.scope_bk,
       pv.price,
       pv.currency,
       pv.valid_from,
       pv.valid_to,
       pv.is_current,
       GREATEST(pv.updated_at, ps.updated_at, s.updated_at) AS updated_at
  FROM price_version pv
  JOIN price_scope ps ON ps.id = pv.price_scope_id
  JOIN sku s ON s.sku_bk = pv.sku_bk;

COMMIT;
