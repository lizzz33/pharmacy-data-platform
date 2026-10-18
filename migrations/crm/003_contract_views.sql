BEGIN;

CREATE SCHEMA contract;

CREATE VIEW contract.v_customer AS
WITH marketing AS (
    SELECT c.customer_bk,
           bool_or(c.revoked_at IS NULL AND ct.deleted_at IS NULL) AS marketing_opt_in,
           max(GREATEST(c.updated_at, ct.updated_at)) AS updated_at
      FROM consent c
      JOIN consent_type ct
        ON ct.id = c.consent_type_id
       AND ct.type_name = 'marketing'
     GROUP BY c.customer_bk
)
SELECT c.customer_bk,
       c.birth_year,
       c.sex,
       cp.city,
       cp.region,
       ll.level_name AS loyalty_level,
       COALESCE(m.marketing_opt_in, false) AS marketing_opt_in,
       c.registered_at,
       GREATEST(
           c.updated_at,
           COALESCE(cp.updated_at, c.updated_at),
           COALESCE(ll.updated_at, c.updated_at),
           COALESCE(m.updated_at, c.updated_at)
       ) AS updated_at
  FROM customer c
  LEFT JOIN customer_profile_version cp
    ON cp.customer_bk = c.customer_bk AND cp.is_current
  LEFT JOIN loyalty_level ll ON ll.id = cp.loyalty_level_id
  LEFT JOIN marketing m ON m.customer_bk = c.customer_bk
 WHERE c.deleted_at IS NULL;

CREATE VIEW contract.v_loyalty_card AS
SELECT lc.card_bk,
       lc.customer_bk,
       lc.issued_at,
       lc.closed_at,
       lc.status,
       lc.bonus_balance,
       lc.updated_at
  FROM loyalty_card lc
  JOIN customer c USING (customer_bk)
 WHERE c.deleted_at IS NULL;

COMMIT;
