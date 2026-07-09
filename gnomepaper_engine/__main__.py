"""Entry point: ``python -m gnomepaper_engine`` or ``gnomepaper-engine``."""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    from gnomepaper_engine.app import run

    # Gio.Application expects full argv including program name
    if argv is None:
        return run(sys.argv)
    return run([sys.argv[0], *argv] if argv and not argv[0].endswith(".py") else argv)


if __name__ == "__main__":
    raise SystemExit(main())
