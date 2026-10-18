BEGIN;

CREATE EXTENSION IF NOT EXISTS btree_gist;

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

CREATE TRIGGER trg_manufacturer_bk_immutable
    BEFORE UPDATE ON manufacturer FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('manufacturer_bk');
CREATE TRIGGER trg_drug_form_bk_immutable
    BEFORE UPDATE ON drug_form FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('drug_form_bk');
CREATE TRIGGER trg_active_ingredient_bk_immutable
    BEFORE UPDATE ON active_ingredient FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('ingredient_bk');
CREATE TRIGGER trg_sku_bk_immutable
    BEFORE UPDATE ON sku FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('sku_bk');

ALTER TABLE price_version
    ADD CONSTRAINT ex_price_version_no_overlap
    EXCLUDE USING gist (
        sku_bk WITH =,
        price_scope_id WITH =,
        scope_bk WITH =,
        tstzrange(valid_from, valid_to, '[)') WITH &&
    );

COMMIT;
