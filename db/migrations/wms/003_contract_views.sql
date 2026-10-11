BEGIN;

CREATE SCHEMA contract;

CREATE VIEW contract.v_supplier AS
SELECT supplier_bk,
       supplier_name,
       country,
       is_active,
       updated_at
  FROM supplier;

CREATE VIEW contract.v_distribution_center AS
SELECT dc_bk,
       dc_name,
       region,
       city,
       is_active,
       updated_at
  FROM distribution_center;

CREATE VIEW contract.v_batch AS
SELECT batch_bk,
       sku,
       series_no,
       manufactured_date,
       expiry_date,
       received_at,
       updated_at
  FROM batch;

CREATE VIEW contract.v_purchase_line AS
SELECT pl.purchase_bk,
       pl.line_no,
       po.supplier_bk,
       po.dc_bk,
       pl.sku,
       pl.batch_bk,
       po.ordered_at,
       b.received_at,
       pl.quantity,
       pl.unit_cost,
       pl.quantity * pl.unit_cost AS line_cost,
       pl.currency,
       GREATEST(
           pl.updated_at,
           po.updated_at,
           COALESCE(b.updated_at, pl.updated_at)
       ) AS updated_at
  FROM purchase_line pl
  JOIN purchase_order po USING (purchase_bk)
  LEFT JOIN batch b USING (batch_bk);

CREATE VIEW contract.v_movement AS
SELECT m.movement_bk,
       m.batch_bk,
       b.sku,
       m.movement_type,
       m.src_type,
       m.src_bk,
       m.dst_type,
       m.dst_bk,
       m.qty,
       m.dispatched_at,
       m.moved_at,
       GREATEST(m.updated_at, b.updated_at) AS updated_at
  FROM movement m
  JOIN batch b USING (batch_bk);

CREATE VIEW contract.v_stock AS
SELECT s.location_type,
       s.location_bk,
       b.sku,
       s.batch_bk,
       s.qty_on_hand,
       GREATEST(s.updated_at, b.updated_at) AS updated_at
  FROM stock s
  JOIN batch b USING (batch_bk);

COMMIT;
