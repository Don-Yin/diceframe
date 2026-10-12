"""Legacy import boundary for D&D 2024 adventure-binding migrations."""

from src.rulesets.dnd2024.adventure_migrations import (
    apply_unreleased_adventure_binding_migration,
    migrate_unreleased_adventure_binding,
)

__all__ = [
    "apply_unreleased_adventure_binding_migration",
    "migrate_unreleased_adventure_binding",
]
