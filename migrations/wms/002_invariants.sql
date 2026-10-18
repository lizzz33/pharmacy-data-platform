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

CREATE TRIGGER trg_supplier_bk_immutable
    BEFORE UPDATE ON supplier FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('supplier_bk');
CREATE TRIGGER trg_distribution_center_bk_immutable
    BEFORE UPDATE ON distribution_center FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('dc_bk');
CREATE TRIGGER trg_purchase_order_bk_immutable
    BEFORE UPDATE ON purchase_order FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('purchase_bk');
CREATE TRIGGER trg_batch_bk_immutable
    BEFORE UPDATE ON batch FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('batch_bk');
CREATE TRIGGER trg_movement_bk_immutable
    BEFORE UPDATE ON movement FOR EACH ROW
    EXECUTE FUNCTION reject_business_key_change('movement_bk');

CREATE FUNCTION apply_movement_to_stock()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NEW.src_type IN ('dc', 'pharmacy') THEN
        UPDATE stock
           SET qty_on_hand = qty_on_hand - NEW.qty
         WHERE location_type = NEW.src_type
           AND location_bk = NEW.src_bk
           AND batch_bk = NEW.batch_bk;
        IF NOT FOUND THEN
            INSERT INTO stock (location_type, location_bk, batch_bk, qty_on_hand)
            VALUES (NEW.src_type, NEW.src_bk, NEW.batch_bk, -NEW.qty);
        END IF;
    END IF;

    IF NEW.dst_type IN ('dc', 'pharmacy') THEN
        INSERT INTO stock (location_type, location_bk, batch_bk, qty_on_hand)
        VALUES (NEW.dst_type, NEW.dst_bk, NEW.batch_bk, NEW.qty)
        ON CONFLICT (location_type, location_bk, batch_bk)
        DO UPDATE SET qty_on_hand = stock.qty_on_hand + EXCLUDED.qty_on_hand;
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER trg_movement_apply_stock
    AFTER INSERT ON movement FOR EACH ROW
    EXECUTE FUNCTION apply_movement_to_stock();

CREATE FUNCTION reject_movement_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'movement rows are immutable; record a compensating movement instead'
        USING ERRCODE = 'P0001';
END;
$$;

CREATE TRIGGER trg_movement_immutable
    BEFORE UPDATE OR DELETE ON movement
    FOR EACH ROW
    EXECUTE FUNCTION reject_movement_mutation();

COMMIT;
