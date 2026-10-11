# Pharmacy data warehouse homework

## HW1 local source databases

The initial HW1 source schemas run in one PostgreSQL container with four
separate databases:

- `crm_service_db`
- `catalog_service_db`
- `wms_service_db`
- `pos_service_db`

Start the local stack and check its status:

```sh
docker compose up -d
docker compose ps
```

PostgreSQL is exposed on `localhost:5432`. The local development credentials
are `pharmacy` / `pharmacy`. On the first start, the scripts under
`docker/postgres/init/` create the databases and apply the numbered migrations
from `db/migrations/<service>/`.

To exercise initialization again from an empty local data volume:

```sh
docker compose down -v
docker compose up -d
```

Run the isolated database-invariant tests after the stack is healthy:

```sh
./scripts/test_invariants.sh
```

The runner executes every negative test in its own transaction, verifies the
observed PostgreSQL SQLSTATE, and rolls back the two positive tests.

Validate the `contract.*` interface, rollback-only representative fixtures,
and course checks C01-C23:

```sh
./scripts/test_contracts.sh
```

The contract validator reads `hws_descriptions/hw1/hw01_contract.yaml`
directly and requires Ruby's standard YAML library.

## Generate the HW1 dataset

After the stack is healthy, generate the deterministic assignment-scale dataset:

```sh
./scripts/seed.sh --seed 42
```

The default data horizon is the exclusive date `2026-10-01`; pass
`--as-of YYYY-MM-DD` to select another fixed horizon. A seed value defines a namespace
for every generated business key. Repeating the same command is idempotent.

Append a smaller, independently namespaced portion for replication/delta tests:

```sh
./scripts/seed.sh --seed 43 --delta
```

Repeating an identical delta is also idempotent. Use a different seed to append
another non-colliding namespace.

The base scale is approximately 2,200 customers, 550 SKU, 21,500 receipts,
63,500 receipt lines, 3,300 batches, 5,400 purchase lines, and 92,000 stock
movements. It covers 18 months. Demand is deliberately non-uniform: weekends
are busier, pharmacy sizes differ, popular SKU follow a long-tail distribution,
about 43% of documents have no customer card, and refunds are about 2.4% of
documents. WMS stock is derived only through movement inserts.

## Run the official course checker

The repository already contains a working `hw01_submission.yaml` for the current local setup.

Run the official data, cross-service, invariant, and realism checks:

```sh
uv run python hws_descriptions/hw1/hw01_check.py \
  --submission ./hw01_submission.yaml \
  --sections contract,keys,volume,dq,cross,inv,realism \
  --skip-exec \
  -v
```

The checker requires the Python dependencies declared in `pyproject.toml` (`PyYAML` and `psycopg2-binary`), so run it through `uv` as shown above.

This command has been executed successfully on the generated dataset. The result
is fully green for the selected sections:

- contract views: 14/14;
- contract nullability and uniqueness: 27/27;
- volume thresholds: 14/14;
- data-quality checks C01-C23: 23/23;
- cross-service checks X01-X10: 10/10;
- invariants I1-I12, P1/P2, and leakage: 15/15;
- realism checks: 5/5.

The remaining checker sections (`repl`, `cdc`, and `ha`) are outside the seed
generator stage and have not been implemented yet.
