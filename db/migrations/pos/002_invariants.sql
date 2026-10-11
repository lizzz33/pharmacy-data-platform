BEGIN;

CREATE FUNCTION reject_business_key_change()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF to_jsonb(NEW) -> TG_ARGV[0] IS DISTINCT FROM to_jsonb(OLD) -> TG_ARGV[0] THEN
        RAISE EXCEPTION 'business key % is immutable', TG_ARGV[0]
            USING ERRCODE = 'P0001';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_pharmacy_bk_immutable BEFORE UPDATE ON pharmacy
    FOR EACH ROW EXECUTE FUNCTION reject_business_key_change('pharmacy_bk');
CREATE TRIGGER trg_cash_register_bk_immutable BEFORE UPDATE ON cash_register
    FOR EACH ROW EXECUTE FUNCTION reject_business_key_change('register_bk');
CREATE TRIGGER trg_cashier_bk_immutable BEFORE UPDATE ON cashier
    FOR EACH ROW EXECUTE FUNCTION reject_business_key_change('cashier_bk');
CREATE TRIGGER trg_shift_bk_immutable BEFORE UPDATE ON shift
    FOR EACH ROW EXECUTE FUNCTION reject_business_key_change('shift_bk');
CREATE TRIGGER trg_receipt_bk_immutable BEFORE UPDATE ON receipt
    FOR EACH ROW EXECUTE FUNCTION reject_business_key_change('receipt_bk');

CREATE FUNCTION assert_receipt_line_total(target_receipt_bk text)
RETURNS void
LANGUAGE plpgsql
AS $$
DECLARE
    expected numeric(18, 2);
    actual numeric;
BEGIN
    SELECT total_amount INTO expected
      FROM receipt
     WHERE receipt_bk = target_receipt_bk
     FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    SELECT COALESCE(sum(quantity * unit_price - line_discount), 0)
      INTO actual FROM receipt_line WHERE receipt_bk = target_receipt_bk;
    IF actual <> expected THEN
        RAISE EXCEPTION 'receipt % total % differs from line total %',
            target_receipt_bk, expected, actual USING ERRCODE = 'P0001';
    END IF;
END;
$$;

CREATE FUNCTION check_receipt_line_total()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'receipt' THEN
        PERFORM assert_receipt_line_total(COALESCE(NEW.receipt_bk, OLD.receipt_bk));
    ELSE
        IF TG_OP <> 'DELETE' THEN PERFORM assert_receipt_line_total(NEW.receipt_bk); END IF;
        IF TG_OP <> 'INSERT' AND (TG_OP = 'DELETE' OR OLD.receipt_bk IS DISTINCT FROM NEW.receipt_bk) THEN
            PERFORM assert_receipt_line_total(OLD.receipt_bk);
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER trg_receipt_line_total_receipt
    AFTER INSERT OR UPDATE ON receipt DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_receipt_line_total();
CREATE CONSTRAINT TRIGGER trg_receipt_line_total_line
    AFTER INSERT OR UPDATE OR DELETE ON receipt_line DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_receipt_line_total();

CREATE FUNCTION assert_payment_total(target_receipt_bk text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    expected numeric(18, 2);
    actual numeric;
BEGIN
    SELECT total_amount INTO expected
      FROM receipt
     WHERE receipt_bk = target_receipt_bk
     FOR UPDATE;
    IF NOT FOUND THEN RETURN; END IF;
    SELECT COALESCE(sum(amount), 0) INTO actual FROM payment WHERE receipt_bk = target_receipt_bk;
    IF actual <> expected THEN
        RAISE EXCEPTION 'receipt % total % differs from payment total %',
            target_receipt_bk, expected, actual USING ERRCODE = 'P0001';
    END IF;
END;
$$;

CREATE FUNCTION check_payment_total()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'receipt' THEN
        PERFORM assert_payment_total(COALESCE(NEW.receipt_bk, OLD.receipt_bk));
    ELSE
        IF TG_OP <> 'DELETE' THEN PERFORM assert_payment_total(NEW.receipt_bk); END IF;
        IF TG_OP <> 'INSERT' AND (TG_OP = 'DELETE' OR OLD.receipt_bk IS DISTINCT FROM NEW.receipt_bk) THEN
            PERFORM assert_payment_total(OLD.receipt_bk);
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER trg_payment_total_receipt
    AFTER INSERT OR UPDATE ON receipt DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_payment_total();
CREATE CONSTRAINT TRIGGER trg_payment_total_payment
    AFTER INSERT OR UPDATE OR DELETE ON payment DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_payment_total();

CREATE FUNCTION assert_sale_line_rules(target_receipt_bk text)
RETURNS void LANGUAGE plpgsql AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM receipt r JOIN receipt_line rl USING (receipt_bk)
         WHERE r.receipt_bk = target_receipt_bk
           AND r.doc_type = 'sale'
           AND (r.receipt_dt AT TIME ZONE 'UTC')::date > rl.batch_expiry_date_snapshot
    ) THEN
        RAISE EXCEPTION 'receipt % sells an expired batch', target_receipt_bk
            USING ERRCODE = 'P0001';
    END IF;
    IF EXISTS (
        SELECT 1 FROM receipt r JOIN receipt_line rl USING (receipt_bk)
         WHERE r.receipt_bk = target_receipt_bk
           AND rl.is_rx_snapshot
           AND r.prescription_bk IS NULL
    ) THEN
        RAISE EXCEPTION 'receipt % contains Rx item without prescription', target_receipt_bk
            USING ERRCODE = 'P0001';
    END IF;
