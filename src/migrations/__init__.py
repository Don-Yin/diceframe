"""Versioned persistence migrations."""

from .sqlite import MigrationError, ensure_column, run_migrations
from .instance import migrate_instance

__all__ = ["MigrationError", "ensure_column", "run_migrations", "migrate_instance"]
