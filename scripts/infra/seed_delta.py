"""Allocate a fresh seed per checker invocation, then run the team's delta mode."""
import sys

from common import connect
from seed import route_arguments
from pharmacy_dwh.seed.cli import main

conn = connect("pos_service_db", user="app", pooled=True)
try:
    with conn:
        with conn.cursor() as cur:
            cur.execute("SELECT nextval('infra.delta_seed_seq')")
            seed = cur.fetchone()[0]
finally:
    conn.close()
print(f"seed_delta namespace: {seed}", flush=True)
sys.argv = [sys.argv[0], *route_arguments(), "--seed", str(seed), "--delta"]
main()
