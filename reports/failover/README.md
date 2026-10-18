# Failover evidence

Valid E1–E7 evidence is stored in the directories whose names begin with the
corresponding experiment number. Every experiment directory contains
`commands.txt`; write workloads additionally contain `write-events.jsonl` and
`write-summary.json`. Patroni and etcd experiments retain their raw logs and
topology snapshots.

The journal uses these valid runs:

- `e1-baseline/`;
- `e2-e3-failover/`;
- `e4-switchover/`;
- `e5-async-baseline/`, `e5-sync-baseline/`, `e5-sync-failover/`,
  `e5-synchronous/`;
- `e6-one-etcd-down/`, `e6-quorum-loss/`, `e6-etcd-quorum/`;
- `e7-connection-pressure/`.

Directories containing `rejected` are retained for audit but are not used for
reported metrics:

- `e2-e3-rejected-auto-restart/` records the discovery that `docker compose
  kill` immediately restarted a service configured with `restart:
  unless-stopped`;
- `e2-e3-rejected-attempt-time/` records the discovery that attempt-start time
  cannot be used as the completion time of a blocked write;
- `e6-rejected-read-auth/` records a read probe with the wrong password.

The corrected harness uses an explicit zero-grace `docker compose stop`, records
write completion timestamps, and supplies the checker password to the RO probe.
