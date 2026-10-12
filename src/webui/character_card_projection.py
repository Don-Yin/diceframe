"""Pure identity and deduplication helpers for reusable character cards."""

from __future__ import annotations

from typing import Any

from src.engine.world.contracts import canonical_id, validate_source_ref

#: Card key holding the server-recorded import provenance of a library card.
#: Only server-side import code writes it; client saves never may.
CARD_PROVENANCE_KEY = "provenance"

#: ``tracked``: the card is the one library copy a source pushes updates into.
#: ``detached``: the card came from that source but no longer follows it.
CARD_PROVENANCE_LINKS = frozenset({"tracked", "detached"})

_PROVENANCE_TEXT_FIELDS = (
    "source_version", "source_digest", "imported_state_digest", "imported_at",
    "pushed_by_device", "book_id",
)


def normalize_card_provenance(value: Any) -> dict[str, str] | None:
    """Return a well-formed provenance object, or ``None`` (fail closed).

    The identity triple must be canonical and the link explicit; a malformed
    object is dropped rather than repaired, so it can never make a card look
    tracked by a source it does not belong to.
    """

    if not isinstance(value, dict):
        return None
    source_kind = value.get("source_kind")
    source_id = value.get("source_id")
    external_id = value.get("external_id")
    link = value.get("link")
    if not all(isinstance(item, str) for item in (source_kind, source_id, external_id, link)):
        return None
    if link not in CARD_PROVENANCE_LINKS:
        return None
    try:
        validate_source_ref(f"{source_kind}:{source_id}")
        canonical_id(source_id, field="source id")
        canonical_id(external_id, field="external id")
    except ValueError:
        return None
    normalized = {
        "source_kind": str(source_kind),
        "source_id": str(source_id),
        "external_id": str(external_id),
        "link": str(link),
    }
    for key in _PROVENANCE_TEXT_FIELDS:
        text = value.get(key)
        if isinstance(text, str) and text:
            normalized[key] = text
    return normalized


def card_provenance(card: dict[str, Any]) -> dict[str, str] | None:
    return normalize_card_provenance(card.get(CARD_PROVENANCE_KEY))


def has_card_provenance(card: dict[str, Any]) -> bool:
    """The card was imported from a tracked source (tracked or detached)."""

    return card_provenance(card) is not None


def is_tracked_card(card: dict[str, Any]) -> bool:
    provenance = card_provenance(card)
    return provenance is not None and provenance["link"] == "tracked"


def is_plugin_card(card: dict[str, Any]) -> bool:
    """Content shipped by an installed plugin (it owns the card)."""

    return bool(str(card.get("source_plugin") or "").strip())


def card_signature(card: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(card.get("character_name") or "").strip().lower(),
        str(card.get("race") or "").strip().lower(),
        str(card.get("class") or "").strip().lower(),
        str(card.get("background") or "").strip().lower(),
        str(card.get("rule_id") or "").strip().lower(),
    )


def dedupe_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep one card per character; plugin content never merges with a
    table-saved card of the same character (it keeps its provenance).

    A card with import provenance is identified by its own id and never
    merged by signature: two devices' copies of the same character, or a kept
    copy next to its duplicate, are distinct cards.
    """
    seen: dict[tuple[str, ...], dict[str, Any]] = {}
    order: list[tuple[str, ...]] = []
    for card in cards:
        if not isinstance(card, dict):
            continue
        signature: tuple[str, ...]
        if has_card_provenance(card):
            signature = ("provenance", str(card.get("id") or f"anon_{len(order)}"))
        else:
            signature = card_signature(card)
            if not signature[0]:
                signature = (
                    str(card.get("id") or f"anon_{len(order)}"),
                    "",
                    "",
                    "",
                    "",
                )
            signature = (*signature, str(card.get("source_plugin") or "").strip())
        if signature not in seen:
            order.append(signature)
        seen[signature] = card
    return [seen[signature] for signature in order]
