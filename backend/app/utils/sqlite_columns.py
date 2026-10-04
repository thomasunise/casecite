"""SQLite-only column backstop for development databases.

PostgreSQL schemas are managed by Alembic. SQLite (local development, DEBUG
only) never runs migrations: its schema comes from ``create_all``, which
creates missing *tables* but never adds a column to a table that already
exists. Without this backstop, a model column added in a new release (e.g.
``users.must_change_password``) makes every query against an existing dev
database fail with "no such column" until the file is deleted.

This adds exactly the model columns an existing SQLite table is missing, and
only those that are safe to add in place (nullable, or carrying a server
default). It is a no-op on PostgreSQL and never drops or alters anything.
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect
from sqlalchemy.engine import Connection
from sqlalchemy.schema import CreateColumn

logger = logging.getLogger(__name__)


def add_missing_sqlite_columns(conn: Connection, metadata) -> list[str]:
    """Add model columns missing from existing SQLite tables. Returns ``table.column`` names."""
    if conn.dialect.name != "sqlite":
        return []

    inspector = inspect(conn)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []
    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {c["name"] for c in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present or column.primary_key:
                continue
            if not column.nullable and column.server_default is None:
                logger.warning(
                    "SQLite backstop: cannot add NOT NULL column %s.%s without a server "
                    "default — delete the development database to rebuild the schema.",
                    table.name,
                    column.name,
                )
                continue
            ddl = CreateColumn(column).compile(dialect=conn.dialect)
            conn.exec_driver_sql(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}')
            added.append(f"{table.name}.{column.name}")
    if added:
        logger.info("SQLite backstop added missing columns: %s", ", ".join(added))
    return added
