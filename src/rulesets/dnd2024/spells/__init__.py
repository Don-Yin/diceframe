"""D&D 2024 spell catalog and selection rules."""

from .catalog import Dnd2024SpellCatalog, SpellCatalogError

__all__ = ["Dnd2024SpellCatalog", "Dnd2024SpellSelection", "SpellCatalogError"]


def __getattr__(name: str):
    if name == "Dnd2024SpellSelection":
        from .selection import Dnd2024SpellSelection

        return Dnd2024SpellSelection
    raise AttributeError(name)
