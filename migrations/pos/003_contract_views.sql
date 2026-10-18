BEGIN;

CREATE SCHEMA contract;

CREATE VIEW contract.v_pharmacy AS
SELECT pharmacy_bk,
       pharmacy_name,
       region,
       city,
       address,
       opened_at,
       closed_at,
       is_active,
       updated_at
  FROM pharmacy;

CREATE VIEW contract.v_receipt AS
WITH discounts AS (
    SELECT receipt_bk,
           sum(line_discount) AS discount_amount,
           max(updated_at) AS updated_at
      FROM receipt_line
     GROUP BY receipt_bk
)
SELECT r.receipt_bk,
       p.pharmacy_bk,
       r.customer_bk,
       r.cashier_bk,
       r.shift_bk,
       r.receipt_dt,
       r.doc_type,
       r.parent_receipt_bk,
       r.total_amount,
       COALESCE(d.discount_amount, 0::numeric) AS discount_amount,
       r.currency,
       r.prescription_bk,
       GREATEST(
           r.updated_at,
           s.updated_at,
           cr.updated_at,
           p.updated_at,
           COALESCE(d.updated_at, r.updated_at)
       ) AS updated_at
  FROM receipt r
  JOIN shift s USING (shift_bk)
  JOIN cash_register cr USING (register_bk)
  JOIN pharmacy p ON p.pharmacy_bk = cr.pharmacy_bk
  LEFT JOIN discounts d USING (receipt_bk);

CREATE VIEW contract.v_receipt_line AS
SELECT receipt_bk,
       line_no,
       sku,
       batch_bk,
       quantity,
       unit_price,
       line_discount,
       quantity * unit_price - line_discount AS line_amount,
       is_rx_snapshot,
       sku_name_snapshot,
       updated_at
  FROM receipt_line;

CREATE VIEW contract.v_payment AS
SELECT receipt_bk,
       payment_no,
       payment_method,
       amount,
       currency,
       updated_at
  FROM payment;

COMMIT;
