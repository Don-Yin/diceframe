"""Validated compact spell metadata sourced from SRD 5.2.1."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from src.rulesets.bundle import LoadedRulesetBundle


SCHOOLS = frozenset({
    "abjuration", "conjuration", "divination", "enchantment",
    "evocation", "illusion", "necromancy", "transmutation",
})
COMPONENTS = frozenset({"V", "S", "M"})


class SpellCatalogError(ValueError):
    """Raised when spell catalog or selections are not mechanically valid."""


def _spell_id(spell_ref: str) -> str:
    prefix = "spell:"
    value = str(spell_ref or "")
    return value[len(prefix):] if value.startswith(prefix) else ""


@dataclass(frozen=True, slots=True)
class Dnd2024SpellCatalog:
    content_version: str
    source_ref: str
    labels: dict[str, str]
    spells: dict[str, dict[str, Any]]

    @classmethod
    def from_bundle(cls, bundle: LoadedRulesetBundle) -> Dnd2024SpellCatalog:
        raw = bundle.get("spell_catalog", "srd_spells")
        if raw is None:
            raise SpellCatalogError("D&D 2024 spell catalog is missing")
        rows = raw.get("spells")
        if not isinstance(rows, list) or len(rows) != 339:
            raise SpellCatalogError("SRD 5.2.1 spell catalog must contain exactly 339 spells")
        labels = raw.get("labels")
        if not isinstance(labels, dict):
            raise SpellCatalogError("spell catalog locale labels are missing")
        spells: dict[str, dict[str, Any]] = {}
        for row in rows:
            if not isinstance(row, dict):
                raise SpellCatalogError("spell catalog row must be an object")
            spell_id = str(row.get("id") or "")
            if not spell_id or spell_id in spells:
                raise SpellCatalogError(f"invalid or duplicate spell id: {spell_id}")
            level = row.get("level")
            if isinstance(level, bool) or not isinstance(level, int) or not 0 <= level <= 9:
                raise SpellCatalogError(f"spell:{spell_id} has an invalid level")
            if row.get("school") not in SCHOOLS:
                raise SpellCatalogError(f"spell:{spell_id} has an invalid school")
            class_refs = row.get("class_refs")
            if not isinstance(class_refs, list) or not class_refs:
                raise SpellCatalogError(f"spell:{spell_id} must belong to a class list")
            components = row.get("components")
            if not isinstance(components, list) or not set(components).issubset(COMPONENTS):
                raise SpellCatalogError(f"spell:{spell_id} has invalid components")
            if not isinstance(row.get("ritual"), bool) or not isinstance(
                row.get("concentration"), bool
            ):
                raise SpellCatalogError(f"spell:{spell_id} flags must be booleans")
            if not all(
                str(row.get(field) or "").strip()
                for field in ("casting_time", "range", "duration")
            ) or not components:
                raise SpellCatalogError(f"spell:{spell_id} metadata is incomplete")
            if len(str(row["casting_time"])) > 240 or len(str(row["range"])) > 100:
                raise SpellCatalogError(f"spell:{spell_id} metadata contains description prose")
            if not str(row.get("source_ref") or "").startswith("srd-5.2.1:p"):
                raise SpellCatalogError(f"spell:{spell_id} source_ref is invalid")
            if not str(labels.get(spell_id) or "").strip():
                raise SpellCatalogError(f"spell:{spell_id} has no locale label")
            spells[spell_id] = deepcopy(row)
        if set(labels) != set(spells):
            raise SpellCatalogError("spell locale labels must cover the catalog exactly")
        return cls(
            content_version=bundle.manifest.content_version,
            source_ref=str(raw["source_ref"]),
            labels={str(key): str(value) for key, value in labels.items()},
            spells=spells,
        )

    def get(self, spell_ref: str) -> dict[str, Any] | None:
        spell_id = _spell_id(spell_ref)
        spell = self.spells.get(spell_id)
        if spell is None:
            return None
        return {**deepcopy(spell), "ref": f"spell:{spell_id}", "name": self.labels[spell_id]}

    def list_for_class(
        self, class_ref: str, *, maximum_level: int | None = None,
    ) -> list[dict[str, Any]]:
        if maximum_level is not None and not 0 <= maximum_level <= 9:
            raise SpellCatalogError("maximum spell level must be from 0 to 9")
        result = []
        for spell_id, spell in self.spells.items():
            if class_ref not in spell["class_refs"]:
                continue
            if maximum_level is not None and int(spell["level"]) > maximum_level:
                continue
            result.append({
                **deepcopy(spell),
                "ref": f"spell:{spell_id}",
                "name": self.labels[spell_id],
            })
        return sorted(result, key=lambda item: (item["level"], item["name"], item["id"]))

    def require(
        self, spell_refs: Any, *, class_ref: str, level: int, count: int, label: str,
    ) -> tuple[list[str], list[str]]:
        errors: list[str] = []
        if not isinstance(spell_refs, list) or any(not isinstance(item, str) for item in spell_refs):
            return [], [f"{label} must be an array of spell refs"]
        refs = list(spell_refs)
        if len(refs) != count:
            errors.append(f"{label} must contain exactly {count} spells")
        if len(set(refs)) != len(refs):
            errors.append(f"{label} must not contain duplicate spells")
        for ref in refs:
            spell = self.get(ref)
            if spell is None:
                errors.append(f"{label} contains unknown spell {ref}")
                continue
            if class_ref not in spell["class_refs"]:
                errors.append(f"{ref} is not on the {class_ref} spell list")
            spell_level = int(spell["level"])
            eligible = spell_level == 0 if level == 0 else 1 <= spell_level <= level
            if not eligible:
                errors.append(f"{ref} is not eligible at spell level {level}")
        return refs, errors
