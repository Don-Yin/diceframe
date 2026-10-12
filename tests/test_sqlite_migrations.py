import sqlite3

import pytest

from src.migrations.sqlite import MigrationError, run_migrations


def test_migration_is_idempotent_and_sets_version():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table t (id integer)")
    calls = []
    step = lambda db: (calls.append(1), db.execute("alter table t add column value text"))
    assert run_migrations(conn, ((1, step),)) == 1
    assert run_migrations(conn, ((1, step),)) == 1
    assert len(calls) == 1


def test_failed_migration_rolls_back_version():
    conn = sqlite3.connect(":memory:")
    conn.execute("create table t (id integer)")
    with pytest.raises(MigrationError):
        run_migrations(conn, ((1, lambda db: db.execute("alter table missing add column x text")),))
    assert conn.execute("pragma user_version").fetchone()[0] == 0


def test_future_database_version_is_rejected_before_running_steps():
    conn = sqlite3.connect(":memory:")
    conn.execute("pragma user_version = 999")
    calls = []

    with pytest.raises(MigrationError, match="newer than supported"):
        run_migrations(conn, ((1, lambda _db: calls.append(1)),))

    assert not calls
    assert conn.execute("pragma user_version").fetchone()[0] == 999
