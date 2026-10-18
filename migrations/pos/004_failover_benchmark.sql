BEGIN;

CREATE SCHEMA failover_bench;

CREATE TABLE failover_bench.write_probe (
    run_id text NOT NULL,
    sequence_no bigint NOT NULL,
    client_started_at timestamptz NOT NULL,
    committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    PRIMARY KEY (run_id, sequence_no)
);

COMMENT ON SCHEMA failover_bench IS
    'Technical-only tables used by the reproducible HW1 failover experiments.';

COMMENT ON TABLE failover_bench.write_probe IS
    'Acknowledged benchmark writes; deliberately separate from POS business facts.';

COMMIT;
