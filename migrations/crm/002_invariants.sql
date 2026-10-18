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

CREATE TRIGGER trg_customer_bk_immutable
    BEFORE UPDATE ON customer FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('customer_bk');
CREATE TRIGGER trg_customer_contact_bk_immutable
    BEFORE UPDATE ON customer_contact FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('contact_bk');
CREATE TRIGGER trg_consent_bk_immutable
    BEFORE UPDATE ON consent FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('consent_bk');
CREATE TRIGGER trg_loyalty_card_bk_immutable
    BEFORE UPDATE ON loyalty_card FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('card_bk');

CREATE FUNCTION anonymize_customer_contacts()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF OLD.deleted_at IS NULL AND NEW.deleted_at IS NOT NULL THEN
        UPDATE customer_contact
           SET contact_value = NULL
         WHERE customer_bk = NEW.customer_bk
           AND contact_value IS NOT NULL;
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_customer_soft_delete_anonymize
    AFTER UPDATE OF deleted_at ON customer FOR EACH ROW
    EXECUTE FUNCTION anonymize_customer_contacts();

COMMIT;
