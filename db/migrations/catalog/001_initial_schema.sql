BEGIN;

CREATE FUNCTION set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

CREATE TABLE manufacturer (
    manufacturer_bk text PRIMARY KEY,
    manufacturer_name text NOT NULL UNIQUE,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE drug_form (
    drug_form_bk text PRIMARY KEY,
    drug_form_name text NOT NULL UNIQUE,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE active_ingredient (
    ingredient_bk text PRIMARY KEY,
    inn_name text NOT NULL UNIQUE,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE sku_category (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category_name text NOT NULL UNIQUE
        CHECK (category_name IN ('rx', 'otc', 'supplement', 'device', 'cosmetics')),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE price_scope (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    scope_name text NOT NULL UNIQUE
        CHECK (scope_name IN ('chain', 'region', 'pharmacy')),
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE sku (
    sku_bk text PRIMARY KEY,
    manufacturer_bk text NOT NULL REFERENCES manufacturer (manufacturer_bk),
    drug_form_bk text REFERENCES drug_form (drug_form_bk),
    pack_qty numeric(18, 3) NOT NULL CHECK (pack_qty > 0),
    is_vital boolean NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_sku_deleted_inactive
        CHECK (deleted_at IS NULL OR NOT is_active)
);

CREATE INDEX ix_sku_manufacturer ON sku (manufacturer_bk);
CREATE INDEX ix_sku_drug_form ON sku (drug_form_bk);

CREATE TABLE sku_version (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku_bk text NOT NULL REFERENCES sku (sku_bk),
    sku_name text NOT NULL,
    category_id bigint NOT NULL REFERENCES sku_category (id),
    is_rx boolean NOT NULL,
    valid_from timestamptz NOT NULL,
    is_current boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (sku_bk, valid_from)
);

CREATE UNIQUE INDEX ux_sku_version_current
    ON sku_version (sku_bk)
    WHERE is_current;
CREATE INDEX ix_sku_version_history
    ON sku_version (sku_bk, valid_from DESC);
CREATE INDEX ix_sku_version_category ON sku_version (category_id);

CREATE TABLE sku_active_ingredient (
    sku_bk text NOT NULL REFERENCES sku (sku_bk),
    ingredient_bk text NOT NULL REFERENCES active_ingredient (ingredient_bk),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (sku_bk, ingredient_bk)
);

CREATE INDEX ix_sku_active_ingredient_ingredient
    ON sku_active_ingredient (ingredient_bk, sku_bk);

CREATE TABLE price_version (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku_bk text NOT NULL REFERENCES sku (sku_bk),
    price_scope_id bigint NOT NULL REFERENCES price_scope (id),
    scope_bk text NOT NULL,
    price numeric(18, 2) NOT NULL CHECK (price > 0),
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    valid_from timestamptz NOT NULL,
    valid_to timestamptz,
    is_current boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (valid_to IS NULL OR valid_to > valid_from),
    CONSTRAINT ck_price_version_current_is_open
        CHECK (is_current = (valid_to IS NULL)),
    UNIQUE (sku_bk, price_scope_id, scope_bk, valid_from)
);

CREATE UNIQUE INDEX ux_price_version_current
    ON price_version (sku_bk, price_scope_id, scope_bk)
    WHERE is_current;
CREATE INDEX ix_price_version_history
    ON price_version (sku_bk, price_scope_id, scope_bk, valid_from DESC);

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'manufacturer', 'drug_form', 'active_ingredient', 'sku_category',
        'price_scope', 'sku', 'sku_version', 'sku_active_ingredient',
        'price_version'
    ]
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%I_set_updated_at BEFORE UPDATE ON %I '
            'FOR EACH ROW EXECUTE FUNCTION set_updated_at()',
            table_name, table_name
        );
    END LOOP;
END;
$$;

COMMIT;
