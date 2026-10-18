"""Invoke the unchanged team generator through the RW pool."""
import os
import sys

from pharmacy_dwh.seed.cli import main


def route_arguments():
    return ["--host", "pgbouncer-rw", "--port", "6432", "--user", "app",
            "--password", os.environ.get("APP_PASSWORD", "app")]


if __name__ == "__main__":
    sys.argv = [sys.argv[0], *route_arguments(), *sys.argv[1:]]
    main()
