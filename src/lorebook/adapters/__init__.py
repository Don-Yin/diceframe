"""External lorebook adapters; adapters never write the store."""
from .legacy import from_legacy_entries
from .lorebook_v3 import from_lorebook_v3
from .sillytavern import from_sillytavern

__all__ = ["from_legacy_entries", "from_lorebook_v3", "from_sillytavern"]
