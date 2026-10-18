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

CREATE TABLE pharmacy (
    pharmacy_bk text PRIMARY KEY,
    pharmacy_name text NOT NULL,
    region text NOT NULL,
    city text NOT NULL,
    address text NOT NULL,
    opened_at date NOT NULL,
    closed_at date,
    is_active boolean NOT NULL,
    deleted_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (closed_at IS NULL OR closed_at >= opened_at),
    CONSTRAINT ck_pharmacy_deleted_inactive
        CHECK (deleted_at IS NULL OR NOT is_active)
);

CREATE TABLE cash_register (
    register_bk text PRIMARY KEY,
    pharmacy_bk text NOT NULL REFERENCES pharmacy (pharmacy_bk),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE INDEX ix_cash_register_pharmacy ON cash_register (pharmacy_bk);

CREATE TABLE cashier (
    cashier_bk text PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE TABLE shift (
    shift_bk text PRIMARY KEY,
    register_bk text NOT NULL REFERENCES cash_register (register_bk),
    opened_at timestamptz NOT NULL,
    closed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (closed_at IS NULL OR closed_at > opened_at)
);

CREATE INDEX ix_shift_register_opened
    ON shift (register_bk, opened_at DESC);

CREATE TABLE receipt (
    receipt_bk text PRIMARY KEY,
    shift_bk text NOT NULL REFERENCES shift (shift_bk),
    cashier_bk text NOT NULL REFERENCES cashier (cashier_bk),
    customer_bk text,
    receipt_dt timestamptz NOT NULL,
    doc_type text NOT NULL CHECK (doc_type IN ('sale', 'refund')),
    parent_receipt_bk text REFERENCES receipt (receipt_bk),
    total_amount numeric(18, 2) NOT NULL CHECK (total_amount >= 0),
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    prescription_bk text,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    CHECK (
        (doc_type = 'sale' AND parent_receipt_bk IS NULL)
        OR (doc_type = 'refund' AND parent_receipt_bk IS NOT NULL)
    ),
    CHECK (parent_receipt_bk IS NULL OR parent_receipt_bk <> receipt_bk)
);

CREATE INDEX ix_receipt_shift_date ON receipt (shift_bk, receipt_dt DESC);
CREATE INDEX ix_receipt_cashier_date ON receipt (cashier_bk, receipt_dt DESC);
CREATE INDEX ix_receipt_customer_date ON receipt (customer_bk, receipt_dt DESC);
CREATE INDEX ix_receipt_parent ON receipt (parent_receipt_bk);

CREATE TABLE receipt_line (
    receipt_bk text NOT NULL REFERENCES receipt (receipt_bk),
    line_no integer NOT NULL CHECK (line_no > 0),
    sku text NOT NULL,
    batch_bk text NOT NULL,
    quantity numeric(18, 3) NOT NULL CHECK (quantity > 0),
    unit_price numeric(18, 2) NOT NULL CHECK (unit_price >= 0),
    line_discount numeric(18, 2) NOT NULL CHECK (line_discount >= 0),
    is_rx_snapshot boolean NOT NULL,
    sku_name_snapshot text NOT NULL,
    batch_expiry_date_snapshot date NOT NULL,
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (receipt_bk, line_no),
    CHECK (line_discount <= quantity * unit_price)
);

CREATE INDEX ix_receipt_line_sku ON receipt_line (sku);
CREATE INDEX ix_receipt_line_batch ON receipt_line (batch_bk);

CREATE TABLE payment (
    receipt_bk text NOT NULL REFERENCES receipt (receipt_bk),
    payment_no integer NOT NULL CHECK (payment_no > 0),
    payment_method text NOT NULL
        CHECK (payment_method IN ('cash', 'card', 'bonus', 'certificate')),
    amount numeric(18, 2) NOT NULL CHECK (amount >= 0),
    currency text NOT NULL CHECK (currency ~ '^[A-Z]{3}$'),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (receipt_bk, payment_no)
);

DO $$
DECLARE
    table_name text;
BEGIN
    FOREACH table_name IN ARRAY ARRAY[
        'pharmacy', 'cash_register', 'cashier', 'shift', 'receipt',
        'receipt_line', 'payment'
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
