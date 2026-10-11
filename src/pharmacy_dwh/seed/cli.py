from __future__ import annotations

import argparse
import time
from datetime import date

from .config import DEFAULT_AS_OF, Settings
from .generator import Generator


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed the four HW1 pharmacy service databases")
    parser.add_argument("--seed", type=int, required=True, help="non-negative deterministic namespace")
    parser.add_argument("--delta", action="store_true", help="append a smaller deterministic namespace")
    parser.add_argument("--as-of", type=date.fromisoformat, default=DEFAULT_AS_OF,
                        help="exclusive deterministic data horizon (YYYY-MM-DD)")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=5432)
    parser.add_argument("--user", default="pharmacy")
    parser.add_argument("--password", default="pharmacy")
    return parser


def main() -> None:
    args = _parser().parse_args()
    if args.seed < 0:
        raise SystemExit("--seed must be non-negative")
    settings = Settings(args.seed, args.delta, args.as_of, args.host, args.port,
                        args.user, args.password)
    started = time.monotonic()
    counts = Generator(settings).run()
    mode = "delta" if settings.delta else "base"
    print(f"seed complete: mode={mode} namespace={settings.namespace} as_of={settings.as_of}")
    for name, count in sorted(counts.items()):
        print(f"  {name}: {count}")
    print(f"elapsed_seconds: {time.monotonic() - started:.2f}")


if __name__ == "__main__":
    main()

