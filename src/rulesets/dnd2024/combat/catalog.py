"""Validated compact combat mechanics from the SRD bundle."""

from __future__ import annotations

import re
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

from src.rulesets.bundle import LoadedRulesetBundle


DICE_RE = re.compile(r"^[1-9]\d*d(?:4|6|8|10|12|20)(?:\+[1-9]\d*)?$")
# 固定伤害（例如徒手打击的 1 点基础伤害）：没有骰子，因此重击不翻倍。
FLAT_DAMAGE_RE = re.compile(r"^[1-9]\d{0,3}$")
SPELL_MODES = frozenset({
    "spell_attack", "saving_throw", "healing", "automatic_damage", "buff", "debuff",
})


class CombatCatalogError(ValueError):
    """Raised when compact combat data cannot be used authoritatively."""


@dataclass(frozen=True, slots=True)
class Dnd2024CombatCatalog:
    source_ref: str
    weapons: dict[str, dict[str, Any]]
    spell_effects: dict[str, dict[str, Any]]
    # 徒手打击是每个 player-like actor 的天然攻击能力，不是捆绑物品；
    # 因此它有自己的 compact 档案，而不是混进 weapons（weapons 全部必须是 item）。
    unarmed_strike: dict[str, Any] | None = None
    labels: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_bundle(cls, bundle: LoadedRulesetBundle) -> Dnd2024CombatCatalog:
        raw = bundle.get("combat_catalog", "srd_combat_core")
        if raw is None:
            raise CombatCatalogError("D&D 2024 combat catalog is missing")
        weapons = raw.get("weapons")
        effects = raw.get("spell_effects")
        if not isinstance(weapons, dict) or not isinstance(effects, dict):
            raise CombatCatalogError("combat weapons and spell effects must be objects")
        item_ids = {str(item["id"]) for item in bundle.list("item")}
        for weapon_id, weapon in weapons.items():
            if weapon_id not in item_ids or not isinstance(weapon, dict):
                raise CombatCatalogError(f"combat weapon is not a bundled item: {weapon_id}")
            if not DICE_RE.fullmatch(str(weapon.get("damage") or "")):
                raise CombatCatalogError(f"combat weapon damage is invalid: {weapon_id}")
            if not 5 <= int(weapon.get("range", 0) or 0) <= 600:
                raise CombatCatalogError(f"combat weapon range is invalid: {weapon_id}")
        spell_catalog = bundle.get("spell_catalog", "srd_spells") or {}
        spell_ids = {
            str(item.get("id") or "") for item in spell_catalog.get("spells", [])
            if isinstance(item, dict)
        }
        for spell_id, effect in effects.items():
            if spell_id not in spell_ids or not isinstance(effect, dict):
                raise CombatCatalogError(f"combat spell is not in the spell catalog: {spell_id}")
            if effect.get("mode") not in SPELL_MODES:
                raise CombatCatalogError(f"combat spell mode is invalid: {spell_id}")
            for dice_field in ("damage", "healing", "upcast_damage", "upcast_healing"):
                dice = effect.get(dice_field)
                if dice is not None and not DICE_RE.fullmatch(str(dice)):
                    raise CombatCatalogError(
                        f"combat spell {dice_field} is invalid: {spell_id}"
                    )
            if not 5 <= int(effect.get("range", 0) or 0) <= 600:
                raise CombatCatalogError(f"combat spell range is invalid: {spell_id}")
        labels = raw.get("labels") or {}
        if not isinstance(labels, dict):
            raise CombatCatalogError("combat catalog labels must be an object")
        return cls(
            source_ref=str(raw.get("source_ref") or ""),
            weapons=deepcopy(weapons),
            spell_effects=deepcopy(effects),
            unarmed_strike=deepcopy(cls._validated_unarmed_strike(raw.get("unarmed_strike"))),
            labels={str(key): str(value) for key, value in labels.items()},
        )

    @staticmethod
    def _validated_unarmed_strike(raw: Any) -> dict[str, Any] | None:
        """Validate the optional canonical Unarmed Strike profile.

        Missing data means "this content does not declare unarmed strikes": the
        engine then exposes none, instead of inventing mechanics in code.
        """

        if raw is None:
            return None
        if not isinstance(raw, dict):
            raise CombatCatalogError("combat unarmed strike profile must be an object")
        damage = str(raw.get("damage") or "")
        if not (DICE_RE.fullmatch(damage) or FLAT_DAMAGE_RE.fullmatch(damage)):
            raise CombatCatalogError("combat unarmed strike damage is invalid")
        if not str(raw.get("damage_type") or "").strip():
            raise CombatCatalogError("combat unarmed strike damage type is invalid")
        if not 5 <= int(raw.get("range", 0) or 0) <= 600:
            raise CombatCatalogError("combat unarmed strike range is invalid")
        return raw
