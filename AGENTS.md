# Agent guide

This repository contains the Data Warehousing homework series. Future homeworks continue in the same Git repository and use the shared Python package:

```text
src/pharmacy_dwh/
```

## What this repository is

The current work is HW1: designing and implementing four PostgreSQL source databases for a pharmacy domain:

```text
CRM      -> crm_service_db
Catalog  -> catalog_service_db
POS      -> pos_service_db
WMS      -> wms_service_db
```

The detailed current status and remaining work are kept in:

```text
notes/hw1/plan.md
```

Read that file when you need to understand what has already been done and what comes next.

## Where things live

### Course materials

```text
hws_descriptions/hw1/
```

Contains the original assignment, contract, invariants, checker, and submission templates.

Important files:

- `README.md` — assignment;
- `hw01_contract.yaml` — required `contract.*` interface;
- `invariants.md` — mandatory DB invariants and SQL-test rules;
- `hw01_check.py` — course checker.

### Design notes

```text
notes/hw1/dbs_schemas/
├── crm.md
├── catalog.md
├── pos.md
└── wms.md
```

These files explain the physical schema decisions for each service database.

The neighboring `*.mmd` files are Mermaid ER diagrams.

Other useful notes:

```text
notes/hw1/plan.md
notes/hw1/remember.md
notes/hw1/interesting_facts.md
```

### PostgreSQL migrations

```text
db/migrations/
├── crm/
├── catalog/
├── pos/
└── wms/
```

Each service currently has layered migrations:

```text
001_initial_schema.sql
002_invariants.sql
003_contract_views.sql
```

### Docker

```text
docker-compose.yml
docker/postgres/init/
```

The default stack is now the prepared HA infrastructure described in
`docs/infra/README.md`; it has not been built or run yet. The original one-server
development stack is retained as `docker-compose.dev.yml`.

### Tests

```text
tests/invariants/
tests/contracts/
```

- `tests/invariants/` — SQL tests for mandatory DB invariants;
- `tests/contracts/` — small rollback-only fixtures for validating contract views.

Helpers:

```text
scripts/test_invariants.sh
scripts/test_contracts.sh
scripts/test_contracts.rb
```

The Ruby file is only a local validation helper for reading the YAML contract and checking the PostgreSQL views. It is not part of the application architecture.

### Shared Python code

```text
src/pharmacy_dwh/
```

Use this package for Python code shared by HW1 and future homeworks.

### Task history

```text
.artifacts/tasks/
.artifacts/reports/
```

These directories contain task descriptions given to coding agents and their completion reports.

They are useful for understanding why a particular implementation change was made.

## Basic working rules

- Start from the course materials and existing design notes instead of redesigning from scratch.
- Do not create cross-database foreign keys; cross-service references use business keys.
- Keep `notes/hw1/plan.md` current when a major stage is completed.
- Put schema/design reasoning in the relevant file under `notes/hw1/dbs_schemas/`.
- Prefer adding new numbered migrations instead of silently rewriting previous work.
- Do not add architecture or tooling that the assignment does not require.

## Current checkpoint

The repository already contains:

- physical schemas for all four databases;
- DB-level invariants;
- SQL invariant tests;
- `contract.*` views;
- local Docker validation;
- contract validation against the course YAML.

For the exact remaining work and next step, see:

```text
notes/hw1/plan.md
```
