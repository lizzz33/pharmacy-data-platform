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

CREATE TABLE supplier (
    supplier_bk text PRIMARY KEY,
    supplier_name text NOT NULL,
    country text NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_supplier_deleted_inactive
        CHECK (deleted_at IS NULL OR NOT is_active)
);

CREATE TABLE distribution_center (
    dc_bk text PRIMARY KEY,
    dc_name text NOT NULL,
    region text NOT NULL,
    city text NOT NULL,
    is_active boolean NOT NULL,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CONSTRAINT ck_distribution_center_deleted_inactive
        CHECK (deleted_at IS NULL OR NOT is_active)
);

CREATE TABLE purchase_order (
    purchase_bk text PRIMARY KEY,
    supplier_bk text NOT NULL REFERENCES supplier (supplier_bk),
    dc_bk text NOT NULL REFERENCES distribution_center (dc_bk),
    ordered_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX ix_purchase_order_supplier_ordered
    ON purchase_order (supplier_bk, ordered_at DESC);
CREATE INDEX ix_purchase_order_dc_ordered
    ON purchase_order (dc_bk, ordered_at DESC);

CREATE TABLE batch (
    batch_bk text PRIMARY KEY,
    sku text NOT NULL,
    series_no text NOT NULL,
    manufactured_date date NOT NULL,
    expiry_date date NOT NULL,
    received_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (sku, series_no),
    UNIQUE (batch_bk, sku),
    CHECK (expiry_date > manufactured_date),
    CHECK (expiry_date >= (received_at AT TIME ZONE 'UTC')::date)
);

CREATE INDEX ix_batch_sku ON batch (sku);
CREATE INDEX ix_batch_expiry_date ON batch (expiry_date);

CREATE TABLE purchase_line (
    purchase_bk text NOT NULL REFERENCES purchase_order (purchase_bk),
    line_no integer NOT NULL CHECK (line_no > 0),
    sku text NOT NULL,
    batch_bk text,
    quantity numeric(18, 3) NOT NULL CHECK (quantity > 0),
    unit_cost numeric(18, 2) NOT NULL CHECK (unit_cost >= 0),
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (purchase_bk, line_no),
    CONSTRAINT fk_purchase_line_batch_sku
        FOREIGN KEY (batch_bk, sku) REFERENCES batch (batch_bk, sku)
);

CREATE INDEX ix_purchase_line_sku ON purchase_line (sku);
CREATE INDEX ix_purchase_line_batch ON purchase_line (batch_bk);

CREATE TABLE movement (
    movement_bk text PRIMARY KEY,
    batch_bk text NOT NULL REFERENCES batch (batch_bk),
    movement_type text NOT NULL
        CHECK (movement_type IN ('receipt', 'transfer', 'sale_writeoff', 'return', 'writeoff')),
    src_type text CHECK (src_type IN ('dc', 'pharmacy', 'supplier')),
    src_bk text,
    dst_type text CHECK (dst_type IN ('dc', 'pharmacy', 'customer', 'supplier')),
    dst_bk text,
    qty numeric(18, 3) NOT NULL CHECK (qty > 0),
    dispatched_at timestamptz,
    moved_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK ((src_type IS NULL) = (src_bk IS NULL)),
    CHECK ((dst_type IS NULL) = (dst_bk IS NULL)),
    CHECK (src_type IS NOT NULL OR dst_type IS NOT NULL),
    CHECK (src_type IS NULL OR dst_type IS NULL OR src_type <> dst_type OR src_bk <> dst_bk),
    CHECK (dispatched_at IS NULL OR dispatched_at <= moved_at),
    CHECK (
        (movement_type = 'receipt' AND dst_type = 'dc' AND src_type IN ('supplier'))
        OR (movement_type = 'receipt' AND dst_type = 'dc' AND src_type IS NULL)
        OR (movement_type = 'transfer' AND src_type = 'dc' AND dst_type = 'pharmacy')
        OR (movement_type = 'sale_writeoff' AND src_type = 'pharmacy' AND dst_type = 'customer')
        OR (movement_type = 'return' AND src_type = 'pharmacy' AND dst_type = 'dc')
        OR (movement_type = 'return' AND src_type = 'dc' AND dst_type = 'supplier')
        OR (movement_type = 'writeoff' AND src_type IN ('dc', 'pharmacy') AND dst_type IS NULL)
    )
);

CREATE INDEX ix_movement_batch_moved
    ON movement (batch_bk, moved_at DESC);
CREATE INDEX ix_movement_source
    ON movement (src_type, src_bk, moved_at DESC);
CREATE INDEX ix_movement_destination
    ON movement (dst_type, dst_bk, moved_at DESC);

CREATE TABLE stock (
    location_type text NOT NULL CHECK (location_type IN ('dc', 'pharmacy')),
    location_bk text NOT NULL,
    batch_bk text NOT NULL REFERENCES batch (batch_bk),
    qty_on_hand numeric(18, 3) NOT NULL CHECK (qty_on_hand >= 0),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (location_type, location_bk, batch_bk)
);

CREATE INDEX ix_stock_batch ON stock (batch_bk);

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'supplier', 'distribution_center', 'purchase_order', 'batch',
        'purchase_line', 'movement', 'stock'
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
