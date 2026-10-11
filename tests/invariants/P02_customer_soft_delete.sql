INSERT INTO customer (customer_bk, registered_at) VALUES ('CUSTOMER-P02', clock_timestamp());
INSERT INTO contact_type (type_name) VALUES ('email')
    ON CONFLICT DO NOTHING;
INSERT INTO customer_contact (contact_bk, customer_bk, contact_type_id, contact_value)
SELECT 'CONTACT-P02', 'CUSTOMER-P02', id, 'person@example.test'
FROM contact_type WHERE type_name = 'email';
UPDATE customer SET deleted_at = clock_timestamp() WHERE customer_bk = 'CUSTOMER-P02';
SELECT EXISTS (SELECT 1 FROM customer WHERE customer_bk = 'CUSTOMER-P02')
   AND NOT EXISTS (SELECT 1 FROM customer_contact WHERE customer_bk = 'CUSTOMER-P02' AND contact_value IS NOT NULL)
   AND NOT EXISTS (SELECT 1 FROM contract.v_customer WHERE customer_bk = 'CUSTOMER-P02')
   AS ok;
