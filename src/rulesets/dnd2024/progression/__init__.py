"""D&D 2024 level progression models."""

from .catalog import Dnd2024ProgressionCatalog, ProgressionCatalogError

__all__ = [
    "Dnd2024AdvancementEngine",
    "Dnd2024ProgressionCatalog",
    "ProgressionCatalogError",
]


def __getattr__(name: str):
    if name == "Dnd2024AdvancementEngine":
        from .advancement import Dnd2024AdvancementEngine

        return Dnd2024AdvancementEngine
    raise AttributeError(name)
