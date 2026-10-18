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

CREATE TABLE customer (
    customer_bk text PRIMARY KEY,
    birth_year integer,
    sex text CHECK (sex IN ('M', 'F')),
    registered_at timestamptz NOT NULL,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE loyalty_level (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    level_name text NOT NULL UNIQUE,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE customer_profile_version (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_bk text NOT NULL REFERENCES customer (customer_bk),
    city text,
    region text,
    loyalty_level_id bigint REFERENCES loyalty_level (id),
    valid_from timestamptz NOT NULL,
    is_current boolean NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (customer_bk, valid_from)
);

CREATE UNIQUE INDEX ux_customer_profile_version_current
    ON customer_profile_version (customer_bk)
    WHERE is_current;
CREATE INDEX ix_customer_profile_version_history
    ON customer_profile_version (customer_bk, valid_from DESC);

CREATE TABLE contact_type (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type_name text NOT NULL UNIQUE,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE customer_contact (
    contact_bk text PRIMARY KEY,
    customer_bk text NOT NULL REFERENCES customer (customer_bk),
    contact_type_id bigint NOT NULL REFERENCES contact_type (id),
    contact_value text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX ix_customer_contact_customer
    ON customer_contact (customer_bk);

CREATE TABLE consent_type (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    type_name text NOT NULL UNIQUE,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE consent (
    consent_bk text PRIMARY KEY,
    customer_bk text NOT NULL REFERENCES customer (customer_bk),
    consent_type_id bigint NOT NULL REFERENCES consent_type (id),
    issued_at timestamptz NOT NULL,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (revoked_at IS NULL OR revoked_at > issued_at)
);

CREATE UNIQUE INDEX ux_consent_active_type
    ON consent (customer_bk, consent_type_id)
    WHERE revoked_at IS NULL;
CREATE INDEX ix_consent_customer_history
    ON consent (customer_bk, consent_type_id, issued_at DESC);

CREATE TABLE loyalty_card (
    card_bk text PRIMARY KEY,
    customer_bk text NOT NULL REFERENCES customer (customer_bk),
    issued_at timestamptz NOT NULL,
    closed_at timestamptz,
    status text NOT NULL CHECK (status IN ('active', 'blocked', 'closed')),
    bonus_balance numeric(18, 2) NOT NULL CHECK (bonus_balance >= 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (closed_at IS NULL OR closed_at >= issued_at),
    CHECK (closed_at IS NULL OR status <> 'active')
);

CREATE UNIQUE INDEX ux_loyalty_card_active_customer
    ON loyalty_card (customer_bk)
    WHERE status = 'active';
CREATE INDEX ix_loyalty_card_customer
    ON loyalty_card (customer_bk, issued_at DESC);

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'customer', 'loyalty_level', 'customer_profile_version',
        'contact_type', 'customer_contact', 'consent_type', 'consent',
        'loyalty_card'
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
