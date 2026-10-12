"""Compatibility facade over the host application's character-card port.

The compatibility layer deliberately knows nothing about WebUI modules.  A
host object supplies the public operations, keeping dependency flow toward the
application boundary instead of importing a concrete transport service.
"""

__all__ = [
    "export_character_cards", "import_character_card", "list_character_cards",
    "save_character_card", "update_character_card",
]


def _operation(host, name: str):
    implementation = getattr(host, name, None)
    if not callable(implementation):
        raise TypeError(f"character-card host does not provide {name}()")
    return implementation


def list_character_cards(host, *args, **kwargs):
    return _operation(host, "list_character_cards")(*args, **kwargs)


def save_character_card(host, *args, **kwargs):
    return _operation(host, "save_character_card")(*args, **kwargs)


def update_character_card(host, *args, **kwargs):
    return _operation(host, "update_character_card")(*args, **kwargs)


def export_character_cards(host, *args, **kwargs):
    return _operation(host, "export_character_cards")(*args, **kwargs)


async def import_character_card(host, *args, **kwargs):
    return await _operation(host, "import_character_card")(*args, **kwargs)
