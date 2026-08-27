"""Brownfield migration bootstrap.

Deployments that predate shipped migrations have a fully-built schema (created
by the runtime create_all backstop) but no alembic_version table. Running
`alembic upgrade head` against such a database explodes on migration 001
(CREATE TABLE users → DuplicateTable) and crash-loops the container.

This script runs BEFORE `alembic upgrade head` (see start.sh / backend
Dockerfile CMD). If it finds tables but no alembic_version, it stamps the
database at revision 004 — the last revision whose work (create/drop whole
tables) a create_all-built schema already reflects. Migrations 005+ are
guarded/idempotent column-and-index alignments and then run normally,
adding exactly the columns a create_all-era schema is missing
(users MFA columns, audit hash-chain columns, authority reasoning, ...).

Fresh (empty) databases are untouched: the normal 001→head path runs.
SQLite is untouched: migrations don't run there at all.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger("migration_bootstrap")

# Last revision that only creates/drops whole tables. A schema built by
# create_all (which creates every model table) is already "at" this point.
_BROWNFIELD_BASELINE = "004"


def _sync_url() -> str | None:
    url = os.environ.get("DATABASE_URL", "")
    if not url or url.startswith("sqlite"):
        return None
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql+asyncpg://"):
        url = url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    elif url.startswith("postgresql://") and "+psycopg2" not in url:
        url = url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(name)s: %(message)s")
    url = _sync_url()
    if url is None:
        logger.info("No PostgreSQL DATABASE_URL — nothing to bootstrap.")
        return 0

    from sqlalchemy import create_engine, inspect

    engine = create_engine(url)
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
    finally:
        engine.dispose()

    if "alembic_version" in tables:
        logger.info("alembic_version present — migrations already under control.")
        return 0
    if "users" not in tables:
        logger.info("Empty database — normal migration path (001 → head) applies.")
        return 0

    logger.info(
        "Brownfield database detected (%d tables, no alembic_version) — "
        "stamping baseline %s so guarded alignment migrations can run.",
        len(tables),
        _BROWNFIELD_BASELINE,
    )
    from alembic import command
    from alembic.config import Config

    command.stamp(Config("alembic.ini"), _BROWNFIELD_BASELINE)
    logger.info("Stamped %s.", _BROWNFIELD_BASELINE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
