"""Entry point: ``python -m gnomepaper_engine`` or ``gnomepaper-engine``."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from gnomepaper_engine.app import run

    return run(argv if argv is not None else sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