END;
$$;

CREATE FUNCTION check_sale_line_rules()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_TABLE_NAME = 'receipt' THEN
        PERFORM assert_sale_line_rules(COALESCE(NEW.receipt_bk, OLD.receipt_bk));
    ELSE
        IF TG_OP <> 'DELETE' THEN PERFORM assert_sale_line_rules(NEW.receipt_bk); END IF;
        IF TG_OP <> 'INSERT' AND (TG_OP = 'DELETE' OR OLD.receipt_bk IS DISTINCT FROM NEW.receipt_bk) THEN
            PERFORM assert_sale_line_rules(OLD.receipt_bk);
        END IF;
    END IF;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER trg_sale_rules_receipt
    AFTER INSERT OR UPDATE ON receipt DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_sale_line_rules();
CREATE CONSTRAINT TRIGGER trg_sale_rules_line
    AFTER INSERT OR UPDATE OR DELETE ON receipt_line DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_sale_line_rules();

CREATE FUNCTION assert_refund_limit(target_receipt_bk text)
RETURNS void LANGUAGE plpgsql AS $$
DECLARE
    parent_bk text;
    parent_type text;
BEGIN
    SELECT parent_receipt_bk INTO parent_bk
      FROM receipt WHERE receipt_bk = target_receipt_bk AND doc_type = 'refund';
    IF NOT FOUND THEN RETURN; END IF;

    PERFORM pg_advisory_xact_lock(hashtextextended(parent_bk, 0));
    SELECT doc_type INTO parent_type FROM receipt WHERE receipt_bk = parent_bk FOR UPDATE;
    IF parent_type IS DISTINCT FROM 'sale' THEN
        RAISE EXCEPTION 'refund % parent must be a sale', target_receipt_bk
            USING ERRCODE = 'P0001';
    END IF;

    IF EXISTS (
        WITH sold AS (
            SELECT sku, sum(quantity) AS qty
              FROM receipt_line WHERE receipt_bk = parent_bk GROUP BY sku
        ), returned AS (
            SELECT rl.sku, sum(rl.quantity) AS qty
              FROM receipt rr JOIN receipt_line rl USING (receipt_bk)
             WHERE rr.doc_type = 'refund' AND rr.parent_receipt_bk = parent_bk
             GROUP BY rl.sku
        )
        SELECT 1 FROM returned x LEFT JOIN sold s USING (sku)
         WHERE x.qty > COALESCE(s.qty, 0)
    ) THEN
        RAISE EXCEPTION 'cumulative refunds exceed sale %', parent_bk
            USING ERRCODE = 'P0001';
    END IF;
END;
$$;

CREATE FUNCTION check_refund_limit()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    changed_bk text;
    refund_bk text;
BEGIN
    FOREACH changed_bk IN ARRAY ARRAY[NEW.receipt_bk, OLD.receipt_bk]
    LOOP
        CONTINUE WHEN changed_bk IS NULL;
        PERFORM assert_refund_limit(changed_bk);
        FOR refund_bk IN SELECT receipt_bk FROM receipt WHERE parent_receipt_bk = changed_bk
        LOOP PERFORM assert_refund_limit(refund_bk); END LOOP;
    END LOOP;
    RETURN NULL;
END;
$$;

CREATE CONSTRAINT TRIGGER trg_refund_limit_receipt
    AFTER INSERT OR UPDATE ON receipt DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_refund_limit();
CREATE CONSTRAINT TRIGGER trg_refund_limit_line
    AFTER INSERT OR UPDATE OR DELETE ON receipt_line DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW EXECUTE FUNCTION check_refund_limit();

COMMIT;
