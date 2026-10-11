INSERT INTO loyalty_level (level_name) VALUES ('gold')
    ON CONFLICT DO NOTHING;
INSERT INTO contact_type (type_name) VALUES ('email')
    ON CONFLICT DO NOTHING;
INSERT INTO consent_type (type_name) VALUES ('marketing')
    ON CONFLICT DO NOTHING;
INSERT INTO customer (customer_bk, birth_year, sex, registered_at)
VALUES ('CUSTOMER-CONTRACT', 1990, 'F', '2025-01-01 10:00+00');
INSERT INTO customer_profile_version
(customer_bk, city, region, loyalty_level_id, valid_from, is_current)
SELECT 'CUSTOMER-CONTRACT', 'Moscow', 'Moscow', id, '2025-01-01 10:00+00', true
FROM loyalty_level WHERE level_name = 'gold';
INSERT INTO consent (consent_bk, customer_bk, consent_type_id, issued_at)
SELECT 'CONSENT-CONTRACT', 'CUSTOMER-CONTRACT', id, '2025-01-02 10:00+00'
FROM consent_type WHERE type_name = 'marketing';
INSERT INTO loyalty_card
(card_bk, customer_bk, issued_at, status, bonus_balance)
VALUES ('CARD-CONTRACT', 'CUSTOMER-CONTRACT', '2025-01-03 10:00+00', 'active', 125.50);
INSERT INTO customer (customer_bk, registered_at)
VALUES ('CUSTOMER-REVOKED-CONTRACT', '2025-01-01 10:00+00');
INSERT INTO consent (consent_bk, customer_bk, consent_type_id, issued_at, revoked_at)
SELECT 'CONSENT-REVOKED-CONTRACT', 'CUSTOMER-REVOKED-CONTRACT', id,
       '2025-01-02 10:00+00', '2025-01-03 10:00+00'
FROM consent_type WHERE type_name = 'marketing';

SELECT 'SMOKE:crm_customer', count(*)
  FROM contract.v_customer
 WHERE customer_bk = 'CUSTOMER-CONTRACT'
   AND city = 'Moscow' AND region = 'Moscow'
   AND loyalty_level = 'gold' AND marketing_opt_in;
SELECT 'SMOKE:crm_card', count(*)
  FROM contract.v_loyalty_card
 WHERE card_bk = 'CARD-CONTRACT' AND bonus_balance = 125.50;
SELECT 'SMOKE:crm_revoked_marketing', count(*)
  FROM contract.v_customer
 WHERE customer_bk = 'CUSTOMER-REVOKED-CONTRACT' AND NOT marketing_opt_in;
