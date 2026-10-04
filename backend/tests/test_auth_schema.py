"""
Schema tests for the session-control columns on ``users``.

- Migration 013 (PostgreSQL path) adds ``must_change_password`` and
  ``token_version`` with server defaults, is idempotent, and downgrades.
- The SQLite backstop (development databases never run Alembic) adds the
  same columns to a database created by an older release.

Both run against a throwaway SQLite file; the migration's operations
(add_column / batch drop_column) are dialect-neutral.
"""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from app.models.db_models import Base
from app.utils.sqlite_columns import add_missing_sqlite_columns

_MIGRATION = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "20261004_000000_013_user_session_controls.py"
)

_NEW_COLUMNS = {"must_change_password", "token_version"}


def _load_migration():
    spec = importlib.util.spec_from_file_location("migration_013", _MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _legacy_engine(tmp_path) -> sa.Engine:
    """A database whose ``users`` table predates the new columns, with one row."""
    engine = sa.create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE users (id VARCHAR(36) PRIMARY KEY, email VARCHAR(255) NOT NULL, "
            "name VARCHAR(255) NOT NULL, password_hash VARCHAR(255), roles JSON, "
            "mfa_enabled BOOLEAN, is_active BOOLEAN, created_at DATETIME NOT NULL)"
        )
        conn.exec_driver_sql(
            "INSERT INTO users (id, email, name, created_at) "
            "VALUES ('u1', 'old@example.com', 'Old', '2026-01-01 00:00:00')"
        )
    return engine


def _columns(engine, table: str = "users") -> set[str]:
    return {c["name"] for c in sa.inspect(engine).get_columns(table)}


class TestMigration013:
    def test_chain_position(self):
        migration = _load_migration()
        assert migration.revision == "013"
        assert migration.down_revision == "012"

    def test_upgrade_adds_columns_with_defaults_for_existing_rows(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        migration = _load_migration()
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()

        assert _columns(engine) >= _NEW_COLUMNS
        with engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT must_change_password, token_version FROM users WHERE id = 'u1'"
            ).one()
        assert not row[0]
        assert row[1] == 0

    def test_upgrade_is_idempotent(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        migration = _load_migration()
        for _ in range(2):
            with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
                migration.upgrade()
        assert _columns(engine) >= _NEW_COLUMNS

    def test_downgrade_removes_columns(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        migration = _load_migration()
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            migration.upgrade()
        with engine.begin() as conn, Operations.context(MigrationContext.configure(conn)):
            migration.downgrade()
        assert not (_NEW_COLUMNS & _columns(engine))


class TestSqliteBackstop:
    def test_adds_missing_columns_to_an_older_database(self, tmp_path):
        engine = _legacy_engine(tmp_path)
        with engine.begin() as conn:
            added = add_missing_sqlite_columns(conn, Base.metadata)

        assert {"users.must_change_password", "users.token_version"} <= set(added)
        assert _columns(engine) >= _NEW_COLUMNS
        with engine.connect() as conn:
            row = conn.exec_driver_sql(
                "SELECT must_change_password, token_version FROM users WHERE id = 'u1'"
            ).one()
        assert not row[0]
        assert row[1] == 0

    def test_is_a_noop_on_a_current_schema(self, tmp_path):
        engine = sa.create_engine(f"sqlite:///{tmp_path / 'current.db'}")
        Base.metadata.create_all(engine)
        with engine.begin() as conn:
            assert add_missing_sqlite_columns(conn, Base.metadata) == []

    def test_never_touches_other_dialects(self):
        class _PostgresConn:
            class dialect:
                name = "postgresql"

        assert add_missing_sqlite_columns(_PostgresConn(), Base.metadata) == []

    def test_model_declares_server_defaults(self):
        """ALTER TABLE ... ADD COLUMN NOT NULL needs a server default."""
        users = Base.metadata.tables["users"]
        for name in _NEW_COLUMNS:
            assert users.c[name].nullable is False
            assert users.c[name].server_default is not None
