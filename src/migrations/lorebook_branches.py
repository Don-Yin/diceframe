"""Schema recognition at the boundary of the two historical Lorebook v10s."""

from collections.abc import Callable
import sqlite3

from src.migrations.sqlite import MigrationError, table_columns


OPERATIONS_COLUMNS = frozenset({
    "id", "owner", "kind", "status", "payload_json", "created_at", "updated_at",
})


def validate_operations_table(conn: sqlite3.Connection) -> None:
    columns = table_columns(conn, "lorebook_operations")
    if columns != OPERATIONS_COLUMNS:
        raise MigrationError("unsupported local Lorebook operations schema")
    metadata = list(conn.execute('PRAGMA table_info("lorebook_operations")'))
    if any(str(row[2]).upper() != "TEXT" for row in metadata):
        raise MigrationError("unsupported local Lorebook operations column types")
    if [str(row[1]) for row in metadata if row[5]] != ["id"]:
        raise MigrationError("unsupported local Lorebook operations identity")


def prepare_local_v10(
    conn: sqlite3.Connection,
    establish_main_identity: Callable[[sqlite3.Connection], None],
) -> None:
    if "external_id" in table_columns(conn, "lorebooks"):
        return  # Main's historical v10 is already complete.
    if int(conn.execute("PRAGMA user_version").fetchone()[0]) != 10:
        raise MigrationError("unrecognized Lorebook schema before version 11")
    validate_operations_table(conn)
    # Called inside the normal migration transaction. A later failure rolls
    # back these columns/indexes together with the version and all other steps.
    establish_main_identity(conn)
